import asyncio
import json
import pytest
import httpx
from backend.core import DomainError, clone
from backend.platform import Platform
from backend.platform.backup import create_backup, restore_backup
from backend.platform.learning_repository import LearningRepository
from backend.agent.learning_service import LearningService
from backend.app import create_app
from backend.config import ROOT
from backend.mcp.platform_server import open_platform_session


@pytest.fixture
def platform(tmp_path):
    result = Platform(tmp_path/'data')
    yield result
    result.db.close()


def workspace():
    return {'version': 3, 'activeId': 'course-default', 'courses': [{'id': 'course-default', 'name': '数据结构', 'data': {'documents': [], 'cards': [], 'records': [], 'bank': [], 'plan': [], 'sessions': []}}]}


def test_sqlite_cas_scope_and_cursor_isolation(platform):
    repo, scope = platform.repository, platform.scope('course-default')
    for index in range(3):
        repo.put(scope, 'note', 'n'+str(index), {'content': str(index)}, 0)
    with pytest.raises(DomainError, match='VERSION_CONFLICT'):
        repo.put(scope, 'note', 'n0', {'content': 'bad'}, 0)
    first = repo.page(scope, 'note', limit=1)
    assert len(first['items']) == 1 and first['nextCursor']
    platform.repository.ensure_course(platform.user_id, {'id': 'other', 'name': '其他课程'})
    with pytest.raises(DomainError, match='INVALID_CURSOR'):
        repo.page(platform.scope('other'), 'note', first['nextCursor'])
    with pytest.raises(DomainError, match='COURSE_NOT_FOUND'):
        repo.read({'userId': 'other-user', 'courseId': 'course-default'}, 'note', 'n0')
    repo.ensure_course(platform.user_id, {'id': 'other', 'name': '其他课程', 'archived': True})
    with pytest.raises(DomainError, match='COURSE_ARCHIVED'):
        repo.put({'userId': platform.user_id, 'courseId': 'other'}, 'note', 'n', {})


def test_workspace_migration_backup_idempotency(platform):
    value = workspace()
    preview = platform.migration.preview(platform.user_id, {'workspace': value, 'raw': {'old-key': 'original'}})
    assert not platform.repository.get_workspace(platform.user_id)
    result = platform.migration.apply(platform.user_id, {'id': preview['id'], 'hash': preview['hash']})
    assert result['version'] == 1
    assert platform.migration.apply(platform.user_id, {'id': preview['id'], 'hash': preview['hash']})['alreadyImported']
    assert platform.migration.backup(platform.user_id, result['backupId'])['raw']['old-key'] == 'original'
    with pytest.raises(DomainError, match='VERSION_CONFLICT'):
        platform.repository.save_workspace(platform.user_id, value, 0)


async def test_real_mcp_confirmed_action_survives_restart_and_receipt_is_atomic(platform):
    scope = platform.scope('course-default')
    async with open_platform_session(platform, scope) as session:
        names = {t['name'] for t in await session.list_tools()}
        assert 'prepare_action' in names and 'apply_action' in names and 'confirm_action' not in names
        preview = await session.call('prepare_action', {'kind': 'note', 'entityId': 'n', 'expectedVersion': 0, 'after': {'title': '新笔记', 'content': '正文', 'sourceIds': []}})
    assert not platform.repository.read(scope, 'note', 'n')
    with pytest.raises(DomainError, match='ACTION_CONFIRMATION_REQUIRED'):
        await platform.authority.apply(scope, preview['actionId'])
    platform.authority.confirm(scope, {'actionId': preview['actionId'], 'digest': preview['digest']})
    from backend.mcp.actions import ActionAuthority
    restarted = ActionAuthority(platform.repository)
    receipt = await restarted.apply(scope, preview['actionId'])
    assert await restarted.apply(scope, preview['actionId']) == receipt
    assert platform.repository.read(scope, 'note', 'n')['value']['content'] == '正文'
    assert platform.db.one('SELECT COUNT(*) AS n FROM audits')['n'] == 1
    assert platform.db.one('SELECT COUNT(*) AS n FROM receipts')['n'] == 1


async def test_source_change_invalidates_confirmed_action(platform):
    scope = platform.scope('course-default')
    platform.repository.put(scope, 'source', 's', {'quote': '原始原文'}, 0)
    preview = await platform.authority.prepare(scope, {'kind': 'question', 'entityId': 'q', 'expectedVersion': 0, 'after': {'prompt': '题干', 'answer': '答案', 'sourceIds': ['s']}})
    platform.authority.confirm(scope, {'actionId': preview['actionId'], 'digest': preview['digest']})
    platform.repository.put(scope, 'source', 's', {'quote': '修改后的原文'}, 1)
    with pytest.raises(DomainError, match='SOURCE_VERSION_CONFLICT'):
        await platform.authority.apply(scope, preview['actionId'])
    assert not platform.repository.read(scope, 'question', 'q')


async def test_parse_job_original_file_progress_and_idempotent_upload(platform):
    scope = platform.scope('course-default')
    data = 'Python 后台资料解析，节点是树的组成部分。'.encode()
    job = platform.upload(scope, '课程.md', data, 'upload-1')
    assert platform.upload(scope, '课程.md', data, 'upload-1')['id'] == job['id']
    with pytest.raises(DomainError, match='IDEMPOTENCY_CONFLICT'):
        platform.upload(scope, '课程.md', b'changed', 'upload-1')
    await platform.jobs.tick()
    for _ in range(100):
        current = platform.jobs.get(job['id'], platform.user_id)
        if current['status'] in ('succeeded', 'failed', 'unknown', 'cancelled'):
            break
        await asyncio.sleep(.05)
    assert current['status'] == 'succeeded', current
    document = platform.document(scope, current['result']['documentId'])
    assert document['status'] == '已解析，可检索'
    assert platform.files.read(document['fileHash']) == data
    assert platform.repository.all(scope, 'source')
    assert any(e.get('progress') for e in platform.jobs.events(job['id'], platform.user_id))


async def test_job_api_unknown_not_retried_and_cpu_cancellation(platform):
    async def uncertain(job, **options):
        raise RuntimeError('remote-outcome-unknown')
    platform.jobs.register('paid-job', uncertain)
    job = platform.jobs.submit(platform.user_id, {'courseId': 'course-default', 'type': 'paid-job', 'input': {}, 'idempotencyKey': 'paid', 'resource': 'api'})
    await platform.jobs.tick()
    await asyncio.sleep(.05)
    assert platform.jobs.get(job['id'], platform.user_id)['status'] == 'unknown'
    with pytest.raises(DomainError, match='JOB_NOT_RETRYABLE'):
        platform.jobs.retry(job['id'], platform.user_id)
    entered = asyncio.Event()
    async def slow(job, **options):
        entered.set()
        await asyncio.sleep(60)
    platform.jobs.register('slow', slow)
    job = platform.jobs.submit(platform.user_id, {'courseId': 'course-default', 'type': 'slow', 'idempotencyKey': 'slow'})
    await platform.jobs.tick()
    await entered.wait()
    platform.jobs.cancel(job['id'], platform.user_id)
    await asyncio.sleep(.02)
    assert platform.jobs.get(job['id'], platform.user_id)['status'] == 'cancelled'


async def test_c_learning_ports_are_durable_in_real_sqlite(platform, course):
    scope = platform.scope('course-default')
    platform.repository.ensure_course(platform.user_id, {'id': 'course', 'name': '合成课程'})
    repository = LearningRepository(platform)
    service = LearningService(repository, clock=lambda: '2026-10-15T01:00:00Z')
    draft = await service.preview_learning_package({**course, 'id': 'package'})
    first = await service.artifacts.adopt(draft, {'confirmed': True, 'operationId': 'adopt'})
    assert await LearningRepository(platform).get('course', 'package') == first
    assert await service.artifacts.adopt(draft, {'confirmed': True, 'operationId': 'adopt'}) == first


def test_backup_restore_checksums_and_new_directory(platform, tmp_path):
    scope = platform.scope('course-default')
    file = platform.files.put(b'original bytes')
    platform.repository.put(scope, 'document', 'd', {'fileHash': file['hash']})
    source, target = tmp_path/'backup', tmp_path/'restored'
    create_backup(platform, source)
    restore_backup(source, target)
    restored = Platform(target, recover=False)
    assert restored.files.read(file['hash']) == b'original bytes'
    restored.db.close()
    with pytest.raises(DomainError, match='RESTORE_REQUIRES_NEW_DIRECTORY'):
        restore_backup(source, target)
    (source/'files'/file['hash'][:2]/file['hash']).write_bytes(b'tampered')
    with pytest.raises(DomainError, match='BACKUP_CHECKSUM_MISMATCH'):
        restore_backup(source, tmp_path/'bad')


async def test_platform_http_auth_migration_actions_and_private_files(platform):
    app = create_app({'root': ROOT, 'ai': {}}, platform=platform)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:4173') as client:
        assert (await client.get('/api/platform/workspace')).status_code == 403
        bootstrap = (await client.get('/api/platform/bootstrap')).json()
        headers = {'X-Xueya-Token': bootstrap['token']}
        assert (await client.get('/api/platform/bootstrap', headers={'Origin': 'http://evil.example'})).status_code == 403
        saved = (await client.put('/api/platform/workspace', headers=headers, json={'workspace': workspace(), 'expectedVersion': 0})).json()
        assert saved['workspace']['version'] == 1
        assert (await client.put('/api/platform/workspace', headers=headers, json={'workspace': workspace(), 'expectedVersion': 0})).status_code == 409
        tools = (await client.get('/api/platform/tools?courseId=course-default', headers=headers)).json()
        assert tools['ok'] and len(tools['tools']) >= 14
        preview = (await client.post('/api/platform/tools/call', headers=headers, json={'name': 'prepare_action', 'arguments': {'kind': 'note', 'entityId': 'n', 'expectedVersion': 0, 'after': {'title': '笔记', 'content': '内容', 'sourceIds': []}}})).json()['data']
        denied = await client.post('/api/platform/tools/call', headers=headers, json={'name': 'apply_action', 'arguments': {'actionId': preview['actionId']}})
        assert denied.status_code == 400
        assert (await client.post('/api/platform/actions/confirm', headers=headers, json={'actionId': preview['actionId'], 'digest': preview['digest']})).json()['ok']
        assert (await client.post('/api/platform/tools/call', headers=headers, json={'name': 'apply_action', 'arguments': {'actionId': preview['actionId']}})).json()['ok']
        assert len((await client.get('/api/platform/audit', headers=headers)).json()['audits']) == 1
        assert (await client.get('/.xueya-data/workspace.sqlite')).status_code == 404
