"""Every Hot100 code question ships a writable three-language starter skeleton.

The starters are produced by scripts/build_practice_starters.py from the official
solutions and contain only the class plus the public method/constructor signatures:
no reference body, no helper methods, no implementation statements. The practice
editor uses them as the initial code, keeps saved user code untouched, and the
official solutions remain behind "查看完整题解" (practice-view solutionBlock).
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
import typing
from pathlib import Path

import pytest

from backend.xueya import practice_bank

ROOT = Path(__file__).resolve().parents[1]
STARTER_FILE = ROOT / 'backend' / 'xueya' / 'data' / 'hot100_starters.json'
BUILD_SCRIPT = ROOT / 'scripts' / 'build_practice_starters.py'
VIEW_FILE = ROOT / 'frontend' / 'js' / 'practice-view.js'
PLACEHOLDER = '请在这里编写代码'
LANGUAGES = ('python', 'cpp', 'java')
STARTER_VERSION = 'hot100-starters-1'
PLACEHOLDER_RETURNS = {
    'return 0;', 'return 0L;', 'return 0.0;', 'return 0.0f;',
    'return false;', 'return true;', 'return null;', 'return nullptr;',
    'return "";', r"return '\0';", 'return {};',
    'return (short) 0;', 'return (byte) 0;',
}


def hot100():
    return [q for q in practice_bank.questions() if q['category'] == 'hot100']


def starter_catalog():
    raw = json.loads(STARTER_FILE.read_text(encoding='utf-8'))
    assert raw.get('version') == STARTER_VERSION
    return raw['questions']


def python_api(question):
    tree = ast.parse(question['solutions']['python'])
    py_class = [node for node in tree.body if isinstance(node, ast.ClassDef)][0]
    methods = [node for node in py_class.body if isinstance(node, ast.FunctionDef)
               and (node.name == '__init__' or not node.name.startswith('_'))]
    return py_class.name, methods


def python_starter_api(starter):
    tree = ast.parse(starter)
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    assert len(classes) == 1
    methods = [node for node in classes[0].body if isinstance(node, ast.FunctionDef)]
    return classes[0].name, methods


def signature_shape(method):
    args = method.args
    names = [argument.arg for argument in args.posonlyargs + args.args]
    annotations = [ast.unparse(argument.annotation) if argument.annotation is not None else None
                   for argument in args.posonlyargs + args.args]
    returns = ast.unparse(method.returns) if method.returns is not None else None
    return names, annotations, returns


def _is_placeholder_return(line):
    if line in PLACEHOLDER_RETURNS:
        return True
    return bool(re.fullmatch(r'return new [^;]+;', line))


def test_starter_catalog_covers_all_hot100_questions_in_three_languages():
    catalog = starter_catalog()
    rows = hot100()
    assert set(catalog) == {q['id'] for q in rows}
    assert len(catalog) == 100
    for question_id, entry in catalog.items():
        assert set(entry) == set(LANGUAGES), question_id
        for language in LANGUAGES:
            text = entry[language]
            assert isinstance(text, str) and text.strip(), (question_id, language)
            assert PLACEHOLDER in text, (question_id, language)
            assert len(text) <= 4000, (question_id, language)


def test_practice_bank_attaches_validated_starter_code():
    catalog = starter_catalog()
    rows = hot100()
    assert len(rows) == 100
    for question in rows:
        assert question.get('starterCode') == catalog[question['id']], question['id']
        assert question['starterCode']['python'] != question['solutions']['python']


def test_python_starter_keeps_the_exact_official_signatures():
    catalog = starter_catalog()
    for question in hot100():
        class_name, official_methods = python_api(question)
        starter_class, starter_methods = python_starter_api(catalog[question['id']]['python'])
        assert starter_class == class_name
        assert [method.name for method in starter_methods] == [method.name for method in official_methods]
        for official, starter in zip(official_methods, starter_methods):
            assert signature_shape(starter) == signature_shape(official), (question['id'], official.name)


def test_cpp_and_java_starters_contain_every_public_signature():
    catalog = starter_catalog()
    for question in hot100():
        class_name, methods = python_api(question)
        for language in ('cpp', 'java'):
            text = catalog[question['id']][language]
            solution = question['solutions'][language]
            assert re.search(r'\bclass\s+' + re.escape(class_name) + r'\b', text), (question['id'], language)
            for method in methods:
                if method.name == '__init__':
                    # a no-argument __init__ may be implicit in the compiled solution
                    if not re.search(r'\b' + re.escape(class_name) + r'\s*\(', solution):
                        continue
                    name = class_name
                else:
                    name = method.name
                assert re.search(r'\b' + re.escape(name) + r'\s*\(', text), (question['id'], language, name)


def test_starters_never_contain_the_official_implementation():
    catalog = starter_catalog()
    for question in hot100():
        class_name, methods = python_api(question)
        design = any(method.name == '__init__' for method in methods)
        for language in LANGUAGES:
            starter = catalog[question['id']][language]
            solution = question['solutions'][language]
            # 1) no control flow and no assignment/initialiser survives
            assert not re.search(r'\b(if|for|while|switch|else|elif|try|catch)\b', starter), (question['id'], language)
            assert '=' not in starter, (question['id'], language)
            # 2) the only return statements are neutral placeholder defaults
            for line in starter.splitlines():
                stripped = line.strip()
                if stripped.startswith('return'):
                    assert _is_placeholder_return(stripped), (question['id'], language, stripped)
            # 3) no implementation statement line from the official solution was kept
            solution_lines = {line.strip() for line in solution.splitlines() if line.strip()}
            starter_lines = {line.strip() for line in starter.splitlines() if line.strip()}
            for line in solution_lines:
                if line in PLACEHOLDER_RETURNS or _is_placeholder_return(line):
                    continue
                if line.startswith(('#', '//', '/*', '*', '@', 'def ', 'class ', 'from ', 'import ', 'using ', 'package ')):
                    continue
                if line.endswith((':', ';', '{', '}', '};', 'public:', 'private:', 'protected:')):
                    continue
                if re.search(r'[=+\-*/]|\+\+|--|push_back|\.push\(|\.pop\(|append\(|insert\(|erase\(|\breturn\b|\bif\b|\bfor\b|\bwhile\b', line):
                    assert line not in starter_lines, (question['id'], language, line)
            # 4) the starter is far smaller than the official answer
            solution_line_count = max(1, len([line for line in solution.splitlines() if line.strip()]))
            starter_line_count = len([line for line in starter.splitlines() if line.strip()])
            limit = max(4 * len(methods) + 8, round(solution_line_count * 0.5)) if design else max(12, round(solution_line_count * 0.5))
            assert starter_line_count <= limit, (question['id'], language, starter_line_count, solution_line_count, limit)


def test_python_starters_execute_with_placeholder_bodies():
    class ListNode:
        def __init__(self, val=0, next=None):
            self.val, self.next = val, next
    class TreeNode:
        def __init__(self, val=0, left=None, right=None):
            self.val, self.left, self.right = val, left, right
    class Node:
        def __init__(self, val=0, next=None, random=None):
            self.val, self.next, self.random = val, next, random
    scope = {'ListNode': ListNode, 'TreeNode': TreeNode, 'Node': Node, '__name__': 'starter'}
    scope.update({name: value for name, value in vars(typing).items() if not name.startswith('_')})
    catalog = starter_catalog()
    for question in hot100():
        class_name, methods = python_api(question)
        namespace = dict(scope)
        exec(compile(catalog[question['id']]['python'], question['id'] + '-starter.py', 'exec'), namespace)
        cls = namespace[class_name]
        assert isinstance(cls, type)
        for method in methods:
            assert callable(getattr(cls, method.name, None)), (question['id'], method.name)
    namespace = dict(scope)
    exec(compile(catalog['h100-53']['python'], 'h100-53-starter.py', 'exec'), namespace)
    assert namespace['Solution']().numIslands([['1', '0'], ['0', '1']]) is None


def _compiler(name):
    return shutil.which(name)


CPP_PRELUDE = '''#include <bits/stdc++.h>
using namespace std;
struct ListNode { int val; ListNode *next; ListNode() : val(0), next(nullptr) {} ListNode(int x) : val(x), next(nullptr) {} ListNode(int x, ListNode *n) : val(x), next(n) {} };
struct TreeNode { int val; TreeNode *left; TreeNode *right; TreeNode() : val(0), left(nullptr), right(nullptr) {} TreeNode(int x) : val(x), left(nullptr), right(nullptr) {} TreeNode(int x, TreeNode *l, TreeNode *r) : val(x), left(l), right(r) {} };
struct Node { int val; Node *next; Node *random; Node() : val(0), next(nullptr), random(nullptr) {} Node(int x) : val(x), next(nullptr), random(nullptr) {} };
'''

JAVA_NODES = {
    'TreeNode': 'class TreeNode { int val; TreeNode left, right; TreeNode() {} TreeNode(int v) { val = v; } TreeNode(int v, TreeNode l, TreeNode r) { val = v; left = l; right = r; } }\n',
    'ListNode': 'class ListNode { int val; ListNode next; ListNode() {} ListNode(int v) { val = v; } ListNode(int v, ListNode n) { val = v; next = n; } }\n',
    'Node': 'class Node { int val; Node next; Node random; Node() {} Node(int v) { val = v; } }\n',
}


@pytest.mark.skipif(_compiler('g++') is None, reason='no C++ compiler on this machine')
def test_representative_cpp_starters_compile(tmp_path):
    catalog = starter_catalog()
    ids = ['h100-01', 'h100-53', 'h100-41', 'h100-38', 'lc-208', 'h100-79']
    for index, question_id in enumerate(ids):
        source = tmp_path / f'starter_{index}.cpp'
        source.write_text(CPP_PRELUDE + catalog[question_id]['cpp'], encoding='utf-8')
        result = subprocess.run([_compiler('g++'), '-std=c++17', '-fsyntax-only', '-w', str(source)],
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
        assert result.returncode == 0, (question_id, result.stderr[-1500:])


@pytest.mark.skipif(_compiler('javac') is None, reason='no Java compiler on this machine')
def test_representative_java_starters_compile(tmp_path):
    catalog = starter_catalog()
    ids = ['h100-01', 'h100-53', 'h100-41', 'h100-38', 'lc-208', 'h100-79']
    files = []
    for index, question_id in enumerate(ids):
        package = f'p{index}'
        directory = tmp_path / package
        directory.mkdir()
        nodes = ''
        starter = catalog[question_id]['java']
        for name, definition in JAVA_NODES.items():
            if re.search(r'(?<!Tree)(?<!List)\b' + name + r'\b', starter):
                nodes += definition
        path = directory / 'Starter.java'
        path.write_text(f'package {package};\nimport java.util.*;\n' + nodes + starter, encoding='utf-8')
        files.append(str(path))
    classes = tmp_path / 'classes'
    classes.mkdir()
    result = subprocess.run([_compiler('javac'), '-encoding', 'UTF-8', '-d', str(classes), *files],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert result.returncode == 0, result.stderr[-2500:]


def test_build_script_regenerates_the_committed_catalog():
    result = subprocess.run([sys.executable, str(BUILD_SCRIPT), '--check'],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=str(ROOT))
    assert result.returncode == 0, (result.stdout + result.stderr)[-2500:]


def test_practice_editor_uses_starters_and_never_overwrites_user_code():
    source = VIEW_FILE.read_text(encoding='utf-8')
    assert 'q?.starterCode?.[language]' in source
    assert 'defaultCodeFor' in source
    assert 'isTemplateCode' in source
    assert '请在这里编写代码' not in source, 'the placeholder text must come from the server starter'
    # "查看完整题解" keeps rendering the official solutions
    assert 'solutionBlock' in source
    block = source[source.find('function solutionBlock'):]
    assert 'q.solutions[language]' in block
