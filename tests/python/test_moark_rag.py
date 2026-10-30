"""Provider protocol and review lifecycle tests. No external network or billed calls."""
import io
import json

import httpx
import pytest
from pypdf import PdfReader, PdfWriter

from backend.xueya.common import AppError
from backend.xueya.rag_api import ApiSettings
from backend.xueya.rag_moark import MinerUProvider, QwenEmbeddingProvider
from backend.xueya.rag_http import configured_service
from backend.xueya.rag_service import RagService
from tests.python.test_rag import completed, ingest


def pdf():
    writer, out = PdfWriter(), io.BytesIO()
    for _ in range(3):
        writer.add_blank_page(width=100, height=100)
    writer.write(out)
    return out.getvalue()


def test_mineru_generated_descriptions_and_temporary_urls_are_not_text_evidence():
    raw = {'output': {'segments': [{'content': '教材正文\n![图片](https://example.com/img?authorization=secret)\n<details><summary>flowchart</summary>模型补写关系</details>\n后续正文'}]}}
    cleaned = MinerUProvider.markdown(raw)
    assert '教材正文' in cleaned and '后续正文' in cleaned
    assert 'authorization' not in cleaned and '模型补写关系' not in cleaned


async def test_qwen_protocol_normalization_and_dimensions(platform):
    calls = []
    def upstream(request):
        value = json.loads(request.content)
        calls.append(value)
        assert value == {'model': 'Qwen3-VL-Embedding-2B', 'input': [{'text': '树'}], 'dimensions': 2, 'encoding_format': 'float'}
        return httpx.Response(200, json={'data': [{'index': 0, 'embedding': [3, 4]}]})
    provider = QwenEmbeddingProvider(platform, ApiSettings(key='test', model='Qwen3-VL-Embedding-2B', dimension=2), transport=httpx.MockTransport(upstream))
    assert await provider.embed(platform.scope(), ['树']) == [[.6, .8]]
    assert await provider.embed(platform.scope(), ['树'], query=True) == [[.6, .8]]
    assert len(calls) == 2 and provider.identity['adapter'] == 'moark-qwen-text-v2'


async def test_mineru_original_pages_cache_and_ledger(platform):
    calls = []
    def upstream(request):
        calls.append(request.method)
        if request.method == 'POST':
            assert b'page-3.pdf' in request.content or b'page-1.pdf' in request.content
            # Only the selected original page is uploaded, not the complete PDF.
            raw = request.content.split(b'Content-Type: application/pdf\r\n\r\n')[1].split(b'\r\n--')[0]
            assert len(PdfReader(io.BytesIO(raw)).pages) == 1
            return httpx.Response(200, json={'task_id': 'remote-'+str(len(calls)), 'status': 'waiting'})
        return httpx.Response(200, json={'status': 'success', 'output': {'segments': [{'index': 99, 'content': '树是结点的有限集合。'}]}})
    settings = ApiSettings(key='test', model='MinerU2.5-Pro', base_url='https://api.moark.com/v1')
    provider = MinerUProvider(platform, settings, transport=httpx.MockTransport(upstream), name='moark-mineru-ocr')
    raw = pdf()
    result = await provider.recognize(platform.scope(), raw, [3, 1])
    assert list(result) == [3, 1] and result[3]['text'].startswith('树')
    assert result[3]['rawResultHash'] and result[3]['confidence'] is None
    assert await provider.recognize(platform.scope(), raw, [3, 1]) == result
    assert calls == ['POST', 'GET', 'POST', 'GET']
    assert [r['status'] for r in platform.db.all('SELECT status FROM invocations')] == ['succeeded', 'succeeded']


async def test_unknown_submission_never_replayed(platform):
    calls = []
    def timeout(request):
        calls.append(request.method)
        raise httpx.ReadTimeout('controlled', request=request)
    provider = MinerUProvider(platform, ApiSettings(key='test', model='MinerU2.5-Pro'), transport=httpx.MockTransport(timeout))
    raw = pdf()
    with pytest.raises(httpx.ReadTimeout):
        await provider.recognize(platform.scope(), raw, [1])
    with pytest.raises(AppError, match='OCR_SUBMISSION_UNKNOWN'):
        await provider.recognize(platform.scope(), raw, [1])
    assert calls == ['POST']
    assert platform.db.one('SELECT status FROM invocations')['status'] == 'unknown'


async def test_remote_task_resume_polls_without_resubmit(platform):
    calls = []
    def upstream(request):
        calls.append(request.method)
        if request.method == 'POST':
            return httpx.Response(200, json={'task_id': 'known-task'})
        if calls.count('GET') == 1:
            raise httpx.ReadTimeout('controlled', request=request)
        return httpx.Response(200, json={'status': 'success', 'output': {'segments': [{'content': '正确文字'}]}})
    provider = MinerUProvider(platform, ApiSettings(key='test', model='MinerU2.5-Pro'), transport=httpx.MockTransport(upstream))
    raw = pdf()
    with pytest.raises(httpx.ReadTimeout):
        await provider.recognize(platform.scope(), raw, [2])
    assert (await provider.recognize(platform.scope(), raw, [2]))[2]['text'] == '正确文字'
    assert calls == ['POST', 'GET', 'GET']
    assert len(platform.db.all('SELECT id FROM invocations')) == 1


async def test_mineru_in_progress_is_polled_without_resubmission(platform):
    calls = []
    def upstream(request):
        calls.append(request.method)
        if request.method == 'POST':
            return httpx.Response(200, json={'task_id': 'progress-task'})
        if calls.count('GET') == 1:
            return httpx.Response(200, json={'status': 'in_progress'})
        return httpx.Response(200, json={'status': 'success', 'output': {'segments': [{'content': '正文'}]}})
    provider = MinerUProvider(platform, ApiSettings(key='test', model='MinerU2.5-Pro'),
                             transport=httpx.MockTransport(upstream), poll_interval=0)
    assert (await provider.recognize(platform.scope(), pdf(), [1]))[1]['text'] == '正文'
    assert calls == ['POST', 'GET', 'GET']


async def test_review_gates_search_read_index_and_invalidates_after_correction(platform):
    rag, scope = RagService(platform), platform.scope()
    doc = await ingest(rag, '# 树\n\n树是结点的有限集合。')
    row = rag.repo.put(scope, 'document', doc['id'], {**doc, 'knowledgeReview': {'confirmedRevision': None}}, doc['version'])
    doc = rag.document(scope, doc['id'])
    assert not rag.sources(scope)
    with pytest.raises(AppError, match='KNOWLEDGE_REVIEW_REQUIRED'):
        rag.read(scope, doc['chunks'][0]['id'])
    with pytest.raises(AppError, match='KNOWLEDGE_REVIEW_REQUIRED'):
        rag.submit(scope, 'rag-index', doc['id'], 'index')
    rag.confirm_review(scope, doc['id'], doc['version'])
    source = rag.sources(scope)[0]
    assert rag.read(scope, source['id'])
    doc = rag.document(scope, doc['id'])
    rag.correct(scope, doc['id'], doc['version'], source['blockId'], '树是有限结点的集合。', '对照原件')
    assert not rag.sources(scope)
    with pytest.raises(AppError, match='VERSION_CONFLICT'):
        rag.confirm_review(scope, doc['id'], doc['version'])


def test_provider_configuration_without_secrets(platform, tmp_path, monkeypatch):
    for key, value in {'RAG_OCR_PROVIDER':'moark-mineru', 'RAG_OCR_MODEL':'MinerU2.5-Pro', 'RAG_OCR_API_KEY':'test',
                       'RAG_EMBEDDING_PROVIDER':'moark-qwen', 'RAG_EMBEDDING_MODEL':'Qwen3-VL-Embedding-8B', 'RAG_EMBEDDING_API_KEY':'test'}.items():
        monkeypatch.setenv(key, value)
    rag = configured_service(platform, tmp_path)
    assert isinstance(rag.ocr, MinerUProvider) and isinstance(rag.embedding, QwenEmbeddingProvider)
    assert rag.embedding.settings.dimension == 4096


def test_review_upload_skips_paid_practice_and_requires_current_confirmation(client):
    import time
    response = client.post('/api/platform/knowledge/upload', params={'name': 'review.md', 'review': '1'},
        headers={**client.platform_headers, 'Idempotency-Key': 'review-upload'}, content='树是结点的有限集合。'.encode())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['practiceGeneration'] is None
    for _ in range(300):
        job = client.platform.jobs.get(data['job']['id'], client.platform.user_id)
        if job['status'] in ('succeeded', 'failed'):
            break
        time.sleep(.02)
    assert job['status'] == 'succeeded'
    url, headers = '/api/platform/knowledge/', client.platform_headers
    cat = client.get(url+'catalog', headers=headers).json()
    doc = next(d for d in cat['documents'] if d['id'] == data['documentId'])
    assert not doc['reviewReady']
    assert not client.post(url+'search', headers=headers, json={'query':'树'}).json()['evidence']['sources']
    value = {'documentId':doc['id'], 'version':doc['version']}
    assert client.post(url+'review-confirm', headers=headers, json=value).json()['error'] == 'CONFIRMATION_REQUIRED'
    assert client.post(url+'review-confirm', headers=headers, json={**value, 'confirmed':True}).status_code == 200
    assert client.post(url+'search', headers=headers, json={'query':'树'}).json()['evidence']['sources']
    assert not client.platform.db.all('SELECT * FROM invocations')
