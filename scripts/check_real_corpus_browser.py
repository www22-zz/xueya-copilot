"""Browser acceptance on a disposable copy of the imported corpus, no AI calls."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import threading
import time

import uvicorn
from backend.xueya.account_scope import account_owner
from backend.xueya.app import create_app
from backend.xueya.backup import create_backup
from backend.xueya.config import ROOT, Config, load_config
from scripts.browser_runtime import browser_path
from scripts.check_learning_browser import Browser
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True)
    args = parser.parse_args()
    out = ROOT/'test-results/stack-only/browser'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-corpus-browser-') as temporary:
        directory = Path(temporary)/'snapshot'
        create_backup(load_config().data_dir, directory)
        app = create_app(Config(root=ROOT, data_dir=directory, preserve_legacy_data=True, auto_import_demo=False), start_jobs=False)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0))
        base = 'http://127.0.0.1:'+str(sock.getsockname()[1])
        host = uvicorn.Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=3))
        worker = threading.Thread(target=lambda: host.run(sockets=[sock]), daemon=True)
        worker.start()
        try:
            for _ in range(200):
                if host.started:
                    break
                time.sleep(.05)
            assert host.started
            p = app.state.platform
            # A test session exists only inside the disposable snapshot host.
            records = [json.loads(r['value']) for r in p.db.all("SELECT value FROM meta WHERE key='local-account-v1' OR key LIKE 'account-v2:%'")]
            record = next(r for r in records if account_owner(r) == args.owner)
            token = 'isolated-corpus-browser-session'
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            app.state.account.sessions[token_hash] = time.monotonic()+300
            app.state.account.identities[token_hash] = record['username']
            invocations = p.db.one('SELECT count(*) AS n FROM invocations')['n']
            os.environ['CHROME_PATH'] = browser_path()
            browser = Browser(Path(temporary))
            try:
                browser._authenticated_origin = base
                browser.call('Network.setCookie', name='xueya_session', value=token, url=base, httpOnly=True)
                browser.call('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
                browser.call('Page.navigate', url=base+'/#space/knowledge')
                browser.wait('document.querySelectorAll(".kb-document").length === 1')
                assert browser.evaluate('document.querySelector("#kbBase option:checked").textContent') == '栈与队列知识库'
                stale_write = browser.evaluate('''(async()=>{const b=await(await fetch('/api/platform/bootstrap')).json();const headers={'Content-Type':'application/json','X-Xueya-Token':b.token};const c=await(await fetch('/api/platform/courses',{method:'POST',headers,body:JSON.stringify({id:'course-default',name:'数据结构'})})).json();const w=await(await fetch('/api/platform/workspace',{headers})).json();const value=w.workspace.data;value.courses.find(c=>c.id==='course-default').name='数据结构';const saved=await(await fetch('/api/platform/workspace',{method:'PUT',headers,body:JSON.stringify({workspace:value,expectedVersion:w.workspace.version})})).json();return {course:c.courses.find(c=>c.id==='course-default').name,workspace:saved.workspace.data.courses.find(c=>c.id==='course-default').name};})()''')
                assert stale_write == {'course': '栈与队列知识库', 'workspace': '栈与队列知识库'}, stale_write
                assert browser.evaluate('document.querySelector("#lwOverviewStats li strong").textContent') == '1'
                assert browser.evaluate('document.querySelectorAll("#lwOverviewStats li strong")[2].textContent') == '1'
                assert browser.evaluate('document.querySelector(".kb-document h3").textContent') == '栈与队列知识库.md'
                assert browser.evaluate('document.querySelector("#lwScaleBody").textContent.includes("1 / 1")')
                assert '期中复习题 2024.pdf' not in browser.evaluate('document.querySelector("#kbDocuments").textContent')
                assert '待解析' not in browser.evaluate('document.querySelector("#lwSyncText").textContent')
                browser.screenshot(out/'catalog-desktop.png')
                browser.fill('#kbQuery', '循环队列')
                browser.click('#kbSearch button[type=submit]')
                browser.wait('!!document.querySelector(".kb-result")')
                scope_check = browser.evaluate('''(async()=>{const b=await(await fetch('/api/platform/bootstrap')).json(); const r=await fetch('/api/platform/rag/search',{method:'POST',headers:{'Content-Type':'application/json','X-Xueya-Token':b.token},body:JSON.stringify({courseId:'course-default',query:'KMP',mode:'lexical',budget:3000,limit:6})});const v=await r.json();return {ok:v.ok,hits:v.evidence?.sources?.length};})()''')
                assert scope_check == {'ok': True, 'hits': 0}, scope_check
                browser.evaluate('document.querySelector("#kbResults").scrollIntoView()')
                browser.screenshot(out/'lexical-retrieval.png')
                browser.reload()
                browser.wait('document.querySelectorAll(".kb-document").length === 1')
                assert browser.evaluate('document.querySelector("#kbBase option:checked").textContent') == '栈与队列知识库'
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                browser.screenshot(out/'catalog-mobile.png')
                assert not browser.evaluate('document.documentElement.scrollWidth > innerWidth+1')
                errors = browser.errors
                assert not errors, errors
            finally:
                browser.close()
            assert invocations == p.db.one('SELECT count(*) AS n FROM invocations')['n']
            (out/'report.json').write_text(json.dumps({'status': 'passed', 'documents': 1, 'checks': ['single-selected-file', 'no-phantoms', 'lexical-retrieval', 'reload', 'mobile-no-overflow'], 'newModelInvocations': 0, 'pageErrors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
            print('Stack-only browser: 1 document, 5 checks, zero new model invocations.')
        finally:
            host.should_exit = True
            worker.join(10)
            sock.close()
            assert not worker.is_alive()


if __name__ == '__main__':
    main()
