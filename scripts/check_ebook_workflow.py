"""Real public-book parsing and learning workflows in an isolated, API-free host."""
import argparse
from datetime import date,timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import parse_qsl
from uuid import uuid4
import httpx
from .check_learning_browser import ROOT
from backend.xueya.app import create_app
from backend.xueya.config import Config
from conftest import live_server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book',default='.xueya-data/public-books/How-to-Think-Like-a-Computer-Scientist-Python3.pdf')
    args=parser.parse_args();book=Path(args.book);output=Path('test-results/ebook-workflow');output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-book-test-') as directory:
        app=create_app(Config(data_dir=Path(directory)/'data',api_key=''))
        with live_server(app) as url,httpx.Client(base_url=url,timeout=90,trust_env=False) as client:
            client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
            def api(path,body=None,platform=False):
                route,_,query=path.partition('?');response=client.request('POST' if body is not None else 'GET',('/api/platform/' if platform else '/api/learning/')+route,params={**dict(parse_qsl(query)),'courseId':'course-default'},json=body)
                value=response.json()
                if response.status_code>=400:raise RuntimeError(path+': '+str(value.get('error')))
                return value.get('result',value)
            uploaded=client.post('/api/platform/rag/upload?courseId=course-default&name=Public-Python3-Book.pdf',content=book.read_bytes(),headers={'Idempotency-Key':'real-book-no-ai','Content-Type':'application/pdf'})
            assert uploaded.status_code in (200,202),uploaded.text
            job=uploaded.json()['job']
            for _ in range(600):
                if job['status'] in ('succeeded','failed','cancelled','unknown'):break
                time.sleep(.1);job=api('jobs/status?id='+job['id'],platform=True)['job']
            assert job['status']=='succeeded',job.get('error')
            doc=api('library/catalog',platform=True)['documents'][0]
            read=api('library/read?documentId='+doc['id'],platform=True)
            assert len(read['artifact']['pages'])==421
            evidence=api('rag/search',{'query':'LIFO push pop stack','documentIds':[doc['id']],'mode':'lexical','limit':5,'budget':6000},True)['evidence']
            source=next(s for s in evidence['sources'] if 'LIFO' in s['quote'] and s.get('page'))
            context=api('rag/read?sourceId='+source['id'],platform=True)
            selection={'sourceIds':[source['id']]}
            quote=source['quote']
            def adopt(path,value):
                preview=api(path,value)
                return api('draft/adopt',{'draftId':preview['draftId'],'operationId':'test-'+str(uuid4()),'confirmed':True})
            note=adopt('content/note/preview',{'id':'book-note','expectedRevision':0,'chapter':'第25章 栈','title':'电子书阅读验证','text':'A stack follows LIFO.\n\n'+quote})
            assert note['content']['chapter']=='第25章 栈'
            edited=adopt('content/note/preview',{'id':'book-note','expectedRevision':1,'chapter':'第25章 栈','title':'电子书阅读验证','text':note['content']['text']+'\n后进先出：最后加入的元素先移除。'})
            assert edited['revision']==2
            q=api('questions/manual',{'id':'book-q','expectedRevision':0,'operationId':'manual-book-q','selection':selection,'question':{'type':'single','prompt':'Which item does a stack remove first?','options':['The item added last','The item added first'],'answer':0,'sourceId':source['id'],'evidenceQuote':quote,'explanation':'The cited original describes LIFO.','conceptIds':[],'difficulty':'easy'}})
            q=api('questions/review',{'id':'book-q','expectedRevision':q['revision'],'expectedVersion':q['content']['version'],'operationId':'review-book-q','selection':selection,'approved':True,'reason':'Isolated test; verified against the quoted original.'})
            quiz=adopt('quiz/preview',{'id':'book-quiz','expectedRevision':0,'questionIds':['book-q'],'count':1,'selection':selection})
            public=api('quiz/book-quiz');assert 'answer' not in public['questions'][0]
            attempt=api('attempts',{'id':'test-attempt','quizId':'book-quiz','quizRevision':quiz['revision'],'responses':[{'questionId':'book-q','answer':0}]})
            assert attempt['content']['events'][0]['grade']['score']>0
            card=adopt('card/preview',{'id':'book-card','prompt':'What does LIFO mean?','answer':'Last in, first out.','evidence':[{'sourceId':source['id'],'quote':quote}],'expectedRevision':0,'selection':selection})
            queue=api('reviews/queue',{'cardIds':['book-card']});assert queue['cards']
            rated=api('reviews/rate',{'id':'book-card','rating':3,'expectedRevision':card['revision'],'operationId':'rate-book-card'})
            assert rated['content']['reviewEvents']
            graph={'courseId':'course-default','concepts':[{'id':'book-stack','courseId':'course-default','name':'Stack','status':'confirmed','aliases':[],'evidence':[{'sourceId':source['id'],'version':str(source['documentRevision']),'quote':quote}]}],'edges':[]}
            adopt('graph/preview',{'graph':graph,'expectedRevision':0,'selection':selection})
            assert api('graph/path',{'selection':selection})['entries']
            plan=adopt('plan/preview',{'id':'book-plan','expectedRevision':0,'examDate':str(date.today()+timedelta(days=14)),'minutes':20,'selection':selection})
            assert plan['content']['days']
            assert not app.state.platform.db.all('SELECT * FROM invocations')
            report={'status':'passed','pages':421,'sources':len(doc.get('chunks',[])),'readPage':source['page'],'needsOcrPages':sum(bool(p.get('needsOcr')) for p in read['artifact']['pages']),'checks':['full-pdf-upload-parse','actual-page-reading','lexical-retrieval','chapter-note-save-edit','manual-question-review','quiz-submit-real-grading','fsrs-rate','evidence-graph-path','review-plan'],'paidApiCalls':0,'studentData':'temporary-only; no real user grades changed','sha256':hashlib.sha256(book.read_bytes()).hexdigest()}
            (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
