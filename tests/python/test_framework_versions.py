"""Graph edits/undo, stale AI apply and durable expansion share one scoped graph."""
import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.common import AppError
from backend.xueya.config import Config
from backend.xueya.study_space_service import StudySpaceService


class Model:
    def __init__(self):self.before=None;self.calls=0
    async def generate(self,messages,**kwargs):
        self.calls+=1
        if self.before:self.before()
        if '局部细化' in messages[0]['content']:
            selected=json.loads(messages[1]['content'])['selected']
            value={'nodes':[{'id':'new','label':'互斥条件','parentId':selected},{'id':'next','label':'临界资源','parentId':'new'}]}
        else:value={'title':'进程概念','nodes':[{'id':'root','label':'进程','parentId':None}]}
        return {'content':json.dumps(value),'model':'controlled'}


@pytest.fixture
def setup(tmp_path,http_root):
    model=Model();app=create_app(Config(root=http_root,data_dir=tmp_path/'data'),provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        yield app,model


def initial(app,model):
    service=StudySpaceService(app.state.platform)
    graph=asyncio.run(service.generate_model_framework('alice',model,'操作系统','进程'))
    return service,service.get_framework('alice',graph['id'])


async def finish(app,job):
    p=app.state.platform;p.jobs.stopped=False
    for _ in range(100):
        await p.jobs.tick();row=p.jobs.get(job['id'],'space:alice')
        if row['status'] not in ('queued','running','cancelling'):return row
        await asyncio.sleep(.01)
    raise AssertionError('job did not finish')


def test_revision_and_undo_restore_graph_without_schedule_mutation(setup):
    app,model=setup;service,graph=initial(app,model)
    saved=service.patch_framework('alice',graph['id'],{'expectedRevision':graph['revision'],'addNode':{'label':'线程','parentId':'root'}})
    with pytest.raises(AppError,match='FRAMEWORK_REVISION_CONFLICT'):
        service.patch_framework('alice',graph['id'],{'expectedRevision':graph['revision'],'updateNode':{'id':'root','label':'迟到覆盖'}})
    restored=service.patch_framework('alice',graph['id'],{'expectedRevision':saved['revision'],'undo':True})
    assert restored['nodes']==graph['nodes'] and len(restored['undo'])==0
    assert not service.list_frameworks('bob') and service.get_active_plan('alice') is None


def test_expansion_is_atomic_and_one_undo_for_the_whole_operation(setup):
    app,model=setup;service,graph=initial(app,model)
    job=app.state.framework_jobs.submit('alice',{'mode':'expand','frameworkId':graph['id'],'nodeId':'root','expectedRevision':graph['revision'],'instruction':'补充互斥概念','operationId':'expand-one'})
    result=asyncio.run(finish(app,job));assert result['status']=='succeeded'
    expanded=service.get_framework('alice',graph['id']);assert len(expanded['nodes'])==3
    restored=service.patch_framework('alice',graph['id'],{'expectedRevision':expanded['revision'],'undo':True})
    assert restored['nodes']==graph['nodes']
    assert app.state.platform.jobs.get(job['id'],'space:bob') is None


def test_late_expansion_does_not_override_manual_edit(setup):
    app,model=setup;service,graph=initial(app,model)
    job=app.state.framework_jobs.submit('alice',{'mode':'expand','frameworkId':graph['id'],'nodeId':'root','expectedRevision':graph['revision'],'instruction':'继续细化','operationId':'expand-stale'})
    model.before=lambda:service.patch_framework('alice',graph['id'],{'expectedRevision':graph['revision'],'updateNode':{'id':'root','label':'我保留的修改'}})
    result=asyncio.run(finish(app,job));assert result['status']=='unknown' and result['error']=='FRAMEWORK_REVISION_CONFLICT'
    current=service.get_framework('alice',graph['id']);assert len(current['nodes'])==1 and current['nodes'][0]['label']=='我保留的修改'
    assert model.calls==2
