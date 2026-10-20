"""Import authored demo materials through existing HTTP APIs, without model calls."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import time
from uuid import uuid4
from urllib.parse import parse_qsl
import httpx

ROOT = Path(__file__).resolve().parents[1]


def seed(base='http://127.0.0.1:4173', course='course-default', credentials=None):
    with httpx.Client(base_url=base,timeout=30,trust_env=False) as client:
        if credentials:
            value=json.loads(Path(credentials).read_text(encoding='utf-8'))
            response=client.post('/api/account/login',json=value)
            if response.status_code!=200: raise RuntimeError('团队账号登录未完成')
        bootstrap=client.get('/api/platform/bootstrap')
        if bootstrap.status_code!=200: raise RuntimeError('请先登录本地服务')
        client.headers['X-Xueya-Token']=bootstrap.json()['token']
        def api(path,body=None,platform=False):
            route,_,query=path.partition('?')
            url=('/api/platform/' if platform else '/api/learning/')+route
            response=client.request('POST' if body is not None else 'GET',url,params={**dict(parse_qsl(query)),'courseId':course},json=body)
            data=response.json()
            if response.status_code>=400 or not data.get('ok'):raise RuntimeError(path+': '+str(data.get('error','请求失败')))
            return data.get('result',data)
        catalog=api('library/catalog',platform=True)
        title='【演示】数据结构：栈与队列'
        doc=next((d for d in catalog['documents'] if d['name']==title+'.md'),None)
        if doc is None:
            text=(ROOT/'demo/materials/栈与队列-演示资料.md').read_text(encoding='utf-8')
            job=api('library/text',{'title':title,'text':text,'chapter':'栈与队列（演示）','idempotencyKey':'demo-stack-queue-v1'},True)['job']
            for _ in range(300):
                if job['status'] in ('succeeded','failed','cancelled','unknown'):break
                time.sleep(.1)
                job=api('jobs/status?id='+job['id'],platform=True)['job']
            if job['status']!='succeeded':raise RuntimeError('演示资料解析尚未成功')
            catalog=api('library/catalog',platform=True)
            doc=next(d for d in catalog['documents'] if d['name']==title+'.md')
        selection={'documentIds':[doc['id']]}
        workspace=api('workspace')
        sources=[s for s in workspace['sources'] if s.get('documentId')==doc['id']]
        def source(quote):return next(s for s in sources if quote in s['quote'])
        def ref(quote):
            s=source(quote)
            return {'sourceId':s['id'],'version':s['version'],'quote':quote}
        def existing(key):
            r=client.get('/api/learning/artifacts',params={'courseId':course,'id':key})
            if r.status_code==404:return None
            if r.status_code!=200:raise RuntimeError('无法核对已有演示内容')
            return r.json()['result']
        def adopt(path,body,key):
            old=existing(key)
            if old:return old
            draft=api(path,{**body,'id':key,'expectedRevision':0,'selection':selection})
            return api('draft/adopt',{'draftId':draft['draftId'],'operationId':'demo-'+str(uuid4()),'confirmed':True})
        note=adopt('note/preview',{'title':'【演示】栈与队列对照笔记','text':'# 栈与队列\n\n演示笔记，依据已导入的演示资料手工编写。\n\n| 结构 | 规则 | A、B、C加入后首次取出 |\n| --- | --- | --- |\n| 栈 | 后进先出 LIFO | C |\n| 队列 | 先进先出 FIFO | A |\n\n先模拟操作顺序，再完成练习和复习卡。'},'demo-note-stack-queue')
        questions=[]
        examples=[('stack','【演示】A、B、C依次入栈，第一次出栈是？',['A','B','C'],2,'栈遵循后进先出（LIFO）原则。','C最后入栈，因此先出栈。'),('queue','【演示】A、B、C依次入队，第一次出队是？',['A','B','C'],0,'队列遵循先进先出（FIFO）原则。','A最先入队，因此先出队。')]
        for suffix,prompt,options,answer,quote,explanation in examples:
            key='demo-question-'+suffix
            row=existing('question:'+key)
            if not row:
                s=source(quote)
                row=api('questions/manual',{'id':key,'operationId':'demo-'+str(uuid4()),'expectedRevision':0,'selection':selection,'question':{'type':'single','prompt':prompt,'options':options,'answer':answer,'sourceId':s['id'],'evidenceQuote':quote,'explanation':explanation,'conceptIds':[],'difficulty':'easy'}})
            if row['content']['status']!='approved':
                row=api('questions/review',{'id':key,'expectedRevision':row['revision'],'expectedVersion':row['content']['version'],'operationId':'demo-'+str(uuid4()),'selection':selection,'approved':True,'reason':'演示数据：已对照演示资料的定义与操作例子核对，不代表个人真实作答。'})
            questions.append(key)
            adopt('card/preview',{'prompt':prompt,'answer':explanation,'evidence':[ref(quote)]},'demo-card-'+suffix)
        adopt('quiz/preview',{'questionIds':questions,'count':2},'demo-quiz-stack-queue')
        graph=api('graph')
        content=graph['content']
        added=[]
        for suffix,name,quote in [('stack','栈（演示）','栈遵循后进先出（LIFO）原则。'),('queue','队列（演示）','队列遵循先进先出（FIFO）原则。')]:
            if not any(c['id']=='demo-concept-'+suffix for c in content['concepts']):
                content['concepts'].append({'id':'demo-concept-'+suffix,'courseId':course,'name':name,'aliases':[],'status':'confirmed','evidence':[ref(quote)]})
                added.append(suffix)
        if added:
            draft=api('graph/preview',{'graph':content,'expectedRevision':graph['revision'],'selection':{}})
            api('draft/adopt',{'draftId':draft['draftId'],'operationId':'demo-'+str(uuid4()),'confirmed':True})
        adopt('plan/preview',{'examDate':str(date.today()+timedelta(days=14)),'minutes':20,'availability':{}},'demo-plan-stack-queue')
        return {'courseId':course,'documentId':doc['id'],'note':'demo-note-stack-queue','questions':questions,'cards':['demo-card-stack','demo-card-queue'],'quiz':'demo-quiz-stack-queue','plan':'demo-plan-stack-queue','paidApiCalls':0,'studentAttemptsCreated':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:4173')
    parser.add_argument('--course',default='course-default')
    parser.add_argument('--credentials')
    args=parser.parse_args()
    print(json.dumps(seed(args.base_url,args.course,args.credentials),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
