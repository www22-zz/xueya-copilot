import asyncio
import copy
import json
import pytest

from backend.xueya.common import AppError
from backend.xueya.platform import Platform
from backend.xueya.rag_service import RagService
from test_pdf_knowledge import pdf
from test_rag import completed
from test_practice_cleanup import seed


@pytest.mark.asyncio
async def test_selected_chapter_preserves_original_pages_review_gate_and_corrections(platform):
    from types import SimpleNamespace
    from backend.xueya.library_http import Library
    from backend.xueya.knowledge_base import KnowledgeBase
    rag = RagService(platform)
    app = SimpleNamespace(state=SimpleNamespace(platform=platform, rag=rag))
    app.state.library = Library(app)
    kb = KnowledgeBase(app)
    scope = platform.scope()
    upload = kb.upload(scope, pdf(3), 'chapter.pdf', '栈与队列', 'chapter', review=True)
    await completed(platform, upload['job'])
    doc = rag.document(scope, upload['documentId'])
    code = '```cpp\nvoid DeQueue() {\n  if (front == rear) throw "empty";\n  front = (front + 1) % QueueSize;\n}\n```'
    pack = {'schema': 'prepared-pdf-ocr-v1', 'sourceFileHash': doc['fileHash'], 'engine': 'fixture',
            'selectedPages': [2], 'pages': [{'page': 2, 'text': '循环队列出队操作。\n\n'+code, 'textFormat': 'markdown'}]}
    for selection in ([], [True], [0], [4], [2, 2], [3, 2], None):
        with pytest.raises(AppError, match='INVALID_PREPARED_PAGE_SELECTION'):
            rag.prepared_pdf.submit(scope, doc['id'], {**pack, 'selectedPages': selection}, 'bad')
    with pytest.raises(AppError, match='PREPARED_PDF_PAGE_MISMATCH'):
        rag.prepared_pdf.submit(scope, doc['id'], {**pack, 'pages': [{'page': 1, 'text': 'wrong page'}]}, 'bad')
    await completed(platform, rag.prepared_pdf.submit(scope, doc['id'], pack, 'selected'))
    doc = rag.document(scope, doc['id'])
    artifact = rag.artifact(scope, doc)
    assert [p['number'] for p in artifact['pages']] == [2]
    assert [p['number'] for p in artifact['originalPages']] == [1, 2, 3]
    assert 'text' not in artifact['originalPages'][0]
    assert [b['text'] for b in artifact['blocks'] if b['type'] == 'code'] == [code]
    assert all(s['page'] == 2 for s in doc['chunks'])
    assert not rag.sources(scope)  # Publication alone cannot claim human confirmation.
    assert kb.catalog(scope)['documents'][0]['pageSelection'] == {'pages': [2], 'originalPageCount': 3}
    rag.confirm_review(scope, doc['id'], doc['version'])
    assert rag.sources(scope) and all(rag.validate(scope, s) for s in rag.sources(scope))
    doc = rag.document(scope, doc['id'])
    block = artifact['blocks'][0]
    rag.correct(scope, doc['id'], doc['version'], block['id'], '循环队列的出队操作。', '核对原文')
    doc = rag.document(scope, doc['id'])
    assert doc['pageSelection']['pages'] == [2] and not rag.sources(scope)
    assert len(rag.artifact(scope, doc)['originalPages']) == 3
    # A later import may choose a different original page, then restore the full file.
    other = {**pack, 'selectedPages': [3], 'pages': [{'page': 3, 'text': '链队列有头结点。'}]}
    await completed(platform, rag.prepared_pdf.submit(scope, doc['id'], other, 'other-page'))
    assert rag.document(scope, doc['id'])['pageSelection']['pages'] == [3]
    full = {k: v for k, v in pack.items() if k != 'selectedPages'}
    full['pages'] = [{'page': n, 'text': '原教材第%d页正文。' % n} for n in (1, 2, 3)]
    await completed(platform, rag.prepared_pdf.submit(scope, doc['id'], full, 'restore-full'))
    restored = rag.document(scope, doc['id'])
    assert 'pageSelection' not in restored
    assert [p['number'] for p in rag.artifact(scope, restored)['pages']] == [1, 2, 3]


@pytest.mark.asyncio
async def test_prepared_pdf_atomic_pages_versions_idempotence_and_cancel(platform):
    rag = RagService(platform)
    scope = platform.scope()
    uploaded = await completed(platform, rag.upload(scope, pdf(2), 'book.pdf', 'original'))
    doc = rag.document(scope, uploaded['result']['documentId'])
    pack = {'schema': 'prepared-pdf-ocr-v1', 'sourceFileHash': doc['fileHash'], 'engine': 'test-fixture',
            'pages': [{'page': 1, 'text': '二叉树的前序遍历先访问根结点。'*30}, {'page': 2, 'text': '', 'reviewedBlank': True}]}
    for patch in ({'sourceFileHash': '0'*64}, {'pages': pack['pages'][:1]}, {'pages': [pack['pages'][0], {'page': 2, 'text': ''}]}):
        with pytest.raises(AppError):
            rag.prepared_pdf.submit(scope, doc['id'], {**pack, **patch}, 'bad')
    assert not rag.sources(scope)
    cancelled = rag.prepared_pdf.submit(scope, doc['id'], pack, 'cancelled')
    platform.jobs.cancel(cancelled['id'], platform.user_id)
    assert not rag.sources(scope)
    job = rag.prepared_pdf.submit(scope, doc['id'], pack, 'adopt')
    done = await completed(platform, job)
    assert done['status'] == 'succeeded', done
    current = rag.document(scope, doc['id'])
    artifact = rag.artifact(scope, current)
    assert artifact['pages'][1]['ocrPreparation']['reviewedBlank']
    assert not artifact['warnings'] and current['ocrPreparation']['engine'] == 'test-fixture'
    found = await rag.search(scope, '二叉树', mode='lexical')
    assert found['sources'] and all(s['page'] == 1 and rag.validate(scope, s) for s in found['sources'])
    assert rag.prepared_pdf.submit(scope, doc['id'], pack, 'adopt')['id'] == job['id']
    with pytest.raises(AppError, match='IDEMPOTENCY_CONFLICT'):
        rag.prepared_pdf.submit(scope, doc['id'], {**pack, 'engine': 'changed'}, 'adopt')
    stale = rag.prepared_pdf.submit(scope, doc['id'], pack, 'stale')
    platform.repo.put(scope, 'document', doc['id'], {**current, 'tags': ['edited']}, current['version'])
    assert (await completed(platform, stale))['status'] == 'failed'
    assert rag.document(scope, doc['id'])['activeArtifact'] == current['activeArtifact']


def test_preserve_private_history_on_startup_and_ui_projection_save(tmp_path):
    from backend.xueya.database import Database
    from backend.xueya.repository import Repository
    db = Database(tmp_path/'workspace.sqlite')
    seed(db, Repository(db))
    before = db.one('SELECT data FROM workspaces')['data']
    db.close()
    p = Platform(tmp_path, recover=False, preserve_legacy_data=True)
    try:
        assert p.repo.read(p.scope(), 'note', 'old-note')
        assert p.db.one("SELECT value FROM meta WHERE key='learning:preview:x'")
        assert p.db.one('SELECT data FROM workspaces')['data'] == before
        ws = p.repo.get_workspace(p.user_id)
        incoming = copy.deepcopy(ws['data'])
        incoming['courses'][0]['data'] = {'documents': [], 'messages': [], 'sessions': []}
        saved = p.repo.save_workspace(p.user_id, incoming, ws['version'])
        assert saved['data']['courses'][0]['data']['notes'] == {'q': 'x'}
        assert p.repo.read(p.scope(), 'note', 'old-note')
    finally:
        asyncio.run(p.close())
