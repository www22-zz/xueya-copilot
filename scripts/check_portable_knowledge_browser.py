"""Fresh machine browser proof: no .env, private DB, prior cache, or model call."""
from pathlib import Path
import argparse
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import uvicorn
import httpx
from backend.xueya.app import create_app
from backend.xueya.config import ROOT, Config
from scripts.browser_runtime import browser_path
from scripts.check_learning_browser import Browser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shared', action='store_true', help='Verify optional team configuration with a synthetic key and no external call')
    shared = parser.parse_args().shared
    out = ROOT/'test-results/portable-knowledge'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='portable-knowledge-') as temporary:
        directory = Path(temporary)
        root = directory/'clone'
        for folder in ('frontend', 'shared', 'materials/stack-queue'):
            shutil.copytree(ROOT/folder, root/folder)
        if shared:
            template = (ROOT/'.env.team-embedding.example').read_text('utf-8')
            (root/'.env.team-embedding').write_text(template.replace('RAG_EMBEDDING_API_KEY=\n', 'RAG_EMBEDDING_API_KEY=synthetic-browser-key\n'), encoding='utf-8')
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
            if shared:
                assert app.state.rag.embedding is not None
                def forbid_network(request):
                    raise AssertionError('Fresh-clone acceptance must not call a model')
                app.state.rag.embedding.transport = httpx.MockTransport(forbid_network)
            os.environ['CHROME_PATH'] = browser_path()
            browser = Browser(directory)
            try:
                # Existing helper registers an isolated test account here.
                browser.call('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
                browser.call('Page.navigate', url=base+'/#space/knowledge')
                browser.wait('document.querySelectorAll(".kb-document").length === 1')
                assert browser.evaluate('document.querySelectorAll("#kbSearch,.lw-probe,[data-kb=jump-search]").length') == 0
                assert browser.evaluate('document.querySelectorAll("#knowledgeWorkspace a[href=\\\"#space/library/manage\\\"],#lwConfigBody,[aria-labelledby=lwConfigTitle]").length') == 0
                assert browser.evaluate('document.querySelector("#courseSelect option:checked").textContent') == '栈与队列知识库'
                if shared:
                    assert browser.evaluate('document.querySelector("#lwScaleBody").textContent.includes("1 / 1")')
                    browser.click('[data-kb=index]')
                    browser.wait('!!document.querySelector("#kbIndexConfirm")')
                    assert browser.evaluate('document.querySelector("#kbDialog").textContent.includes("Qwen3-VL-Embedding-2B")')
                    assert browser.evaluate('document.querySelector("#kbDialog").textContent.includes("可复用 178 条已有向量，0 条需要计算")')
                    assert not browser.evaluate('document.querySelector("#kbIndexConfirm").checkValidity()')
                    browser.click('#kbIndexConfirm input[type=checkbox]')
                    browser.click('#kbIndexConfirm button')
                    browser.wait('!document.querySelector("#kbDialog[open]")')
                    for _ in range(200):
                        done = app.state.platform.db.one("SELECT status,result FROM jobs WHERE type='rag-index' ORDER BY created_at DESC LIMIT 1")
                        if done and done['status'] == 'succeeded':
                            break
                        time.sleep(.05)
                    assert done and done['status'] == 'succeeded'
                    assert json.loads(done['result'])['computed'] == 0
                    assert browser.evaluate("(async()=> (await fetch('/.env.team-embedding')).status)()") == 404
                else:
                    assert browser.evaluate('document.querySelector(".kb-document").textContent.includes("已有缓存，服务未配置")')
                assert browser.evaluate('document.querySelectorAll(".kb-document").length') == 1
                browser.screenshot(out/('fresh-clone-shared.png' if shared else 'fresh-clone-no-keys.png'))
                retrieval = browser.evaluate('''(async()=>{const b=await(await fetch('/api/platform/bootstrap')).json();const r=await fetch('/api/platform/knowledge/search',{method:'POST',headers:{'Content-Type':'application/json','X-Xueya-Token':b.token},body:JSON.stringify({courseId:'course-default',query:'循环队列',mode:'lexical'})});const v=await r.json();return {ok:v.ok,hits:v.evidence?.sources?.length};})()''')
                assert retrieval['ok'] and retrieval['hits'] > 0
                browser.reload()
                browser.wait('document.querySelectorAll(".kb-document").length === 1')
                assert not browser.errors, browser.errors
                p = app.state.platform
                assert not p.db.one('SELECT id FROM invocations')
                (out/('browser-shared.json' if shared else 'browser.json')).write_text(json.dumps({'status':'passed','freshDatabase':True,'envCopied':False,'sharedEmbeddingConfigured':shared,'documentsPerOwner':1,'vectorsPerOwner':178,'newModelRequests':0,'lexicalWorksWithoutKeys':True,'pageErrors':browser.errors},indent=2),encoding='utf-8')
                print('Fresh clone browser passed: one file, 178 vectors, shared configuration='+str(shared)+', zero model calls.')
            finally:
                browser.close()
        finally:
            host.should_exit=True; worker.join(10); sock.close()
            assert not worker.is_alive()


if __name__ == '__main__':
    main()
