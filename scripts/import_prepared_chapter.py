"""Import selected original PDF pages as a separate, unconfirmed knowledge base.

No OCR, embedding or chat provider is constructed. Validation defaults to an
isolated temporary store; --apply requires the desktop host to be stopped.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

from backend.xueya.common import digest, require
from backend.xueya.config import load_config
from backend.xueya.knowledge_base import KnowledgeBase
from backend.xueya.library_http import Library
from backend.xueya.platform import Platform
from backend.xueya.rag_service import RagService
from backend.xueya.server import pid_alive
from scripts.import_prepared_pdf import finish


async def import_draft(p, content, pack, *, name, key):
    require(isinstance(pack.get('selectedPages'), list) and pack['selectedPages'], 'CHAPTER_PAGES_REQUIRED')
    require(len(content) <= 64*1024*1024, 'FILE_TOO_LARGE')
    require(hashlib.sha256(content).hexdigest() == pack.get('sourceFileHash'), 'PREPARED_PDF_HASH_MISMATCH')
    rag = RagService(p)  # Intentionally has no external providers or publish hook.
    app = SimpleNamespace(state=SimpleNamespace(platform=p, rag=rag))
    app.state.library = Library(app)
    kb = KnowledgeBase(app)
    course = kb.create({'name': name, 'description': '仅收录栈与队列一章的文字与代码；校正版等待人工核对，不包含图片向量。',
                        'idempotencyKey': key})
    scope = p.scope(course['id'])
    pages = pack['selectedPages']
    filename = f'栈与队列（原PDF第{pages[0]}至{pages[-1]}页）.pdf'
    p.jobs.stopped = False
    uploaded = kb.upload(scope, content, filename, '栈与队列', key+'-original', review=True)
    await finish(p, uploaded['job'])
    result = await finish(p, rag.prepared_pdf.submit(scope, uploaded['documentId'], pack, 'chapter-text-'+digest(pack, canonical=True)))
    doc = rag.document(scope, uploaded['documentId'])
    artifact = rag.artifact(scope, doc)
    require([page['number'] for page in artifact['pages']] == pages and bool(doc['chunks']), 'CHAPTER_SCOPE_CHECK_FAILED')
    for source in doc['chunks']:
        require(source['page'] in pages, 'CHAPTER_SCOPE_CHECK_FAILED')
        rag._check_source(source, doc, artifact)
    # This tool cannot mark an AI transcription as human confirmed.
    require(not rag.reviewed(doc) and not rag.sources(scope) and not doc.get('embeddingIdentity'), 'CHAPTER_REVIEW_GATE_FAILED')
    return {'status': 'draft-awaiting-human-review', 'courseId': scope.course_id, 'documentId': doc['id'],
            'version': doc['version'], 'contentRevision': doc['contentRevision'],
            'pages': len(pages), 'pageSelection': doc['pageSelection'], 'sourceCount': len(doc['chunks']),
            'sourceFileHash': doc['fileHash'], 'textHash': artifact['textHash'], 'providerRequests': 0,
            'reviewConfirmed': False, 'vectorIndexed': False, 'result': result['result']}


async def run(args):
    content = args.pdf.read_bytes()
    pack = json.loads(args.prepared.read_text(encoding='utf-8'))
    if args.apply:
        config = load_config()
        lock = config.data_dir/'server.json'
        if lock.exists():
            require(not pid_alive(json.loads(lock.read_text('utf-8'))['pid']), 'STOP_HOST_BEFORE_IMPORT')
        p = Platform(config.data_dir, recover=False, preserve_legacy_data=True)
        try:
            require(not p.db.one("SELECT id FROM jobs WHERE status NOT IN ('succeeded','failed','cancelled','unknown') LIMIT 1"), 'WAIT_FOR_ACTIVE_JOBS')
            require(not p.db.one("SELECT id FROM invocations WHERE status='pending' LIMIT 1"), 'WAIT_FOR_ACTIVE_INVOCATIONS')
            return await import_draft(p, content, pack, name=args.name, key=args.key)
        finally:
            await p.close()
    with tempfile.TemporaryDirectory(prefix='xueya-chapter-check-') as directory:
        p = Platform(Path(directory), recover=False, preserve_legacy_data=True)
        try:
            report = await import_draft(p, content, pack, name=args.name, key=args.key)
            return {**report, 'status': 'validated-in-isolated-store', 'privateStoreModified': False}
        finally:
            await p.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--name', default='栈与队列（文字与代码）')
    parser.add_argument('--key', default='stack-queue-chapter-v1')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'pages', 'sourceCount', 'providerRequests')}, ensure_ascii=False))


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
