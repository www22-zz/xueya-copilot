"""G4 actual Chrome flow; isolated DB/profile, no provider credentials or paid requests."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import sys
import uvicorn

from scripts.check_learning_browser import Browser
from backend.xueya.app import create_app
from backend.xueya.config import Config, ROOT


@contextmanager
def server(folder):
    app = create_app(Config(data_dir=folder/'data'))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    host = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    thread = threading.Thread(target=host.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if host.started:
                break
            time.sleep(.02)
        assert host.started
        yield f'http://127.0.0.1:{port}', app
    finally:
        host.should_exit = True
        thread.join(8)
        sock.close()
        assert not thread.is_alive()


def main():
    output = ROOT/'test-results/g4-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-g4-') as directory:
        folder = Path(directory)
        with server(folder) as (base, app):
            p = app.state.platform
            p.repo.put(p.scope(), 'source', 'plant', {'id': 'plant', 'documentId': 'plant-doc', 'title': '无关标题', 'quote': '光合作用发生在叶绿体。', 'location': '第1段'})
            p.repo.put(p.scope(), 'document', 'plant-doc', {'id': 'plant-doc', 'name': '植物.md'})
            browser = Browser(folder)
            try:
                browser.call('Page.navigate', url=base+'/#space/chat')
                browser.wait('!!document.querySelector("#cLearning") && !!document.querySelector("#searchTrigger")')
                browser.click('#searchTrigger')
                browser.wait('!!document.querySelector("[data-g4-form=search]")')
                browser.fill('[data-g4-form=search] [name=query]', '光合作用')
                browser.evaluate('document.querySelector("[data-g4-form=search]").requestSubmit()')
                browser.wait('!!document.querySelector("[data-g4=read]")')
                browser.click('[data-g4=read]')
                browser.wait('document.querySelector("#g4Detail").innerText.includes("叶绿体")')
                browser.fill('[data-g4-form=policy] [name=budget]', '12000')
                browser.evaluate('document.querySelector("[data-g4-form=policy]").requestSubmit()')
                browser.wait('document.querySelector("[data-g4-form=policy] [name=budget]").value === "12000" && !document.querySelector("#g4Dialog [role=status]")')
                browser.fill('[data-g4-form=ask] [name=query]', '光合作用发生在哪里？')
                browser.evaluate('document.querySelector("[data-g4-form=ask]").requestSubmit()')
                browser.wait('!!document.querySelector("[data-g4=result]")')
                browser.click('[data-g4=result]')
                browser.wait('document.querySelector("#g4Detail").innerText.includes("叶绿体")')
                if '--with-content' in sys.argv:
                    browser.click('[data-g4=convert-result]')
                    browser.wait('!!document.querySelector("#g3Dialog [data-g3-form=convert]")')
                    browser.evaluate('document.querySelector("#g3Dialog [data-g3-form=convert]").requestSubmit()')
                    browser.wait('!!document.querySelector("#g3Dialog [data-g3=adopt]:not(:disabled)")')
                    browser.click('#g3Dialog [data-g3=adopt]')
                    browser.wait('!document.querySelector("#g3Dialog").open')
                    browser.click('#searchTrigger')
                    browser.wait('!!document.querySelector("[data-g4-form=search]")')
                browser.screenshot(output/'desktop.png')
                browser.click('[data-g4=close]')
                browser.reload()
                browser.click('#searchTrigger')
                browser.wait('document.querySelector("[data-g4-form=policy] [name=budget]")?.value === "12000"')
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                browser.screenshot(output/'mobile.png')
                assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                assert not browser.errors, browser.errors
                (output/'report.json').write_text(json.dumps({'passed': True, 'flows': ['body search', 'open actual source', 'context policy save/refresh', 'queued excerpt answer', '390px layout'], 'contentConversion': '--with-content' in sys.argv, 'paidApiCalls': 0}, indent=2), encoding='utf-8')
            finally:
                browser.ws.close()
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(browser.process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    browser.process.terminate()
                browser.process.wait(timeout=10)


if __name__ == '__main__':
    main()
