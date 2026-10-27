"""Trace real MCP attempts without changing existing workflow contracts."""
import asyncio
from contextlib import asynccontextmanager

from test_api_agent import Agent, FakeProvider, SOURCES, collect
from test_agent_p1 import host, ask, plan, call, finish
from backend.xueya.common import AppError


def test_dynamic_stream_exposes_arguments_before_observation_and_correlates_round(host):
    with host() as (client, requests, _):
        result, events = ask(client, stream=True)
        assert result['agent']['status'] == 'completed'
        pending = next(e['agent'] for e in events if e.get('stage') == 'tool')
        action = pending['decisions'][-1]
        assert action['tool'] == 'search_materials' and action['arguments']['query']
        assert not pending['observations']
        for observation in result['agent']['observations']:
            decision = next(d for d in result['agent']['decisions'] if d['round'] == observation['round'])
            assert decision['tool'] == observation['tool']
            assert decision['arguments'] == observation['arguments']


def test_fixed_workflow_reports_running_and_completed_actual_calls_without_dynamic_agent():
    events = asyncio.run(collect(Agent(FakeProvider()).workflow({
        'question': '二叉搜索树的查找复杂度？', 'sources': SOURCES})))
    pending = next(e['toolCalls'] for e in events if e.get('stage') == 'tool')
    assert pending[0]['status'] == 'running'
    done = events[-1]
    assert 'agent' not in done
    assert done['toolCalls'][0]['tool'] == 'search_materials'
    assert done['toolCalls'][0]['arguments']['query']
    assert all(c['status'] == 'completed' and 'data' in c for c in done['toolCalls'])
    assert any(c['tool'] == 'read_source' for c in done['toolCalls'])
    assert pending[0]['status'] == 'running'  # Earlier SSE snapshots are immutable.


def test_fixed_workflow_keeps_failed_tool_record_when_answer_falls_back(monkeypatch):
    class Broken:
        definitions = {'search_materials': {}}

        async def call(self, *args, **kwargs):
            raise AppError('MCP_BUSY')

    @asynccontextmanager
    async def unavailable(*args, **kwargs):
        yield Broken()

    monkeypatch.setattr('backend.xueya.agent.open_session', unavailable)
    events = asyncio.run(collect(Agent(FakeProvider()).workflow({
        'question': '二叉搜索树的查找复杂度？', 'sources': SOURCES})))
    call = events[-1]['toolCalls'][0]
    assert call['status'] == 'failed' and call['data']['error'] == 'MCP_BUSY'
    assert call['tool'] == 'search_materials'
    assert any(e.get('status') == 'degraded' for e in events)


def test_ten_tool_results_survive_final_trace_while_model_observations_stay_bounded(host):
    def script(value, platform):
        n = value['state']['decisionCount']
        if n <= 10:
            decision = {'action': call('read', 'read_source', sourceId='trace-'+str(n))}
            if n == 1:
                decision['plan'] = plan(['read', 'answer'])
            return decision
        return {'action': finish(answer={'answer': '队列原文片段 1', 'sources': ['trace-1']})}

    with host(script, agent_max_rounds=12, run_model_calls=12) as (client, requests, p):
        for n in range(1, 11):
            p.repo.put(p.scope(), 'source', 'trace-'+str(n), {
                'id': 'trace-'+str(n), 'title': '队列原文 '+str(n),
                'quote': '队列原文片段 '+str(n), 'location': '第一章'}, 0)
        result, _ = ask(client)
        assert result['agent']['status'] == 'completed'
        observations = result['agent']['observations']
        assert len(observations) == 10
        assert [o['round'] for o in observations] == list(range(1, 11))
        sent = __import__('json').loads(requests[-1]['messages'][-1]['content'])
        assert len(sent['state']['observations']) == 8
