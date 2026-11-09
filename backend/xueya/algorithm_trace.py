"""Deterministic teaching traces from the two actual Hot100 examples."""
import copy
import json
import re
from .common import require
from .practice_bank import question


def trace(question_id, sample_index=0):
    require(question_id in ('h100-63', 'h100-53'), 'DEMO_NOT_AVAILABLE')
    q = question(question_id)
    require(q and 0 <= sample_index < len(q.get('samples', [])), 'DEMO_SAMPLE_NOT_FOUND')
    sample = q['samples'][sample_index]
    steps = []
    if question_id == 'h100-63':
        match = re.fullmatch(r'nums\s*=\s*(\[.*\]),\s*target\s*=\s*(-?\d+)', sample['input'])
        require(match is not None, 'DEMO_SAMPLE_INVALID')
        nums, target = json.loads(match[1]), int(match[2])
        left, right = 0, len(nums)
        def save(line, note, mid=None):
            steps.append({'left': left, 'right': right, 'mid': mid, 'line': line, 'note': note})
        save(1, '初始化左闭右开区间 [left, right)')
        while left < right:
            mid = left + (right-left)//2
            save(3, f'中点 {mid}，比较 {nums[mid]} 与目标 {target}', mid)
            if nums[mid] < target:
                left = mid+1
                save(5, '中点值小于目标，排除中点及其左侧')
            else:
                right = mid
                save(7, '中点值不小于目标，保留中点作为候选插入位置')
        save(8, f'搜索结束，插入位置为 {left}')
        result = left
        inputs = {'nums': nums, 'target': target}
        code = ['left, right = 0, len(nums)', 'while left < right:', '    mid = left + (right-left)//2', '    if nums[mid] < target:', '        left = mid + 1', '    else:', '        right = mid', 'return left']
    else:
        require(sample['input'].startswith('grid = '), 'DEMO_SAMPLE_INVALID')
        grid = json.loads(sample['input'].split('=', 1)[1])
        visited, stack, count = [], [], 0
        def save(line, note, current=None):
            steps.append(copy.deepcopy({'line': line, 'note': note, 'visited': visited, 'stack': stack, 'count': count, 'current': current}))
        def visit(r, c):
            if not (0 <= r < len(grid) and 0 <= c < len(grid[0])) or grid[r][c] != '1' or [r, c] in visited:
                return
            stack.append([r,c]); visited.append([r,c]); save(3, f'深入访问 ({r}, {c})', [r,c])
            for dr, dc in ((-1,0),(0,1),(1,0),(0,-1)):
                visit(r+dr,c+dc)
            stack.pop(); save(6, f'回溯：({r}, {c}) 的四邻域已处理', stack[-1] if stack else None)
        save(1, '陆地只按上、右、下、左四方向连接；对角线不相连')
        for r, row in enumerate(grid):
            for c, value in enumerate(row):
                if value == '1' and [r,c] not in visited:
                    count += 1; save(8, f'发现第 {count} 座岛屿', [r,c]); visit(r,c)
        result = count; save(9, f'遍历完成，共 {count} 座岛屿')
        inputs = {'grid': grid}
        code = ['visited, count = set(), 0', 'def dfs(r, c):', '    visited.add((r, c))', '    for next in four_neighbors(r, c):', '        if unvisited_land(next): dfs(*next)', '    return  # 回溯', 'for cell in grid:', '    if unvisited_land(cell): count += 1; dfs(*cell)', 'return count']
    require(str(result) == sample['output'].strip(), 'DEMO_RESULT_MISMATCH')
    return {'questionId': q['id'], 'title': q['title'], 'number': q['leetcodeNumber'],
            'sample': sample, 'sampleIndex': sample_index, 'sampleCount': len(q['samples']),
            'inputs': inputs, 'steps': steps, 'code': code, 'result': result}
