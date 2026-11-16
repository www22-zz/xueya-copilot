#!/usr/bin/env python
"""Generate writable Hot100 starter skeletons from the official three-language solutions.

Contract (AGENT_PLAN.md §2.4): 'backend/xueya/data/hot100_starters.json'

    {"version": "hot100-starters-1",
     "questions": {"h100-01": {"python": "...", "cpp": "...", "java": "..."}, ...}}

A starter keeps only what the learner must supply: the class (Solution or the
design class such as LRUCache / Trie / MinStack / MedianFinder), the official
public method/constructor signatures with their parameter lists, and a
placeholder comment. Reference bodies, helper methods, private data members,
implementation imports and other answer details are dropped, so a starter can
never leak the official solution.

Usage::

    .venv/Scripts/python.exe scripts/build_practice_starters.py            # write
    .venv/Scripts/python.exe scripts/build_practice_starters.py --check    # verify up to date
    .venv/Scripts/python.exe scripts/build_practice_starters.py --dump h100-01
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK_FILE = ROOT / 'backend' / 'xueya' / 'data' / 'practice_bank.json'
OUT_FILE = ROOT / 'backend' / 'xueya' / 'data' / 'hot100_starters.json'
STARTER_VERSION = 'hot100-starters-1'
LANGS = ('python', 'cpp', 'java')
PLACEHOLDER = '请在这里编写代码'
PY_PLACEHOLDER = '# ' + PLACEHOLDER
CPP_PLACEHOLDER = '// ' + PLACEHOLDER
JAVA_PLACEHOLDER = '// ' + PLACEHOLDER
NODE_TYPES = ('ListNode', 'TreeNode', 'Node')


class StarterError(RuntimeError):
    """Raised when a question cannot be reduced to a clean starter."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def load_hot100() -> list[dict]:
    raw = json.loads(BANK_FILE.read_text(encoding='utf-8'))
    hot = [q for q in raw.get('questions', []) if q.get('category') == 'hot100']
    if len(hot) != 100 or len({q['id'] for q in hot}) != 100:
        raise StarterError(f'expected 100 unique Hot100 questions, found {len(hot)}')
    return hot


def _sanitize(source: str) -> str:
    """Remove comments and neutralise string/char literal bodies for brace scanning."""
    out: list[str] = []
    index, length = 0, len(source)
    while index < length:
        char = source[index]
        nxt = source[index + 1] if index + 1 < length else ''
        if char == '/' and nxt == '/':
            while index < length and source[index] != '\n':
                index += 1
            continue
        if char == '/' and nxt == '*':
            index += 2
            while index + 1 < length and not (source[index] == '*' and source[index + 1] == '/'):
                out.append('\n' if source[index] == '\n' else ' ')
                index += 1
            index = min(length, index + 2)
            continue
        if char in ('"', "'"):
            quote = char
            out.append(quote)
            index += 1
            while index < length:
                if source[index] == '\\':
                    out.append(' ')
                    index += 2
                    continue
                if source[index] == quote:
                    out.append(quote)
                    index += 1
                    break
                out.append('\n' if source[index] == '\n' else ' ')
                index += 1
            continue
        out.append(char)
        index += 1
    return ''.join(out)


def _match_pair(text: str, start: int, opening: str = '{', closing: str = '}') -> int:
    depth = 0
    for position in range(start, len(text)):
        char = text[position]
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return position
    raise StarterError('unbalanced brackets in the official solution')


def _split_top_level(text: str) -> list[str]:
    """Split a parameter list on commas outside <>, (), [] and {}."""
    parts: list[str] = []
    current: list[str] = []
    round_depth = angle_depth = square_depth = 0
    for char in text:
        if char == '(':
            round_depth += 1
        elif char == ')':
            round_depth = max(0, round_depth - 1)
        elif char == '<':
            angle_depth += 1
        elif char == '>':
            angle_depth = max(0, angle_depth - 1)
        elif char == '[':
            square_depth += 1
        elif char == ']':
            square_depth = max(0, square_depth - 1)
        if char == ',' and round_depth == angle_depth == square_depth == 0:
            parts.append(''.join(current).strip())
            current = []
            continue
        current.append(char)
    tail = ''.join(current).strip()
    if tail:
        parts.append(tail)
    return [part for part in parts if part]


def _normalize_params(params_text: str) -> str:
    cleaned = []
    for part in _split_top_level(params_text):
        part = re.sub(r'\s+', ' ', part).strip()
        if part in ('', 'void'):
            continue
        cleaned.append(part)
    return ', '.join(cleaned)


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def _py_signature(method: ast.FunctionDef) -> str:
    clone = ast.FunctionDef(
        name=method.name,
        args=deepcopy(method.args),
        body=[ast.Pass()],
        decorator_list=[],
        returns=deepcopy(method.returns),
        type_comment=None,
        type_params=deepcopy(getattr(method, 'type_params', [])),
    )
    module = ast.Module(body=[clone], type_ignores=[])
    ast.fix_missing_locations(module)
    text = ast.unparse(module)
    signature = text.splitlines()[0].strip()
    if not signature.startswith('def ') or not signature.endswith(':'):
        raise StarterError(f'cannot isolate the signature of Python method {method.name!r}')
    return signature


def _python_api(solution: str, question_id: str) -> tuple[list[str], str, list[ast.FunctionDef]]:
    try:
        tree = ast.parse(solution)
    except SyntaxError as error:  # pragma: no cover - bank solutions always parse
        raise StarterError(f'{question_id}: official Python solution does not parse: {error}') from error
    imports = [ast.unparse(node) for node in tree.body
               if isinstance(node, ast.ImportFrom) and node.module == 'typing']
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if len(classes) != 1:
        raise StarterError(f'{question_id}: expected exactly one Python class, got {[c.name for c in classes]}')
    py_class = classes[0]
    methods = [node for node in py_class.body
               if isinstance(node, ast.FunctionDef)
               and (node.name == '__init__' or not node.name.startswith('_'))]
    if not methods:
        raise StarterError(f'{question_id}: the Python class exposes no public method')
    names = [method.name for method in methods]
    if names.count('__init__') > 1:
        raise StarterError(f'{question_id}: duplicate __init__ in the Python class')
    return imports, py_class.name, methods


def _python_starter(imports: list[str], class_name: str, methods: list[ast.FunctionDef]) -> str:
    lines: list[str] = list(imports)
    if lines:
        lines.append('')
    lines.append(f'class {class_name}:')
    for index, method in enumerate(methods):
        if index:
            lines.append('')
        lines.append('    ' + _py_signature(method))
        lines.append('        ' + PY_PLACEHOLDER)
        lines.append('        pass')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# C++
# ---------------------------------------------------------------------------


def _find_class(source: str, class_name: str, *, java: bool = False) -> tuple[str, int, int]:
    if java:
        pattern = re.compile(r'\b(?:public\s+)?(?:final\s+|abstract\s+)?class\s+'
                             + re.escape(class_name) + r'\b[^{;]*\{')
    else:
        pattern = re.compile(r'\b(?:class|struct)\s+' + re.escape(class_name) + r'\b[^{;]*\{')
    match = pattern.search(source)
    if not match:
        raise StarterError(f'cannot find class {class_name!r} in the official solution')
    open_index = match.end() - 1
    return match.group(0), open_index, _match_pair(source, open_index)


def _scan_members(source: str, open_index: int, close_index: int):
    """Yield ('access', name) and ('block', text) entries of one class body."""
    position = open_index + 1
    buffer: list[str] = []
    while position < close_index:
        char = source[position]
        if char == '{':
            text = ''.join(buffer).strip()
            buffer = []
            yield ('block', text)
            position = _match_pair(source, position) + 1
            continue
        if char == ';':
            text = ''.join(buffer).strip()
            buffer = []
            if text:
                yield ('statement', text)
            position += 1
            continue
        if char == ':':
            stripped = ''.join(buffer).strip()
            if stripped in ('public', 'private', 'protected'):
                yield ('access', stripped)
                buffer = []
                position += 1
                continue
        buffer.append(char)
        position += 1
    tail = ''.join(buffer).strip()
    if tail:
        yield ('statement', tail)


_CPP_MODIFIERS = ('static', 'inline', 'virtual', 'explicit', 'constexpr', 'consteval', 'friend')


def _cpp_method(text: str, class_name: str) -> dict | None:
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return None
    if re.match(r'^(?:template\s*<[^>]*>\s*)?(?:class|struct|union|enum)\b', text):
        return None
    if text.startswith('friend '):
        return None
    paren = text.find('(')
    if paren <= 0:
        return None
    prefix = text[:paren].strip()
    name_match = re.search(r'([A-Za-z_]\w*)$', prefix)
    if not name_match:
        return None
    name = name_match.group(1)
    before = prefix[:name_match.start()].strip()
    modifiers = []
    for word in _CPP_MODIFIERS:
        pattern = re.compile(r'\b' + word + r'\b')
        if pattern.search(before):
            if word != 'friend':
                modifiers.append(word)
            before = pattern.sub(' ', before).strip()
    close = _match_pair(text, paren, '(', ')')
    params = _normalize_params(text[paren + 1:close])
    suffix_words = re.findall(r'[A-Za-z_]\w*', text[close + 1:])
    qualifier = ' const' if 'const' in suffix_words else ''
    if name == class_name:
        return {'name': name, 'constructor': True,
                'signature': ' '.join(modifiers + [class_name]) + '(' + params + ')'}
    if not before:
        return None
    signature = ' '.join(modifiers + [before, name]) + '(' + params + ')' + qualifier
    return {'name': name, 'constructor': False, 'signature': signature, 'returnType': before}


def _cpp_default(return_type: str) -> str | None:
    text = re.sub(r'\b(const|volatile|typename|std::)\b', ' ', return_type)
    text = re.sub(r'\s+', '', text)
    if text in ('', 'void'):
        return None
    if text.endswith('*') or text.endswith('*&'):
        return 'nullptr'
    if text.endswith('&'):
        text = text[:-1]
    scalars = {
        'int': '0', 'long': '0', 'longlong': '0', 'short': '0', 'unsigned': '0',
        'unsignedint': '0', 'unsignedlong': '0', 'unsignedlonglong': '0', 'size_t': '0',
        'int32_t': '0', 'int64_t': '0', 'uint32_t': '0', 'uint64_t': '0',
        'double': '0.0', 'float': '0.0', 'longdouble': '0.0',
        'bool': 'false', 'char': "'\\0'",
        'string': '""',
    }
    if text in scalars:
        return scalars[text]
    compound = ('vector<', 'pair<', 'map<', 'unordered_map<', 'set<', 'unordered_set<',
                'multiset<', 'queue<', 'stack<', 'priority_queue<', 'array<')
    if text.startswith(compound) and text.endswith('>'):
        return '{}'
    if text in NODE_TYPES:
        return '{}'
    raise StarterError(f'unsupported C++ return type {return_type!r}')


def _cpp_starter(class_name: str, methods: list[dict]) -> str:
    lines = [f'class {class_name} {{', 'public:']
    for index, method in enumerate(methods):
        if index:
            lines.append('')
        lines.append('    ' + method['signature'] + ' {')
        lines.append('        ' + CPP_PLACEHOLDER)
        if not method['constructor']:
            default = _cpp_default(method['returnType'])
            if default is not None:
                lines.append('        return ' + default + ';')
        lines.append('    }')
    lines.append('};')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------


def _java_method(text: str, class_name: str) -> dict | None:
    text = re.sub(r'\s+', ' ', text).strip()
    while text.startswith('@'):
        token = re.match(r'@[\w.]+', text)
        if not token:
            break
        text = text[token.end():].strip()
        if text.startswith('('):
            text = text[_match_pair(text, 0, '(', ')') + 1:].strip()
    if not text:
        return None
    words = text.split(' ')
    access = 'package'
    modifiers: list[str] = []
    while words and words[0] in ('public', 'protected', 'private', 'static', 'final',
                                 'synchronized', 'native', 'abstract', 'default', 'strictfp'):
        word = words.pop(0)
        if word in ('public', 'protected', 'private'):
            access = word
        elif word in ('static',):
            modifiers.append(word)
    rest = ' '.join(words).strip()
    if not rest or rest.startswith(('class ', 'interface ', 'enum ', 'record ')):
        return None
    paren = rest.find('(')
    if paren <= 0:
        return None
    prefix = rest[:paren].strip()
    name_match = re.search(r'([A-Za-z_]\w*)$', prefix)
    if not name_match:
        return None
    name = name_match.group(1)
    before = prefix[:name_match.start()].strip()
    close = _match_pair(rest, paren, '(', ')')
    params = _normalize_params(rest[paren + 1:close])
    if name == class_name:
        return {'name': name, 'constructor': True, 'access': access,
                'signature': ' '.join(modifiers + ['public', class_name]) + '(' + params + ')'}
    if not before:
        return None
    signature = ' '.join(modifiers + ['public', before, name]) + '(' + params + ')'
    return {'name': name, 'constructor': False, 'access': access,
            'signature': signature, 'returnType': before}


def _java_default(return_type: str) -> str | None:
    text = re.sub(r'\s+', '', return_type).replace('java.util.', '')
    if text in ('void', ''):
        return None
    if text.endswith('[]'):
        base = text
        dimensions = 0
        while base.endswith('[]'):
            base = base[:-2]
            dimensions += 1
        return f'new {base}[0]' + '[]' * (dimensions - 1)
    scalars = {
        'int': '0', 'long': '0', 'short': '0', 'byte': '0',
        'double': '0.0', 'float': '0.0', 'boolean': 'false', 'char': "'\\0'",
        'Integer': '0', 'Long': '0L', 'Short': '(short) 0', 'Byte': '(byte) 0',
        'Double': '0.0', 'Float': '0.0f', 'Boolean': 'false', 'Character': "'\\0'",
        'String': '""',
    }
    if text in scalars:
        return scalars[text]
    if text.startswith(('List<', 'ArrayList<', 'LinkedList<')):
        return 'new ArrayList<>()'
    if text.startswith(('Set<', 'HashSet<')):
        return 'new HashSet<>()'
    if text.startswith(('Map<', 'HashMap<')):
        return 'new HashMap<>()'
    if text.startswith(('Queue<', 'Deque<', 'ArrayDeque<')):
        return 'new ArrayDeque<>()'
    if text in NODE_TYPES:
        return 'null'
    raise StarterError(f'unsupported Java return type {return_type!r}')


def _java_starter(class_name: str, methods: list[dict]) -> str:
    lines = [f'class {class_name} {{']
    for index, method in enumerate(methods):
        if index:
            lines.append('')
        lines.append('    ' + method['signature'] + ' {')
        lines.append('        ' + JAVA_PLACEHOLDER)
        if not method['constructor']:
            default = _java_default(method['returnType'])
            if default is not None:
                lines.append('        return ' + default + ';')
        lines.append('    }')
    lines.append('}')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# Cross-language extraction
# ---------------------------------------------------------------------------


def _pick_methods(parsed: list[dict], expected: list[str], language: str, question_id: str,
                  class_name: str, *, require_constructor: bool = False) -> list[dict]:
    keep: dict[str, dict] = {}
    for item in parsed:
        if item['constructor']:
            keep.setdefault(class_name, item)
        elif item['name'] in expected:
            keep.setdefault(item['name'], item)
    wanted = [name for name in expected if name != '__init__']
    if require_constructor:
        wanted.append(class_name)
    missing = [name for name in wanted if name not in keep]
    if missing:
        parsed_names = [item['name'] for item in parsed]
        raise StarterError(f'{question_id}: {language} starter is missing {missing}; '
                           f'parsed public methods were {parsed_names}')
    ordered = []
    for name in expected:
        if name == '__init__':
            if class_name in keep:
                ordered.append(keep[class_name])
        else:
            ordered.append(keep[name])
    return ordered


def build_question(q: dict) -> dict:
    question_id = q['id']
    imports, class_name, py_methods = _python_api(q['solutions']['python'], question_id)
    expected = [method.name for method in py_methods]
    init_node = next((method for method in py_methods if method.name == '__init__'), None)
    init_arity = 0
    if init_node is not None:
        args = init_node.args
        init_arity = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs) + len(args.kwarg or [])
    require_constructor = init_arity > 1
    python_source = _python_starter(imports, class_name, py_methods)

    cpp_source = _sanitize(q['solutions']['cpp'])
    cpp_declaration, cpp_open, cpp_close = _find_class(cpp_source, class_name)
    cpp_access = 'public' if cpp_declaration.lstrip().startswith('struct') else 'private'
    parsed_cpp: list[dict] = []
    for kind, *payload in _scan_members(cpp_source, cpp_open, cpp_close):
        if kind == 'access':
            cpp_access = payload[0]
            continue
        if kind != 'block':
            continue
        method = _cpp_method(payload[0], class_name)
        if method and cpp_access == 'public':
            parsed_cpp.append(method)
    cpp_methods = _pick_methods(parsed_cpp, expected, 'cpp', question_id, class_name,
                                require_constructor=require_constructor)

    java_source = _sanitize(q['solutions']['java'])
    _, java_open, java_close = _find_class(java_source, class_name, java=True)
    parsed_java: list[dict] = []
    for kind, *payload in _scan_members(java_source, java_open, java_close):
        if kind != 'block':
            continue
        method = _java_method(payload[0], class_name)
        if method and method['access'] == 'public':
            parsed_java.append(method)
    java_methods = _pick_methods(parsed_java, expected, 'java', question_id, class_name,
                                require_constructor=require_constructor)

    return {
        'python': python_source,
        'cpp': _cpp_starter(class_name, cpp_methods),
        'java': _java_starter(class_name, java_methods),
    }


# ---------------------------------------------------------------------------
# Static validation: never leak the official implementation
# ---------------------------------------------------------------------------


def _solution_lines(solution: str) -> set[str]:
    return {line.strip() for line in solution.splitlines() if line.strip()}


_PLACEHOLDER_RETURNS = {
    'return 0;', 'return 0L;', 'return 0.0;', 'return 0.0f;', 'return false;',
    'return true;', 'return null;', 'return nullptr;', 'return "";',
    r"return '\0';", 'return {};', 'return (short) 0;', 'return (byte) 0;',
}


def _is_placeholder_return(line: str) -> bool:
    return line in _PLACEHOLDER_RETURNS or bool(re.fullmatch(r'return new [^;]+;', line))


_STRUCTURAL_ENDINGS = (':', '{', '}', '};')
_STRUCTURAL_STARTS = ('class ', 'struct ', 'from ', 'import ', 'using ', 'package ',
                      'public:', 'private:', 'protected:', '@')


def _validate_starter(question: dict, language: str, starter: str, *,
                      design: bool = False) -> None:
    question_id = question['id']
    if PLACEHOLDER not in starter:
        raise StarterError(f'{question_id}/{language}: starter is missing the placeholder comment')
    if not starter.strip():
        raise StarterError(f'{question_id}/{language}: starter is empty')
    if re.search(r'\b(for|while|switch)\s*\(', starter):
        raise StarterError(f'{question_id}/{language}: starter contains an implementation loop')
    if re.search(r'^\s*(if|elif|else|for|while|try|with)\b', starter, re.M):
        raise StarterError(f'{question_id}/{language}: starter contains Python implementation statements')
    if language == 'python':
        try:
            compile(starter, f'{question_id}-starter.py', 'exec')
        except SyntaxError as error:
            raise StarterError(f'{question_id}/{language}: starter is not valid Python: {error}') from error
    solution = question['solutions'][language]
    solution_lines = _solution_lines(solution)
    for line in starter.splitlines():
        stripped = line.strip()
        if not stripped or stripped == 'pass' or stripped.startswith(('#', '//')):
            continue
        if _is_placeholder_return(stripped):
            continue
        if stripped in solution_lines and not (stripped.endswith(_STRUCTURAL_ENDINGS)
                                               or stripped.startswith(_STRUCTURAL_STARTS)):
            raise StarterError(f'{question_id}/{language}: starter kept a non-structural solution line: {stripped!r}')
    solution_line_count = max(1, len([line for line in solution.splitlines() if line.strip()]))
    starter_line_count = len([line for line in starter.splitlines() if line.strip()])
    limit = max(28, round(solution_line_count * 1.5)) if design else max(12, round(solution_line_count * 0.5))
    if starter_line_count > limit:
        raise StarterError(f'{question_id}/{language}: starter has {starter_line_count} lines, '
                           f'too close to the {solution_line_count}-line official solution')


def build() -> dict:
    hot = load_hot100()
    questions: dict[str, dict] = {}
    errors: list[str] = []
    for q in hot:
        try:
            starters = build_question(q)
            design = '__init__' in starters['python']
            for language in LANGS:
                _validate_starter(q, language, starters[language], design=design)
            questions[q['id']] = starters
        except StarterError as error:
            errors.append(str(error))
    if errors:
        raise StarterError('\n'.join(errors))
    return {
        'version': STARTER_VERSION,
        'source': 'backend/xueya/data/practice_bank.json solutions (official signatures only)',
        'questions': questions,
    }


def payload_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='verify the committed file is up to date')
    parser.add_argument('--dump', default='', help='print the starter of one question id')
    options = parser.parse_args(argv)
    try:
        payload = build()
    except StarterError as error:
        print(f'starter build failed:\n{error}', file=sys.stderr)
        return 1
    if options.dump:
        starters = payload['questions'].get(options.dump)
        if not starters:
            print(f'unknown question id {options.dump!r}', file=sys.stderr)
            return 2
        for language in LANGS:
            print(f'===== {language} =====')
            print(starters[language])
        return 0
    text = payload_text(payload)
    if options.check:
        current = OUT_FILE.read_text(encoding='utf-8') if OUT_FILE.exists() else ''
        if current != text:
            print(f'{OUT_FILE} is out of date; run scripts/build_practice_starters.py', file=sys.stderr)
            return 1
        print(f'{OUT_FILE} is up to date ({len(payload["questions"])} questions)')
        return 0
    OUT_FILE.write_text(text, encoding='utf-8')
    total = sum(len(starters[language]) for starters in payload['questions'].values()
                for language in LANGS)
    print(f'wrote {OUT_FILE} ({len(payload["questions"])} questions, {total} starter chars)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
