import asyncio
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config


def test_plan_response_timeout_is_explicit_and_never_retried(tmp_path,http_root):
    class Model:
        calls=0
        async def generate(self,*args,**kwargs):
            self.calls+=1
            raise TimeoutError('private provider detail')
    model=Model()
    app=create_app(Config(root=http_root,data_dir=tmp_path/'timeout',api_key='controlled',
                         preserve_legacy_data=True,auto_import_demo=False),provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'timeout-owner','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        job=client.post('/api/learning/space/plan/generate',json={
            'goal':'学习数据结构','subjects':['数据结构'],'daysCount':26,'dailyMinutes':60,'operationId':'timeout-once'}).json()['job']
        async def drain():
            queue=app.state.platform.jobs;queue.stopped=False
            await queue.tick()
            await asyncio.gather(*list(queue.active.values()))
            await queue.tick()
        asyncio.run(drain())
        value=client.get('/api/learning/space/plan/list').json()
        saved=value['jobs'][0]
        assert saved['id']==job['id'] and saved['status']=='unknown' and saved['error']=='AI_PLAN_RESPONSE_TIMEOUT'
        assert saved['diagnosticCode']=='AI_PLAN_RESPONSE_TIMEOUT'
        assert model.calls==1 and saved['attempts']==1 and value['drafts']==[]
        assert 'private provider detail' not in str(value)
