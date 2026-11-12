import copy
import pytest

from backend.xueya.common import AppError
from backend.xueya.study_space_service import StudySpaceService


def draft(service, title):
    return service.create_plan_draft('alice', {'title':title,'goal':'复习基础知识','daysCount':3,'dailyMinutes':30,'restDays':[], 'tasks':[{'title':'学习并复习','minutes':30}]})


def identity(plan):
    return {'id':plan['id'],'revision':plan['revision']} if plan else None


def test_old_draft_can_replace_current_only_with_fresh_explicit_confirmation(platform):
    service=StudySpaceService(platform)
    old=draft(service,'旧草稿'); first=draft(service,'已采用计划')
    active=service.adopt_plan('alice',first['id'],1,True,'first')
    with pytest.raises(AppError,match='PLAN_CURRENT_CHANGED'):
        service.adopt_plan('alice',old['id'],1,True,'legacy')
    with pytest.raises(AppError,match='PLAN_CURRENT_CHANGED'):
        service.adopt_plan('alice',old['id'],1,True,'stale',expected_current=None)
    with pytest.raises(AppError,match='CONFIRMATION_REQUIRED'):
        service.adopt_plan('alice',old['id'],1,False,'unconfirmed',expected_current=identity(active))
    result=service.adopt_plan('alice',old['id'],1,True,'fresh',expected_current=identity(active))
    assert result['status']=='active' and result['id']==old['id']
    assert service.get_plan('alice',first['id'])['status']=='archived'
    assert service.adopt_plan('alice',old['id'],1,True,'fresh',expected_current=identity(active))==result
    assert len([p for p in service.repo.all(service._scope('alice'),'plan') if p['status']=='active'])==1
    assert not platform.db.one('SELECT id FROM invocations')


def test_concurrent_progress_change_still_blocks_replacement_until_confirmed_again(platform):
    service=StudySpaceService(platform)
    first=draft(service,'执行计划')
    active=service.adopt_plan('alice',first['id'],1,True,'first')
    old=draft(service,'待采用草稿')
    observed=identity(active)
    task=active['days'][0]['tasks'][0]
    service.toggle_task('alice',active['id'],task['id'],True,expected_revision=active['revision'],operation_id='progress')
    current=copy.deepcopy(service.get_active_plan('alice'))
    with pytest.raises(AppError,match='PLAN_CURRENT_CHANGED'):
        service.adopt_plan('alice',old['id'],1,True,'racing',expected_current=observed)
    assert service.get_active_plan('alice')==current
    assert service.get_plan('alice',old['id'])['status']=='draft'
    adopted=service.adopt_plan('alice',old['id'],1,True,'confirmed-again',expected_current=identity(current))
    assert adopted['id']==old['id']
    archived=service.get_plan('alice',first['id'])
    assert archived['days'][0]['tasks'][0]['completed']


@pytest.mark.parametrize('invalid',[{},False,{'id':'other','revision':True},{'id':'other','revision':0},{'id':'other','revision':1,'extra':0}])
def test_invalid_current_snapshot_never_changes_active_plan(platform,invalid):
    service=StudySpaceService(platform); plan=draft(service,'草稿')
    with pytest.raises(AppError,match='INVALID_CURRENT_PLAN'):
        service.adopt_plan('alice',plan['id'],1,True,'invalid',expected_current=invalid)
    assert service.get_active_plan('alice') is None


def test_confirmed_absent_current_is_supported(platform):
    service=StudySpaceService(platform); plan=draft(service,'第一份计划')
    assert service.adopt_plan('alice',plan['id'],1,True,'initial',expected_current=None)['status']=='active'


def test_http_adoption_optional_current_is_forwarded_and_validated(client):
    client.get('/api/learning/space/plan/list',headers=client.platform_headers)
    service=client.app.state.study_space
    first=service.create_plan_draft('local',{'goal':'第一份','daysCount':2,'dailyMinutes':30})
    old=service.create_plan_draft('local',{'goal':'旧草稿','daysCount':2,'dailyMinutes':30})
    active=service.adopt_plan('local',first['id'],1,True,'active')
    url='/api/learning/space/plan/adopt'
    value={'planId':old['id'],'expectedRevision':1,'confirmed':True,'operationId':'http'}
    assert client.post(url,headers=client.platform_headers,json=value).json()['error']=='PLAN_CURRENT_CHANGED'
    response=client.post(url,headers=client.platform_headers,json={**value,'expectedCurrent':identity(active)})
    assert response.status_code==200,response.text
    assert response.json()['plan']['id']==old['id']
