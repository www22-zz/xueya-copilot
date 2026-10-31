"""Exercise learning-center navigation and real HTTP wiring in isolated Chrome.

No private database or live model services are used.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time

for key in ('MIMO_API_KEY', 'RAG_OCR_API_KEY', 'RAG_EMBEDDING_API_KEY', 'RAG_RERANK_API_KEY', 'TAVILY_API_KEY'):
    os.environ[key] = ''

import uvicorn
from playwright.sync_api import sync_playwright, expect
from backend.xueya.app import create_app
from backend.xueya.config import Config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'test-results/repair-learning-space'


class Model:
    calls = 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        if '拆解可执行任务' in messages[0]['content']:
            value = {'explanation': '先理解进程状态，再完成回忆练习。', 'tasks': [
                {'title': '理解进程状态转换', 'subject': '操作系统', 'minutes': 30},
                {'title': '回忆线程与进程区别', 'subject': '操作系统', 'minutes': 30}]}
        else:
            value = {'title': '进程知识框架', 'nodes': [
                {'id': 'root', 'label': '进程管理', 'parentId': None},
                {'id': 'states', 'label': '进程状态', 'parentId': 'root'}]}
        return {'content': json.dumps(value, ensure_ascii=False), 'model': 'controlled'}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-repair-browser-') as directory:
        model = Model()
        app = create_app(Config(root=ROOT, data_dir=Path(directory), auto_import_demo=False,
                                preserve_legacy_data=True), provider=model)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=3))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started: break
                time.sleep(.05)
            assert server.started
            base = f'http://127.0.0.1:{port}'
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
                context = browser.new_context(viewport={'width': 1400, 'height': 950})
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
                reply = context.request.post(base+'/api/account/register', data={
                    'username': 'repaircase', 'password': 'Fixture123', 'confirmPassword': 'Fixture123'})
                assert reply.ok
                page = context.new_page(); errors=[];page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base+'/#space/courses')
                nav = page.locator('.learning-center-nav')
                expect(nav).to_be_visible()
                assert nav.locator('a').all_text_contents() == ['课程学习', '练习', '复习', '学习分析']
                assert nav.evaluate("node => node.parentElement.classList.contains('learning-center-shell')")
                assert nav.bounding_box()['x'] < page.locator('#spaceContent').bounding_box()['x']
                assert page.locator('.workspace-primary > a').all_text_contents() == ['AI 助手', '学习中心']
                page.locator('.workspace-primary > a').first.click()
                expect(page.locator('#chatThread')).to_be_visible();expect(nav).to_be_hidden()
                assert page.locator('#chatThread').bounding_box()['height'] > 100
                assert page.locator('#chatThread').bounding_box()['y'] < 600
                page.goto(base+'/#space/frameworks')
                expect(page.locator('[data-kf-generate]')).to_be_visible()
                assert model.calls == 0, 'Opening history must not generate content'
                page.locator('[data-kf-generate]').click()
                expect(page.locator('.kf-node-card').first).to_contain_text('进程管理')
                page.on('dialog', lambda dialog: dialog.accept('用户补充概念') if dialog.type=='prompt' else dialog.accept())
                page.locator('[data-kf-add-child]').first.click()
                expect(page.locator('.kf-node-card')).to_have_count(3)
                page.locator('.kf-node-card').last.drag_to(page.locator('.kf-node-card').nth(1))
                expect(page.locator('.kf-node-card').last.locator('.kf-node-badge')).to_have_text('L2')
                page.locator('[data-kf-collapse]').first.click()
                expect(page.locator('.kf-node-card')).to_have_count(1)
                page.locator('[data-kf-collapse]').first.click()
                expect(page.locator('.kf-node-card')).to_have_count(3)
                page.reload()
                expect(page.locator('.kf-node-card')).to_have_count(3)
                page.goto(base+'/#space/analysis')
                page.locator('[data-tab-switch=plan]').click()
                page.locator('[data-open-create-plan]').click()
                page.locator('[name=goal]').fill('复习进程和线程')
                page.locator('#createPlanForm button[type=submit]').click()
                expect(page.locator('[data-adopt-draft]')).to_be_visible()
                page.locator('[data-adopt-draft]').click()
                expect(page.locator('[data-toggle-task]').first).to_be_visible()
                page.locator('[data-toggle-task]').first.check()
                expect(page.locator('[data-toggle-task]').first).to_be_checked()
                page.screenshot(path=str(OUT/'learning-center-desktop.png'), full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                expect(page.locator('.learning-center-nav')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                page.screenshot(path=str(OUT/'learning-center-mobile.png'), full_page=True)
                page.evaluate("document.documentElement.dataset.theme='dark'")
                page.screenshot(path=str(OUT/'learning-center-mobile-dark.png'), full_page=True)
                page.goto(base+'/#space/ask')
                expect(page.locator('.learning-shortcuts')).to_contain_text('今日任务')
                expect(page.locator('[data-shortcut-task]').first).to_be_checked()
                page.locator('[data-open-my-plan]').click()
                expect(page.locator('[data-toggle-task]').first).to_be_visible()
                for view in ('courses','practice','review','analysis'):
                    page.locator(f'.learning-center-nav a[data-view={view}]').click()
                    expect(page.locator(f'.learning-center-nav a[data-view={view}]')).to_have_attribute('aria-current','page')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                assert not errors, errors
                browser.close()
                print(json.dumps({'navigation': 'passed', 'framework_history_and_generation': 'passed',
                                  'plan_create_adopt_complete': 'passed', 'mobile': 'passed',
                                  'page_errors':errors,'controlled_model_calls':model.calls,'paid_calls':0}))
        finally:
            server.should_exit=True;thread.join(10);sock.close()


if __name__ == '__main__':
    main()
