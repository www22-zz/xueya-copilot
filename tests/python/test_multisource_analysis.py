"""Program facts, immutable sources and local-only scheduling with a fixed clock."""
import copy
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from backend.agent.practice_analysis import validate_report
from backend.xueya.analysis_sources import source_options,workspace_owner
from backend.xueya.analysis_schedule import AnalysisSchedule
from backend.xueya.common import AppError,dumps
from backend.xueya.config import Config
from backend.xueya.course_records import CourseRecords,platform_courses
from backend.xueya.practice_analysis import PracticeAnalysis

NOW=datetime(2026,10,31,4,tzinfo=timezone.utc)


class NoCalls:
    calls=0
    async def generate(self,*args,**kwargs):
        self.calls+=1
        raise AssertionError('local scheduling must never invoke any provider')


def analysis(platform):
    return PracticeAnalysis(platform,NoCalls(),Config(api_key='controlled',auto_import_demo=False,preserve_legacy_data=True))


def course_event(platform,monkeypatch):
    monkeypatch.setattr('backend.xueya.course_records.utc_now',lambda:NOW.isoformat())
    course=platform_courses()[0]
    records=CourseRecords(platform)
    records.record('alice',{'courseId':course['id'],'episodeId':course['episodes'][0]['id'],'completed':True,'operationId':'confirm-course'})


def test_conversation_exclusion_scope_and_branch_message_dedup(platform,workspace):
    platform.db.execute('INSERT INTO meta(key,value) VALUES(?,?)',('account-v2:fixture',dumps({'username':'alice','dataOwner':'owner-alice'})))
    value=copy.deepcopy(workspace);data=value['courses'][0]['data']
    data['messages']=[]
    data['sessions']=[{'id':'one','title':'学习操作系统','messages':[{'id':'m-one','role':'user','text':'解释进程状态','createdAt':NOW.isoformat()}, {'id':'ai-one','role':'ai','text':'你已完全掌握','createdAt':NOW.isoformat()}]},
        {'id':'fork','title':'学习操作系统分支','messages':[{'id':'m-one','role':'user','text':'解释进程状态','createdAt':NOW.isoformat()}]},
        {'id':'nonlearning','title':'外卖','messages':[{'id':'m-two','role':'user','text':'今天吃什么','createdAt':NOW.isoformat()}]}]
    platform.repo.save_workspace('owner-alice',value,0)
    host=analysis(platform);options={'days':7,**source_options({})}
    snapshot=host.capture('alice',options,NOW)
    assert snapshot['activitySources']['counts']['userQuestions']==1
    assert all('你已完全掌握' not in json.dumps(e,ensure_ascii=False) for e in snapshot['activitySources']['evidence'])
    assert host.capture('bob',options,NOW)['activitySources']['counts']['userQuestions']==0
    excluded=host.capture('alice',{**options,'excludedSessionIds':['one','fork'],'includedSessionIds':['nonlearning']},NOW)
    assert [e['sessionId'] for e in excluded['activitySources']['evidence']]==['nonlearning']
    assert workspace_owner(platform,'alice')=='owner-alice'


def test_course_only_report_has_true_evidence_and_validates_references(platform,monkeypatch):
    course_event(platform,monkeypatch);host=analysis(platform)
    snapshot=host.capture('alice',{'days':7,**source_options({})},NOW)
    assert snapshot['stats']['attempts']==0 and snapshot['hasNonPracticeActivity']
    assert snapshot['activitySources']['counts']['courseConfirmations']==1
    evidence=snapshot['activitySources']['evidence'][0]['id']
    report={'title':'有限的课程观察','summary':'仅有手动确认，不能判断掌握。',
        'findings':[{'kind':'coverage','title':'已确认章节','detail':'基于实际课程事件。','questionIds':[],'evidenceIds':[evidence]}],
        'recommendations':[{'title':'闭卷复述','reason':'先补充理解依据。','questionIds':[],'evidenceIds':[evidence]}],
        'limitations':['没有客观练习记录。']}
    assert validate_report(json.dumps(report),snapshot)['recommendations'][0]['evidenceIds']==[evidence]
    report['recommendations'][0]['evidenceIds']=['session:another-account']
    with pytest.raises(AppError,match='ANALYSIS_INVALID_REFERENCE'):validate_report(json.dumps(report),snapshot)


def test_attempt_versions_are_not_attempts_and_snapshots_do_not_change(platform):
    host=analysis(platform)
    from backend.xueya.study_space_service import StudySpaceService
    scope=StudySpaceService(platform)._scope('alice')
    row={'id':'attempt-one','questionId':'question-one','createdAt':NOW.isoformat(),'answer':'原答案','evaluations':[
        {'id':'first','source':'ai-reference','status':'graded','result':{'score':1,'maxScore':4}},
        {'id':'human','source':'human','status':'graded','result':{'score':3,'maxScore':4}}]}
    row['effectiveEvaluation']=copy.deepcopy(row['evaluations'][-1])
    platform.repo.put(scope,'attempt',row['id'],row,0)
    snapshot=host.capture('alice',{'days':7,**source_options({})},NOW)
    assert snapshot['activitySources']['counts']['quizAttempts']==1
    assert snapshot['activitySources']['counts']['humanCorrection']==1 and snapshot['stats']['attempts']==0
    row['effectiveEvaluation']['result']['score']=4;platform.repo.put(scope,'attempt',row['id'],row,1)
    assert snapshot['activitySources']['evidence'][0]['evaluation']['result']['score']==3


def test_local_schedule_merge_multiworker_restart_and_no_provider_calls(platform,monkeypatch):
    course_event(platform,monkeypatch);host=analysis(platform);clock=[NOW]
    one=AnalysisSchedule(host,clock=lambda:clock[0]);two=AnalysisSchedule(host,clock=lambda:clock[0])
    first=one.read('alice')
    assert first['enabled'] and not first['automaticExternalDispatch']
    clock[0]=NOW+timedelta(days=35)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda service:service.tick('alice'),[one,two]))
    assert sum(result['status']=='awaiting-manual-analysis' for result in results)==1
    candidates=one.listing('alice');assert len(candidates)==1 and candidates[0]['window']['missedMerged']
    snapshot=copy.deepcopy(candidates[0]['snapshot'])
    assert host.p.db.one('SELECT COUNT(*) AS n FROM jobs')['n']==0 and host.provider.calls==0
    clock[0]+=timedelta(days=35)
    assert two.tick('alice')['status']=='skipped-no-new-records'
    assert one.listing('alice')[0]['snapshot']==snapshot
    current=two.read('alice')
    changed=two.update('alice',{'enabled':False,'expectedRevision':current['revision'],'operationId':'disable'})
    clock[0]+=timedelta(days=35);assert one.tick('alice')['status']=='not-due'
    assert changed['enabled'] is False and host.provider.calls==0
    with pytest.raises(AppError,match='AUTOMATIC_ANALYSIS_AUTHORIZATION_REQUIRED'):
        one.update('alice',{'expectedRevision':changed['revision'],'operationId':'unapproved-auto','automaticExternalDispatch':True})


def test_unknown_identical_snapshot_is_never_replayed_by_new_key(platform,monkeypatch):
    course_event(platform,monkeypatch);host=analysis(platform)
    request={'days':0,**source_options({})}
    snapshot=host.capture('alice',request,NOW)
    first=host.submit('alice',{**request,'idempotencyKey':'one'},captured=snapshot)
    platform.db.execute("UPDATE jobs SET status='unknown' WHERE id=?",(first['id'],))
    second=host.submit('alice',{**request,'idempotencyKey':'two'},captured={**snapshot,'cutoff':(NOW+timedelta(hours=1)).isoformat()})
    assert second['id']==first['id'] and second['status']=='unknown'
    assert platform.db.one('SELECT COUNT(*) AS n FROM jobs')['n']==1 and host.provider.calls==0


def test_automatic_dispatch_requires_account_opt_in_and_unknown_is_not_replayed(platform,monkeypatch):
    course_event(platform,monkeypatch);host=analysis(platform);clock=[NOW]
    schedule=AnalysisSchedule(host,clock=lambda:clock[0]);settings=schedule.read('alice')
    enabled=schedule.update('alice',{'expectedRevision':settings['revision'],'operationId':'explicit-consent',
        'automaticExternalDispatch':True,'confirmedExternalDispatch':True})
    assert enabled['externalDispatchConsentAt']
    clock[0]+=timedelta(days=30)
    outcome=schedule.tick('alice');assert outcome['status']=='submitted'
    platform.db.execute("UPDATE jobs SET status='unknown' WHERE id=?",(outcome['jobId'],))
    clock[0]+=timedelta(days=30)
    assert schedule.tick('alice')['status']=='skipped-no-new-records'
    assert platform.db.one('SELECT COUNT(*) AS n FROM jobs')['n']==1 and host.provider.calls==0
