"""Tests for Hot100 real Python execution and AI complexity diagnosis.

No real provider call is ever made: the AI tests inject a fake host model and
verify the host/ledger path is used, or that a missing model yields
``AI_UNAVAILABLE``. Execution tests only run our own reference solutions and
small failing snippets, under a workspace-local temporary root.
"""
import asyncio
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from backend.xueya import code_runner
from backend.xueya.common import AppError
from backend.xueya.practice_bank import questions

ROOT = Path(__file__).resolve().parent.parent
HOT = {q['id']: q for q in questions() if q.get('category') == 'hot100'}


@pytest.fixture
def runner_root(monkeypatch):
    """Workspace-local temp root: the sandbox denies system-temp writes."""
    path = ROOT / 'test-results' / 'code-runner-tests'
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(code_runner, 'WORK_ROOT', str(path))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def make_request(payload):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    state = {'sent': False}

    async def receive():
        if not state['sent']:
            state['sent'] = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        # Mimic a live client: after the body, receive blocks until disconnect.
        await asyncio.Event().wait()
        return {'type': 'http.disconnect'}

    scope = {
        'type': 'http',
        'method': 'POST',
        'path': '/api/learning/space/workbench/code/run',
        'raw_path': b'/api/learning/space/workbench/code/run',
        'query_string': b'',
        'headers': [],
    }
    return Request(scope, receive)


async def call_dispatch(rest, payload, host=None, course='course-default'):
    response = await code_runner.dispatch(rest, make_request(payload), course, host)
    return response, json.loads(response.body.decode('utf-8'))


class FakeModel:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def generate(self, value):
        self.calls.append(value)
        if self.error is not None:
            raise self.error
        return self.result


class FakeHost:
    def __init__(self, model):
        self._model = model

    def service(self, course):
        assert course == 'course-default'
        return SimpleNamespace(model=self._model)


def analysis_result(**overrides):
    payload = {
        'timeComplexity': 'O(n)',
        'spaceComplexity': 'O(n)',
        'summary': '使用哈希表一次遍历，时间线性。',
        'keyRisks': ['空数组时不能直接访问首元素', '重复元素可能影响下标选择'],
    }
    payload.update(overrides)
    return {
        'content': json.dumps(payload, ensure_ascii=False),
        'model': 'controlled-model',
        'usage': {'prompt_tokens': 12, 'completion_tokens': 34, 'total_tokens': 46},
    }


# ---------------------------------------------------------------------------
# Real execution
# ---------------------------------------------------------------------------


async def test_unknown_question_is_rejected(runner_root):
    with pytest.raises(AppError) as info:
        await code_runner.run_code({'questionId': 'h100-does-not-exist', 'language': 'python', 'code': 'x = 1'})
    assert info.value.code == 'QUESTION_NOT_FOUND'


async def test_syntax_error_is_reported_not_faked(runner_root):
    result = await code_runner.run_code({
        'questionId': 'h100-01', 'language': 'python', 'code': 'class Solution:\n    def broken(:\n        pass\n',
    })
    assert result['supported'] is True and result['passed'] is False
    assert result['error'] and '语法' in result['error']
    assert result['cases'] == []


async def test_infinite_loop_times_out(runner_root, monkeypatch):
    monkeypatch.setattr(code_runner, 'RUN_TIMEOUT_MS', 700)
    result = await code_runner.run_code({
        'questionId': 'h100-01',
        'language': 'python',
        'code': 'class Solution:\n    def twoSum(self, nums, target):\n        while True:\n            pass\n',
    })
    assert result['timedOut'] is True
    assert result['passed'] is False and result['cases'] == []
    assert '超时' in result['error']
    # The child process was killed and its workspace removed.
    assert list(runner_root.iterdir()) == []


async def test_reference_solution_passes(runner_root):
    question = HOT['h100-01']
    result = await code_runner.run_code({
        'questionId': question['id'], 'language': 'python', 'code': question['solutions']['python'],
    })
    assert result['supported'] is True and result['passed'] is True
    assert result['passedCases'] == result['totalCases'] == len(question['samples'])
    assert result['method'] == 'twoSum'
    assert result['sandbox']['note'] and result['sandbox']['isolatedProcess'] is True
    for case in result['cases']:
        assert case['passed'] is True and case['actual']
        assert case['input'] and case['expected']
    assert result['durationMs'] > 0
    assert list(runner_root.iterdir()) == []


async def test_wrong_answer_reports_real_actual_output(runner_root):
    result = await code_runner.run_code({
        'questionId': 'h100-01',
        'language': 'python',
        'code': 'class Solution:\n    def twoSum(self, nums, target):\n        return [0, 0]\n',
    })
    assert result['supported'] is True and result['passed'] is False
    assert result['totalCases'] == len(HOT['h100-01']['samples'])
    failed = [case for case in result['cases'] if not case['passed']]
    assert failed, 'a fabricated pass would leave no failed case'
    assert failed[0]['actual'] == '[0, 0]'
    assert failed[0]['error'] is None
    assert failed[0]['expected']


async def test_empty_linked_list_compares_as_empty(runner_root):
    question = HOT['h100-32']  # 反转链表, includes head = []
    result = await code_runner.run_code({
        'questionId': question['id'], 'language': 'python', 'code': question['solutions']['python'],
    })
    assert result['supported'] is True and result['passed'] is True


async def test_design_class_question_is_unsupported(runner_root):
    question = HOT['h100-68']  # 最小栈: no single Solution method
    result = await code_runner.run_code({
        'questionId': question['id'], 'language': 'python', 'code': question['solutions']['python'],
    })
    assert result['supported'] is False
    assert '设计类' in result['reason']
    assert 'passed' not in result


async def test_compiled_languages_follow_local_toolchain(runner_root):
    """C++/Java run only when the host has a working compiler; otherwise honest reason."""
    from backend.xueya import judge_toolchain
    question = HOT['h100-01']
    capabilities = judge_toolchain.detect(force=True)['capabilities']
    for language in ('cpp', 'java'):
        result = await code_runner.run_code({
            'questionId': question['id'], 'language': language,
            'code': question['solutions'][language],
        })
        if capabilities[language]['available']:
            assert result['supported'] is True
            assert result['passed'] is True
            assert result['compiler']['name'] in ('g++', 'javac')
        else:
            assert result['supported'] is False
            assert result['reason']


async def test_code_without_solution_class_is_unsupported(runner_root):
    result = await code_runner.run_code({
        'questionId': 'h100-01', 'language': 'python', 'code': 'def twoSum(nums, target):\n    return [0, 1]\n',
    })
    assert result['supported'] is False
    assert 'Solution' in result['reason']


async def test_case_index_runs_a_single_case(runner_root):
    question = HOT['h100-01']
    result = await code_runner.run_code({
        'questionId': question['id'], 'language': 'python',
        'code': question['solutions']['python'], 'caseIndex': 1,
    })
    assert result['totalCases'] == 1
    assert result['cases'][0]['index'] == 0
    assert result['cases'][0]['input'].startswith('nums = [3, 2, 4]')


async def test_user_stdout_is_capped(runner_root):
    code = (
        'import sys\n'
        'class Solution:\n'
        '    def twoSum(self, nums, target):\n'
        '        sys.stdout.write("x" * 80000)\n'
        '        return [0, 1]\n'
    )
    result = await code_runner.run_code({'questionId': 'h100-01', 'language': 'python', 'code': code})
    assert result['supported'] is True
    assert len(result['stdout']) <= code_runner.MAX_CAPTURE_BYTES + 64
    assert '截断' in result['stdout']


async def test_run_route_via_dispatch(runner_root):
    question = HOT['h100-01']
    response, data = await call_dispatch('run', {
        'questionId': question['id'], 'language': 'python', 'code': question['solutions']['python'],
    })
    assert response.status_code == 200
    assert data['ok'] is True and data['result']['passed'] is True


async def test_unknown_rest_returns_none(runner_root):
    assert await code_runner.dispatch('missing', make_request({}), 'course-default', None) is None


# ---------------------------------------------------------------------------
# AI complexity diagnosis (fake host model only, never billed)
# ---------------------------------------------------------------------------


async def test_analyze_without_model_is_ai_unavailable():
    with pytest.raises(AppError) as info:
        await code_runner.analyze_code(
            {'questionId': 'h100-01', 'language': 'python', 'code': HOT['h100-01']['solutions']['python']},
            'course-default', FakeHost(None),
        )
    assert info.value.code == 'AI_UNAVAILABLE'


async def test_analyze_uses_host_scoped_model_and_returns_real_fields():
    model = FakeModel(analysis_result())
    data = await code_runner.analyze_code(
        {'questionId': 'h100-01', 'language': 'python', 'code': HOT['h100-01']['solutions']['python']},
        'course-default', FakeHost(model),
    )
    assert len(model.calls) == 1
    call = model.calls[0]
    assert call['maxOutputTokens'] == 900
    assert call['responseFormat'] == {'type': 'json_object'}
    assert call['messages'][0]['role'] == 'system'
    assert data['analysis']['timeComplexity'] == 'O(n)'
    assert data['analysis']['spaceComplexity'] == 'O(n)'
    assert data['analysis']['model'] == 'controlled-model'
    assert data['usage'] == {'prompt_tokens': 12, 'completion_tokens': 34, 'total_tokens': 46}
    assert data['durationMs'] >= 0


async def test_analyze_rejects_non_json_model_output():
    model = FakeModel({'content': '这不是 JSON', 'model': 'controlled-model'})
    with pytest.raises(AppError) as info:
        await code_runner.analyze_code(
            {'questionId': 'h100-01', 'language': 'python', 'code': HOT['h100-01']['solutions']['python']},
            'course-default', FakeHost(model),
        )
    assert info.value.code == 'AI_INVALID_RESPONSE'


async def test_analyze_maps_model_timeout_and_failure():
    with pytest.raises(AppError) as timeout_info:
        await code_runner.analyze_code(
            {'questionId': 'h100-01', 'language': 'python', 'code': HOT['h100-01']['solutions']['python']},
            'course-default', FakeHost(FakeModel(error=TimeoutError())),
        )
    assert timeout_info.value.code == 'AI_TIMEOUT'
    with pytest.raises(AppError) as failure_info:
        await code_runner.analyze_code(
            {'questionId': 'h100-01', 'language': 'python', 'code': HOT['h100-01']['solutions']['python']},
            'course-default', FakeHost(FakeModel(error=RuntimeError('provider down'))),
        )
    assert failure_info.value.code == 'AI_UNAVAILABLE'


async def test_analyze_validates_question_and_code_length():
    with pytest.raises(AppError) as info:
        await code_runner.analyze_code({'questionId': 'missing', 'language': 'python', 'code': 'x'},
                                       'course-default', FakeHost(FakeModel(analysis_result())))
    assert info.value.code == 'QUESTION_NOT_FOUND'
    with pytest.raises(AppError) as info:
        await code_runner.analyze_code({'questionId': 'h100-01', 'language': 'python', 'code': 'x' * 20001},
                                       'course-default', FakeHost(FakeModel(analysis_result())))
    assert info.value.code == 'CODE_TOO_LARGE'


async def test_analyze_route_via_dispatch():
    response, data = await call_dispatch('analyze', {
        'questionId': 'h100-01', 'language': 'python', 'code': HOT['h100-01']['solutions']['python'],
    }, host=FakeHost(FakeModel(analysis_result())))
    assert response.status_code == 200
    assert data['ok'] is True
    assert data['analysis']['summary']
    assert data['analysis']['keyRisks']
