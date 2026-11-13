"""Acceptance check for the video-course learning page and the Ask sidebar wheel.

Covers the 2026-11-13 delivery:
  * the account / verification panels at the top of the course page are gone;
  * the 算法机制演练屏 source tab and its canvas are gone;
  * in-class quick and custom questions are answered inline, on the same page,
    instead of navigating to the AI assistant;
  * the left sidebar scrolls with a real mouse wheel on the Ask page.

Runs against an isolated temporary host and account: no model call is made and
the stream endpoint is mocked, so no paid API is touched.
"""
import hashlib
import json
import socket
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright, expect

from backend.xueya.app import create_app
from backend.xueya.config import Config
from .browser_runtime import browser_path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'test-results/video-course'
USERNAME = 'coursefixture'
COURSE = 'cs-arch-sys'
EPISODE = 'arch-ep-1'
COURSE_HASH = f'#space/courses/{COURSE}/{EPISODE}'
SESSIONS = 40


class NoModel:
    async def generate(self, *args, **kwargs):
        raise AssertionError('In-class answers must come from the mocked stream')


def workspace_seed():
    """A long recent-chat list so the sidebar list becomes scrollable."""
    owner = 'account-' + hashlib.sha256(USERNAME.encode()).hexdigest()[:40]
    sessions = [{
        'id': f's{i}',
        'title': f'第 {i + 1} 个对话：二叉搜索树复杂度复盘',
        'createdAt': '2026-11-12T00:00:00Z',
        'messages': [{'id': f'm{i}', 'role': 'user', 'text': '二叉搜索树查找复杂度为什么是 O(log n)？'}],
    } for i in range(SESSIONS)]
    state = {
        'version': 3,
        'activeId': 'course-default',
        'courses': [{
            'id': 'course-default', 'name': '数据结构', 'archived': False,
            'data': {'documents': [], 'documentCount': 2, 'messages': [],
                     'sessions': sessions, 'sessionId': f's{SESSIONS - 1}'},
        }],
    }
    return 'xueya-copilot-workspace-v3:' + owner, state


def sse(payload):
    return 'data: ' + json.dumps(payload, ensure_ascii=False) + '\n\n'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    storage_key, state = workspace_seed()
    seed_script = (
        "try{localStorage.setItem(" + json.dumps(storage_key) + "," +
        json.dumps(json.dumps(state, ensure_ascii=False)) + ");}catch(e){}"
    )
    checks, page_errors, external, stream_questions = [], [], [], []
    with tempfile.TemporaryDirectory(prefix='xueya-video-course-') as directory:
        app = create_app(Config(root=ROOT, data_dir=Path(directory), api_key='',
                                auto_import_demo=False, preserve_legacy_data=True), provider=NoModel())
        sock = socket.socket(); sock.bind(('127.0.0.1', 0))
        base = f'http://127.0.0.1:{sock.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=3))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            assert server.started, 'isolated host failed to start'
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=browser_path(), headless=True)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})

                def local_only(route):
                    if route.request.url.startswith(base + '/'):
                        route.continue_()
                    else:
                        external.append(route.request.url)
                        route.abort()

                def mock_stream(route):
                    try:
                        payload = json.loads(route.request.post_data or '{}')
                    except ValueError:
                        payload = {}
                    question = str(payload.get('question') or '')
                    stream_questions.append(question)
                    answer = f'随堂回答：关于「{question[:60]}」的核心结论已按本节知识切片核对。'
                    body = sse({'type': 'workflow', 'label': '正在核对本节知识切片'})
                    body += sse({'type': 'content', 'text': json.dumps({'answer': answer}, ensure_ascii=False)})
                    body += sse({'type': 'done', 'ok': True, 'answer': answer, 'sources': [],
                                 'engine': '资料问答', 'online': True, 'model': 'controlled'})
                    route.fulfill(status=200, content_type='text/event-stream; charset=utf-8', body=body)

                context.route('**/*', local_only)
                context.route('**/api/agent/stream', mock_stream)
                context.add_init_script(seed_script)
                reply = context.request.post(base + '/api/account/register', data={
                    'username': USERNAME, 'password': 'Fixture123', 'confirmPassword': 'Fixture123'})
                assert reply.ok, reply.text()
                page = context.new_page()
                page.set_default_timeout(20000)
                page.on('pageerror', lambda error: page_errors.append(str(error)))

                # ---------- the course page top no longer carries banners ----------
                page.goto(base + '/' + COURSE_HASH)
                expect(page.locator('[data-back-to-catalog]')).to_be_visible()
                expect(page.locator('[data-ask-in-class]').first).to_be_visible()
                page_text = page.locator('#spaceContent').inner_text()
                assert '课程与手动完成记录保存在当前账号' not in page_text, 'account banner must be gone'
                assert '导入本账号的本机旧记录' not in page_text, 'import button must be gone'
                assert '平台课程 · 课程来源' not in page_text, 'verification banner must be gone'
                checks.append('course-top-banners-removed')

                # ---------- 算法机制演练屏 entry and canvas are gone ----------
                assert page.locator('[data-switch-source="algo-demo"]').count() == 0, 'demo tab must be gone'
                assert page.locator('#algoCanvas').count() == 0, 'demo canvas must be gone'
                assert '算法机制' not in page_text
                page.screenshot(path=str(OUT / 'course-player.png'))
                checks.append('algorithm-demo-entry-removed')

                # ---------- the catalog page top no longer carries the banner ----------
                page.goto(base + '/#space/courses')
                page.reload()
                expect(page.locator('.courses-container')).to_be_visible()
                catalog_text = page.locator('#spaceContent').inner_text()
                assert '课程与手动完成记录保存在当前账号' not in catalog_text
                assert '配套视频课程' in catalog_text
                page.screenshot(path=str(OUT / 'course-catalog.png'))
                checks.append('catalog-banner-removed')

                # ---------- quick question is answered on the same page ----------
                page.goto(base + '/' + COURSE_HASH)
                expect(page.locator('[data-ask-in-class]').first).to_be_visible()
                chip_question = page.locator('[data-ask-in-class]').first.inner_text().strip()
                page.locator('[data-ask-in-class]').first.click()
                thread_box = page.locator('#csInClassThread')
                expect(thread_box).to_be_visible()
                expect(thread_box.locator('.cs-inclass-answer')).to_have_count(1)
                expect(thread_box.locator('.cs-inclass-answer').first).to_contain_text('随堂回答')
                expect(thread_box.locator('.cs-inclass-user-bubble').first).to_contain_text(chip_question[:12])
                assert page.evaluate('() => location.hash') == COURSE_HASH, 'quick ask must not navigate away'
                assert stream_questions and '第 01 讲' in stream_questions[-1]
                page.screenshot(path=str(OUT / 'course-inclass-quick.png'))
                checks.append('quick-question-answered-inline')

                # ---------- custom question via Enter is answered on the same page ----------
                page.locator('#inClassCustomInput').fill('CPI 和 MIPS 指标在评估 CPU 性能时有哪些局限？')
                page.locator('#inClassCustomInput').press('Enter')
                expect(thread_box.locator('.cs-inclass-answer')).to_have_count(2)
                expect(thread_box.locator('.cs-inclass-user-bubble')).to_have_count(2)
                assert page.evaluate('() => location.hash') == COURSE_HASH, 'custom ask must not navigate away'
                assert 'CPI 和 MIPS' in stream_questions[-1] and '第 01 讲' in stream_questions[-1]
                assert page.locator('#inClassCustomInput').input_value() == ''
                page.screenshot(path=str(OUT / 'course-inclass-custom.png'))
                checks.append('custom-question-answered-inline')

                # ---------- the thread survives a full re-render ----------
                page.locator('[data-toggle-ep-complete]').click()
                expect(page.locator('#csInClassThread')).to_be_visible()
                expect(thread_box.locator('.cs-inclass-answer')).to_have_count(2)
                assert page.evaluate('() => location.hash') == COURSE_HASH
                checks.append('in-class-thread-survives-rerender')

                # ---------- the thread can be cleared ----------
                page.locator('[data-inclass-clear]').click()
                expect(thread_box).to_be_hidden()
                checks.append('in-class-thread-clear')

                # ---------- every video course uses the same inline thread ----------
                page.goto(base + '/#space/courses/cs-ds-algo/ds-ep-2')
                expect(page.locator('[data-ask-in-class]').first).to_be_visible()
                page.locator('[data-ask-in-class]').nth(1).click()
                expect(page.locator('#csInClassThread')).to_be_visible()
                expect(page.locator('#csInClassThread .cs-inclass-answer')).to_have_count(1)
                assert page.evaluate('() => location.hash') == '#space/courses/cs-ds-algo/ds-ep-2'
                checks.append('inline-thread-applies-to-every-video-course')

                # ---------- the Ask sidebar scrolls with a real mouse wheel ----------
                page.goto(base + '/#space/ask')
                expect(page.locator('#stitchSidebar')).to_be_visible()
                page.wait_for_function(
                    f'document.querySelectorAll("#stitchRecentSessions .session-item-row").length === {SESSIONS}')
                metrics = page.evaluate(
                    """() => {
                        const list = document.querySelector('#stitchRecentSessions');
                        return {scrollHeight: list.scrollHeight, clientHeight: list.clientHeight};
                    }""")
                assert metrics['scrollHeight'] > metrics['clientHeight'], metrics
                box = page.locator('#stitchRecentSessions').bounding_box()
                page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                before = page.evaluate("() => document.querySelector('#stitchRecentSessions').scrollTop")
                page.mouse.wheel(0, 420)
                page.wait_for_timeout(500)
                after = page.evaluate("() => document.querySelector('#stitchRecentSessions').scrollTop")
                assert after > before, f'sidebar wheel did not scroll: {before} -> {after}'
                assert page.evaluate('() => scrollY') == 0, 'page itself must not scroll'
                page.screenshot(path=str(OUT / 'ask-sidebar-wheel.png'))
                checks.append('ask-sidebar-wheel-scroll')

                assert not page_errors, page_errors
                browser.close()
            result = {
                'status': 'passed',
                'checks': checks,
                'streamQuestions': stream_questions,
                'externalRequests': external,
                'pageErrors': page_errors,
                'paidApiCalls': 0,
                'screenshots': sorted(path.name for path in OUT.glob('*.png')),
            }
            (OUT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False))
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
