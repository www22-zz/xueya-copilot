"""Fixed resource identities, preview/adopt, event dedup and stale updates."""
import copy
import pytest

from backend.xueya.common import AppError
from backend.xueya.study_resources import external_link, question_catalog
from backend.xueya.study_space_service import StudySpaceService


def plan(service):
    resource=next(r for r in question_catalog() if r['category']=='exam408')
    draft=service.create_plan_draft('alice',{'goal':'复习计算机基础','startDate':'2026-11-02','daysCount':5,
        'dailyMinutes':30,'restDays':[],'tasks':[
            {'title':'完成第一轮基础练习','minutes':30,'questionId':resource['questionId'],'phase':'基础'},
            {'title':'闭卷整理所学概念','minutes':45,'phase':'巩固'}]})
    adopted=service.adopt_plan('alice',draft['id'],1,True,'initial-adopt')
    return adopted,resource


def test_only_real_resources_are_resolved_and_answers_do_not_enter_catalog(platform):
    service=StudySpaceService(platform);current,resource=plan(service)
    task=current['days'][0]['tasks'][0]
    assert task['resource']==resource and task['kind']=='practice'
    assert task['resource']['url'].endswith('/'+resource['questionId'])
    assert all(not {'answer','rubric','explanation','solution'} & set(r) for r in question_catalog())
    fake=service.create_plan_draft('alice',{'dailyMinutes':30,'daysCount':1,'restDays':[],
        'tasks':[{'title':'需要不存在的课程','minutes':20,'questionId':'nonexistent','resource':{'courseId':'invented'}}]})
    assert fake['days'][0]['tasks'][0]['resource']['type']=='self-study'
    assert fake['days'][0]['tasks'][0]['resource']['matched'] is False


@pytest.mark.parametrize('url',['javascript:alert(1)','data:text/html,bad','http://127.0.0.1/a','https://example.com@127.0.0.1/a','https://user:pass@example.com','https://example.com\n/bad'])
def test_external_resource_protocols_and_private_targets_are_rejected(url):
    with pytest.raises(AppError):external_link(url)


def test_link_and_completion_receipts_do_not_duplicate_events(platform):
    service=StudySpaceService(platform);current,_=plan(service)
    task=current['days'][0]['tasks'][0]
    data={'planId':current['id'],'taskId':task['id'],'expectedRevision':current['revision'],
          'operationId':'add-link','url':'https://docs.python.org/3/tutorial/','title':'用户补充'}
    linked=service.attach_task_link('alice',data)
    assert linked==service.attach_task_link('alice',data)
    assert linked['resource']['sourceType']=='user-link' and linked['resource']['verification']=='unverified'
    with pytest.raises(AppError,match='IDEMPOTENCY_CONFLICT'):
        service.attach_task_link('alice',{**data,'url':'https://example.com/other'})
    before=len(service.repo.all(service._scope('alice'),'event'))
    result=service.toggle_task('alice',current['id'],task['id'],True,expected_revision=linked['plan']['revision'],operation_id='complete-one')
    assert service.toggle_task('alice',current['id'],task['id'],True,expected_revision=linked['plan']['revision'],operation_id='complete-one')==result
    assert len(service.repo.all(service._scope('alice'),'event'))==before+1
    assert service.toggle_task('alice',current['id'],task['id'],True)['plan']['revision']==result['plan']['revision']


def test_adjustment_is_unpaid_draft_and_preserves_completed_identity(platform):
    service=StudySpaceService(platform);current,_=plan(service)
    first=current['days'][0]['tasks'][0]
    result=service.toggle_task('alice',current['id'],first['id'],True)
    active_before=copy.deepcopy(service.get_active_plan('alice'))
    params={'planId':current['id'],'expectedRevision':result['plan']['revision'],'startDate':'2026-11-03',
            'dailyMinutes':15,'endDate':'2026-11-10','restDays':[7],'operationId':'adjust-one'}
    draft=service.adjust_plan_draft('alice',params)
    assert draft==service.adjust_plan_draft('alice',params)
    assert service.get_active_plan('alice')==active_before
    assert draft['completedHistory'][0]['id']==first['id'] and draft['completedHistory'][0]['completedAt']
    unfinished_before={t['sourceTaskId'] for d in active_before['days'] for t in d['tasks'] if not t['completed']}
    assert {t['sourceTaskId'] for d in draft['days'] for t in d['tasks']}==unfinished_before
    assert all(not day['tasks'] if day['isRestDay'] else sum(t['minutes'] for t in day['tasks'])<=15 for day in draft['days'])
    adopted=service.adopt_plan('alice',draft['id'],1,True,'adopt-adjustment')
    assert service.adopt_plan('alice',draft['id'],1,True,'adopt-adjustment')==adopted
    assert adopted['completedHistory']==draft['completedHistory']
    assert service.get_plan('alice',current['id'])['status']=='archived'
    assert service.get_active_plan('bobby') is None


def test_stale_preview_cannot_overwrite_completion_and_failed_defer_keeps_original(platform):
    service=StudySpaceService(platform);current,_=plan(service)
    draft=service.adjust_plan_draft('alice',{'planId':current['id'],'expectedRevision':current['revision'],'dailyMinutes':60})
    first=current['days'][0]['tasks'][0]
    service.toggle_task('alice',current['id'],first['id'],True)
    with pytest.raises(AppError,match='REPLAN_SOURCE_CHANGED'):
        service.adopt_plan('alice',draft['id'],1,True,'stale-adopt')
    unchanged=copy.deepcopy(service.get_active_plan('alice'))
    with pytest.raises(AppError):service.delay_task('alice',current['id'],first['id'],'2026-11-04',operation_id='invalid-defer')
    assert service.get_active_plan('alice')==unchanged
