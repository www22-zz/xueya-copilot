"""Tests for the real, verified Hot100 algorithm demo trace engine (demo-2).

Every assertion is backed by data: the engine executes the official Python
reference solution in a child process, records the executed lines/locals and
only returns a trace when the observed result equals the bank sample output.
These tests re-check that result independently from the trace payload.

Default (fast) run: one sample per question, ~100 child-process traces.
Exhaustive run (all questions x all samples, writes the coverage artifact):

    XUEYA_ALGO_DEMO_FULL=1 python -m pytest tests_python/test_algorithm_demo.py -q
    python tests_python/test_algorithm_demo.py

The coverage file test-results/algorithm-demo-coverage.json distinguishes
question-level and sample-level success and records real failure reasons.
"""
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.xueya import algorithm_demo, code_runner  # noqa: E402
from backend.xueya.common import AppError  # noqa: E402
from backend.xueya.practice_bank import questions  # noqa: E402
from backend.xueya.algorithm_trace import trace as compatibility_trace  # noqa: E402

HOT = [q for q in questions() if q.get('category') == 'hot100']
HOT_BY_ID = {q['id']: q for q in HOT}
FULL = os.environ.get('XUEYA_ALGO_DEMO_FULL') == '1'
COVERAGE = ROOT / 'test-results' / 'algorithm-demo-coverage.json'
REQUIRED_FIELDS = (
    'schemaVersion', 'questionId', 'title', 'number', 'topic', 'difficulty',
    'sample', 'sampleIndex', 'sampleCount', 'inputs', 'code', 'codeLanguage',
    'viz', 'layout', 'steps', 'result', 'meta', 'warnings',
)
VIZES = {
    'array', 'matrix', 'grid', 'tree', 'linked-list', 'graph', 'dp', 'string',
    'stack-queue', 'backtracking', 'design', 'scalar',
}
REPRESENTATIVE = {
    'array': 'h100-01',
    'string': 'h100-08',
    'grid': 'h100-53',
    'graph': 'h100-55',
    'tree': 'h100-42',
    'linked-list': 'h100-32',
    'matrix': 'h100-26',
    'dp': 'h100-81',
    'stack-queue': 'h100-67',
    'backtracking': 'h100-56',
    'design': 'h100-38',
}


@pytest.fixture(autouse=True, scope='module')
def demo_workspace():
    """Workspace-local temp root: system temp may be locked down on Windows."""
    path = ROOT / 'test-results' / 'algorithm-demo-tests'
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    original = algorithm_demo.WORK_ROOT
    algorithm_demo.WORK_ROOT = str(path)
    yield path
    algorithm_demo.WORK_ROOT = original
    shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# Independent expected-output helpers (do not reuse the engine's own check)
# ---------------------------------------------------------------------------


def documented_design_expected(q, sample):
    """Parse the documented query return values from the sample output text."""
    number = q.get('leetcodeNumber')
    text = sample['output'].strip()
    if number == 208:
        return json.loads(text.lower())
    if number == 295:
        return [float(item) for item in re.findall(r'-?\d+(?:\.\d+)?', text)]
    if number == 146:
        return [int(item) for item in re.findall(r'-?\d+', text)]
    if number == 155:
        return [int(item) for item in re.findall(r'返回\s*(-?\d+)', text)]
    raise AssertionError('unexpected design question %r' % number)


def planned_case(q, sample_index):
    plan = code_runner._build_plan(q, q['solutions']['python'])
    assert not plan.get('unsupported'), plan.get('reason')
    return plan['cases'][sample_index]


def assert_demo_result_matches_sample(demo, q, sample_index):
    assert demo['result'] == demo.get('result')
    number = q.get('leetcodeNumber')
    if number in algorithm_demo.DESIGN_NUMBERS:
        expected = documented_design_expected(q, q['samples'][sample_index])
        assert code_runner._equal(expected, demo['result']), (expected, demo['result'])
        return
    case = planned_case(q, sample_index)
    mode = case.get('mode', 'literal')
    if mode in ('cycle-index', 'intersection'):
        assert demo['result'] == case.get('expected'), (demo['result'], case.get('expected'))
        return
    expected, actual = case.get('expected'), demo['result']
    compare = case.get('compare', 'exact')
    if compare != 'exact':
        assert code_runner._equal(code_runner._canonical(expected, compare),
                                  code_runner._canonical(actual, compare))
    else:
        assert code_runner._equal(expected, actual), (expected, actual)


# ---------------------------------------------------------------------------
# Plumbing helpers
# ---------------------------------------------------------------------------


def assert_json_safe(value, path='state'):
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, list):
        for item in value:
            assert_json_safe(item, path)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str), (path, key)
            assert_json_safe(item, path + '.' + key)
        return
    raise AssertionError('non JSON-safe value at %s: %r' % (path, type(value).__name__))


def assert_schema(demo, q, sample_index):
    for field in REQUIRED_FIELDS:
        assert field in demo, field
    assert demo['schemaVersion'] == 'demo-2'
    assert demo['questionId'] == q['id']
    assert demo['title'] == q['title']
    assert demo['number'] == q.get('leetcodeNumber')
    assert demo['topic'] == q.get('topic')
    assert demo['sampleIndex'] == sample_index
    assert demo['sampleCount'] == len(q['samples'])
    assert demo['sample']['input'] == q['samples'][sample_index]['input']
    assert demo['codeLanguage'] == 'python'
    assert isinstance(demo['code'], list) and demo['code']
    assert demo['viz'] in VIZES
    assert isinstance(demo['layout'], dict)
    assert demo['layout'].get('primary') == demo['viz']
    assert isinstance(demo['layout'].get('pointers'), list)
    assert all(isinstance(name, str) for name in demo['layout']['pointers'])
    assert isinstance(demo['layout'].get('legend'), list)
    assert all(isinstance(item, str) for item in demo['layout']['legend'])
    assert isinstance(demo['steps'], list) and demo['steps']
    assert len(demo['steps']) <= algorithm_demo.MAX_STEPS
    for step in demo['steps']:
        assert isinstance(step['line'], int) and step['line'] >= 0
        assert isinstance(step['note'], str) and step['note']
        assert 0 < len(step['note']) <= 600, len(step['note'])
        assert isinstance(step['highlight'], list)
        assert_json_safe(step['state'])
        assert len(json.dumps(step['state'], ensure_ascii=False)) <= 24000
    assert len(json.dumps(demo, ensure_ascii=False)) <= 1200000
    assert isinstance(demo['warnings'], list)
    assert isinstance(demo['meta'], dict)
    for key in ('coreIdea', 'hints', 'complexity'):
        assert key in demo['meta']
    assert_json_safe(demo['inputs'])
    assert_json_safe(demo['result'])


# ---------------------------------------------------------------------------
# Structural coverage
# ---------------------------------------------------------------------------


def test_supported_questions_cover_all_hot100():
    assert len(HOT) == 100
    assert set(algorithm_demo.supported_ids()) == set(HOT_BY_ID)
    assert algorithm_demo._is_design(HOT_BY_ID['h100-38'])
    assert algorithm_demo._is_design(HOT_BY_ID['h100-68'])


def test_representative_trace_per_visualisation():
    for viz, question_id in REPRESENTATIVE.items():
        q = HOT_BY_ID[question_id]
        demo = algorithm_demo.trace(question_id, 0)
        assert demo['viz'] == viz, (question_id, demo['viz'], viz)
        assert_schema(demo, q, 0)
        assert_demo_result_matches_sample(demo, q, 0)


# ---------------------------------------------------------------------------
# The real sweep: every question, first sample (fast default)
# ---------------------------------------------------------------------------


def test_every_question_first_sample_trace_verifies():
    started = time.time()
    failures = []
    for q in HOT:
        result = algorithm_demo.probe(q['id'], 0)
        if not result['ok']:
            failures.append((q['id'], result['error'], result.get('detail', '')))
            continue
        demo = result['demo']
        try:
            assert_schema(demo, q, 0)
            assert_demo_result_matches_sample(demo, q, 0)
        except AssertionError as error:
            failures.append((q['id'], 'ASSERT', str(error)[:300]))
    assert not failures, failures[:5]
    elapsed = time.time() - started
    assert elapsed < 180, 'first-sample sweep took %.1fs' % elapsed


# ---------------------------------------------------------------------------
# Special structures / design class / legacy compatibility
# ---------------------------------------------------------------------------


def test_design_class_operation_traces():
    for number in sorted(algorithm_demo.DESIGN_NUMBERS):
        q = next(item for item in HOT if item.get('leetcodeNumber') == number)
        for index in range(len(q['samples'])):
            demo = algorithm_demo.trace(q['id'], index)
            assert demo['viz'] == 'design'
            operations = demo['inputs'].get('operations')
            assert isinstance(operations, list) and operations
            assert len(demo['steps']) == len(operations)
            for step, operation in zip(demo['steps'], operations):
                assert step['state']['operation'].startswith(operation['method'] + '(')
                assert 'returned' in step['state']
            assert len(demo['result']) == len([op for op in operations
                                               if op['method'] not in ('push', 'pop', 'put', 'insert', 'addNum')])
            assert_demo_result_matches_sample(demo, q, index)


def test_special_linked_structures_validate():
    expectations = {
        'h100-31': 'intersection',
        'h100-34': 'cycle',
        'lc-141': 'cycle',
        'lc-138': 'random',
        'h100-48': 'tree-ref',
        'lc-114': 'mutate-tree',
    }
    for question_id, kind in expectations.items():
        q = HOT_BY_ID[question_id]
        for index in range(len(q['samples'])):
            demo = algorithm_demo.trace(question_id, index)
            assert demo['viz'] in ('linked-list', 'tree'), (question_id, demo['viz'])
            assert_demo_result_matches_sample(demo, q, index)


def test_legacy_questions_keep_old_fields_and_demo2_envelope():
    for question_id in ('h100-63', 'h100-53'):
        q = HOT_BY_ID[question_id]
        for index in range(len(q['samples'])):
            demo = compatibility_trace(question_id, index)
            assert demo['schemaVersion'] == 'demo-2'
            assert demo['result'] == int(q['samples'][index]['output'].strip())
            for step in demo['steps']:
                assert 'state' in step and isinstance(step['state'], dict)
                assert 'note' in step and isinstance(step['line'], int)
            if question_id == 'h100-63':
                assert all('left' in step and 'right' in step for step in demo['steps'])
                assert all(step['left'] <= step['right'] for step in demo['steps'])
                assert demo['steps'][-1]['left'] == demo['result']
            else:
                assert any('回溯' in step['note'] for step in demo['steps'])
                assert demo['steps'][-1]['stack'] == []
                for step in demo['steps']:
                    for left, right in zip(step['stack'], step['stack'][1:]):
                        assert abs(left[0] - right[0]) + abs(left[1] - right[1]) == 1


def test_unknown_and_invalid_requests_return_demo_errors():
    with pytest.raises(AppError) as info:
        algorithm_demo.trace('h100-does-not-exist')
    assert info.value.code == 'DEMO_NOT_AVAILABLE'
    basic_id = next(q['id'] for q in questions() if q.get('category') == 'basic')
    with pytest.raises(AppError) as info:
        algorithm_demo.trace(basic_id)
    assert info.value.code == 'DEMO_NOT_AVAILABLE'
    with pytest.raises(AppError) as info:
        algorithm_demo.trace('h100-01', 999)
    assert info.value.code == 'DEMO_SAMPLE_NOT_FOUND'
    with pytest.raises(AppError) as info:
        algorithm_demo.trace('h100-01', -1)
    assert info.value.code == 'DEMO_SAMPLE_NOT_FOUND'
    assert algorithm_demo.probe('h100-01', 999)['ok'] is False


def test_state_is_a_full_snapshot_not_incremental():
    demo = algorithm_demo.trace('h100-01', 0)
    for step in demo['steps']:
        assert step['state'].get('nums') == [2, 7, 11, 15]
        assert step['state'].get('target') == 9


def test_step_selection_caps_long_traces_and_keeps_edges():
    code = ['line one', 'line two', 'line three']
    raw = [{'line': (offset % 3) + 1, 'depth': 0,
            'state': {'i': offset}} for offset in range(1200)]
    annotated = algorithm_demo._annotate(raw)
    selected, sampled = algorithm_demo._select_steps(annotated)
    assert sampled is True
    assert len(selected) <= algorithm_demo.MAX_STEPS
    assert selected[0]['index'] == 0
    assert selected[-1]['index'] == len(raw) - 1
    assert [item['index'] for item in selected] == sorted(item['index'] for item in selected)
    steps = algorithm_demo._build_notes(selected, code)
    assert len(steps) == len(selected)
    assert all('执行第' in step['note'] for step in steps)


def test_available_ids_only_lists_verified_demos():
    ids = algorithm_demo.available_ids()
    assert len(ids) == 100
    assert set(ids) == set(HOT_BY_ID)
    rows = algorithm_demo.describe_all(verify=False)
    assert len(rows) == 100
    assert all(row['id'] in HOT_BY_ID for row in rows)


def test_wrong_result_is_reported_not_faked(monkeypatch):
    original = algorithm_demo._execute

    def broken(payload):
        executed = original(payload)
        if payload.get('mode') == 'solve':
            executed['actual'] = ['伪造错误结果']
        return executed

    monkeypatch.setattr(algorithm_demo, '_execute', broken)
    algorithm_demo.clear_cache()
    with pytest.raises(AppError) as info:
        algorithm_demo.trace('h100-01', 0)
    assert info.value.code == 'DEMO_RESULT_MISMATCH'
    monkeypatch.undo()
    algorithm_demo.clear_cache()
    demo = algorithm_demo.trace('h100-01', 0)
    assert demo['result'] == [0, 1]


def test_trace_is_cached_per_question_sample_and_code_hash():
    algorithm_demo.clear_cache()
    first = algorithm_demo.trace('h100-01', 0)
    second = algorithm_demo.trace('h100-01', 0)
    assert first is second
    other_sample = algorithm_demo.trace('h100-01', 1)
    assert other_sample is not first and other_sample['sampleIndex'] == 1
    algorithm_demo.clear_cache()
    rebuilt = algorithm_demo.trace('h100-01', 0)
    assert rebuilt is not first
    assert rebuilt['steps'] == first['steps']


# ---------------------------------------------------------------------------
# Exhaustive sweep (gated; also writes the coverage artifact)
# ---------------------------------------------------------------------------


def run_coverage():
    """Trace every question x every sample; write test-results coverage JSON."""
    started = time.time()
    rows, failures = [], []
    for q in HOT:
        sample_rows = []
        for index in range(len(q['samples'])):
            result = algorithm_demo.probe(q['id'], index)
            if result['ok']:
                demo = result['demo']
                try:
                    assert_schema(demo, q, index)
                    assert_demo_result_matches_sample(demo, q, index)
                except AssertionError as error:
                    detail = str(error)[:400]
                    sample_rows.append({'sampleIndex': index, 'ok': False,
                                        'error': 'DEMO_TRACE_ASSERTION_FAILED', 'detail': detail})
                    failures.append({'questionId': q['id'], 'number': q.get('leetcodeNumber'),
                                     'title': q['title'], 'sampleIndex': index,
                                     'error': 'DEMO_TRACE_ASSERTION_FAILED', 'detail': detail})
                    continue
                sample_rows.append({'sampleIndex': index, 'ok': True,
                                    'steps': len(demo['steps']), 'viz': demo['viz']})
            else:
                detail = str(result.get('detail', ''))[:500]
                sample_rows.append({'sampleIndex': index, 'ok': False,
                                    'error': result['error'], 'detail': detail})
                failures.append({'questionId': q['id'], 'number': q.get('leetcodeNumber'),
                                 'title': q['title'], 'sampleIndex': index,
                                 'error': result['error'], 'detail': detail})
        rows.append({'questionId': q['id'], 'number': q.get('leetcodeNumber'),
                     'title': q['title'], 'topic': q.get('topic'),
                     'difficulty': q.get('difficulty'),
                     'design': algorithm_demo._is_design(q),
                     'ok': all(item['ok'] for item in sample_rows),
                     'samples': sample_rows})
    elapsed = round(time.time() - started, 1)
    summary = {
        'schemaVersion': 'demo-2',
        'engine': 'backend/xueya/algorithm_demo.py',
        'generatedAt': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'totalQuestions': len(HOT),
        'totalSamples': sum(len(q['samples']) for q in HOT),
        'okQuestions': sum(1 for row in rows if row['ok']),
        'failedQuestions': sum(1 for row in rows if not row['ok']),
        'okSamples': sum(1 for row in rows for item in row['samples'] if item['ok']),
        'failedSamples': len(failures),
        'durationSeconds': elapsed,
    }
    COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE.write_text(json.dumps({'summary': summary, 'failures': failures,
                                    'questions': rows}, ensure_ascii=False, indent=1),
                        encoding='utf-8')
    return summary


@pytest.mark.skipif(not FULL, reason='set XUEYA_ALGO_DEMO_FULL=1 for the exhaustive sweep')
def test_all_samples_trace_verifies():
    summary = run_coverage()
    assert summary['failedSamples'] == 0, summary
    assert summary['okQuestions'] == summary['totalQuestions'] == 100
    assert summary['okSamples'] == summary['totalSamples'] == 213


if __name__ == '__main__':
    summary = run_coverage()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if summary['failedSamples'] == 0 and summary['okQuestions'] == 100 else 1)
