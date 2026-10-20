from test_agent_p1 import host, SOURCE
from test_agent_p2 import create, step, BASE


def bank(p):
    q = {'id': 'approved-queue', 'courseId': 'course-default', 'version': '1', 'type': 'single',
        'prompt': '队列的出队顺序是什么？', 'options': ['先进先出', '后进先出'], 'answer': 0,
        'topic': '队列', 'conceptIds': [], 'sourceId': SOURCE['id'], 'sourceVersion': '1',
        'evidenceQuote': SOURCE['quote'], 'status': 'approved'}
    p.repo.put(p.scope(), 'question', q['id'], q, 0)
    return q


def prepared(client, p, scenario='chapter'):
    create(client, scenario=scenario)
    for _ in range(8):
        run = step(client, p)
        if run['status'] != 'queued':
            return run
    raise AssertionError('run did not stop')


def act(client, run, action, **body):
    r = client.post(BASE+'/'+run['id']+'/'+action, json={'revision': run['revision'], **body})
    assert r.status_code == 200, r.text
    return r.json()['result']


def test_chapter_requires_confirmation_and_real_answers(host):
    with host() as (client, calls, p):
        q = bank(p)
        run = prepared(client, p)
        assert run['status'] == 'awaiting_confirmation', run
        assert run['interaction']['preview']['questions'][0]['id'] == q['id']
        assert 'answer' not in run['interaction']['preview']['questions'][0]
        assert not [a for a in client.app.state.learning.repo.all('course-default') if a.get('kind') == 'attempt']
        run = act(client, run, 'confirm', confirmed=True, digest=run['interaction']['digest'])
        assert run['interaction']['kind'] == 'quiz'
        bad = client.post(BASE+'/'+run['id']+'/answer', json={'revision': run['revision'], 'responses': []})
        assert bad.status_code != 200
        run = act(client, run, 'answer', responses=[{'questionId': q['id'], 'answer': 1, 'reasoning': '我以为是栈'}])
        assert run['interaction']['grades'][0]['grade']['score'] == 0
        assert q['id'] not in run['interaction']['nextPracticeIds']
        assert run['status'] == 'awaiting_confirmation'
        count = len(calls)
        run = act(client, run, 'confirm', confirmed=True, digest=run['interaction']['digest'])
        assert run['status'] == 'completed' and len(calls) == count
        artifacts = client.app.state.learning.repo.all('course-default')
        assert any(a.get('kind') == 'plan' for a in artifacts)


def test_no_approved_questions_parks_without_fabricating(host):
    with host() as (client, calls, p):
        run = prepared(client, p)
        assert run['status'] == 'awaiting_user'
        assert run['interaction']['kind'] == 'missing_questions'
        assert len(calls) == 3


def test_tampered_confirmation_and_stale_source_rejected(host):
    with host() as (client, _, p):
        bank(p)
        run = prepared(client, p)
        path = BASE+'/'+run['id']+'/confirm'
        assert client.post(path, json={'revision': run['revision'], 'confirmed': True, 'digest': 'forged'}).status_code == 409
        row = p.repo.read(p.scope(), 'source', SOURCE['id'])
        p.repo.put(p.scope(), 'source', SOURCE['id'], {**SOURCE, 'quote': '资料已更新'}, row['version'])
        assert client.post(path, json={'revision': run['revision'], 'confirmed': True, 'digest': run['interaction']['digest']}).status_code == 409
