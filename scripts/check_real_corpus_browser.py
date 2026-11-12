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
from backend.xueya.common import Scope
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
            docs = [d for d in p.repo.all(Scope(user_id=args.owner, course_id='course-default'), 'document') if not d.get('archived') and not d.get('superseded')]
            expected_count = len(docs)
            stack = next(d for d in docs if d['name'] == '栈与队列知识库.md')
            indexed = sum(d.get('indexStatus') == 'ready' and d.get('embeddingIdentity') == app.state.rag.embedding.identity for d in docs)
            os.environ['CHROME_PATH'] = browser_path()
            browser = Browser(Path(temporary))
            try:
                browser._authenticated_origin = base
                browser.call('Network.setCookie', name='xueya_session', value=token, url=base, httpOnly=True)
                browser.call('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
                browser.call('Page.navigate', url=base+'/#space/knowledge')
                browser.wait('document.querySelectorAll(".kb-document").length === '+str(expected_count))
                assert browser.evaluate('document.querySelectorAll("#kbSearch,.lw-probe,[data-kb=jump-search]").length') == 0
                assert browser.evaluate('document.querySelectorAll("#knowledgeWorkspace a[href=\\\"#space/library/manage\\\"],#lwConfigBody,[aria-labelledby=lwConfigTitle]").length') == 0
                assert browser.evaluate('!document.querySelector(".lw-overview") && !!document.querySelector("#kbUploadToggle") && !!document.querySelector("#lwScaleBody")')
                assert browser.evaluate('document.querySelector("#courseSelect option:checked").textContent') == '栈与队列知识库'
                assert browser.evaluate('document.querySelector("#lwDocsTitle").textContent.startsWith("个人资料列表")')
                assert browser.evaluate('!document.querySelector("#kbUploadPanel") && !document.querySelector("#kbUploadDialog[open]")')
                browser.evaluate('document.documentElement.dataset.theme="dark"')
                point = browser.evaluate('(()=>{const r=document.querySelector("#kbUploadToggle").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
                browser.call('Input.dispatchMouseEvent', type='mouseMoved', **point)
                browser.wait('getComputedStyle(document.querySelector("#kbUploadToggle")).filter.includes("brightness")')
                time.sleep(.2)
                browser.screenshot(out/'upload-button-hover-dark.png')
                browser.click('#kbUploadToggle')
                assert browser.evaluate('!!document.querySelector("#kbUploadDialog[open]") && document.querySelector("#kbUploadDialog").contains(document.activeElement)')
                assert browser.evaluate('document.querySelector("#kbUploadStart").disabled')
                browser.fill('#kbUploadChapter', '上传章节保留检查')
                browser.screenshot(out/'upload-desktop.png')
                browser.click('#kbUploadDialog [data-kb=upload-close]')
                browser.click('#kbUploadToggle')
                assert browser.evaluate('document.querySelector("#kbUploadChapter").value') == '上传章节保留检查'
                browser.call('Input.dispatchKeyEvent', type='keyDown', key='Escape', code='Escape', windowsVirtualKeyCode=27)
                browser.call('Input.dispatchKeyEvent', type='keyUp', key='Escape', code='Escape', windowsVirtualKeyCode=27)
                browser.wait('!document.querySelector("#kbUploadDialog[open]")')
                browser.wait('document.activeElement.id === "kbUploadToggle"')
                stale_write = browser.evaluate('''(async()=>{const b=await(await fetch('/api/platform/bootstrap')).json();const headers={'Content-Type':'application/json','X-Xueya-Token':b.token};const c=await(await fetch('/api/platform/courses',{method:'POST',headers,body:JSON.stringify({id:'course-default',name:'数据结构'})})).json();const w=await(await fetch('/api/platform/workspace',{headers})).json();const value=w.workspace.data;value.courses.find(c=>c.id==='course-default').name='数据结构';const saved=await(await fetch('/api/platform/workspace',{method:'PUT',headers,body:JSON.stringify({workspace:value,expectedVersion:w.workspace.version})})).json();return {course:c.courses.find(c=>c.id==='course-default').name,workspace:saved.workspace.data.courses.find(c=>c.id==='course-default').name};})()''')
                assert stale_write == {'course': '栈与队列知识库', 'workspace': '栈与队列知识库'}, stale_write
                assert browser.evaluate('document.querySelectorAll(".kb-document").length') == expected_count
                assert browser.evaluate('[...document.querySelectorAll(".kb-document h3")].some(n=>n.textContent==="栈与队列知识库.md")')
                assert browser.evaluate('document.querySelector("#lwScaleBody").textContent').find(str(indexed)+' / '+str(expected_count)) >= 0
                assert '期中复习题 2024.pdf' not in browser.evaluate('document.querySelector("#kbDocuments").textContent')
                browser.click('[data-document-id="'+stack['id']+'"] [data-kb=index]')
                browser.wait('!!document.querySelector("#kbIndexConfirm")')
                assert browser.evaluate('document.querySelector("#kbDialog").textContent.includes("Qwen3-VL-Embedding-2B")')
                assert browser.evaluate('document.querySelector("#kbDialog").textContent.includes("可复用 178 条已有向量，0 条需要计算")')
                assert not browser.evaluate('document.querySelector("#kbIndexConfirm").checkValidity()')
                browser.screenshot(out/'index-confirmation.png')
                browser.click('#kbDialog [data-kb=close]')
                browser.screenshot(out/'catalog-desktop.png')
                retrieval = browser.evaluate('''(async()=>{const b=await(await fetch('/api/platform/bootstrap')).json();const r=await fetch('/api/platform/knowledge/search',{method:'POST',headers:{'Content-Type':'application/json','X-Xueya-Token':b.token},body:JSON.stringify({courseId:'course-default',query:'循环队列',mode:'lexical'})});const v=await r.json();return {ok:v.ok,hits:v.evidence?.sources?.length};})()''')
                assert retrieval['ok'] and retrieval['hits'] > 0
                scope_check = browser.evaluate('''(async()=>{const b=await(await fetch('/api/platform/bootstrap')).json(); const r=await fetch('/api/platform/rag/search',{method:'POST',headers:{'Content-Type':'application/json','X-Xueya-Token':b.token},body:JSON.stringify({courseId:'course-default',documentIds:__STACK_IDS__,query:'KMP',mode:'lexical',budget:3000,limit:6})});const v=await r.json();return {ok:v.ok,hits:v.evidence?.sources?.length};})()'''.replace('__STACK_IDS__', json.dumps([stack['id']])))
                assert scope_check == {'ok': True, 'hits': 0}, scope_check
                browser.reload()
                browser.wait('document.querySelectorAll(".kb-document").length === '+str(expected_count))
                assert browser.evaluate('document.querySelector("#courseSelect option:checked").textContent') == '栈与队列知识库'
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                browser.screenshot(out/'catalog-mobile.png')
                assert not browser.evaluate('document.documentElement.scrollWidth > innerWidth+1')
                browser.click('#kbUploadToggle')
                assert not browser.evaluate('document.documentElement.scrollWidth > innerWidth+1')
                browser.screenshot(out/'upload-mobile.png')
                assert browser.evaluate('document.querySelector("#kbUploadDialog").scrollWidth <= document.querySelector("#kbUploadDialog").clientWidth+1')
                errors = browser.errors
                assert not errors, errors
            finally:
                browser.close()
            assert invocations == p.db.one('SELECT count(*) AS n FROM invocations')['n']
            (out/'report.json').write_text(json.dumps({'status': 'passed', 'documents': expected_count, 'checks': ['actual-active-documents', 'no-phantoms', 'lexical-retrieval', 'reload', 'mobile-no-overflow'], 'newModelInvocations': 0, 'pageErrors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
            print('Actual-corpus browser:', expected_count, 'documents, zero new model invocations.')
        finally:
            host.should_exit = True
            worker.join(10)
            sock.close()
            assert not worker.is_alive()


if __name__ == '__main__':
    main()
