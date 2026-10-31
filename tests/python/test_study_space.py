"""Tests for AI Learning Space Domain Services (Plan, Framework, Quiz, Today)."""
import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from backend.xueya.config import Config
from backend.xueya.app import create_app
from backend.xueya.rag_http import install_rag


@pytest.fixture
def client(tmp_path, http_root):
    class Model:
        async def generate(self, messages, **kwargs):
            task = messages[0]['content']
            if '拆解可执行任务' in task:
                result={'explanation':'按基础知识顺序复习。','tasks':[{'title':'复习进程调度','subject':'操作系统','minutes':30}]}
            elif '生成知识框架' in task:
                result={'title':'进程管理','nodes':[{'id':'node-root','label':'进程管理','parentId':None},{'id':'process','label':'进程状态','parentId':'node-root'}]}
            else:
                result={'prompt':'TCP收到三个重复ACK触发什么？','options':['慢启动','快重传','拥塞避免','超时重传'],'answer':1,'explanation':'触发快重传。'}
            return {'content':json.dumps(result,ensure_ascii=False),'model':'controlled'}
    app = install_rag(create_app(Config(root=http_root, data_dir=tmp_path / "space-data"),provider=Model()))
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        test_client.post("/api/account/register",json={"username":"alice","password":"Fixture123","confirmPassword":"Fixture123"})
        yield test_client


def test_study_plan_lifecycle_and_constraints(client):
    token = client.get("/api/platform/bootstrap").json()["token"]
    headers = {"X-Xueya-Token": token, "X-Xueya-Account": "alice"}

    # 1. Create a draft plan
    draft_res = client.post("/api/learning/space/plan/draft", headers=headers, json={
        "title": "408 核心两周突击",
        "goal": "完成数据结构与计组基础复习",
        "dailyMinutes": 60,
        "daysCount": 14,
        "restDays": [7],
        "subjects": ["数据结构", "计算机组成原理"]
    })
    assert draft_res.status_code == 200
    plan = draft_res.json()["plan"]
    assert plan["status"] == "draft"
    assert len(plan["days"]) == 14
    plan_id = plan["id"]

    # 2. Check active plan before adoption -> should be None
    act_before = client.get("/api/learning/space/plan/active", headers=headers).json()["plan"]
    assert act_before is None

    # 3. Adopt the plan
    adopt_res = client.post("/api/learning/space/plan/adopt", headers=headers, json={
        "planId": plan_id,
        "expectedRevision": 1,
        "confirmed": True
    })
    assert adopt_res.status_code == 200
    adopted = adopt_res.json()["plan"]
    assert adopted["status"] == "active"

    # 4. Active plan should now be this plan
    act_after = client.get("/api/learning/space/plan/active", headers=headers).json()["plan"]
    assert act_after is not None
    assert act_after["id"] == plan_id

    # 5. Toggle a task completion
    first_task = adopted["days"][0]["tasks"][0]
    toggle_res = client.post("/api/learning/space/plan/task/toggle", headers=headers, json={
        "planId": plan_id,
        "taskId": first_task["id"],
        "completed": True
    })
    assert toggle_res.status_code == 200
    assert toggle_res.json()["completed"] is True

    # 6. Sync course completion
    sync_res = client.post("/api/learning/space/plan/sync-course", headers=headers, json={
        "courseId": "cs-数据结构",
        "episodeId": "ep-1",
        "completed": True
    })
    assert sync_res.status_code == 200


def test_knowledge_framework_crud_and_patch(client):
    token = client.get("/api/platform/bootstrap").json()["token"]
    headers = {"X-Xueya-Token": token, "X-Xueya-Account": "bob"}

    # 1. Generate framework
    gen_res = client.post("/api/learning/space/framework/generate", headers=headers, json={
        "subject": "操作系统",
        "topic": "进程管理"
    })
    assert gen_res.status_code == 200
    fw = gen_res.json()["framework"]
    fw_id = fw["id"]
    assert len(fw["nodes"]) > 0
    assert len(fw["edges"]) > 0

    # 2. Patch framework: Add custom node
    patch_res = client.post(f"/api/learning/space/framework/{fw_id}/patch", headers=headers, json={
        "addNode": {
            "id": "node-custom-1",
            "label": "用户自定义注解：死锁检测",
            "parentId": "node-root"
        }
    })
    assert patch_res.status_code == 200
    patched_fw = patch_res.json()["framework"]
    assert any(n["id"] == "node-custom-1" for n in patched_fw["nodes"])

    # 3. List frameworks for Bob
    list_res = client.get("/api/learning/space/framework/list", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()["frameworks"]) >= 1

    # 4. Cross-account isolation: Charlie should have empty list
    client.post("/api/account/register",json={"username":"charlie","password":"Fixture123","confirmPassword":"Fixture123"})
    charlie_headers = {"X-Xueya-Token": token, "X-Xueya-Account": "charlie"}
    charlie_list = client.get("/api/learning/space/framework/list", headers=charlie_headers)
    assert charlie_list.json()["frameworks"] == []


def test_interactive_chat_quiz_and_grading(client):
    token = client.get("/api/platform/bootstrap").json()["token"]
    headers = {"X-Xueya-Token": token, "X-Xueya-Account": "alice"}

    # 1. Generate quiz question (Public view must not leak answer)
    quiz_res = client.post("/api/learning/space/quiz/generate", headers=headers, json={
        "subject": "计算机网络",
        "type": "single"
    })
    assert quiz_res.status_code == 200
    q = quiz_res.json()["question"]
    assert "id" in q
    assert "prompt" in q
    assert "options" in q
    assert "answer" not in q # MUST NOT leak answer in public DTO!
    assert "explanation" not in q # MUST NOT leak explanation before submission!

    # 2. Submit wrong answer
    wrong_sub = client.post("/api/learning/space/quiz/grade", headers=headers, json={
        "questionId": q["id"],
        "answer": 0
    })
    assert wrong_sub.status_code == 200
    w_res = wrong_sub.json()["result"]
    assert w_res["correct"] is False
    assert w_res["score"] == 0

    # 3. Submit correct answer
    correct_sub = client.post("/api/learning/space/quiz/grade", headers=headers, json={
        "questionId": q["id"],
        "answer": 1 # B: 快重传
    })
    assert correct_sub.status_code == 200
    c_res = correct_sub.json()["result"]
    assert c_res["correct"] is True
    assert c_res["score"] == 1
    assert "快重传" in c_res["explanation"]


def test_homepage_today_summary(client):
    token = client.get("/api/platform/bootstrap").json()["token"]
    headers = {"X-Xueya-Token": token, "X-Xueya-Account": "david"}

    res = client.get("/api/learning/space/today", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "date" in data
    assert "continueLearning" in data


def test_framework_rejects_cycles_and_deletes_descendants(client):
    token = client.get('/api/platform/bootstrap').json()['token']
    headers = {'X-Xueya-Token': token}
    fw = client.post('/api/learning/space/framework/generate',headers=headers,json={'subject':'操作系统'}).json()['framework']
    path = f"/api/learning/space/framework/{fw['id']}/patch"
    assert client.post(path,headers=headers,json={'addNode':{'id':'leaf','parentId':'process','label':'阻塞态'}}).status_code == 200
    bad = client.post(path,headers=headers,json={'updateNode':{'id':'process','parentId':'leaf'}})
    assert not bad.json()['ok']
    saved = client.get(f"/api/learning/space/framework/{fw['id']}",headers=headers).json()['framework']
    assert next(n for n in saved['nodes'] if n['id']=='process')['parentId'] == 'node-root'
    removed = client.post(path,headers=headers,json={'removeNodeId':'process'}).json()['framework']
    assert [n['id'] for n in removed['nodes']] == ['node-root']
    assert removed['edges'] == []


def test_plan_budget_confirmation_and_archived_history(client):
    from backend.xueya.study_space_service import StudySpaceService
    service = StudySpaceService(client.app.state.platform)
    data = {'goal':'进程管理','startDate':'2026-11-02','daysCount':3,'dailyMinutes':30,'restDays':[],
            'tasks':[{'title':'理解进程状态','minutes':30},{'title':'理解进程切换','minutes':30}]}
    a = service.create_plan_draft('alice',data)
    assert a['daysCount']==3 and not any(d['isRestDay'] for d in a['days'])
    from backend.xueya.common import AppError
    with pytest.raises(AppError): service.adopt_plan('alice',a['id'],1,'false')
    service.adopt_plan('alice',a['id'],1,True)
    task=a['days'][0]['tasks'][0]
    with pytest.raises(AppError): service.delay_task('alice',a['id'],task['id'],'2026-11-03')
    assert len(service.get_active_plan('alice')['days'][0]['tasks'])==1
    service.toggle_task('alice',a['id'],task['id'],True)
    b=service.create_plan_draft('alice',data)
    service.adopt_plan('alice',b['id'],1,True)
    previous=service.get_plan('alice',a['id'])
    assert previous['status']=='archived' and previous['days'][0]['tasks'][0]['completed']
    with pytest.raises(AppError): service.adopt_plan('alice',a['id'],previous['revision'],True)


def test_subjective_evaluation_uses_model_and_requires_rubric_for_scores(client):
    import asyncio
    from backend.xueya.study_space_service import StudySpaceService
    service=StudySpaceService(client.app.state.platform)
    class Reviewer:
        calls=0
        async def generate(self,messages,**kwargs):
            self.calls+=1
            return {'content':json.dumps({'feedback':'遗漏了阻塞态的唤醒条件。','rubricPoints':[{'id':'states','earned':2}]})}
    provider=Reviewer()
    q={'id':'q','type':'short','prompt':'解释进程状态转换','rubric':[{'id':'states','description':'状态转换正确','points':4}]}
    scored=asyncio.run(service.evaluate_model_answer('alice',provider,q,'等待IO时阻塞。'))
    assert scored['score']==2 and scored['maxScore']==4 and scored['method']=='llm-review'
    q['rubric']=[]
    analysis=asyncio.run(service.evaluate_model_answer('alice',provider,q,'很长的答案'*100))
    assert 'score' not in analysis and 'maxScore' not in analysis and provider.calls==2
    with pytest.raises(Exception): service.grade_submission(q,'答案')


def test_course_sync_requires_exact_episode_and_boolean(client):
    from backend.xueya.study_space_service import StudySpaceService
    service=StudySpaceService(client.app.state.platform)
    p=service.create_plan_draft('alice',{'daysCount':2,'restDays':[],'tasks':[{'title':'进程','minutes':30},{'title':'调度','minutes':30}]})
    scope=service._scope('alice');row=service.repo.read(scope,'plan',p['id'])
    for task,episode in zip(p['days'][0]['tasks'],['ep1','ep2']):
        task.update(kind='course',resource={'courseId':'os','episodeId':episode})
    service.repo.put(scope,'plan',p['id'],p,expected_version=row['version'])
    service.adopt_plan('alice',p['id'],1,True)
    assert service.sync_course_completion('alice','os','ep1',True)==1
    assert [t['completed'] for t in service.get_active_plan('alice')['days'][0]['tasks']]==[True,False]
    token=client.get('/api/platform/bootstrap').json()['token']
    reply=client.post('/api/learning/space/plan/sync-course',headers={'X-Xueya-Token':token},json={'courseId':'os','episodeId':'ep1','completed':'false'})
    assert not reply.json()['ok']
