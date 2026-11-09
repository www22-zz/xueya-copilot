from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config
import pytest
from backend.xueya.common import AppError
from backend.xueya.exam_sessions import ExamSessions
from backend.xueya.practice_catalog import exam_bank


def test_extra_ai_recommendations_are_explicitly_selected_to_exact_quota():
    pool=exam_bank()['questions']
    ids=[q['id'] for q in pool[:20]]
    selected=ExamSessions.select_recommendations(pool,ids,3)
    assert len(selected)==3 and len({q['id'] for q in selected})==3
    assert all(q['id'] in ids for q in selected)
    for invalid in (ids[:2],ids+['invented-id'],[ids[0]]*3):
        with pytest.raises(AppError):ExamSessions.select_recommendations(pool,invalid,3)


def test_exam_snapshot_timer_grading_and_account_isolation(tmp_path,http_root):
    app=create_app(Config(root=http_root,data_dir=tmp_path/'data',preserve_legacy_data=True,auto_import_demo=False),start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'alice','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        request={'count':3,'minutes':1,'mode':'fixed','operationId':'exam-first'}
        response=client.post('/api/learning/space/exams',json=request)
        assert response.status_code==200,response.text
        paper=response.json()['session'];key=paper['id']
        assert all('answer' not in q and 'explanation' not in q for q in paper['questions'])
        assert client.post('/api/learning/space/exams',json=request).json()['session']['id']==key
        clock=[1000];app.state.exam_sessions.now=lambda:clock[0]
        base='/api/learning/space/exams/'+key
        paper=client.post(base+'/start',json={'expectedRevision':paper['revision']}).json()['session']
        assert paper['deadline']==1060
        scope,row=app.state.exam_sessions.load('alice',key)
        q=row['value']['questions'][0]
        paper=client.post(base+'/answers',json={'expectedRevision':paper['revision'],'answers':{q['id']:q['answer']}}).json()['session']
        assert client.get(base).json()['session']['answers'][q['id']]==q['answer']
        clock[0]=1061
        paper=client.get(base).json()['session']
        assert paper['status']=='submitted' and paper['result']['score']==1 and paper['result']['unanswered']==2
        assert len(client.get('/api/learning/space/quiz/list').json()['attempts'])==1
        assert all('answer' in q and 'explanation' in q for q in paper['questions'])
        repeat=client.post(base+'/submit',json={'expectedRevision':1}).json()['session']
        assert repeat['revision']==paper['revision'] and repeat['result']==paper['result']
        assert len(client.get('/api/learning/space/quiz/list').json()['attempts'])==1
        client.post('/api/account/register',json={'username':'bob','password':'Fixture123','confirmPassword':'Fixture123'})
        assert client.get(base).status_code!=200
        assert client.get('/api/learning/space/exams').json()['sessions']==[]


def test_attendance_is_independent_and_idempotent(tmp_path,http_root):
    app=create_app(Config(root=http_root,data_dir=tmp_path/'data',preserve_legacy_data=True,auto_import_demo=False),start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'alice','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        for _ in range(2):
            value=client.post('/api/learning/space/attendance',json={}).json()
            assert value['signed'] and len(value['history'])==1
        assert not app.state.platform.repo.all(app.state.material_learning.service._scope('alice'),'plan')
