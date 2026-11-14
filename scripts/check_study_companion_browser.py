"""Real-browser companion checks with a controlled answer, zero model calls."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import uvicorn
from backend.xueya.app import create_app
from backend.xueya.config import Config, ROOT
from backend.xueya.study_space_service import StudySpaceService
from scripts.browser_runtime import browser_path
from scripts.check_learning_browser import Browser


class NoModel:
    async def generate(self, *args, **kwargs):
        raise AssertionError('The companion test must not call a provider')


def main():
    out = ROOT / 'test-results/study-companion'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-companion-') as directory:
        app = create_app(Config(root=ROOT, data_dir=Path(directory)/'data', api_key='',
                                auto_import_demo=False, preserve_legacy_data=True), provider=NoModel())
        sock = socket.socket(); sock.bind(('127.0.0.1', 0))
        base = f'http://127.0.0.1:{sock.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=3))
        worker = threading.Thread(target=lambda:server.run(sockets=[sock]), daemon=True); worker.start()
        try:
            for _ in range(200):
                if server.started: break
                time.sleep(.05)
            assert server.started
            os.environ['CHROME_PATH'] = browser_path()
            browser = Browser(Path(directory))
            try:
                browser.call('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
                browser.call('Page.navigate', url=base+'/#space/materials/plan')
                browser.wait('!!document.querySelector(".companion-robot") && !!document.querySelector("[data-pw-goal]")')
                assert browser.evaluate('document.querySelectorAll(".study-companion").length') == 1
                assert browser.evaluate('document.querySelector(".companion-art").getBoundingClientRect().width') > 80
                browser.click('[data-companion-wave]')
                assert browser.evaluate('document.querySelector(".study-companion").dataset.state') == 'wave'
                browser.screenshot(out/'robot-idle.png')
                browser.click('[data-companion-robot]')
                browser.wait('!document.querySelector("[data-companion-panel]").hidden')
                browser.click('[data-companion-tab="today"]')
                browser.wait('document.querySelector("[data-companion-today]").textContent.includes("还没有正在执行的计划")')
                browser.click('[data-companion-close]')
                # Build today's plan directly in the isolated fixture, no inference.
                service = app.state.study_space
                today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
                draft = service.create_plan_draft('browser-fixture', {'title':'今天的复习', 'goal':'复习线性表',
                    'startDate':today.isoformat(), 'daysCount':2, 'restDays':[], 'schedulingMode':'by-days',
                    'tasks':[{'title':'线性表基础','minutes':30}, {'title':'链表练习','minutes':40}]})
                service.adopt_plan('browser-fixture', draft['id'], 1, True, 'companion-test-adopt')
                # Inject only the answer boundary. The actual DOM, drag, plan API,
                # routing, account keys and storage remain the production code.
                browser.evaluate('''(()=>{
                    window.companionCalls=[];
                    window.XueyaStudyCompanion.mount({
                        ask:async(question,options)=>{companionCalls.push({question,courseId:options.courseId,history:options.history});
                            return new Promise((resolve,reject)=>{window.finishCompanionAnswer=()=>{options.onUpdate({answer:'受控测试回答：链表通过指针连接结点。'});resolve({answer:'受控测试回答：链表通过指针连接结点。',sources:[]});};
                                options.signal.addEventListener('abort',()=>reject(new DOMException('Stopped','AbortError')),{once:true});});},
                        getCourseId:()=>window.companionScope||'course-default',getBusy:()=>false,
                        navigate:hash=>{if(location.hash===hash)dispatchEvent(new HashChangeEvent('hashchange'));else location.hash=hash;}
                    });
                })()''')
                browser.click('[data-companion-robot]')
                browser.fill('[data-companion-input]','链表是什么？')
                old_hash = browser.evaluate('location.hash')
                browser.click('[data-companion-send]')
                browser.wait('document.querySelector(".study-companion").dataset.state==="thinking"')
                assert browser.evaluate('companionCalls.length') == 1
                browser.evaluate('finishCompanionAnswer()')
                browser.wait('document.querySelector(".companion-messages").textContent.includes("链表通过指针")')
                assert browser.evaluate('location.hash') == old_hash
                browser.screenshot(out/'companion-answer.png')
                # Content is rendered as text, not executable HTML.
                browser.fill('[data-companion-input]','<img src=x onerror=alert(1)>')
                browser.click('[data-companion-send]'); browser.wait('companionCalls.length===2')
                assert browser.evaluate('document.querySelectorAll(".companion-messages img").length') == 0
                browser.click('[data-companion-stop]')
                browser.wait('document.querySelector(".companion-messages").textContent.includes("已停止回答")')
                assert browser.evaluate('companionCalls.length') == 2
                # Per-course history never spills into another course.
                browser.evaluate('window.companionScope="other-course";XueyaStudyCompanion.sync()')
                assert not browser.evaluate('document.querySelector(".companion-messages").textContent.includes("链表通过指针")')
                browser.evaluate('window.companionScope="course-default";XueyaStudyCompanion.sync()')
                assert browser.evaluate('document.querySelector(".companion-messages").textContent.includes("链表通过指针")')
                browser.click('[data-companion-tab="today"]')
                browser.wait('document.querySelector("[data-companion-today]").textContent.includes("线性表基础")')
                browser.screenshot(out/'companion-today.png')
                browser.click('[data-companion-start]')
                browser.wait('!!document.querySelector(".route-day-view")')
                assert browser.evaluate('document.querySelector(".route-day-view").textContent.includes("线性表基础")')
                browser.click('[data-companion-minimize]')
                assert not browser.evaluate('document.querySelector("[data-companion-restore]").hidden')
                browser.reload()
                browser.wait('!!document.querySelector("[data-companion-restore]")')
                assert not browser.evaluate('document.querySelector("[data-companion-restore]").hidden')
                browser.click('[data-companion-restore]')
                # Drag through actual pointer input, retaining the new position.
                point = browser.evaluate('(()=>{const b=document.querySelector(".companion-robot").getBoundingClientRect();return{x:b.x+b.width/2,y:b.y+b.height/2};})()')
                browser.evaluate('window.dragProbe=[];for(const type of ["pointerdown","pointermove","pointerup"])document.addEventListener(type,e=>dragProbe.push({type,target:e.target.tagName,cls:e.target.getAttribute("class"),x:e.clientX,y:e.clientY}),true)')
                for kind,dx,dy,buttons in [('mousePressed',0,0,1),('mouseMoved',-140,-120,1),('mouseReleased',-140,-120,0)]:
                    browser.call('Input.dispatchMouseEvent',type=kind,x=point['x']+dx,y=point['y']+dy,button='left' if kind!='mouseMoved' else 'none',buttons=buttons,clickCount=1)
                moved = browser.evaluate('document.querySelector(".companion-dock").getBoundingClientRect().x')
                assert moved < point['x']-100,(point,moved,browser.evaluate('JSON.stringify(dragProbe)'),browser.errors)
                browser.reload();browser.wait('!!document.querySelector(".companion-dock")')
                assert abs(browser.evaluate('document.querySelector(".companion-dock").getBoundingClientRect().x')-moved) < 2
                for theme in ('dark','light'):
                    browser.evaluate('document.documentElement.dataset.theme='+json.dumps(theme))
                    for width in (1440,390):
                        browser.call('Emulation.setDeviceMetricsOverride',width=width,height=900,deviceScaleFactor=1,mobile=False)
                        browser.click('[data-companion-robot]')
                        browser.wait('!document.querySelector("[data-companion-panel]").hidden')
                        assert browser.evaluate('(()=>{const b=document.querySelector(".companion-panel").getBoundingClientRect();return b.left>=0&&b.right<=innerWidth&&b.top>=0&&b.bottom<=innerHeight;})()')
                        browser.screenshot(out/f'companion-{theme}-{width}.png')
                        browser.click('[data-companion-close]')
                browser.call('Emulation.setEmulatedMedia',features=[{'name':'prefers-reduced-motion','value':'reduce'}])
                assert browser.evaluate('getComputedStyle(document.querySelector(".companion-body")).animationName') == 'none'
                assert not browser.errors, browser.errors
                (out/'report.json').write_text(json.dumps({'status':'passed','paidModelCalls':0,'checks':['idle-wave-thinking-done','inline-answer-no-navigation','stop-no-retry','escaped-input','course-scoped-history','today-task-navigation','minimize-persistence','pointer-drag-persistence','desktop-mobile-light-dark','reduced-motion']},ensure_ascii=False,indent=2),encoding='utf-8')
                print('Study companion browser checks passed; zero paid model calls.')
            finally:
                browser.close()
        finally:
            server.should_exit=True;worker.join(10);sock.close()


if __name__=='__main__': main()
