"""Practice sources, written self-assessment, retirement and history preservation."""
from collections import Counter
from datetime import datetime, timezone
import json
import time

from fastapi.testclient import TestClient

from backend.agent.practice_analysis import build_snapshot
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.platform import Platform
from backend.xueya.practice_bank import bank
from backend.xueya.practice_catalog import exam_bank
from backend.xueya.practice_state import PracticeState


class NoGeneration:
    def __init__(self):self.calls=0
    async def generate(self,*args,**kwargs):
        self.calls+=1
        raise AssertionError('Retired practice generation must not call provider')


def authorize(client):
    client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']


def test_workspace_sources_preserve_original_algorithm_and_course_independence(tmp_path):
    app=create_app(Config(data_dir=tmp_path),start_jobs=False)
    with TestClient(app,base_url='http://localhost') as client:
        authorize(client)
        value=client.get('/api/practice/bank?source=workspace').json()
        assert value['ok']
        algorithm=[q for q in value['questions'] if q['bankSource']=='algorithm']
        original=[q for q in bank()['questions'] if q['category']=='hot100']
        assert [{k:v for k,v in q.items() if k!='bankSource'} for q in algorithm] == original
        assert len(algorithm)==100
        exams=[q for q in value['questions'] if q['bankSource']=='exam408']
        assert Counter(q['type'] for q in exams)=={'single':240,'short':60}
        assert {q['subject'] for q in exams}=={'数据结构','计算机组成原理','操作系统','计算机网络'}
        assert Counter(q['origin']['kind'] for q in exams)=={'adapted':151,'authored':149}
        assert len({q['id'] for q in value['questions']})==len(value['questions'])
        assert client.get('/api/practice/bank?source=workspace&courseId=not-a-course').json()['version']==value['version']
        assert len(client.get('/api/practice/bank').json()['questions'])==250


def test_written_answers_scores_notes_restart_and_partial_rejection(tmp_path):
    q=next(q for q in exam_bank()['questions'] if q['type']=='short' and not q.get('paper'))
    app=create_app(Config(data_dir=tmp_path),start_jobs=False)
    with TestClient(app,base_url='http://localhost') as client:
        authorize(client)
        payload={'questionType':'short','answers':{'p1':'我的算法与计算过程'},'scores':{'p1':2}}
        ops=[{'opId':'written-one','kind':'written-save','questionId':q['id'],'payload':payload},
             {'opId':'bad-score','kind':'written-save','questionId':q['id'],'payload':{**payload,'scores':{'p1':999}}},
             {'opId':'note-one','kind':'note-save','questionId':q['id'],'payload':{'text':'复习笔记','baseRevision':0}}]
        result=client.post('/api/practice/ops',json={'ops':ops}).json()
        assert result['accepted']==['written-one','note-one']
        assert result['rejected']==[{'opId':'bad-score','error':'INVALID_SELF_SCORE'}]
        row=result['statuses'][q['id']]
        assert row['writtenAnswers']==payload['answers'] and row['selfScores']==payload['scores']
        assert row['correctCount']==0 and row['wrongCount']==0 and row['lastResult'] is None
        assert client.get('/api/practice/notes/'+q['id']).json()['note']['text']=='复习笔记'
        replay=client.post('/api/practice/ops',json={'ops':[ops[0]]}).json()
        assert replay['duplicates']==['written-one']
        alice=PracticeState(app.state.platform)
        assert not alice.state('another-account')['statuses']
    with TestClient(create_app(Config(data_dir=tmp_path),start_jobs=False),base_url='http://localhost') as client:
        authorize(client)
        state=client.get('/api/practice/state').json()
        assert state['statuses'][q['id']]['writtenAnswers']['p1']=='我的算法与计算过程'
        assert state['notes'][q['id']]['text']=='复习笔记'


def test_upload_is_parse_only_and_resume_is_retired(tmp_path):
    model=NoGeneration()
    app=create_app(Config(data_dir=tmp_path,api_key='controlled'),provider=model)
    with TestClient(app,base_url='http://localhost') as client:
        authorize(client)
        upload=client.post('/api/platform/knowledge/upload?courseId=course-default&name=操作系统.md',
            content=('进程与线程、内存管理、同步和调度。\n'*150).encode(),
            headers={'Idempotency-Key':'practice-retirement-upload'})
        assert upload.status_code==200
        assert upload.json()['practiceGeneration']['status']=='deferred'
        time.sleep(.3)
        assert not app.state.platform.db.all("SELECT id FROM jobs WHERE type='practice-generate'")
        assert client.get('/api/platform/knowledge/catalog?courseId=course-default').json()['practiceGenerations']==[]
        response=client.post('/api/practice/generation/old-id/resume',json={}).json()
        assert response['error']=='PRACTICE_GENERATION_RETIRED'
        assert model.calls==0


def test_startup_cancels_queued_old_batches_without_touching_notes(tmp_path):
    host=Platform(tmp_path,recover=False,preserve_legacy_data=True)
    practice=PracticeState(host)
    scope=practice.scope('local')
    host.jobs.register('practice-generate',lambda *args,**kwargs:None)
    job=host.jobs.submit(scope.user_id,{'type':'practice-generate','courseId':scope.course_id,
        'resource':'api','maxAttempts':1,'idempotencyKey':'retire-old-batch','input':{'setId':'legacy-set','batch':1}})
    identifier=bank()['questions'][0]['id']
    practice.accept('local',[{'opId':'existing-real-note','kind':'note-save','questionId':identifier,
                              'payload':{'text':'keep original data','baseRevision':0}}])
    host.db.close()
    model=NoGeneration()
    app=create_app(Config(data_dir=tmp_path,api_key='controlled'),provider=model,start_jobs=False)
    with TestClient(app,base_url='http://localhost'):
        p=app.state.platform
        assert p.jobs.get(job['id'],scope.user_id)['status']=='cancelled'
        assert PracticeState(p).note('local',identifier)['text']=='keep original data'
        assert model.calls==0


def test_self_assessment_is_separate_from_objective_accuracy_and_sources():
    exam=next(q for q in exam_bank()['questions'] if q['type']=='short')
    algorithm=next(q for q in bank()['questions'] if q['category']=='hot100')
    legacy={**algorithm,'id':'g-old','generated':True}
    at='2026-10-29T01:00:00Z'
    now=datetime(2026,10,29,2,tzinfo=timezone.utc)
    rows=[{'id':'draft','questionId':exam['id'],'action':'written-save','at':at,'payload':{'answers':{'p1':'x'},'scores':{}}},
          {'id':'score','questionId':exam['id'],'action':'written-save','at':at,'payload':{'scores':{'p1':1}}},
          {'id':'edit-after-score','questionId':exam['id'],'action':'written-save','at':at,'payload':{'scores':{'p1':1}}}]
    value=build_snapshot([exam,algorithm,legacy],rows,{'statuses':{},'notes':{}},{'days':0,'category':'exam408'},now)
    assert value['stats']['attempts']==0
    assert value['stats']['selfAssessments']==1
    assert sum(q['selfAssessments'] for q in value['questions'])==1
    algorithms=build_snapshot([exam,algorithm,legacy],[],{'statuses':{},'notes':{}},{'days':0,'category':'hot100'},now)
    assert [q['id'] for q in algorithms['questions']]==[algorithm['id']]


def test_authored_arithmetic_and_source_manifest_integrity():
    value=exam_bank()
    assert len({q['prompt'] for q in value['questions']})==300
    assert not any(q.get('paper') for q in value['questions'])
    assert len({q['year'] for q in value['questions'] if q['origin']['kind']=='adapted'})==17
    from scripts.build_exam408_bank import build_bank
    assert build_bank()==value
    from backend.agent.exam408_topics import CHAPTERS, order
    assert value['questions']==sorted(value['questions'],key=order)
    for q in value['questions']:
        assert q['tags'] and q['topic']
        assert q['topic'] in CHAPTERS[q['subject']]
        assert q['subtopic'] in q['tags']
        assert '答案依据公开整理索引' not in q.get('explanation','')
        if q['origin']['kind']=='adapted':
            assert '非原题' in q['origin']['label']
            assert q['year']==q['origin']['year']
            assert q['originalNumber']==q['origin']['number']
            assert all(r['url'].startswith('https://') for r in q['references'])
        if q.get('parts'):
            assert all(part['points']>0 and part['reference'] for part in q['parts'])


def test_reviewed_numeric_answers_against_independent_calculations():
    """Exercise mathematical oracles, not a copy of answer-index constants."""
    import heapq
    import math
    import struct
    questions={q['id']:q for q in exam_bank()['questions']}
    def answer(identifier):
        q=questions[identifier]
        return q['options'][q['answer']]
    checks={
        'e408-2014-15':max(12,11)+8,
        'e408-2015-02':math.comb(6,3)//4,
        'e408-2015-13':min(x-256 if x>=128 else x for x in range(256) if x.bit_count()==2),
        'e408-2016-05':18-11,
        'e408-2016-16':(64-16)*1024//(8*1024*4//8),
        'e408-2017-38':2**(32-16-int(math.log2(64)))-2,
        'e408-2018-08':sum(2**i for i in range(4)),
        'e408-2019-11':(1-20)%(5-1),
        'e408-2019-03':(39+1)//2,
        'e408-2019-35':2**4-10,
        'e408-2023-08':(1000).bit_length(),
        'e408-2024-12':32770-2**16,
    }
    for identifier,expected in checks.items():
        assert int(answer(identifier).replace('−','-'))==expected,identifier
    heap=[2,3,7,9];heapq.heapify(heap);cost=0
    while len(heap)>1:
        combined=heapq.heappop(heap)+heapq.heappop(heap)
        cost+=combined;heapq.heappush(heap,combined)
    assert int(answer('e408-2021-05'))==cost
    assert answer('e408-2022-14')==struct.pack('>f',-.75).hex().upper()
    assert float(answer('e408-2025-35').removesuffix('ms'))==((2**8-1)*512/10**7*1000)


def test_historical_composites_are_self_contained_with_real_scoring_steps():
    variations=[q for q in exam_bank()['questions'] if q['origin']['kind']=='adapted' and q['type']=='short']
    assert len(variations)==14
    assert {q['year'] for q in variations}=={2021,2022}
    assert sum(len(q['parts']) for q in variations)==45
    for q in variations:
        assert not q.get('paper')
        assert len(q['prompt'])>50
        assert all(p['points']>=2 and '分' in p['reference'] and '对照整理解析' not in p['reference'] for p in q['parts'])
        assert '本页为准' in q['explanation']
