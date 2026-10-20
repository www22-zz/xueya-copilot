"""Persistent stepping, CAS and budget acceptance; no external network."""
import asyncio
import pytest
from test_agent_p1 import host

BASE = '/api/learning/agent-runs'


def create(client, **extra):
    client.headers['x-xueya-token'] = client.app.state.token
    r = client.post(BASE, json={'id': 'durable-test', 'question': '帮我学习队列这一章', **extra})
    assert r.status_code == 200, r.text
    return r.json()['result']


def step(client, p, key='durable-test'):
    return client.portal.call(client.app.state.learning.dynamic.execute, p.scope(), {'runId': key})


def test_steps_restore_results_and_budget_without_replaying(host):
    with host() as (client, calls, p):
        run = create(client)
        assert create(client) == run
        for expected in range(1, 5):
            run = step(client, p)
            assert len(calls) == expected
            assert run['budget']['models'] == expected
            if run['status'] == 'completed':
                break
        assert run['status'] == 'completed', run
        assert run['state']['persistedResume']
        assert run['result']['sources'] == ['p1-source']
        assert len(run['state']['completedStepIds']) == 3
        assert step(client, p)['status'] == 'completed'
        assert len(calls) == 3


def test_pause_revision_guard_resume_and_scope(host):
    with host() as (client, calls, p):
        run = create(client)
        path = BASE+'/durable-test/'
        paused = client.post(path+'pause', json={'revision': run['revision']}).json()['result']
        assert paused['status'] == 'paused'
        assert step(client, p)['status'] == 'paused' and not calls
        assert client.post(path+'resume', json={'revision': run['revision']}).status_code == 409
        r = client.post(path+'resume', json={'revision': paused['revision']})
        assert r.json()['result']['status'] == 'queued'
        assert client.get(BASE+'/durable-test?courseId=another-course').status_code != 200


def test_recovery_never_replays_unknown_model(host):
    with host() as (client, calls, p):
        run = create(client)
        service = client.app.state.learning.dynamic
        stored = service.get('course-default', run['id'])
        service.save({**stored, 'status': 'running', 'state': {'phase': 'deciding'}}, stored['revision'])
        client.portal.call(service.recover)
        recovered = service.get('course-default', run['id'])
        assert recovered['status'] == 'unknown'
        r = client.post(BASE+'/durable-test/resume', json={'revision': recovered['revision']})
        assert r.status_code != 200 and not calls


def test_budget_is_whole_run_across_jobs(host):
    with host(run_model_calls=1) as (client, calls, p):
        create(client)
        assert step(client, p)['status'] == 'queued'
        result = step(client, p)
        assert result['status'] == 'partial' and len(calls) == 1
        assert result['result']['agent']['stopReason'] == 'AI_MODEL_BUDGET_EXCEEDED'
