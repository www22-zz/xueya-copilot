import time

from backend.xueya.learning import COURSE


def catalog(client):
    return client.get('/api/platform/knowledge/catalog', headers=client.platform_headers).json()


def test_metadata_demo_rows_are_not_real_documents(client):
    p = client.platform
    for doc in COURSE['documents']:
        p.repo.put(p.scope(), 'document', doc['id'], doc)
    result = catalog(client)
    assert result['documents'] == []
    assert result['summary']['documents'] == result['summary']['sources'] == 0
    # Exclusion is a projection, not deletion of historical records.
    assert len(p.repo.all(p.scope(), 'document')) == 3


def test_workspace_migration_does_not_publish_fixtures(platform, workspace):
    workspace['courses'][0]['data']['documents'] = COURSE['documents']
    saved = platform.repo.save_workspace(platform.user_id, workspace)
    assert saved['data']['courses'][0]['data']['documents'] == []
    assert platform.repo.all(platform.scope(), 'document') == []
    assert platform.repo.all(platform.scope(), 'source') == []


def test_protected_catalog_keeps_facts_without_exposing_body(client):
    p = client.platform
    doc = {'id': 'protected-doc', 'name': '预置.md', 'isPlatform': True, 'fileHash': 'a'*64, 'chunks': []}
    p.repo.put(p.scope(), 'document', doc['id'], doc)
    from backend.xueya.rag_scope_adapter import public_api_value
    result = public_api_value(p, {**doc, 'sourceCount': 18, 'kind': 'md', 'size': 1200,
                                 'originalAvailable': True, 'reviewReady': True,
                                 'review': {'totalPages': 0, 'pendingPages': [], 'text': 'PRIVATE_BODY'},
                                 'text': 'PRIVATE_BODY', 'blocks': [{'text': 'PRIVATE_BODY'}]})
    assert result['sourceCount'] == 18 and result['originalAvailable']
    assert result['kind'] == 'md' and result['size'] == 1200
    assert result['protected'] and result['chunks'] == []
    assert 'PRIVATE_BODY' not in str(result)


def test_real_upload_and_missing_original_are_distinct_from_demos(client):
    uploaded = client.post('/api/platform/knowledge/upload', params={'name': COURSE['documents'][0]['name'].replace('.pdf', '.md')},
                           headers={**client.platform_headers, 'Idempotency-Key': 'real-file'}, content='栈是后进先出的线性结构。'.encode()).json()
    for _ in range(300):
        job = client.platform.jobs.get(uploaded['job']['id'], client.platform.user_id)
        if job['status'] == 'succeeded':
            break
        time.sleep(.02)
    assert job['status'] == 'succeeded'
    before = catalog(client)
    assert before['summary']['documents'] == 1
    assert before['summary']['sources'] > 0
    assert before['documents'][0]['originalAvailable'] is True
    doc = client.platform.document(client.platform.scope(), uploaded['documentId'])
    client.platform.files.path(doc['fileHash']).unlink()
    after = catalog(client)
    assert after['summary']['documents'] == 1  # Retain broken records for recovery.
    assert after['summary']['sources'] == 0
    assert after['summary']['missingOriginals'] == 1
    assert after['documents'][0]['originalAvailable'] is False
