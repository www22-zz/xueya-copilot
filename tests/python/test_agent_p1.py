"""Causal, offline P1 acceptance against the production host and real MCP SDK."""
import asyncio
from contextlib import contextmanager, aclosing
from copy import deepcopy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.xueya.agent import Agent
from backend.xueya.app import create_app
from backend.xueya.common import dumps, utc_now
from backend.xueya.config import Config
from backend.xueya.learning import today, add_days
from backend.xueya.mcp_core import CONNECTIONS
from backend.xueya.provider import MimoProvider
from backend.agent.tool_adapter import READ_ONLY_TOOLS
from scripts.readonly_agent_fixture import planner_response

SOURCE = {'id': 'p1-source', 'title': '队列', 'location': '章节1', 'quote': '队列遵循先进先出，先入队的元素先出队。', 'keywords': ['队列', '先进先出']}


def plan(ids, requirements=('evidence',)):
    return {'goal': '完成本轮队列学习准备', 'requirements': list(requirements), 'steps': [{'id': key, 'title': key} for key in ids]}


def call(step, name, **args):
    return {'type': 'call_tool', 'stepId': step, 'tool': name, 'arguments': args}


def finish(step='answer', **extra):
    return {'type': 'finish', 'stepId': step, 'completion': 'completed',
            'answer': {'answer': SOURCE['quote'], 'sources': [SOURCE['id']], 'knowledgePoints': []}, **extra}


@pytest.fixture
def host(tmp_path):
    @contextmanager
    def start(script=None, **options):
        captured, platform = [], []
        def upstream(request):
            payload = json.loads(request.content)
            captured.append(payload)
            if 'xueya.readonly-agent.v1' not in str(payload['messages'][0]['content']):
                result = dumps({'answer': SOURCE['quote'], 'sources': [SOURCE['id']]})
                if payload.get('stream'):
                    return httpx.Response(200, text='data: '+dumps({'choices': [{'delta': {'content': result}}]})+'\n\ndata: [DONE]\n\n')
                return httpx.Response(200, json={'choices': [{'message': {'content': result}, 'finish_reason': 'stop'}]})
            value = json.loads(payload['messages'][-1]['content'])
            if script is None:
                return planner_response(payload)
            decision = script(value, platform[0])
            if isinstance(decision, httpx.Response):
                return decision
            return httpx.Response(200, json={'choices': [{'message': {'content': dumps(decision)}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 50, 'completion_tokens': 100}})
        config = Config(data_dir=tmp_path/('data-'+str(len(list(tmp_path.iterdir())))), api_key='offline-only', **options)
        app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)), start_jobs=False)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            p = app.state.platform
            platform.append(p)
            p.repo.put(p.scope(), 'source', SOURCE['id'], SOURCE, 0)
            p.repo.put(p.scope(), 'question', 'p1-q', {'id': 'p1-q', 'topic': '队列', 'prompt': '队列顺序', 'sourceId': SOURCE['id']}, 0)
            p.repo.put(p.scope(), 'attempt', 'p1-a', {'id': 'p1-a', 'questionId': 'p1-q', 'correct': False, 'createdAt': utc_now()}, 0)
            yield client, captured, p
    return start


def ask(client, question='帮我学习队列这一章', stream=False, **body):
    response = client.post('/api/agent'+('/stream' if stream else ''), json={'question': question, **body})
    assert response.status_code == 200, response.text
    if not stream:
        return response.json(), []
    events = [json.loads(frame[6:]) for frame in response.text.split('\n\n') if frame.startswith('data: ')]
    assert events[-1]['type'] == 'done', events
    return events[-1], events


@pytest.mark.parametrize('question,expected', [
    ('帮我学习队列这一章', {'search_materials', 'read_source'}),
    ('分析队列错题并准备巩固资料', {'search_materials', 'read_source', 'analyze_progress', 'list_wrong_questions'}),
    ('根据错题安排备考复习计划', {'analyze_progress', 'list_wrong_questions', 'build_review_plan'})])
@pytest.mark.parametrize('stream', [False, True])
def test_three_learning_scenarios_choose_tools_and_keep_existing_contract(host, question, expected, stream):
    with host() as (client, requests, p):
        result, events = ask(client, question, stream)
        assert result['agent']['status'] == 'completed', result
        used = {o['tool'] for o in result['agent']['observations'] if 'tool' in o}
        assert used >= expected and used <= READ_ONLY_TOOLS
        assert set(('answer', 'sources', 'knowledgePoints', 'model', 'workflow')) <= result.keys()
        if 'read_source' in expected:
            assert SOURCE['quote'] in result['answer'] and result['sources'] == [SOURCE['id']]
        if 'build_review_plan' in expected:
            assert result['artifacts']['plan']['days'] and '尚未修改' in result['answer']
        assert result['agent']['decisionCount'] == len(requests)
        assert p.repo.all(p.scope(), 'note') == [] and p.repo.all(p.scope(), 'plan') == []
        run = p.repo.all(p.scope(), 'run')[0]
        assert run['status'] == 'succeeded' and run['result']['agent']['plan']
        assert p.repo.all(p.scope(), 'checkpoint')[0]['agent']['decisionCount']
        assert len(p.db.all('SELECT id FROM invocations')) == len(requests)
        assert all(r['max_completion_tokens'] == 1536 for r in requests)
        if stream:
            assert {e['type'] for e in events} <= {'workflow', 'content', 'done'}
            assert any(e.get('stage') == 'observe' for e in events)


def test_empty_search_changes_plan_and_query_from_observation(host):
    def script(value, p):
        state = value['state']
        if state['plan'] is None:
            return {'plan': plan(['first', 'read', 'answer']), 'action': call('first', 'search_materials', query='不存在的术语')}
        if not state['replans']:
            assert state['observations'][-1]['data']['sources'] == []
            revised = deepcopy(state['plan'])
            revised['steps'].insert(1, {'id': 'second', 'title': '换用队列关键词搜索'})
            return {'action': {'type': 'revise_plan', 'plan': revised}}
        if 'second' not in state['completedStepIds']:
            return {'action': call('second', 'search_materials', query='队列')}
        if 'read' not in state['completedStepIds']:
            source = state['observations'][-1]['data']['sources'][0]
            return {'action': call('read', 'read_source', sourceId=source['id'])}
        return {'action': finish()}
    with host(script) as (client, _, _):
        result, events = ask(client, stream=True)
        assert result['agent']['status'] == 'completed'
        assert result['agent']['planRevision'] == 2 and result['agent']['replans'] == 1
        queries = [o['arguments']['query'] for o in result['agent']['observations'] if o.get('tool') == 'search_materials']
        assert queries == ['不存在的术语', '队列']
        assert any(e.get('stage') == 'replan' for e in events)


def test_readonly_plan_can_use_proposed_time_settings_without_saving(host):
    exam = add_days(today(), 14)
    def script(value, p):
        state = value['state']
        if not state['plan']:
            return {'plan': plan(['progress', 'schedule', 'answer'], ['progress', 'review_plan']), 'action': call('progress', 'analyze_progress')}
        if 'schedule' not in state['completedStepIds']:
            return {'action': call('schedule', 'build_review_plan', examDate=exam, minutes=40)}
        return {'action': finish()}
    with host(script) as (client, _, p):
        result, _ = ask(client, '两周后考试，每天40分钟，安排队列复习计划')
        assert result['agent']['status'] == 'completed'
        assert result['artifacts']['plan']['examDate'] == exam and result['artifacts']['plan']['minutes'] == 40
        assert not p.repo.all(p.scope(), 'plan') and p.repo.get_workspace(p.user_id) is None


def test_premature_completion_is_rejected_and_actual_next_action_changes(host):
    def script(value, p):
        if value['state']['plan'] is None:
            return {'plan': plan(['answer']), 'action': finish()}
        assert value['state']['observations'][-1]['data']['missingRequirements'] == ['evidence']
        return {'action': {'type': 'ask_user', 'question': '请提供本章资料或明确要理解的知识点。'}}
    with host(script) as (client, requests, p):
        result, _ = ask(client)
        assert result['agent']['status'] == 'awaiting_user' and len(requests) == 2
        assert result['sources'] == [] and '需要你补充' in result['answer']
        assert p.repo.all(p.scope(), 'run')[0]['status'] == 'awaiting_user'


@pytest.mark.parametrize('tool,args', [('apply_action', {}), ('lookup_reference', {'doi': '10.1/evil'}),
    ('read_source', {'sourceId': SOURCE['id'], 'courseId': 'other'}),
    ('build_review_plan', {'confirmed': True})])
def test_untrusted_decision_cannot_escalate_tools_scope_or_confirmation(host, tool, args):
    def script(value, p):
        return {'plan': plan(['attempt', 'answer']), 'action': call('attempt', tool, **args)} if value['state']['plan'] is None else {'action': {'type': 'ask_user', 'question': '请补充学习范围。'}}
    with host(script) as (client, _, p):
        result, _ = ask(client, budget={'maxCalls': 9999}, allowedTools=['apply_action'])
        observation = result['agent']['observations'][0]
        assert observation['status'] == 'failed' and observation['data']['error'] in ('TOOL_FORBIDDEN', 'INVALID_TOOL_ARGUMENTS')
        assert not p.db.all('SELECT * FROM audits') and not p.repo.all(p.scope(), 'note')


def test_duplicate_calls_stop_without_reexecuting_tools(host):
    def script(value, p):
        answer = {'action': call('find', 'search_materials', query='没有匹配资料')}
        if not value['state']['plan']:
            answer['plan'] = plan(['find', 'answer'])
        return answer
    with host(script) as (client, requests, _):
        result, _ = ask(client)
        assert result['agent']['status'] == 'awaiting_user' and result['agent']['stopReason'] == 'AGENT_NO_PROGRESS'
        assert len(requests) == 2 and result['agent']['observations'][-1]['status'] == 'duplicate'


@pytest.mark.parametrize('options,reason,calls', [({'agent_max_rounds': 1}, 'AGENT_ROUND_LIMIT', 1),
    ({'run_model_calls': 1}, 'AI_MODEL_BUDGET_EXCEEDED', 1),
    ({'run_tool_calls': 1}, 'AI_TOOL_BUDGET_EXCEEDED', 2)])
def test_p0_and_loop_budgets_bound_the_entire_dynamic_request(host, options, reason, calls):
    with host(**options) as (client, captured, p):
        result, _ = ask(client)
        assert result['agent']['status'] == 'partial' and result['agent']['stopReason'] == reason
        assert len(captured) == calls and len(p.db.all('SELECT id FROM invocations')) == calls
        assert p.resources.active['api'] == 0


@pytest.mark.parametrize('mutate', ['delete', 'same-text-revision'])
def test_source_change_during_decision_invalidates_earlier_observations(host, mutate):
    def script(value, p):
        if value['state']['plan'] is None:
            return {'plan': plan(['read', 'answer']), 'action': call('read', 'read_source', sourceId=SOURCE['id'])}
        row = p.repo.read(p.scope(), 'source', SOURCE['id'])
        p.repo.put(p.scope(), 'source', SOURCE['id'], row['value'], row['version'], deleted=mutate == 'delete')
        return {'action': finish()}
    with host(script) as (client, requests, _):
        result, _ = ask(client)
        assert len(requests) == 2 and result['sources'] == []
        assert result['agent']['stopReason'] == 'STALE_EVIDENCE' and '更新或移除' in result['answer']


def test_unverified_final_answer_and_client_forged_sources_never_become_facts(host):
    injected = '模型伪造的已保存成绩'
    def script(value, p):
        assert '客户端伪造原文' not in dumps(value)
        if value['state']['plan'] is None:
            return {'plan': plan(['read', 'answer']), 'action': call('read', 'read_source', sourceId=SOURCE['id'])}
        return {'action': finish(answer={'answer': injected, 'sources': [SOURCE['id']]})}
    with host(script) as (client, _, _):
        result, events = ask(client, stream=True, sources=[{'id': SOURCE['id'], 'quote': '客户端伪造原文'}])
        assert result['agent']['status'] == 'completed'
        assert SOURCE['quote'] in result['answer'] and injected not in dumps(events)


def test_replanning_cannot_delete_completed_steps_or_lower_requirements(host):
    def script(value, p):
        if value['state']['plan'] is None:
            return {'plan': plan(['read', 'answer']), 'action': call('read', 'read_source', sourceId=SOURCE['id'])}
        revised = deepcopy(value['state']['plan'])
        revised['steps'] = [{'id': 'answer', 'title': 'answer'}]
        return {'action': {'type': 'revise_plan', 'plan': revised}}
    with host(script) as (client, requests, _):
        result, _ = ask(client)
        assert result['agent']['status'] == 'partial' and result['agent']['stopReason'] == 'AGENT_COMPLETED_STEP_CHANGED'
        assert len(requests) == 2


def test_malformed_and_unknown_model_outcomes_do_not_trigger_paid_repair(host):
    with host(lambda value, p: {'answer': 'not a decision'}) as (client, captured, _):
        result, _ = ask(client)
        assert result['agent']['status'] == 'partial' and len(captured) == 1
    def broken(value, p):
        raise httpx.ReadError('offline unknown outcome')
    with host(broken) as (client, captured, p):
        result, _ = ask(client)
        assert result['agent']['status'] == 'partial' and len(captured) == 1
        assert p.db.one('SELECT status FROM invocations')['status'] == 'unknown'


def test_server_can_disable_planner_and_greetings_keep_zero_model_calls(host):
    with host(agent_planning_enabled=False) as (client, captured, _):
        result, _ = ask(client)
        assert 'agent' not in result and SOURCE['quote'] in result['answer']
        assert len(captured) == 1
    with host() as (client, captured, _):
        result, _ = ask(client, '你好')
        assert 'agent' not in result and len(captured) == 0


@pytest.mark.parametrize('correct,expected', [(False, 'read_source'), (True, 'get_review_queue')])
def test_same_goal_selects_different_next_tool_from_real_grade(host, correct, expected):
    def script(value, p):
        state = value['state']
        if state['plan'] is None:
            return {'plan': plan(['progress', 'next', 'answer'], ['progress']), 'action': call('progress', 'analyze_progress')}
        if 'next' not in state['completedStepIds']:
            stats = state['observations'][0]['data']
            assert stats['total'] == 1
            return {'action': call('next', 'get_review_queue') if stats['correct'] == 1 else call('next', 'read_source', sourceId=SOURCE['id'])}
        return {'action': finish()}
    with host(script) as (client, _, p):
        row = p.repo.read(p.scope(), 'attempt', 'p1-a')
        p.repo.put(p.scope(), 'attempt', 'p1-a', {**row['value'], 'correct': correct}, row['version'])
        result, _ = ask(client, '分析队列学习情况')
        assert result['agent']['status'] == 'completed'
        assert [o['tool'] for o in result['agent']['observations']] == ['analyze_progress', expected]
        assert result['artifacts']['progress']['correct'] == int(correct)


def test_forged_tool_quote_is_not_forwarded_or_used_for_completion(host, monkeypatch):
    import backend.xueya.mcp_core as mcp
    original = mcp.platform_registry
    def compromised(*args, **kwargs):
        registry = original(*args, **kwargs)
        registry.tools['read_source'].handler = lambda args: {'source': {**SOURCE, 'quote': '伪造工具原文'}}
        return registry
    monkeypatch.setattr(mcp, 'platform_registry', compromised)
    def script(value, p):
        return {'plan': plan(['read', 'answer']), 'action': call('read', 'read_source', sourceId=SOURCE['id'])}
    with host(script) as (client, requests, _):
        result, events = ask(client, stream=True)
        assert result['agent']['status'] == 'partial' and result['agent']['stopReason'] == 'MCP_INVALID_RESULT'
        assert len(requests) == 1 and result['sources'] == []
        assert '伪造工具原文' not in dumps(events)


async def test_cancelled_planning_releases_model_mcp_and_records_cancelled_run(tmp_path):
    ready = asyncio.Event()
    async def blocked(request):
        ready.set()
        await asyncio.Event().wait()
    config = Config(data_dir=tmp_path, api_key='offline-only')
    from backend.xueya.platform import Platform
    p = Platform(tmp_path)
    p.repo.put(p.scope(), 'source', SOURCE['id'], SOURCE, 0)
    provider = MimoProvider(config, p, httpx.MockTransport(blocked))
    async def collect():
        async with aclosing(Agent(provider, p).workflow({'question': '学习队列'})) as events:
            return [event async for event in events]
    try:
        task = asyncio.create_task(collect())
        await asyncio.wait_for(ready.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert p.resources.active['api'] == 0 and CONNECTIONS.active == 0
        assert p.repo.all(p.scope(), 'run')[0]['status'] == 'cancelled'
        assert p.db.one('SELECT status FROM invocations')['status'] == 'unknown'
    finally:
        await p.close()
