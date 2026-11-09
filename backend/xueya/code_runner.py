"""Hot100 code workbench: real local execution (Python / C++ / Java) and AI complexity diagnosis.

Mounted by :class:`backend.xueya.workbench_api.WorkbenchWorkspace` (feature ``code``)::

    GET  /api/learning/space/workbench/code/capabilities[?refresh=1]
         -> {"ok": true, "capabilities": {...}, "languages": [...]}
    POST /api/learning/space/workbench/code/run
         body {questionId, language, code, caseIndex?} -> {"ok": true, "result": {...}}
    POST /api/learning/space/workbench/code/analyze
         body {questionId, language, code} -> {"ok": true, "analysis": {...}, "usage": ...}

Request validation errors raise :class:`backend.xueya.common.AppError`, which the host
turns into ``{"ok": false, "error": CODE}`` (see ``backend/xueya/app.py``).

Execution model
---------------
Python is executed in a separate interpreter (the current ``sys.executable``) started
with ``-I -B``. C++ (g++) and Java (javac + java) are compiled and run by
:mod:`backend.xueya.judge_compiled` only when :mod:`backend.xueya.judge_toolchain`
detects a working toolchain (version probe plus a minimal compile/run probe).
Every language runs in a throw-away working directory, a separate process, a minimal
environment, a hard timeout, capped stdout/stderr and a result file that is read back.

This is a local, single-user convenience runner, **not a security sandbox**:
user code can still read the user's files, open sockets and spawn processes. Only run
code you would run yourself.

The runner never fakes a pass: every case is compared against the stored sample output
with a real call into the user's method. Design-class questions (LRU, Trie, MinStack,
MedianFinder) and special linked structures (cycles, random pointers, shared nodes,
list-of-list nodes) have no single Solution method / plain literal driver and return
``supported: false`` with a reason instead of inventing a result. Compiled-language
support is reported per host: a missing g++/JDK is an explicit unavailable reason,
never a silent pass. Unlike the Python path, the generated C++/Java driver reports the
observed value and the parent process performs the comparison.
"""
from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fastapi.responses import JSONResponse

from .common import AppError, require
from .practice_bank import bank, question as bank_question

RUN_TIMEOUT_MS = 5000
MAX_CODE_CHARS = 20000
MAX_CAPTURE_BYTES = 65536
MAX_RESULT_BYTES = 262144
MAX_CASE_ACTUAL_CHARS = 8000
SUPPORTED_LANGUAGES = ('python', 'cpp', 'java')
LANGUAGE_LABELS = {'python': 'Python', 'cpp': 'C++', 'java': 'Java'}

SANDBOX_NOTE = (
    '本机单用户本地执行：独立子进程 + 临时目录 + 最小环境变量 + 5 秒超时 + 输出上限 64KB；'
    '这不是强安全沙箱，用户代码仍可能访问本机文件/网络，请只运行自己信任的代码。'
)
DESIGN_REASON = (
    '本题为设计类题目（如 MinStack / Trie / LRU / MedianFinder 等，没有单一的 Solution 求解方法），'
    '暂不支持在线运行。可对照官方题解手动验证，或直接在力扣运行。'
)
UNSUPPORTED_LANGUAGE_REASON = (
    '本机未检测到该语言可用的运行环境；请先安装对应编译器/运行时，然后点击“重新检测”。'
    '你仍可查看官方题解，或复制代码到力扣运行。'
)

# Questions whose sample inputs carry extra structure that plain literal parsing
# cannot express (cycles, shared nodes, random pointers).
SPECIAL_QUESTIONS = {138: 'random-list', 141: 'cycle', 142: 'cycle', 160: 'intersection'}

# Questions whose answer is an unordered collection (LeetCode accepts any order).
# The comparison canonicalises both sides for these; everything else stays exact.
UNORDERED_QUESTIONS = {
    17: 'sort_outer',   # letter combinations
    22: 'sort_outer',   # generate parentheses
    39: 'sort_outer',   # combination sum (inner order ascending)
    46: 'sort_outer',   # permutations (inner order meaningful)
    49: 'sort_all',     # group anagrams (inner and outer order free)
    51: 'sort_outer',   # N queens (board rows meaningful, board order free)
    78: 'sort_subsets', # subsets (inner set order free)
    131: 'sort_outer',  # palindrome partition
    347: 'sort_scalars',# top-k frequent
}

_LINKED_NAMES = {'head', 'l1', 'l2', 'list1', 'list2', 'headA', 'headB'}

# Directory used for per-run temporary workspaces. Production keeps the system
# default (``tempfile.mkdtemp``); tests / locked-down hosts can point this at a
# writable directory (``tests_python`` uses the git-ignored ``test-results``).
WORK_ROOT: str | None = os.environ.get('XUEYA_CODE_RUNNER_TMP') or None


def _work_root():
    if not WORK_ROOT:
        return None
    root = Path(WORK_ROOT).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def _make_workspace() -> str:
    """Create a private-ish run directory without ``mkdtemp``'s 0o700 ACL.

    ``tempfile.mkdtemp`` creates the directory with mode 0o700, which some
    locked-down Windows sandboxes treat as non-inheritable. A default-mode
    directory keeps the same uniqueness while remaining writable by this user.
    """
    root = Path(_work_root() or tempfile.gettempdir()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for _ in range(50):
        candidate = root / ('xueya-code-' + next(tempfile._get_candidate_names()))
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return str(candidate.resolve())
    raise AppError('CODE_RUNNER_TMP_FAILED')



# ---------------------------------------------------------------------------
# Bank / AST helpers
# ---------------------------------------------------------------------------


def _hot100(question_id) -> dict:
    """Return a Hot100 question or raise QUESTION_NOT_FOUND."""
    require(isinstance(question_id, str) and 0 < len(question_id) <= 60, 'INVALID_QUESTION_ID')
    found = bank_question(question_id)
    require(found is not None and found.get('category') == 'hot100', 'QUESTION_NOT_FOUND')
    return found


def _parse_python(source: str):
    return ast.parse(source)


def _class_methods(tree) -> dict:
    """Map class name -> list of (method_name, method_node) for top-level classes."""
    classes = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes[node.name] = [
                (item.name, item)
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
    return classes


def _official_solution_method(question) -> tuple[str, ast.FunctionDef] | None:
    """First public method of the reference ``class Solution``; ``None`` = design class."""
    try:
        tree = _parse_python(question['solutions']['python'])
    except SyntaxError:
        return None
    methods = _class_methods(tree).get('Solution') or []
    for name, node in methods:
        if not name.startswith('_') and name != '__init__':
            return name, node
    return None


def _is_design_question(question) -> bool:
    return _official_solution_method(question) is None


def _annotation_text(node) -> str:
    if node is None:
        return ''
    try:
        return ast.unparse(node).replace(' ', '')
    except Exception:  # pragma: no cover - defensive for exotic annotations
        return ''


def _user_method(tree, preferred: str | None):
    """Pick the method to call from user code: the official name when present."""
    classes = _class_methods(tree)
    methods = classes.get('Solution') or []
    public = [(name, node) for name, node in methods if not name.startswith('_') and name != '__init__']
    if not public:
        return None
    if preferred:
        for name, node in public:
            if name == preferred:
                return name, node
    return public[0]


# ---------------------------------------------------------------------------
# Sample input / expected output parsing
# ---------------------------------------------------------------------------


def _split_top_level(text: str) -> list[str]:
    """Split ``a = ..., b = ...`` on commas outside brackets/quotes."""
    parts, current = [], []
    depth = 0
    quote = None
    escaped = False
    for char in text:
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ('"', "'"):
            quote = char
            current.append(char)
        elif char in '[({':
            depth += 1
            current.append(char)
        elif char in '])}':
            depth = max(0, depth - 1)
            current.append(char)
        elif char in ',;' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        elif char in '\n' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
    tail = ''.join(current).strip()
    if tail:
        parts.append(tail)
    return [part for part in parts if part]


_NULL_WORDS = re.compile(r'(?<![\w"\'])null(?![\w"\'])')


def _literal(text: str):
    """Parse a sample literal with JavaScript-style true/false/null tolerated."""
    cleaned = text.strip()
    cleaned = re.sub(r'(?<![\w"\'])true(?![\w"\'])', 'True', cleaned)
    cleaned = re.sub(r'(?<![\w"\'])false(?![\w"\'])', 'False', cleaned)
    cleaned = _NULL_WORDS.sub('None', cleaned)
    return ast.literal_eval(cleaned)


def _parse_input_vars(text: str) -> dict:
    """Parse ``name = value`` sample inputs into an ordered dict; extra names kept."""
    values = {}
    for part in _split_top_level(text):
        if '=' not in part:
            continue
        name, _, raw = part.partition('=')
        name = name.strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            continue
        try:
            values[name] = _literal(raw)
        except (ValueError, SyntaxError) as error:
            raise AppError('INVALID_SAMPLE_INPUT') from error
    return values


def _strip_output_suffix(text: str) -> str:
    """Drop LeetCode-style parenthetical notes such as （一种合法结果）. """
    cleaned = text.strip()
    cleaned = re.sub(r'（[^（）]*）\s*$', '', cleaned).strip()
    cleaned = re.sub(r'\([^()]*\)\s*$', '', cleaned).strip()
    return cleaned


def _parse_expected(sample) -> tuple[str, object]:
    """Return (mode, expected_value). Only design questions fail to parse."""
    raw = sample.get('output', '')
    node_ref = re.match(r'^值为\s*(-?\d+)\s*的结点$', raw.strip())
    if node_ref:
        return 'node-ref', int(node_ref.group(1))
    text = _strip_output_suffix(raw)
    try:
        return 'literal', _literal(text)
    except (ValueError, SyntaxError) as error:
        raise AppError('INVALID_SAMPLE_OUTPUT') from error


# ---------------------------------------------------------------------------
# Plan building (parent side)
# ---------------------------------------------------------------------------


def _make_kind(question, official_name, index, official_params, annotation):
    """Describe how one parameter must be materialised inside the child process."""
    number = question.get('leetcodeNumber')
    special = SPECIAL_QUESTIONS.get(number)
    if special == 'cycle' and official_name == 'head':
        return {'kind': 'cycle_head'}
    if special == 'random-list' and official_name == 'head':
        return {'kind': 'random_list'}
    if special == 'intersection':
        return {'kind': 'intersection_a' if index == 0 else 'intersection_b'}
    if number == 236:
        if official_name == 'root':
            return {'kind': 'tree'}
        if official_name in ('p', 'q'):
            return {'kind': 'tree_ref', 'fromName': 'root'}
    compact = annotation
    if compact:
        if 'listoflistnode' in compact.lower() or 'List[ListNode]' in compact.replace('optional', ''):
            return {'kind': 'list_of_linked'}
        if 'ListNode' in compact:
            return {'kind': 'linked'}
        if 'TreeNode' in compact:
            return {'kind': 'tree'}
        if re.search(r'(?<!Tree)(?<!List)Node', compact):
            return {'kind': 'random_list'}
    if official_name in _LINKED_NAMES:
        return {'kind': 'linked'}
    if official_name == 'lists':
        return {'kind': 'list_of_linked'}
    if official_name == 'root':
        return {'kind': 'tree'}
    return {'kind': 'raw'}


def _sample_value_for(name, official_name, index, variables, order):
    if name in variables:
        return name, variables[name]
    if official_name and official_name in variables:
        return official_name, variables[official_name]
    if index < len(order):
        return order[index], variables[order[index]]
    raise AppError('INVALID_SAMPLE_INPUT')


def _case_args(official_name, index, official_params, user_name, kind, variables, order):
    _, value = _sample_value_for(user_name, official_name, index, variables, order)
    if kind['kind'] == 'cycle_head':
        pos = variables.get('pos')
        require(isinstance(value, list), 'INVALID_SAMPLE_INPUT')
        return {'kind': 'cycle_head', 'value': value, 'pos': pos}
    if kind['kind'] == 'random_list':
        require(isinstance(value, list), 'INVALID_SAMPLE_INPUT')
        return {'kind': 'random_list', 'value': value}
    if kind['kind'] in ('intersection_a', 'intersection_b'):
        return {
            'kind': kind['kind'],
            'value': value,
            'skipA': variables.get('skipA'),
            'skipB': variables.get('skipB'),
        }
    if kind['kind'] == 'tree_ref':
        root_name = kind.get('fromName') or ''
        root_index = official_params.index(root_name) if root_name in official_params else 0
        return {'kind': 'tree_ref', 'value': value, 'fromArg': root_index}
    if kind['kind'] == 'linked':
        require(isinstance(value, list), 'INVALID_SAMPLE_INPUT')
    if kind['kind'] in ('list_of_linked', 'tree'):
        require(isinstance(value, list), 'INVALID_SAMPLE_INPUT')
    return {'kind': kind['kind'], 'value': value}


def _mutation_target(kind, args, param_index):
    if kind['kind'] in ('tree',):
        return {'argIndex': param_index}
    if kind['kind'] == 'raw' and args and isinstance(args.get('value'), list):
        return {'argIndex': param_index}
    return None


def _intersection_expected(variables):
    head_a, head_b = variables.get('headA'), variables.get('headB')
    skip_a, skip_b = variables.get('skipA'), variables.get('skipB')
    if not isinstance(head_a, list) or not isinstance(head_b, list):
        return None
    if type(skip_a) is not int or type(skip_b) is not int:
        return None
    if not (0 <= skip_a < len(head_a) and 0 <= skip_b < len(head_b)):
        return None
    if head_a[skip_a:] != head_b[skip_b:]:
        return None
    return head_a[skip_a]


def build_cases(question, param_names, kinds) -> dict:
    """Build per-sample cases from the bank question and parameter descriptions.

    ``param_names`` are the official parameter names (matching the sample input
    variable names); ``kinds`` describes how each argument is materialised.
    This is shared by the Python driver and the compiled C++/Java drivers.
    """
    number = question.get('leetcodeNumber')
    special = SPECIAL_QUESTIONS.get(number)
    node_result = any(kind['kind'] in ('linked', 'list_of_linked', 'tree', 'random_list', 'cycle_head', 'intersection_a')
                      for kind in kinds)
    cases = []
    for sample_index, sample in enumerate(question['samples']):
        variables = _parse_input_vars(sample.get('input', ''))
        order = list(variables)
        args = []
        arg_index = 0
        while arg_index < len(param_names):
            if special == 'intersection' and arg_index == 1:
                args.append({'kind': 'intersection_b', 'value': None,
                             'skipA': variables.get('skipA'), 'skipB': variables.get('skipB')})
                arg_index += 1
                continue
            spec = _case_args(param_names[arg_index], arg_index, param_names,
                              param_names[arg_index], kinds[arg_index], variables, order)
            if special == 'intersection' and arg_index == 0:
                spec = {**spec, 'skipA': variables.get('skipA'), 'skipB': variables.get('skipB'),
                        'other': variables.get('headB')}
            args.append(spec)
            arg_index += 1
        mode, expected = _parse_expected(sample)
        if special == 'cycle' and number == 142:
            pos = variables.get('pos')
            expected = pos if type(pos) is int and pos >= 0 else None
            mode = 'cycle-index'
        elif special == 'intersection':
            expected = _intersection_expected(variables)
            mode = 'intersection'
        elif special == 'random-list':
            mode = 'random-list'
        cases.append({
            'index': sample_index,
            'input': sample.get('input', ''),
            'expectedText': sample.get('output', ''),
            'expected': expected,
            'mode': mode,
            'args': args,
            'mutate': None,
            'scalarNode': number == 236,
            'nodeResult': node_result,
            'compare': UNORDERED_QUESTIONS.get(number, 'exact'),
        })
    if not cases:
        return {'unsupported': True, 'reason': '该题没有可用于自动判题的样例。'}
    # Methods that mutate an argument and return None (moveZeroes, rotate,
    # setZeroes, sortColors, flatten, nextPermutation) compare the mutated input.
    if any(case['expected'] is not None for case in cases):
        for index, kind in enumerate(kinds):
            probe = cases[0]['args'][index]
            target = _mutation_target(kind, probe, index)
            if target:
                for case in cases:
                    case['mutate'] = target
                break
    return {'cases': cases}


def _build_plan(question, code) -> dict:
    """Analyse the user's code and the bank samples into an execution plan."""
    official = _official_solution_method(question)
    if official is None:
        return {'unsupported': True, 'reason': DESIGN_REASON}
    official_method, official_node = official
    official_params = [arg.arg for arg in official_node.args.args[1:]]
    try:
        tree = _parse_python(code)
    except SyntaxError as error:
        return {'compileError': f'代码存在语法错误：第 {error.lineno} 行 {error.msg}'}
    chosen = _user_method(tree, official_method)
    if chosen is None:
        return {'unsupported': True, 'reason': '未在代码中找到 class Solution 的可调用方法；请保留题目要求的方法名与签名。'}
    method, node = chosen
    user_params = [arg.arg for arg in node.args.args[1:]]
    if len(user_params) != len(official_params):
        return {
            'unsupported': True,
            'reason': f'方法 {method} 的参数数量与题目要求不一致：题目需要 {len(official_params)} 个参数，当前为 {len(user_params)} 个。',
        }
    annotations = {
        arg.arg: _annotation_text(arg.annotation)
        for arg in node.args.args[1:]
        if arg.annotation is not None
    }
    kinds = [
        _make_kind(question, official_params[index], index, official_params, annotations.get(user_params[index], ''))
        for index in range(len(user_params))
    ]
    built = build_cases(question, official_params, kinds)
    if built.get('unsupported'):
        return built
    return {
        'method': method,
        'officialMethod': official_method,
        'cases': built['cases'],
        'timeoutMs': RUN_TIMEOUT_MS,
        'note': SANDBOX_NOTE,
    }


# ---------------------------------------------------------------------------
# Child process driver (runs user code; parent only trusts the result file)
# ---------------------------------------------------------------------------


_DRIVER_SOURCE = r'''"""Generated per-run Hot100 driver. Runs in a separate Python interpreter."""
import json
import os
import sys
import time
import traceback
from collections import deque

BASE = os.path.dirname(os.path.abspath(__file__))
LIMIT = 65536


class _Capped:
    def __init__(self):
        self.parts = []
        self.size = 0
        self.cut = False

    def write(self, value):
        text = str(value)
        if self.size < LIMIT:
            chunk = text[: LIMIT - self.size]
            self.parts.append(chunk)
            self.size += len(chunk)
            if len(chunk) < len(text) or self.size >= LIMIT:
                self.cut = True
        else:
            self.cut = True
        return len(text)

    def flush(self):
        return None

    def isatty(self):
        return False

    @property
    def encoding(self):
        return 'utf-8'

    def text(self):
        body = ''.join(self.parts)
        if self.cut:
            body += '\n…（输出超过 64 KB 已截断）'
        return body


OUT, ERR = _Capped(), _Capped()


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


def run_case(case, solution_class, method_name):
    started = time.perf_counter()
    context = {'shared': None}
    try:
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
                    spec.get('skipA'), spec.get('skipB'),
                )
                context['shared'] = shared
                args.extend([head_a, head_b])
            elif kind == 'intersection_b':
                continue
            else:
                raise ValueError('未知的样例参数类型：' + str(kind))
        solution = solution_class()
        result = getattr(solution, method_name)(*args)
        mode = case.get('mode', 'literal')
        if mode == 'cycle-index':
            if result is None:
                actual = {'index': None, 'value': None}
            else:
                nodes = context.get('cycle_nodes') or []
                position = next((i for i, node in enumerate(nodes) if node is result), None)
                actual = {'index': position, 'value': getattr(result, 'val', None)}
            payload = {'actual': actual}
        elif mode == 'intersection':
            if result is None:
                payload = {'actual': {'isNull': True, 'isTarget': False, 'value': None}}
            else:
                payload = {'actual': {'isNull': False, 'isTarget': result is context.get('shared'),
                                      'value': getattr(result, 'val', None)}}
        else:
            if result is None and case.get('mutate'):
                result = args[case['mutate']['argIndex']]
            payload = {'actual': serialize(result, scalar_node=bool(case.get('scalarNode')))}
        payload['durationMs'] = round((time.perf_counter() - started) * 1000, 2)
        # Bound the result file so a pathological return value cannot flood it.
        try:
            encoded = json.dumps(payload['actual'], ensure_ascii=False)
        except (TypeError, ValueError):
            payload['actual'] = str(payload['actual'])[:8000]
        else:
            if len(encoded) > 8000:
                payload['actual'] = '…（返回结果超过 8000 字符，已截断）'
        return payload
    except BaseException as error:  # user code may raise anything, incl. SystemExit
        return {'error': format_error(error), 'durationMs': round((time.perf_counter() - started) * 1000, 2)}


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
        exec(compile(source, 'solution.py', 'exec'), namespace)
    except BaseException as error:
        write_result({'compileError': format_error(error), 'stdout': OUT.text(), 'stderr': ERR.text(),
                      'durationMs': round((time.perf_counter() - started) * 1000, 2)})
        return
    solution_class = namespace.get('Solution')
    if not callable(solution_class):
        write_result({'compileError': '未在代码中找到 class Solution。', 'stdout': OUT.text(),
                      'stderr': ERR.text(), 'durationMs': round((time.perf_counter() - started) * 1000, 2)})
        return
    cases = []
    for case in payload.get('cases', []):
        try:
            item = run_case(case, solution_class, payload.get('method'))
        except BaseException as error:
            item = {'error': format_error(error)}
        item['index'] = case.get('index')
        cases.append(item)
    write_result({'cases': cases, 'stdout': OUT.text(), 'stderr': ERR.text(),
                  'durationMs': round((time.perf_counter() - started) * 1000, 2)})


main()
'''


# ---------------------------------------------------------------------------
# Subprocess execution (parent side)
# ---------------------------------------------------------------------------


def _trim(text, limit=MAX_CAPTURE_BYTES) -> str:
    text = text or ''
    if len(text) <= limit:
        return text
    return text[:limit] + '\n…（已截断）'


def _execute_plan(plan: dict) -> dict:
    """Run one plan in a child interpreter; never raises for user-code problems."""
    directory = _make_workspace()
    started = time.perf_counter()
    try:
        root = Path(directory)
        (root / 'driver.py').write_text(_DRIVER_SOURCE, encoding='utf-8')
        (root / 'payload.json').write_text(
            json.dumps({'method': plan['method'], 'cases': [{key: case[key] for key in
                        ('index', 'args', 'mode', 'mutate', 'scalarNode')} for case in plan['cases']]},
                       ensure_ascii=False),
            encoding='utf-8',
        )
        (root / 'user_code.py').write_text(plan['code'], encoding='utf-8')
        environment = {
            'TEMP': directory,
            'TMP': directory,
            'SYSTEMROOT': os.environ.get('SYSTEMROOT', ''),
            'PYTHONUTF8': '1',
            'PYTHONIOENCODING': 'utf-8',
            'PYTHONDONTWRITEBYTECODE': '1',
        }
        command = [sys.executable or 'python', '-I', '-B', '-X', 'utf8', str(root / 'driver.py')]
        timeout_s = max(0.2, RUN_TIMEOUT_MS / 1000)
        try:
            completed = subprocess.run(
                command,
                cwd=directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                'timedOut': True,
                'durationMs': round((time.perf_counter() - started) * 1000, 2),
                'timeoutMs': RUN_TIMEOUT_MS,
                'stderr': f'运行超过 {RUN_TIMEOUT_MS} ms，已强制终止子进程。',
            }
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        result_path = root / 'result.json'
        if not result_path.exists():
            diagnostic = completed.stderr.decode('utf-8', errors='replace')
            return {'fatal': '本地执行器未返回结果。', 'stderr': _trim(diagnostic), 'durationMs': elapsed}
        raw = result_path.read_bytes()[:MAX_RESULT_BYTES]
        try:
            result = json.loads(raw.decode('utf-8', errors='replace'))
        except ValueError:
            return {'fatal': '本地执行器返回了无法解析的结果。', 'durationMs': elapsed}
        if completed.stderr:
            extra = completed.stderr.decode('utf-8', errors='replace')
            result['stderr'] = _trim((result.get('stderr') or '') + ('\n' + extra if extra.strip() else ''))
        # Report the honest end-to-end wall time (interpreter startup included),
        # not just the in-child compute time.
        result['computeMs'] = result.get('durationMs')
        result['durationMs'] = elapsed
        return result
    finally:
        shutil.rmtree(directory, ignore_errors=True)


# ---------------------------------------------------------------------------
# Comparison / response assembly
# ---------------------------------------------------------------------------


def _equal(expected, actual) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(expected - actual) <= 1e-9
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(_equal(a, b) for a, b in zip(expected, actual))
    return expected == actual


def _canonical(value, mode):
    if mode == 'sort_scalars':
        return sorted(value, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    if mode == 'sort_all':
        return sorted(
            [sorted(item, key=lambda entry: json.dumps(entry, ensure_ascii=False, sort_keys=True))
             for item in value],
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
        )
    if mode == 'sort_subsets':
        return sorted(
            [sorted(item, key=lambda entry: json.dumps(entry, ensure_ascii=False, sort_keys=True))
             for item in value],
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
        )
    if mode == 'sort_outer':
        return sorted(value, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    return value


def _check_case(case, item) -> tuple[bool, object, str | None]:
    """Return (passed, display_actual, error)."""
    if item.get('error'):
        return False, None, item['error']
    actual = item.get('actual')
    mode = case.get('mode', 'literal')
    if mode == 'cycle-index':
        expected = case.get('expected')
        passed = actual.get('index') == expected
        if actual.get('index') is None:
            display = 'null'
        else:
            display = f"值为 {actual.get('value')} 的结点（下标 {actual.get('index')}）"
        return passed, display, None
    if mode == 'intersection':
        expected = case.get('expected')
        if actual.get('isNull'):
            return expected is None, 'null', None
        display = (f"值为 {actual.get('value')} 的交点结点" if actual.get('isTarget')
                   else f"值为 {actual.get('value')} 的结点（不是两条链表的公共结点）")
        passed = expected is not None and bool(actual.get('isTarget')) and _equal(expected, actual.get('value'))
        return passed, display, None
    compare = case.get('compare', 'exact')
    expected = case.get('expected')
    if compare != 'exact' and expected is not None and actual is not None:
        passed = _equal(_canonical(expected, compare), _canonical(actual, compare))
    else:
        passed = _equal(expected, actual)
    if not passed and case.get('nodeResult') and expected == [] and actual is None:
        # LeetCode renders an empty linked list / tree as [] while the method
        # legitimately returns None; both mean the same empty structure.
        return True, [], None
    return passed, actual, None


def _display(value) -> str:
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)[:MAX_CASE_ACTUAL_CHARS]


def _assemble(q, plan, executed) -> dict:
    base = {
        'questionId': q['id'],
        'leetcodeNumber': q.get('leetcodeNumber'),
        'title': q['title'],
        'method': plan.get('method'),
        'timeoutMs': RUN_TIMEOUT_MS,
        'sandbox': {
            'mode': 'local-subprocess',
            'isolatedProcess': True,
            'timeoutMs': RUN_TIMEOUT_MS,
            'maxOutputBytes': MAX_CAPTURE_BYTES,
            'note': SANDBOX_NOTE,
        },
    }
    if executed.get('timedOut'):
        return {**base, 'supported': True, 'passed': False, 'timedOut': True, 'cases': [],
                'durationMs': executed.get('durationMs', 0),
                'error': f"运行超时：超过 {RUN_TIMEOUT_MS} ms 未结束，已强制终止子进程。",
                'stdout': '', 'stderr': executed.get('stderr', '')}
    if executed.get('compileError') or executed.get('fatal'):
        message = executed.get('compileError') or executed.get('fatal')
        return {**base, 'supported': True, 'passed': False, 'cases': [],
                'durationMs': executed.get('durationMs', 0), 'error': message,
                'stdout': _trim(executed.get('stdout', '')), 'stderr': _trim(executed.get('stderr', ''))}
    results = executed.get('cases') or []
    by_index = {item.get('index'): item for item in results}
    cases, passed_count = [], 0
    for case in plan['cases']:
        item = by_index.get(case['index'], {'error': '本地执行器未返回该用例的结果。'})
        passed, actual, error = _check_case(case, item)
        if passed:
            passed_count += 1
        display_actual = actual
        if case.get('mode') in ('cycle-index', 'intersection'):
            display_actual_text = actual
        else:
            display_actual_text = _display(actual)
        cases.append({
            'index': case['index'],
            'input': case['input'],
            'expected': case['expectedText'],
            'actual': display_actual_text if error is None else '',
            'passed': bool(passed),
            'error': error,
            'durationMs': item.get('durationMs'),
        })
    total = len(cases)
    passed = bool(total) and passed_count == total
    return {
        **base,
        'supported': True,
        'passed': passed,
        'passedCases': passed_count,
        'totalCases': total,
        'cases': cases,
        'durationMs': executed.get('durationMs', 0),
        'stdout': _trim(executed.get('stdout', '')),
        'stderr': _trim(executed.get('stderr', '')),
        'error': None,
    }


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------


async def run_code(value: dict) -> dict:
    """Execute user code against the question's samples and compare real results."""
    from . import judge_toolchain
    q = _hot100(value.get('questionId'))
    language = value.get('language') or 'python'
    require(isinstance(language, str) and language in SUPPORTED_LANGUAGES, 'INVALID_LANGUAGE')
    capabilities = (await asyncio.to_thread(judge_toolchain.detect))['capabilities']
    capability = capabilities.get(language) or {}
    base = {'questionId': q['id'], 'leetcodeNumber': q.get('leetcodeNumber'), 'title': q['title'],
            'language': language, 'supported': False,
            'sandbox': {
                'mode': 'local-subprocess', 'isolatedProcess': True, 'timeoutMs': RUN_TIMEOUT_MS,
                'maxOutputBytes': MAX_CAPTURE_BYTES, 'note': SANDBOX_NOTE}}
    if not capability.get('available'):
        return {**base, 'reason': capability.get('reason') or UNSUPPORTED_LANGUAGE_REASON}
    code = value.get('code')
    require(isinstance(code, str) and code.strip(), 'INVALID_CODE')
    require(len(code) <= MAX_CODE_CHARS, 'CODE_TOO_LARGE')
    case_index = value.get('caseIndex')
    if case_index is not None:
        require(type(case_index) is int and 0 <= case_index < len(q['samples']), 'INVALID_CASE_INDEX')
    if _is_design_question(q):
        return {**base, 'reason': DESIGN_REASON}
    if language == 'python':
        plan = _build_plan(q, code)
        if plan.get('unsupported'):
            return {**base, 'reason': plan['reason']}
        if plan.get('compileError'):
            return {**base, 'supported': True, 'passed': False, 'cases': [], 'durationMs': 0,
                    'error': plan['compileError'], 'stdout': '', 'stderr': ''}
        if case_index is not None:
            plan = {**plan, 'cases': [dict(plan['cases'][case_index], index=0)]}
        plan['code'] = code
        executed = await asyncio.to_thread(_execute_plan, plan)
    else:
        from . import judge_compiled
        plan = judge_compiled.build_plan(q, code, language)
        if plan.get('unsupported'):
            return {**base, 'reason': plan['reason']}
        if plan.get('compileError'):
            return {**base, 'supported': True, 'passed': False, 'cases': [], 'durationMs': 0,
                    'error': plan['compileError'], 'stdout': '', 'stderr': ''}
        if case_index is not None:
            plan = {**plan, 'cases': [dict(plan['cases'][case_index], index=0)]}
        executed = await asyncio.to_thread(judge_compiled.execute, plan)
        if executed.get('unsupported'):
            return {**base, 'reason': executed['reason']}
    result = _assemble(q, plan, executed)
    result['language'] = language
    result['supported'] = True
    result['compiler'] = ({'name': 'g++', 'version': capability.get('version', ''), 'path': capability.get('path', '')}
                          if language == 'cpp' else
                          {'name': 'javac', 'version': capability.get('version', ''), 'path': capability.get('path', '')}
                          if language == 'java' else
                          {'name': 'python', 'version': capability.get('version', ''), 'path': capability.get('path', '')})
    if language != 'python':
        result['sandbox']['note'] = (
            f'本机 {LANGUAGE_LABELS[language]} 本地编译执行：临时目录 + 独立子进程 + 编译 {judge_compiled.COMPILE_TIMEOUT_MS // 1000} 秒/'
            f'运行 {RUN_TIMEOUT_MS // 1000} 秒超时 + 输出上限 64KB；这不是强安全沙箱，请只运行自己信任的代码。'
        )
        result['sandbox']['compiler'] = capability.get('path', '')
    return result


_SYSTEM_PROMPT = (
    '你是算法学习助手的代码复杂度分析器。只分析用户提交的代码本身，不执行代码，不编造运行结果，'
    '不评价题目难度，不输出 Markdown。严格返回一个 JSON 对象，键为：'
    'timeComplexity（字符串，如 "O(n)"）、spaceComplexity（字符串，如 "O(1)"）、'
    'summary（不超过 120 字的中文结论）、keyRisks（2 到 4 条中文风险点字符串数组，'
    '说明可能的边界、溢出、递归深度或性能问题）。'
)


def _extract_model_json(text: str):
    cleaned = (text or '').strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()
    try:
        return json.loads(cleaned)
    except ValueError:
        start, end = cleaned.find('{'), cleaned.rfind('}')
        require(start >= 0 and end > start, 'AI_INVALID_RESPONSE')
        try:
            return json.loads(cleaned[start:end + 1])
        except ValueError as error:
            raise AppError('AI_INVALID_RESPONSE') from error


def _validate_analysis(payload) -> dict:
    require(isinstance(payload, dict), 'AI_INVALID_RESPONSE')
    time_complexity = payload.get('timeComplexity')
    space_complexity = payload.get('spaceComplexity')
    summary = payload.get('summary')
    risks = payload.get('keyRisks')
    require(isinstance(time_complexity, str) and 0 < len(time_complexity.strip()) <= 120, 'AI_INVALID_RESPONSE')
    require(isinstance(space_complexity, str) and 0 < len(space_complexity.strip()) <= 120, 'AI_INVALID_RESPONSE')
    require(isinstance(summary, str) and 0 < len(summary.strip()) <= 2000, 'AI_INVALID_RESPONSE')
    require(isinstance(risks, list) and 1 <= len(risks) <= 6
            and all(isinstance(item, str) and 0 < len(item.strip()) <= 400 for item in risks), 'AI_INVALID_RESPONSE')
    return {
        'timeComplexity': time_complexity.strip(),
        'spaceComplexity': space_complexity.strip(),
        'summary': summary.strip(),
        'keyRisks': [item.strip() for item in risks],
    }


def _usage_summary(usage):
    if not isinstance(usage, dict):
        return None
    allowed = ('prompt_tokens', 'completion_tokens', 'total_tokens',
               'promptTokens', 'completionTokens', 'totalTokens')
    summary = {key: usage[key] for key in allowed if type(usage.get(key)) is int}
    return summary or None


async def analyze_code(value: dict, course: str, host) -> dict:
    """Ask the host's scoped model (with its ledger/limiter/budget) for complexity analysis."""
    q = _hot100(value.get('questionId'))
    code = value.get('code')
    language = value.get('language') or 'python'
    require(isinstance(language, str) and language in SUPPORTED_LANGUAGES, 'INVALID_LANGUAGE')
    require(isinstance(code, str) and code.strip(), 'INVALID_CODE')
    require(len(code) <= MAX_CODE_CHARS, 'CODE_TOO_LARGE')
    model = host.service(course).model if host is not None else None
    if model is None:
        raise AppError('AI_UNAVAILABLE')
    prompt = json.dumps({
        'leetcodenumber': q.get('leetcodeNumber'),
        'title': q['title'],
        'prompt': q['prompt'][:1200],
        'language': LANGUAGE_LABELS.get(language, language),
        'code': code,
    }, ensure_ascii=False)
    messages = [
        {'role': 'system', 'content': _SYSTEM_PROMPT},
        {'role': 'user', 'content': prompt},
    ]
    started = time.perf_counter()
    try:
        result = await model.generate({
            'messages': messages,
            'maxOutputTokens': 900,
            'responseFormat': {'type': 'json_object'},
        })
    except AppError:
        raise
    except TimeoutError as error:
        raise AppError('AI_TIMEOUT') from error
    except Exception as error:  # never leak provider details or credentials
        raise AppError('AI_UNAVAILABLE') from error
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    require(isinstance(result, dict), 'AI_INVALID_RESPONSE')
    analysis = _validate_analysis(_extract_model_json(result.get('content')))
    analysis['model'] = result.get('model') or 'unknown'
    return {
        'questionId': q['id'],
        'language': language,
        'analysis': analysis,
        'usage': _usage_summary(result.get('usage')),
        'durationMs': duration_ms,
        'promptVersion': 'code-complexity-v1',
    }


async def dispatch(rest: str, request, course: str, host):
    """Workbench feature entry point used by ``workbench_api`` (rest = run/analyze/capabilities)."""
    from . import judge_toolchain
    if rest == 'capabilities':
        require(request.method == 'GET', 'METHOD_NOT_ALLOWED')
        force = request.query_params.get('refresh') == '1'
        return JSONResponse({'ok': True, **await asyncio.to_thread(judge_toolchain.detect, force)})
    if rest not in ('run', 'analyze'):
        return None
    from .app import connected_work, json_body
    require(request.method == 'POST', 'METHOD_NOT_ALLOWED')
    value = await json_body(request, 65536)
    require('courseId' not in value or value['courseId'] == course, 'COURSE_MISMATCH')
    if rest == 'run':
        result = await connected_work(request, run_code(value))
        return JSONResponse({'ok': True, 'result': result})
    analysis = await connected_work(request, analyze_code(value, course, host))
    return JSONResponse({'ok': True, **analysis})


# ---------------------------------------------------------------------------
# Self-check CLI: run every official Python reference solution against its samples
# ---------------------------------------------------------------------------


async def _self_check(languages=('python',)) -> dict:
    hot = [q for q in bank()['questions'] if q.get('category') == 'hot100']
    reports = {}
    for language in languages:
        supported = passed = 0
        failures, unsupported = [], []
        for q in hot:
            result = await run_code({'questionId': q['id'], 'language': language,
                                     'code': q['solutions'].get(language, '')})
            if os.environ.get('XUEYA_SELFCHECK_PROGRESS') == '1':
                print(f"{language} {q['id']} supported={bool(result.get('supported'))} passed={bool(result.get('passed'))}",
                      file=sys.stderr, flush=True)
            if not result.get('supported'):
                unsupported.append({'id': q['id'], 'number': q.get('leetcodeNumber'),
                                    'title': q['title'], 'reason': result.get('reason')})
                continue
            supported += 1
            if result.get('passed'):
                passed += 1
            else:
                failures.append({
                    'id': q['id'], 'number': q.get('leetcodeNumber'), 'title': q['title'],
                    'error': result.get('error'),
                    'cases': [{'index': case['index'], 'expected': case['expected'],
                               'actual': case['actual'], 'error': case['error']}
                              for case in result.get('cases', []) if not case['passed']],
                    'stderr': (result.get('stderr') or '')[-1500:],
                })
        reports[language] = {
            'total': len(hot),
            'supported': supported,
            'passed': passed,
            'supportRate': round(supported / len(hot) * 100, 1),
            'passRate': round(passed / len(hot) * 100, 1),
            'unsupported': unsupported,
            'failures': failures,
        }
    if len(reports) == 1:
        return next(iter(reports.values()))
    return {'languages': reports}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] != ['--self-check']:
        print('usage: python -m backend.xueya.code_runner --self-check [--languages python,cpp,java]')
        return 2
    languages = ('python',)
    for index, value in enumerate(argv):
        if value == '--languages' and index + 1 < len(argv):
            languages = tuple(item.strip() for item in argv[index + 1].split(',') if item.strip())
    from . import judge_toolchain
    available = judge_toolchain.available_languages()
    unsupported = [language for language in languages if language not in available]
    if unsupported:
        print(json.dumps({'error': '语言在本机不可用：' + ','.join(unsupported),
                          'available': available}, ensure_ascii=False))
        return 1
    report = asyncio.run(_self_check(languages))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':  # pragma: no cover - manual tool
    raise SystemExit(main())
