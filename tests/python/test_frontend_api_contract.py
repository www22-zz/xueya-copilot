"""Cross-check the frontend module API surface.

Node is not required. These tests check that every method the app calls on a module handle
is actually defined in that module's source — the class of bug that left `practiceUI.mount()`
dangling and stopped the workspace from opening at all. The check is textual and deliberately
conservative: it proves a definition exists, not that the call site is correct.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'frontend'
BACKEND = Path(__file__).resolve().parents[2] / 'backend' / 'xueya'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def defined_names(source: str) -> set:
    """Names that look like methods, fields, or shorthand members (including the last one)."""
    names = set(re.findall(r'(?:^|[,{;]\s*|\s)(?:async\s+)?(?:get\s+)?([A-Za-z_$][\w$]*)\s*\(', source, re.M))
    names |= set(re.findall(r'(?:^|[,{;]\s*|\s)([A-Za-z_$][\w$]*)\s*:', source, re.M))
    names |= set(re.findall(r'(?:^|[,{;]\s*|\s)([A-Za-z_$][\w$]*)\s*(?=[,}])', source, re.M))
    return names


def test_defined_names_recognizes_final_shorthand_members():
    for source in ('return {state, ready};', 'return {ready};',
                   'return {\n  state,\n  ready\n};', 'return {state, ready,};'):
        assert 'ready' in defined_names(source)
        assert 'missing' not in defined_names(source)
    assert 'ready' not in defined_names('const ready = new Promise(resolve => {}); return {state};')


def called_methods(source: str, handle: str) -> set:
    return set(re.findall(r'\b' + handle + r'\??\.(\w+)', source))


def test_script_and_stylesheet_tags_point_at_real_files():
    html = read('index.html')
    missing = [value for _, value in re.findall(r'(src|href)="([^"]+\.(?:js|css))"', html)
               if not (ROOT.parent / value.replace('../', '')).exists() and not (ROOT / value).exists()]
    assert not missing, f'index.html references missing files: {missing}'


def test_no_reference_to_deleted_modules_or_the_removed_more_menu():
    stale = []
    for path in ROOT.rglob('*.js'):
        text = path.read_text(encoding='utf-8')
        for probe in ('XueyaNotes', 'XueyaContentWorkspace', 'XueyaPracticeUI', 'learning-ui.js',
                      'practice-controller', 'practice-service.js', '#workspaceMore', '#bankDialog'):
            if probe in text:
                stale.append(f'{path.name}: {probe}')
    assert not stale, f'dead module references remain: {stale}'


def test_app_only_calls_methods_the_practice_modules_define():
    app = read('js/app.js')
    modules = {
        'practiceUI': read('js/practice-view.js'),
        'practiceStore': read('js/state/practice-store.js'),
        'practiceClient': read('js/services/practice-client.js'),
    }
    broken = []
    for handle, source in modules.items():
        known = defined_names(source)
        for method in sorted(called_methods(app, handle)):
            if method not in known:
                broken.append(f'app.js calls {handle}.{method}() but practice module source never defines it')
    assert not broken, broken


def test_practice_view_only_touches_real_store_and_client_members():
    view = read('js/practice-view.js')
    known_store = defined_names(read('js/state/practice-store.js'))
    known_client = defined_names(read('js/services/practice-client.js'))
    broken = [f'practice-view.js calls store.{m}() but it is not defined'
              for m in sorted(called_methods(view, 'store')) if m not in known_store]
    broken += [f'practice-view.js calls client.{m}() but it is not defined'
               for m in sorted(called_methods(view, 'client')) if m not in known_client]
    assert not broken, broken


def test_practice_state_machine_js_and_python_expose_the_same_actions():
    js = read('js/state/practice-store.js')
    js_actions = {a.strip() for a in re.search(r"ACTIONS=\[([^\]]+)\]", js).group(1).replace("'", '').split(',') if a.strip()}
    py_transitions = {a.strip() for a in re.search(r"ACTIONS = \(([^)]+)\)", (BACKEND / 'practice_rules.py').read_text(encoding='utf-8'))
                      .group(1).replace("'", '').replace('\n', '').split(',') if a.strip()}
    py_storage = {a.strip() for a in re.search(r"ACTIONS = \(([^)]+)\)", (BACKEND / 'practice_state.py').read_text(encoding='utf-8'))
                  .group(1).replace("'", '').replace('\n', '').split(',') if a.strip()}
    assert py_transitions <= js_actions, (sorted(py_transitions), sorted(js_actions))
    assert js_actions <= py_storage, (sorted(js_actions), sorted(py_storage))


def test_routes_follow_the_prd_route_table():
    html = read('index.html')
    for href in ('#space/overview', '#space/ask', '#space/knowledge', '#space/practice', '#space/review'):
        assert f'href="{href}"' in html, f'missing nav route {href}'
    for gone in ('#space/cards', '#space/chapters', '#space/plan', '#space/graph', '#space/memory', '#space/chat'):
        assert f'href="{gone}"' not in html, f'deleted route {gone} still linked'


def test_every_asset_indexed_by_index_html_exists():
    html = read('index.html')
    for value in re.findall(r'(?:src|href)="((?:js|css)/[^"]+)"', html):
        assert (ROOT / value).exists(), f'index.html references missing {value}'


def test_the_workspace_still_opens_route_never_guards_a_missing_module():
    """mount() must not call a method that would throw before route() hides the home page."""
    app = read('js/app.js')
    body = app[app.find('function mount()'):]
    body = body[:body.find('\n  }')]
    for handle in re.findall(r'\b(\w+)\??\.(\w+)\(\)', body):
        name, method = handle
        if name not in ('document', 'window', 'location', 'fetch', 'console'):
            source = {'practiceUI': 'js/practice-view.js', 'workspace': 'js/workspace-controller.js',
                      'practiceClient': 'js/services/practice-client.js', 'agentRuns': 'js/services/agent-run-ui.js',
                      'experience': 'js/experience.js'}.get(name)
            if source:
                assert method in defined_names(read(source)), f'mount() calls {name}.{method}() which is not defined'
