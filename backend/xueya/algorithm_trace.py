"""Algorithm demo trace provider (backward compatible, demo-2 schema).

The actual trace engine now lives in backend.xueya.algorithm_demo and covers all
100 Hot100 questions.  This module keeps the public trace(question_id,
sample_index) entry point used by GET /api/learning/space/algorithm-demo/{id}
and dispatches to the new engine, with two exceptions:

* h100-63 (#35 search-insert) and h100-53 (#200 islands) keep their original
  hand-written teaching traces because existing regression checks read their
  legacy step fields (left/right/mid and visited/stack/count/current).  The
  response is upgraded to demo-2: schemaVersion, topic, difficulty, viz, layout,
  meta, warnings and a per-step state snapshot are added while the legacy
  fields stay untouched.
* every other question is delegated to algorithm_demo.trace.

Design-class questions (146/155/208/295) are handled by the new engine too.
"""
from __future__ import annotations

import copy
import json
import re

from .common import require
from .practice_bank import question
from . import algorithm_demo

LEGACY_IDS = ('h100-63', 'h100-53')


def trace(question_id, sample_index=0):
    """Return a demo-2 trace for any traceable Hot100 question/sample."""
    if question_id in LEGACY_IDS:
        return _legacy_demo(question_id, sample_index)
    return algorithm_demo.trace(question_id, sample_index)


# ---------------------------------------------------------------------------
# Legacy hand-written traces (unchanged maths; demo-2 envelope added)
# ---------------------------------------------------------------------------


def _binary_search_trace(sample):
    match = re.fullmatch(r'nums\s*=\s*(\[.*\]),\s*target\s*=\s*(-?\d+)', sample['input'])
    require(match is not None, 'DEMO_SAMPLE_INVALID')
    nums, target = json.loads(match[1]), int(match[2])
    left, right = 0, len(nums)
    steps = []

    def save(line, note, mid=None):
        steps.append({'left': left, 'right': right, 'mid': mid, 'line': line, 'note': note})

    save(1, '初始化左闭右开区间 [left, right)')
    while left < right:
        mid = left + (right - left) // 2
        save(3, '中点 %d，比较 %d 与目标 %d' % (mid, nums[mid], target), mid)
        if nums[mid] < target:
            left = mid + 1
            save(5, '中点值小于目标，排除中点及其左侧')
        else:
            right = mid
            save(7, '中点值不小于目标，保留中点作为候选插入位置')
    save(8, '搜索结束，插入位置为 %d' % left)
    code = ['left, right = 0, len(nums)', 'while left < right:',
            '    mid = left + (right-left)//2', '    if nums[mid] < target:',
            '        left = mid + 1', '    else:', '        right = mid', 'return left']
    return {'inputs': {'nums': nums, 'target': target}, 'steps': steps,
            'code': code, 'result': left, 'viz': 'array',
            'pointers': ['left', 'right', 'mid']}


def _islands_trace(sample):
    require(sample['input'].startswith('grid = '), 'DEMO_SAMPLE_INVALID')
    grid = json.loads(sample['input'].split('=', 1)[1])
    visited, stack, count = [], [], 0
    steps = []

    def save(line, note, current=None):
        steps.append(copy.deepcopy({'line': line, 'note': note, 'visited': visited,
                                    'stack': stack, 'count': count, 'current': current}))

    def visit(r, c):
        if not (0 <= r < len(grid) and 0 <= c < len(grid[0])) or grid[r][c] != '1' or [r, c] in visited:
            return
        stack.append([r, c])
        visited.append([r, c])
        save(3, '深入访问 (%d, %d)' % (r, c), [r, c])
        for dr, dc in ((-1, 0), (0, 1), (1, 0), (0, -1)):
            visit(r + dr, c + dc)
        stack.pop()
        save(6, '回溯：(%d, %d) 的四邻域已处理' % (r, c), stack[-1] if stack else None)

    save(1, '陆地只按上、右、下、左四方向连接；对角线不相连')
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value == '1' and [r, c] not in visited:
                count += 1
                save(8, '发现第 %d 座岛屿' % count, [r, c])
                visit(r, c)
    result = count
    save(9, '遍历完成，共 %d 座岛屿' % count)
    code = ['visited, count = set(), 0', 'def dfs(r, c):', '    visited.add((r, c))',
            '    for next in four_neighbors(r, c):',
            '        if unvisited_land(next): dfs(*next)', '    return  # 回溯',
            'for cell in grid:', '    if unvisited_land(cell): count += 1; dfs(*cell)',
            'return count']
    return {'inputs': {'grid': grid}, 'steps': steps, 'code': code,
            'result': result, 'viz': 'grid', 'pointers': ['current']}


def _decorate_steps(steps, base_state, track):
    """Add demo-2 state/highlight to legacy steps without touching old fields."""
    previous = {}
    for step in steps:
        state = dict(base_state)
        for name in track:
            state[name] = step.get(name)
        current = {name: json.dumps(value, ensure_ascii=False, sort_keys=True)
                   for name, value in state.items()}
        changed = [name for name, value in current.items() if previous.get(name) != value]
        step['state'] = copy.deepcopy(state)
        step['highlight'] = changed[:6]
        previous = current


def _legacy_demo(question_id, sample_index):
    q = question(question_id)
    require(q is not None and q.get('category') == 'hot100', 'DEMO_NOT_AVAILABLE')
    require(type(sample_index) is int and 0 <= sample_index < len(q['samples']),
            'DEMO_SAMPLE_NOT_FOUND')
    sample = q['samples'][sample_index]
    if question_id == 'h100-63':
        demo = _binary_search_trace(sample)
        base_state = {'nums': demo['inputs']['nums'], 'target': demo['inputs']['target']}
        _decorate_steps(demo['steps'], base_state, ('left', 'right', 'mid'))
    else:
        demo = _islands_trace(sample)
        base_state = {'grid': demo['inputs']['grid']}
        _decorate_steps(demo['steps'], base_state, ('visited', 'stack', 'count', 'current'))
    require(str(demo['result']) == sample['output'].strip(), 'DEMO_RESULT_MISMATCH')
    return {
        'schemaVersion': algorithm_demo.SCHEMA_VERSION,
        'questionId': q['id'],
        'title': q['title'],
        'number': q.get('leetcodeNumber'),
        'topic': q.get('topic'),
        'difficulty': q.get('difficulty'),
        'sample': {'input': sample.get('input', ''), 'output': sample.get('output', '')},
        'sampleIndex': sample_index,
        'sampleCount': len(q['samples']),
        'inputs': demo['inputs'],
        'code': demo['code'],
        'codeLanguage': 'python',
        'viz': demo['viz'],
        'layout': algorithm_demo._layout(demo['viz'], demo['pointers']),
        'steps': demo['steps'],
        'result': demo['result'],
        'meta': algorithm_demo._meta(q),
        'warnings': ['本题保留旧版手写教学轨迹（兼容既有回归检查），并为每一步补充 demo-2 的 state 快照。'],
    }


__all__ = ['trace', 'LEGACY_IDS']
