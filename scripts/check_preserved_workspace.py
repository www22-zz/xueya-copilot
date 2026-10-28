"""Compare preserved pages with a Git baseline in Chrome; all API responses are fixtures."""
import argparse
import base64
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import subprocess
import threading
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright, expect

from backend.xueya.practice_bank import bank


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'test-results/preserved-workspace'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', default='9d9b4e5')
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    messages = [dict(id='u', role='user', text='解释队列'),
                dict(id='a', role='ai', text='队列是先进先出的线性表。\n\n从队尾加入，从队首离开。', engine='受控回答', sources=[])]
    fixtures = {'version': 3, 'activeId': 'course-default', 'courses': [
        dict(id='course-default', name='数据结构', archived=False, data=dict(documents=[], sessionId='one',
             sessions=[dict(id='one', title='解释队列', messages=messages, createdAt='2026-10-28T00:00:00Z')]))]}
    catalog = dict(ok=True, documents=[], summary=dict(documents=0, sources=0, processing=0, needsReview=0), capabilities={})
    errors, captures, checks, files, pixel_deltas = [], {}, [], {}, {}

    def respond(route):
        path = urlparse(route.request.url).path
        value = {'ok': True}
        if path.endswith('/account/status'):
            value.update(configured=False, authenticated=True, username='local')
        elif path.endswith('/platform/bootstrap'):
            value.update(token='controlled', schemaVersion='1.0', workspace=None, courses=[
                {'id': 'course-default', 'name': '数据结构', 'archived': False}], jobs=[], resources={})
        elif path.endswith('/knowledge/bases'):
            value['bases'] = [{'id': 'course-default', 'name': '数据结构'}]
        elif path.endswith('/knowledge/catalog'):
            value = catalog
        elif path.endswith('/practice/bank'):
            value.update(bank())
        elif path.endswith('/practice/state'):
            value.update(serverSeq=0, statuses={}, notes={})
        elif path.endswith('/practice/analysis'):
            value.update(available=True, reports=[], jobs=[])
        elif path.endswith('/documents'):
            value['documents'] = []
        elif path.endswith('/library/catalog'):
            value.update(documents=[], media=[], links=[], profile={})
        route.fulfill(status=200, content_type='application/json', body=json.dumps(value, ensure_ascii=False))

    def baseline_asset(route):
        path = unquote(urlparse(route.request.url).path).lstrip('/')
        if path not in files:
            files[path] = subprocess.check_output(['git', 'show', args.baseline + ':' + path], cwd=ROOT)
        mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if path.endswith('.js'):
            mime = 'text/javascript'
        route.fulfill(status=200, content_type=mime, body=files[path])

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe')
            for version in ('baseline', 'integrated'):
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, service_workers='block')
                context.add_init_script("if(!localStorage.getItem('xueya-copilot-workspace-v3'))localStorage.setItem('xueya-copilot-workspace-v3'," + json.dumps(json.dumps(fixtures, ensure_ascii=False)) + ');')
                if version == 'baseline':
                    context.route('**/frontend/**', baseline_asset)
                    context.route('**/shared/**', baseline_asset)
                context.route('**/api/**', respond)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                for width, height in ((1440, 1000), (390, 844)):
                    page.set_viewport_size({'width': width, 'height': height})
                    for theme in ('light', 'dark'):
                        for view in ('overview', 'ask'):
                            page.goto(base + '/frontend/index.html#space/' + view)
                            expect(page.locator('.study-title' if view == 'overview' else '.ai-message')).to_be_visible()
                            page.evaluate("theme=>{localStorage.setItem('xueya-theme',theme);document.documentElement.dataset.theme=theme;}", theme)
                            page.evaluate('document.fonts.ready')
                            page.mouse.move(0, 0)
                            page.locator('#chatInput').focus()
                            page.wait_for_timeout(500)
                            key = f'{view}-{theme}-{width}'
                            shot = page.screenshot(path=str(OUTPUT / f'{version}-{key}.png'), animations='disabled',
                                                   style='.cursor-ring,.cursor-dot{visibility:hidden!important}')
                            metrics = page.evaluate("""() => {
                              const selectors=['.study-title','.title-lens','.daily-checkin-btn','.session-panel','.chat-thread','.composer','.user-message .message-body','.ai-message .rich-content','.cursor-ring'];
                              return Object.fromEntries(selectors.map(s=>{const el=document.querySelector(s);if(!el)return [s,null];const c=getComputedStyle(el),r=el.getBoundingClientRect();return [s,{x:r.x,y:r.y,width:r.width,height:r.height,font:c.fontSize,line:c.lineHeight,padding:c.padding,border:c.borderRadius,background:c.backgroundColor,display:c.display}]}));
                            }""")
                            # Cursor position depends on the timing of mouse events, not page layout.
                            metrics['.cursor-ring'].update(x=0, y=0)
                            if version == 'baseline':
                                captures[key] = (shot, metrics)
                            else:
                                assert metrics == captures[key][1], (key, metrics, captures[key][1])
                                delta = page.evaluate("""async images => {
                                  const pixels=await Promise.all(images.map(async data=>{
                                    const bitmap=await createImageBitmap(await (await fetch('data:image/png;base64,'+data)).blob());
                                    const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;
                                    const ctx=canvas.getContext('2d');ctx.drawImage(bitmap,0,0);return ctx.getImageData(0,0,canvas.width,canvas.height).data;
                                  }));
                                  let max=0,changed=0;for(let i=0;i<pixels[0].length;i+=4){let difference=0;for(let c=0;c<3;c++)difference=Math.max(difference,Math.abs(pixels[0][i+c]-pixels[1][i+c]));max=Math.max(max,difference);if(difference>2)changed++;}return {max,changed};
                                }""", [base64.b64encode(data).decode() for data in (captures[key][0], shot)])
                                pixel_deltas[key] = delta
                                # Allow only a few antialiased edge pixels; geometry must match exactly above.
                                assert delta['max'] <= 8 and delta['changed'] <= 10, f'visual difference: {key}, {delta}'
                                checks.append(key + '-matches-baseline')
                                assert page.locator('[data-session-action]').count() == 0
                                assert page.locator('#composerUploadHint').count() == 0
                            if view == 'ask' and width == 390:
                                page.locator('[data-history-open]').click()
                                expect(page.locator('#chatHistoryPanel')).to_be_visible()
                                page.locator('#chatHistoryPanel [data-history-close]').click()
                if version == 'integrated':
                    page.set_viewport_size({'width': 1440, 'height': 1000})
                    page.goto(base + '/frontend/index.html#space/analysis')
                    expect(page.locator('.practice-select-trigger')).not_to_have_count(0)
                    assert not page.locator('html').evaluate("el=>el.classList.contains('workspace-original')")
                    page.locator('[data-view=overview]').click()
                    expect(page.locator('.study-title')).to_be_visible()
                    assert page.locator('html').evaluate("el=>el.classList.contains('workspace-original')")
                    assert page.locator('.practice-select-trigger').count() == 0
                    assert page.locator('.cursor-ring').evaluate('el=>el.parentElement===document.body')
                    expect(page.locator('.title-lens')).not_to_have_css('display', 'none')
                    gap = page.evaluate("""()=>{
                      for(const x of [300,700])document.body.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerType:'mouse',clientX:x,clientY:150}));
                      const r=new DOMMatrix(getComputedStyle(document.querySelector('.cursor-ring')).transform);
                      const d=new DOMMatrix(getComputedStyle(document.querySelector('.cursor-dot')).transform);
                      return Math.hypot(r.e-d.e,r.f-d.f);
                    }""")
                    assert 1 < gap <= 10.1, 'preserved spring pointer must retain its bounded trailing motion'
                    page.locator('[data-view=ask]').click()
                    expect(page.locator('[data-toggle-web-search]')).to_be_visible()
                    page.locator('[data-toggle-web-search]').click()
                    expect(page.locator('[data-toggle-web-search]')).to_have_attribute('aria-pressed', 'true')
                    page.locator('[data-view=analysis]').click()
                    expect(page.locator('.practice-select-trigger')).not_to_have_count(0)
                    assert page.locator('.cursor-ring').evaluate("el=>el.parentElement.classList.contains('cursor-layer')")
                    checks.append('route-switch-restores-original-title-pointer-selects-and-keeps-MCP-toggle')
                context.close()
            browser.close()
        assert not errors, errors
        result = dict(status='passed', baseline=args.baseline, checks=checks, pageErrors=errors,
                      visualMaxChannelDifferences=pixel_deltas, paidApiCalls=0)
        (OUTPUT / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        server.shutdown()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
