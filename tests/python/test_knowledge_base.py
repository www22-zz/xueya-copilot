import json
import io
import time
import zipfile

import pytest

from backend.xueya.knowledge_base import infer_chapter
from backend.xueya.rag import parse_document
from backend.xueya.rag_parse import structured_chunks


def post(client, op, value):
    return client.post('/api/platform/knowledge/'+op, headers=client.platform_headers, json=value)


def create(client, key='new-kb', name='数据结构与算法'):
    r = post(client, 'create', {'name': name, 'description': '课程课件', 'idempotencyKey': key})
    assert r.status_code == 200, r.text
    return r.json()['base']['id']


def catalog(client, course):
    return client.get('/api/platform/knowledge/catalog', params={'courseId': course}, headers=client.platform_headers).json()


def upload(client, course, key='file-1', text='# 栈与队列\n栈的特点是后进先出。队列的特点是先进先出。', chapter='', name='week4 第3章_栈和队列.md'):
    return client.post('/api/platform/knowledge/upload', params={'courseId': course, 'name': name, 'chapter': chapter},
                       headers={**client.platform_headers, 'Idempotency-Key': key}, content=text.encode())


def wait(client, job):
    for _ in range(300):
        current = client.platform.jobs.get(job['id'], client.platform.user_id)
        if current['status'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
            return current
        time.sleep(.02)
    raise AssertionError('job timed out')


def test_create_preserves_existing_data_and_is_idempotent(client):
    before = client.platform.repo.courses(client.platform.user_id)
    course = create(client)
    assert create(client) == course
    assert all(c in client.platform.repo.courses(client.platform.user_id) for c in before)
    assert post(client, 'create', {'name': 'changed', 'idempotencyKey': 'new-kb'}).status_code == 409
    assert post(client, 'create', {'name': '', 'idempotencyKey': 'bad'}).status_code == 400
    assert course in {c['id'] for c in client.get('/api/platform/knowledge/bases', headers=client.platform_headers).json()['bases']}


def test_upload_chapter_dedup_across_keys_search_and_actual_citation(client):
    course = create(client)
    r = upload(client, course)
    assert r.status_code == 200, r.text
    job = wait(client, r.json()['job'])
    assert job['status'] == 'succeeded', job
    repeated = upload(client, course, 'different-browser-key').json()
    assert repeated['documentId'] == r.json()['documentId']
    assert repeated['job']['id'] == job['id']
    assert upload(client, course, text='改变正文').status_code == 409
    assert upload(client, course, chapter='不同章节').status_code == 409
    data = catalog(client, course)
    assert data['summary']['documents'] == 1 and data['summary']['sources'] > 0
    doc = data['documents'][0]
    assert doc['chapter'] == 'week4 第3章_栈和队列' and 'chunks' not in doc and 'fileHash' not in doc
    assert doc['task']['status'] == 'succeeded' and not doc['vectorReady']
    search = post(client, 'search', {'courseId': course, 'query': '后进先出', 'chapter': doc['chapter']}).json()['evidence']
    assert search['sources'] and not search['warnings']
    for source in search['sources']:
        assert client.post('/api/platform/rag/validate', json={'courseId': course, 'citation': source}, headers=client.platform_headers).json()['valid']
    assert not post(client, 'search', {'courseId': course, 'query': '栈', 'chapter': '不存在'}).json()['evidence']['sources']
    assert not client.platform.db.all('SELECT * FROM invocations')


def test_isolation_and_external_confirmation(client):
    a, b = create(client, 'a'), create(client, 'b')
    result = upload(client, a).json()
    assert wait(client, result['job'])['status'] == 'succeeded'
    assert not catalog(client, b)['documents']
    assert not post(client, 'search', {'courseId': b, 'query': '栈'}).json()['evidence']['sources']
    assert post(client, 'task', {'courseId': b, 'id': result['job']['id'], 'action': 'cancel'}).status_code == 404
    assert post(client, 'search', {'courseId': a, 'query': '栈', 'mode': 'hybrid'}).json()['error'] == 'EXTERNAL_CONFIRMATION_REQUIRED'
    d = catalog(client, a)['documents'][0]
    process = {'courseId': a, 'documentId': d['id'], 'version': d['version'], 'action': 'index', 'idempotencyKey': 'index'}
    assert post(client, 'process', process).json()['error'] == 'EXTERNAL_CONFIRMATION_REQUIRED'
    assert post(client, 'process', {**process, 'confirmedExternal': True}).json()['error'] == 'EMBEDDING_UNAVAILABLE'
    assert client.get('/api/platform/knowledge/bases').status_code == 403
    assert client.get('/api/platform/knowledge/bases', headers={**client.platform_headers, 'Origin': 'https://foreign.invalid'}).status_code == 403


def test_archive_excluded_and_retry_failed_parse(client):
    course = create(client)
    r = upload(client, course, text='非法PPT', name='week1.pptx').json()
    job = wait(client, r['job'])
    assert job['status'] == 'failed'
    assert catalog(client, course)['documents'][0]['task']['status'] == 'failed'
    retry = post(client, 'task', {'courseId': course, 'id': job['id'], 'action': 'retry'})
    assert retry.status_code == 200
    post(client, 'task', {'courseId': course, 'id': job['id'], 'action': 'cancel'})
    r = upload(client, course, 'good').json()
    assert wait(client, r['job'])['status'] == 'succeeded'
    d = next(d for d in catalog(client, course)['documents'] if d['id'] == r['documentId'])
    assert client.post('/api/platform/library/organize', headers=client.platform_headers, json={'courseId': course, 'documentId': d['id'], 'version': d['version'], 'action': 'archive', 'confirmed': True}).status_code == 200
    assert not post(client, 'search', {'courseId': course, 'query': '栈'}).json()['evidence']['sources']
    assert catalog(client, course)['summary']['documents'] == 1  # Failed file remains visible.


def test_index_plan_uses_configured_service_without_calling_it_and_is_scoped(client):
    from backend.xueya.rag_api import ApiSettings
    from backend.xueya.rag_moark import QwenEmbeddingProvider
    rag = client.app.state.rag
    rag.embedding = QwenEmbeddingProvider(client.platform, ApiSettings(
        key='synthetic-never-sent', model='Qwen3-VL-Embedding-2B', dimension=2048,
        base_url='https://api.moark.com/v1'))
    a, b = create(client, 'plan-a'), create(client, 'plan-b')
    result = upload(client, a).json()
    assert wait(client, result['job'])['status'] == 'succeeded'
    params = {'courseId': a, 'documentId': result['documentId']}
    response = client.get('/api/platform/knowledge/index-plan', params=params, headers=client.platform_headers)
    assert response.status_code == 200
    plan = response.json()['plan']
    assert plan['model'] == 'Qwen3-VL-Embedding-2B' and plan['requiresExternal']
    assert plan['cachedVectors'] == 0 and plan['missingVectors'] == plan['sourceCount'] > 0
    assert 'synthetic-never-sent' not in response.text
    assert client.get('/api/platform/knowledge/index-plan', params={**params, 'courseId': b}, headers=client.platform_headers).status_code == 404
    assert client.get('/api/platform/knowledge/index-plan', params=params).status_code == 403
    assert not client.platform.db.one('SELECT id FROM invocations')


@pytest.mark.parametrize('name,chapter', [('week14 第7.4章图.pptx', '第7.4章'), ('week5_字符串.pptx', '第5周'), ('讲义.pptx', '')])
def test_explicit_filename_labels(name, chapter):
    assert infer_chapter(name) == chapter


def test_bad_inputs_and_free_cpu_process(client):
    course = create(client)
    assert upload(client, course, name='~$locked.pptx').status_code == 400
    assert upload(client, course, name='../lecture.md').status_code == 400
    r = upload(client, course).json()
    assert wait(client, r['job'])['status'] == 'succeeded'
    d = catalog(client, course)['documents'][0]
    value = {'courseId': course, 'documentId': d['id'], 'action': 'parse', 'version': d['version'], 'idempotencyKey': 'reparse'}
    job = post(client, 'process', value).json()['job']
    assert wait(client, job)['status'] == 'succeeded'
    assert catalog(client, course)['documents'][0]['contentRevision'] == 2
    assert post(client, 'process', {**value, 'idempotencyKey': 'stale'}).status_code == 409
    assert not client.platform.db.all('SELECT * FROM invocations')
    assert post(client, 'process', {**value, 'action': 'ocr', 'confirmedExternal': True, 'idempotencyKey': 'not-pdf'}).json()['error'] == 'OCR_PDF_REQUIRED'


def test_pptx_keeps_same_slide_context_table_boundaries_and_exact_offsets():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('ppt/presentation.xml', '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldId r:id="r1"/><p:sldId r:id="r2"/></p:presentation>')
        archive.writestr('ppt/_rels/presentation.xml.rels', '<Relationships><Relationship Id="r1" Target="slides/slide1.xml"/><Relationship Id="r2" Target="slides/slide2.xml"/></Relationships>')
        for number in (1, 2):
            archive.writestr(f'ppt/slides/slide{number}.xml', f'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:spTree><p:sp><a:p><a:t>第{number}页 栈</a:t></a:p><a:p><a:t>后进先出</a:t></a:p></p:sp><p:graphicFrame><a:tbl><a:tr><a:tc><a:t>操作</a:t></a:tc><a:tc><a:t>入栈</a:t></a:tc></a:tr></a:tbl></p:graphicFrame><p:sp><a:p><a:t>示例结尾</a:t></a:p></p:sp></p:spTree></p:sld>')
    parsed = parse_document(output.getvalue(), 'pptx')
    assert len(parsed['blocks']) == 6
    assert parsed['blocks'][0]['text'] == '第1页 栈\n后进先出'
    assert parsed['blocks'][1]['type'] == 'table'
    chunks = structured_chunks(parsed, {'id': 'slides', 'name': '课件.pptx'})
    assert any('栈\n后进先出' in s['quote'] for s in chunks)
    for block in parsed['blocks']:
        assert parsed['text'][block['start']:block['end']] == block['text']
    for source in chunks:
        page = parsed['pages'][source['page']-1]
        assert page['start'] <= source['start'] < source['end'] <= page['end']
