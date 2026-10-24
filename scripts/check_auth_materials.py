"""Local browser acceptance; isolated database, no model/API calls."""
import socket
import tempfile
import threading
import time
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright
from backend.xueya.app import create_app
from backend.xueya.config import Config


def main():
    with tempfile.TemporaryDirectory(prefix='xueya-auth-ui-') as directory:
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        base = 'http://127.0.0.1:' + str(sock.getsockname()[1])
        app = create_app(Config(data_dir=Path(directory), api_key=''))
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        while not server.started:
            time.sleep(.05)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base)
                page.locator('.hero-actions a[href="#space/overview"]').click()
                page.locator('#accountLoginDialog').wait_for(state='visible')
                assert page.locator('#spacePage').is_hidden()
                page.get_by_role('button', name='点击注册', exact=True).click()
                page.locator('#accountLoginDialog [name=username]').fill('student-browser')
                page.screenshot(path='test-results/auth-register-desktop.png')
                password = page.locator('#accountLoginDialog [name=password]')
                password.fill('short')
                assert password.get_attribute('aria-invalid') == 'true'
                password.fill('Learning123')
                page.locator('[name=confirmPassword]').fill('Learning124')
                assert page.locator('[data-confirm-error]').inner_text()
                page.locator('[name=confirmPassword]').fill('Learning123')
                page.route('**/api/account/register', lambda route: route.fulfill(status=404, content_type='application/json', body='{"ok":false,"error":"NOT_FOUND"}'))
                page.get_by_role('button', name='注册并进入学习空间').click()
                page.get_by_text('当前后台尚未加载账号功能，请重启学涯服务后再试。', exact=True).wait_for()
                page.unroute('**/api/account/register')
                page.get_by_role('button', name='注册并进入学习空间').click()
                page.locator('#spacePage').wait_for(state='visible')
                page.goto(base+'/#space/knowledge')
                page.get_by_role('heading', name='课程资料', exact=True).wait_for()
                assert page.locator('#kbDocuments').is_hidden()
                assert page.get_by_role('heading', name='检索原文').count() == 0
                page.get_by_role('button', name='上传资料', exact=True).click()
                page.locator('#kbFiles').set_input_files({'name': '验证资料.md', 'mimeType': 'text/markdown', 'buffer': '二叉树每个节点最多有两个孩子。'.encode()})
                page.get_by_role('button', name='查看资料', exact=True).click()
                page.get_by_role('heading', name='验证资料.md').wait_for()
                page.wait_for_function("document.querySelector('.kb-status')?.textContent.includes('解析') || document.querySelector('.kb-status')?.textContent.includes('完成')")
                page.get_by_role('button', name='查看原文', exact=True).click()
                page.locator('#kbDialog').wait_for(state='visible')
                assert '二叉树每个节点最多有两个孩子' in page.locator('#kbDialog').inner_text()
                page.get_by_role('button', name='关闭', exact=True).click()
                page.get_by_role('button', name='用于问答', exact=True).click()
                page.wait_for_url('**/#space/chat')
                assert page.locator('#chatThread').is_visible()
                assert page.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('xueya-c-learning:')&&k.includes(':scope:')).some(k=>JSON.parse(localStorage.getItem(k)).length===1)") is True
                page.context.clear_cookies()
                page.reload()
                page.locator('#accountLoginDialog').wait_for(state='visible')
                page.locator('#accountLoginDialog [name=username]').fill('student-browser')
                page.locator('#accountLoginDialog [name=password]').fill('Wrong123')
                page.get_by_role('button', name='登录', exact=True).click()
                page.get_by_text('账号或密码不正确。', exact=True).wait_for()
                page.locator('#accountLoginDialog [name=password]').fill('Learning123')
                page.get_by_role('button', name='登录', exact=True).click()
                page.locator('#spacePage').wait_for(state='visible')
                page.goto(base+'/#space/knowledge')
                page.set_viewport_size({'width': 375, 'height': 812})
                page.get_by_role('heading', name='课程资料', exact=True).wait_for()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path='test-results/auth-materials-mobile.png', full_page=True)
                browser.close()
                assert not errors, errors
                print('Browser acceptance passed: registration, validation, upload, reader, question scope, mobile layout')
        finally:
            server.should_exit = True
            thread.join(timeout=10)


if __name__ == '__main__':
    main()
