"""Tests for local toolchain detection and compiled C++/Java execution.

Hermetic unit tests never touch a compiler; the execution tests are skipped when
this machine has no C++/Java toolchain. No paid model call is involved.
"""
import asyncio
import json
import shutil
from pathlib import Path

import pytest
from starlette.requests import Request

from backend.xueya import code_runner, judge_compiled, judge_toolchain
from backend.xueya.practice_bank import questions

ROOT = Path(__file__).resolve().parent.parent
HOT = {q['id']: q for q in questions() if q.get('category') == 'hot100'}
BY_NUMBER = {q.get('leetcodeNumber'): q for q in HOT.values()}


@pytest.fixture
def runner_root(monkeypatch):
    path = ROOT / 'test-results' / 'compiled-runner-tests'
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(code_runner, 'WORK_ROOT', str(path))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_toolchain_cache():
    judge_toolchain.reset_cache()
    yield
    judge_toolchain.reset_cache()


def make_request(method='POST', payload=None, query=''):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else b''
    state = {'sent': False}

    async def receive():
        if not state['sent']:
            state['sent'] = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        await asyncio.Event().wait()
        return {'type': 'http.disconnect'}

    scope = {
        'type': 'http', 'method': method,
        'path': '/api/learning/space/workbench/code/run', 'raw_path': b'/api/learning/space/workbench/code/run',
        'query_string': query.encode('utf-8'), 'headers': [],
    }
    return Request(scope, receive)


def capabilities():
    return judge_toolchain.detect(force=True)['capabilities']


# ---------------------------------------------------------------------------
# Toolchain detection (hermetic)
# ---------------------------------------------------------------------------


def test_detection_without_compilers_is_honest(monkeypatch):
    monkeypatch.setattr(judge_toolchain, '_find', lambda name, override=None: None)
    value = judge_toolchain.detect(force=True)
    assert value['capabilities']['python']['available'] is True
    assert value['capabilities']['cpp']['available'] is False
    assert 'g++' in value['capabilities']['cpp']['reason']
    assert value['capabilities']['java']['available'] is False
    assert 'javac' in value['capabilities']['java']['reason']
    assert value['languages'] == ['python']


def test_available_languages_follow_capabilities(monkeypatch):
    monkeypatch.setattr(judge_toolchain, 'detect', lambda force=False: {
        'capabilities': {'python': {'available': True}, 'cpp': {'available': True}, 'java': {'available': False}},
        'languages': ['python', 'cpp'],
    })
    assert judge_toolchain.available_languages() == ['python', 'cpp']


def test_overridden_compiler_path_must_exist(monkeypatch, tmp_path):
    fake = tmp_path / 'g++-custom'
    fake.write_text('', encoding='utf-8')
    monkeypatch.setenv('XUEYA_GPP_PATH', str(fake))
    assert judge_toolchain._override_path('cpp') == str(fake)
    monkeypatch.setenv('XUEYA_GPP_PATH', str(tmp_path / 'missing'))
    assert judge_toolchain._override_path('cpp') is None


# ---------------------------------------------------------------------------
# Signature parsing and literal generation (hermetic)
# ---------------------------------------------------------------------------


def test_cpp_signature_parsing():
    question = BY_NUMBER[1]
    return_type, params = judge_compiled._parse_cpp_signature(question['solutions']['cpp'], 'twoSum')
    assert return_type == 'vector<int>'
    assert [name for _type, name in params] == ['nums', 'target']
    assert params[0][0] == 'vector<int>' and params[1][0] == 'int'


def test_java_signature_parsing():
    question = BY_NUMBER[1]
    return_type, params = judge_compiled._parse_java_signature(question['solutions']['java'], 'twoSum')
    assert return_type == 'int[]'
    assert [name for _type, name in params] == ['nums', 'target']
    assert params[0][0] == 'int[]' and params[1][0] == 'int'


def test_cpp_literal_generation():
    assert judge_compiled._cpp_literal(9, 'int') == '9'
    assert judge_compiled._cpp_literal(True, 'bool') == 'true'
    assert judge_compiled._cpp_literal('ab', 'string') == '"ab"'
    assert judge_compiled._cpp_literal([2, 7], 'vector<int>') == 'std::vector<int>{2, 7}'
    assert judge_compiled._cpp_literal([[1, 2], [3]], 'vector<vector<int>>') == \
        'std::vector<std::vector<int>>{std::vector<int>{1, 2}, std::vector<int>{3}}'
    assert judge_compiled._cpp_literal(['a', 'b'], 'vector<char>') == "std::vector<char>{'a', 'b'}"


def test_java_literal_generation():
    assert judge_compiled._java_literal(9, 'int') == '9'
    assert judge_compiled._java_literal(True, 'boolean') == 'true'
    assert judge_compiled._java_literal('ab', 'String') == '"ab"'
    assert judge_compiled._java_literal([2, 7], 'int[]') == 'new int[]{2, 7}'
    assert judge_compiled._java_literal([[1, 2], [3]], 'int[][]') == 'new int[][]{new int[]{1, 2}, new int[]{3}}'
    assert judge_compiled._java_literal([1, 2], 'List<Integer>') == \
        'new ArrayList<>(Arrays.asList(1, 2))'
    assert judge_compiled._java_literal([], 'List<Integer>') == 'new ArrayList<>()'


def test_tree_and_linked_values_validate_types():
    assert judge_compiled._tree_tokens([1, None, 2]) == ['1', 'null', '2']
    assert judge_compiled._linked_values([1, 2, 3]) == [1, 2, 3]
    with pytest.raises(judge_compiled._Unsupported):
        judge_compiled._tree_tokens('not-a-list')
    with pytest.raises(judge_compiled._Unsupported):
        judge_compiled._linked_values(['x'])


# ---------------------------------------------------------------------------
# Plan building (hermetic)
# ---------------------------------------------------------------------------


def test_compiled_plan_builds_cases_and_harness():
    question = BY_NUMBER[1]
    for language in ('cpp', 'java'):
        plan = judge_compiled.build_plan(question, question['solutions'][language], language)
        assert plan.get('unsupported') is None
        assert plan['method'] == 'twoSum'
        assert len(plan['cases']) == len(question['samples'])
        assert plan['harness']
        assert 'twoSum' in plan['harness']
        assert plan['params'][0]['name'] == 'nums'


def test_design_question_is_unsupported_for_compiled_languages():
    question = BY_NUMBER.get(146) or next(q for q in HOT.values() if 'LRU' in q['title'])
    plan = judge_compiled.build_plan(question, question['solutions']['cpp'], 'cpp')
    assert plan['unsupported'] is True and '设计类' in plan['reason']


def test_special_linked_structure_question_is_unsupported():
    question = BY_NUMBER[141]  # 环形链表：需要构造环
    plan = judge_compiled.build_plan(question, question['solutions']['cpp'], 'cpp')
    assert plan['unsupported'] is True and '环' in plan['reason']


def test_missing_language_solution_is_unsupported():
    question = BY_NUMBER[1]
    solutions = {'python': question['solutions']['python'], 'cpp': question['solutions']['cpp']}
    plan = judge_compiled.build_plan({**question, 'solutions': solutions},
                                     question['solutions']['cpp'], 'java')
    assert plan['unsupported'] is True and '缺少' in plan['reason']


# ---------------------------------------------------------------------------
# Route / capabilities endpoint
# ---------------------------------------------------------------------------


async def test_capabilities_route(monkeypatch):
    monkeypatch.setattr(judge_toolchain, 'detect', lambda force=False: {
        'capabilities': {'python': {'available': True, 'label': 'Python'},
                         'cpp': {'available': True, 'label': 'g++'},
                         'java': {'available': False, 'reason': '未检测到 javac'}},
        'languages': ['python', 'cpp'], 'detectedAt': 'now',
    })
    response = await code_runner.dispatch('capabilities', make_request('GET'), 'course-default', None)
    assert response.status_code == 200
    data = json.loads(response.body.decode('utf-8'))
    assert data['ok'] is True
    assert data['languages'] == ['python', 'cpp']
    assert data['capabilities']['java']['reason'] == '未检测到 javac'


async def test_capabilities_route_rejects_post():
    from backend.xueya.common import AppError
    with pytest.raises(AppError) as info:
        await code_runner.dispatch('capabilities', make_request('POST', {}), 'course-default', None)
    assert info.value.code == 'METHOD_NOT_ALLOWED'


# ---------------------------------------------------------------------------
# Real compiled execution (only when this machine has the toolchain)
# ---------------------------------------------------------------------------


def require_language(language):
    available = judge_toolchain.available_languages()
    if language not in available:
        pytest.skip(f'{language} toolchain not installed on this machine')


async def test_cpp_reference_solution_passes(runner_root):
    require_language('cpp')
    question = BY_NUMBER[1]
    result = await code_runner.run_code({'questionId': question['id'], 'language': 'cpp',
                                         'code': question['solutions']['cpp']})
    assert result['supported'] is True and result['passed'] is True
    assert result['compiler']['name'] == 'g++'
    assert result['passedCases'] == result['totalCases'] == len(question['samples'])
    assert result['language'] == 'cpp'
    assert list(runner_root.iterdir()) == []


async def test_java_reference_solution_passes(runner_root):
    require_language('java')
    question = BY_NUMBER[1]
    result = await code_runner.run_code({'questionId': question['id'], 'language': 'java',
                                         'code': question['solutions']['java']})
    assert result['supported'] is True and result['passed'] is True
    assert result['compiler']['name'] == 'javac'
    assert list(runner_root.iterdir()) == []


async def test_compiled_tree_question_passes(runner_root):
    require_language('cpp')
    question = BY_NUMBER[94]  # 二叉树的中序遍历
    result = await code_runner.run_code({'questionId': question['id'], 'language': 'cpp',
                                         'code': question['solutions']['cpp']})
    assert result['supported'] is True and result['passed'] is True


async def test_compiled_mutation_question_passes(runner_root):
    require_language('cpp')
    question = BY_NUMBER[283]  # 移动零：返回 void，比较被修改的数组
    result = await code_runner.run_code({'questionId': question['id'], 'language': 'cpp',
                                         'code': question['solutions']['cpp']})
    assert result['supported'] is True and result['passed'] is True


async def test_compiled_compile_error_is_reported(runner_root):
    require_language('cpp')
    result = await code_runner.run_code({'questionId': BY_NUMBER[1]['id'], 'language': 'cpp',
                                         'code': 'class Solution { public: vector<int> twoSum(vector<int>& nums, int target) { this is not c++ } };'})
    assert result['supported'] is True and result['passed'] is False
    assert '编译' in (result['error'] or '')
    assert result['cases'] == []
    assert list(runner_root.iterdir()) == []


async def test_compiled_missing_toolchain_returns_unsupported(runner_root, monkeypatch):
    monkeypatch.setattr(judge_toolchain, 'detect', lambda force=False: {
        'capabilities': {'python': {'available': True}, 'cpp': {'available': False, 'reason': '未检测到 g++ 编译器。'},
                         'java': {'available': False, 'reason': '未检测到 javac/java。'}},
        'languages': ['python'],
    })
    result = await code_runner.run_code({'questionId': BY_NUMBER[1]['id'], 'language': 'cpp',
                                         'code': BY_NUMBER[1]['solutions']['cpp']})
    assert result['supported'] is False and '未检测到 g++' in result['reason']
