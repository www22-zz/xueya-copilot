"""Replay the live 2026-10-23 finish response without paid repair calls."""
from copy import deepcopy

import pytest

from test_agent_p1 import host, ask, plan, call, SOURCE
from test_agent_p2 import create, step


def live_finish():
    # The real provider omitted the decision envelope and used summary/source objects.
    return {'type': 'finish', 'stepId': 'answer', 'completion': 'completed',
            'answer': {'summary': '已核对先进先出定义。',
                       'sources': [{'id': SOURCE['id'], 'quote': SOURCE['quote']}],
                       'claims': [{'text': '伪造的已保存成绩', 'evidenceSourceId': SOURCE['id'],
                                   'quote': SOURCE['quote']}],
                       'knowledgePoints': [{'name': '队列', 'mastery': '已掌握'}]}}


@pytest.mark.parametrize('durable', [False, True])
def test_live_flat_finish_completes_after_real_read_and_keeps_answer_verification(host, durable):
    def script(value, platform):
        if value['state']['plan'] is None:
            return {'plan': plan(['read', 'answer']),
                    'action': call('read', 'read_source', sourceId=SOURCE['id'])}
        return live_finish()

    with host(script) as (client, requests, p):
        if durable:
            create(client)
            assert step(client, p)['status'] == 'queued'
            run = step(client, p)
            assert run['status'] == 'completed'
            result = run['result']
        else:
            result, _ = ask(client, stream=True)
        assert result['agent']['status'] == 'completed'
        assert result['agent']['stopReason'] == 'FINISHED'
        assert len(requests) == 2  # No extra model call to repair the JSON.
        assert SOURCE['quote'] in result['answer']
        assert result['sources'] == [SOURCE['id']]
        assert result['verification'] == 'verbatim-only'
        assert result['engine'] == 'local-workflow'
        assert '伪造' not in result['answer'] and '已掌握' not in result['answer']
        assert p.repo.all(p.scope(), 'plan') == []


@pytest.mark.parametrize('extra', [
    {'courseId': 'other'}, {'confirmed': True}, {'tool': 'apply_action'},
    {'action': {'type': 'ask_user', 'question': 'override'}},
    {'completion': 'saved'}, {'stepId': 'unknown'},
])
def test_flat_finish_does_not_drop_unknown_fields_or_skip_step_checks(host, extra):
    def script(value, platform):
        if value['state']['plan'] is None:
            return {'plan': plan(['read', 'answer']),
                    'action': call('read', 'read_source', sourceId=SOURCE['id'])}
        return {**live_finish(), **deepcopy(extra)}

    with host(script) as (client, requests, p):
        result, _ = ask(client)
        assert result['agent']['status'] == 'partial'
        assert result['agent']['stopReason'] in ('AGENT_INVALID_DECISION', 'AGENT_UNKNOWN_STEP')
        assert len(requests) == 2
        assert p.repo.all(p.scope(), 'plan') == []


def test_flat_finish_cannot_satisfy_missing_evidence(host):
    def script(value, platform):
        decision = live_finish()
        if value['state']['plan'] is None:
            return {'plan': plan(['read', 'answer']), 'action': decision}
        return decision

    with host(script, agent_no_progress_limit=1) as (client, requests, _):
        result, _ = ask(client)
        assert result['agent']['status'] == 'awaiting_user'
        assert result['agent']['stopReason'] == 'AGENT_NO_PROGRESS'
        assert result['sources'] == [] and len(requests) == 1


def test_flat_tool_call_remains_invalid_without_executing(host):
    with host(lambda value, platform: call('read', 'read_source', sourceId=SOURCE['id'])) as (client, requests, _):
        result, _ = ask(client)
        assert result['agent']['stopReason'] == 'AGENT_INVALID_DECISION'
        assert not result['agent']['observations'] and len(requests) == 1
