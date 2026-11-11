"""Install only the selected stack/queue Markdown; retire the previous corpus.

Requires an explicit owner/course, stopped host and new backup for --apply.
Other originals and learning history are retained. No external model calls.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace
from backend.xueya.account_scope import bind_owner
from backend.xueya.backup import create_backup
from backend.xueya.common import require
from backend.xueya.config import ROOT, load_config
from backend.xueya.document_catalog import is_demo_placeholder
from backend.xueya.knowledge_base import KnowledgeBase
from backend.xueya.library_http import Library
from backend.xueya.platform import Platform
from backend.xueya.rag_service import RagService
from backend.xueya.server import pid_alive


def inventory(root=ROOT):
    path = root/'materials/stack-queue/栈与队列知识库.md'
    content = path.read_bytes()
    require(bool(content), 'EMPTY_KNOWLEDGE_FILE')
    return [{'path': path, 'name': path.name, 'chapter': '栈与队列',
             'sha256': hashlib.sha256(content).hexdigest()}]


async def finish(p, scope, job):
    deadline = time.monotonic()+300
    while time.monotonic() < deadline:
        await p.jobs.tick()
        state = p.jobs.get(job['id'], scope.user_id)
        if state['status'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
            require(state['status'] == 'succeeded', 'CORPUS_JOB_FAILED:'+str(state['error']))
            return state
        await asyncio.sleep(.05)
    raise RuntimeError('CORPUS_JOB_TIMEOUT')


async def install(p, scope, items):
    require(len(items) == 1, 'SINGLE_KNOWLEDGE_FILE_REQUIRED')
    require(not p.db.one("SELECT id FROM jobs WHERE status IN ('queued','running','cancelling')"), 'ACTIVE_JOBS')
    require(not p.db.one("SELECT id FROM invocations WHERE status='pending'"), 'ACTIVE_INVOCATIONS')
    rag = RagService(p)
    host = SimpleNamespace(state=SimpleNamespace(platform=p, rag=rag))
    host.state.library = Library(host)
    kb = KnowledgeBase(host)
    p.jobs.stopped = False
    item = items[0]
    same = [d for d in p.repo.all(scope, 'document') if d.get('fileHash') == item['sha256']
            and not d.get('archived') and not d.get('superseded')]
    if same:
        doc_id = same[0]['id']
    else:
        uploaded = kb.upload(scope, item['path'].read_bytes(), item['name'], item['chapter'], 'corpus-'+item['sha256'])
        host.state.library.annotate(scope, uploaded['job'], {'origin': {'type': 'repository-corpus',
            'materialPath': str(item['path'].relative_to(ROOT)), 'sourceFileHash': item['sha256']}})
        await finish(p, scope, uploaded['job'])
        doc_id = uploaded['documentId']
    doc = rag.document(scope, doc_id)
    require(hashlib.sha256(p.files.read(doc['fileHash'])).hexdigest() == item['sha256'] and doc.get('chunks'), 'CORPUS_PUBLISH_FAILED')
    retired = []
    with p.db.transaction():
        profile_id = 'source-bound-knowledge-base'
        profile = p.repo.read(scope, 'artifact', profile_id)
        p.repo.put(scope, 'artifact', profile_id, {'kind': profile_id, 'name': '栈与队列知识库',
                   'documentId': doc_id, 'fileHash': item['sha256']}, profile['version'] if profile else 0)
        for other in p.repo.all(scope, 'document'):
            if other['id'] == doc_id or other.get('archived') or other.get('superseded'):
                continue
            # Undo only our previous corpus import, not unrelated private uploads.
            if (other.get('origin') or {}).get('type') == 'repository-corpus' or is_demo_placeholder(other):
                host.state.library.organize(scope, {'documentId': other['id'], 'version': other['version'], 'action': 'archive'})
                retired.append(other['id'])
        p.repo.ensure_course(scope.user_id, {'id': scope.course_id, 'name': '栈与队列知识库'})
        workspace = p.repo.get_workspace(scope.user_id)
        if workspace:
            value = workspace['data']
            for course in value['courses']:
                if course['id'] != scope.course_id:
                    continue
                course['name'] = '栈与队列知识库'
                data = course['data']
                data['documents'] = [d for d in data.get('documents', []) if d.get('id') not in retired]
                data['documentCount'] = 1
                data['selectedDocuments'] = [doc_id]
                for session in data.get('sessions', []):
                    if 'scopeDocumentIds' in session:
                        session['scopeDocumentIds'] = [d for d in session['scopeDocumentIds'] if d not in retired]
            p.repo.save_workspace(scope.user_id, value, workspace['version'])
    active = [d for d in p.repo.all(scope, 'document') if not any(d.get(k) for k in ('archived', 'superseded', 'deleted'))]
    require(len(active) == 1 and active[0]['id'] == doc_id, 'UNEXPECTED_ACTIVE_KNOWLEDGE_FILES')
    checks = []
    for query in ('循环队列', '后进先出', '单调栈', '两栈队列'):
        result = await rag.search(scope, query, mode='lexical')
        require(result['sources'] and all(s['documentId'] == doc_id and rag.validate(scope, s) for s in result['sources']), 'KNOWLEDGE_SCOPE_CHECK_FAILED')
        checks.append({'query': query, 'hits': len(result['sources']), 'onlySelectedFile': True})
    return {'status': 'passed', 'documents': [{'id': doc_id, 'name': doc['name'], 'sha256': doc['fileHash'], 'sources': len(doc['chunks'])}],
            'summary': kb.catalog(scope)['summary'], 'retiredDocumentIds': retired, 'checks': checks,
            'originalsRetained': True, 'providerRequests': 0}


async def run(args, items):
    require(args.owner and args.course_id and args.backup, 'EXPLICIT_OWNER_COURSE_AND_BACKUP_REQUIRED')
    config = load_config()
    lock = config.data_dir/'server.json'
    require(not lock.exists() or not pid_alive(json.loads(lock.read_text('utf-8'))['pid']), 'STOP_HOST_BEFORE_IMPORT')
    backup = create_backup(config.data_dir, args.backup)
    p = Platform(config.data_dir, recover=False, preserve_legacy_data=True)
    try:
        with bind_owner(args.owner):
            return {**await install(p, p.scope(args.course_id), items), 'backup': backup}
    finally:
        await p.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--owner')
    parser.add_argument('--course-id')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--output', type=Path, default=Path('test-results/stack-only/report.json'))
    args = parser.parse_args()
    items = inventory()
    result = (asyncio.run(run(args, items)) if args.apply else
              {'status': 'validated-only', 'documents': [{'name': i['name'], 'sha256': i['sha256']} for i in items], 'providerRequests': 0})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'providerRequests')}, ensure_ascii=False))


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
