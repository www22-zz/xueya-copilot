import json
import pytest
from backend.xueya.common import AppError,dumps
from backend.xueya.study_space_service import StudySpaceService


def pending(service):
    plan=service.create_plan_draft('alice',{'goal':'队列学习','daysCount':3,'dailyMinutes':30,'restDays':[],
                                         'tasks':[{'title':'队列基础','minutes':30}]})
    scope=service._scope('alice');plan['generationStatus']='framework-pending'
    service.repo.put(scope,'plan',plan['id'],plan,1)
    return plan,scope


@pytest.mark.parametrize('status,owner,stage,matching,account,eligible',[
    ('unknown','alice','framework',True,'alice',True),
    ('failed','alice','framework',True,'alice',True),
    ('cancelled','alice','framework',True,'alice',True),
    ('running','alice','framework',True,'alice',False),
    ('queued','alice','framework',True,'alice',False),
    ('unknown','bob','framework',True,'alice',False),
    ('unknown','alice','planning',True,'alice',False),
    ('unknown','alice','framework',False,'alice',False),
    ('unknown','alice','framework',True,'bob',False),
])
def test_only_terminated_matching_owner_checkpoint_unlocks_saved_plan(platform,status,owner,stage,matching,account,eligible):
    service=StudySpaceService(platform);plan,scope=pending(service)
    if 'space-plan-generate' not in platform.jobs.handlers:
        async def dummy(*args,**kwargs):return {}
        platform.jobs.register('space-plan-generate',dummy)
    other=service._scope(owner)
    job=platform.jobs.submit(other.user_id,{'courseId':other.course_id,'type':'space-plan-generate','resource':'api','maxAttempts':1,'idempotencyKey':'partial','input':{'account':account}})
    platform.db.execute('UPDATE jobs SET status=?,checkpoint=?,error=? WHERE id=?',
                        (status,dumps({'stage':stage,'planId':plan['id'] if matching else 'different'}),'AI_INVALID_RESPONSE',job['id']))
    view=service.list_plans('alice')['drafts'][0]
    assert view['canAdopt'] is eligible and view['revision']==1
    assert service.repo.read(scope,'plan',plan['id'])['version']==2  # GET did not change storage.
    assert service.get_active_plan('alice') is None
    with pytest.raises(AppError,match='CONFIRMATION_REQUIRED'):
        service.adopt_plan('alice',plan['id'],1,False,'unconfirmed')
    with pytest.raises(AppError,match='PLAN_REVISION_CONFLICT'):
        service.adopt_plan('alice',plan['id'],99,True,'stale')
    if eligible:
        adopted=service.adopt_plan('alice',plan['id'],1,True,'adopt')
        assert adopted['status']=='active' and adopted['frameworkStatus']=='failed'
        assert adopted['days']==plan['days'] and adopted.get('frameworkId') is None
        assert service.adopt_plan('alice',plan['id'],1,True,'adopt')==adopted
        task=adopted['days'][0]['tasks'][0]
        service.toggle_task('alice',plan['id'],task['id'],True,expected_revision=adopted['revision'],operation_id='complete')
        assert service.get_active_plan('alice')['days'][0]['tasks'][0]['completed'] is True
    else:
        with pytest.raises(AppError,match='GENERATION_NOT_COMPLETED'):
            service.adopt_plan('alice',plan['id'],1,True,'adopt')
    assert not platform.db.all('SELECT id FROM invocations')
