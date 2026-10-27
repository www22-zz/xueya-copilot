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
