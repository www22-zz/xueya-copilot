"""Generated plan wording follows the real fixed-bank source boundary."""
import copy
import json

import pytest

from backend.xueya.common import AppError
from backend.xueya.study_space_service import StudySpaceService


@pytest.mark.parametrize('source,expected',[
    ('真题改编题与真题复习','考点改编题与考点练习复习'),
    ('原创题与考点改编','原创题与考点改编'),
    (None,None),
])
def test_source_claim_normalization_is_display_only(source,expected):
    assert StudySpaceService.generated_plan_text(source)==expected


async def test_generated_labels_change_without_rewriting_user_goal_question_or_schedule(platform):
    service=StudySpaceService(platform)
    returned={}
    class Model:
        async def generate(self,messages,**kwargs):
            payload=json.loads(messages[1]['content'])
            assert '固定题为原创或考点改编' in messages[0]['content']
            assert '课程总览不代表' in messages[0]['content']
            qid=payload['resources'][0]['questionId']
            returned.update({'explanation':'使用真题和真题改编题巩固基础。','tasks':[
                {'key':'first','title':'真题改编题精练','subject':'数据结构','phase':'真题基础阶段','minutes':90,'dependsOn':[],'questionId':qid}]})
            return {'content':json.dumps(returned,ensure_ascii=False)}
    request={'title':'我的真题备考目标','goal':'学习真题解法并巩固基础','subjects':['数据结构'],
             'startDate':'2026-11-05','endDate':'2026-11-08','daysCount':4,'dailyMinutes':60,'restDays':[7]}
    snapshot=copy.deepcopy(request)
    plan=await service.generate_model_plan('alice',Model(),request)
    assert request==snapshot
    assert plan['title']==request['title'] and plan['goal']==request['goal']
    assert plan['explanation']=='使用考点练习和考点改编题巩固基础。'
    tasks=[t for day in plan['days'] for t in day['tasks']]
    assert [t['minutes'] for t in tasks]==[60,30]
    assert all(t['title']=='考点改编题精练' and t['phase']=='考点练习基础阶段' for t in tasks)
    assert all(t['resource']['questionId']==returned['tasks'][0]['questionId'] for t in tasks)
    assert returned['tasks'][0]['title']=='真题改编题精练'
    assert plan['startDate']=='2026-11-05' and plan['endDate']=='2026-11-08'
    assert all(not day['tasks'] for day in plan['days'] if day['isRestDay'])
    assert all(sum(t['minutes'] for t in day['tasks'])<=day['budgetMinutes'] for day in plan['days'])


async def test_display_protection_does_not_repair_invalid_task_content(platform):
    service=StudySpaceService(platform)
    class InvalidModel:
        async def generate(self,*args,**kwargs):
            return {'content':json.dumps({'explanation':'真题说明','tasks':[{'key':'bad','title':None,'minutes':30}]})}
    with pytest.raises(AppError,match='INVALID_PLAN_TASKS'):
        await service.generate_model_plan('alice',InvalidModel(),{'goal':'学习基础','daysCount':4,'dailyMinutes':60,'subjects':['数据结构']})
    assert not service.repo.all(service._scope('alice'),'plan')
