"""Planning intent, missing conditions, durable generation and no paid replay."""
import asyncio
import json
import pytest
from fastapi.testclient import TestClient

from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.common import AppError


class Model:
    def __init__(self):self.calls=[];self.fail_framework=False
    async def generate(self,messages,**kwargs):
        self.calls.append(messages)
        if '拆解可执行任务' in messages[0]['content']:
            value={'explanation':'先学习概念，再主动回忆。','tasks':[{'title':'复习进程切换','subject':'操作系统','minutes':30,'phase':'基础'}]}
        else:
            if self.fail_framework:raise AppError('AI_TIMEOUT')
            value={'title':'进程管理','nodes':[{'id':'root','label':'进程','parentId':None},{'id':'switch','label':'上下文切换','parentId':'root'}]}
        return {'content':json.dumps(value,ensure_ascii=False),'model':'controlled'}


@pytest.fixture
def setup(tmp_path,http_root):
    model=Model();config=Config(root=http_root,data_dir=tmp_path/'planning',preserve_legacy_data=True)
    app=create_app(config,provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert client.post('/api/account/register',json={'username':'alice','password':'Fixture123','confirmPassword':'Fixture123'}).status_code==200
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        yield app,client,model,config


def intake(client,text,operation='one',**extra):
    response=client.post('/api/learning/space/chat/plan',json={'question':text,'sessionId':'session-one','operationId':operation,**extra})
    assert response.status_code==200,response.text
    return response.json()


async def finish(app,job_id):
    p=app.state.platform;p.jobs.stopped=False
    for _ in range(300):
        await p.jobs.tick()
        job=p.jobs.get(job_id,'space:alice')
        if job['status'] in ('succeeded','failed','unknown','cancelled'):return job
        await asyncio.sleep(.01)
    pytest.fail('plan job did not finish')


def test_explaining_planning_does_not_create_job_or_call_model(setup):
    app,client,model,_=setup
    assert intake(client,'什么是学习规划？')['handled'] is False
    assert not model.calls
    assert app.state.conversation_planning.listing('alice')==[]


def test_existing_long_history_does_not_break_non_planning_chat_dispatch(setup):
    _,client,model,_=setup
    history=[{'role':'assistant','content':'历史'*2500} for _ in range(8)]
    response=intake(client,'二叉树是什么？','long-history',history=history)
    assert response['handled'] is False and not model.calls


def test_missing_conditions_reuse_known_user_information_and_explicit_defaults(setup):
    _,client,model,_=setup
    first=intake(client,'帮我规划操作系统，每天45分钟')
    assert first['missing']==['daysCount'] and first['conditions']['dailyMinutes']==45
    assert not model.calls
    selected=intake(client,'按默认条件安排','two')
    assert selected['conditions']['daysCount']==28 and selected['conditions']['dailyMinutes']==45
    assert selected['jobId']
    assert intake(client,'按默认条件安排','two')['jobId']==selected['jobId']
    assert not model.calls # submission alone is not generation or adoption


def test_history_conditions_are_not_asked_again_and_forged_account_is_ignored(setup):
    app,client,_,_=setup
    value=intake(client,'请帮我制定学习计划','history',history=[{'role':'user','content':'我想复习操作系统，两周，每天30分钟'}],accountId='bobby')
    assert value['status']=='queued' and value['conditions']=={'goal':'操作系统','daysCount':14,'dailyMinutes':30}
    assert app.state.conversation_planning.status('alice',value['jobId'])
    with pytest.raises(AppError):app.state.conversation_planning.status('bobby',value['jobId'])


def test_both_entries_generate_same_kind_of_persisted_draft_and_independent_framework(setup):
    app,client,model,_=setup
    response=client.post('/api/learning/space/plan/generate',json={'goal':'操作系统','daysCount':14,'dailyMinutes':30,'operationId':'analysis-entry'}).json()
    job=asyncio.run(finish(app,response['job']['id']));assert job['status']=='succeeded',job
    service=app.state.conversation_planning.service
    plan=service.get_plan('alice',job['result']['planId']);fw=service.get_framework('alice',job['result']['frameworkId'])
    assert plan['status']=='draft' and plan['generationStatus']=='completed'
    assert fw['planId']==plan['id'] and plan['frameworkId']==fw['id']
    assert service.get_active_plan('alice') is None
    assert fw['nodes'][1]['label']=='上下文切换' and 'date' not in fw['nodes'][1]
    assert len(model.calls)==2
    before=len(model.calls)
    assert client.get('/api/learning/space/plan/list').json()['drafts'][0]['id']==plan['id']
    assert client.get('/api/learning/space/framework/'+fw['id']).json()['framework']['id']==fw['id']
    assert len(model.calls)==before


def test_failed_framework_keeps_partial_draft_and_never_auto_replays_after_restart(setup):
    app,client,model,config=setup;model.fail_framework=True
    submitted=intake(client,'帮我规划操作系统，两周，每天30分钟')
    job=asyncio.run(finish(app,submitted['jobId']));assert job['status']=='unknown'
    plan=app.state.conversation_planning.service.get_plan('alice',job['checkpoint']['planId'])
    assert plan['status']=='draft' and plan['generationStatus']=='framework-pending'
    adoption=client.post('/api/learning/space/plan/adopt',json={'planId':plan['id'],'expectedRevision':1,'confirmed':True,'operationId':'not-complete'})
    assert adoption.json()['error']=='GENERATION_NOT_COMPLETED'
    assert len(model.calls)==2
    again=intake(client,'帮我规划操作系统，两周，每天30分钟')
    assert again['jobId']==job['id'] and len(model.calls)==2
    with TestClient(create_app(config,provider=model,start_jobs=False),base_url='http://127.0.0.1') as recovered:
        recovered.post('/api/account/login',json={'username':'alice','password':'Fixture123'})
        headers={'X-Xueya-Token':recovered.get('/api/platform/bootstrap').json()['token']}
        assert recovered.get('/api/learning/space/jobs/'+job['id'],headers=headers).json()['job']['status']=='unknown'
        assert len(model.calls)==2
