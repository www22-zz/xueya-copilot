"""Verified algorithm execution demos for every Hot100 question (demo-2 schema).

The demo endpoint GET /api/learning/space/algorithm-demo/{question_id}?sample=N
used to serve two hand-written traces (h100-63 / h100-53).  This module replaces
that with a general, honest engine:

* the question's official Python reference solution runs in a throw-away
  subprocess (-I -B, minimal environment, hard timeout, bounded files);
* sys.settrace records only frames whose code filename is '<solution>', so every
  step is a real executed line of the reference code with a JSON-safe snapshot of
  the local variables at that moment;
* after the run the observed return value (including LeetCode "mutate the input
  in place and return None" semantics, cycle-index, intersection and node
  serialisation rules) is compared with the sample's expected output using the
  same rules as backend.xueya.code_runner; a mismatch raises
  DEMO_RESULT_MISMATCH instead of inventing steps;
* the four design-class questions (146 LRU, 155 MinStack, 208 Trie, 295
  MedianFinder) are traced operation by operation against the official class,
  using the operation sequence written in the sample input;
* traces are cached per (questionId, sampleIndex, codeHash) in an in-memory LRU,
  capped at ~320 steps with the first/last and the most significant changes kept.

Schema contract (AGENT_PLAN section 2.1, demo-2):

    {"schemaVersion": "demo-2", "questionId": ..., "title": ..., "number": ...,
     "topic": ..., "difficulty": ..., "sample": {...}, "sampleIndex": ...,
     "sampleCount": ..., "inputs": {...}, "code": [...], "codeLanguage": "python",
     "viz": "array|matrix|grid|tree|linked-list|graph|dp|string|stack-queue|
             backtracking|design|scalar",
     "layout": {"primary": ..., "pointers": [...], "legend": [...]},
     "steps": [{"line": 1, "note": "...", "state": {...}, "highlight": [...]}],
     "result": ..., "meta": {"coreIdea": ..., "hints": [...], "complexity": {...}},
     "warnings": [...]}

Run available_ids() for the registry and trace(question_id, sample_index) for the
endpoint.  probe() / probe_detail() are the coverage/test helpers returning the
real failure reason instead of raising.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import OrderedDict
from pathlib import Path

from .common import AppError, require
from .practice_bank import question
from . import code_runner

SCHEMA_VERSION = 'demo-2'
MAX_STEPS = 320
EVENT_LIMIT = 8000
RUN_TIMEOUT_MS = 10000
MAX_RESULT_BYTES = 4 * 1024 * 1024
DESIGN_NUMBERS = frozenset((146, 155, 208, 295))

# Optional workspace-local temp root for locked-down hosts and tests.  Mirrors
# code_runner.WORK_ROOT so one monkeypatch/fixture controls both.
WORK_ROOT: str | None = os.environ.get('XUEYA_ALGO_DEMO_TMP') or None

_CACHE: 'OrderedDict[tuple, dict]' = OrderedDict()
_CACHE_MAX = 128


class _TraceFailure(Exception):
    """Internal failure carrying both the public DEMO_* code and a detail."""

    def __init__(self, code: str, detail: str = ''):
        super().__init__(code if not detail else code + ': ' + detail)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Child process driver (executed in a separate interpreter; self-contained)
# ---------------------------------------------------------------------------

_DRIVER_SOURCE = r'''"""Generated per-run Hot100 algorithm-demo driver (separate interpreter)."""
import json
import os
import sys
import time
import traceback
import types
from collections import deque, OrderedDict

BASE = os.path.dirname(os.path.abspath(__file__))
SOLUTION_FILE = '<solution>'
EVENT_LIMIT = 8000
EVENT_BYTES = 2500000
DEPTH_LIMIT = 8
LIST_LIMIT = 200
DICT_LIMIT = 200
STR_LIMIT = 240


class _Sink:
    def write(self, value):
        return len(str(value))

    def flush(self):
        return None

    def isatty(self):
        return False

    @property
    def encoding(self):
        return 'utf-8'


OUT, ERR = _Sink(), _Sink()


class ListNode:
    def __init__(self, val=0, next=None):
        self.val, self.next = val, next


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val, self.left, self.right = val, left, right


class Node:
    def __init__(self, val=0, next=None, random=None):
        self.val, self.next, self.random = val, next, random


def chain(values):
    head = None
    for value in reversed(values):
        head = ListNode(value, head)
    return head


def tree_from_list(values):
    if not values or values[0] is None:
        return None
    root = TreeNode(values[0])
    queue = deque([root])
    index = 1
    while queue and index < len(values):
        node = queue.popleft()
        if index < len(values):
            value = values[index]
            index += 1
            if value is not None:
                node.left = TreeNode(value)
                queue.append(node.left)
        if index < len(values):
            value = values[index]
            index += 1
            if value is not None:
                node.right = TreeNode(value)
                queue.append(node.right)
    return root


def find_tree_node(root, value):
    queue = deque([root])
    seen = 0
    while queue:
        node = queue.popleft()
        if node is None:
            continue
        seen += 1
        if seen > 20000:
            break
        if getattr(node, 'val', None) == value:
            return node
        queue.append(getattr(node, 'left', None))
        queue.append(getattr(node, 'right', None))
    return None


def cycle_head(values, pos):
    nodes = [ListNode(value) for value in values]
    for left, right in zip(nodes, nodes[1:]):
        left.next = right
    if nodes and type(pos) is int and 0 <= pos < len(nodes):
        nodes[-1].next = nodes[pos]
    return (nodes[0] if nodes else None), nodes


def intersection_build(values_a, values_b, skip_a, skip_b):
    if (type(skip_a) is int and type(skip_b) is int and 0 <= skip_a < len(values_a)
            and 0 <= skip_b < len(values_b) and values_a[skip_a:] == values_b[skip_b:]):
        shared = chain(values_a[skip_a:])
        head_a = chain(values_a[:skip_a])
        head_b = chain(values_b[:skip_b])
        if head_a is None:
            head_a = shared
        else:
            tail = head_a
            while tail.next:
                tail = tail.next
            tail.next = shared
        if head_b is None:
            head_b = shared
        else:
            tail = head_b
            while tail.next:
                tail = tail.next
            tail.next = shared
        return head_a, head_b, shared
    return chain(values_a), chain(values_b), None


def random_list(values):
    nodes = [Node(item[0] if isinstance(item, (list, tuple)) else item) for item in values]
    for left, right in zip(nodes, nodes[1:]):
        left.next = right
    for node, item in zip(nodes, values):
        raw = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else None
        if type(raw) is int and 0 <= raw < len(nodes):
            node.random = nodes[raw]
    return (nodes[0] if nodes else None)


def level_order(root):
    if root is None:
        return []
    result = []
    queue = deque([root])
    seen = 0
    while queue:
        node = queue.popleft()
        seen += 1
        if seen > 20000:
            raise ValueError('返回的树节点过多或存在环')
        if node is None:
            result.append(None)
            continue
        result.append(getattr(node, 'val', None))
        queue.append(getattr(node, 'left', None))
        queue.append(getattr(node, 'right', None))
    while result and result[-1] is None:
        result.pop()
    return result


def linked_values(head):
    result = []
    seen = set()
    while head is not None:
        if id(head) in seen:
            raise ValueError('返回的链表存在环，无法序列化')
        seen.add(id(head))
        result.append(getattr(head, 'val', None))
        head = getattr(head, 'next', None)
        if len(result) > 20000:
            raise ValueError('返回的链表过长')
    return result


def random_values(head):
    nodes, seen = [], set()
    while head is not None:
        if id(head) in seen:
            raise ValueError('返回的链表存在环，无法序列化')
        seen.add(id(head))
        nodes.append(head)
        head = getattr(head, 'next', None)
        if len(nodes) > 20000:
            raise ValueError('返回的链表过长')
    index = {id(node): position for position, node in enumerate(nodes)}
    result = []
    for node in nodes:
        target = getattr(node, 'random', None)
        result.append([getattr(node, 'val', None), index.get(id(target)) if target is not None else None])
    return result


def sanitize(value):
    if isinstance(value, float) and (value != value or value in (float('inf'), float('-inf'))):
        return str(value)
    return value


def serialize(value, scalar_node=False):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return sanitize(value)
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize(item) for key, item in value.items()}
    if hasattr(value, 'random') and hasattr(value, 'next'):
        return random_values(value)
    if hasattr(value, 'left') or hasattr(value, 'right'):
        return getattr(value, 'val', None) if scalar_node else level_order(value)
    if hasattr(value, 'next') and hasattr(value, 'val'):
        return linked_values(value)
    if hasattr(value, 'val'):
        return serialize(getattr(value, 'val', None))
    return {'__unserializable__': type(value).__name__}


def format_error(error):
    text = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if len(lines) > 18:
        lines = lines[:6] + ['…'] + lines[-8:]
    return '\n'.join(lines)[-4000:]


# ---------------------------------------------------------------------------
# JSON-safe local-state snapshots (bounded depth/length, stable ordering)
# ---------------------------------------------------------------------------

class _Skip:
    pass


SKIP = _Skip()


def snapshot_linked(head):
    values, seen, node, cycle = [], set(), head, False
    while node is not None:
        if id(node) in seen:
            cycle = True
            break
        seen.add(id(node))
        values.append(getattr(node, 'val', None))
        node = getattr(node, 'next', None)
        if len(values) >= LIST_LIMIT:
            break
    return {'__type__': 'ListNode', 'values': values, 'cycle': cycle}


def snapshot_random(head):
    nodes, seen, node, cycle = [], set(), head, False
    while node is not None:
        if id(node) in seen:
            cycle = True
            break
        seen.add(id(node))
        nodes.append(node)
        node = getattr(node, 'next', None)
        if len(nodes) >= LIST_LIMIT:
            break
    index = {id(item): position for position, item in enumerate(nodes)}
    values = []
    for item in nodes:
        target = getattr(item, 'random', None)
        values.append([getattr(item, 'val', None),
                       index.get(id(target)) if target is not None else None])
    return {'__type__': 'Node', 'values': values, 'cycle': cycle}


def snapshot_tree(root):
    if root is None:
        return None
    result = []
    queue = deque([root])
    seen = 0
    while queue:
        node = queue.popleft()
        seen += 1
        if seen > 20000:
            break
        if node is None:
            result.append(None)
            continue
        result.append(getattr(node, 'val', None))
        if len(result) >= LIST_LIMIT:
            result.append('…')
            break
        queue.append(getattr(node, 'left', None))
        queue.append(getattr(node, 'right', None))
    while result and result[-1] is None:
        result.pop()
    return {'__type__': 'TreeNode', 'values': result}


def snapshot(value, depth=0):
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and len(value) > STR_LIMIT:
            return value[:STR_LIMIT] + '…'
        return value
    if isinstance(value, float):
        return sanitize(value)
    if depth >= DEPTH_LIMIT:
        return '…'
    if isinstance(value, OrderedDict):
        items = list(value.items())[:DICT_LIMIT]
        pairs = []
        for key, item in items:
            plain_key = key if isinstance(key, (str, int, float, bool)) or key is None else str(key)
            pairs.append([plain_key, snapshot(item, depth + 1)])
        return pairs
    if isinstance(value, deque):
        items = [snapshot(item, depth + 1) for item in list(value)[:LIST_LIMIT]]
        if len(value) > LIST_LIMIT:
            items.append('…共 %d 项' % len(value))
        return items
    if isinstance(value, (list, tuple)):
        items = [snapshot(item, depth + 1) for item in list(value)[:LIST_LIMIT]]
        if len(value) > LIST_LIMIT:
            items.append('…共 %d 项' % len(value))
        return items
    if isinstance(value, dict):
        try:
            keys = sorted(value.keys(), key=lambda key: str(key))
        except Exception:
            keys = list(value.keys())
        keys = keys[:DICT_LIMIT]
        result = {}
        for key in keys:
            try:
                result[str(key)] = snapshot(value[key], depth + 1)
            except Exception:
                result[str(key)] = '<无法读取>'
        if len(value) > DICT_LIMIT:
            result['…'] = '共 %d 项' % len(value)
        return result
    if isinstance(value, (set, frozenset)):
        try:
            items = sorted(value)
        except TypeError:
            try:
                items = sorted(value, key=lambda item: repr(item))
            except Exception:
                items = list(value)
        listed = [snapshot(item, depth + 1) for item in items[:LIST_LIMIT]]
        if len(value) > LIST_LIMIT:
            listed.append('…共 %d 项' % len(value))
        return listed
    if isinstance(value, types.ModuleType) or isinstance(value, type):
        return SKIP
    if isinstance(value, (types.FunctionType, types.BuiltinFunctionType, types.MethodType)):
        return SKIP
    if isinstance(value, Node):
        return snapshot_random(value)
    if isinstance(value, TreeNode):
        return snapshot_tree(value)
    if isinstance(value, ListNode):
        return snapshot_linked(value)
    try:
        attributes = vars(value)
    except TypeError:
        return '<%s>' % type(value).__name__
    result = {'__type__': type(value).__name__}
    for name, item in list(attributes.items())[:30]:
        if str(name).startswith('__'):
            continue
        try:
            result[str(name)] = snapshot(item, depth + 1)
        except Exception:
            result[str(name)] = '<无法读取>'
    return result


def snapshot_instance(instance):
    try:
        attributes = vars(instance)
    except TypeError:
        return {}
    result = {}
    for name in sorted(attributes.keys()):
        if str(name).startswith('__'):
            continue
        try:
            result[str(name)] = snapshot(attributes[name], 1)
        except Exception:
            result[str(name)] = '<无法读取>'
    return result


TRY = {'on': False}
TRACE = {'steps': [], 'size': 0, 'truncated': False, 'snapshotTruncated': False}


def frame_depth(frame):
    depth = 0
    parent = frame.f_back
    while parent is not None and parent.f_code.co_filename == SOLUTION_FILE:
        depth += 1
        parent = parent.f_back
    return depth


def snapshot_locals(frame):
    values = {}
    for name, value in frame.f_locals.items():
        if name in ('self', '_') or name.startswith('__') or name.startswith('.') or name.startswith('<'):
            continue
        try:
            item = snapshot(value)
        except BaseException:
            continue
        if item is SKIP:
            continue
        values[name] = item
    return values


def record(step):
    if not TRY['on']:
        return
    if len(TRACE['steps']) >= EVENT_LIMIT or TRACE['size'] >= EVENT_BYTES:
        TRACE['truncated'] = True
        return
    try:
        encoded = json.dumps(step, ensure_ascii=False)
    except (TypeError, ValueError):
        TRACE['snapshotTruncated'] = True
        return
    TRACE['size'] += len(encoded)
    TRACE['steps'].append(step)


def tracer(frame, event, arg):
    if frame.f_code.co_filename != SOLUTION_FILE:
        return None
    if event == 'call':
        return tracer
    if event == 'line':
        try:
            state = snapshot_locals(frame)
        except BaseException:
            state = {}
        record({'line': int(frame.f_lineno), 'depth': frame_depth(frame), 'state': state})
    elif event == 'return':
        try:
            state = snapshot_locals(frame)
        except BaseException:
            state = {}
        try:
            returned = serialize(arg)
        except BaseException:
            returned = '<无法序列化>'
            TRACE['snapshotTruncated'] = True
        record({'line': int(frame.f_lineno), 'depth': frame_depth(frame),
                'state': state, 'returned': returned})
    return tracer


def materialize(case):
    context = {'shared': None}
    args = []
    for spec in case['args']:
        kind = spec['kind']
        if kind == 'raw':
            args.append(spec.get('value'))
        elif kind == 'linked':
            args.append(chain(spec.get('value') or []))
        elif kind == 'list_of_linked':
            args.append([chain(item or []) for item in (spec.get('value') or [])])
        elif kind == 'tree':
            args.append(tree_from_list(spec.get('value') or []))
        elif kind == 'random_list':
            args.append(random_list(spec.get('value') or []))
        elif kind == 'tree_ref':
            args.append(find_tree_node(args[spec.get('fromArg', 0)], spec.get('value')))
        elif kind == 'cycle_head':
            head, nodes = cycle_head(spec.get('value') or [], spec.get('pos'))
            context['cycle_nodes'] = nodes
            args.append(head)
        elif kind == 'intersection_a':
            head_a, head_b, shared = intersection_build(
                spec.get('value') or [], spec.get('other') or [],
                spec.get('skipA'), spec.get('skipB'))
            context['shared'] = shared
            args.extend([head_a, head_b])
        elif kind == 'intersection_b':
            continue
        else:
            raise ValueError('未知的样例参数类型：' + str(kind))
    return args, context


def _bounded(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)[:8000]
    if len(encoded) > 8000:
        return '…（结果超过 8000 字符，已截断）'
    return value


def run_solve(payload, namespace):
    started = time.perf_counter()
    solution_class = namespace.get('Solution')
    if not callable(solution_class):
        return {'fatal': '未在官方参考代码中找到 class Solution。'}
    case = payload['cases'][0]
    try:
        args, context = materialize(case)
        solution = solution_class()
        TRACE['steps'] = []
        TRACE['size'] = 0
        TRACE['truncated'] = False
        TRACE['snapshotTruncated'] = False
        TRY['on'] = True
        previous = sys.gettrace()
        sys.settrace(tracer)
        try:
            result = getattr(solution, payload['method'])(*args)
        finally:
            sys.settrace(previous)
            TRY['on'] = False
        mode = case.get('mode', 'literal')
        if mode == 'cycle-index':
            if result is None:
                actual = {'index': None, 'value': None}
            else:
                nodes = context.get('cycle_nodes') or []
                position = next((i for i, node in enumerate(nodes) if node is result), None)
                actual = {'index': position, 'value': getattr(result, 'val', None)}
        elif mode == 'intersection':
            if result is None:
                actual = {'isNull': True, 'isTarget': False, 'value': None}
            else:
                actual = {'isNull': False, 'isTarget': result is context.get('shared'),
                          'value': getattr(result, 'val', None)}
        else:
            if result is None and case.get('mutate'):
                result = args[case['mutate']['argIndex']]
            actual = serialize(result, scalar_node=bool(case.get('scalarNode')))
        return {
            'actual': _bounded(actual),
            'steps': TRACE['steps'],
            'traceTruncated': TRACE['truncated'],
            'snapshotTruncated': TRACE['snapshotTruncated'],
            'durationMs': round((time.perf_counter() - started) * 1000, 2),
        }
    except BaseException as error:
        return {'error': format_error(error),
                'durationMs': round((time.perf_counter() - started) * 1000, 2)}


def run_design(payload, namespace):
    started = time.perf_counter()
    class_name = payload.get('className')
    cls = namespace.get(class_name) if isinstance(class_name, str) else None
    if not callable(cls):
        return {'fatal': '未在官方参考代码中找到设计类 ' + str(class_name)}
    try:
        instance = cls(*(payload.get('ctorArgs') or []), **(payload.get('ctorKwargs') or {}))
    except BaseException as error:
        return {'error': format_error(error),
                'durationMs': round((time.perf_counter() - started) * 1000, 2)}
    steps = []
    for operation in payload.get('operations') or []:
        name = operation.get('method')
        method = getattr(instance, name, None)
        if not callable(method):
            return {'error': '设计类缺少样例所需的方法：' + str(name)}
        args = operation.get('args') or []
        kwargs = operation.get('kwargs') or {}
        try:
            returned = method(*args, **kwargs)
        except BaseException as error:
            return {'error': format_error(error),
                    'durationMs': round((time.perf_counter() - started) * 1000, 2)}
        try:
            plain = snapshot(returned, 1)
        except BaseException:
            plain = str(returned)[:240]
        steps.append({'method': name, 'args': args, 'kwargs': kwargs,
                      'returned': plain, 'state': snapshot_instance(instance)})
    return {'steps': steps, 'durationMs': round((time.perf_counter() - started) * 1000, 2)}


def write_result(value):
    with open(os.path.join(BASE, 'result.json'), 'w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False)


def main():
    sys.stdout, sys.stderr = OUT, ERR
    try:
        with open(os.path.join(BASE, 'payload.json'), encoding='utf-8') as handle:
            payload = json.load(handle)
        with open(os.path.join(BASE, 'user_code.py'), encoding='utf-8') as handle:
            source = handle.read()
    except BaseException as error:
        write_result({'fatal': '读取运行计划失败：' + format_error(error)})
        return
    namespace = {'ListNode': ListNode, 'TreeNode': TreeNode, 'Node': Node, '__name__': 'solution'}
    import typing
    namespace.update({name: value for name, value in vars(typing).items() if not name.startswith('_')})
    started = time.perf_counter()
    try:
        exec(compile(source, SOLUTION_FILE, 'exec'), namespace)
    except BaseException as error:
        write_result({'compileError': format_error(error),
                      'durationMs': round((time.perf_counter() - started) * 1000, 2)})
        return
    mode = payload.get('mode') or 'solve'
    if mode == 'design':
        result = run_design(payload, namespace)
    else:
        result = run_solve(payload, namespace)
    result.setdefault('durationMs', round((time.perf_counter() - started) * 1000, 2))
    write_result(result)


main()
'''


# ---------------------------------------------------------------------------
# Parent helpers
# ---------------------------------------------------------------------------


def _hot100(question_id) -> dict:
    require(isinstance(question_id, str) and 0 < len(question_id) <= 60, 'DEMO_NOT_AVAILABLE')
    found = question(question_id)
    require(found is not None and found.get('category') == 'hot100', 'DEMO_NOT_AVAILABLE')
    return found


def _is_design(q: dict) -> bool:
    return code_runner._official_solution_method(q) is None


def _supported(q: dict) -> bool:
    if _is_design(q):
        return q.get('leetcodeNumber') in DESIGN_NUMBERS
    return code_runner._official_solution_method(q) is not None


def _code_hash(source: str) -> str:
    return hashlib.sha256(source.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Design-class operation sequence parsing (transcribed from the sample input)
# ---------------------------------------------------------------------------


def _parse_call_args(text: str):
    text = (text or '').strip()
    if not text:
        return [], {}
    args, kwargs = [], {}
    for part in code_runner._split_top_level(text):
        if '=' in part:
            name, _, raw = part.partition('=')
            name = name.strip()
            if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
                try:
                    kwargs[name] = code_runner._literal(raw.strip())
                except (ValueError, SyntaxError) as error:
                    raise _TraceFailure('DEMO_SAMPLE_INVALID', '无法解析操作参数 ' + part) from error
                continue
        try:
            args.append(code_runner._literal(part))
        except (ValueError, SyntaxError) as error:
            raise _TraceFailure('DEMO_SAMPLE_INVALID', '无法解析操作参数 ' + part) from error
    return args, kwargs


def _parse_design_input(raw: str) -> dict:
    """Parse the capacity = 2；put(1,1)；get(1) style design sample input.

    The bank stores design-class examples as LeetCode's textual operation list
    (separators vary: Chinese semicolons, newlines, ASCII semicolons or commas).
    code_runner._split_top_level splits on commas/semicolons only outside
    brackets, so arguments like put(1, 1) survive; strings are kept intact.
    """
    text = (raw or '').replace('；', ';').replace('，', ',')
    class_hint = None
    ctor_args, ctor_kwargs = [], {}
    ops = []
    for part in code_runner._split_top_level(text):
        part = part.strip().rstrip('。.')
        if not part:
            continue
        match = re.fullmatch(
            r'(?:[A-Za-z_]\w*\s+)?(?:(?P<var>[A-Za-z_]\w*)\s*=\s*)?new\s+'
            r'(?P<cls>[A-Za-z_]\w*)\s*\((?P<args>.*)\)', part)
        if match:
            class_hint = match.group('cls')
            ctor_args, ctor_kwargs = _parse_call_args(match.group('args'))
            continue
        match = re.fullmatch(r'(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<value>.+)', part)
        if match and '(' not in match.group('value'):
            ctor_kwargs[match.group('name')] = code_runner._literal(match.group('value').strip())
            continue
        match = re.fullmatch(
            r'(?:(?P<obj>[A-Za-z_]\w*)\.)?(?P<name>[A-Za-z_]\w*)\s*\((?P<args>.*)\)', part)
        if match:
            args, kwargs = _parse_call_args(match.group('args'))
            ops.append({'method': match.group('name'), 'args': args, 'kwargs': kwargs})
            continue
        raise _TraceFailure('DEMO_SAMPLE_INVALID', '无法解析设计类样例操作：' + part)
    if not ops:
        raise _TraceFailure('DEMO_SAMPLE_INVALID', '设计类样例中没有可执行操作。')
    return {'classNameHint': class_hint, 'ctorArgs': ctor_args,
            'ctorKwargs': ctor_kwargs, 'operations': ops}


def _design_class(q: dict, parsed: dict) -> str:
    try:
        tree = ast.parse(q['solutions']['python'])
    except SyntaxError as error:  # pragma: no cover - official data is checked
        raise _TraceFailure('DEMO_EXECUTION_FAILED', '官方参考代码无法解析') from error
    classes = {
        node.name: {item.name for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for node in tree.body if isinstance(node, ast.ClassDef)
    }
    if not classes:
        raise _TraceFailure('DEMO_EXECUTION_FAILED', '官方参考代码中没有设计类。')
    hint = parsed.get('classNameHint')
    wanted = {op['method'] for op in parsed['operations']}
    if hint in classes:
        return hint
    ranked = sorted(classes, key=lambda name: (-len(wanted & classes[name]), name))
    if not wanted or wanted & classes[ranked[0]]:
        return ranked[0]
    raise _TraceFailure('DEMO_SAMPLE_INVALID',
                        '样例操作与官方设计类不匹配：' + ', '.join(sorted(wanted)))


def _design_method_lines(q: dict, class_name: str) -> dict:
    lines: dict = {}
    try:
        tree = ast.parse(q['solutions']['python'])
    except SyntaxError:
        return lines
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines[item.name] = item.lineno
    return lines


def _design_expected(q: dict, sample: dict):
    """Extract the documented query return values from the sample output text."""
    text = (sample.get('output') or '').strip()
    number = q.get('leetcodeNumber')
    if number == 208:
        try:
            return code_runner._literal(text)
        except (ValueError, SyntaxError) as error:
            raise _TraceFailure('DEMO_SAMPLE_INVALID', '无法解析样例输出：' + text) from error
    if number == 295:
        return [float(item) for item in re.findall(r'-?\d+(?:\.\d+)?', text)]
    if number == 146:
        return [int(item) for item in re.findall(r'-?\d+', text)]
    if number == 155:
        return [int(item) for item in re.findall(r'返回\s*(-?\d+)', text)]
    raise _TraceFailure('DEMO_SAMPLE_INVALID', '未知的设计类输出格式。')


# ---------------------------------------------------------------------------
# Subprocess execution (parent side)
# ---------------------------------------------------------------------------


def _work_root():
    configured = WORK_ROOT or code_runner.WORK_ROOT
    if not configured:
        return None
    root = Path(configured).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def _make_workspace() -> str:
    root = Path(_work_root() or tempfile.gettempdir()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for _ in range(50):
        candidate = root / ('xueya-demo-' + next(tempfile._get_candidate_names()))
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return str(candidate.resolve())
    raise _TraceFailure('DEMO_EXECUTION_FAILED', '无法创建临时执行目录。')


def _execute(payload: dict) -> dict:
    """Run one demo plan in a child interpreter; never raises for child problems."""
    directory = _make_workspace()
    started = time.perf_counter()
    try:
        root = Path(directory)
        (root / 'driver.py').write_text(_DRIVER_SOURCE, encoding='utf-8')
        (root / 'payload.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        (root / 'user_code.py').write_text(payload['code'], encoding='utf-8')
        environment = {
            'TEMP': directory,
            'TMP': directory,
            'SYSTEMROOT': os.environ.get('SYSTEMROOT', ''),
            'PYTHONUTF8': '1',
            'PYTHONIOENCODING': 'utf-8',
            'PYTHONDONTWRITEBYTECODE': '1',
        }
        command = [sys.executable or 'python', '-I', '-B', '-X', 'utf8', str(root / 'driver.py')]
        timeout_s = max(0.5, RUN_TIMEOUT_MS / 1000)
        try:
            completed = subprocess.run(
                command, cwd=directory, env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout_s, check=False,
            )
        except subprocess.TimeoutExpired:
            return {'timedOut': True, 'timeoutMs': RUN_TIMEOUT_MS,
                    'durationMs': round((time.perf_counter() - started) * 1000, 2)}
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        result_path = root / 'result.json'
        if not result_path.exists():
            diagnostic = completed.stderr.decode('utf-8', errors='replace')
            return {'fatal': '演示执行器未返回结果。', 'stderr': diagnostic[-4000:], 'durationMs': elapsed}
        raw = result_path.read_bytes()[:MAX_RESULT_BYTES]
        try:
            result = json.loads(raw.decode('utf-8', errors='replace'))
        except ValueError:
            return {'fatal': '演示执行器返回了无法解析的结果。', 'durationMs': elapsed}
        result['durationMs'] = elapsed
        return result
    finally:
        shutil.rmtree(directory, ignore_errors=True)


# ---------------------------------------------------------------------------
# Trace post-processing (parent side): notes, highlights, step selection
# ---------------------------------------------------------------------------

_POINTER_NAMES = (
    'i', 'j', 'k', 'l', 'r', 'p', 'q', 'x', 'y', 'left', 'right', 'mid', 'lo', 'hi',
    'slow', 'fast', 'start', 'end', 'row', 'col', 'idx', 'index', 'pos', 'cur',
)


def _short(value, limit: int = 72) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'null'
    if isinstance(value, (dict, list)):
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    else:
        text = str(value)
    if len(text) > limit:
        text = text[:limit] + '…'
    return text


def _state_signature(state) -> str:
    try:
        return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    except (TypeError, ValueError):
        return repr(state)


def _annotate(raw_steps: list) -> list:
    """Attach per-step changed-variable metadata, computed against the real
    previous executed line (not against a sampled subset)."""
    annotated = []
    previous: dict = {}
    for index, step in enumerate(raw_steps):
        state = step.get('state') or {}
        current = {}
        changed = []
        for name, value in state.items():
            text = value if isinstance(value, str) else _state_signature(value)
            current[name] = text
            if previous.get(name) != text:
                changed.append(name)
        for name in previous.keys():
            if name not in state:
                changed.append(name)
        annotated.append({
            'line': int(step.get('line') or 0),
            'depth': int(step.get('depth') or 0),
            'state': state,
            'returned': step.get('returned'),
            'hasReturn': 'returned' in step,
            'changed': [name for name in changed if name in state][:8],
            'index': index,
        })
        previous = current
    return annotated


def _step_score(item: dict) -> tuple:
    score = len(item['changed'])
    if item['hasReturn']:
        score += 3
    if item['depth'] == 0 and item['line']:
        score += 1
    return (score, -item['index'])


def _select_steps(items: list) -> tuple:
    """Keep first/last plus the most significant steps, spread over time."""
    total = len(items)
    if total <= MAX_STEPS:
        return items, False
    keep = {0, total - 1}
    slots = MAX_STEPS - 2
    middle = list(range(1, total - 1))
    if slots > 0 and middle:
        bucket = max(1, -(-len(middle) // slots))
        for start in range(0, len(middle), bucket):
            chunk = middle[start:start + bucket]
            best = max(chunk, key=lambda offset: _step_score(items[offset]))
            keep.add(best)
    ordered = sorted(keep)
    return [items[offset] for offset in ordered], True


def _line_text(code_lines: list, line: int) -> str:
    if 1 <= line <= len(code_lines):
        return code_lines[line - 1].strip()
    return ''


def _build_notes(items: list, code_lines: list) -> list:
    steps = []
    for item in items:
        line = item['line']
        text = _line_text(code_lines, line)
        state = item['state']
        changed = [name for name in item['changed'] if name in state]
        parts = [name + '=' + _short(state[name]) for name in changed[:4]]
        if item['hasReturn']:
            note = '执行第 %d 行：%s；返回 %s' % (line, text or '（函数返回）', _short(item.get('returned')))
            if parts:
                note += '；变化：' + '、'.join(parts)
        elif parts:
            note = '执行第 %d 行：%s；变化：%s' % (line, text or '（无对应代码行）', '、'.join(parts))
        else:
            note = '执行第 %d 行：%s；无关键变量变化' % (line, text or '（无对应代码行）')
        if item['depth']:
            note += '（递归深度 %d）' % item['depth']
        steps.append({'line': line, 'note': note, 'state': state, 'highlight': changed[:6]})
    return steps


def _json_size(value) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Visualisation / layout inference
# ---------------------------------------------------------------------------

_TOPIC_VIZ = {
    '链表': 'linked-list',
    '二叉树': 'tree',
    '矩阵': 'matrix',
    '图论': 'graph',
    '回溯': 'backtracking',
    '栈': 'stack-queue',
    '堆': 'stack-queue',
    '二分查找': 'array',
    '动态规划': 'dp',
    '多维动态规划': 'dp',
    '滑动窗口': 'string',
    '子串': 'string',
    '哈希': 'array',
    '双指针': 'array',
    '普通数组': 'array',
    '贪心算法': 'array',
    '技巧': 'array',
}

_LINKED_KINDS = ('linked', 'list_of_linked', 'cycle_head', 'intersection_a',
                 'intersection_b', 'random_list')
_TREE_KINDS = ('tree', 'tree_ref')

LEGENDS = {
    'array': ['当前下标 / 指针', '已排除区间', '候选值'],
    'matrix': ['当前格', '已处理行 / 列', '候选位置'],
    'grid': ['当前格', '已访问 / 已淹没', '水域 / 未访问'],
    'tree': ['当前结点', '已访问子树', '待访问结点'],
    'linked-list': ['当前结点', '已处理 / 已反转', '待处理'],
    'graph': ['当前结点', '已访问', '入队 / 待处理'],
    'dp': ['当前状态', '已计算状态', '最优值 / 转移'],
    'string': ['当前字符', '窗口 / 已匹配', '候选区间'],
    'stack-queue': ['栈顶 / 队头', '栈内 / 队内元素', '输出'],
    'backtracking': ['当前选择', '已选路径', '候选 / 剪枝'],
    'design': ['本次操作', '数据结构内容', '返回值'],
    'scalar': ['当前状态'],
}


def _case_kinds(case: dict) -> list:
    return [arg.get('kind') for arg in case.get('args') or []]


def _infer_viz(q: dict, case: dict, inputs: dict) -> str:
    if _is_design(q):
        return 'design'
    kinds = _case_kinds(case)
    if any(kind in _LINKED_KINDS for kind in kinds):
        return 'linked-list'
    if any(kind in _TREE_KINDS for kind in kinds):
        return 'tree'
    topic = q.get('topic') or ''
    if topic == '图论':
        return 'grid' if 'grid' in inputs else 'graph'
    if topic == '多维动态规划' and 'grid' in inputs:
        return 'matrix'
    if topic in ('滑动窗口', '子串'):
        return 'string'
    values = list(inputs.values())
    if values and isinstance(values[0], str) and topic in ('哈希', '贪心算法', '双指针'):
        return 'string'
    return _TOPIC_VIZ.get(topic, 'array')


def _infer_pointers(raw_items: list) -> list:
    seen = []
    for item in raw_items:
        for name in item['state'].keys():
            if name in _POINTER_NAMES and name not in seen:
                seen.append(name)
    return seen[:6]


def _layout(viz: str, pointers: list) -> dict:
    return {'primary': viz, 'pointers': pointers, 'legend': list(LEGENDS.get(viz, ['当前状态']))}


# ---------------------------------------------------------------------------
# Meta / sample echo
# ---------------------------------------------------------------------------


def _meta(q: dict) -> dict:
    complexity = q.get('complexity') or {}
    explanation = (q.get('explanation') or '').strip()
    summary = explanation if len(explanation) <= 260 else explanation[:258] + '…'
    return {
        'coreIdea': q.get('coreIdea'),
        'hints': list(q.get('hints') or []),
        'complexity': {'time': complexity.get('time'), 'space': complexity.get('space')},
        'summary': summary,
        'topic': q.get('topic'),
        'difficulty': q.get('difficulty'),
        'pitfalls': q.get('pitfalls'),
        'dataRange': q.get('dataRange'),
    }


def _sample_echo(q: dict, sample_index: int) -> dict:
    sample = q['samples'][sample_index]
    return {'input': sample.get('input', ''), 'output': sample.get('output', '')}


# ---------------------------------------------------------------------------
# Solve-mode demo (the generic engine)
# ---------------------------------------------------------------------------


def _resolve_result(case: dict, item: dict):
    mode = case.get('mode', 'literal')
    actual = item.get('actual')
    if mode == 'cycle-index':
        return (actual or {}).get('index')
    if mode == 'intersection':
        actual = actual or {}
        return actual.get('value') if actual.get('isTarget') else None
    if actual is None and case.get('nodeResult') and case.get('expected') == []:
        return []
    return actual


def _result_text(case: dict, result, item: dict) -> str:
    mode = case.get('mode', 'literal')
    if mode == 'cycle-index':
        if result is None:
            return 'null（链表无环）'
        value = (item.get('actual') or {}).get('value')
        return '值为 %s 的结点（下标 %s）' % (value, result)
    if mode == 'intersection':
        if result is None:
            return 'null（两条链表不相交）'
        return '值为 %s 的相交结点' % result
    if isinstance(result, bool):
        return 'true' if result else 'false'
    return _short(result, 120)


def _parse_sample_inputs(q: dict, sample_index: int) -> dict:
    sample = q['samples'][sample_index]
    try:
        return code_runner._parse_input_vars(sample.get('input', ''))
    except AppError as error:
        raise _TraceFailure('DEMO_SAMPLE_INVALID', '无法解析样例输入。') from error


def _build_solve_demo(q: dict, sample_index: int) -> dict:
    source = q['solutions']['python']
    plan = code_runner._build_plan(q, source)
    if plan.get('unsupported'):
        raise _TraceFailure('DEMO_NOT_AVAILABLE', plan.get('reason') or '')
    if plan.get('compileError'):
        raise _TraceFailure('DEMO_EXECUTION_FAILED', plan['compileError'])
    case = dict(plan['cases'][sample_index], index=0)
    payload = {
        'mode': 'solve',
        'method': plan['method'],
        'code': source,
        'cases': [{key: case.get(key) for key in ('index', 'args', 'mode', 'mutate', 'scalarNode')}],
    }
    executed = _execute(payload)
    if executed.get('timedOut'):
        raise _TraceFailure('DEMO_TIMEOUT', '参考解执行超过 %d ms。' % RUN_TIMEOUT_MS)
    if executed.get('fatal') or executed.get('compileError'):
        detail = executed.get('fatal') or executed.get('compileError')
        raise _TraceFailure('DEMO_EXECUTION_FAILED', str(detail)[:600])
    if executed.get('error'):
        raise _TraceFailure('DEMO_EXECUTION_FAILED', str(executed['error'])[:600])
    item = executed
    passed, display, error = code_runner._check_case(case, item)
    if error:
        raise _TraceFailure('DEMO_EXECUTION_FAILED', str(error)[:600])
    if not passed:
        raise _TraceFailure(
            'DEMO_RESULT_MISMATCH',
            '参考解实际输出 %s，与样例期望 %s 不一致。'
            % (code_runner._display(display), case.get('expectedText')),
        )
    result = _resolve_result(case, item)
    code_lines = source.splitlines()
    raw_steps = item.get('steps') or []
    if not raw_steps:
        raise _TraceFailure('DEMO_EXECUTION_FAILED', '执行过程没有记录到参考解的任何代码行。')
    warnings = []
    if item.get('traceTruncated'):
        warnings.append('执行事件过多，仅记录前 %d 个事件后继续执行并保留最终返回。' % EVENT_LIMIT)
    annotated = _annotate(raw_steps)
    selected, sampled = _select_steps(annotated)
    if sampled:
        warnings.append('轨迹共 %d 个执行事件，已保留首尾与变化显著的 %d 步。'
                        % (len(annotated), len(selected)))
    steps = _build_notes(selected, code_lines)
    if item.get('snapshotTruncated'):
        warnings.append('部分变量值过长，已在快照中截断。')
    guard = 0
    while _json_size(steps) > 3_500_000 and len(steps) > 60 and guard < 6:
        last = steps[-1]
        half = steps[:-1][::2]
        steps = half + [last]
        guard += 1
    if guard:
        warnings.append('快照体积过大，已进一步抽样（保留 %d 步）。' % len(steps))
    inputs = _parse_sample_inputs(q, sample_index)
    viz = _infer_viz(q, case, inputs)
    pointers = _infer_pointers(annotated)
    return {
        'schemaVersion': SCHEMA_VERSION,
        'questionId': q['id'],
        'title': q['title'],
        'number': q.get('leetcodeNumber'),
        'topic': q.get('topic'),
        'difficulty': q.get('difficulty'),
        'sample': _sample_echo(q, sample_index),
        'sampleIndex': sample_index,
        'sampleCount': len(q['samples']),
        'inputs': inputs,
        'code': code_lines,
        'codeLanguage': 'python',
        'viz': viz,
        'layout': _layout(viz, pointers),
        'steps': steps,
        'result': result,
        'resultText': _result_text(case, result, item),
        'expectedText': case.get('expectedText'),
        'meta': _meta(q),
        'warnings': warnings,
        'verified': True,
    }


# ---------------------------------------------------------------------------
# Design-mode demo
# ---------------------------------------------------------------------------


def _display_design_return(value) -> str:
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return _short(value, 72)


def _build_design_demo(q: dict, sample_index: int) -> dict:
    source = q['solutions']['python']
    sample = q['samples'][sample_index]
    parsed = _parse_design_input(sample.get('input', ''))
    class_name = _design_class(q, parsed)
    payload = {
        'mode': 'design',
        'code': source,
        'className': class_name,
        'ctorArgs': parsed['ctorArgs'],
        'ctorKwargs': parsed['ctorKwargs'],
        'operations': parsed['operations'],
    }
    executed = _execute(payload)
    if executed.get('timedOut'):
        raise _TraceFailure('DEMO_TIMEOUT', '参考实现执行超过 %d ms。' % RUN_TIMEOUT_MS)
    if executed.get('fatal') or executed.get('compileError'):
        raise _TraceFailure('DEMO_EXECUTION_FAILED',
                            str(executed.get('fatal') or executed.get('compileError'))[:600])
    if executed.get('error'):
        raise _TraceFailure('DEMO_EXECUTION_FAILED', str(executed['error'])[:600])
    raw_steps = executed.get('steps') or []
    if not raw_steps:
        raise _TraceFailure('DEMO_EXECUTION_FAILED', '设计类实例没有执行任何操作。')
    expected = _design_expected(q, sample)
    query_returns = [step.get('returned') for step in raw_steps if step.get('returned') is not None]
    if not code_runner._equal(expected, query_returns):
        raise _TraceFailure(
            'DEMO_RESULT_MISMATCH',
            '官方实现实际返回 %s，与样例输出 %s 不一致。'
            % (_short(query_returns, 160), sample.get('output', '')),
        )
    method_lines = _design_method_lines(q, class_name)
    code_lines = source.splitlines()
    steps = []
    previous: dict = {}
    for step in raw_steps:
        method = step.get('method')
        args = step.get('args') or []
        kwargs = step.get('kwargs') or {}
        attrs = step.get('state') or {}
        signature = '%s(%s)' % (method, ', '.join(
            [_short(value, 40) for value in args]
            + ['%s=%s' % (key, _short(value, 40)) for key, value in kwargs.items()]))
        changed = [name for name, value in attrs.items()
                   if _state_signature(value) != previous.get(name)]
        returned = step.get('returned')
        line = method_lines.get(method, 0)
        code_text = _line_text(code_lines, line)
        note_parts = ['执行第 %d 行：%s' % (line, code_text or '（设计类方法）'),
                      '调用 ' + signature,
                      '返回 ' + _display_design_return(returned)]
        if changed:
            note_parts.append('变化：' + '、'.join(
                name + '=' + _short(attrs[name]) for name in changed[:3]))
        state = {'operation': signature, 'returned': returned}
        state.update(attrs)
        steps.append({'line': line, 'note': '；'.join(note_parts),
                      'state': state, 'highlight': changed[:6]})
        previous = {name: _state_signature(value) for name, value in attrs.items()}
    inputs = {
        'className': class_name,
        'constructor': {'args': parsed['ctorArgs'], 'kwargs': parsed['ctorKwargs']},
        'operations': [{'method': op['method'], 'args': op['args'], 'kwargs': op['kwargs']}
                       for op in parsed['operations']],
        'documentedOutput': sample.get('output', ''),
    }
    return {
        'schemaVersion': SCHEMA_VERSION,
        'questionId': q['id'],
        'title': q['title'],
        'number': q.get('leetcodeNumber'),
        'topic': q.get('topic'),
        'difficulty': q.get('difficulty'),
        'sample': _sample_echo(q, sample_index),
        'sampleIndex': sample_index,
        'sampleCount': len(q['samples']),
        'inputs': inputs,
        'code': code_lines,
        'codeLanguage': 'python',
        'viz': 'design',
        'layout': _layout('design', []),
        'steps': steps,
        'result': query_returns,
        'resultText': '查询返回依次为 ' + '、'.join(_display_design_return(value) for value in query_returns),
        'expectedText': sample.get('output', ''),
        'meta': _meta(q),
        'warnings': ['设计类题目按原题示例的操作序列逐次调用官方实现生成轨迹，不执行用户代码。'],
        'verified': True,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def trace(question_id, sample_index=0) -> dict:
    """Return a verified demo-2 trace for one Hot100 sample.

    Raises AppError with a DEMO_* code when the question/sample is unavailable or
    when the official reference solution does not reproduce the documented sample
    output.
    """
    q = _hot100(question_id)
    require(_supported(q), 'DEMO_NOT_AVAILABLE')
    require(type(sample_index) is int and 0 <= sample_index < len(q['samples']),
            'DEMO_SAMPLE_NOT_FOUND')
    key = (q['id'], sample_index, _code_hash(q['solutions']['python']))
    cached = _CACHE.get(key)
    if cached is not None:
        _CACHE.move_to_end(key)
        return cached
    try:
        demo = (_build_design_demo(q, sample_index) if _is_design(q)
                else _build_solve_demo(q, sample_index))
    except _TraceFailure as failure:
        raise AppError(failure.code) from failure
    _CACHE[key] = demo
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return demo


def probe(question_id, sample_index=0) -> dict:
    """Coverage helper: {ok: True, demo} or {ok: False, error, detail}."""
    try:
        demo = trace(question_id, sample_index)
    except AppError as error:
        failure = error.__cause__ if isinstance(error.__cause__, _TraceFailure) else None
        return {'ok': False, 'questionId': question_id, 'sampleIndex': sample_index,
                'error': error.code, 'detail': failure.detail if failure else ''}
    except Exception as error:  # pragma: no cover - defensive
        return {'ok': False, 'questionId': question_id, 'sampleIndex': sample_index,
                'error': 'DEMO_EXECUTION_FAILED', 'detail': '%s: %s' % (type(error).__name__, error)}
    return {'ok': True, 'questionId': question_id, 'sampleIndex': sample_index, 'demo': demo}


def supported_ids() -> list:
    """Cheap structural availability (no execution): all traceable Hot100 ids."""
    from .practice_bank import questions
    return [q['id'] for q in questions() if q.get('category') == 'hot100' and _supported(q)]


def describe(question_id, verify: bool = True) -> dict:
    """Registry row for one question; verify traces sample 0 for real."""
    q = _hot100(question_id)
    require(_supported(q), 'DEMO_NOT_AVAILABLE')
    row = {
        'id': q['id'], 'title': q['title'], 'number': q.get('leetcodeNumber'),
        'topic': q.get('topic'), 'difficulty': q.get('difficulty'),
        'sampleCount': len(q['samples']),
    }
    if verify:
        try:
            demo = trace(q['id'], 0)
        except AppError as error:
            row.update({'verified': False, 'error': error.code})
            return row
        row.update({'verified': True, 'viz': demo['viz']})
    return row


def describe_all(verify: bool = True) -> list:
    """Registry rows in bank order; verified entries expose viz."""
    from .practice_bank import questions
    rows = []
    for q in questions():
        if q.get('category') != 'hot100' or not _supported(q):
            continue
        row = {
            'id': q['id'], 'title': q['title'], 'number': q.get('leetcodeNumber'),
            'topic': q.get('topic'), 'difficulty': q.get('difficulty'),
            'sampleCount': len(q['samples']),
        }
        if verify:
            try:
                demo = trace(q['id'], 0)
            except AppError as error:
                failure = error.__cause__ if isinstance(error.__cause__, _TraceFailure) else None
                row.update({'verified': False, 'error': error.code,
                            'detail': failure.detail if failure else ''})
            else:
                row.update({'verified': True, 'viz': demo['viz']})
        rows.append(row)
    return rows


def available_ids() -> list:
    """Ids with a real, verified demo (registry source of truth).

    Traces the first sample of every structurally supported question once
    (cached afterwards); --write / --check and the tests share this engine.
    """
    return [row['id'] for row in describe_all(verify=True) if row.get('verified')]


def clear_cache() -> None:
    _CACHE.clear()


__all__ = [
    'SCHEMA_VERSION', 'MAX_STEPS', 'DESIGN_NUMBERS', 'WORK_ROOT',
    'trace', 'probe', 'supported_ids', 'describe', 'describe_all',
    'available_ids', 'clear_cache',
]
