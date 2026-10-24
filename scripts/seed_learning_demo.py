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

        # 章节学习 / 复习计划 / 知识图谱 / 笔记 / AI 出题已随产品导航重构移除；
        # 演示种子只负责把示例课程资料导入本机服务，不再写入那些模块的数据。
        return {'courseId': course, 'documentId': doc['id']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:4173')
    parser.add_argument('--course',default='course-default')
    parser.add_argument('--credentials')
    args=parser.parse_args()
    print(json.dumps(seed(args.base_url,args.course,args.credentials),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
