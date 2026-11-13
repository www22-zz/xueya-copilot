"""Static contract for the learning sidebar hub added on 2026-11-13.

The overview page keeps the current-space card, today's plan, recent AI sessions
and the account footer; learning-center and ask views keep their original rail.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_sidebar_hub_assets_and_contract():
    index = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
    app = (ROOT / 'frontend' / 'js' / 'app.js').read_text(encoding='utf-8')
    hub = (ROOT / 'frontend' / 'js' / 'sidebar-hub.js').read_text(encoding='utf-8')
    css = (ROOT / 'frontend' / 'css' / 'sidebar-hub.css').read_text(encoding='utf-8')

    assert 'css/sidebar-hub.css' in index
    assert 'js/sidebar-hub.js' in index
    for anchor in ('id="stitchSpaceCard"', 'id="stitchTodaySection"',
                   'id="stitchNavSection"', 'class="stitch-sidebar-foot"'):
        assert anchor in index, anchor
    # Space card, account footer and settings row all remain reachable.
    assert index.count('data-open-settings') >= 3
    assert 'data-manage-courses' in index

    assert 'window.XueyaSidebarHub?.create' in app
    assert "state.view==='overview'?4:undefined" in app
    assert "sidebarHub?.sync(state.view)" in app

    for endpoint in ('/api/learning/space/plan/active',
                     '/api/learning/space/plan/task/toggle',
                     '/api/learning/space/today'):
        assert endpoint in hub, endpoint
    for selector in ('sidebar-space-card', 'sidebar-task', 'sidebar-account',
                     'stitch-sidebar-scroll'):
        assert selector in css, selector
