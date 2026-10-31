"""Real course identities, private ownership and one explicit completion event."""
import copy
import pytest
from backend.xueya.common import AppError
from backend.xueya.course_records import CourseRecords, platform_courses
from backend.xueya.study_space_service import StudySpaceService


def private_course():
    return {'id':'custom-private','title':'个人数据结构','bvid':'BV1b7411N798','episodes':[{'id':'one','title':'栈与队列','bpage':1}]}


def test_private_course_revision_ownership_and_delete_preserve_history(platform):
    records=CourseRecords(platform)
    data={'course':private_course(),'expectedRevision':0,'operationId':'save-one'}
    first=records.save_course('alice',data)
    assert records.save_course('alice',data)==first
    assert first['course']['platform'] is False
    assert not records.course('bob','custom-private')
    with pytest.raises(AppError,match='COURSE_REVISION_CONFLICT'):
        records.save_course('alice',{**data,'operationId':'stale-save'})
    progress={'courseId':'custom-private','episodeId':'one','completed':True,'expectedRevision':0,'operationId':'complete-one'}
    assert records.record('alice',progress)==records.record('alice',progress)
    with pytest.raises(AppError,match='COURSE_NOT_FOUND'):records.record('bob',progress)
    records.delete_course('alice',{'courseId':'custom-private','expectedRevision':1,'operationId':'delete-one'})
    assert not records.course('alice','custom-private') and records.continue_learning('alice') is None
    assert len(platform.repo.all(records.scope('alice'),'event'))==1


def test_course_plan_double_direction_and_new_review_instance(platform):
    records=CourseRecords(platform);space=StudySpaceService(platform)
    course=platform_courses()[0];episode=course['episodes'][0]
    draft=space.create_plan_draft('alice',{'dailyMinutes':30,'daysCount':2,'restDays':[],
        'tasks':[{'title':'学习课程章节','minutes':30,'courseId':course['id'],'episodeId':episode['id']}]})
    task=draft['days'][0]['tasks'][0]
    assert task['kind']=='course' and task['resource']['courseId']==course['id']
    active=space.adopt_plan('alice',draft['id'],1,True)
    data={'courseId':course['id'],'episodeId':episode['id'],'completed':True,'expectedRevision':0,'operationId':'manual-complete'}
    result=records.record('alice',data)
    assert result['syncedTasks']==1 and records.record('alice',data)==result
    active=space.get_active_plan('alice')
    assert active['days'][0]['tasks'][0]['completed'] is True
    before=len(platform.repo.all(records.scope('alice'),'event'))
    space.toggle_task('alice',active['id'],task['id'],False,expected_revision=active['revision'],operation_id='undo-task')
    assert records.listing('alice')['progress'][course['id']]['episodes'][episode['id']]['completed'] is False
    assert len(platform.repo.all(records.scope('alice'),'event'))==before+2
    # An already-completed course is not applied to later review instances.
    records.record('alice',{**data,'operationId':'complete-again','expectedRevision':2})
    next_draft=space.create_plan_draft('alice',{'dailyMinutes':30,'daysCount':1,'restDays':[],
        'tasks':[{'title':'再次闭卷回忆','minutes':30}]})
    assert next_draft['days'][0]['tasks'][0]['completed'] is False


def test_position_is_not_completion_and_cannot_claim_iframe_telemetry(platform):
    records=CourseRecords(platform);course=platform_courses()[0];ep=course['episodes'][0]
    data={'courseId':course['id'],'episodeId':ep['id'],'seconds':120,'positionSource':'html5-observed','operationId':'position-one'}
    with pytest.raises(AppError,match='INVALID_VIDEO_POSITION'):
        records.record('alice',{**data,'positionSource':'official-iframe'})
    result=records.record('alice',data)
    assert result['progress']['completed'] is False and not platform.repo.all(records.scope('alice'),'event')
    assert records.continue_learning('alice')['url'].endswith('/'+ep['id'])
    assert records.continue_learning('bob') is None
    assert records.continue_learning('alice')['seconds']==120
    with pytest.raises(AppError,match='COURSE_REVISION_CONFLICT'):
        records.record('alice',{**data,'expectedRevision':0,'operationId':'stale-position'})


def test_model_cannot_reference_another_accounts_private_course(platform):
    records=CourseRecords(platform);records.save_course('alice',{'course':private_course(),'operationId':'save-private'})
    service=StudySpaceService(platform)
    request={'dailyMinutes':30,'daysCount':1,'restDays':[], 'tasks':[{'title':'另一账号的课程','minutes':30,'courseId':'custom-private','episodeId':'one'}]}
    assert service.create_plan_draft('alice',request)['days'][0]['tasks'][0]['kind']=='course'
    assert service.create_plan_draft('bob',request)['days'][0]['tasks'][0]['kind']=='self-study'


def test_original_course_ids_and_episode_ids_are_preserved():
    courses=platform_courses()
    assert len(courses)==7 and sum(len(c['episodes']) for c in courses)==22
    assert courses[0]['id']=='cs-ds-algo' and courses[0]['episodes'][0]['id']=='ds-ep-1'
    assert all(c['verification']=='legacy-unverified' for c in courses)
