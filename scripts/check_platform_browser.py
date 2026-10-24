"""UI confirmation, server persistence and original-file job checks; no paid API."""
import os
import socket
import subprocess
import sys
import time
import uuid
import re
import httpx
from playwright.sync_api import sync_playwright, expect
from backend.config import ROOT
from backend.xueya.database import Database


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
            process = subprocess.Popen([sys.executable, '-m', 'backend.xueya.server'], cwd=ROOT, stdout=log, stderr=log, env={**os.environ, 'PYTHONUTF8': '1', 'PORT':str(port),'XUEYA_DATA_DIR':str(data),'MIMO_API_KEY':'','XUEYA_AUTO_IMPORT_DEMO':'0'})
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
                browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get('CHROME_PATH', r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: print('Browser error: '+str(error)))
                page.request.post(base+'/api/account/register',data={'username':'platformuser','password':'Platform123','confirmPassword':'Platform123'})
                page.goto(base+'/#space/ask')
                page.locator('#appSettingsButton').click()
                page.locator('[data-settings-tab=services]').click()
                page.locator('#platformData').click()
                page.locator('#platformPreview').click()
                expect(page.locator('#platformApply')).to_be_visible()
                page.locator('#platformApply').click()
                expect(page.locator('#platformStatus')).to_contain_text('迁移完成', timeout=15000)
                assert page.locator('#platformNoteTitle').count()==0
                assert page.locator('#platformNoteConfirm').count()==0
                page.locator('#platformClose').click()
                page.goto(base+'/#space/practice/hot100')
                page.locator('[data-note]').fill('每题随手记持久化验证')
                page.wait_for_function("JSON.parse(localStorage.getItem('xueya-practice-v1:platformuser')||'{}').notes?.['h100-01']?.text==='每题随手记持久化验证'")
                page.wait_for_function("JSON.parse(localStorage.getItem('xueya-practice-ops:platformuser')||'[]').length===0")
                process.terminate()
                process.wait(timeout=10)
                start()
                login=page.request.post(base+'/api/account/login',data={'username':'platformuser','password':'Platform123'})
                assert login.ok
                page.reload()
                bootstrap=page.request.get(base+'/api/platform/bootstrap').json()
                persisted=page.request.get(base+'/api/practice/state',headers={'X-Xueya-Token':bootstrap['token']}).json()
                assert persisted['notes']['h100-01']['text']=='每题随手记持久化验证'
                expect(page.locator('[data-note]')).to_have_value('每题随手记持久化验证')
                page.goto(base+'/#space/knowledge')
                page.get_by_role('button', name='上传资料', exact=True).click()
                page.locator('#kbFiles').set_input_files({'name': 'Python服务端上传.md', 'mimeType': 'text/markdown', 'buffer': '后台解析与原件保存验证。'.encode()})
                page.get_by_role('button', name='查看资料', exact=True).click()
                row = page.locator('.kb-document').filter(has_text='Python服务端上传.md')
                expect(row.locator('.kb-status')).to_contain_text(re.compile('已解析|完成|可检索'), timeout=15000)
                db = Database(data/'workspace.sqlite')
                try:
                    assert db.one("SELECT COUNT(*) AS n FROM entities WHERE user_id='practice:platformuser' AND kind='event'")['n'] >= 1
                    assert db.one("SELECT COUNT(*) AS n FROM jobs WHERE status='succeeded'")['n'] >= 1
                    assert db.one("SELECT COUNT(*) AS n FROM entities WHERE kind='note'")['n'] == 0
                finally:
                    db.close()
                page.screenshot(path=str(output/'platform-persisted.png'), full_page=True)
                browser.close()
            print('Platform browser passed: explicit migration, retired note UI absent, per-question note server restart persistence and isolated file parse job. No paid models.')
        finally:
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
