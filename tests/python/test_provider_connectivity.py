import asyncio
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.common import AppError, Scope
from backend.xueya.config import Config
from backend.xueya.platform import Platform
from backend.xueya.provider import MimoProvider
from test_material_learning import Model


async def test_connectivity_probe_has_no_credentials_content_or_invocation(tmp_path):
    requests = []
    def receive(request):
        requests.append(request)
        return httpx.Response(404)
    config = Config(data_dir=tmp_path,api_key='secret-key',base_url='https://provider.invalid/v1?private=hidden')
    platform = Platform(tmp_path,preserve_legacy_data=True)
    try:
        provider = MimoProvider(config,platform,httpx.MockTransport(receive))
        assert await provider.probe_connectivity()=={'connected':True,'httpStatus':404,'inference':False}
        assert len(requests)==1
        assert requests[0].method=='GET' and str(requests[0].url)=='https://provider.invalid/'
        assert 'authorization' not in requests[0].headers and not requests[0].content
        assert not platform.db.all('SELECT id FROM invocations')
    finally:
        await platform.close()


async def test_transport_error_records_class_without_sensitive_message(tmp_path):
    secret = 'secret-body-and-key'
    def broken(request):
        raise httpx.ConnectError(secret,request=request)
    config = Config(data_dir=tmp_path,api_key=secret,base_url='https://provider.invalid/v1')
    platform = Platform(tmp_path,preserve_legacy_data=True)
    try:
        provider = MimoProvider(config,platform,httpx.MockTransport(broken))
        with pytest.raises(AppError,match='AI_CONNECTION_FAILED'):
            await provider.probe_connectivity()
        assert not platform.db.all('SELECT id FROM invocations')
        with pytest.raises(httpx.ConnectError):
            await provider.generate([{'role':'user','content':'synthetic'}],scope=Scope(user_id=platform.user_id,course_id='course-default'))
        invocation = platform.db.one('SELECT * FROM invocations')
        assert invocation['status']=='unknown' and invocation['usage_json'] is None
        record = platform.db.one('SELECT value FROM meta WHERE key=?',('invocation-context:'+invocation['id'],))['value']
        assert json.loads(record)['errorType']=='ConnectError' and secret not in record
    finally:
        await platform.close()


def test_unreachable_host_refuses_batch_before_any_jobs_or_model_calls(tmp_path,http_root):
    class OfflineModel(Model):
        probes = 0
        async def probe_connectivity(self):
            self.probes += 1
            raise AppError('AI_CONNECTION_FAILED')
    model = OfflineModel()
    app = create_app(Config(root=http_root,data_dir=tmp_path/'data',api_key='controlled',
                           preserve_legacy_data=True,auto_import_demo=False),provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'probeowner','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        client.post('/api/platform/library/text',json={'courseId':'course-default','title':'synthetic',
                    'text':'队列先进先出。'*100,'idempotencyKey':'probe-test'})
        async def drain():
            queue=app.state.platform.jobs;queue.stopped=False
            for _ in range(200):
                await queue.tick()
                if all(r['status'] not in ('queued','running') for r in app.state.platform.db.all('SELECT status FROM jobs')):return
                await asyncio.sleep(.001)
        asyncio.run(drain())
        calls = model.calls
        endpoint='/api/learning/space/course-graph/continue'
        value={'courseId':'course-default','confirmedExternal':True,'callLimit':10}
        # Access/limit checks must run before even the free transport probe.
        assert client.post(endpoint,json={**value,'courseId':'not-owned'}).status_code!=200
        assert client.post(endpoint,json={**value,'callLimit':True}).status_code!=200
        assert model.probes==0
        response=client.post(endpoint,json=value)
        assert response.status_code!=200 and response.json()['error']=='AI_CONNECTION_FAILED'
        assert model.probes==1 and model.calls==calls
        assert not app.state.platform.db.all("SELECT id FROM jobs WHERE type='course-graph-range'")


def test_plan_preflight_refuses_offline_submission_without_jobs_or_inference(tmp_path,http_root):
    class OfflineModel(Model):
        probes=0
        async def probe_connectivity(self):
            self.probes+=1
            raise AppError('AI_CONNECTION_FAILED')
    model=OfflineModel()
    app=create_app(Config(root=http_root,data_dir=tmp_path/'plan',api_key='controlled',
                         preserve_legacy_data=True,auto_import_demo=False),provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'planner','password':'Fixture123','confirmPassword':'Fixture123'})
        value={'goal':'学习队列','daysCount':7,'dailyMinutes':30,'operationId':'offline-plan'}
        assert client.post('/api/learning/space/plan/generate',json=value).status_code!=200
        assert model.probes==0
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        invalid=client.post('/api/learning/space/plan/generate',json={**value,'dailyMinutes':True})
        assert invalid.json()['error']=='INVALID_DAILY_MINUTES' and model.probes==0
        result=client.post('/api/learning/space/plan/generate',json=value)
        assert result.json()['error']=='AI_CONNECTION_FAILED'
        assert model.calls==0 and model.probes==1
        assert not app.state.platform.db.all("SELECT id FROM jobs WHERE type='space-plan-generate'")
        assert not app.state.platform.db.all('SELECT id FROM invocations')
        assert client.get('/api/learning/space/plan/connectivity').json()['error']=='AI_CONNECTION_FAILED'
        assert model.calls==0


def test_existing_plan_receipt_is_recovered_offline_without_new_probe(tmp_path,http_root):
    class SwitchModel(Model):
        probes=0
        offline=False
        async def probe_connectivity(self):
            self.probes+=1
            if self.offline:raise AppError('AI_CONNECTION_FAILED')
            return {'connected':True,'inference':False}
    model=SwitchModel()
    app=create_app(Config(root=http_root,data_dir=tmp_path/'receipt',api_key='controlled',
                         preserve_legacy_data=True,auto_import_demo=False),provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'planner','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        value={'goal':'学习队列','daysCount':7,'dailyMinutes':30,'operationId':'lost-receipt'}
        first=client.post('/api/learning/space/plan/generate',json=value).json()['job']
        assert model.probes==1
        model.offline=True
        repeated=client.post('/api/learning/space/plan/generate',json=value)
        assert repeated.json()['job']['id']==first['id'] and model.probes==1
        changed=client.post('/api/learning/space/plan/generate',json={**value,'dailyMinutes':60})
        assert changed.json()['error']=='IDEMPOTENCY_CONFLICT' and model.probes==1
        assert len(app.state.platform.db.all("SELECT id FROM jobs WHERE type='space-plan-generate'"))==1
        assert model.calls==0


def test_plan_connection_drop_keeps_unknown_ledger_and_explains_old_jobs(tmp_path,http_root):
    secret='do-not-expose-provider-details'
    requests=[]
    def receive(request):
        requests.append(request.method)
        if request.method=='GET':
            assert not request.content and 'authorization' not in request.headers
            return httpx.Response(404)
        raise httpx.ConnectError(secret,request=request)
    config=Config(root=http_root,data_dir=tmp_path/'drop',api_key='controlled',
                  base_url='https://provider.invalid/v1',preserve_legacy_data=True,auto_import_demo=False)
    app=create_app(config,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        app.state.provider=MimoProvider(config,app.state.platform,httpx.MockTransport(receive))
        client.post('/api/account/register',json={'username':'planner','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        assert client.get('/api/learning/space/plan/connectivity').json()['connected'] is True
        response=client.post('/api/learning/space/plan/generate',json={
            'goal':'理解队列','daysCount':7,'dailyMinutes':30,'operationId':'dropped-plan'})
        assert response.status_code==200
        job=response.json()['job']
        async def drain():
            queue=app.state.platform.jobs;queue.stopped=False
            for _ in range(100):
                await queue.tick()
                if queue.get(job['id'],job['userId'])['status'] in ('failed','unknown'):break
                await asyncio.sleep(.005)
        # get() accepts the scoped owner from the stored row, not client input.
        owner=app.state.platform.db.one('SELECT user_id FROM jobs WHERE id=?',(job['id'],))['user_id']
        job['userId']=owner
        asyncio.run(drain())
        stored=app.state.platform.jobs.get(job['id'],owner)
        assert stored['status']=='unknown' and stored['error']=='AI_CONNECTION_FAILED' and stored['attempts']==1
        ledger=app.state.platform.db.one('SELECT * FROM invocations')
        assert ledger['status']=='unknown' and ledger['billing_status']=='unknown' and ledger['usage_json'] is None
        # Simulate the old generic error without editing or retrying its invocation.
        app.state.platform.db.execute("UPDATE jobs SET error='JOB_FAILED' WHERE id=?",(job['id'],))
        listing=client.get('/api/learning/space/plan/list')
        assert listing.json()['jobs'][0]['diagnosticCode']=='AI_CONNECTION_FAILED'
        assert secret not in listing.text
        assert listing.json()['drafts']==[]
        assert requests.count('POST')==1
