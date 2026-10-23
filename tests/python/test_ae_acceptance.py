"""Cross-module regressions against the default host; never uses paid providers."""
import asyncio
import json
import time
from contextlib import aclosing
from types import SimpleNamespace

from backend.xueya.agent import Agent
from backend.xueya.common import AppError, utc_now
from backend.xueya.mcp_core import open_session, platform_registry


def wait_job(client, headers, job):
    for _ in range(300):
        current = client.get('/api/platform/jobs/status?id='+job['id'], headers=headers).json()['job']
        if current['status'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
            return current
        time.sleep(.02)
    raise AssertionError('job timeout')


def test_default_upload_uses_b_and_failed_replacement_keeps_evidence(client):
    h = client.platform_headers
    def upload(key, body, previous=''):
        response = client.post('/api/platform/documents/upload?name=biology.md'+('&previousDocumentId='+previous if previous else ''),
                               headers={**h, 'Idempotency-Key': key}, content=body)
        assert response.status_code == 200, response.text
        return wait_job(client, h, response.json()['job'])
    job = upload('first', '# Biology\n\nPhotosynthesis occurs in chloroplasts.'.encode())
    assert job['type'] == 'rag-parse' and job['status'] == 'succeeded'
    doc_id = job['result']['documentId']
    doc = client.platform.document(client.platform.scope(), doc_id)
    assert doc['activeArtifact'] and doc['chunks'][0]['blockId']
    bad = upload('invalid-replacement', bytes([255]), doc_id)
    assert bad['status'] == 'failed'
    original = client.platform.document(client.platform.scope(), doc_id)
    assert not original.get('superseded')
    source = original['chunks'][-1]
    result = client.post('/api/platform/tools/call', headers=h,
        json={'name': 'search_materials', 'arguments': {'query': 'Photosynthesis'}}).json()
    assert source['id'] in [s['id'] for s in result['data']['sources']]
    saved = client.post('/api/platform/documents/update', headers=h, json={'documentId': doc_id,
        'version': original['version'], 'changes': {'name': 'biology.md', 'chapter': 'Unit 1', 'tags': ['bio']}}).json()['document']
    assert saved['chapter'] == 'Unit 1'
    result = client.post('/api/platform/documents/remove', headers=h, json={'documentId': doc_id, 'version': saved['version']})
    assert result.json()['removed']
    assert client.platform.repo.read(client.platform.scope(), 'artifact', original['activeArtifact']) is None


def test_main_agent_general_greeting_and_course_refusal():
    class Provider:
        config = SimpleNamespace(model='controlled')
        calls = 0
        async def stream(self, messages, **kwargs):
            self.calls += 1
            assert '通用问答' in messages[0]['content']
            yield {'type': 'content', 'text': '巴黎。', 'model': 'controlled'}
    provider = Provider()
    async def call(value):
        async with aclosing(Agent(provider).workflow(value)) as events:
            return [e async for e in events][-1]
    greeting = asyncio.run(call({'question': '你好'}))
    assert '你好' in greeting['answer'] and provider.calls == 0
    result = asyncio.run(call({'question': '法国首都在哪里？'}))
    assert result['engine'] == 'general-chat' and not result['sources'] and provider.calls == 1
    refused = asyncio.run(call({'question': '根据讲义，法国首都在哪里？'}))
    assert not refused['sources'] and provider.calls == 1


def test_mcp_reads_c_artifacts_and_isolates_courses(client):
    host = client.app.state.learning
    p = client.platform
    p.repo.ensure_course(p.user_id, {'id': 'other', 'name': 'Other'})
    async def check():
        await host.repo.commit({'courseId': 'course-default', 'id': 'c-note', 'operationId': 'test-note',
            'requestHash': 'test', 'expectedRevision': 0, 'value': {'id': 'c-note', 'kind': 'note',
            'courseId': 'course-default', 'revision': 1, 'content': {'text': 'C note'}}})
        await host.repo.commit({'courseId': 'course-default', 'id': 'c-attempt', 'operationId': 'test-attempt',
            'requestHash': 'test', 'expectedRevision': 0, 'value': {'id': 'c-attempt', 'kind': 'attempt',
            'courseId': 'course-default', 'revision': 1, 'content': {'questionSnapshots': [{'id': 'c-q', 'prompt': '树的组成', 'sourceId': 's'}],
            'events': [{'questionId': 'c-q', 'createdAt': utc_now(), 'grade': {'status': 'graded', 'score': 0, 'maxScore': 1}}]}}})
        for course, expected in [('course-default', ['c-note']), ('other', [])]:
            async with open_session(platform_registry(p, p.scope(course), learning=host, rag=client.app.state.rag)) as session:
                found = await session.call('list_notes')
                assert [r['id'] for r in found['items']] == expected
                progress = await session.call('analyze_progress')
                assert progress['total'] == (1 if expected else 0)
                wrong = await session.call('list_wrong_questions')
                assert [q['id'] for q in wrong['items']] == (['c-q'] if expected else [])
                graph = await session.call('get_course_graph')
                assert graph['courseId'] == course
    asyncio.run(check())


def test_artifact_pages_filter_before_pagination(client):
    host = client.app.state.learning
    async def prepare():
        for i in range(25):
            key = 'a-note-'+str(i).zfill(2)
            await host.repo.commit({'courseId': 'course-default', 'id': key, 'operationId': key,
                'requestHash': key, 'expectedRevision': 0, 'value': {'id': key, 'kind': 'note', 'revision': 1, 'content': {}}})
        await host.repo.commit({'courseId': 'course-default', 'id': 'z-card', 'operationId': 'z-card',
            'requestHash': 'card', 'expectedRevision': 0, 'value': {'id': 'z-card', 'kind': 'memory-card', 'revision': 1, 'content': {}}})
    asyncio.run(prepare())
    headers = client.platform_headers
    workspace = client.get('/api/learning/workspace?kinds=memory-card', headers=headers).json()['result']
    assert [r['id'] for r in workspace['artifacts']] == ['z-card'] and not workspace['hasMore']
    first = client.get('/api/learning/artifacts?kinds=note', headers=headers).json()['result']
    assert len(first['items']) == 20 and first['next']
    second = client.get('/api/learning/artifacts?kinds=note&after='+first['next'], headers=headers).json()['result']
    assert len(second['items']) == 5 and not second['next']


def test_direct_and_practice_use_course_owned_quotes(platform):
    class Provider:
        config = SimpleNamespace(model='controlled')
        messages = None
        async def generate(self, messages, **kwargs):
            self.messages, self.scope = messages, kwargs['scope']
            return {'content': json.dumps({'answer': '原文', 'sources': ['s']}), 'model': 'controlled'}
    p = platform
    p.repo.ensure_course(p.user_id, {'id': 'biology', 'name': 'Biology'})
    scope = p.scope('biology')
    p.repo.put(scope, 'source', 's', {'id': 's', 'quote': '真正的课程原文', 'title': '真实标题', 'location': '段落1'})
    provider = Provider()
    async def check():
        async with aclosing(Agent(provider, p).direct({'question': '问题', 'courseId': 'biology',
            'sources': [{'id': 's', 'quote': '客户端伪造'}]})) as events:
            assert [e async for e in events][-1]['sources'] == ['s']
        assert provider.scope.course_id == 'biology'
        assert '真正的课程原文' in provider.messages[-1]['content'] and '伪造' not in provider.messages[-1]['content']
        try:
            await Agent(provider, p).practice('topics', {'courseId': 'biology', 'sources': [{'id': 'elsewhere', 'quote': '其他课程'}]})
        except AppError as error:
            assert error.code == 'NO_SOURCES'
        else:
            raise AssertionError('foreign evidence accepted')
    asyncio.run(check())


def test_large_course_catalog_stays_usable_while_generation_is_bounded(client):
    p = client.platform
    for i in range(2):
        p.repo.put(p.scope(), 'source', 'large-'+str(i), {'id': 'large-'+str(i), 'title': 'Large lecture', 'quote': '课程原文'*50000})
    headers = client.platform_headers
    page = client.get('/api/learning/workspace', headers=headers)
    assert page.status_code == 200, page.text
    assert all(len(s['quote']) <= 1500 for s in page.json()['result']['sources'])
    refused = client.post('/api/learning/summary/preview', headers=headers, json={'id': 'large-summary'})
    assert refused.json()['error'] == 'CHAPTER_BUDGET_EXCEEDED'


def test_agent_does_not_publish_deleted_evidence_after_model_returns(platform):
    p = platform
    p.repo.put(p.scope(), 'source', 'bst', {'id': 'bst', 'title': 'BST', 'quote': 'BST lookup is O(h).', 'location': 'Paragraph 1'})
    class Provider:
        config = SimpleNamespace(model='controlled')
        async def stream(self, messages, **kwargs):
            row = p.repo.read(p.scope(), 'source', 'bst')
            p.repo.put(p.scope(), 'source', 'bst', row['value'], row['version'], deleted=True)
            yield {'type': 'content', 'text': json.dumps({'answer': 'BST lookup is O(h).', 'sources': ['bst']})}
    async def check():
        async with aclosing(Agent(Provider(), p).workflow({'question': 'BST lookup?', 'sources': ['bst']})) as events:
            result = [e async for e in events][-1]
        assert not result['sources'] and '更新或移除' in result['answer']
    asyncio.run(check())
