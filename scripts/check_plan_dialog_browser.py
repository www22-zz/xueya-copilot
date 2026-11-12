"""Actual browser proof for plan navigation and draft review; no paid providers."""
import json
from pathlib import Path
import runpy
import socket
import tempfile
import threading
import time
import os

import uvicorn
from backend.xueya.app import create_app
from backend.xueya.config import ROOT, Config
from backend.xueya.rag_http import install_rag
from backend.xueya.rag_service import RagService
from scripts.browser_runtime import browser_path
from scripts.check_learning_browser import Browser


def main():
    out=ROOT/'test-results/plan-dialog';out.mkdir(parents=True,exist_ok=True)
    model=runpy.run_path(str(ROOT/'tests/python/test_conversation_planning.py'))['Model']()
    with tempfile.TemporaryDirectory(prefix='xueya-plan-dialog-') as directory:
        app=create_app(Config(root=ROOT,data_dir=Path(directory)/'data',api_key='controlled-only',preserve_legacy_data=True,auto_import_demo=False),provider=model)
        install_rag(app,service_factory=RagService)
        sock=socket.socket();sock.bind(('127.0.0.1',0));base='http://127.0.0.1:'+str(sock.getsockname()[1])
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',timeout_graceful_shutdown=3))
        worker=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);worker.start()
        try:
            for _ in range(200):
                if server.started:break
                time.sleep(.05)
            assert server.started
            os.environ['CHROME_PATH']=browser_path()
            browser=Browser(Path(directory))
            try:
                browser.call('Page.addScriptToEvaluateOnNewDocument',source="""(()=>{const original=window.fetch;window.fetch=function(url,options){if(String(url).endsWith('/plan/generate')&&options?.method==='POST'){const calls=JSON.parse(sessionStorage.getItem('plan-test-requests')||'[]');calls.push(JSON.parse(options.body));sessionStorage.setItem('plan-test-requests',JSON.stringify(calls));}return original.apply(this,arguments);};})();""")
                requests=lambda:browser.evaluate("JSON.parse(sessionStorage.getItem('plan-test-requests')||'[]')")
                modal='!!document.querySelector(".pw-review-dialog[open]")'
                browser.call('Emulation.setDeviceMetricsOverride',width=1440,height=1000,deviceScaleFactor=1,mobile=False)
                browser.call('Page.navigate',url=base+'/#space/materials/plan')
                browser.wait('!!document.querySelector(".pw-entry-nav")')
                browser.wait('document.querySelector(".pw-entry-nav")?.textContent.includes("定制计划") && document.querySelector(".pw-entry-nav")?.textContent.includes("我的计划")')
                assert not browser.evaluate(modal)
                browser.wait('document.querySelector(".material-learning") && !document.querySelector(".material-learning").textContent.includes("签到记录")')
                browser.wait('document.querySelector("[data-material-manage]")?.textContent === "个人资料库"')
                browser.click('[data-attendance]')
                browser.wait('document.querySelector("[data-attendance]")?.textContent==="今日已签到"')
                browser.evaluate("sessionStorage.setItem(window.XueyaDataKey('xueya-material-return'),JSON.stringify({hash:'#space/materials/test/topic',name:'学习计划.docx'}))")
                browser.click('[data-pw-my-plans]')
                browser.wait('location.hash==="#space/analysis/plans"')
                browser.wait('document.querySelector(".material-return")?.textContent.includes("当前位置：我的学习计划")')
                assert not browser.evaluate('document.querySelector(".material-return").textContent.includes("学习计划.docx")')
                assert not model.calls
                browser.call('Page.navigate',url=base+'/#space/materials/plan')
                browser.wait('!!document.querySelector("[data-pw-goal]")')
                browser.fill('[data-pw-goal]','两周内理解操作系统的进程管理')
                browser.click('[data-pw-generate]')
                browser.wait(modal,timeout=35)
                assert len(requests())==1 and len(model.calls)==2
                assert browser.evaluate('document.querySelectorAll("[data-pw-result] .pw-draft").length')==0
                browser.click('[data-pw-review-close]')
                browser.wait('!'+modal)
                browser.wait('!!document.querySelector("[data-pw-openreview]")')
                browser.reload()
                browser.wait('!!document.querySelector("[data-pw-openreview]")')
                assert not browser.evaluate(modal) and len(requests())==1
                browser.click('[data-pw-openreview]')
                browser.wait(modal)
                browser.click('[data-pw-regenerate]')
                browser.wait('!'+modal)
                browser.wait('document.activeElement.matches("[data-pw-goal]")')
                assert browser.evaluate('document.querySelector("[data-pw-goal]").value')=='两周内理解操作系统的进程管理'
                assert len(requests())==1 and len(model.calls)==2
                model.fail_framework=True
                browser.fill('[data-pw-goal]','两周内理解操作系统的进程管理并进行复习')
                browser.click('[data-pw-generate]')
                browser.wait(modal,timeout=35)
                assert browser.evaluate('!document.querySelector("[data-pw-adopt]").disabled')
                assert browser.evaluate('document.querySelector(".pw-review-dialog").textContent.includes("关联导图生成未完成")')
                assert len(requests())==2 and len(model.calls)==4
                assert requests()[0]['operationId']!=requests()[1]['operationId']
                browser.click('.pw-daily-schedule > summary')
                browser.click('[data-pw-preview]')
                browser.wait('!!document.querySelector(".pw-review-dialog .pw-map")')
                for theme in ('light','dark'):
                    browser.evaluate('document.documentElement.dataset.theme='+json.dumps(theme))
                    for width in (1440,390):
                        browser.call('Emulation.setDeviceMetricsOverride',width=width,height=1000,deviceScaleFactor=1,mobile=False)
                        browser.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                        browser.wait('document.documentElement.scrollWidth<=innerWidth+1')
                        assert browser.evaluate('(()=>{const el=document.querySelector(".pw-review-dialog");return el.scrollWidth<=el.clientWidth+1;})()')
                        assert browser.evaluate('document.querySelector("[data-pw-adopt]").getBoundingClientRect().bottom<=innerHeight')
                        browser.screenshot(out/f'draft-{theme}-{width}.png')
                browser.evaluate('window.confirm=()=>true')
                # Reproduce a saved draft based on an older execution plan.
                service=app.state.study_space
                first=next(p for p in service.list_plans('browser-fixture')['drafts'] if p['goal']=='两周内理解操作系统的进程管理')
                active=service.adopt_plan('browser-fixture',first['id'],first['revision'],True,'test-first-active')
                # Another window completes a task after the adoption preflight.
                browser.evaluate("window.adoptTestFetch=window.fetch;window.fetch=(url,...args)=>String(url).endsWith('/plan/adopt')?new Promise(resolve=>{window.releaseTestAdoption=()=>resolve(window.adoptTestFetch(url,...args))}):window.adoptTestFetch(url,...args)")
                browser.click('[data-pw-adopt]')
                browser.wait('typeof window.releaseTestAdoption === "function"')
                service.toggle_task('browser-fixture',active['id'],active['days'][0]['tasks'][0]['id'],True,expected_revision=active['revision'],operation_id='test-other-window-progress')
                browser.evaluate('window.releaseTestAdoption()')
                browser.wait('document.querySelector("[data-pw-adopt-error]")?.textContent.includes("刚刚发生变化")')
                assert browser.evaluate(modal)
                assert browser.evaluate('!document.querySelector("[data-pw-adopt]").disabled')
                assert not browser.evaluate('document.querySelector("[data-pw-adopt-error]").textContent.includes("PLAN_CURRENT_CHANGED")')
                browser.screenshot(out/'adoption-concurrent-change.png')
                assert service.get_active_plan('browser-fixture')['id']==first['id']
                browser.evaluate('window.fetch=window.adoptTestFetch;delete window.adoptTestFetch;delete window.releaseTestAdoption')
                browser.click('[data-pw-adopt]')
                browser.wait('location.hash==="#space/analysis/plans" && !document.querySelector(".pw-review-dialog[open]")')
                assert browser.evaluate('document.querySelector("#toast").textContent.includes("采用成功")')
                assert service.get_active_plan('browser-fixture')['id']!=first['id']
                assert service.get_plan('browser-fixture',first['id'])['days'][0]['tasks'][0]['completed']
                finished=app.state.platform.db.one("SELECT id FROM jobs WHERE type='space-plan-generate' AND user_id='space:browser-fixture' ORDER BY rowid DESC LIMIT 1")['id']
                # An old recovery receipt must not resurrect an adopted draft.
                browser.evaluate("(()=>{const key=window.XueyaDataKey('xueya-plan-workbench-v1');const value=JSON.parse(sessionStorage.getItem(key)||'{}');value.pending={jobId:"+json.dumps(finished)+"};sessionStorage.setItem(key,JSON.stringify(value));})()")
                browser.call('Page.navigate',url=base+'/#space/materials/plan')
                browser.wait('!!document.querySelector("[data-pw-my-plans]")')
                browser.wait("!JSON.parse(sessionStorage.getItem(window.XueyaDataKey('xueya-plan-workbench-v1'))||'{}').pending")
                assert not browser.evaluate(modal)
                assert browser.evaluate('document.querySelectorAll(".pw-draft-resume").length')==0
                browser.screenshot(out/'adopted-draft-hidden.png')
                browser.click('[data-pw-my-plans]')
                browser.wait('location.hash==="#space/analysis/plans"')
                # The existing My Plans adoption entry uses the same fresh check.
                stale=service.create_plan_draft('browser-fixture',{'title':'我的计划旧草稿','goal':'复习','daysCount':2,'dailyMinutes':30})
                intervening=service.create_plan_draft('browser-fixture',{'title':'临时执行计划','goal':'复习','daysCount':2,'dailyMinutes':30})
                service.adopt_plan('browser-fixture',intervening['id'],1,True,'test-secondary-current')
                browser.reload()
                browser.wait('!!document.querySelector("[data-adopt-draft=\\\"'+stale['id']+'\\\"]")')
                browser.evaluate('window.confirm=()=>true')
                browser.click('[data-adopt-draft="'+stale['id']+'"]')
                browser.wait('document.querySelector("#toast")?.textContent.includes("采用成功")')
                assert service.get_active_plan('browser-fixture')['id']==stale['id']
                assert len(requests())==2 and len(model.calls)==4 and not browser.errors,browser.errors
                (out/'report.json').write_text(json.dumps({'status':'passed','generateRequests':2,'controlledModelCalls':4,'paidApiCalls':0,'checks':['entry-navigation','automatic-draft-dialog','no-inline-plan-stack','close-preserves-draft','reload-without-popup','regenerate-returns-form-no-call','partial-framework-adoption','route-preview','light-dark-mobile','old-draft-replacement','concurrent-change-friendly-error','success-toast-and-close','adopt-navigates-to-my-plans'],'pageErrors':browser.errors},ensure_ascii=False,indent=2),encoding='utf-8')
                print('Plan dialog browser passed: 13 checks, old-draft adoption and concurrent conflict covered, zero paid API calls.')
            finally:
                browser.close()
        finally:
            server.should_exit=True;worker.join(10);sock.close()
            assert not worker.is_alive()


if __name__=='__main__':
    main()
