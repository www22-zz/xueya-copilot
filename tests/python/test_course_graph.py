import asyncio
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.common import Scope
from test_material_learning import Model


def test_full_range_resume_merge_isolation_and_revision(tmp_path, http_root):
    model = Model()
    app = create_app(Config(root=http_root,data_dir=tmp_path/'data',api_key='controlled',
        preserve_legacy_data=True,auto_import_demo=False),provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'alice','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        client.post('/api/platform/library/text',json={'courseId':'course-default','title':'多章队列讲义',
            'text':'# 队列\n'+('队列具有先进先出性质，队头出队，队尾入队。\n'*500),'idempotencyKey':'full-graph'})
        async def drain():
            p=app.state.platform;p.jobs.stopped=False
            for _ in range(1000):
                await p.jobs.tick()
                if all(r['status'] not in ('queued','running') for r in p.db.all('SELECT status FROM jobs')):return
                await asyncio.sleep(.001)
            raise AssertionError('jobs did not finish')
        asyncio.run(drain())
        endpoint='/api/learning/space/course-graph'
        before=model.calls
        graph=client.get(endpoint).json()
        assert model.calls==before # Reading never submits or pays.
        assert graph['coverage']['totalRanges']>2
        assert not graph['coverage']['inputComplete']
        request={'callLimit':2,'confirmedExternal':True}
        first=client.post(endpoint+'/continue',json=request).json()
        assert len(first['jobIds'])==2
        # Concurrent/repeated submissions skip all queued range identities.
        again=client.post(endpoint+'/continue',json=request).json()
        assert not set(first['jobIds']) & set(again['jobIds'])
        asyncio.run(drain())
        partial=client.get(endpoint).json()
        assert partial['coverage']['completedRanges']==4
        client.post(endpoint+'/continue',json={'callLimit':50,'confirmedExternal':True})
        asyncio.run(drain())
        full=client.get(endpoint).json()
        assert full['coverage']['inputComplete']
        assert full['coverage']['remainingCalls']==0
        concepts=[n for n in full['nodes'] if n['kind']=='concept']
        assert len(concepts)==full['coverage']['completedRanges']+1
        assert len({n['id'] for n in concepts})==len(concepts)
        assert full['coverage']['questions']==4*len(concepts) # Equal titles/prompts do not prove a shared source identity.
        assert client.post(endpoint+'/continue',json=request).json()['jobIds']==[]
        assert client.post(endpoint+'/continue',json={'callLimit':1}).status_code!=200
        assert client.get(endpoint+'?courseId=not-owned').status_code!=200
        assert client.post(endpoint+'/continue',json={'confirmedExternal':True,'callLimit':True}).status_code!=200
        m=app.state.material_learning
        from backend.xueya.account_scope import account_owner
        owner=account_owner({'username':'alice'})
        scope,_,ranges=m.corpus.inventory('alice',owner,'course-default')
        assert all(r['saved'] for r in ranges)
        assert all(sum(p['end']-p['start'] for p in r['part'])<=1800 for r in ranges)
        # Withdrawn originals remove their derived nodes from the current graph.
        source_scope=Scope(**ranges[0]['scope'])
        record=m.p.repo.read(source_scope,'document',ranges[0]['rawId'])
        m.p.repo.put(source_scope,'document',ranges[0]['rawId'],{**record['value'],'archived':True},record['version'])
        assert not [n for n in client.get(endpoint).json()['nodes'] if n['kind']=='concept']
        client.post('/api/account/register',json={'username':'bob','password':'Fixture123','confirmPassword':'Fixture123'})
        isolated=client.get(endpoint).json()
        assert not isolated['documents'] and len(isolated['nodes'])==1


def test_title_normalization_preserves_meaningful_operators():
    from backend.xueya.course_graph import label_key
    assert label_key(' 队列，操作 ')==label_key('队列操作')
    assert label_key('C++')!=label_key('C')
    assert label_key('a+b')!=label_key('a-b')
