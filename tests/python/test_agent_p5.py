import pytest
from test_agent_p1 import host
from test_agent_p2 import create, step, BASE


@pytest.mark.parametrize('setting', [{'agent_durable_enabled': False}, {'agent_rollout_percent': 0}, {'agent_planning_enabled': False}])
def test_rollout_disables_new_runs_and_keeps_old_chat(host, setting):
    with host(**setting) as (client, calls, p):
        client.headers['x-xueya-token'] = client.app.state.token
        features = client.get(BASE+'/features').json()['result']
        assert features['durable'] is False
        assert client.post(BASE, json={'id': 'disabled', 'question': '学习队列'}).status_code != 200
        assert client.post('/api/agent', json={'question': '你好'}).status_code == 200
        assert not calls


def test_interactive_switch_keeps_readonly_and_hides_internal_cache(host):
    with host(agent_interactive_enabled=False) as (client, _, p):
        client.headers['x-xueya-token'] = client.app.state.token
        assert client.post(BASE, json={'id': 'disabled', 'question': '学习队列', 'scenario': 'chapter'}).status_code != 200
        create(client)
        run = step(client, p)
        assert 'tools' not in run['state']
        stored = client.app.state.learning.dynamic.get('course-default', 'durable-test')
        assert 'tools' in stored['state']


def test_selected_sources_cannot_inject_or_expand_scope(host):
    with host() as (client, _, p):
        client.headers['x-xueya-token'] = client.app.state.token
        assert client.post(BASE, json={'id': 'inject', 'question': '学习队列', 'sourceIds': ['fake']}).status_code == 409
        run = create(client, sourceIds=['p1-source'])
        assert run['status'] == 'queued'


def test_structured_planner_mode_reaches_actual_provider_transport(host):
    with host() as (client, calls, p):
        create(client)
        step(client, p)
        assert calls[0]['response_format'] == {'type': 'json_object'}
