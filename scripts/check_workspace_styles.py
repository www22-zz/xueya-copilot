"""Check local-only workspace rendering, both themes and mobile navigation.

Uses a temporary account/database and blocks every non-local browser request.
Never calls a model or opens the user's browser profile.
"""
import json
import re
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
OUT = ROOT / 'test-results/workspace-styles'


class NoModel:
    async def generate(self, *args, **kwargs):
        raise AssertionError('Rendering must not call an AI service')


CONTRAST = r"""selector => {
 const el=document.querySelector(selector),rgb=s=>(s.match(/[\d.]+/g)||[]).map(Number);
 const over=(f,b)=>{const a=f[3]??1;return [0,1,2].map(i=>f[i]*a+b[i]*(1-a));};
 const lum=c=>c.map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;})
   .reduce((a,x,i)=>a+x*[.2126,.7152,.0722][i],0);
 let bg=[255,255,255],chain=[];for(let p=el;p;p=p.parentElement)chain.unshift(p);
 for(const p of chain)bg=over(rgb(getComputedStyle(p).backgroundColor),bg);
 const style=getComputedStyle(el),fg=over(rgb(style.color),bg),a=lum(fg),b=lum(bg);
 return {selector,color:style.color,background:bg,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
}"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-style-check-') as directory:
        app = create_app(Config(root=ROOT, data_dir=Path(directory), api_key='',
                                auto_import_demo=False, preserve_legacy_data=True), provider=NoModel())
        sock = socket.socket(); sock.bind(('127.0.0.1', 0))
        base = f'http://127.0.0.1:{sock.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=3))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            assert server.started
            reports, errors, external = [], [], []
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=browser_path(), headless=True)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})

                def local_only(route):
                    if route.request.url.startswith(base + '/'):
                        route.continue_()
                    else:
                        external.append(route.request.url)
                        route.abort()

                context.route('**/*', local_only)
                reply = context.request.post(base + '/api/account/register', data={
                    'username': 'stylefixture', 'password': 'Fixture123', 'confirmPassword': 'Fixture123'})
                assert reply.ok
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                for width, height in ((1440, 1000), (1024, 900), (768, 900), (390, 844)):
                    page.set_viewport_size({'width': width, 'height': height})
                    for theme in ('light', 'dark'):
                        for view in ('overview', 'ask'):
                            page.goto(base + '/#space/' + view)
                            expect(page.locator('#spacePage')).to_be_visible()
                            page.wait_for_function('!!window.XueyaPreferences')
                            page.evaluate('(theme)=>window.XueyaPreferences.applyTheme(theme)', theme)
                            expect(page.locator('.stitch-overview-view' if view == 'overview' else '.chat-empty-workbench')).to_be_visible()
                            page.evaluate('document.fonts.ready')
                            page.wait_for_function('''document.getAnimations().filter(a=>
                              a.effect?.getTiming().iterations !== Infinity).every(a=>a.playState!=='running')''')
                            assert page.evaluate('document.fonts.check(\'20px "Material Symbols Outlined"\')')
                            if not page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'):
                                page.screenshot(path=str(OUT / 'overflow.png'), full_page=True)
                                raise AssertionError((width, view, theme, page.evaluate('''[...document.querySelectorAll('body *')].filter(el=>{
                                  const r=el.getBoundingClientRect();return r.width>0 && r.right>innerWidth+1;
                                }).slice(0,18).map(el=>({tag:el.tagName,cls:el.className,right:el.getBoundingClientRect().right}))''')))
                            assert page.locator('.stitch-topbar > div').evaluate('(el)=>getComputedStyle(el).display') == 'flex'
                            selector = '.stitch-overview-view h1' if view == 'overview' else '.chat-empty-headline'
                            contrast = page.evaluate(CONTRAST, selector)
                            heading_contrast = contrast['ratio']
                            assert heading_contrast >= 4.5, contrast
                            surface = page.locator('#spacePage').evaluate('(el)=>getComputedStyle(el).backgroundColor')
                            assert surface == ('rgb(17, 20, 30)' if theme == 'dark' else 'rgb(250, 248, 255)'), surface
                            if view == 'ask':
                                assert page.locator('#chatThread').evaluate('(el)=>el.scrollTop') == 0
                                for selector in ('.suggest-text', '.composer textarea', '.chat-empty-card-head'):
                                    contrast = page.evaluate(CONTRAST, selector)
                                    assert contrast['ratio'] >= 4.5, contrast
                            if width < 1024:
                                page.locator('#stitchSidebarToggle').click()
                                page.wait_for_function('''document.getAnimations().filter(a=>
                                  a.effect?.getTiming().iterations !== Infinity).every(a=>a.playState!=='running')''')
                                expect(page.locator('#stitchSidebar')).to_have_class(re.compile('mobile-open'))
                                page.locator('#stitchSidebarToggle').click()
                                page.wait_for_function('document.querySelector("#stitchSidebar").getBoundingClientRect().right <= 1')
                            else:
                                page.wait_for_function('document.querySelector(".stitch-main-content").getBoundingClientRect().left === 260')
                            path = OUT / f'{theme}-{view}-{width}.png'
                            page.screenshot(path=str(path), full_page=True)
                            reports.append({'theme': theme, 'view': view, 'width': width,
                                            'surface': surface, 'headingContrast': heading_contrast})
                page.locator('button[data-open-settings]').first.click()
                expect(page.locator('#appSettingsDialog')).to_be_visible()
                page.locator('[data-theme-choice=system]').click()
                for system_theme in ('light', 'dark'):
                    page.emulate_media(color_scheme=system_theme)
                    expect(page.locator('html')).to_have_attribute('data-theme', system_theme)
                page.locator('[data-theme-choice=dark]').click()
                page.locator('[data-settings-close]').click()
                page.reload()
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                page.evaluate('navigator.serviceWorker.ready')
                page.wait_for_function('''async()=>{
                  const names=(await caches.keys()).filter(n=>n.startsWith('xueya-public-shell-'));
                  for(const name of names){const cache=await caches.open(name);
                    if(await cache.match('/css/utilities.css') && await cache.match('/assets/material-symbols-outlined.woff2'))return true;}
                  return false;
                }''')
                assert not external, external
                assert not errors, errors
                browser.close()
            result = {'checks': reports, 'externalRequests': external, 'runtimeErrors': errors, 'paidApiCalls': 0}
            (OUT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False))
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
