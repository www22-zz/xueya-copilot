"""Import an original PDF and its prepared OCR companion without model requests.

Stop the local host first. Defaults to validation only; --apply publishes through
the existing CPU queue. --replace-ppt explicitly retires this course's old PPTs
only after real lexical/citation checks. No private learning data is purged.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time

from backend.xueya.common import require
from backend.xueya.config import load_config
from backend.xueya.platform import Platform
from backend.xueya.rag_service import RagService
from backend.xueya.knowledge_replacement import KnowledgeReplacement
from backend.xueya.server import pid_alive


async def finish(p, job):
    deadline = time.monotonic()+300
    while time.monotonic() < deadline:
        await p.jobs.tick()
        state = p.jobs.get(job['id'], p.user_id)
        if state['status'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
            require(state['status'] == 'succeeded', 'IMPORT_JOB_'+state['status'].upper()+': '+str(state['error']))
            return state
        await asyncio.sleep(.05)
    raise RuntimeError('IMPORT_JOB_TIMEOUT')


async def run(args):
    config = load_config()
    value = json.loads(args.prepared.read_text(encoding='utf-8'))
    require(args.pdf.stat().st_size <= 64*1024*1024, 'FILE_TOO_LARGE')
    content = args.pdf.read_bytes()
    fingerprint = hashlib.sha256(content).hexdigest()
    require(value.get('sourceFileHash') == fingerprint, 'PREPARED_PDF_HASH_MISMATCH')
    if not args.apply:
        return {'status': 'validated-original-only', 'pages': len(value.get('pages', [])), 'providerRequests': 0}
    lock = config.data_dir/'server.json'
    if lock.exists():
        require(not pid_alive(json.loads(lock.read_text('utf-8'))['pid']), 'STOP_HOST_BEFORE_IMPORT')
    p = Platform(config.data_dir, recover=False, preserve_legacy_data=True)
    try:
        scope = p.scope(args.course_id)
        rag = RagService(p)
        p.jobs.stopped = False
        uploaded = await finish(p, rag.upload(scope, content, args.name or args.pdf.name, 'prepared-original-'+fingerprint))
        doc_id = uploaded['result']['documentId']
        result = await finish(p, rag.prepared_pdf.submit(scope, doc_id, value, 'prepared-text-'+fingerprint))
        checks = []
        for query in ('顺序表', '链表', '栈', '队列', '二叉树', '哈夫曼', '最小生成树', '最短路径', '排序'):
            evidence = await rag.search(scope, query, document_ids=[doc_id], mode='lexical')
            sources = evidence['sources']
            valid = bool(sources) and all(rag.validate(scope, s) for s in sources)
            require(valid, 'PREPARED_PDF_SEARCH_CHECK_FAILED')
            checks.append({'query': query, 'hits': len(sources), 'pages': [s['page'] for s in sources], 'citationsValid': valid})
        replacement = None
        if args.replace_ppt:
            old = [d['id'] for d in p.repo.all(scope, 'document') if d.get('kind') == 'pptx' and not any(d.get(k) for k in ('superseded', 'archived', 'deleted'))]
            if old:
                manager = KnowledgeReplacement(p, rag)
                preview = manager.preview(scope, {'targetDocumentId': doc_id, 'oldDocumentIds': old})
                replacement = manager.apply(scope, {'previewId': preview['previewId'], 'confirmed': True})
        return {'status': 'passed', 'courseId': scope.course_id, 'documentId': doc_id, 'sha256': fingerprint,
                'pages': len(value['pages']), 'result': result['result'], 'queries': checks,
                'replacement': replacement, 'providerRequests': 0, 'privateLegacyDataPreserved': True}
    finally:
        await p.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--course-id', required=True)
    parser.add_argument('--name')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--replace-ppt', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('test-results/pdf-knowledge/import-prepared.json'))
    args = parser.parse_args()
    require(not args.replace_ppt or args.apply, 'APPLY_REQUIRED')
    report = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'pages', 'providerRequests')}, ensure_ascii=False))


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
