import pytest

from test_knowledge_base import create, upload, wait, catalog, post
from test_rag import embedding


@pytest.mark.parametrize('name,chapter,expected', [('Lab1_2.md', '', 'Lab1_2'), ('week4 第3章_栈.md', '  ', 'week4 第3章_栈'), ('notes.v2.md', '', 'notes.v2'), ('Lab1_2.md', ' 自定义章节 ', '自定义章节')])
def test_filename_default_persisted_and_searchable(client, name, chapter, expected):
    course = create(client)
    result = upload(client, course, name=name, chapter=chapter).json()
    assert wait(client, result['job'])['status'] == 'succeeded'
    doc = catalog(client, course)['documents'][0]
    assert doc['chapter'] == expected
    assert client.app.state.rag.document(client.platform.scope(course), doc['id'])['chapter'] == expected
    assert post(client, 'search', {'courseId': course, 'query': '后进先出', 'chapter': expected}).json()['evidence']['sources']


def test_legacy_empty_chapter_uses_filename_in_catalog_and_filter(client):
    course = create(client)
    result = upload(client, course, name='Lab1_2.md').json()
    assert wait(client, result['job'])['status'] == 'succeeded'
    rag, scope = client.app.state.rag, client.platform.scope(course)
    doc = rag.document(scope, result['documentId'])
    rag.repo.put(scope, 'document', doc['id'], {**doc, 'chapter': ''}, doc['version'])
    assert catalog(client, course)['documents'][0]['chapter'] == 'Lab1_2'
    assert post(client, 'search', {'courseId': course, 'query': '后进先出', 'chapter': 'Lab1_2'}).json()['evidence']['sources']


def test_legacy_upload_dedup_and_reupload_after_confirmed_delete(client, monkeypatch):
    from backend.xueya import knowledge_base
    course = create(client)
    with monkeypatch.context() as legacy:
        legacy.setattr(knowledge_base, 'filename_chapter', knowledge_base.infer_chapter)
        result = upload(client, course, name='Lab1_2.md').json()
        assert wait(client, result['job'])['status'] == 'succeeded'
    repeated = upload(client, course, name='Lab1_2.md').json()
    assert repeated['documentId'] == result['documentId']
    assert len(catalog(client, course)['documents']) == 1
    d = catalog(client, course)['documents'][0]
    assert post(client, 'remove', {'courseId': course, 'documentId': d['id'], 'version': d['version'], 'confirmed': True}).json()['removed']
    for _ in range(2):
        again = upload(client, course, name='Lab1_2.md').json()
        assert again.get('ok'), again
        assert wait(client, again['job'])['status'] == 'succeeded'
        assert again['documentId'] != d['id']
        d = catalog(client, course)['documents'][0]
        assert d['chapter'] == 'Lab1_2'
        assert post(client, 'remove', {'courseId': course, 'documentId': d['id'], 'version': d['version'], 'confirmed': True}).json()['removed']


def test_delete_is_confirmed_scoped_versioned_and_cleans_only_unused_vectors(client):
    rag = client.app.state.rag
    embedding(rag)
    course, other = create(client, 'delete-a'), create(client, 'delete-b')
    scope = client.platform.scope(course)
    docs = []
    for i, text in enumerate(['# 共享\n\n栈遵循后进先出。', '# 共享\n\n栈遵循后进先出。', '# 独立\n\n队列遵循先进先出。']):
        result = upload(client, course, key='file-'+str(i), name=str(i)+'.md', text=text).json()
        assert wait(client, result['job'])['status'] == 'succeeded'
        doc = rag.document(scope, result['documentId'])
        index = post(client, 'process', {'courseId': course, 'documentId': doc['id'], 'version': doc['version'], 'action': 'index', 'idempotencyKey': 'idx-'+str(i), 'confirmedExternal': True}).json()['job']
        assert wait(client, index)['status'] == 'succeeded'
        docs.append(rag.document(scope, doc['id']))
    shared = {rag._cache_id(rag.embedding.identity, s['quote']) for s in rag.sources(scope, document_ids=[docs[0]['id']])}
    independent = {rag._cache_id(rag.embedding.identity, s['quote']) for s in rag.sources(scope, document_ids=[docs[2]['id']])}
    assert shared and independent and not shared.intersection(independent)
    value = {'courseId': course, 'documentId': docs[0]['id'], 'version': docs[0]['version'], 'confirmed': True}
    assert post(client, 'remove', {**value, 'confirmed': False}).json()['error'] == 'CONFIRMATION_REQUIRED'
    assert post(client, 'remove', {**value, 'version': value['version']-1}).status_code == 409
    assert post(client, 'remove', {**value, 'courseId': other}).status_code == 404
    assert client.post('/api/platform/knowledge/remove', json=value).status_code == 403
    before = client.platform.db.one('SELECT count(*) AS n FROM invocations')['n']
    assert post(client, 'remove', value).json()['removed']
    assert len(catalog(client, course)['documents']) == 2
    assert {v['id'] for v in rag.repo.all(scope, 'vector')} == shared | independent
    deleted = rag.repo.read(scope, 'document', docs[0]['id'], include_deleted=True)
    assert deleted['deleted'] and deleted['value']['indexStatus'] == 'deleted' and deleted['value']['embeddingIdentity'] is None
    assert not any(s['documentId'] == docs[0]['id'] for s in rag.repo.all(scope, 'source'))
    assert post(client, 'remove', {**value, 'documentId': docs[1]['id'], 'version': docs[1]['version']}).json()['removed']
    assert {v['id'] for v in rag.repo.all(scope, 'vector')} == independent
    assert catalog(client, course)['summary']['sources'] > 0
    assert client.platform.db.one('SELECT count(*) AS n FROM invocations')['n'] == before
    client.platform.jobs.stopped = True
    queued = rag.submit(scope, 'rag-index', docs[2]['id'], 'pending-delete-index', expected_version=docs[2]['version'])
    assert post(client, 'remove', {**value, 'documentId': docs[2]['id'], 'version': docs[2]['version']}).json()['removed']
    assert client.platform.jobs.get(queued['id'], scope.user_id)['status'] in ('cancelled', 'cancelling', 'succeeded')
    assert not rag.repo.all(scope, 'vector')
    assert not post(client, 'search', {'courseId': course, 'query': '后进先出'}).json()['evidence']['sources']
