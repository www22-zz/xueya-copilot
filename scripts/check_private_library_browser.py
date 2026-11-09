"""Account switches, persisted conversations and materials in the local browser."""
import json
from pathlib import Path
import socket
import tempfile
import threading
import time

import uvicorn
from playwright.sync_api import sync_playwright, expect
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.common import Scope
from .browser_runtime import browser_path

ROOT = Path(__file__).resolve().parents[1]


def main():
    output=ROOT/'test-results/private-library';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-private-browser-') as directory:
        app=create_app(Config(root=ROOT,data_dir=Path(directory),auto_import_demo=False,preserve_legacy_data=True))
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',timeout_graceful_shutdown=3))
        worker=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);worker.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            assert server.started
            base=f'http://127.0.0.1:{port}'
            public_scope=Scope(user_id=app.state.platform.user_id,course_id='preset-stack-queue')
            app.state.platform.repo.ensure_course(public_scope.user_id,{'id':public_scope.course_id,'name':'栈与队列公共教材'})
            material=ROOT/'materials/stack-queue/栈与队列知识库.md'
            public_job=app.state.rag.upload(public_scope,material.read_bytes(),material.name,'browser-approved-preset')
            for _ in range(300):
                public_job=app.state.platform.jobs.get(public_job['id'],public_scope.user_id)
                if public_job['status'] in ('succeeded','failed','unknown'):break
                time.sleep(.05)
            assert public_job['status']=='succeeded',public_job
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=browser_path(),headless=True)
                context=browser.new_context(viewport={'width':1400,'height':950})
                context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base) else route.abort())
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                def login(name,register=False):
                    reply=context.request.post(base+'/api/account/'+('register' if register else 'login'),data={
                        'username':name,'password':'Fixture123','confirmPassword':'Fixture123'})
                    assert reply.ok,reply.text()
                    return {'X-Xueya-Token':context.request.get(base+'/api/platform/bootstrap').json()['token']}
                headers=login('alice',True)
                value={'version':3,'activeId':'course-default','courses':[{'id':'course-default','name':'个人课程','archived':False,'data':{
                    'documents':[],'messages':[{'id':'alice-message','role':'user','text':'ALICE_PRIVATE_CHAT_9204'}],
                    'sessions':[{'id':'alice-session','title':'Alice 私人学习','messages':[{'id':'alice-message','role':'user','text':'ALICE_PRIVATE_CHAT_9204'}]}],
                    'sessionId':'alice-session'}}]}
                assert context.request.put(base+'/api/platform/workspace',headers=headers,data={'workspace':value,'expectedVersion':0}).ok
                upload=context.request.post(base+'/api/platform/documents/upload?name=Alice-private.md',headers={**headers,'Idempotency-Key':'private-browser-upload'},data=b'ALICE_PRIVATE_FILE_5042')
                assert upload.ok;job=upload.json()['job']
                for _ in range(100):
                    job=context.request.get(base+'/api/platform/jobs/status?id='+job['id'],headers=headers).json()['job']
                    if job['status'] in ('succeeded','failed','unknown'):break
                    time.sleep(.05)
                assert job['status']=='succeeded',job
                page.goto(base+'/#space/ask');expect(page.locator('#chatThread')).to_contain_text('ALICE_PRIVATE_CHAT_9204')
                alice_owner=page.evaluate('window.XueyaDataOwner');assert alice_owner
                page.evaluate("async()=>{const cache=XueyaFileCache.createCache();await cache.put('same-local-key',new Blob(['ALICE_CACHE_PRIVATE_7092']));}")
                # An unassigned old browser workspace must remain preserved, and
                # must not be adopted by another signed-in account on this PC.
                page.evaluate("localStorage.setItem('xueya-copilot-workspace-v3',JSON.stringify({legacy:'UNASSIGNED_BROWSER_9361'}))")
                assert context.request.post(base+'/api/account/logout',headers=headers,data={}).ok
                login('bobby',True)
                page.reload();expect(page.locator('#chatThread')).to_be_visible()
                assert 'ALICE_PRIVATE_CHAT_9204' not in page.locator('body').inner_text()
                assert 'UNASSIGNED_BROWSER_9361' not in page.locator('body').inner_text()
                assert page.evaluate('window.XueyaDataOwner')!=alice_owner
                assert page.evaluate("async()=>Boolean(await XueyaFileCache.createCache().get('same-local-key'))") is False
                page.goto(base+'/#space/knowledge');page.get_by_role('button',name='查看资料',exact=True).click()
                expect(page.locator('body')).not_to_contain_text('Alice-private.md')
                bob_headers={'X-Xueya-Token':context.request.get(base+'/api/platform/bootstrap').json()['token']}
                denied=context.request.get(base+'/api/platform/documents/original?documentId='+job['result']['documentId'],headers=bob_headers)
                assert denied.status>=400
                evidence=context.request.post(base+'/api/platform/rag/search',headers=bob_headers,data={
                    'query':'循环队列 front rear','mode':'lexical','budget':3000,'limit':6}).json()['evidence']
                assert evidence['sources'] and all(s['originCourseId']==public_scope.course_id and 'quote' not in s for s in evidence['sources'])
                # Seed a clearly labelled saved UI fixture using the actual HTTP
                # source DTO. This checks quote-free citations, not model quality.
                public_message={'id':'public-citation-ui','role':'ai','text':'来源界面验证（非AI生成）。','sources':[evidence['sources'][0]]}
                bob_value=json.loads(json.dumps(value))
                bob_data=bob_value['courses'][0]['data']
                bob_data.update(messages=[public_message],sessions=[{'id':'bob-public-session','title':'公共来源界面验证','messages':[public_message]}],sessionId='bob-public-session')
                current=context.request.get(base+'/api/platform/workspace',headers=bob_headers).json()['workspace']
                saved=context.request.put(base+'/api/platform/workspace',headers=bob_headers,data={'workspace':bob_value,'expectedVersion':current['version'] if current else 0})
                assert saved.ok,saved.text()
                # Use the visible restore workflow, which retains the browser
                # backup, rather than discard a pending browser save silently.
                page.goto(base+'/#space/ask')
                page.locator('button[data-open-settings]:visible').first.click()
                page.locator('[data-settings-tab=services]').click()
                page.locator('#platformData').click()
                with page.expect_navigation(wait_until='load'):
                    page.locator('#platformRestore').click()
                page.goto(base+'/#space/ask')
                expect(page.locator('.citation-chip')).to_contain_text('栈与队列公共教材')
                page.locator('.citation-chip').click()
                expect(page.locator('#sourceDialog')).to_be_visible()
                expect(page.locator('.source-location')).to_contain_text('栈与队列公共教材')
                expect(page.locator('#readerPassage')).to_contain_text('平台预置资料仅供 AI 回答参考')
                expect(page.locator('#sourceDialog .eyebrow')).to_have_text('公共资料来源')
                expect(page.locator('#readerSearch')).to_have_count(0)
                expect(page.get_by_role('button',name='下载原件',exact=True)).to_have_count(0)
                expect(page.get_by_role('button',name='导出正文',exact=True)).to_have_count(0)
                page.screenshot(path=str(output/'public-origin-metadata.png'),full_page=True,animations='disabled')
                page.get_by_role('button',name='关闭原文',exact=True).click()
                assert context.request.post(base+'/api/account/logout',headers=bob_headers,data={}).ok
                login('alice');page.reload();page.goto(base+'/#space/ask')
                expect(page.locator('#chatThread')).to_contain_text('ALICE_PRIVATE_CHAT_9204')
                page.reload();expect(page.locator('#chatThread')).to_contain_text('ALICE_PRIVATE_CHAT_9204')
                assert page.evaluate("async()=>(await XueyaFileCache.createCache().get('same-local-key')).text()")=='ALICE_CACHE_PRIVATE_7092'
                for theme in ('light','dark'):
                    for width,height in ((1400,950),(390,844)):
                        page.set_viewport_size({'width':width,'height':height})
                        page.evaluate('(theme)=>{document.documentElement.dataset.theme=theme}',theme)
                        page.screenshot(path=str(output/f'{theme}-{width}.png'),full_page=True,animations='disabled')
                        page.wait_for_function('document.documentElement.scrollWidth <= innerWidth+1',timeout=5000)
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'), page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&getComputedStyle(e).position!=='fixed').map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right})).slice(0,12)")
                assert page.evaluate("localStorage.getItem('xueya-copilot-workspace-v3')")==json.dumps({'legacy':'UNASSIGNED_BROWSER_9361'},separators=(',',':'))
                assert not errors,errors
                browser.close()
                result={'account_switch':'passed','private_upload':'passed','guessed_original':'denied','refresh_restore':'passed',
                        'legacy_browser_preserved':True,'original_cache_isolation':'passed','cross_course_public_metadata':'passed',
                        'page_errors':errors,'paid_calls':0,'screenshots':5}
                (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(result,ensure_ascii=False))
        finally:
            server.should_exit=True;worker.join(6);sock.close();assert not worker.is_alive()


if __name__=='__main__':
    main()
