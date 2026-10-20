"""Conversation history layout/drag/keyboard/mobile acceptance with no model calls."""
import json
from pathlib import Path
import tempfile

from scripts.check_learning_browser import Browser
from scripts.check_search_browser import server


def main():
    output=Path('test-results/history-layout');output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-history-') as temporary:
        directory=Path(temporary)
        with server(directory) as (base,app):
            browser=Browser(directory)
            try:
                browser.call('Emulation.setDeviceMetricsOverride',width=1440,height=1000,deviceScaleFactor=1,mobile=False)
                browser.call('Page.addScriptToEvaluateOnNewDocument',source='''if(!localStorage.getItem('history-test-seeded')){localStorage.setItem('history-test-seeded','1');const sessions=Array.from({length:45},(_,i)=>({id:'history-'+i,title:'第 '+(i+1)+' 次课程学习对话',messages:[{id:'message-'+i,role:'user',text:'学习问题 '+i}]}));localStorage.setItem('xueya-copilot-state-v2',JSON.stringify({sessionId:'history-0',sessions,messages:sessions[0].messages}));}''')
                browser.call('Page.addScriptToEvaluateOnNewDocument',source='''Object.defineProperty(window,'XueyaWorkspace',{configurable:true,set(api){Object.defineProperty(window,'XueyaWorkspace',{value:api,writable:true,configurable:true});const create=api.createWorkspace;api.createWorkspace=ctx=>{window.historyTestRender=ctx.render;return create(ctx);};}});''')
                browser.call('Page.navigate',url=base+'/#space/chat')
                browser.wait('document.body.classList.contains("history-layout") && document.querySelectorAll(".session-item").length===45')
                rect='(()=>{const r=document.querySelector("#chatHistoryPanel").getBoundingClientRect();return {left:r.left,top:r.top,width:r.width,height:r.height};})()'
                value=browser.evaluate(rect);assert value=={'left':0,'top':0,'width':288,'height':1000},value
                assert browser.evaluate('document.querySelector(".chat-main").getBoundingClientRect().left>document.querySelector("#chatHistoryPanel").getBoundingClientRect().right')
                assert browser.evaluate('document.querySelector(".session-list").scrollHeight>document.querySelector(".session-list").clientHeight')
                assert browser.evaluate('!document.querySelector("#chatHistoryPanel").innerText.match(/定时任务|插件|云盘|API 服务/)')
                browser.screenshot(output/'desktop-default.png')
                point=browser.evaluate('(()=>{const r=document.querySelector("[data-history-resize]").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
                browser.call('Input.dispatchMouseEvent',type='mouseMoved',**point)
                browser.call('Input.dispatchMouseEvent',type='mousePressed',button='left',clickCount=1,**point)
                browser.call('Input.dispatchMouseEvent',type='mouseMoved',button='left',buttons=1,x=point['x']+100,y=point['y'])
                browser.call('Input.dispatchMouseEvent',type='mouseReleased',button='left',clickCount=1,x=point['x']+100,y=point['y'])
                browser.wait('Math.abs(document.querySelector("#chatHistoryPanel").getBoundingClientRect().width-388)<2')
                browser.screenshot(output/'desktop-resized.png')
                browser.reload();browser.wait('Math.abs(document.querySelector("#chatHistoryPanel").getBoundingClientRect().width-388)<2')
                browser.evaluate('document.querySelector("[data-history-resize]").focus()')
                browser.call('Input.dispatchKeyEvent',type='keyDown',key='ArrowRight')
                browser.wait('Math.abs(document.querySelector("#chatHistoryPanel").getBoundingClientRect().width-404)<2')
                browser.evaluate('window.historyTestRender()')
                browser.wait('document.activeElement.matches("[data-history-resize]")')
                browser.call('Input.dispatchKeyEvent',type='keyDown',key='End')
                assert browser.evaluate('document.querySelector("#chatHistoryPanel").getBoundingClientRect().width<=innerWidth*.45+1')
                browser.call('Emulation.setDeviceMetricsOverride',width=900,height=900,deviceScaleFactor=1,mobile=False)
                assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), 'Wide history at a narrow desktop width must not cause horizontal overflow'
                browser.call('Emulation.setDeviceMetricsOverride',width=1440,height=1000,deviceScaleFactor=1,mobile=False)
                browser.call('Input.dispatchKeyEvent',type='keyDown',key='Home')
                assert browser.evaluate('document.querySelector("#chatHistoryPanel").getBoundingClientRect().width===180')
                browser.evaluate('document.querySelector("[data-history-resize]").dispatchEvent(new MouseEvent("dblclick",{bubbles:true}))')
                assert browser.evaluate('localStorage.getItem("xueya-history-width-v1")===null && document.querySelector("#chatHistoryPanel").getBoundingClientRect().width===288')
                browser.fill('#sessionSearch','第 12 次')
                browser.wait('document.querySelectorAll(".session-item").length===1')
                browser.click('[data-session="history-11"]')
                browser.wait('document.querySelector("#chatThread").innerText.includes("学习问题 11")')
                browser.fill('#sessionSearch','')
                browser.evaluate('location.hash="space/library"')
                browser.wait('!document.body.classList.contains("history-layout") && !!document.querySelector("#libraryRows")')
                assert browser.evaluate('getComputedStyle(document.querySelector(".site-header")).marginLeft==="0px"')
                browser.evaluate('location.hash="space/chat"')
                browser.wait('document.body.classList.contains("history-layout")')
                browser.evaluate('window.XueyaPreferences.applyTheme("dark")')
                browser.screenshot(output/'desktop-dark.png')
                browser.call('Emulation.setDeviceMetricsOverride',width=390,height=844,deviceScaleFactor=1,mobile=True)
                assert browser.evaluate('!document.querySelector("#chatHistoryPanel").checkVisibility() && document.documentElement.scrollWidth<=innerWidth+1')
                browser.click('[data-history-open]')
                browser.wait('document.body.classList.contains("history-drawer-open")')
                assert browser.evaluate('document.querySelector("#chatHistoryPanel").getBoundingClientRect().height===innerHeight && document.activeElement.matches("[data-history-close]")')
                assert browser.evaluate('(()=>{const close=document.querySelector("#chatHistoryPanel [data-history-close]"),r=close.getBoundingClientRect();return close.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));})()'), 'Drawer close control must stay above the site header'
                browser.screenshot(output/'mobile-dark-drawer.png')
                browser.call('Input.dispatchKeyEvent',type='keyDown',key='Escape')
                browser.wait('!document.body.classList.contains("history-drawer-open")')
                assert browser.evaluate('document.activeElement.matches("[data-history-open]")')
                browser.click('[data-history-open]');browser.click('[data-session="history-1"]')
                browser.wait('!document.body.classList.contains("history-drawer-open") && document.querySelector("#chatThread").innerText.includes("学习问题 1")')
                browser.evaluate('window.XueyaPreferences.applyTheme("light")')
                browser.click('[data-history-open]');browser.screenshot(output/'mobile-light-drawer.png')
                browser.click('.history-backdrop')
                browser.wait('!document.body.classList.contains("history-drawer-open")')
                assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                browser.screenshot(output/'mobile-chat.png')
                assert not browser.errors,browser.errors
                assert not app.state.platform.db.all('SELECT * FROM invocations')
                (output/'report.json').write_text(json.dumps({'passed':True,'paidApiCalls':0,'checks':['20-percent-default','full-viewport-height','independent-history-scroll','pointer-drag','remembered-width-after-reload','keyboard-and-bounds','divider-focus-after-chat-rerender','double-click-reset','search-and-switch','other-pages-unaffected','mobile-drawer-Escape-focus','mobile-selection-closes','light-dark-no-overflow']},indent=2),encoding='utf-8')
                print('History browser passed: full-height 20% sidebar, drag/keyboard/persistence, search/switch and mobile light/dark drawer. No API calls.')
            except BaseException:
                browser.screenshot(output/'failure.png');raise
            finally:browser.close()


if __name__=='__main__':main()
