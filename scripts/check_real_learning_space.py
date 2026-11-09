"""Explicitly authorized, bounded real API smoke checks on synthetic isolated data.

Never use this script as part of pytest or check_isolated. No user workspace,
private library, OCR or vector index is opened. Reports contain statuses/usage,
not configuration secrets. Each provider request occurs at most once.
"""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

from backend.xueya.common import AppError
from backend.xueya.config import load_config
from backend.xueya.platform import Platform
from backend.xueya.provider import MimoProvider
from backend.xueya.space_planning import ConversationPlanning
from backend.xueya.space_quiz import SpaceQuiz
from backend.xueya.framework_jobs import FrameworkJobs
from backend.xueya.practice_analysis import PracticeAnalysis

ROOT=Path(__file__).resolve().parents[1]


class BoundedProvider(MimoProvider):
    def __init__(self,config,platform,limit):
        super().__init__(config,platform);self.calls=0;self.limit=limit

    async def generate(self,*args,**kwargs):
        if self.calls>=self.limit:raise AppError('SMOKE_REQUEST_LIMIT')
        self.calls+=1
        result=await super().generate(*args,**kwargs)
        # Only this isolated synthetic runner persists response bodies; no keys.
        folder=ROOT/'test-results/real-learning-space';folder.mkdir(parents=True,exist_ok=True)
        (folder/(self.phase+'-response-'+str(self.calls)+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result


async def run(limit,phase):
    output=ROOT/'test-results/real-learning-space';output.mkdir(parents=True,exist_ok=True)
    result={'data':'synthetic-isolated','paidRequests':0,'limit':limit,'checks':[]}
    with tempfile.TemporaryDirectory(prefix='xueya-authorized-api-') as temporary:
        config=replace(load_config(),data_dir=Path(temporary),auto_import_demo=False,preserve_legacy_data=True,api_slots=1)
        if not config.api_key:raise AppError('AI_UNAVAILABLE')
        platform=Platform(config.data_dir,api_slots=1,preserve_legacy_data=True)
        platform.jobs.budget_config=config;platform.jobs.stopped=False
        provider=BoundedProvider(config,platform,limit)
        provider.phase=phase
        app=SimpleNamespace(state=SimpleNamespace(platform=platform,provider=provider,config=config))
        plans=ConversationPlanning(app);quizzes=SpaceQuiz(app);frameworks=FrameworkJobs(app)
        analysis=PracticeAnalysis(platform,provider,config)
        account='synthetic-real-check'
        async def finish(job):
            for _ in range(1800):
                owner=analysis.scope(account).user_id if job['type'].startswith('practice-analysis') else quizzes.scope(account).user_id
                await platform.jobs.tick();current=platform.jobs.get(job['id'],owner)
                if current['status'] not in ('queued','running','cancelling'):
                    if current['status']!='succeeded':raise AppError(current.get('error') or current['status'])
                    return current['result']
                await asyncio.sleep(.1)
            raise AppError('SMOKE_JOB_TIMEOUT')
        def record(name,status='passed',**extra):
            row={'name':name,'status':status,**extra};result['checks'].append(row)
            print(json.dumps(row,ensure_ascii=True),flush=True)
        try:
            async with provider.connection_pool():
                if phase in ('analysis','report'):
                    from .real_learning_fixture import seed
                    seed(platform,account)
                    if phase=='report':
                        from backend.xueya.course_records import CourseRecords,platform_courses
                        course=platform_courses()[0]
                        CourseRecords(platform).record(account,{'courseId':course['id'],'episodeId':course['episodes'][0]['id'],'completed':False,'operationId':'independent-course-undo'})
                    report_result=await finish(analysis.submit(account,{'days':7,'idempotencyKey':'independent-real-report'}))
                    report=analysis.report(account,report_result['reportId'])
                    assert report['snapshot']['activitySources']['counts']['quizAttempts']==1
                    record('multi-source-report',findings=len(report['analysis']['findings']))
                    await finish(analysis.submit(account,{'reportId':report['id'],'message':'只有一次作答和一次手动确认，哪些结论仍不能确定？','idempotencyKey':'independent-real-followup'},chat=True))
                    assert len(analysis.report(account,report['id'])['conversation'])==2
                    record('report-followup')
                    if phase=='report':return 0
                    generated=await finish(quizzes.submit_generation(account,{'subject':'操作系统临界区与互斥基础','type':'single','count':1,'operationId':'real-objective'}))
                    question=quizzes.question(account,generated['questionIds'][0])
                    answer=quizzes.submit_attempt(account,{'questionId':question['id'],'questionRevision':question['revision'],'answer':question['answer'],'operationId':'real-objective-answer'})
                    assert answer['effectiveEvaluation']['result']['correct'] is True
                    record('objective-question-server-judgement')
                    return 0
                planned=await finish(plans.submit(account,{'goal':'3天复习操作系统临界区与互斥，不超过3项任务','daysCount':3,'dailyMinutes':30,'restDays':[],'subjects':['操作系统'],'operationId':'real-plan'}))
                plan=plans.service.get_plan(account,planned['planId']);graph=plans.service.get_framework(account,planned['frameworkId'])
                assert plan['status']=='draft' and plan['generationStatus']=='completed'
                assert graph['planId']==plan['id'] and all(sum(t['minutes'] for t in d['tasks'])<=d['budgetMinutes'] for d in plan['days'])
                record('plan-and-framework',tasks=sum(len(d['tasks']) for d in plan['days']),concepts=len(graph['nodes']))
                generated=await finish(quizzes.submit_generation(account,{'subject':'操作系统临界区与互斥基础','type':'short','count':1,'operationId':'real-quiz'}))
                question=quizzes.question(account,generated['questionIds'][0])
                submitted=quizzes.submit_attempt(account,{'questionId':question['id'],'questionRevision':question['revision'],
                    'answer':'临界区是访问共享资源的代码。互斥要求同一时刻最多一个进程进入相关临界区，避免并发修改破坏数据。还需要保证空闲让进和有限等待，具体规则取决于题目中的同步条件。','operationId':'real-answer'})
                await finish(platform.jobs.get(submitted['evaluations'][0]['jobId'],quizzes.scope(account).user_id))
                attempt=quizzes.attempt(account,submitted['id']);assert attempt['effectiveEvaluation']['status']=='graded'
                record('subjective-question-and-review',hasRubric=bool(question.get('rubric')),hasScore='score' in attempt['effectiveEvaluation']['result'])
                root=next(n for n in graph['nodes'] if n['parentId'] is None)
                await finish(frameworks.submit(account,{'mode':'expand','frameworkId':graph['id'],'expectedRevision':graph['revision'],
                    'nodeId':root['id'],'instruction':'只补充两个现有图中遗漏的具体子概念','operationId':'real-expand'}))
                expanded=plans.service.get_framework(account,graph['id']);assert len(expanded['nodes'])>len(graph['nodes'])
                record('framework-expansion',added=len(expanded['nodes'])-len(graph['nodes']))
                report_result=await finish(analysis.submit(account,{'days':7,'idempotencyKey':'real-report'}))
                report=analysis.report(account,report_result['reportId'])
                assert report['snapshot']['activitySources']['counts']['quizAttempts']==1
                record('multi-source-report',findings=len(report['analysis']['findings']),attempts=report['snapshot']['activitySources']['counts']['quizAttempts'])
                await finish(analysis.submit(account,{'reportId':report['id'],'message':'这份样例只有一次作答，应该如何理解分析的限制？','idempotencyKey':'real-followup'},chat=True))
                assert len(analysis.report(account,report['id'])['conversation'])==2
                record('report-followup')
                current=quizzes.attempt(account,attempt['id'])
                reviewed=quizzes.review(account,current['id'],{'expectedRevision':current['revision'],'reason':'请按原rubric核对遗漏，不因长度评分。','operationId':'real-rereview'})
                entry=reviewed['evaluations'][-1]
                if entry.get('jobId'):await finish(platform.jobs.get(entry['jobId'],quizzes.scope(account).user_id))
                assert len(quizzes.attempt(account,attempt['id'])['evaluations'])==2
                record('assessment-version-chain')
        except Exception as error:
            record('interrupted',status='not-completed',error=error.code if isinstance(error,AppError) else type(error).__name__)
        finally:
            result['paidRequests']=provider.calls
            result['invocations']=[{'status':r['status'],'usage':json.loads(r['usage_json']) if r.get('usage_json') else None} for r in platform.db.all('SELECT status,usage_json FROM invocations')]
            result['allPassed']=all(r['status']=='passed' for r in result['checks']) and len(result['checks'])==({'analysis':3,'report':2}.get(phase,6))
            (output/(phase+'-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'paidRequests':provider.calls,'allPassed':result['allPassed'],'output':str(output/(phase+'-result.json'))},ensure_ascii=True),flush=True)
            await platform.close()
    return 0 if result['allPassed'] else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--authorized',action='store_true');parser.add_argument('--max-calls',type=int,default=8)
    parser.add_argument('--phase',choices=('learning','analysis','report'),default='learning')
    args=parser.parse_args()
    if not args.authorized or not 1<=args.max_calls<=8:parser.error('Requires explicit --authorized and 1..8 bounded requests')
    raise SystemExit(asyncio.run(run(args.max_calls,args.phase)))


if __name__=='__main__':main()
