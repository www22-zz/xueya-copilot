"""Real HTTP/SQLite two-account privacy checks; no external services."""
import asyncio
import json

from fastapi.testclient import TestClient
import pytest

from backend.xueya.account_scope import account_owner, bind_owner
from backend.xueya.app import create_app
from backend.xueya.common import Scope
from backend.xueya.config import Config
from backend.xueya.rag_scope_adapter import ScopeAdapter, public_api_value
from tests.python.test_rag import completed


PASSWORD = 'Fixture123'


def login(client, name, register=False):
    reply = client.post('/api/account/' + ('register' if register else 'login'), json={
        'username': name, 'password': PASSWORD, 'confirmPassword': PASSWORD})
    assert reply.status_code == 200, reply.text
    return {'X-Xueya-Token': client.get('/api/platform/bootstrap').json()['token']}


@pytest.fixture
def library(tmp_path, http_root):
    config = Config(root=http_root, data_dir=tmp_path/'data', preserve_legacy_data=True)
    app = create_app(config, start_jobs=False)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        p, rag = app.state.platform, app.state.rag
        legacy = p.scope()
        for name, text, shared in [('legacy.md', 'OLD_UNASSIGNED_PRIVATE_8542', False),
                                   ('preset.md', 'PLATFORM_INTERNAL_6293 栈只能在一端插入删除。', True)]:
            job = rag.upload(legacy, text.encode(), name, 'seed-'+name)
            asyncio.run(completed(p, job))
            if shared:
                doc = next(d for d in p.repo.all(legacy, 'document') if d['name'] == name)
                p.repo.put(legacy, 'document', doc['id'], {**doc, 'isPlatform': True}, doc['version'])
        yield app, client, config


def upload(app, client, headers, path='/api/platform/knowledge/upload', key='upload-private'):
    reply = client.post(path+'?name=private.md&courseId=course-default', content='ALICE_PRIVATE_8137 栈复习笔记。'.encode(),
                        headers={**headers, 'Idempotency-Key': key})
    assert reply.status_code == 200, reply.text
    job = reply.json()['job']
    async def finish():
        p = app.state.platform
        owner = p.db.one('SELECT user_id FROM jobs WHERE id=?', (job['id'],))['user_id']
        p.jobs.stopped = False
        for _ in range(500):
            await p.jobs.tick()
            state = p.jobs.get(job['id'], owner)
            if state['status'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
                assert state['status'] == 'succeeded', state
                return
            await asyncio.sleep(.01)
        pytest.fail('private parse did not complete')
    asyncio.run(finish())
    return client.get('/api/platform/jobs/status?id='+job['id'], headers=headers).json()['job']


@pytest.mark.parametrize('path', ['/api/platform/knowledge/upload', '/api/platform/rag/upload', '/api/platform/documents/upload'])
def test_upload_read_search_jobs_and_old_routes_are_account_scoped(library, path):
    app, client, _ = library
    alice = login(client, 'alice', True)
    job = upload(app, client, alice, path)
    document_id = job['result']['documentId']
    own = client.get('/api/platform/documents', headers=alice)
    assert 'ALICE_PRIVATE_8137' in own.text
    assert 'OLD_UNASSIGNED_PRIVATE_8542' not in own.text
    sources = client.get('/api/platform/entities?kind=source', headers=alice).json()['items']
    source = sources[0]
    assert client.get('/api/platform/rag/original?documentId='+document_id, headers=alice).content.startswith(b'ALICE_PRIVATE')
    assert client.get('/api/platform/library/read?documentId='+document_id, headers=alice).json()['artifact']['text'].startswith('ALICE_PRIVATE')
    assert app.state.platform.user_id == 'local-user'
    bob = login(client, 'bobby', True)
    alice_owner = account_owner(app.state.account.find('alice')[0])
    stale = client.put('/api/platform/workspace', headers={**bob,'X-Xueya-Owner':alice_owner}, json={'workspace':{},'expectedVersion':0})
    assert stale.status_code == 409 and stale.json()['error'] == 'ACCOUNT_CHANGED'
    for url in ['/api/platform/documents', '/api/platform/bootstrap', '/api/platform/jobs', '/api/learning/workspace',
                '/api/platform/library/catalog', '/api/platform/knowledge/catalog', '/api/platform/workbench/tasks']:
        response = client.get(url, headers=bob)
        assert response.status_code == 200, response.text
        assert 'ALICE_PRIVATE_8137' not in response.text and document_id not in response.text
        assert 'OLD_UNASSIGNED_PRIVATE_8542' not in response.text
    for url in ['/api/platform/rag/original?documentId='+document_id,
                '/api/platform/documents/original?documentId='+document_id,
                '/api/platform/rag/export?documentId='+document_id,
                '/api/platform/library/read?documentId='+document_id+'&version=1',
                '/api/platform/rag/read?sourceId='+source['id'], '/api/platform/jobs/status?id='+job['id'],
                '/api/platform/jobs/events?id='+job['id']]:
        response = client.get(url+'&accountId=alice', headers={**bob, 'X-Xueya-Account': 'alice'})
        assert response.status_code >= 400, (url, response.text)
        assert 'ALICE_PRIVATE_8137' not in response.text
    assert not client.post('/api/platform/rag/validate', headers=bob, json={'citation':source}).json()['valid']
    evidence = client.post('/api/platform/rag/search', headers=bob, json={'query':'栈', 'mode':'lexical'}).json()['evidence']
    assert evidence['sources'] and all(s['isPlatform'] and 'quote' not in s for s in evidence['sources'])
    assert 'ALICE_PRIVATE_8137' not in json.dumps(evidence)
    for route in ['knowledge/search', 'rag/search']:
        response = client.post('/api/platform/'+route, headers=bob, json={'query':'ALICE_PRIVATE_8137', 'mode':'lexical', 'documentIds':[document_id]})
        assert not response.json()['evidence']['sources']


def test_public_aliases_revalidate_at_original_scope_and_never_share_unassigned_data(library):
    app, client, _ = library
    headers = login(client, 'alice', True)
    upload(app, client, headers)
    p, rag = app.state.platform, app.state.rag
    owner = account_owner(app.state.account.find('alice')[0])
    adapter = ScopeAdapter(p, owner)
    sources = adapter.sources(rag, 'course-default')
    assert any('ALICE_PRIVATE' in s['quote'] for s in sources)
    public = next(s for s in sources if s.get('isPlatform'))
    assert public['id'].startswith('pub-')
    assert not any('OLD_UNASSIGNED' in s['quote'] for s in sources)
    assert adapter.validate_citation(rag, public)
    forged = {**public, 'scopeOrigin': {'user_id':'other-account','course_id':'course-default'}}
    with pytest.raises(Exception, match='SOURCE_SCOPE_FORBIDDEN'):
        adapter.validate_citation(rag, forged)
    with bind_owner(owner):
        library_sources = app.state.agent.current_library(p.scope())
        assert {s['id'] for s in library_sources} == {s['id'] for s in sources}
        snapshot = app.state.agent.evidence_snapshot(p.scope(), [public])
        assert app.state.agent.evidence_current(p.scope(), [public], snapshot)
    # Neither alias nor a guessed raw public source ID opens protected text.
    raw = next(s for s in p.repo.all(p.scope(), 'source') if s.get('documentId') == public['documentId'])
    read = client.get('/api/platform/rag/read?sourceId='+public['id'], headers=headers)
    assert read.status_code == 200 and 'quote' not in read.json()['source']
    assert client.get('/api/platform/rag/read?sourceId='+raw['id'], headers=headers).status_code >= 400
    original_scope, _ = adapter.resolve_source(public['id'], 'course-default')
    doc = rag.document(original_scope, public['documentId'])
    rag.remove(original_scope, doc['id'], doc['version'])
    with bind_owner(owner):
        assert not app.state.agent.evidence_current(p.scope(), [public], snapshot)


def test_all_old_public_outputs_project_sources_artifacts_and_serialized_previews(library):
    app, client, _ = library
    p = app.state.platform
    doc = next(d for d in p.repo.all(p.scope(), 'document') if d.get('isPlatform'))
    source = next(s for s in p.repo.all(p.scope(), 'source') if s['documentId'] == doc['id'])
    token = client.get('/api/platform/bootstrap').json()['token']; headers={'X-Xueya-Token':token}
    for url in ['/api/platform/library/read?documentId='+doc['id'], '/api/platform/knowledge/catalog',
                '/api/platform/rag/export?documentId='+doc['id'], '/api/learning/workspace',
                '/api/platform/entities?kind=artifact', '/api/platform/entities?kind=source']:
        response = client.get(url, headers=headers)
        assert response.status_code == 200, response.text
        assert 'PLATFORM_INTERNAL_6293' not in response.text, (url, response.text)
    payload={'claims':[{'evidence':[{'sourceId':source['id'], 'quote':source['quote']}]}],
             'toolCalls':[{'preview':json.dumps({'source':source}), 'data':{'sources':[source]}}],
             'checkpoint':{'text':source['quote']}, 'content':json.dumps({'documentId':doc['id'], 'blocks':[{'text':source['quote']}]})}
    assert 'PLATFORM_INTERNAL_6293' not in json.dumps(public_api_value(p, payload))
    # MCP HTTP endpoint uses the same boundary; internal tools retain the real text.
    result=client.post('/api/platform/tools/call',headers=headers,json={'name':'read_source','arguments':{'sourceId':source['id']}})
    assert result.status_code==200 and 'PLATFORM_INTERNAL_6293' not in result.text


def test_rename_and_restart_preserve_private_owner_and_legacy_rows(library):
    app, client, config = library
    headers=login(client,'alice',True);job=upload(app,client,headers)
    legacy_before=app.state.platform.repo.all(app.state.platform.scope(), 'document')
    assert client.post('/api/account/password', headers=headers, json={'currentPassword':PASSWORD,'password':PASSWORD,'username':'renamed'}).status_code==200
    assert job['result']['documentId'] in client.get('/api/platform/documents',headers=headers).text
    assert app.state.platform.repo.all(app.state.platform.scope(), 'document') == legacy_before
    with TestClient(create_app(config, start_jobs=False),base_url='http://127.0.0.1') as restarted:
        headers=login(restarted,'renamed')
        assert job['result']['documentId'] in restarted.get('/api/platform/documents',headers=headers).text


def test_concurrent_contexts_do_not_change_legacy_platform_identity(library):
    app, client, _ = library
    login(client, 'alice', True); login(client, 'bobby', True)
    p=app.state.platform
    async def read(owner):
        with bind_owner(owner):
            await asyncio.sleep(0)
            return p.scope().user_id
    owners=[account_owner(app.state.account.find(name)[0]) for name in ('alice','bobby')]
    # Ensure courses were initialized by authenticated bootstrap requests.
    async def run():
        return await asyncio.gather(*(read(o) for o in owners))
    assert asyncio.run(run()) == owners
    assert p.scope().user_id == p.user_id == 'local-user'


def test_protected_sse_holds_split_evidence_and_preserves_verified_narrative(library):
    from backend.xueya.account_scope import AccountBoundaryMiddleware
    app, _, _ = library
    source = next(s for s in app.state.platform.repo.all(app.state.platform.scope(), 'source') if 'PLATFORM_INTERNAL' in s['quote'])
    async def response(scope, receive, send):
        await send({'type':'http.response.start', 'status':200, 'headers':[(b'content-type',b'text/event-stream')]})
        events = [{'type':'content','text':'{"answer":"PLATFORM_INTERNAL_'},
                  {'type':'content','text':'6293 原文片段"}'},
                  {'type':'done','ok':True,'answer':'栈可以从受限端访问，因此后放入的元素先取出。',
                   'sources':[source['id']], 'sourceDetails':[source], 'verification':'reviewed-claims'}]
        data = ''.join('data: '+json.dumps(e,ensure_ascii=False)+'\n\n' for e in events).encode()
        for index in range(0,len(data),7):
            await send({'type':'http.response.body','body':data[index:index+7],'more_body':True})
        await send({'type':'http.response.body','body':b'','more_body':False})
    collected=[]
    async def send(message):
        collected.append(message)
    async def receive():
        return {'type':'http.request','body':b''}
    middleware=AccountBoundaryMiddleware(response, app)
    asyncio.run(middleware({'type':'http','path':'/api/agent/stream','headers':[], 'method':'POST','query_string':b''},receive,send))
    data=b''.join(m.get('body',b'') for m in collected).decode()
    assert 'PLATFORM_INTERNAL' not in data and 'quote' not in data
    events=[json.loads(line[6:]) for line in data.splitlines() if line.startswith('data: ')]
    assert [e['type'] for e in events] == ['content','done']
    assert '栈可以从受限端访问' in events[-1]['answer']


def test_protected_material_cannot_drive_legacy_question_generation(library):
    app, client, _ = library
    token=client.get('/api/platform/bootstrap').json()['token'];headers={'X-Xueya-Token':token}
    doc=next(d for d in app.state.platform.repo.all(app.state.platform.scope(),'document') if d.get('isPlatform'))
    response=client.post('/api/learning/questions/generate',headers=headers,
                         json={'selection':{'documentIds':[doc['id']]},'count':1,'types':['single']})
    assert response.status_code>=400 and response.json()['error']=='RAG_USE_CASE_FORBIDDEN'
