"""Bound planning metadata without losing source question/phase identities."""
import json
from types import SimpleNamespace

import pytest

from backend.xueya.common import AppError
from backend.xueya.material_learning import MaterialLearning
from backend.xueya.study_space_service import StudySpaceService


class CapturingModel:
    def __init__(self, tokens=4096, extra_tasks=False):
        self.config=SimpleNamespace(max_output_tokens=tokens)
        self.calls=[]
        self.extra_tasks=extra_tasks

    async def generate(self,messages,**kwargs):
        payload=json.loads(messages[1]['content'])
        self.calls.append((messages,payload,kwargs))
        count=payload['maxTasks']+1 if self.extra_tasks else min(3,payload['maxTasks'])
        resources=payload['resources']
        tasks=[]
        for i in range(count):
            task={'key':f't{i}','title':f'阶段练习{i}','subject':'数据结构','phase':f'阶段{i+1}',
                  'minutes':60,'dependsOn':[f't{i-1}'] if i else []}
            if resources:task['questionId']=resources[i*(len(resources)-1)//max(1,count-1)]['questionId']
            tasks.append(task)
        return {'content':json.dumps({'explanation':'按真实题目分阶段学习。','tasks':tasks},ensure_ascii=False)}


def conditions():
    return {'goal':'完成数据结构基础学习与练习','subjects':['数据结构'],'difficulty':'基础',
            'startDate':'2026-11-05','endDate':'2026-11-30','daysCount':26,'dailyMinutes':60,'restDays':[7]}


def seed_material_questions(service):
    scope=service._scope('alice')
    concepts={i:{'id':f'concept-{i}','label':f'知识点{i:02}', 'questionIds':[]} for i in range(21)}
    for i in range(88):
        topic=i%21
        qid=f'material-q-{i:03}'
        concepts[topic]['questionIds'].append(qid)
        service.repo.put(scope,'question',qid,{'id':qid,'type':'single','prompt':f'知识点{topic:02}的练习条件'+('正文'*100),
            'subject':f'知识点{topic:02}','courseSubject':'数据结构','conceptId':f'concept-{topic}',
            'materialId':'material-corpus','options':['A','B'],'answer':0,'explanation':'内部答案不要进入规划输入'},0)
    service.repo.put(scope,'artifact','material-corpus',{'concepts':list(concepts.values())},0)
    return scope


async def test_real_scale_material_plan_is_compact_and_preserves_phase_question_links(platform,monkeypatch):
    service=StudySpaceService(platform);scope=seed_material_questions(service)
    monkeypatch.setattr('backend.xueya.study_resources.question_catalog',lambda:[])
    monkeypatch.setattr('backend.xueya.course_records.platform_courses',lambda:[
        {'id':'ds-real','title':'数据结构课程','subject':'数据结构','verification':'verified-metadata',
         'episodes':[{'id':f'ds-{i}','title':f'第{i}讲'} for i in range(8)]},
        {'id':'os-not-selected','title':'操作系统','subject':'操作系统','episodes':[{'id':'os-1','title':'进程'}]}])
    model=CapturingModel()
    plan=await service.generate_model_plan('alice',model,conditions())
    messages,payload,kwargs=model.calls[0]
    assert len(payload['resources'])==21
    assert {r['topic'] for r in payload['resources']}=={f'知识点{i:02}' for i in range(21)}
    assert all(set(r)=={'questionId','title','subject','topic'} for r in payload['resources'])
    assert len(json.dumps(payload,ensure_ascii=False))<10000
    assert '内部答案' not in json.dumps(payload,ensure_ascii=False)
    assert [c['courseId'] for c in payload['courses']]==['ds-real']
    assert len(payload['courses'][0]['episodes'])==3
    assert payload['maxTasks']==20 and payload['availableStudyDays']==22
    assert payload['availableStudyMinutes']==1320
    assert kwargs['timeout']==120 and kwargs['max_output_tokens']==4096
    assert '不要逐日展开' in messages[0]['content']
    tasks=[task for day in plan['days'] for task in day['tasks']]
    assert len(tasks)==3 and len({t['phase'] for t in tasks})==3
    assert all(t['resource']['conceptId'] and t['resource']['materialId']=='material-corpus' for t in tasks)
    material=object.__new__(MaterialLearning);material.p=platform;material.service=service
    framework=material.plan_framework('alice',plan)
    linked=[n for n in framework['nodes'] if n.get('conceptId')]
    assert len(linked)==3
    for node in linked:
        assert node['resource']['questionId'] in node['questionIds']
        assert service.repo.read(scope,'question',node['resource']['questionId'])


@pytest.mark.parametrize('tokens,limit',[(1024,4),(2048,9),(4096,20),(8192,20)])
async def test_plan_output_budget_bounds_tasks_without_changing_other_model_json_defaults(platform,monkeypatch,tokens,limit):
    service=StudySpaceService(platform)
    monkeypatch.setattr('backend.xueya.study_resources.question_catalog',lambda:[])
    model=CapturingModel(tokens)
    await service.generate_model_plan('alice',model,conditions())
    assert model.calls[0][1]['maxTasks']==limit
    assert model.calls[0][2]['max_output_tokens']==min(tokens,4096)
    class OtherModel:
        async def generate(self,messages,**kwargs):
            assert kwargs['timeout']==60 and 'max_output_tokens' not in kwargs
            return {'content':'{"ok":true}'}
    assert await service.model_json('alice',OtherModel(),'read-only control',{})=={'ok':True}


async def test_bounded_catalog_sampling_includes_late_topics_and_discloses_partial_selection(platform,monkeypatch):
    service=StudySpaceService(platform)
    resources=[{'questionId':f'long-q-{i}','subject':'数据结构','title':'标题'*100,'topic':f'topic-{i}',
                'type':'question','version':1,'tags':[],'url':'#space/practice/ai/fake','category':'ai','matched':True} for i in range(300)]
    monkeypatch.setattr(service,'material_question_resources',lambda account:resources)
    monkeypatch.setattr('backend.xueya.study_resources.question_catalog',lambda:[])
    model=CapturingModel()
    await service.generate_model_plan('alice',model,conditions())
    payload=model.calls[0][1]
    selected=payload['resources']
    assert 1<len(selected)<=64 and len(json.dumps(selected,ensure_ascii=False))<=12000
    assert selected[0]['questionId']=='long-q-0' and selected[-1]['questionId']=='long-q-299'
    assert payload['resourceSelection']=={'availableTopics':300,'includedTopics':len(selected),'partial':True}


async def test_excess_tasks_are_rejected_instead_of_cutting_a_dependency_graph(platform,monkeypatch):
    service=StudySpaceService(platform)
    monkeypatch.setattr('backend.xueya.study_resources.question_catalog',lambda:[])
    with pytest.raises(AppError,match='AI_INVALID_RESPONSE'):
        await service.generate_model_plan('alice',CapturingModel(extra_tasks=True),conditions())
    assert not service.repo.all(service._scope('alice'),'plan')
