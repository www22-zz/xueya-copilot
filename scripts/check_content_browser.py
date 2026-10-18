"""G3 actual browser flow; isolated profile/database and controlled model only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from scripts.check_learning_browser import Browser, server
from backend.xueya.config import ROOT


def main():
    output = ROOT/"test-results/g3-browser"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="xueya-g3-") as directory:
        folder = Path(directory)
        with server(folder) as (base, app):
            scope = app.state.platform.scope()
            app.state.platform.repo.put(scope, "source", "g3-source", {"id": "g3-source", "documentId": "g3-doc", "title": "植物", "quote": "光合作用发生在叶绿体。", "location": "原文第一段"})
            app.state.platform.repo.put(scope, "document", "g3-doc", {"id": "g3-doc", "name": "植物.md", "chunks": []})
            browser = Browser(folder)
            try:
                browser.call("Page.navigate", url=base+"/#space/cards")
                browser.wait('!!document.querySelector("#g3Workspace [data-g3=note-new]")')
                browser.click('[data-g3=note-new]')
                browser.fill('#g3Dialog [name=title]', '我的理解')
                browser.fill('#g3Dialog [name=text]', '个人理解不能当成教材。')
                browser.fill('#g3Dialog [name=pendingQuestions]', '需要核对适用条件。')
                browser.evaluate('document.querySelector("#g3Dialog form").requestSubmit()')
                browser.wait('!!document.querySelector("#g3Dialog [data-g3=adopt]:not(:disabled)")')
                browser.click('#g3Dialog [data-g3=adopt]')
                browser.wait('document.querySelector("#g3Workspace").innerText.includes("我的理解")')
                browser.reload()
                browser.wait('document.querySelector("#g3Workspace")?.innerText.includes("我的理解")')
                browser.evaluate('document.querySelector("[data-g3-form=run] [name=documents]").checked=true;document.querySelector("[data-g3-form=run] [name=allowApi]").checked=true;document.querySelector("[data-g3-form=run]").requestSubmit()')
                browser.wait('!!document.querySelector("#g3Workspace [data-g3=recover]")')
                browser.click('#g3Workspace [data-g3=recover]')
                browser.wait('!!document.querySelector("#g3Dialog [data-g3=adopt]:not(:disabled)")')
                browser.click('#g3Dialog [data-g3=adopt]')
                browser.wait('document.querySelector("#g3Workspace").innerText.includes("template-result")')
                browser.evaluate('document.getElementById("g3Workspace").scrollIntoView({behavior:"instant",block:"start"})')
                browser.screenshot(output/'desktop.png')
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                browser.evaluate('document.getElementById("g3Workspace").scrollIntoView({behavior:"instant",block:"start"})')
                browser.screenshot(output/'mobile.png')
                assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                assert not browser.errors, browser.errors
                (output/'report.json').write_text(json.dumps({"passed": True, "flows": ["personal note preview/adopt", "refresh persistence", "template trial/adopt", "390px layout"], "paidApiCalls": 0}, indent=2), encoding='utf-8')
            finally:
                browser.ws.close()
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(browser.process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    browser.process.terminate()
                browser.process.wait(timeout=10)


if __name__ == '__main__':
    main()
