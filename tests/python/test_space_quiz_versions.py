"""Private quiz/attempt identities and append-only effective assessment chains."""
import asyncio
import copy
import json
import pytest
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.common import AppError


class Model:
    def __init__(self):self.calls=[];self.fail=False
    async def generate(self,messages,**kwargs):
        self.calls.append(messages)
        if self.fail:raise AppError('AI_TIMEOUT')
        payload=json.loads(messages[1]['content'])
        if 'rubric' in payload:
            value={'feedback':'正确说明了互斥限制，还需要补充适用条件。','rubricPoints':[{'id':point['id'],'earned':point['points']/2} for point in payload['rubric']]}
        else:
            value={'prompt':'解释临界区互斥的含义。','rubric':[{'id':'one','description':'互斥约束与条件','points':4}],'explanation':'结合临界资源的同时访问说明。'}
        return {'content':json.dumps(value,ensure_ascii=False),'model':'controlled-review'}


@pytest.fixture
def setup(tmp_path,http_root):
    model=Model();config=Config(root=http_root,data_dir=tmp_path/'quiz',preserve_legacy_data=True)
    app=create_app(config,provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'alice','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        yield app,client,model,config


async def finish(app,job_id):
    p=app.state.platform;p.jobs.stopped=False
    for _ in range(300):
        await p.jobs.tick();job=p.jobs.get(job_id,'space:alice')
        if job['status'] in ('succeeded','failed','cancelled','unknown'):return job
        await asyncio.sleep(.01)
    pytest.fail('quiz job did not finish')


def seed(app,kind='short',rubric=True):
    service=app.state.space_quiz
    question={'id':'private-question','type':kind,'subject':'操作系统','prompt':'说明互斥限制','sourceType':'ai-generated','explanation':'互斥限制'}
    if kind=='single':question.update(options=['同时访问','互斥访问'],answer=1)
    else:question['rubric']=[{'id':'one','description':'解释互斥与适用条件','points':4}] if rubric else []
    app.state.platform.repo.put(service.scope('alice'),'question',question['id'],question,0)
    return question


def test_unanswered_question_hides_answer_and_grade_ignores_client_score(setup):
    app,client,model,_=setup;q=seed(app,'single')
    public=client.get('/api/learning/space/quiz/question/'+q['id']).json()['question']
    assert not {'answer','rubric','explanation'} & set(public)
    body={'questionId':q['id'],'questionRevision':1,'answer':0,'score':100,'correct':True,'operationId':'first-answer'}
    reply=client.post('/api/learning/space/quiz/attempts',json=body).json()['attempt']
    assert not {'answer','rubric','explanation'} & set(reply['questionSnapshotView'])
    assert reply['effectiveEvaluation']['result']['correct'] is False
    assert client.post('/api/learning/space/quiz/attempts',json=body).json()['attempt']==reply
    scope=app.state.space_quiz.scope('alice')
    assert len(app.state.platform.repo.all(scope,'attempt'))==1 and not model.calls
    before=copy.deepcopy(reply['evaluations'][0])
    reviewed=client.post('/api/learning/space/quiz/attempts/'+reply['id']+'/review',json={
        'expectedRevision':reply['revision'],'reason':'重新按标准答案核对','operationId':'recheck'}).json()['attempt']
    assert reviewed['evaluations'][0]==before and reviewed['effectiveEvaluation']['source']=='objective-recheck'
    assert len(app.state.platform.repo.all(scope,'attempt'))==1 and not model.calls


def test_subjective_answer_survives_failure_without_zero_and_unknown_not_replayed(setup):
    app,client,model,_=setup;q=seed(app);model.fail=True
    submitted=client.post('/api/learning/space/quiz/attempts',json={'questionId':q['id'],'questionRevision':1,
        'answer':'同一时刻最多一个进程进入相关临界区。','operationId':'short-answer'}).json()['attempt']
    assert submitted['answer'] and 'effectiveEvaluation' not in submitted
    job=asyncio.run(finish(app,submitted['evaluations'][0]['jobId']));assert job['status']=='unknown'
    stored=client.get('/api/learning/space/quiz/attempts/'+submitted['id']).json()['attempt']
    assert stored['answer']==submitted['answer'] and stored['evaluations'][0]['status']=='unknown'
    assert 'effectiveEvaluation' not in stored and 'result' not in stored['evaluations'][0]
    asyncio.run(app.state.platform.jobs.tick());assert len(model.calls)==1


def test_ai_review_and_human_correction_keep_versions_and_one_attempt(setup):
    app,client,model,_=setup;q=seed(app)
    attempt=app.state.space_quiz.submit_attempt('alice',{'questionId':q['id'],'questionRevision':1,'answer':'互斥访问','operationId':'one'})
    asyncio.run(finish(app,attempt['evaluations'][0]['jobId']))
    first=app.state.space_quiz.attempt('alice',attempt['id']);initial=copy.deepcopy(first['evaluations'][0])
    assert initial['result']['score']==2 and initial['result']['model']=='controlled-review'
    review=app.state.space_quiz.review('alice',attempt['id'],{'expectedRevision':first['revision'],'reason':'我已说明适用条件','operationId':'review-one'})
    asyncio.run(finish(app,review['evaluations'][-1]['jobId']))
    reviewed=app.state.space_quiz.attempt('alice',attempt['id'])
    corrected=app.state.space_quiz.review('alice',attempt['id'],{'expectedRevision':reviewed['revision'],'reason':'教师核对后修正','score':3,'operationId':'manual'},manual=True)
    assert corrected['evaluations'][0]==initial and len(corrected['evaluations'])==3
    assert corrected['effectiveEvaluation']['source']=='human' and corrected['effectiveEvaluation']['result']['score']==3
    assert len(app.state.platform.repo.all(app.state.space_quiz.scope('alice'),'attempt'))==1
    assert len(model.calls)==2
    assert json.loads(model.calls[1][1]['content'])['reviewReason']=='我已说明适用条件'


def test_no_rubric_gives_feedback_only_and_manual_cannot_invent_score(setup):
    app,_,_,_=setup;q=seed(app,rubric=False);service=app.state.space_quiz
    attempt=service.submit_attempt('alice',{'questionId':q['id'],'questionRevision':1,'answer':'解释互斥','operationId':'one'})
    asyncio.run(finish(app,attempt['evaluations'][0]['jobId']))
    current=service.attempt('alice',attempt['id'])
    assert 'score' not in current['effectiveEvaluation']['result']
    with pytest.raises(AppError,match='RUBRIC_REQUIRED'):
        service.review('alice',attempt['id'],{'expectedRevision':current['revision'],'reason':'不能凭空评分','score':100,'operationId':'invalid'},manual=True)
    disputed=service.review('alice',attempt['id'],{'expectedRevision':current['revision'],'reason':'结论待核对','disputed':True,'operationId':'dispute'},manual=True)
    assert disputed['effectiveEvaluation']['status']=='disputed'


def test_generation_and_practice_listing_share_question_and_account_permissions(setup):
    app,client,model,_=setup
    queued=client.post('/api/learning/space/chat/quiz',json={'question':'请生成一道操作系统主观题','sessionId':'source-session','operationId':'generate'}).json()
    job=asyncio.run(finish(app,queued['jobId']));assert job['status']=='succeeded'
    question_id=job['result']['questionIds'][0]
    directory=client.get('/api/learning/space/quiz/list').json()
    assert directory['questions'][0]['id']==question_id and 'rubric' not in directory['questions'][0]
    assert app.state.space_quiz.question('alice',question_id)['sessionId']=='source-session'
    assert len(model.calls)==1
    client.post('/api/account/register',json={'username':'bobby','password':'Fixture123','confirmPassword':'Fixture123'})
    assert client.get('/api/learning/space/quiz/question/'+question_id).status_code==404
    assert not client.get('/api/learning/space/quiz/list').json()['questions']
    assert client.get('/api/learning/space/jobs/'+job['id']).status_code==404


def test_cancel_before_evaluation_does_not_leave_a_permanent_queued_grade(setup):
    app,_,model,_=setup;q=seed(app);service=app.state.space_quiz
    attempt=service.submit_attempt('alice',{'questionId':q['id'],'questionRevision':1,'answer':'保存答案','operationId':'one'})
    app.state.platform.jobs.cancel(attempt['evaluations'][0]['jobId'],service.scope('alice').user_id)
    current=service.attempt('alice',attempt['id'])
    assert current['evaluations'][0]['status']=='cancelled' and 'effectiveEvaluation' not in current
    assert current['answer']=='保存答案' and not model.calls


def test_late_model_result_preserves_newer_human_correction(setup):
    app,_,_,_=setup;q=seed(app);service=app.state.space_quiz
    attempt=service.submit_attempt('alice',{'questionId':q['id'],'questionRevision':1,'answer':'原始答案','operationId':'one'})
    service.review('alice',attempt['id'],{'expectedRevision':attempt['revision'],'reason':'先由教师核对','score':4,'operationId':'human-first'},manual=True)
    asyncio.run(finish(app,attempt['evaluations'][0]['jobId']))
    stored=service.attempt('alice',attempt['id'])
    assert stored['evaluations'][0]['result']['score']==2
    assert stored['effectiveEvaluation']['source']=='human' and stored['effectiveEvaluation']['result']['score']==4
    assert len(app.state.platform.repo.all(service.scope('alice'),'attempt'))==1


def test_legacy_evaluation_is_readable_without_rewriting_or_inventing_version(setup):
    app,client,model,_=setup;q=seed(app,'single');service=app.state.space_quiz
    old={'id':'legacy-attempt','questionId':q['id'],'questionSnapshot':q,'answer':0,
         'evaluation':{'status':'graded','score':0,'maxScore':1,'correct':False,'method':'old-method'}}
    scope=service.scope('alice');app.state.platform.repo.put(scope,'attempt',old['id'],old,0)
    before=app.state.platform.repo.read(scope,'attempt',old['id'])
    listing=client.get('/api/learning/space/quiz/list').json()
    history=next(a for a in listing['attempts'] if a['id']==old['id'])
    assert history['evaluations'][0]['source']=='legacy-assessment'
    assert history['evaluations'][0]['result']==old['evaluation']
    assert history['questionRevision'] is None
    assert app.state.platform.repo.read(scope,'attempt',old['id'])==before
    assert not model.calls


def test_duplicate_batch_does_not_publish_fake_successful_question_cards(setup):
    app,client,model,_=setup
    response=client.post('/api/learning/space/chat/quiz',json={'question':'请生成两道操作系统主观题','operationId':'batch','sessionId':'session'}).json()
    job=asyncio.run(finish(app,response['jobId']))
    assert job['status']=='unknown' and job['error']=='DUPLICATE_QUIZ_QUESTION'
    assert len(model.calls)==2
    assert json.loads(model.calls[-1][1]['content'])['avoidPrompts']==['解释临界区互斥的含义。']
    assert not client.get('/api/learning/space/quiz/list').json()['questions']


def test_fixed_subjective_bridge_keeps_original_rubric_and_one_attempt(setup):
    from backend.xueya.practice_catalog import exam_bank
    app,client,model,_=setup
    q=next(q for q in exam_bank()['questions'] if q['type']=='short' and q.get('selfScoreMode')!='mastery')
    value={'questionId':q['id'],'answer':'我按小问说明了资源分配、状态变化和必要条件。','operationId':'fixed-one','score':1000,'rubric':[{'id':'fake','points':1000}]}
    first=client.post('/api/learning/space/quiz/fixed-attempt',json=value).json()['attempt']
    assert client.post('/api/learning/space/quiz/fixed-attempt',json=value).json()['attempt']==first
    stored=app.state.space_quiz.attempt('alice',first['id'])
    assert stored['questionSnapshot']['originalQuestionId']==q['id']
    assert [r['points'] for r in stored['questionSnapshot']['rubric']]==[p['points'] for p in q['parts']]
    assert len(client.get('/api/learning/space/quiz/list').json()['attempts'])==1
    job=asyncio.run(finish(app,first['evaluations'][0]['jobId']))
    assert job['status']=='succeeded'
    result=app.state.space_quiz.attempt('alice',first['id'])['effectiveEvaluation']['result']
    assert result['maxScore']==sum(p['points'] for p in q['parts']) and result['score']!=1000


def test_hot100_text_review_does_not_execute_code_or_invent_numeric_rubric(setup):
    from backend.xueya.practice_bank import bank
    app,client,model,_=setup
    q=next(q for q in bank()['questions'] if q['type']=='code')
    value={'questionId':q['id'],'answer':'print("example") # 只作为文本，不执行','operationId':'code-one'}
    submitted=client.post('/api/learning/space/quiz/fixed-attempt',json=value).json()['attempt']
    job=asyncio.run(finish(app,submitted['evaluations'][0]['jobId']))
    assert job['status']=='succeeded'
    attempt=app.state.space_quiz.attempt('alice',submitted['id'])
    assert attempt['questionSnapshot']['rubric']==[]
    assert 'score' not in attempt['effectiveEvaluation']['result']
    assert '不运行代码' in attempt['questionSnapshot']['limitations'][0]


@pytest.mark.parametrize('kind,extra,answer,status', [
    ('multiple',{'options':['a','b','c'],'answer':[0,2]},[2,0],'graded'),
    ('boolean',{'answer':False},False,'graded'),
    ('fill',{'answer':[['FIFO','先进先出']]},['先进先出'],'graded'),
    ('fill',{'answer':[['FIFO']]},['可能等价的描述'],'pending-review'),
])
def test_objective_types_use_same_private_attempt_chain(setup,kind,extra,answer,status):
    app,client,model,_=setup
    q={'id':'typed-question','type':kind,'subject':'数据结构','prompt':'____' if kind=='fill' else '请选择',
       'sourceType':'ai-generated','explanation':'保存的解析',**extra}
    service=app.state.space_quiz
    app.state.platform.repo.put(service.scope('alice'),'question',q['id'],q,0)
    public=client.get('/api/learning/space/quiz/question/'+q['id']).json()['question']
    assert 'answer' not in public and 'explanation' not in public
    body={'questionId':q['id'],'questionRevision':1,'answer':answer,'operationId':'typed-first'}
    response=client.post('/api/learning/space/quiz/attempts',json=body)
    assert response.status_code==200,response.text
    attempt=response.json()['attempt']
    assert attempt['evaluations'][0]['status']==status
    if status=='graded':assert attempt['effectiveEvaluation']['result']['score']==1
    else:
        assert 'effectiveEvaluation' not in attempt
        reviewed=service.review('alice',attempt['id'],{'expectedRevision':1,'reason':'请复核等价形式','operationId':'typed-review'})
        assert reviewed['evaluations'][-1]['status']=='pending-review'
        assert 'effectiveEvaluation' not in reviewed
    assert client.post('/api/learning/space/quiz/attempts',json=body).json()['attempt']['id']==attempt['id']
    assert not model.calls
