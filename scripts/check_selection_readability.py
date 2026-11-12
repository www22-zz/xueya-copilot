"""Isolated Chrome check: selected/highlighted text stays readable in both themes.

Runs the real frontend against a mocked API (no paid calls, no backend state):
- preserved conversation shell (#space/ask, html.workspace-original)
- Stitch workspace shell (#space/knowledge)
- app settings dialog
- highlighted search matches inside source quotes and library originals
"""
import functools
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'test-results' / 'selection-readability'
CHROME = next((str(path) for path in (
    Path(os.environ.get('CHROME_PATH', 'C:/Program Files/Google/Chrome/Application/chrome.exe')),
    Path(os.environ.get('LOCALAPPDATA', '')) / 'Google/Chrome/Application/chrome.exe',
    Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'),
) if path.is_file()), None)
# Single source of truth for the global ::selection pair in frontend/css/styles.css.
EXPECTED = {
    'light': {'color': 'rgb(20, 35, 68)', 'background': 'rgb(198, 211, 255)'},
    'dark': {'color': 'rgb(247, 249, 255)', 'background': 'rgb(58, 80, 180)'},
}
MIN_CONTRAST = 4.5


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def luminance(css_color):
    channels = [int(c.strip()) / 255 for c in css_color.removeprefix('rgb(').removesuffix(')').split(',')[:3]]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(first, second):
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def assert_contrast(where, color, background):
    pair = {'color': color, 'background': background}
    ratio = contrast(color, background)
    assert ratio >= MIN_CONTRAST, (where, pair, round(ratio, 2))
    return pair, ratio


def selection_pair(locator):
    return locator.evaluate(
        "el=>{const style=getComputedStyle(el,'::selection');"
        "return {color:style.color,background:style.backgroundColor}}")


def expected_selection(where, pair, theme):
    assert pair == EXPECTED[theme], (where, theme, pair, EXPECTED[theme])
    ratio = contrast(pair['color'], pair['background'])
    assert ratio >= MIN_CONTRAST, (where, theme, pair, round(ratio, 2))
    return ratio


def select_contents(locator):
    locator.evaluate("""el=>{
        const range=document.createRange();
        range.selectNodeContents(el);
        const selection=getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        document.dispatchEvent(new Event('selectionchange'));}""")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    documents = [dict(id=f'doc-{i}', name=f'课程讲义 {i}.md', kind='md', version=1,
        contentRevision=1, status='已解析，可检索', size=100, sourceCount=1, chunks=[],
        review=dict(pendingPages=[], transcribedPages=[], blankPages=[], supplementedPages=[]), quality={}) for i in (1, 2)]
    catalog = dict(ok=True, documents=documents,
        summary=dict(documents=2, sources=2, processing=0, needsReview=0), capabilities={})
    messages = [
        dict(role='user', text='平衡二叉树（AVL）失衡时如何判断进行单旋（LL/RR）和双旋（LR/RL）？'),
        dict(role='ai',
            text='## 结论\n\n判断依据是失衡节点上较高子树的较高侧在哪一边：若较高子树本身在左侧，再看它的较高子树在左（LL）还是右（LR）。\n\n'
                 '具体来说，AVL 树通过检查平衡因子发现失衡，并要求调整后左、右子树高度差不超过 1。\n\n'
                 '```c\nint height(struct Node *n) {\n  return n ? n->height : 0;\n}\n```\n\n'
                 '- 若路径是“左一左”，对失衡节点做一次右单旋。\n- 若路径是“左一右”，先左旋再右旋。',
            engine='MiMo 通用问答', sources=[]),
    ]
    fixtures = {'version': 3, 'activeId': 'course-default', 'courses': [
        dict(id='course-default', name='数据结构', archived=False,
            data=dict(documents=[], sessionId='chat-1', sessions=[
                dict(id='chat-1', title='平衡二叉树（AVL）', messages=messages),
                dict(id='chat-2', title='另一个对话', messages=[])])),
        dict(id='course-other', name='其他课程', archived=False, data=dict(documents=[], sessions=[]))]}
    checks = []
    errors = []

    def respond(route):
        path = urlparse(route.request.url).path
        value = {'ok': True}
        if path.endswith('/account/status'):
            value.update(configured=False, authenticated=True, username='local')
        elif path.endswith('/platform/bootstrap'):
            value.update(token='controlled', schemaVersion='1.0', workspace=None,
                courses=[{'id': c['id'], 'name': c['name'], 'archived': False} for c in fixtures['courses']],
                jobs=[], resources={})
        elif path.endswith('/knowledge/bases'):
            value['bases'] = [{'id': c['id'], 'name': c['name']} for c in fixtures['courses']]
        elif path.endswith('/knowledge/catalog'):
            value = catalog
        elif path.endswith('/documents'):
            value['documents'] = documents
        elif path.endswith('/library/catalog'):
            value.update(documents=documents, media=[], links=[], profile={})
        route.fulfill(status=200, content_type='application/json', body=json.dumps(value, ensure_ascii=False))

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=CHROME)
            context = browser.new_context(viewport={'width': 1600, 'height': 1000})
            context.add_init_script(
                "if(!localStorage.getItem('selection-check-ready')){"
                "localStorage.setItem('xueya-copilot-workspace-v3', %s);"
                "localStorage.setItem('xueya-theme','dark');"
                "localStorage.setItem('selection-check-ready','1');}"
                % json.dumps(json.dumps(fixtures, ensure_ascii=False)))
            context.route('**/api/**', respond)
            page = context.new_page()
            page.set_default_timeout(15000)
            page.on('pageerror', lambda error: errors.append(str(error)))

            def open_ask():
                page.goto(base + '/frontend/index.html#space/ask')
                session = page.locator('[data-session=chat-1]')
                expect(session).to_be_visible()
                session.first.click()
                expect(page.locator('.ai-message .rich-content p').first).to_be_visible()

            def check_conversation(theme):
                open_ask()
                assert page.locator('html').evaluate("el=>el.classList.contains('workspace-original')")
                for selector in ('.ai-message .rich-content p', '.ai-message .rich-content li',
                                 '.ai-message .rich-content pre', '.user-message p', '.message-meta'):
                    location = page.locator(selector).first
                    expect(location).to_be_visible()
                    ratio = expected_selection(selector, selection_pair(location), theme)
                    checks.append(f'{theme} conversation {selector} selection contrast {ratio:.2f}')
                select_contents(page.locator('.ai-message .rich-content p').first)
                page.wait_for_timeout(150)
                page.screenshot(path=str(OUTPUT / f'{theme}-conversation-selected.png'))
                bubble = page.locator('.user-message p').first
                bubble.scroll_into_view_if_needed()
                select_contents(bubble)
                page.wait_for_timeout(150)
                page.screenshot(path=str(OUTPUT / f'{theme}-user-bubble-selected.png'))
                page.locator('button[data-open-settings]:visible,#appSettingsButton:visible').first.click()
                settings = page.locator('#appSettingsDialog')
                expect(settings).to_be_visible()
                settings.locator('[data-settings-tab=general]').click()
                paragraph = settings.locator('[data-settings-panel=general] p')
                expect(paragraph).to_be_visible()
                ratio = expected_selection('settings', selection_pair(paragraph), theme)
                checks.append(f'{theme} settings copy selection contrast {ratio:.2f}')
                select_contents(paragraph)
                page.wait_for_timeout(150)
                page.screenshot(path=str(OUTPUT / f'{theme}-settings-selected.png'))
                page.keyboard.press('Escape')
                expect(settings).not_to_be_visible()

            def check_stitch_shell(theme):
                page.goto(base + '/frontend/index.html#space/knowledge')
                heading = page.locator('.view-heading p').first
                expect(heading).to_be_visible()
                assert not page.locator('html').evaluate("el=>el.classList.contains('workspace-original')")
                ratio = expected_selection('knowledge', selection_pair(heading), theme)
                checks.append(f'{theme} stitch shell selection contrast {ratio:.2f}')
                select_contents(heading)
                page.wait_for_timeout(150)
                page.screenshot(path=str(OUTPUT / f'{theme}-knowledge-selected.png'))

            def check_gradient_greeting(theme):
                page.goto(base + '/frontend/index.html#space/overview')
                greeting = page.locator('h1 .bg-clip-text')
                if not greeting.count():
                    checks.append(f'{theme} gradient greeting not rendered in this route (skipped)')
                    return
                expect(greeting.first).to_be_visible()
                ratio = expected_selection('overview greeting', selection_pair(greeting.first), theme)
                checks.append(f'{theme} gradient greeting selection contrast {ratio:.2f}')
                select_contents(greeting.first)
                page.wait_for_timeout(150)
                page.screenshot(path=str(OUTPUT / f'{theme}-gradient-greeting-selected.png'))

            def check_highlight_marks(theme):
                page.goto(base + '/frontend/index.html#space/ask')
                expect(page.locator('[data-session=chat-1]')).to_be_visible()
                marks = page.evaluate("""()=>{
                    const host=document.createElement('div');host.id='selection-check-marks';
                    host.innerHTML='<blockquote class="source-quote">原文片段：查找从根节点开始，<mark>最多沿着一条根到叶的路径</mark>。</blockquote>'
                        +'<div class="library-original">资料原句：<mark>平衡因子</mark>用于判断失衡。</div>';
                    document.querySelector('main')?.prepend(host) || document.body.prepend(host);
                    return [...host.querySelectorAll('mark')].map(mark=>{
                        const style=getComputedStyle(mark);
                        return {text:mark.textContent,color:style.color,background:style.backgroundColor};});
                }""")
                assert len(marks) == 2, marks
                for mark in marks:
                    ratio = contrast(mark['color'], mark['background'])
                    assert ratio >= MIN_CONTRAST, (theme, 'mark', mark, round(ratio, 2))
                page.locator('#selection-check-marks').scroll_into_view_if_needed()
                box = page.locator('#selection-check-marks').bounding_box()
                page.screenshot(path=str(OUTPUT / f'{theme}-highlight-marks.png'),
                                clip={'x': max(0, box['x'] - 8), 'y': max(0, box['y'] - 8),
                                      'width': min(1568, box['width'] + 16), 'height': min(800, box['height'] + 16)})
                page.evaluate("document.getElementById('selection-check-marks')?.remove()")
                checks.append(f'{theme} highlighted marks contrast {[round(contrast(m["color"], m["background"]), 2) for m in marks]}')

            for theme in ('light', 'dark'):
                page.goto(base + '/frontend/index.html#space/ask')
                expect(page.locator('.stitch-topbar')).to_be_visible()
                page.evaluate('(theme)=>window.XueyaPreferences.applyTheme(theme)', theme)
                expect(page.locator('html')).to_have_attribute('data-theme', theme)
                check_conversation(theme)
                check_stitch_shell(theme)
                check_gradient_greeting(theme)
                check_highlight_marks(theme)
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    report = {'status': 'passed', 'minContrast': MIN_CONTRAST, 'expectedSelection': EXPECTED,
              'checks': checks, 'pageErrors': errors, 'providerRequests': 0}
    (OUTPUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
