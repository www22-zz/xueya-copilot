"""Rough JS delimiter balance check (node is unavailable in this environment).

Handles line/block comments, regex literals, and template literals with nested `${...}`
expressions — enough to catch a truncated or unbalanced edit without a JS parser.
"""
import sys
from pathlib import Path

OPEN = '([{'
CLOSE = ')]}'
REGEX_PRECEDERS = set('=([,{;:!&|?+-*%~^<>\n')


def scan(path):
    src = Path(path).read_text(encoding='utf-8')
    i, n, line = 0, len(src), 1
    stack = []          # delimiter stack for code
    templates = []      # each entry: expression-depth when the template opened
    issues = []

    def prev_non_space():
        j = i - 1
        while j >= 0 and src[j] in ' \t':
            j -= 1
        return src[j] if j >= 0 else ''

    while i < n:
        c = src[i]
        if c == '\n':
            line += 1
            i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                if src[i] == '\n':
                    line += 1
                i += 1
            i += 2
            continue
        if c == '`':
            if templates and templates[-1] == 'template':
                templates.pop()      # end of a template literal body
            else:
                templates.append('template')
            i += 1
            continue
        if templates and templates[-1] == 'template' and c == '\\':
            i += 2
            continue
        if templates and templates[-1] == 'template' and c == '$' and i + 1 < n and src[i + 1] == '{':
            stack.append(('${', line))
            templates.append('expr')
            i += 2
            continue
        if templates and templates[-1] == 'expr' and c == '}' and stack and stack[-1][0] == '${':
            stack.pop()
            templates.pop()
            i += 1
            continue
        if templates and templates[-1] == 'template':
            if c == '}':
                issues.append(f'{path}:{line} stray }} in template literal')
            i += 1
            continue
        if c in '"\'':
            quote = c
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                if src[i] == '\n':
                    line += 1
                    issues.append(f'{path}:{line} unterminated string')
                    break
                i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] not in ('/', '*') and prev_non_space() in REGEX_PRECEDERS:
            i += 1
            while i < n and src[i] != '/':
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == '\n':
                    break
                if src[i] == '[':
                    while i < n and src[i] != ']':
                        if src[i] == '\\':
                            i += 1
                        i += 1
                i += 1
            i += 1
            continue
        if c in OPEN:
            stack.append((c, line))
        elif c in CLOSE:
            if not stack:
                issues.append(f'{path}:{line} unbalanced {c}')
            else:
                o, ol = stack.pop()
                if o == '${' or OPEN.index(o) != CLOSE.index(c):
                    issues.append(f'{path}:{line} mismatched {o} (line {ol}) vs {c}')
        i += 1
    if templates:
        issues.append(f'{path}: unclosed template literal')
    for o, ol in stack:
        issues.append(f'{path}: unclosed {o} opened line {ol}')
    return issues


def main(paths):
    bad = []
    for path in paths:
        bad += scan(path)
    print('\n'.join(bad) if bad else 'BALANCE OK for all files')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
