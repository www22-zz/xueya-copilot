"""Real C++17 / Java compiled execution for the Hot100 code workbench.

The Python path lives in :mod:`backend.xueya.code_runner`; this module reuses its
question parsing, sample-case building and response assembly, and adds a compile +
run stage per language. User code is compiled and executed in a throw-away
directory through :mod:`subprocess` with a hard timeout and capped output. It is
a local single-user convenience runner, not a security sandbox.

Protocol: the generated harness calls the user's ``Solution`` method once per
sample, writes one JSON record per case to ``result.json`` and the parent
compares against the stored sample output (same comparison code as Python).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .common import AppError  # noqa: F401  (kept for callers importing from here)
from . import judge_toolchain

COMPILE_TIMEOUT_MS = 20000
RUN_TIMEOUT_MS = 5000
MAX_CAPTURE_BYTES = 65536
MAX_RESULT_BYTES = 262144

SPECIAL_REASON = (
    '本题包含环、随机指针、公共结点或链表数组等特殊样例结构，目前只在 Python 模式支持在线运行。'
    '可切换语言后查看官方题解，或复制代码到力扣运行。'
)
TYPE_REASON = '该题的方法参数或返回值包含暂不支持自动构造的类型（{type}），当前只在 Python 模式支持。'
VOID_REASON = '该题需要比较被修改的参数，但未能确定修改对象，暂不支持在线运行。'


class _Unsupported(Exception):
    def __init__(self, reason):
        self.reason = reason


# ---------------------------------------------------------------------------
# Source cleaning / signature parsing
# ---------------------------------------------------------------------------


def _strip_noise(source: str) -> str:
    """Replace comments and string/char literals with spaces, keeping offsets."""
    output = []
    index, length, state, quote = 0, len(source), 'code', ''
    while index < length:
        char = source[index]
        nxt = source[index + 1] if index + 1 < length else ''
        if state == 'code':
            if char == '/' and nxt == '/':
                state = 'line-comment'
                output.append('  ')
                index += 2
                continue
            if char == '/' and nxt == '*':
                state = 'block-comment'
                output.append('  ')
                index += 2
                continue
            if char in ('"', "'"):
                state, quote = 'string', char
                output.append(' ')
                index += 1
                continue
            output.append(char)
            index += 1
            continue
        if state == 'line-comment':
            output.append('\n' if char == '\n' else ' ')
            if char == '\n':
                state = 'code'
            index += 1
            continue
        if state == 'block-comment':
            if char == '*' and nxt == '/':
                state = 'code'
                output.append('  ')
                index += 2
                continue
            output.append('\n' if char == '\n' else ' ')
            index += 1
            continue
        # string literal
        if char == '\\':
            output.append('  ')
            index += 2
            continue
        if char == quote:
            state = 'code'
            output.append(' ')
            index += 1
            continue
        output.append('\n' if char == '\n' else ' ')
        index += 1
    return ''.join(output)


def _class_body(source: str, name: str = 'Solution') -> str | None:
    match = re.search(r'\b(?:class|struct)\s+' + re.escape(name) + r'\b[^{;]*\{', source)
    if not match:
        return None
    start, depth, index = match.end(), 1, match.end()
    while index < len(source):
        char = source[index]
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return source[start:index]
        index += 1
    return None


def _split_params(text: str) -> list[str]:
    """Split a parameter list on top-level commas, respecting <> [] () and ``=``."""
    parts, current, depth, angle = [], [], 0, 0
    for char in text:
        if char in '([{':
            depth += 1
        elif char in ')]}':
            depth = max(0, depth - 1)
        elif char == '<':
            angle += 1
        elif char == '>':
            angle = max(0, angle - 1)
        if char == ',' and depth == 0 and angle == 0:
            parts.append(''.join(current).strip())
            current = []
            continue
        current.append(char)
    tail = ''.join(current).strip()
    if tail:
        parts.append(tail)
    return [part for part in parts if part]


def _strip_attributes(text: str) -> str:
    for word in ('const ', 'constexpr ', 'static ', 'inline ', 'final ', 'virtual '):
        text = text.replace(word, '')
    return text.strip().rstrip('&').strip()


def _parse_cpp_signature(source: str, method: str):
    cleaned = _strip_noise(source)
    body = _class_body(cleaned)
    if body is None:
        return None
    pattern = re.compile(
        r'(?:public\s*:\s*)?([A-Za-z_][\w:<>,\s\*&]*?)\s+' + re.escape(method) +
        r'\s*\(([^)]*)\)\s*(?:const\s*)?(?:noexcept\s*)?\{',
        re.S,
    )
    match = pattern.search(body)
    if not match:
        return None
    return_type = _cpp_norm(match.group(1))
    params = []
    for raw in _split_params(match.group(2)):
        raw = raw.split('=')[0].strip()
        if not raw or raw == 'void':
            continue
        pieces = raw.rsplit(None, 1)
        if len(pieces) != 2:
            raise _Unsupported(TYPE_REASON.format(type=raw))
        param_type, name = pieces[0], pieces[1]
        params.append((_cpp_norm(param_type), name))
    return return_type, params


def _parse_java_signature(source: str, method: str):
    cleaned = _strip_noise(source)
    body = _class_body(cleaned)
    if body is None:
        return None
    pattern = re.compile(
        r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?'
        r'([A-Za-z_][\w<>\[\],\.\s]*?)\s+' + re.escape(method) +
        r'\s*\(([^)]*)\)\s*(?:throws\s+[^{]+)?\{',
        re.S,
    )
    match = pattern.search(body)
    if not match:
        return None
    return_type = _java_norm(match.group(1))
    params = []
    for raw in _split_params(match.group(2)):
        raw = raw.split('=')[0].strip()
        if not raw:
            continue
        pieces = raw.rsplit(None, 1)
        if len(pieces) != 2:
            raise _Unsupported(TYPE_REASON.format(type=raw))
        params.append((_java_norm(pieces[0]), pieces[1]))
    return return_type, params


# ---------------------------------------------------------------------------
# Type support
# ---------------------------------------------------------------------------


def _cpp_norm(text: str) -> str:
    text = re.sub(r'\b(const|volatile|std::|public|private|protected|static|inline|virtual)\b', '', text or '')
    text = text.replace('&', '').replace(' ', '')
    return text.strip()


def _java_norm(text: str) -> str:
    text = re.sub(r'\b(public|private|protected|static|final|synchronized|native|abstract|volatile|transient)\b', '', text or '')
    text = text.replace('java.util.', '')
    return re.sub(r'\s+', '', text).strip()


_CPP_SCALARS = {'int', 'long', 'longlong', 'short', 'unsigned', 'unsignedlonglong',
                'size_t', 'double', 'float', 'bool', 'char', 'string'}
_JAVA_SCALARS = {'int', 'long', 'short', 'double', 'float', 'boolean', 'char', 'String',
                 'Integer', 'Long', 'Short', 'Double', 'Float', 'Boolean', 'Character'}


def _cpp_value_type_ok(text: str) -> bool:
    t = text
    if t in _CPP_SCALARS:
        return True
    if t.startswith('vector<') and t.endswith('>'):
        return _cpp_value_type_ok(t[len('vector<'):-1])
    return False


def _java_value_type_ok(text: str) -> bool:
    t = text
    if t in _JAVA_SCALARS:
        return True
    if t.endswith('[]'):
        return _java_value_type_ok(t[:-2])
    if t.startswith('List<') and t.endswith('>'):
        return _java_value_type_ok(t[len('List<'):-1])
    return False


def _cpp_param_ok(text: str, kind: str) -> bool:
    if kind == 'linked':
        return text in ('ListNode*', 'ListNode')
    if kind == 'tree':
        return text in ('TreeNode*', 'TreeNode')
    if kind == 'raw':
        return _cpp_value_type_ok(text)
    return False


def _java_param_ok(text: str, kind: str) -> bool:
    if kind == 'linked':
        return text == 'ListNode'
    if kind == 'tree':
        return text == 'TreeNode'
    if kind == 'raw':
        return _java_value_type_ok(text)
    return False


def _cpp_ret_ok(text: str) -> bool:
    if text in ('void',):
        return True
    if text in ('ListNode*', 'ListNode', 'TreeNode*', 'TreeNode'):
        return True
    return _cpp_value_type_ok(text)


def _java_ret_ok(text: str) -> bool:
    if text == 'void':
        return True
    if text in ('ListNode', 'TreeNode'):
        return True
    return _java_value_type_ok(text)


def _kind_for_cpp(text: str, index: int, kind_hint=None) -> dict | None:
    t = text
    if 'vector<ListNode*>' in t or 'vector<ListNode*>' == t:
        return None
    if t in ('ListNode*', 'ListNode'):
        return {'kind': 'linked'}
    if t in ('TreeNode*', 'TreeNode'):
        return {'kind': 'tree'}
    if 'Node*' in t:
        return None
    return {'kind': 'raw'}


def _kind_for_java(text: str, index: int, kind_hint=None) -> dict | None:
    if 'List<ListNode>' in text:
        return None
    if text == 'ListNode':
        return {'kind': 'linked'}
    if text == 'TreeNode':
        return {'kind': 'tree'}
    if text == 'Node':
        return None
    return {'kind': 'raw'}


# ---------------------------------------------------------------------------
# Literal generation
# ---------------------------------------------------------------------------


def _cpp_decl(text: str) -> str:
    t = text
    if t == 'string':
        return 'std::string'
    if t in ('ListNode*', 'ListNode', 'TreeNode*', 'TreeNode'):
        return t
    if t.startswith('vector<') and t.endswith('>'):
        return 'std::vector<' + _cpp_decl(t[len('vector<'):-1]) + '>'
    return t


def _java_decl(text: str) -> str:
    return text


def _java_escape(text: str) -> str:
    return json.dumps(text, ensure_ascii=True)


def _cpp_string_literal(text: str) -> str:
    return json.dumps(text, ensure_ascii=True)


def _cpp_scalar(value, ctype: str) -> str:
    t = ctype
    if t == 'string':
        if not isinstance(value, str):
            raise _Unsupported(TYPE_REASON.format(type=ctype))
        return _cpp_string_literal(value)
    if t == 'char':
        if isinstance(value, str) and len(value) == 1:
            return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"
        raise _Unsupported(TYPE_REASON.format(type=ctype))
    if t == 'bool':
        return 'true' if value else 'false'
    if t in ('double', 'float'):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _Unsupported(TYPE_REASON.format(type=ctype))
        text = repr(float(value))
        return text
    if t in ('longlong', 'unsignedlonglong', 'size_t'):
        return str(int(value)) + 'LL'
    if t in ('int', 'long', 'short', 'unsigned'):
        if isinstance(value, bool) or not isinstance(value, int):
            raise _Unsupported(TYPE_REASON.format(type=ctype))
        return str(value)
    raise _Unsupported(TYPE_REASON.format(type=ctype))


def _cpp_literal(value, ctype: str) -> str:
    t = ctype
    if t.startswith('vector<') and t.endswith('>'):
        inner = t[len('vector<'):-1]
        if not isinstance(value, (list, tuple)):
            raise _Unsupported(TYPE_REASON.format(type=ctype))
        items = ', '.join(_cpp_literal(item, inner) for item in value)
        return _cpp_decl(t) + '{' + items + '}'
    return _cpp_scalar(value, t)


def _java_scalar(value, jtype: str) -> str:
    t = jtype
    if t in ('String',):
        if not isinstance(value, str):
            raise _Unsupported(TYPE_REASON.format(type=jtype))
        return _java_escape(value)
    if t in ('char', 'Character'):
        if isinstance(value, str) and len(value) == 1:
            return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"
        if isinstance(value, int) and not isinstance(value, bool):
            return "'" + chr(value).replace('\\', '\\\\').replace("'", "\\'") + "'"
        raise _Unsupported(TYPE_REASON.format(type=jtype))
    if t in ('boolean', 'Boolean'):
        return 'true' if value else 'false'
    if t in ('double', 'float', 'Double', 'Float'):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _Unsupported(TYPE_REASON.format(type=jtype))
        return repr(float(value))
    if t in ('int', 'long', 'short', 'Integer', 'Long', 'Short'):
        if isinstance(value, bool) or not isinstance(value, int):
            raise _Unsupported(TYPE_REASON.format(type=jtype))
        return str(value) + ('L' if t in ('long', 'Long') else '')
    raise _Unsupported(TYPE_REASON.format(type=jtype))


def _java_literal(value, jtype: str) -> str:
    t = jtype
    if t.endswith('[]'):
        inner = t[:-2]
        if not isinstance(value, (list, tuple)):
            raise _Unsupported(TYPE_REASON.format(type=jtype))
        items = ', '.join(_java_literal(item, inner) for item in value)
        return 'new ' + _java_decl(t) + '{' + items + '}'
    if t.startswith('List<') and t.endswith('>'):
        inner = t[len('List<'):-1]
        if not isinstance(value, (list, tuple)):
            raise _Unsupported(TYPE_REASON.format(type=jtype))
        if not value:
            return 'new ArrayList<>()'
        items = ', '.join(_java_literal(item, inner) for item in value)
        return 'new ArrayList<>(Arrays.asList(' + items + '))'
    return _java_scalar(value, t)


def _tree_tokens(values) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise _Unsupported(TYPE_REASON.format(type='TreeNode'))
    tokens = []
    for item in values:
        if item is None:
            tokens.append('null')
        elif isinstance(item, bool) or not isinstance(item, int):
            raise _Unsupported(TYPE_REASON.format(type='TreeNode'))
        else:
            tokens.append(str(item))
    return tokens


def _linked_values(values) -> list[int]:
    if not isinstance(values, (list, tuple)):
        raise _Unsupported(TYPE_REASON.format(type='ListNode'))
    result = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, int):
            raise _Unsupported(TYPE_REASON.format(type='ListNode'))
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Harness generation
# ---------------------------------------------------------------------------


_CPP_RUNTIME = r'''
namespace judge_rt {
using std::string;
using std::vector;
static string esc(const string& s) {
  string out; out.reserve(s.size() + 2); out.push_back('"');
  for (unsigned char c : s) {
    if (c == '"') out += "\\\"";
    else if (c == '\\') out += "\\\\";
    else if (c == '\n') out += "\\n";
    else if (c == '\r') out += "\\r";
    else if (c == '\t') out += "\\t";
    else if (c < 0x20) { char b[8]; std::snprintf(b, sizeof(b), "\\u%04x", c); out += b; }
    else out.push_back(static_cast<char>(c));
  }
  out.push_back('"'); return out;
}
static string dump(int v) { return std::to_string(v); }
static string dump(long v) { return std::to_string(v); }
static string dump(long long v) { return std::to_string(v); }
static string dump(unsigned v) { return std::to_string(v); }
static string dump(unsigned long long v) { return std::to_string(v); }
static string dump(double v) {
  if (!std::isfinite(v)) return "null";
  std::ostringstream os; os << std::setprecision(15) << v;
  string text = os.str();
  if (text.find('.') == string::npos && text.find('e') == string::npos) text += ".0";
  return text;
}
static string dump(float v) { return dump(static_cast<double>(v)); }
static string dump(bool v) { return v ? "true" : "false"; }
static string dump(char v) { return esc(string(1, v)); }
static string dump(const string& v) { return esc(v); }
static string dump(const char* v) { return esc(string(v)); }
template <class T> static string dump(const vector<T>& values) {
  string out = "[";
  for (size_t i = 0; i < values.size(); ++i) {
    if (i) out += ",";
    out += dump(static_cast<T>(values[i]));
  }
  return out + "]";
}
static ListNode* build_list(const vector<int>& values) {
  ListNode* head = nullptr;
  for (int i = static_cast<int>(values.size()) - 1; i >= 0; --i) head = new ListNode(values[i], head);
  return head;
}
static TreeNode* build_tree(const vector<string>& tokens) {
  if (tokens.empty() || tokens[0] == "null") return nullptr;
  TreeNode* root = new TreeNode(std::stoi(tokens[0]));
  vector<TreeNode*> queue{root};
  size_t head = 0, index = 1;
  while (head < queue.size() && index < tokens.size()) {
    TreeNode* current = queue[head++];
    if (!current) continue;
    if (index < tokens.size()) {
      if (tokens[index] != "null") { current->left = new TreeNode(std::stoi(tokens[index])); queue.push_back(current->left); }
      else queue.push_back(nullptr);
      ++index;
    }
    if (index < tokens.size()) {
      if (tokens[index] != "null") { current->right = new TreeNode(std::stoi(tokens[index])); queue.push_back(current->right); }
      else queue.push_back(nullptr);
      ++index;
    }
  }
  return root;
}
static string dump(ListNode* head) {
  vector<int> values;
  std::unordered_set<ListNode*> seen;
  while (head) {
    if (seen.count(head)) throw std::runtime_error("返回的链表存在环，无法序列化");
    seen.insert(head);
    values.push_back(head->val);
    head = head->next;
    if (values.size() > 20000) throw std::runtime_error("返回的链表过长");
  }
  return dump(values);
}
static string dump(TreeNode* root) {
  if (!root) return "[]";
  vector<string> out;
  vector<TreeNode*> queue{root};
  for (size_t head = 0; head < queue.size(); ++head) {
    TreeNode* node = queue[head];
    if (!node) { out.push_back("null"); continue; }
    if (out.size() > 20000) throw std::runtime_error("返回的树节点过多或存在环");
    out.push_back(std::to_string(node->val));
    queue.push_back(node->left);
    queue.push_back(node->right);
  }
  while (!out.empty() && out.back() == "null") out.pop_back();
  string text = "[";
  for (size_t i = 0; i < out.size(); ++i) { if (i) text += ","; text += out[i]; }
  return text + "]";
}
static string record(int index, const string& actual, const string& error, double ms) {
  std::ostringstream os;
  os << "{\"index\":" << index << ",\"actual\":" << (error.empty() ? actual : "null")
     << ",\"error\":" << (error.empty() ? "null" : esc(error))
     << ",\"durationMs\":" << std::fixed << std::setprecision(2) << ms << "}";
  return os.str();
}
}
'''


_CPP_NODES = '''struct ListNode {
  int val;
  ListNode *next;
  ListNode() : val(0), next(nullptr) {}
  ListNode(int x) : val(x), next(nullptr) {}
  ListNode(int x, ListNode *next) : val(x), next(next) {}
};
struct TreeNode {
  int val;
  TreeNode *left;
  TreeNode *right;
  TreeNode() : val(0), left(nullptr), right(nullptr) {}
  TreeNode(int x) : val(x), left(nullptr), right(nullptr) {}
  TreeNode(int x, TreeNode *left, TreeNode *right) : val(x), left(left), right(right) {}
};
'''


def _cpp_has_definition(source: str, name: str) -> bool:
    return bool(re.search(r'\b(?:struct|class)\s+' + name + r'\b', _strip_noise(source)))


def _cpp_harness(plan: dict) -> str:
    from . import code_runner as cr

    user = plan['userSource']
    nodes = ''
    if not _cpp_has_definition(user, 'ListNode') or not _cpp_has_definition(user, 'TreeNode'):
        nodes = _CPP_NODES
        if _cpp_has_definition(user, 'ListNode'):
            nodes = nodes[nodes.index('struct TreeNode'):]
        elif _cpp_has_definition(user, 'TreeNode'):
            nodes = nodes[:nodes.index('struct TreeNode')]
    lines = ['#include <bits/stdc++.h>', 'using namespace std;', '', nodes, user, '', _CPP_RUNTIME, 'int main() {', '  std::vector<std::string> __parts;']
    params = plan['params']
    ret = plan['returnType']
    mutate = plan.get('mutate')
    for case in plan['cases']:
        index = case['index']
        lines.append('  {')
        lines.append('    auto __start = std::chrono::steady_clock::now();')
        lines.append('    std::string __actual; std::string __error;')
        lines.append('    try {')
        arg_names = []
        for position, arg in enumerate(case['args']):
            kind = arg.get('kind')
            if kind in ('cycle_head', 'random_list', 'intersection_a', 'intersection_b', 'tree_ref', 'list_of_linked'):
                return ''
            param = params[position]
            type_text, name = param['type'], param['name']
            var = f'a{index}_{position}'
            if kind == 'linked':
                values = ', '.join(str(item) for item in _linked_values(arg.get('value')))
                lines.append(f'      {_cpp_decl(type_text)} {var} = judge_rt::build_list(std::vector<int>{{{values}}});')
            elif kind == 'tree':
                tokens = _tree_tokens(arg.get('value'))
                payload = ', '.join(_cpp_string_literal(item) for item in tokens)
                lines.append(f'      {_cpp_decl(type_text)} {var} = judge_rt::build_tree(std::vector<std::string>{{{payload}}});')
            else:
                lines.append(f'      {_cpp_decl(type_text)} {var} = {_cpp_literal(arg.get("value"), type_text)};')
            arg_names.append(var)
        call = f'Solution().{plan["method"]}(' + ', '.join(arg_names) + ')'
        if ret == 'void':
            target = mutate['argIndex'] if mutate else 0
            lines.append(f'      {call};')
            lines.append(f'      __actual = judge_rt::dump({arg_names[target]});')
        else:
            lines.append(f'      auto __ret = {call};')
            lines.append('      __actual = judge_rt::dump(__ret);')
        lines.append('    } catch (const std::exception& __e) { __error = __e.what(); }')
        lines.append('      catch (...) { __error = "unknown exception"; }')
        lines.append('    double __ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - __start).count();')
        lines.append(f'    __parts.push_back(judge_rt::record({index}, __actual, __error, __ms));')
        lines.append('  }')
    lines += [
        '  std::ofstream __out("result.json", std::ios::binary);',
        '  __out << "[";',
        '  for (size_t i = 0; i < __parts.size(); ++i) { if (i) __out << ","; __out << __parts[i]; }',
        '  __out << "]";',
        '  return 0;',
        '}',
        '',
    ]
    return '\n'.join(lines)


_JAVA_NODES = '''class ListNode { int val; ListNode next; ListNode() {} ListNode(int v) { val = v; } ListNode(int v, ListNode n) { val = v; next = n; } }
class TreeNode { int val; TreeNode left, right; TreeNode() {} TreeNode(int v) { val = v; } TreeNode(int v, TreeNode l, TreeNode r) { val = v; left = l; right = r; } }
'''


_JAVA_RUNTIME = r'''
  static String esc(String s) {
    StringBuilder out = new StringBuilder("\"");
    for (int i = 0; i < s.length(); i++) {
      char c = s.charAt(i);
      if (c == '"') out.append("\\\"");
      else if (c == '\\') out.append("\\\\");
      else if (c == '\n') out.append("\\n");
      else if (c == '\r') out.append("\\r");
      else if (c == '\t') out.append("\\t");
      else if (c < 0x20) out.append(String.format("\\u%04x", (int) c));
      else out.append(c);
    }
    return out.append('"').toString();
  }
  static String dump(Object v) {
    if (v == null) return "null";
    if (v instanceof String) return esc((String) v);
    if (v instanceof Character) return esc(String.valueOf(v));
    if (v instanceof Boolean) return ((Boolean) v) ? "true" : "false";
    if (v instanceof Double || v instanceof Float) {
      double d = ((Number) v).doubleValue();
      if (Double.isNaN(d) || Double.isInfinite(d)) return "null";
      if (d == Math.rint(d) && Math.abs(d) < 1e15) return String.valueOf((long) d);
      return String.valueOf(d);
    }
    if (v instanceof Number) return String.valueOf(v);
    if (v instanceof ListNode) return dumpList((ListNode) v);
    if (v instanceof TreeNode) return dumpTree((TreeNode) v);
    if (v instanceof List) {
      StringBuilder out = new StringBuilder("[");
      boolean first = true;
      for (Object item : (List<?>) v) { if (!first) out.append(','); first = false; out.append(dump(item)); }
      return out.append(']').toString();
    }
    if (v.getClass().isArray()) {
      int n = java.lang.reflect.Array.getLength(v);
      StringBuilder out = new StringBuilder("[");
      for (int i = 0; i < n; i++) { if (i > 0) out.append(','); out.append(dump(java.lang.reflect.Array.get(v, i))); }
      return out.append(']').toString();
    }
    return esc(String.valueOf(v));
  }
  static String dumpList(ListNode head) {
    List<Integer> values = new ArrayList<>();
    Set<ListNode> seen = Collections.newSetFromMap(new IdentityHashMap<ListNode, Boolean>());
    while (head != null) {
      if (!seen.add(head)) throw new RuntimeException("返回的链表存在环，无法序列化");
      values.add(head.val);
      head = head.next;
      if (values.size() > 20000) throw new RuntimeException("返回的链表过长");
    }
    return dump(values);
  }
  static String dumpTree(TreeNode root) {
    if (root == null) return "[]";
    List<String> out = new ArrayList<>();
    List<TreeNode> queue = new ArrayList<>();
    queue.add(root);
    for (int head = 0; head < queue.size(); head++) {
      TreeNode node = queue.get(head);
      if (node == null) { out.add("null"); continue; }
      if (out.size() > 20000) throw new RuntimeException("返回的树节点过多或存在环");
      out.add(String.valueOf(node.val));
      queue.add(node.left);
      queue.add(node.right);
    }
    while (!out.isEmpty() && out.get(out.size() - 1).equals("null")) out.remove(out.size() - 1);
    return "[" + String.join(",", out) + "]";
  }
  static ListNode buildList(int[] values) {
    ListNode head = null;
    for (int i = values.length - 1; i >= 0; i--) head = new ListNode(values[i], head);
    return head;
  }
  static TreeNode buildTree(String[] tokens) {
    if (tokens.length == 0 || tokens[0].equals("null")) return null;
    TreeNode root = new TreeNode(Integer.parseInt(tokens[0]));
    List<TreeNode> queue = new ArrayList<>();
    queue.add(root);
    int head = 0, index = 1;
    while (head < queue.size() && index < tokens.length) {
      TreeNode current = queue.get(head++);
      if (current == null) continue;
      if (index < tokens.length) {
        if (!tokens[index].equals("null")) { current.left = new TreeNode(Integer.parseInt(tokens[index])); queue.add(current.left); }
        else queue.add(null);
        index++;
      }
      if (index < tokens.length) {
        if (!tokens[index].equals("null")) { current.right = new TreeNode(Integer.parseInt(tokens[index])); queue.add(current.right); }
        else queue.add(null);
        index++;
      }
    }
    return root;
  }
  static String record(int index, String actual, String error, double ms) {
    return "{\"index\":" + index + ",\"actual\":" + (error == null ? actual : "null")
      + ",\"error\":" + (error == null ? "null" : esc(error))
      + ",\"durationMs\":" + String.format(java.util.Locale.ROOT, "%.2f", ms) + "}";
  }
'''


def _java_harness(plan: dict) -> str:
    user = plan['userSource']
    nodes = '' if (_java_has_definition(user, 'ListNode') and _java_has_definition(user, 'TreeNode')) else _JAVA_NODES
    if nodes and _java_has_definition(user, 'ListNode'):
        nodes = nodes[nodes.index('class TreeNode'):]
    elif nodes and _java_has_definition(user, 'TreeNode'):
        nodes = nodes[:nodes.index('class TreeNode')]
    lines = ['import java.util.*;', 'import java.nio.file.*;', 'import java.nio.charset.StandardCharsets;', '', nodes,
             'public class Main {', _JAVA_RUNTIME, '  public static void main(String[] args) throws Exception {',
             '    List<String> parts = new ArrayList<>();']
    params = plan['params']
    ret = plan['returnType']
    mutate = plan.get('mutate')
    for case in plan['cases']:
        index = case['index']
        lines.append('    {')
        lines.append('      long __start = System.nanoTime();')
        lines.append('      String actual = null, error = null;')
        lines.append('      try {')
        arg_names = []
        for position, arg in enumerate(case['args']):
            kind = arg.get('kind')
            if kind in ('cycle_head', 'random_list', 'intersection_a', 'intersection_b', 'tree_ref', 'list_of_linked'):
                return ''
            param = params[position]
            type_text, name = param['type'], param['name']
            var = f'a{index}_{position}'
            if kind == 'linked':
                values = ', '.join(str(item) for item in _linked_values(arg.get('value')))
                lines.append(f'        {_java_decl(type_text)} {var} = buildList(new int[]{{{values}}});')
            elif kind == 'tree':
                tokens = _tree_tokens(arg.get('value'))
                payload = ', '.join(_java_escape(item) for item in tokens)
                lines.append(f'        {_java_decl(type_text)} {var} = buildTree(new String[]{{{payload}}});')
            else:
                lines.append(f'        {_java_decl(type_text)} {var} = {_java_literal(arg.get("value"), type_text)};')
            arg_names.append(var)
        call = f'new Solution().{plan["method"]}(' + ', '.join(arg_names) + ')'
        if ret == 'void':
            target = mutate['argIndex'] if mutate else 0
            lines.append(f'        {call};')
            lines.append(f'        actual = dump({arg_names[target]});')
        else:
            lines.append(f'        Object __ret = {call};')
            lines.append('        actual = dump(__ret);')
        lines.append('      } catch (Throwable __e) { error = String.valueOf(__e); }')
        lines.append('      double __ms = (System.nanoTime() - __start) / 1e6;')
        lines.append(f'      parts.add(record({index}, actual, error, __ms));')
        lines.append('    }')
    lines += [
        '    Files.writeString(Path.of("result.json"), "[" + String.join(",", parts) + "]", StandardCharsets.UTF_8);',
        '  }',
        '}',
        '',
    ]
    return '\n'.join(lines)


def _java_has_definition(source: str, name: str) -> bool:
    return bool(re.search(r'\b(?:class|interface)\s+' + name + r'\b', _strip_noise(source)))


# ---------------------------------------------------------------------------
# Plan building
# ---------------------------------------------------------------------------


def build_plan(question, code: str, language: str) -> dict:
    from . import code_runner as cr

    official = cr._official_solution_method(question)
    if official is None:
        return {'unsupported': True, 'reason': cr.DESIGN_REASON}
    method_name, official_node = official
    number = question.get('leetcodeNumber')
    if number in cr.SPECIAL_QUESTIONS or number == 236:
        return {'unsupported': True, 'reason': SPECIAL_REASON}
    solution = (question.get('solutions') or {}).get(language)
    if not isinstance(solution, str) or not solution.strip():
        return {'unsupported': True, 'reason': '题库缺少该语言的参考题解，无法生成自动判题驱动。'}
    try:
        signature = _parse_cpp_signature(solution, method_name) if language == 'cpp' else _parse_java_signature(solution, method_name)
    except _Unsupported as error:
        return {'unsupported': True, 'reason': error.reason}
    if signature is None:
        return {'unsupported': True, 'reason': '未能在官方题解中解析出方法签名，暂不支持该语言的自动判题。'}
    return_type, params = signature
    py_params = [arg.arg for arg in official_node.args.args[1:]]
    if len(params) != len(py_params):
        return {'unsupported': True, 'reason': '该题不同语言的参数数量不一致，暂不支持自动判题。'}
    if language == 'cpp':
        kinds, ok = [], _cpp_param_ok
        kind_builder = _kind_for_cpp
        ret_ok = _cpp_ret_ok
    else:
        kinds, ok = [], _java_param_ok
        kind_builder = _kind_for_java
        ret_ok = _java_ret_ok
    for index, (type_text, _name) in enumerate(params):
        kind = kind_builder(type_text, index)
        if kind is None or not (kind['kind'] in ('linked', 'tree') and ok(type_text, kind['kind'])
                                or kind['kind'] == 'raw' and ok(type_text, 'raw')):
            return {'unsupported': True, 'reason': TYPE_REASON.format(type=type_text)}
        kinds.append(kind)
    if not ret_ok(return_type):
        return {'unsupported': True, 'reason': TYPE_REASON.format(type=return_type)}
    built = cr.build_cases(question, [name for _type, name in params], kinds)
    if built.get('unsupported'):
        return built
    for case in built['cases']:
        if case.get('mode') != 'literal':
            return {'unsupported': True, 'reason': SPECIAL_REASON}
        for arg in case['args']:
            if arg.get('kind') not in ('raw', 'linked', 'tree'):
                return {'unsupported': True, 'reason': SPECIAL_REASON}
    mutate = next((case['mutate'] for case in built['cases'] if case.get('mutate')), None)
    if return_type == 'void' and not mutate:
        return {'unsupported': True, 'reason': VOID_REASON}
    plan = {
        'language': language,
        'method': method_name,
        'returnType': return_type,
        'params': [{'type': type_text, 'name': name, 'kind': kinds[index]['kind']}
                   for index, (type_text, name) in enumerate(params)],
        'cases': built['cases'],
        'mutate': mutate,
        'userSource': code,
    }
    try:
        plan['harness'] = _cpp_harness(plan) if language == 'cpp' else _java_harness(plan)
    except _Unsupported as error:
        return {'unsupported': True, 'reason': error.reason}
    if not plan['harness']:
        return {'unsupported': True, 'reason': SPECIAL_REASON}
    return plan


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _trim(text: bytes | str, limit=MAX_CAPTURE_BYTES) -> str:
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='replace')
    text = text or ''
    return text if len(text) <= limit else text[:limit] + '\n…（已截断）'


def _environment(directory: Path) -> dict:
    env = judge_toolchain._child_env(directory)
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def execute(plan: dict) -> dict:
    """Compile and run one C++/Java plan; never raises for user-code problems."""
    language = plan['language']
    capabilities = judge_toolchain.detect()['capabilities']
    capability = capabilities.get(language) or {}
    if not capability.get('available'):
        return {'unsupported': True, 'reason': capability.get('reason') or '本机未检测到对应编译器。'}
    directory = Path(_make_workspace())
    started = time.perf_counter()
    try:
        env = _environment(directory)
        if language == 'cpp':
            source = directory / 'main.cpp'
            source.write_text(plan['harness'], encoding='utf-8')
            binary = directory / ('main.exe' if os.name == 'nt' else 'main')
            compile_command = [capability['path'], '-std=c++17', '-O0', '-o', str(binary), str(source)]
            run_command = [str(binary)]
            compiler_dir = str(Path(capability['path']).parent)
            for key in ('PATH', 'LD_LIBRARY_PATH'):
                env[key] = compiler_dir + os.pathsep + env.get(key, '')
        else:
            (directory / 'Solution.java').write_text('import java.util.*;\n' + plan['userSource'], encoding='utf-8')
            (directory / 'Main.java').write_text(plan['harness'], encoding='utf-8')
            classes = directory / 'classes'
            classes.mkdir()
            compile_command = [capability['path'], '-encoding', 'UTF-8', '-d', str(classes),
                               str(directory / 'Solution.java'), str(directory / 'Main.java')]
            run_command = [capability.get('javaPath') or 'java', '-Dfile.encoding=UTF-8', '-cp', str(classes), 'Main']
        stdout_path, stderr_path = directory / 'stdout.txt', directory / 'stderr.txt'
        with open(stdout_path, 'wb') as out, open(stderr_path, 'wb') as err:
            try:
                compile_run = subprocess.run(
                    compile_command, cwd=str(directory), env=env, stdin=subprocess.DEVNULL,
                    stdout=out, stderr=err, timeout=COMPILE_TIMEOUT_MS / 1000, check=False,
                )
            except subprocess.TimeoutExpired:
                return {'compileError': f'编译超过 {COMPILE_TIMEOUT_MS} ms，已终止编译器。',
                        'stderr': _trim(stderr_path.read_bytes()), 'durationMs': _elapsed(started)}
        compile_stderr = _trim(stderr_path.read_bytes())
        if compile_run.returncode != 0:
            return {'compileError': '编译未通过，请检查语法、类型和类名。', 'stderr': compile_stderr,
                    'stdout': _trim(stdout_path.read_bytes()), 'durationMs': _elapsed(started)}
        stdout_path.write_bytes(b'')
        stderr_path.write_bytes(b'')
        with open(stdout_path, 'wb') as out, open(stderr_path, 'wb') as err:
            try:
                run = subprocess.run(
                    run_command, cwd=str(directory), env=env, stdin=subprocess.DEVNULL,
                    stdout=out, stderr=err, timeout=RUN_TIMEOUT_MS / 1000, check=False,
                )
            except subprocess.TimeoutExpired:
                return {'timedOut': True, 'durationMs': _elapsed(started), 'timeoutMs': RUN_TIMEOUT_MS,
                        'stderr': f'运行超过 {RUN_TIMEOUT_MS} ms，已强制终止子进程。',
                        'stdout': _trim(stdout_path.read_bytes())}
        elapsed = _elapsed(started)
        result_path = directory / 'result.json'
        stdout_text = _trim(stdout_path.read_bytes())
        stderr_text = _trim(stderr_path.read_bytes())
        if not result_path.exists():
            return {'fatal': '判题驱动未返回结果（进程可能提前退出或崩溃）。',
                    'stdout': stdout_text, 'stderr': stderr_text or _trim(stderr_path.read_bytes()),
                    'durationMs': elapsed, 'exitCode': run.returncode}
        raw = result_path.read_bytes()[:MAX_RESULT_BYTES]
        try:
            cases = json.loads(raw.decode('utf-8', errors='replace'))
        except ValueError:
            return {'fatal': '判题驱动返回了无法解析的结果。', 'stdout': stdout_text,
                    'stderr': stderr_text, 'durationMs': elapsed}
        return {'cases': cases, 'stdout': stdout_text, 'stderr': stderr_text, 'durationMs': elapsed,
                'compileMs': None, 'exitCode': run.returncode}
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def _make_workspace() -> str:
    from . import code_runner as cr
    return cr._make_workspace()
