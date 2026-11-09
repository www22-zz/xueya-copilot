"""Opt-in bounded real service checks using only a synthetic temporary library."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from backend.xueya.app import create_app
from backend.xueya.config import load_config
from backend.xueya.common import Scope,require
from .check_real_learning_space import BoundedProvider

ROOT=Path(__file__).resolve().parents[1]


async def run(exam_only=False):
    output=ROOT/'test-results/real-learning-space';output.mkdir(parents=True,exist_ok=True)
    report={'syntheticOnly':True,'limit':1 if exam_only else 3,'checks':[]}
    with tempfile.TemporaryDirectory(prefix='xueya-real-material-') as folder:
        config=replace(load_config(),data_dir=Path(folder),auto_import_demo=False,preserve_legacy_data=True,api_slots=1)
        require(bool(config.api_key),'AI_UNAVAILABLE')
        provider=BoundedProvider(config,None,1 if exam_only else 3);provider.phase='material-exam' if exam_only else 'material'
        app=create_app(config,provider=provider,start_jobs=False)
        async with app.router.lifespan_context(app):
            p=app.state.platform;account='synthetic-material';owner='synthetic-private-owner'
            p.db.execute('INSERT INTO meta(key,value) VALUES(?,?)',('local-account-v1',json.dumps({'username':account,'dataOwner':owner})))
            scope=Scope(user_id=owner,course_id='course-default')
            p.repo.ensure_course(owner,{'id':'course-default','name':'数据结构'})
            async def finish(job):
                p.jobs.stopped=False
                for _ in range(2000):
                    await p.jobs.tick()
                    owner_row=p.db.one('SELECT user_id FROM jobs WHERE id=?',(job['id'],))
                    current=p.jobs.get(job['id'],owner_row['user_id'])
                    if current['status'] not in ('queued','running','cancelling'):
                        require(current['status']=='succeeded',current.get('error') or current['status']);return current['result']
                    await asyncio.sleep(.1)
                require(False,'REAL_CHECK_TIMEOUT')
            try:
                if exam_only:
                    job=app.state.exam_sessions.create(account,{'mode':'ai','count':3,'minutes':15,'operationId':'synthetic-independent-exam'})['job']
                    exam=(await finish(job))['session']
                    report['checks'].append({'name':'ai-exam-selection','status':'passed','questions':len(exam['questions'])})
                    return 0
                text=('# 合成队列教材\n队列是一种先进先出的线性结构，队头删除，队尾插入。'
                      '空队列不能删除元素。循环队列可使用长度计数区分队满与队空。'
                      '使用数组长度N、头索引front和元素个数size，尾部插入位置为(front+size)%N。'
                      '本样例中size为0时为空，size为N时为满。入队和出队都为O(1)。\n')*8
                parsed=app.state.library.text_import(scope,{'title':'合成队列讲义','text':text,'idempotencyKey':'synthetic-upload'})
                await finish(parsed)
                listing=app.state.material_learning.listing(account,owner,'course-default')['materials']
                material=listing[0]
                generated=await finish(p.jobs.get(material['jobId'],'space:'+account))
                report['checks'].append({'name':'material-generation','questions':len(generated['questionIds']),'status':'passed'})
                q=app.state.space_quiz.question(account,generated['questionIds'][0])
                plan=await app.state.material_learning.service.generate_model_plan(account,provider,{
                    'goal':'只复习给定资料知识点，并选用给定题目的questionId，不要仅安排自主学习。',
                    'daysCount':3,'dailyMinutes':30,'restDays':[],'subjects':[q['subject']],'difficulty':'基础'})
                graph=app.state.material_learning.plan_framework(account,plan)
                require(graph is not None,'PLAN_MATERIAL_LINK_MISSING')
                report['checks'].append({'name':'plan-material-graph','status':'passed','nodes':len(graph['nodes'])})
                job=app.state.exam_sessions.create(account,{'mode':'ai','count':3,'minutes':15,'operationId':'synthetic-exam'})['job']
                exam=(await finish(job))['session']
                report['checks'].append({'name':'ai-exam-selection','status':'passed','questions':len(exam['questions'])})
            except Exception as error:
                report['checks'].append({'name':'interrupted','status':'failed','error':getattr(error,'code',type(error).__name__)})
            finally:
                report['providerAttempts']=provider.calls
                report['externalInvocationRecords']=len(p.db.all('SELECT id FROM invocations'))
                report['usage']=[{'status':r['status'],'usage':json.loads(r['usage_json']) if r.get('usage_json') else None}
                    for r in p.db.all('SELECT status,usage_json FROM invocations')]
                report['allPassed']=len(report['checks'])==(1 if exam_only else 3) and all(c['status']=='passed' for c in report['checks'])
                (output/('material-exam-result.json' if exam_only else 'material-result.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(report,ensure_ascii=True),flush=True)
    return 0 if report['allPassed'] else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--authorized',action='store_true');parser.add_argument('--exam-only',action='store_true');args=parser.parse_args()
    if not args.authorized:parser.error('Requires explicit --authorized; maximum three real model requests')
    raise SystemExit(asyncio.run(run(args.exam_only)))


if __name__=='__main__':main()
