"""Browser regression for instant shelf return and background freshness; no API/model calls."""
import functools
import json
import threading
from http.server import ThreadingHTTPServer

from playwright.sync_api import sync_playwright, expect

from scripts.browser_runtime import browser_path
from scripts.check_plan_day_browser import QuietHandler, ROOT


def graph(subject='数据结构', title='线性表'):
    return dict(ok=True, documents=[dict(id='doc', name='linear.md', title=title,
        subject=subject, ready=True, revision=1)],
        nodes=[dict(id='node', kind='concept', label=title, questionIds=[],
            descriptions=['课程正文'], references=[dict(documentId='doc')])],
        edges=[dict(source='doc', target='node')], blocked=[], available=False,
        coverage=dict(pendingJobs=0, completedRanges=0, totalRanges=1, questions=0,
            unreadyDocuments=0, inputComplete=False, remainingCalls=1, outlineNodes=1))


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT/'frontend')))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/'
    html = '''<!doctype html><html data-theme="dark"><head><meta charset="utf-8">
      <link rel="stylesheet" href="css/stitch-theme.css"></head><body>
      <main id="surface"></main><script src="js/ui/rich-content.js"></script>
      <script src="js/course-graph.js"></script><script src="js/material-learning.js"></script>
      </body></html>'''
    setup = r'''window.owner='alice'; window.XueyaDataKey=key=>key+':'+window.owner;
      window.fixture=FIXTURE; window.calls=0; window.holdGraph=false; window.waiters=[];
      window.attendanceWaiters=[]; window.holdAttendance=true; window.failGraph=false;
      window.XueyaPlatform={spaceFetch:async (path,options={})=>{
        if(path.includes('course-graph')){
          window.calls++; const value=structuredClone(window.fixture), fail=window.failGraph;
          if(window.holdGraph) await new Promise(resolve=>window.waiters.push(resolve));
          if(fail) throw Error('模拟离线');
          return {ok:true,json:async()=>value};
        }
        if(path.endsWith('/attendance')){
          if(options.method==='POST')return {ok:true,json:async()=>({signed:true})};
          if(window.holdAttendance) await new Promise(resolve=>window.attendanceWaiters.push(resolve));
          return {ok:true,json:async()=>({signed:false})};
        }
        return {ok:true,json:async()=>({materials:[],courses:[],available:false})};
      }};
      window.enter=()=>{window.XueyaMaterialLearning.unmount();
        document.querySelector('#surface').innerHTML='<div id="material"></div>';
        void window.XueyaMaterialLearning.mount(document.querySelector('#material'),'course-default');};
      window.release=()=>{window.holdGraph=false;window.waiters.splice(0).forEach(resolve=>resolve());};
    '''.replace('FIXTURE', json.dumps(graph(), ensure_ascii=False))
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=browser_path())
            try:
                page = browser.new_page(viewport=dict(width=1440, height=1000), reduced_motion='reduce')
                page.clock.install()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.add_init_script(setup)
                page.route('**/shelf-preview', lambda route: route.fulfill(content_type='text/html; charset=utf-8', body=html))
                page.goto(base+'shelf-preview#space/materials/corpus')
                page.evaluate('enter()')
                expect(page.locator('.cg-book')).to_have_count(1)
                assert page.evaluate('attendanceWaiters.length') == 1
                expect(page.locator('[data-attendance]')).to_have_text('正在读取签到…')
                page.evaluate('holdAttendance=false;attendanceWaiters.splice(0).forEach(resolve=>resolve())')
                expect(page.locator('[data-attendance]')).to_have_text('每日签到')
                # Entering with a deliberately stalled graph response paints synchronously.
                result = page.evaluate('''()=>{window.holdGraph=true;enter();
                    return {books:document.querySelectorAll('.cg-book').length,
                        loading:document.querySelector('#material').textContent.includes('正在读取课程书架')};}''')
                assert result == dict(books=1, loading=False), result
                calls = page.evaluate('calls')
                page.evaluate('enter();enter()')
                assert page.evaluate('calls') == calls, 'Remounts must share the pending read'
                page.evaluate('release()')
                # A late GET cannot overwrite a successful sign-in or remount the map.
                page.evaluate('holdAttendance=true;enter()')
                page.locator('[data-attendance]').click()
                expect(page.locator('[data-attendance]')).to_have_text('今日已签到')
                page.evaluate('holdAttendance=false;attendanceWaiters.splice(0).forEach(resolve=>resolve())')
                expect(page.locator('[data-attendance]')).to_have_text('今日已签到')
                page.locator('.cg-book').click()
                expect(page.locator('.cg-reader')).to_be_visible()
                result = page.evaluate('''()=>{window.holdGraph=true;enter();
                    return !!document.querySelector('.cg-reader');}''')
                assert result, 'Map and selected subject must survive returning'
                page.evaluate('release()')
                # A changed revision/title refreshes the selected map without blanking it.
                page.wait_for_function('waiters.length===0')
                page.evaluate("fixture.documents[0].revision=2;fixture.documents[0].title='更新后的章节';window.dispatchEvent(new Event('xueya:materials-changed'))")
                expect(page.locator('.cg-reader-heading h2')).to_have_text('更新后的章节')
                # Periodic checks discover changes made outside this page.
                page.evaluate("fixture.documents[0].title='其他窗口的修订'")
                page.clock.fast_forward(15010)
                expect(page.locator('.cg-reader-heading h2')).to_have_text('其他窗口的修订')
                page.evaluate("failGraph=true;window.dispatchEvent(new Event('focus'))")
                expect(page.locator('[data-cg-load-status]')).to_contain_text('当前内容已保留')
                expect(page.locator('.cg-reader-heading h2')).to_have_text('其他窗口的修订')
                # Deletion replaces the cached book; it cannot stay visible indefinitely.
                page.evaluate("failGraph=false;fixture.documents=[];fixture.nodes=[];fixture.edges=[];window.dispatchEvent(new Event('focus'))")
                expect(page.locator('.cg-empty')).to_be_visible()
                # A different account must never render the previous account's cache.
                page.evaluate("owner='bob';holdGraph=true;enter()")
                expect(page.locator('.cg-book,.cg-reader')).to_have_count(0)
                expect(page.locator('#material')).to_contain_text('正在读取课程书架')
                page.evaluate('release()')
                expect(page.locator('.cg-empty')).to_be_visible()
                assert not errors, errors
                output = ROOT/'test-results/course-shelf'
                output.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(output/'empty-after-delete.png'))
                print('PASS: attendance isolation, synchronous warm return, shared requests, map selection, revisions, periodic refresh, offline retention, deletion, account isolation; zero model calls')
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


if __name__ == '__main__':
    main()
