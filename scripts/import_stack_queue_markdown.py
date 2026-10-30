"""Install the authored Markdown through the existing CPU queue, archiving old PDFs.

Default is an isolated local rehearsal. --apply requires a stopped host and a
successful code-validation report matching the exact Markdown hash. No model
providers are created here; vector indexing is a separate, budgeted operation.
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

ROOT = Path(__file__).resolve().parents[1]
MATERIAL = ROOT/'materials/stack-queue/栈与队列知识库.md'
SPEC = ROOT/'evals/rag/stack-queue-md.json'


async def evidence_checks(rag, scope, document_id):
    specification = json.loads(SPEC.read_text(encoding='utf-8'))
    rows = []
    for question in specification['queries']:
        result = await rag.search(scope, question['query'], document_ids=[document_id], mode='lexical', budget=9000)
        sources = result['sources']
        valid = all(rag.validate(scope, s) and s['page'] is None for s in sources)
        hit = any(any(part.startswith(question['section']+' ') for part in s['sectionPath'])
                  and question['contains'] in s['quote'] for s in sources)
        rows.append({'id': question['id'], 'passed': bool(hit and valid),
                     'locations': [s['location'] for s in sources], 'usedBytes': result['budget']['used']})
    return {'kind': 'author-designed-evidence-check', 'passed': sum(r['passed'] for r in rows),
            'count': len(rows), 'modelRequests': 0, 'rows': rows}


async def install(p, scope, content, validation, *, archive_pdf_ids=(), rag=None):
    fingerprint = hashlib.sha256(content).hexdigest()
    require(validation.get('materialSha256') == fingerprint and validation.get('examples') == 13
            and validation.get('passed') == 13 and len(validation.get('rows', [])) == 13
            and all(r.get('passed') for r in validation['rows']), 'MATERIAL_CODE_VALIDATION_REQUIRED')
    rag = rag or RagService(p)
    app = SimpleNamespace(state=SimpleNamespace(platform=p, rag=rag))
    app.state.library = Library(app)
    kb = KnowledgeBase(app)
    receipt_id = 'authored-chapter-'+digest({'file': fingerprint, 'old': sorted(archive_pdf_ids)})[:40]
    previous = p.repo.read(scope, 'artifact', receipt_id)
    if previous:
        doc = rag.document(scope, previous['value']['documentId'], active=True)
        require(doc['fileHash'] == fingerprint and rag.reviewed(doc), 'INSTALLED_MATERIAL_CHANGED')
        require(all(rag.document(scope, old)['archived'] for old in archive_pdf_ids), 'ARCHIVE_STATE_CHANGED')
        return previous['value']
    before = [rag.document(scope, old) for old in archive_pdf_ids]
    require(all(d['kind'] == 'pdf' for d in before), 'ONLY_DECLARED_PDFS_CAN_BE_ARCHIVED')
    uploaded = kb.upload(scope, content, MATERIAL.name, '栈与队列', 'authored-md-'+fingerprint, review=False)
    doc = rag.document(scope, uploaded['documentId'])
    app.state.library.annotate(scope, uploaded['job'], {
        'origin': {'type': 'authored-markdown', 'aiAuthored': True, 'humanReviewedWholeDocument': False,
                   'materialPath': str(MATERIAL.relative_to(ROOT)), 'materialSha256': fingerprint,
                   'validation': {'cppStandard': 'C++17', 'examplesPassed': 13,
                                  'method': 'compiled-examples-and-independent-oracles'}}})
    p.jobs.stopped = False
    await finish(p, uploaded['job'])
    checks = await evidence_checks(rag, scope, uploaded['documentId'])
    require(checks['passed'] == checks['count'], 'MARKDOWN_EVIDENCE_CHECK_FAILED:'+','.join(r['id'] for r in checks['rows'] if not r['passed']))
    doc = rag.document(scope, uploaded['documentId'], active=True)
    artifact = rag.artifact(scope, doc)
    require(len([b for b in artifact['blocks'] if b['type'] == 'code']) == 13
            and not artifact['warnings'] and all(s['page'] is None for s in doc['chunks']), 'MARKDOWN_STRUCTURE_CHECK_FAILED')
    # Commit retirement only after real citations and the new source are usable.
    with p.db.transaction():
        for old in before:
            current = rag.document(scope, old['id'])
            require(current['version'] == old['version'], 'VERSION_CONFLICT')
        for old in before:
            if not old.get('archived'):
                app.state.library.organize(scope, {'documentId': old['id'], 'version': old['version'], 'action': 'archive'})
        profile = p.repo.read(scope, 'artifact', 'knowledge-base-profile')
        if profile:
            p.repo.put(scope, 'artifact', 'knowledge-base-profile', {**profile['value'],
                       'description': '重新编写的栈与队列Markdown教材：基础概念、存储实现、应用和进阶算法；附13个经编译验证的C++17实例。'}, profile['version'])
        result = {'status': 'markdown-active-pdf-archived', 'documentId': doc['id'], 'courseId': scope.course_id,
                  'sourceFileHash': fingerprint, 'contentRevision': doc['contentRevision'], 'sourceCount': len(doc['chunks']),
                  'codeBlocks': 13, 'archivedPdfIds': list(archive_pdf_ids), 'originalsRetained': True,
                  'evidenceChecks': checks, 'providerRequests': 0, 'vectorIndexed': False,
                  'reviewMethod': 'authored-content-with-automated-validation-not-human-OCR-confirmation'}
        p.repo.put(scope, 'artifact', receipt_id, result, 0)
    return result


async def run(args):
    content = MATERIAL.read_bytes()
    validation = json.loads(args.validation.read_text(encoding='utf-8'))
    if args.apply:
        config = load_config()
        lock = config.data_dir/'server.json'
        if lock.exists():
            require(not pid_alive(json.loads(lock.read_text('utf-8'))['pid']), 'STOP_HOST_BEFORE_IMPORT')
        require(args.course_id, 'COURSE_ID_REQUIRED')
        p = Platform(config.data_dir, recover=False, preserve_legacy_data=True)
        try:
            require(not p.db.one("SELECT id FROM jobs WHERE status NOT IN ('succeeded','failed','cancelled','unknown')"), 'ACTIVE_JOBS')
            require(not p.db.one("SELECT id FROM invocations WHERE status='pending'"), 'ACTIVE_INVOCATIONS')
            return await install(p, p.scope(args.course_id), content, validation, archive_pdf_ids=args.archive_pdf)
        finally:
            await p.close()
    with tempfile.TemporaryDirectory(prefix='xueya-markdown-check-') as directory:
        p = Platform(Path(directory), recover=False, preserve_legacy_data=True)
        try:
            result = await install(p, p.scope(), content, validation)
            return {**result, 'status': 'validated-in-isolated-store', 'privateStoreModified': False}
        finally:
            await p.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation', type=Path, default=ROOT/'test-results/stack-queue-md/code-validation.json')
    parser.add_argument('--course-id')
    parser.add_argument('--archive-pdf', action='append', default=[])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'sourceCount', 'codeBlocks', 'providerRequests')}, ensure_ascii=False))


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
