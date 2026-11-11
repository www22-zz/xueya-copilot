"""Fresh machine browser proof: no .env, private DB, prior cache, or model call."""
from pathlib import Path
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import uvicorn
from backend.xueya.app import create_app
from backend.xueya.config import ROOT, Config
from scripts.browser_runtime import browser_path
from scripts.check_learning_browser import Browser


def main():
    out = ROOT/'test-results/portable-knowledge'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='portable-knowledge-') as temporary:
        directory = Path(temporary)
        root = directory/'clone'
        for folder in ('frontend', 'shared', 'materials/stack-queue'):
            shutil.copytree(ROOT/folder, root/folder)
        config = Config(root=root, data_dir=directory/'brand-new-data', auto_import_stack=True)
        app = create_app(config)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0))
        base = 'http://127.0.0.1:'+str(sock.getsockname()[1])
        host = uvicorn.Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=3))
        worker = threading.Thread(target=lambda:host.run(sockets=[sock]), daemon=True); worker.start()
        try:
            for _ in range(200):
                if host.started:break
                time.sleep(.05)
            assert host.started
            os.environ['CHROME_PATH'] = browser_path()
            browser = Browser(directory)
            try:
                # Existing helper registers an isolated test account here.
                browser.call('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
                browser.call('Page.navigate', url=base+'/#space/knowledge')
                browser.wait('document.querySelectorAll(".kb-document").length === 1')
                assert browser.evaluate('document.querySelector("#kbBase option:checked").textContent') == '栈与队列知识库'
                assert browser.evaluate('document.querySelector(".kb-document").textContent.includes("已有缓存，服务未配置")')
                assert browser.evaluate('document.querySelector("#lwOverviewStats li strong").textContent') == '1'
                browser.screenshot(out/'fresh-clone-no-keys.png')
                browser.fill('#kbQuery', '循环队列')
                browser.click('#kbSearch button[type=submit]')
                browser.wait('!!document.querySelector(".kb-result")')
                browser.reload()
                browser.wait('document.querySelectorAll(".kb-document").length === 1')
                assert not browser.errors, browser.errors
                p = app.state.platform
                assert not p.db.one('SELECT id FROM invocations')
                (out/'browser.json').write_text(json.dumps({'status':'passed','freshDatabase':True,'envCopied':False,'documentsPerOwner':1,'vectorsPerOwner':178,'newModelRequests':0,'lexicalWorksWithoutKeys':True,'pageErrors':browser.errors},indent=2),encoding='utf-8')
                print('Fresh clone browser passed: one file, existing vectors, no keys or model calls.')
            finally:
                browser.close()
        finally:
            host.should_exit=True; worker.join(10); sock.close()
            assert not worker.is_alive()


if __name__ == '__main__':
    main()
