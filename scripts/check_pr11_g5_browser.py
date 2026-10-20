"""Compare visible PR11 surfaces against the integration, using isolated data and no APIs."""
import argparse
from contextlib import contextmanager
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import zipfile

import uvicorn

from backend.xueya.app import create_app
from backend.xueya.config import Config, ROOT
from scripts.check_learning_browser import Browser


@contextmanager
def server(root, directory):
    app = create_app(Config(root=root, data_dir=directory/'data'))
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
            time.sleep(.03)
        assert host.started
        yield f'http://127.0.0.1:{port}'
    finally:
        host.should_exit = True
        thread.join(8)
        sock.close()
        assert not thread.is_alive()


SNAPSHOT = r'''(()=>{
 const rows=[];
 for(const el of document.body.querySelectorAll('*')){
  if(el.closest('script,style,svg,canvas,#toast,[aria-hidden=true]'))continue;
  const r=el.getBoundingClientRect();
  if(!el.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||!r.width||!r.height)continue;
  const text=[...el.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').replace(/\s+/g,' ').trim();
  if(!text)continue;
  const s=getComputedStyle(el);
  rows.push({tag:el.tagName,text,box:[r.x,r.y,r.width,r.height].map(v=>Math.round(v)),color:s.color,background:s.backgroundColor,font:s.fontSize});
 }
 return rows;
})()'''


def stable(browser):
    previous = None
    for _ in range(80):
        current = browser.evaluate(SNAPSHOT)
        if current == previous and not any('正在读取' in x['text'] or '正在连接' in x['text'] for x in current):
            return current
        previous = current
        time.sleep(.15)
    raise AssertionError('Visible surface did not settle')


def capture(root, directory, output, name):
    result = {}
    directory.mkdir()
    with server(root, directory) as base:
        browser = Browser(directory)
        try:
            browser.call('Emulation.setEmulatedMedia', features=[{'name':'prefers-reduced-motion','value':'reduce'}])
            browser.call('Page.addScriptToEvaluateOnNewDocument', source="localStorage.setItem('xueya-theme','light')")
            browser.call('Page.navigate', url=base+'/#space/overview')
            browser.wait('!!document.querySelector("#workspaceMore") && !!window.XueyaPreferences')
            browser.evaluate('document.fonts.ready')
            browser.evaluate("document.head.insertAdjacentHTML('beforeend','<style>*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}</style>')")
            for width in (1440,390):
                browser.call('Emulation.setDeviceMetricsOverride', width=width,height=1000 if width==1440 else 844,deviceScaleFactor=1,mobile=width==390)
                for theme in ('light','dark'):
                    browser.evaluate('window.XueyaPreferences.applyTheme('+json.dumps(theme)+')')
                    for view in ('home','overview','chat','library','cards','practice','memory','chapters','plan','graph'):
                        browser.evaluate('location.hash='+json.dumps('home' if view=='home' else 'space/'+view))
                        if view=='home':
                            browser.wait('!document.querySelector("#homePage").hidden')
                        else:
                            browser.wait('!document.querySelector("#spacePage").hidden && document.title.startsWith('+json.dumps({'overview':'学习概览','chat':'资料问答','library':'课程资料','cards':'知识卡片','practice':'练习与错题','memory':'记忆卡片','chapters':'章节学习','plan':'复习计划','graph':'知识图谱'}[view])+')')
                        key=f'{width}-{theme}-{view}'
                        result[key]=stable(browser)
                        assert browser.evaluate('!document.querySelector(".space-top-right #g5Open") && !document.querySelector("#workspaceMore [data-view=media]")')
                        assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        if view in ('overview','cards','chapters'):
                            browser.screenshot(output/f'{name}-{key}.png')
                    browser.click('#appSettingsButton')
                    result[f'{width}-{theme}-settings']=stable(browser)
                    browser.screenshot(output/f'{name}-{width}-{theme}-settings.png')
                    browser.click('[data-settings-close]')
            assert not browser.errors, browser.errors
        finally:
            browser.close()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',default='6f6c223ac87ba0a903a0ecfbf9357a3dfaa0d48e')
    args=parser.parse_args()
    output=ROOT/'test-results/pr11-g5';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-pr11-g5-') as temporary:
        folder=Path(temporary)
        archive=subprocess.run(['git','archive','--format=zip',args.baseline,'frontend','shared'],cwd=ROOT,check=True,capture_output=True).stdout
        baseline=folder/'baseline';baseline.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            z.extractall(baseline)
        before=capture(baseline,folder/'before',output,'pr11')
        after=capture(ROOT,folder/'after',output,'integrated')
        changes={k:{'before':before[k],'after':after[k]} for k in before if before[k]!=after[k]}
        (output/'report.json').write_text(json.dumps({'passed':not changes,'baseline':args.baseline,'surfaces':len(before),'paidApiCalls':0,'changes':changes},ensure_ascii=False,indent=2),encoding='utf-8')
        assert not changes, 'PR11 visible differences: '+', '.join(changes)
        print(f'PR11 visible text/layout/style unchanged across {len(before)} desktop/mobile light/dark surfaces. No paid APIs.')


if __name__=='__main__':main()
