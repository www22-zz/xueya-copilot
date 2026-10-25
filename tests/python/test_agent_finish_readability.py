"""Agent 完成分支的 HTTP/SSE 特征测试，复用真实宿主与 MCP 测试夹具。"""
import pytest

from test_agent_p1 import SOURCE, ask, call, finish, host, plan


@pytest.mark.parametrize('completion', ['completed', 'partial'])
def test_finish_keeps_completion_status_and_emits_one_final_result(host, completion):
    def script(value, platform):
        if value['state']['plan'] is None:
            return {'plan': plan(['read', 'answer']), 'action': call('read', 'read_source', sourceId=SOURCE['id'])}
        return {'action': finish(completion=completion)}

    with host(script) as (client, calls, platform):
        result, events = ask(client, stream=True)
        assert result['agent']['status'] == completion
        assert result['agent']['stopReason'] == ('FINISHED' if completion == 'completed' else 'INSUFFICIENT_RESULTS')
        assert result['agent']['completedStepIds'] == (['answer', 'read'] if completion == 'completed' else ['read'])
        assert result['sources'] == [SOURCE['id']]
        assert len(calls) == 2
        assert sum(event['type'] == 'done' for event in events) == 1
        assert any(event.get('stage') == 'validate' for event in events)


def test_premature_finish_can_continue_to_read_evidence_without_saving_false_completion(host):
    def script(value, platform):
        state = value['state']
        if state['plan'] is None:
            return {'plan': plan(['read', 'answer']), 'action': finish()}
        if len(state['decisions']) == 1:
            assert state['observations'][-1]['kind'] == 'completion-check'
            return {'action': call('read', 'read_source', sourceId=SOURCE['id'])}
        return {'action': finish()}

    with host(script) as (client, calls, platform):
        result, events = ask(client, stream=True)
        assert result['agent']['status'] == 'completed'
        assert result['agent']['decisionCount'] == 3 and len(calls) == 3
        assert result['agent']['observations'][0]['status'] == 'rejected'
        assert result['agent']['noProgress'] == 0
        assert result['sources'] == [SOURCE['id']]
        assert any(event.get('stage') == 'evaluate' and event['status'] == 'degraded' for event in events)
        assert sum(event['type'] == 'done' for event in events) == 1
