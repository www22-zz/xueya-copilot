"""UI confirmation, server persistence and original-file job checks; no paid API."""
import os
import socket
import subprocess
import sys
import time
import uuid
import httpx
from playwright.sync_api import sync_playwright, expect
from backend.config import ROOT
from backend.platform.database import Database


def main():
    output = ROOT/'test-results/platform-browser-python'/str(uuid.uuid4())
    output.mkdir(parents=True)
    data = output/'data'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = 'http://127.0.0.1:'+str(port)
    process = None
    with (output/'server.log').open('w', encoding='utf-8') as log:
        def start():
            nonlocal process
            process = subprocess.Popen([sys.executable, '-m', 'scripts.browser_fixture_server', '--port', str(port), '--platform-data', str(data)], cwd=ROOT, stdout=log, stderr=log, env={**os.environ, 'PYTHONUTF8': '1'})
            for _ in range(100):
                try:
                    if httpx.get(base+'/api/health', timeout=1).status_code == 200:
                        return
                except httpx.HTTPError:
                    time.sleep(.1)
            raise RuntimeError('Platform did not start')
        try:
            start()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get('CHROME_PATH', r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'))
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: print('Browser error: '+str(error)))
                page.goto(base+'/#space/chat')
                page.locator('#platformData').click()
                page.locator('#platformPreview').click()
                expect(page.locator('#platformApply')).to_be_visible()
                page.locator('#platformApply').click()
                expect(page.locator('#platformStatus')).to_contain_text('迁移完成', timeout=15000)
                page.locator('#platformNoteTitle').fill('Python 持久化验证')
                page.locator('#platformNoteContent').fill('这是经过用户预览并确认的笔记。')
                page.locator('#platformNotePreview').click()
                expect(page.locator('#platformNoteConfirm')).to_be_visible()
                db = Database(data/'workspace.sqlite')
                try:
                    assert db.one('SELECT COUNT(*) AS n FROM audits')['n'] == 0
                finally:
                    db.close()
                page.locator('#platformNoteConfirm').click()
                page.wait_for_function("!document.querySelector('#platformDialog')?.open", timeout=15000)
                page.wait_for_load_state('networkidle')
                page.goto(base+'/#space/cards')
                expect(page.locator('#cardList')).to_contain_text('Python 持久化验证')
                process.terminate()
                process.wait(timeout=10)
                start()
                page.reload()
                expect(page.locator('#cardList')).to_contain_text('Python 持久化验证')
                page.get_by_role('link', name='课程资料', exact=False).first.click()
                page.locator('#fileInput').set_input_files({'name': 'Python服务端上传.md', 'mimeType': 'text/markdown', 'buffer': '后台解析与原件保存验证。'.encode()})
                row = page.locator('.document-row').filter(has_text='Python服务端上传.md')
                expect(row).to_contain_text('已解析，可检索', timeout=15000)
                db = Database(data/'workspace.sqlite')
                try:
                    assert db.one('SELECT COUNT(*) AS n FROM audits')['n'] == 1
                    assert db.one("SELECT COUNT(*) AS n FROM jobs WHERE status='succeeded'")['n'] >= 1
                    assert db.one("SELECT COUNT(*) AS n FROM receipts")['n'] == 1
                finally:
                    db.close()
                page.screenshot(path=str(output/'platform-persisted.png'), full_page=True)
                browser.close()
            print('Platform browser passed: explicit migration, preview before write, confirmation/audit/receipt, server restart persistence and isolated file parse job. No paid models.')
        finally:
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
