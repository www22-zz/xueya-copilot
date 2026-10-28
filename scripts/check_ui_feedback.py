"""Isolated Chrome checks for the nine UI feedback items. No live data/API calls."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect
from backend.xueya.practice_bank import bank

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'test-results/ui-feedback'
CHROME = next((str(path) for path in (
    Path(os.environ.get('CHROME_PATH','C:/Program Files/Google/Chrome/Application/chrome.exe')),
    Path(os.environ.get('LOCALAPPDATA',''))/'Google/Chrome/Application/chrome.exe',
    Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'),
) if path.is_file()), None)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def settings_button(page):
    return page.locator('button[data-open-settings]:visible,#appSettingsButton:visible').first


def custom_cursor(page, item, *, prove_painted=False):
    item.hover()
    expect(item).to_have_css('cursor','none')
    expect(page.locator('.cursor-dot')).to_have_css('opacity','1')
    assert page.locator('.cursor-layer').evaluate("el=>el.matches(':popover-open')")
    if prove_painted:
        page.evaluate('()=>new Promise(requestAnimationFrame)')
        point=page.locator('.cursor-dot').evaluate('el=>{const m=new DOMMatrix(getComputedStyle(el).transform);return {x:m.e,y:m.f}}')
        clip={'x':max(0,point['x']-16),'y':max(0,point['y']-16),'width':32,'height':32}
        visible=page.screenshot(clip=clip)
        page.locator('.cursor-layer').evaluate("el=>el.style.visibility='hidden'")
        hidden=page.screenshot(clip=clip)
        page.locator('.cursor-layer').evaluate("el=>el.style.visibility=''")
        assert visible!=hidden, 'cursor covered by dialog/menu'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    documents = [dict(id=f'doc-{i}', name=f'课程讲义 {i}.md', kind='md', version=1,
        contentRevision=1, status='已解析，可检索', size=100, sourceCount=1, chunks=[],
        review=dict(pendingPages=[], transcribedPages=[], blankPages=[], supplementedPages=[]), quality={}) for i in (1, 2)]
    catalog = dict(ok=True, documents=documents, summary=dict(documents=2, sources=2, processing=0, needsReview=0), capabilities={})
    messages = [dict(role='user',text='给我出一道有关指针的题目'), dict(role='ai',text='## 指针练习\n\n在 C 语言中，请判断 `x` 的值。\n\n```c\nint x = 3;\nint *p = &x;\n*p = 5;\n```\n\n- 先观察指针指向哪个变量。\n- 再说明赋值如何改变原变量。',engine='MiMo 通用问答',sources=[])]
    fixtures = {'version':3,'activeId':'course-default','courses':[
        dict(id='course-default',name='数据结构',archived=False,data=dict(documents=[],sessionId='chat-1',sessions=[dict(id='chat-1',title='指针练习',messages=messages),dict(id='chat-2',title='另一个对话',messages=[])])),
        dict(id='course-other',name='其他课程',archived=False,data=dict(documents=[],sessions=[]))]}
    checks = []
    errors = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=CHROME)
            context = browser.new_context(viewport={'width':1440,'height':1000},permissions=['clipboard-read','clipboard-write'])
            context.add_init_script('''if(!localStorage.getItem('ui-fixture-ready')){localStorage.setItem('xueya-copilot-workspace-v3', %s);localStorage.setItem('xueya-theme','dark');localStorage.setItem('ui-fixture-ready','1');}''' % json.dumps(json.dumps(fixtures, ensure_ascii=False)))

            def respond(route):
                path = urlparse(route.request.url).path
                value = {'ok':True}
                if path.endswith('/account/status'):
                    value.update(configured=False, authenticated=True, username='local')
                elif path.endswith('/platform/bootstrap'):
                    value.update(token='controlled', schemaVersion='1.0', workspace=None, courses=[{'id':c['id'],'name':c['name'],'archived':False} for c in fixtures['courses']], jobs=[],resources={})
                elif path.endswith('/knowledge/bases'):
                    value['bases']=[{'id':c['id'],'name':c['name']} for c in fixtures['courses']]
                elif path.endswith('/knowledge/catalog'):
                    value=catalog
                elif path.endswith('/practice/bank'):
                    value.update(bank())
                elif path.endswith('/practice/state'):
                    value.update(serverSeq=0,statuses={},notes={})
                elif path.endswith('/practice/analysis'):
                    value.update(available=True,reports=[],jobs=[])
                elif path.endswith('/documents'):
                    value['documents']=documents
                elif path.endswith('/library/catalog'):
                    value.update(documents=documents,media=[],links=[],profile={})
                route.fulfill(status=200, content_type='application/json', body=json.dumps(value,ensure_ascii=False))

            context.route('**/api/**', respond)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base+'/frontend/index.html#space/overview')
            expect(page.locator('.study-title')).to_be_visible()
            expect(page.locator('#documentCount')).to_have_text('0')
            assert page.locator('[data-document-total]').count()==0
            title=page.locator('.study-title').bounding_box()
            for x in (title['x']+2,title['x']+title['width']-2):
                page.mouse.move(x,title['y']+title['height']/2)
                assert page.locator('.title-lens').evaluate('(el)=>getComputedStyle(el).display')!='none'
                assert abs(page.locator('.study-title').bounding_box()['width']-title['width'])<1
            checks.append('preserved title lens hover stays aligned')
            page.locator('[data-add-images]').focus()
            expect(page.locator('[data-add-images]')).to_be_focused()
            assert page.locator('#composerUploadHint').count()==0
            checks.append('preserved upload control remains keyboard accessible')
            page.screenshot(path=str(OUTPUT/'overview-dark.png'),full_page=True)
            for view in ('ask','knowledge','overview','ask'):
                page.goto(base+'/frontend/index.html#space/'+view)
                expect(page.locator('#documentCount')).to_have_text('0' if view in ('ask','overview') else '2')
            checks.append('original page counts and server library counts retain their route behavior')
            assert page.locator('html').evaluate("el=>el.classList.contains('workspace-original')")
            page.locator('.session-item-row').first.hover()
            page.locator('[data-session-menu]').first.click()
            expect(page.locator('.session-dropdown-menu')).to_be_visible()
            panel=page.locator('.session-dropdown-menu').bounding_box()
            assert panel['x']>=0 and panel['y']+panel['height']<=1000
            assert page.locator('.session-item-btn').first.bounding_box()['width']>140
            page.screenshot(path=str(OUTPUT/'chat-menu-dark.png'),full_page=True)
            page.locator('[data-rename-session]').first.click()
            page.locator('#workspaceForm [name=title]').fill('重命名后的对话')
            page.locator('#workspaceForm button[type=submit]').click()
            expect(page.locator('[data-session=chat-1] .session-title')).to_have_text('重命名后的对话')
            page.reload()
            expect(page.locator('[data-session=chat-1] .session-title')).to_have_text('重命名后的对话')
            page.locator('.session-item-row').filter(has=page.locator('[data-session=chat-1]')).hover()
            page.locator('[data-session-menu=chat-1]').click()
            page.locator('[data-pin-session]').first.click()
            assert '重命名' in page.locator('.session-item-row').first.inner_text()
            checks.append('conversation rename/pin survives rerender/reload')
            page.locator('.session-item-row').first.hover()
            page.locator('[data-session-menu]').first.click()
            page.locator('[data-branch-session]').first.click()
            assert page.locator('.session-item-row').count()==3
            page.locator('.session-item-row.active').hover()
            page.locator('.session-item-row.active [data-session-menu]').click()
            page.locator('.session-item-row.active [data-delete-session]').click()
            expect(page.locator('#workspaceDialog')).to_be_visible()
            page.locator('#workspaceForm button[type=submit]').click()
            assert page.locator('.session-item-row').count()==2
            checks.append('conversation fork preserves transcript; delete requires confirmation')
            page.goto(base+'/frontend/index.html#space/knowledge')
            target=settings_button(page)
            target.hover()
            page.wait_for_timeout(250)
            size=page.locator('.cursor-ring').evaluate("el=>{const c=getComputedStyle(el,'::before');return parseFloat(c.width)*new DOMMatrix(c.transform).a}")
            assert size<=30
            page.mouse.down()
            assert page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
            page.mouse.up()
            assert page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
            if page.locator('#appSettingsDialog[open]').count():
                page.locator('#appSettingsDialog [data-settings-close]').click()
            # No pointer movement is needed to restore the cursor after a click.
            target.hover()
            page.mouse.down()
            page.mouse.move(500,450)
            assert not page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
            page.mouse.up()
            assert page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
            page.goto(base+'/frontend/index.html#space/ask')
            page.locator('[data-session=chat-1]').click()
            page.locator('.user-message p').first.hover()
            assert not page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
            checks.append('custom cursor survives click down/up; native cursor during drag and text selection')
            page.goto(base+'/frontend/index.html#space/analysis')
            for theme in ('light','dark'):
                page.evaluate('(theme)=>window.XueyaPreferences.applyTheme(theme)',theme)
                settings_button(page).click()
                settings=page.locator('#appSettingsDialog')
                expect(settings).to_be_visible()
                settings.locator('[data-settings-tab=general]').click()
                for selector in ('h2','[data-settings-tab=account]','[data-theme-choice=light]'):
                    item=settings.locator(selector)
                    custom_cursor(page,item,prove_painted=True)
                page.screenshot(path=str(OUTPUT/f'settings-cursor-{theme}.png'))
                settings.locator('[data-settings-tab=account]').click()
                field=settings.locator('input[name=username]')
                field.hover()
                assert field.evaluate('el=>getComputedStyle(el).cursor')=='text'
                settings.locator('[data-settings-close]').click()
                settings_button(page).hover()
                assert page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
                page.evaluate('void window.XueyaAccount.login()')
                login=page.locator('#accountLoginDialog')
                expect(login).to_be_visible()
                for selector in ('h1','input[name=username]','button[type=submit]','[data-auth-switch]'):
                    item=login.locator(selector)
                    if selector.startswith('input'):
                        item.hover()
                        expect(item).to_have_css('cursor','text')
                    else:
                        custom_cursor(page,item,prove_painted=True)
                    page.mouse.down()
                    assert item.evaluate('el=>getComputedStyle(el).cursor')==('text' if selector.startswith('input') else 'none')
                    page.mouse.up()
                custom_cursor(page,login.locator('h1'),prove_painted=True)
                page.mouse.move(2,2)
                assert page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
                custom_cursor(page,login.locator('h1'))
                page.screenshot(path=str(OUTPUT/f'login-cursor-{theme}.png'))
                page.keyboard.press('Escape')
                expect(login).not_to_be_visible()
                settings_button(page).hover()
                assert page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
                page.goto(base+'/frontend/index.html#space/analysis')
                expect(page.locator('.analysis-status')).to_be_empty()
                for name,value,text in (('category','hot100','Hot 100'),('days','30','最近 30 天')):
                    native=page.locator(f'select[data-analysis-filter={name}]')
                    trigger=native.locator('..').get_by_role('combobox')
                    trigger.click()
                    option=page.locator('.practice-select-menu').get_by_role('option',name=text,exact=True)
                    custom_cursor(page,option,prove_painted=True)
                    page.screenshot(path=str(OUTPUT/f'analysis-menu-{name}-{theme}.png'))
                    page.mouse.down()
                    expect(option).to_have_css('cursor','none')
                    page.mouse.up()
                    expect(native).to_have_value(value)
                    expect(trigger).to_have_text(text)
                    expect(page.locator('.practice-select-menu')).to_have_count(0)
                # Native controls keep their form data and required validation.
                settings_button(page).click()
                settings.locator('[data-settings-tab=services]').click()
                settings.evaluate('''el=>{const form=document.createElement('form');form.id='cursor-select-fixture';form.innerHTML='<label>测试范围<select name="scope" required><option value="">请选择</option><option value="chosen">已选择</option></select></label>';el.querySelector('.settings-content').append(form)}''')
                modal_select=settings.locator('#cursor-select-fixture select')
                modal_trigger=modal_select.locator('..').get_by_role('combobox')
                expect(modal_trigger).to_be_visible()
                assert not settings.locator('#cursor-select-fixture').evaluate('el=>el.reportValidity()')
                modal_trigger.click()
                modal_option=page.locator('.practice-select-menu').get_by_role('option',name='已选择',exact=True)
                custom_cursor(page,modal_option,prove_painted=True)
                modal_option.click()
                form_state=settings.locator('#cursor-select-fixture').evaluate("el=>({valid:el.reportValidity(),value:el.querySelector('select').value,data:new FormData(el).get('scope'),html:el.innerHTML})")
                assert form_state['valid'] and form_state['data']=='chosen',form_state
                modal_trigger.click()
                page.keyboard.press('Escape')
                expect(page.locator('.practice-select-menu')).to_have_count(0)
                expect(settings).to_be_visible()
                page.keyboard.press('Escape')
                expect(settings).not_to_be_visible()
                settings.locator('#cursor-select-fixture').evaluate('el=>el.remove()')
            checks.append('custom cursor paints above login/settings modals on hover and press in both themes; inputs keep caret and close recovers')
            checks.append('analysis category/time selections and modal selects keep custom cursor, update values, restore focus and preserve form validation')
            custom_cursor(page,settings_button(page))
            performance=page.evaluate('''async()=>{
                const target=document.querySelector('#appSettingsButton'),r=target.getBoundingClientRect();
                const writes=[];const observer=new MutationObserver(rows=>writes.push(...rows));
                observer.observe(document.body,{attributes:true,attributeFilter:['class']});
                for(let i=0;i<1000;i++)target.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerType:'mouse',clientX:r.x+10+i%10,clientY:r.y+10}));
                await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);
                observer.disconnect();const ring=new DOMMatrix(getComputedStyle(document.querySelector('.cursor-ring')).transform),dot=new DOMMatrix(getComputedStyle(document.querySelector('.cursor-dot')).transform);
                return {bodyWrites:writes.length,error:Math.hypot(ring.e-(r.x+19),ring.f-(r.y+10)),gap:Math.hypot(ring.e-dot.e,ring.f-dot.f)};
            }''')
            assert performance['bodyWrites']==0,performance
            assert performance['error']<0.1 and performance['gap']<0.1,performance
            page.emulate_media(reduced_motion='reduce')
            settings_button(page).hover()
            assert not page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
            page.emulate_media(reduced_motion='no-preference')
            checks.append('1000 movement events produce no body class rewrites; ring/dot follow the latest point within one frame; reduced motion uses native cursor')
            page.goto(base+'/frontend/index.html#space/knowledge')
            expect(page.locator('#kbBase').locator('..').get_by_role('combobox')).to_be_visible()
            page.locator('#kbNotice').evaluate("el=>el.textContent='会话已变化，请刷新页面'")
            assert page.locator('#kbNotice').evaluate('el=>getComputedStyle(el).color')=='rgb(230, 234, 245)'
            assert page.locator('#kbBase').locator('..').get_by_role('combobox').evaluate('el=>getComputedStyle(el).borderRadius')=='12px'
            page.wait_for_timeout(250)
            page.locator('#kbNotice').evaluate("el=>el.textContent='会话已变化，请刷新页面'")
            page.screenshot(path=str(OUTPUT/'knowledge-dark.png'),full_page=True)
            checks.append('course selector and notices follow dark theme')
            for theme in ('light','dark'):
                page.evaluate('theme=>window.XueyaPreferences.applyTheme(theme)',theme)
                page.goto(base+'/frontend/index.html#space/practice/hot100')
                expect(page.locator('.practice-row')).to_have_count(100)
                expect(page.get_by_text('正在加载题库…', exact=True)).to_have_count(0)
                pane = page.locator('.practice-list-pane')
                assert pane.evaluate('''el=>{
                    const topic=el.querySelector('.practice-topic');
                    el.scrollTop=0;
                    const origin=topic.getBoundingClientRect().top;
                    for(const fraction of [0,.2,.5,.8,1]){
                        el.scrollTop=(el.scrollHeight-el.clientHeight)*fraction;
                        if(Math.abs(topic.getBoundingClientRect().top+el.scrollTop-origin)>1)return false;
                        const rows=[...el.querySelectorAll('.practice-topic,.practice-row')].map(node=>node.getBoundingClientRect());
                        if(rows.some((row,i)=>i&&row.top<rows[i-1].bottom-1))return false;
                    }
                    el.scrollTop=650;
                    return true;
                }''')
                page.screenshot(path=str(OUTPUT/f'topic-scroll-{theme}.png'))
                page.goto(base+'/frontend/index.html#space/practice/foundation')
                for name in ('subject','type','tag'):
                    native = page.locator(f'select[data-filter={name}]')
                    selector = native.locator('..').get_by_role('combobox')
                    expect(selector).to_be_visible()
                    selector.hover()
                    selector.focus()
                    assert page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')&&el.classList.contains('cursor-interactive')")
                    assert selector.evaluate("el=>getComputedStyle(el).cursor")=='none'
                    selector.click()
                    menu = page.locator('.practice-select-menu')
                    expect(menu).to_be_visible()
                    option = menu.get_by_role('option').first
                    option.hover()
                    assert page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
                    assert option.evaluate("el=>getComputedStyle(el).cursor")=='none'
                    page.mouse.down()
                    assert page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
                    page.mouse.up()
                    expect(menu).to_have_count(0)
                subject = page.locator('select[data-filter=subject]')
                subject_trigger = subject.locator('..').get_by_role('combobox')
                unfiltered_count = page.locator('.practice-row').count()
                subject_trigger.click()
                choice = page.locator('.practice-select-menu [role=option]').nth(1)
                chosen = choice.inner_text()
                choice.click()
                expect(subject_trigger).to_have_text(chosen)
                assert subject.evaluate('el=>el.selectedIndex')==1
                assert 0 < page.locator('.practice-row').count() < unfiltered_count
                subject_trigger.press('Enter')
                subject_trigger.press('Home')
                subject_trigger.press('Enter')
                expect(subject_trigger).to_have_text('全部科目')
                subject_trigger.click()
                subject_trigger.press('Escape')
                expect(page.locator('.practice-select-menu')).to_have_count(0)
                subject_trigger.click()
                page.locator('[data-filter=keyword]').click()
                expect(page.locator('.practice-select-menu')).to_have_count(0)
                page.set_viewport_size({'width':390,'height':844})
                subject_trigger.click()
                menu = page.locator('.practice-select-menu')
                box = menu.bounding_box()
                assert box['x']>=0 and box['x']+box['width']<=390
                page.screenshot(path=str(OUTPUT/f'filter-menu-{theme}-mobile.png'))
                expect(menu).to_be_visible()
                subject_trigger.press('Escape')
                page.set_viewport_size({'width':1440,'height':1000})
                subject_trigger.click()
                page.locator('.practice-select-menu [role=option]').nth(1).hover()
                page.screenshot(path=str(OUTPUT/f'filter-menu-{theme}-desktop.png'))
                expect(page.locator('.practice-select-menu')).to_be_visible()
                subject_trigger.press('Escape')
                page.locator('[data-filter=keyword]').hover()
                assert not page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
                page.goto(base+'/frontend/index.html#space/knowledge')
                kb_picker=page.locator('#kbBase').locator('..').get_by_role('combobox')
                kb_picker.hover()
                kb_picker.focus()
                assert page.locator('body').evaluate("el=>el.classList.contains('custom-cursor')")
                if not page.locator('#kbFiles').is_visible():
                    page.locator('[data-kb=toggle-upload]').click()
                upload = page.locator('#kbFiles')
                expect(upload).to_be_visible()
                upload.focus()
                colors = upload.evaluate("el=>{const s=getComputedStyle(el,'::file-selector-button');return {text:s.color,background:s.backgroundColor}}")
                def luminance(css_color):
                    channels = [int(c.strip())/255 for c in css_color.removeprefix('rgb(').removesuffix(')').split(',')]
                    linear = [c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4 for c in channels]
                    return sum(c*w for c,w in zip(linear,(0.2126,0.7152,0.0722)))
                light, dark = sorted((luminance(colors['text']),luminance(colors['background'])),reverse=True)
                assert (light+0.05)/(dark+0.05)>=4.5, colors
                for width, height in ((1440,1000),(390,844)):
                    page.set_viewport_size({'width':width,'height':height})
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    upload.evaluate("el=>el.scrollIntoView({block:'center',behavior:'instant'})")
                    upload.screenshot(path=str(OUTPUT/f'upload-{theme}-{width}.png'))
                page.set_viewport_size({'width':1440,'height':1000})
                page.goto(base+'/frontend/index.html#space/ask')
                selection=page.locator('.user-message p').evaluate("el=>({color:getComputedStyle(el,'::selection').color,background:getComputedStyle(el,'::selection').backgroundColor})")
                assert selection['color']!=selection['background']
                page.screenshot(path=str(OUTPUT/f'chat-{theme}.png'),full_page=True)
            checks.append('selected text remains readable in light/dark themes')
            checks.append('rounded topic labels scroll with questions without stacking or overlap in either theme')
            checks.append('in-page filter options retain cursor through actual clicks; filtering, keyboard, dismissal, mobile bounds and both themes pass')
            checks.append('upload file button contrast >=4.5 in light/dark themes; desktop/mobile screenshots')
            page.set_viewport_size({'width':390,'height':844})
            page.goto(base+'/frontend/index.html#space/ask')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.locator('[data-history-open]').click()
            expect(page.locator('#chatHistoryPanel')).to_be_visible()
            page.locator('.session-item-row').first.hover()
            page.locator('[data-session-menu]').first.click()
            expect(page.locator('.session-dropdown-menu')).to_be_visible()
            page.screenshot(path=str(OUTPUT/'chat-mobile.png'),full_page=True)
            checks.append('mobile layout and conversation actions remain usable')
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    report={'status':'passed','checks':checks,'pageErrors':errors,'providerRequests':0}
    (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
