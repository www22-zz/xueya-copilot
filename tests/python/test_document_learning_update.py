import copy
import pytest
from backend.xueya.algorithm_trace import trace
from backend.xueya.learning_route import build, view, validate_attempt, sync_completion
from backend.xueya.study_space_service import StudySpaceService
from backend.xueya.common import AppError


@pytest.mark.parametrize('question_id,index,result', [('h100-63',0,2),('h100-63',1,1),('h100-63',2,4),('h100-53',0,1),('h100-53',1,3)])
def test_real_sample_traces(question_id,index,result):
    demo=trace(question_id,index)
    assert demo['result']==result
    if question_id=='h100-53':
        assert any('回溯' in s['note'] for s in demo['steps'])
        assert demo['steps'][-1]['stack']==[]
        for step in demo['steps']:
            for a,b in zip(step['stack'],step['stack'][1:]):
                assert abs(a[0]-b[0])+abs(a[1]-b[1])==1
    else:
        assert all(s['left']<=s['right'] for s in demo['steps'])
        assert demo['steps'][-1]['left']==result


def seed(service,account):
    scope=service._scope(account)
    for i in range(4):
        service.repo.put(scope,'question',f'q{i}',{'id':f'q{i}','type':'boolean','prompt':f'队列判断 {i}',
            'answer':True,'explanation':'FIFO','conceptId':'k','materialId':'m','difficulty':'简单' if i<3 else '困难','sourceRevision':'v1'},0)
    service.repo.put(scope,'artifact','m',{'concepts':[{'id':'k','label':'队列','questionIds':['q0','q1','q2','q3']} ]},0)
    plan={'id':'route-plan','title':'测试','status':'active','difficulty':'基础','days':[
        {'date':'2026-11-06','isRestDay':False,'tasks':[{'id':'t1','title':'队列练习','minutes':20,'phase':'线性结构','resource':{'conceptId':'k','materialId':'m'}}]},
        {'date':'2026-11-07','isRestDay':False,'tasks':[{'id':'t2','title':'队列复习','minutes':20,'phase':'巩固','resource':{'conceptId':'k','materialId':'m'}}]},
        {'date':'2026-11-08','isRestDay':True,'tasks':[]}]}
    plan['learningRoute']=build(service,account,plan)
    service.repo.put(scope,'plan',plan['id'],plan,0)
    return scope,plan


def test_fixed_groups_completion_and_stage_isolation(platform):
    service=StudySpaceService(platform);scope,plan=seed(service,'alice')
    original=copy.deepcopy(plan['learningRoute'])
    assert [q['id'] for q in original['phases'][0]['stages'][0]['nodes'][0]['questions']]==['q0','q1']
    assert original['phases'][1]['stages'][0]['nodes'][0]['missingCount']==1
    assert view(service,'alice',plan)['days'][0]['completed'] is False
    for i in range(2):
        attempt={'id':f'a{i}','questionId':f'q{i}','questionRevision':1,'planId':plan['id'],'nodeId':'t1',
                 'createdAt':f'2026-11-06T00:0{i}:00Z','evaluations':[{'status':'graded','result':{'correct':i==0}}]}
        service.repo.put(scope,'attempt',attempt['id'],attempt,0)
        if i==0:assert not view(service,'alice',plan)['days'][0]['completed']
    result=view(service,'alice',plan)
    assert result['days'][0]['completed']
    assert not result['days'][1]['completed'] and not result['days'][2]['completed']
    assert result['phases'][0]['report']['firstAccuracy']==.5
    assert result['phases'][1]['report']['firstAccuracy'] is None
    sync_completion(service,'alice',plan['id']);sync_completion(service,'alice',plan['id'])
    assert len([a for a in service.repo.all(scope,'artifact') if a.get('kind')=='study-completion'])==1
    assert service.repo.read(scope,'plan',plan['id'])['value']['learningRoute']==original
    q={**service.repo.read(scope,'question','q0')['value'],'revision':1}
    assert validate_attempt(service,'alice',{'planId':plan['id'],'nodeId':'t1'},q)['nodeId']=='t1'
    with pytest.raises(AppError):validate_attempt(service,'alice',{'planId':plan['id'],'nodeId':'t2'},q)
    with pytest.raises(AppError):validate_attempt(service,'bob',{'planId':plan['id'],'nodeId':'t1'},q)


def test_supplement_uses_original_sources_and_receipt(tmp_path,http_root):
    import asyncio
    import json
    import runpy
    from pathlib import Path
    from fastapi.testclient import TestClient
    from backend.xueya.app import create_app
    from backend.xueya.config import Config
    Base=runpy.run_path(str(Path(__file__).with_name('test_material_learning.py')))['Model']
    class Model(Base):
        async def generate(self,messages,**kwargs):
            reply=await super().generate(messages,**kwargs)
            data=json.loads(reply['content'])
            if '只为指定知识点补题' in messages[0]['content']:
                for node in data['concepts']:
                    for i,q in enumerate(node['questions']):
                        q.update(prompt=q['prompt']+'（补充练习）',difficulty='中等',difficultyReason='结合队头与队尾操作推导')
            reply['content']=json.dumps(data,ensure_ascii=False)
            return reply
    model=Model();app=create_app(Config(root=http_root,data_dir=tmp_path/'data',api_key='controlled',
        preserve_legacy_data=True,auto_import_demo=False),provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'alice','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        client.post('/api/platform/library/text',json={'courseId':'course-default','title':'队列','text':'# 队列\n'+('先进先出，队头出队，队尾入队。\n'*60),'idempotencyKey':'supplement-source'})
        async def drain():
            p=app.state.platform;p.jobs.stopped=False
            for _ in range(500):
                await p.jobs.tick()
                if all(j['status'] not in ('queued','running') for j in p.db.all('SELECT status FROM jobs')):return
                await asyncio.sleep(.01)
            raise AssertionError('jobs did not finish')
        asyncio.run(drain())
        m=client.get('/api/learning/space/materials').json()['materials'][0]
        node=m['concepts'][0];path='/api/learning/space/materials/concept/'+node['id']
        before=client.get(path).json();assert len(before['groups']['待分级'])==4
        data={'conceptId':node['id'],'difficulty':'中等','confirmedExternal':True}
        first=client.post('/api/learning/space/materials/supplement',json=data).json()['job']
        second=client.post('/api/learning/space/materials/supplement',json=data).json()['job']
        assert first['id']==second['id']
        asyncio.run(drain())
        after=client.get(path).json()
        assert len(after['groups']['中等'])==4 and len(after['groups']['待分级'])==4,after
        assert after['jobs'][0]['status']=='succeeded'
        assert all(q['conceptId']==node['id'] and q['sourceRevision']==m['revision'] for q in after['groups']['中等'])
        assert all('answer' not in q for q in after['groups']['中等'])
        assert model.calls==2
        client.get(path);client.post('/api/learning/space/materials/supplement',json=data);asyncio.run(drain())
        assert model.calls==2
        failed={**data,'difficulty':'困难'}
        bad=client.post('/api/learning/space/materials/supplement',json=failed).json()['job']
        asyncio.run(drain())
        assert app.state.platform.jobs.get(bad['id'],'space:alice')['status']=='unknown'
        again=client.post('/api/learning/space/materials/supplement',json=failed).json()['job']
        assert again['id']==bad['id']
        asyncio.run(drain());assert model.calls==3
        client.post('/api/account/register',json={'username':'bob','password':'Fixture123','confirmPassword':'Fixture123'})
        assert client.get(path).status_code!=200
        assert client.post('/api/learning/space/materials/supplement',json=data).status_code!=200
