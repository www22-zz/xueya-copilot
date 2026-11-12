"""Existing-bank exercises must be scoped, stable, and usable without materials or AI."""
import copy
import pytest
from backend.xueya.common import AppError
from backend.xueya.study_space_service import StudySpaceService
from backend.xueya.plan_practice import prepare,fixed_candidates,task_brief
from backend.xueya.learning_route import nodes,validate_attempt,view


def old_plan(service,account='alice',title='学习数据结构概念、逻辑结构与存储结构'):
    plan=service.create_plan_draft(account,dict(startDate='2026-11-12',daysCount=2,dailyMinutes=60,restDays=[],subjects=['数据结构'],
        tasks=[dict(title=title,subject='数据结构',minutes=60),dict(title='练习二维数组行优先地址计算',subject='数据结构',minutes=60)]))
    return plan


def test_empty_old_nodes_get_real_fixed_questions_once(platform):
    service=StudySpaceService(platform);plan=old_plan(service);ids=[n['id'] for n in nodes(plan['learningRoute'])]
    original=copy.deepcopy(plan)
    result=prepare(service,'alice',plan['id'],[ids[0]])
    first,second=nodes(result['learningRoute'])
    assert 2<=len(first['questions'])<=6 and not second['questions']
    assert first['fixedPracticePrepared'] and first['requiredCount']==len(first['questions']) and first['readiness']=='ready'
    assert first['taskSummary'] and len(first['knowledgePoints'])==3
    question_rows=service.repo.all(service._scope('alice'),'question')
    assert len(question_rows)==len(first['questions'])
    assert all(q['sourceType']=='fixed' and q['originalQuestionId'] and q['options'] and isinstance(q['answer'],int) for q in question_rows)
    assert any(q['difficulty']=='中等' for q in question_rows)  # Preserve bank labels; do not relabel as simple.
    assert all('answer' not in service.public_question(q) for q in question_rows)
    again=prepare(service,'alice',plan['id'],[ids[0]])
    assert again==result and len(service.repo.all(service._scope('alice'),'question'))==len(question_rows)
    assert result['days']==original['days'] and result['learningRoute']['phases'][0]['stages'][0]['nodes'][0]['id']==ids[0]
    assert not platform.db.all('SELECT id FROM jobs') and not platform.db.all('SELECT id FROM invocations')


def test_cross_account_archived_and_invalid_node_requests_are_rejected(platform):
    service=StudySpaceService(platform);plan=old_plan(service);node=nodes(plan['learningRoute'])[0]
    with pytest.raises(AppError,match='PLAN_NOT_FOUND'):prepare(service,'bob',plan['id'],[node['id']])
    with pytest.raises(AppError,match='PLAN_NODE_NOT_FOUND'):prepare(service,'alice',plan['id'],[node['id'],'unknown'])
    assert not service.repo.all(service._scope('alice'),'question')
    for invalid in [None,[],['x']*21,[1]]:
        with pytest.raises(AppError,match='INVALID_PLAN_NODES'):prepare(service,'alice',plan['id'],invalid)
    row=service.repo.read(service._scope('alice'),'plan',plan['id']);plan['status']='archived'
    service.repo.put(service._scope('alice'),'plan',plan['id'],plan,row['version'])
    with pytest.raises(AppError,match='PLAN_NOT_ACTIVE'):prepare(service,'alice',plan['id'],[node['id']])


def test_fixed_attempt_bypasses_material_dependency_but_keeps_binding(platform):
    service=StudySpaceService(platform);plan=old_plan(service);ids=[n['id'] for n in nodes(plan['learningRoute'])]
    result=prepare(service,'alice',plan['id'],ids);scope=service._scope('alice')
    row=service.repo.read(scope,'plan',plan['id']);saved=row['value'];saved['status']='active';service.repo.put(scope,'plan',plan['id'],saved,row['version'])
    # This material gate denies every concept: fixed bank refs still work.
    class Materials:
        def accessible_concepts(self,*args):return set()
        def account_owner_for(self,*args):return None
    platform.material_learning=Materials()
    refs=nodes(result['learningRoute'])[0]['questions']
    for ref in refs:
        qrow=service.repo.read(scope,'question',ref['id']);q={**qrow['value'],'revision':qrow['version']}
        assert validate_attempt(service,'alice',dict(planId=plan['id'],nodeId=ids[0]),q)['nodeId']==ids[0]
        with pytest.raises(AppError,match='PLAN_QUESTION_MISMATCH'):validate_attempt(service,'alice',dict(planId=plan['id'],nodeId='unknown'),q)
        broken={**q,'originalQuestionId':'invented'}
        with pytest.raises(AppError,match='PLAN_QUESTION_MISMATCH'):validate_attempt(service,'alice',dict(planId=plan['id'],nodeId=ids[0]),broken)
        attempt=dict(id='a-'+ref['id'],questionId=ref['id'],questionRevision=ref['revision'],planId=plan['id'],nodeId=ids[0],createdAt='2026-11-12T10:00:00Z',evaluations=[dict(status='graded',result=dict(correct=True))])
        service.repo.put(scope,'attempt',attempt['id'],attempt,0)
    assert view(service,'alice',saved)['days'][0]['completed'] is True
    assert view(service,'alice',saved)['days'][1]['completed'] is False
    repeated=prepare(service,'alice',plan['id'],[ids[0]])
    assert nodes(repeated['learningRoute'])[0]['questions']==refs


def test_existing_material_group_is_never_replaced(platform):
    service=StudySpaceService(platform);plan=old_plan(service);node=nodes(plan['learningRoute'])[0]
    node['questions']=[dict(id='kept-question',revision=3)];node['readiness']='ready'
    row=service.repo.read(service._scope('alice'),'plan',plan['id']);service.repo.put(service._scope('alice'),'plan',plan['id'],plan,row['version'])
    result=prepare(service,'alice',plan['id'],[node['id']])
    assert nodes(result['learningRoute'])[0]['questions']==[dict(id='kept-question',revision=3)]
    assert not service.repo.all(service._scope('alice'),'question')


@pytest.mark.parametrize('title',[
    '学习数据结构概念、逻辑结构与存储结构','练习逻辑结构、存储结构与链式存储代表题',
    '学习算法时间复杂度与频度分析','练习时间复杂度与二分查找效率题',
    '学习数组维度、索引范围与顺序存储','练习二维数组行优先地址计算',
    '学习对称与三角矩阵压缩存储映射','练习特殊矩阵压缩存储下标题',
    '观看MOOC第01讲：算法复杂度与渐进表示','练习顺序表随机访问与线性表考点题',
    '练习栈与队列：中缀转后缀考点改编题','观看MOOC第02讲并练习完全二叉树考点题',
    '观看MOOC第03讲并练习图的概念考点题'])
def test_all_current_plan_topics_have_existing_objective_exercises(title):
    candidates=fixed_candidates(dict(title=title,subject='数据结构'))
    assert len(candidates)>=2,title
    assert all(q['type']=='single' and q.get('subject') in ('数据结构','数据结构与算法') for _,_,q,_ in candidates)
    assert len(task_brief(dict(title=title,subject='数据结构'))['knowledgePoints'])==3


def test_prepare_http_and_submit_objective_answer_without_model(client):
    service=StudySpaceService(client.platform);plan=old_plan(service,'local');node=nodes(plan['learningRoute'])[0]
    token=client.get('/api/platform/bootstrap').json()['token'];headers={'X-Xueya-Token':token}
    url=f"/api/learning/space/plan/{plan['id']}/practice"
    response=client.post(url,headers=headers,json={'nodeIds':[node['id']]})
    assert response.json()['ok'],response.text
    prepared=response.json()['plan'];ref=nodes(prepared['learningRoute'])[0]['questions'][0]
    scope=service._scope('local');row=service.repo.read(scope,'plan',plan['id']);active=row['value'];active['status']='active';service.repo.put(scope,'plan',plan['id'],active,row['version'])
    public=client.get('/api/learning/space/quiz/question/'+ref['id'],headers=headers).json()['question']
    assert public['sourceType']=='fixed' and 'answer' not in public and public['revision']==ref['revision']
    saved=service.repo.read(scope,'question',ref['id'])['value']
    response=client.post('/api/learning/space/quiz/attempts',headers=headers,json=dict(questionId=ref['id'],questionRevision=ref['revision'],planId=plan['id'],nodeId=node['id'],answer=saved['answer'],operationId='fixed-plan-attempt'))
    assert response.json()['ok'],response.text
    attempt=response.json()['attempt'];assert attempt['planId']==plan['id'] and attempt['evaluations'][0]['source']=='objective'
    assert not client.platform.db.all('SELECT id FROM jobs') and not client.platform.db.all('SELECT id FROM invocations')
