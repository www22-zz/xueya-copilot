import asyncio
import base64
import io
import json
import random

import httpx
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.xueya.common import AppError
from backend.xueya.rag_api import ApiSettings, OcrProvider
from backend.xueya.rag_search import exact, fuse, lexical
from backend.xueya.rag_service import RagService
from test_knowledge_base import wait
from test_rag import completed
from test_visual_review import slides


def pdf(pages=1, text=False, large=False):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=300, height=400)
        if text:
            font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')}))
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
            stream = DecodedStreamObject()
            stream.set_data(b'BT /F1 12 Tf 20 200 Td (Tree search and stack operations.) Tj ET')
            page[NameObject('/Contents')] = writer._add_object(stream)
    if large:
        writer.add_metadata({'/Padding': 'x'*(10*1024*1024+1024)})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def upload(client, content, name, key):
    result = client.post('/api/platform/knowledge/upload', params={'name': name}, content=content,
                         headers={**client.platform_headers, 'Idempotency-Key': key}).json()
    assert 'job' in result, result
    job = wait(client, result['job'])
    assert job['status'] == 'succeeded', job
    return job['result']['documentId']


def post(client, operation, value):
    return client.post('/api/platform/knowledge/'+operation, json=value, headers=client.platform_headers)


def test_large_pdf_explicit_ocr_batch_remaps_original_pages_and_preserves_other_blocks(platform):
    async def run():
        rag = RagService(platform)
        scope = platform.scope()
        raw = pdf(70, large=True)
        assert len(raw) > 10*1024*1024
        parsed = await completed(platform, rag.upload(scope, raw, 'book.pdf', 'large-book'))
        doc = rag.document(scope, parsed['result']['documentId'])
        assert len(rag.artifact(scope, doc)['pages']) == 70 and not doc['chunks']
        calls = []
        def ocr(request):
            value = json.loads(request.content)
            selected = base64.b64decode(value['document']['document_url'].split(',', 1)[1])
            assert len(selected) < 10*1024*1024 and len(PdfReader(io.BytesIO(selected)).pages) == 2
            assert value['pages'] == [0, 1]
            calls.append(value['pages'])
            return httpx.Response(200, json={'pages': [{'index': 0, 'markdown': '# Tree\n\nA stack is last in first out.'},
                                                       {'index': 1, 'markdown': 'Binary search uses a sorted sequence.'}]})
        rag.ocr = OcrProvider(platform, ApiSettings(key='controlled', model='controlled-ocr', base_url='https://controlled.invalid/v1'),
                              transport=httpx.MockTransport(ocr))
        job = rag.submit(scope, 'rag-ocr', doc['id'], 'explicit-ocr', expected_version=doc['version'], pages=[66, 2])
        outcome = await completed(platform, job)
        assert outcome['status'] == 'succeeded', (outcome.get('error'), calls)
        updated = rag.document(scope, doc['id'])
        artifact = rag.artifact(scope, updated)
        assert 'last in first out' in artifact['text'][artifact['pages'][65]['start']:artifact['pages'][65]['end']]
        assert 'Binary search' in artifact['text'][artifact['pages'][1]['start']:artifact['pages'][1]['end']]
        assert artifact['pages'][0]['needsOcr'] and not artifact['pages'][65]['needsOcr']
        assert platform.files.read(updated['fileHash']) == raw
        assert rag.submit(scope, 'rag-ocr', doc['id'], 'explicit-ocr', expected_version=doc['version'], pages=[66, 2])['id'] == job['id']
        with pytest.raises(AppError, match='IDEMPOTENCY_CONFLICT'):
            rag.submit(scope, 'rag-ocr', doc['id'], 'explicit-ocr', pages=[2])
        for index, invalid in enumerate(([66], [3, 3], [True], [0], list(range(1, 66)))):
            with pytest.raises(AppError, match='INVALID_OCR_PAGES'):
                rag.submit(scope, 'rag-ocr', doc['id'], 'invalid-'+str(index), pages=invalid)
        assert len(calls) == 1 and len(platform.db.all('SELECT * FROM invocations')) == 1
        for source in updated['chunks']:
            assert rag.validate(scope, rag.read(scope, source['id']))
    asyncio.run(run())


def test_replacement_requires_usable_pdf_explicit_confirm_and_preserves_history_and_notes(client):
    old = upload(client, slides(), 'old.pptx', 'old')
    scan = upload(client, pdf(), 'scan.pdf', 'scan')
    assert post(client, 'replacement-preview', {'targetDocumentId': scan, 'oldDocumentIds': [old]}).json()['error'] == 'REPLACEMENT_NOT_READY'
    new = upload(client, pdf(text=True), 'book.pdf', 'book')
    client.platform.repo.put(client.platform.scope(), 'note', 'private-old-note', {'text': '保留私人笔记'}, 0)
    preview = post(client, 'replacement-preview', {'targetDocumentId': new, 'oldDocumentIds': [old]}).json()['preview']
    assert client.app.state.rag.document(client.platform.scope(), old)
    assert post(client, 'replacement-apply', {'previewId': preview['previewId']}).json()['error'] == 'CONFIRMATION_REQUIRED'
    result = post(client, 'replacement-apply', {'previewId': preview['previewId'], 'confirmed': True}).json()['replacement']
    assert result['removedDocumentIds'] == [old] and result['retainedForRecovery']
    assert post(client, 'replacement-apply', {'previewId': preview['previewId'], 'confirmed': True}).json()['replacement'] == result
    assert client.platform.repo.read(client.platform.scope(), 'document', old, include_deleted=True)['deleted']
    assert client.platform.repo.read(client.platform.scope(), 'note', 'private-old-note')['value']['text'] == '保留私人笔记'
    assert client.app.state.rag.sources(client.platform.scope(), document_ids=[new])
    assert not client.platform.db.all('SELECT * FROM invocations')


def test_replacement_stale_preview_and_cross_course_cannot_remove_any_ppt(client):
    a = upload(client, slides(), 'a.pptx', 'a')
    b = upload(client, slides(), 'b.pptx', 'b')
    new = upload(client, pdf(text=True), 'book.pdf', 'book')
    preview = post(client, 'replacement-preview', {'targetDocumentId': new, 'oldDocumentIds': [a, b]}).json()['preview']
    p = client.platform
    row = p.repo.read(p.scope(), 'document', b)
    p.repo.put(p.scope(), 'document', b, {**row['value'], 'chapter': 'changed'}, row['version'])
    assert post(client, 'replacement-apply', {'previewId': preview['previewId'], 'confirmed': True}).status_code == 409
    assert client.app.state.rag.document(p.scope(), a) and client.app.state.rag.document(p.scope(), b)
    p.repo.ensure_course(p.user_id, {'id': 'other', 'name': 'Other'})
    assert post(client, 'replacement-apply', {'courseId': 'other', 'previewId': preview['previewId'], 'confirmed': True}).status_code == 404


def test_equal_scores_do_not_depend_on_random_import_ids_and_aliases_stay_distinct():
    for seed in range(10):
        rng = random.Random(seed)
        sources = [{'id': str(rng.random()), 'title': 'Book', 'quote': 'tree traversal', 'page': n, 'start': n*20} for n in (1, 2)]
        rng.shuffle(sources)
        assert [s['page'] for _, s in lexical('tree', sources)] == [1, 2]
        assert [s['page'] for _, s in exact([1, 0], [([1, 0], s) for s in sources])] == [1, 2]
        rows = [(1, s) for s in sources]
        assert [s['page'] for _, s in fuse(rows, list(reversed(rows)))] == [1, 2]
    sources = [{'id': 'pre', 'title': '', 'quote': '先序遍历先访问根。'}, {'id': 'post', 'title': '', 'quote': '后序遍历最后访问根。'}]
    assert lexical('preorder', sources)[0][1]['id'] == 'pre'
    assert lexical('postorder', sources)[0][1]['id'] == 'post'
    assert lexical('hash table', [{'id': 'hash', 'title': '', 'quote': '散列表采用散列函数。'}])
