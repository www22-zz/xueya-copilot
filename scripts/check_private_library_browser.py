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
                # An unassigned old browser workspace must remain preserved, and
                # must not be adopted by another signed-in account on this PC.
                page.evaluate("localStorage.setItem('xueya-copilot-workspace-v3',JSON.stringify({legacy:'UNASSIGNED_BROWSER_9361'}))")
                assert context.request.post(base+'/api/account/logout',headers=headers,data={}).ok
                login('bobby',True)
                page.reload();expect(page.locator('#chatThread')).to_be_visible()
                assert 'ALICE_PRIVATE_CHAT_9204' not in page.locator('body').inner_text()
                assert 'UNASSIGNED_BROWSER_9361' not in page.locator('body').inner_text()
                assert page.evaluate('window.XueyaDataOwner')!=alice_owner
                page.goto(base+'/#space/knowledge');page.get_by_role('button',name='查看资料',exact=True).click()
                expect(page.locator('body')).not_to_contain_text('Alice-private.md')
                bob_headers={'X-Xueya-Token':context.request.get(base+'/api/platform/bootstrap').json()['token']}
                denied=context.request.get(base+'/api/platform/documents/original?documentId='+job['result']['documentId'],headers=bob_headers)
                assert denied.status>=400
                assert context.request.post(base+'/api/account/logout',headers=bob_headers,data={}).ok
                login('alice');page.reload();page.goto(base+'/#space/ask')
                expect(page.locator('#chatThread')).to_contain_text('ALICE_PRIVATE_CHAT_9204')
                page.reload();expect(page.locator('#chatThread')).to_contain_text('ALICE_PRIVATE_CHAT_9204')
                for theme in ('light','dark'):
                    for width,height in ((1400,950),(390,844)):
                        page.set_viewport_size({'width':width,'height':height})
                        page.evaluate('(theme)=>{document.documentElement.dataset.theme=theme}',theme)
                        page.screenshot(path=str(output/f'{theme}-{width}.png'),full_page=True)
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'), page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&getComputedStyle(e).position!=='fixed').map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right})).slice(0,12)")
                assert page.evaluate("localStorage.getItem('xueya-copilot-workspace-v3')")==json.dumps({'legacy':'UNASSIGNED_BROWSER_9361'},separators=(',',':'))
                assert not errors,errors
                browser.close()
                result={'account_switch':'passed','private_upload':'passed','guessed_original':'denied','refresh_restore':'passed',
                        'legacy_browser_preserved':True,'page_errors':errors,'paid_calls':0,'screenshots':4}
                (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(result,ensure_ascii=False))
        finally:
            server.should_exit=True;worker.join(6);sock.close();assert not worker.is_alive()


if __name__=='__main__':
    main()
