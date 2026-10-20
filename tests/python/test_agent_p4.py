from test_agent_p1 import host, SOURCE
from test_agent_p2 import create, step
from test_agent_p3 import bank, prepared, act


def graph(client, p):
    content = {'courseId': 'course-default', 'concepts': [
        {'id': key, 'name': name, 'courseId': 'course-default', 'status': 'confirmed',
         'evidence': [{'sourceId': SOURCE['id'], 'version': '1', 'quote': SOURCE['quote']}]}
        for key, name in [('basics', '第一章：队列定义'), ('applications', '第二章：队列应用')]],
        'edges': [{'from': 'basics', 'to': 'applications', 'type': 'prerequisite', 'status': 'confirmed',
            'evidence': [{'sourceId': SOURCE['id'], 'version': '1', 'quote': SOURCE['quote']}]}]}
    repo = client.app.state.learning.repo
    p.repo.put(p.scope(), 'artifact', repo.key('course-graph'), {'id': 'course-graph', 'kind': 'concept-graph',
        'courseId': 'course-default', 'revision': 1, 'content': content}, 0)


def test_wrong_cause_requires_human_confirmation_and_changes_followup(host):
    with host() as (client, _, p):
        q = bank(p)
        run = prepared(client, p)
        run = act(client, run, 'confirm', confirmed=True, digest=run['interaction']['digest'])
        act(client, run, 'answer', responses=[{'questionId': q['id'], 'answer': 1}])
        create(client, id='wrong-run', scenario='wrong', question='分析队列错题并准备巩固资料')
        for _ in range(8):
            run = step(client, p, 'wrong-run')
            if run['status'] != 'queued':
                break
        assert run['interaction']['kind'] == 'diagnosis', run
        # An unseen, approved alternative is required for another practice round.
        p.repo.put(p.scope(), 'question', 'alternative', {**q, 'id': 'alternative', 'prompt': '先入队的元素何时出队？'}, 0)
        run = act(client, run, 'diagnose', confirmed=True, cause='input-error', reason='我点错了选项')
        assert run['status'] == 'awaiting_confirmation'
        assert run['interaction']['diagnosticActions'][0]['action'] == 'optional-retry'
        assert run['interaction']['preview']['questions'][0]['id'] == 'alternative'


def test_exam_replans_real_changes_and_preserves_confirmation(host):
    with host() as (client, calls, p):
        graph(client, p)
        run = prepared(client, p, 'exam')
        assert run['status'] == 'awaiting_confirmation', run
        content = run['interaction']['preview']
        assert {t['conceptId'] for d in content['days'] for t in d['tasks']} == {'basics', 'applications'}
        run = act(client, run, 'confirm', confirmed=True, digest=run['interaction']['digest'])
        count = len(calls)
        run = act(client, run, 'replan', settings={'minutes': 10})
        assert run['interaction']['preview']['minutes'] == 10
        assert all(sum(t['minutes'] for t in d['tasks']) <= 10 for d in run['interaction']['preview']['days'])
        assert run['interaction']['changes']['previous']['minutes'] == 30
        assert len(calls) == count
        old = client.app.state.learning.dynamic.get('course-default', run['id'])
        assert old['pendingDraft']['expectedRevision'] == 1
        run = act(client, run, 'confirm', confirmed=True, digest=run['interaction']['digest'])
        assert run['status'] == 'completed'


def test_exam_without_graph_waits_instead_of_empty_plan(host):
    with host() as (client, _, p):
        run = prepared(client, p, 'exam')
        assert run['interaction']['kind'] == 'missing_graph'
