"""Actual new 200-question curriculum in Chrome; isolated course fixture, no model calls."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
from types import SimpleNamespace

import uvicorn
from playwright.sync_api import sync_playwright, expect
from backend.agent.data_structure_bank import PACKAGE_FILE, TEXTBOOK_HASH
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.curated_practice import CuratedPractice

OUTPUT = Path('test-results/curated-data-structures')
CHROME = os.environ.get('CHROME_PATH', 'C:/Users/571/AppData/Local/Google/Chrome/Application/chrome.exe')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    expect.set_options(timeout=15000)
    package = json.loads(PACKAGE_FILE.read_text(encoding='utf-8'))
    by_id = {q['id']:q for q in package['questions']}
    errors, checks = [], []
    with tempfile.TemporaryDirectory(prefix='curated-ds-', ignore_cleanup_errors=True) as directory:
        app = create_app(Config(data_dir=Path(directory), api_key=''), start_jobs=False)
        sock = socket.socket()
        sock.bind(('127.0.0.1',0))
        base = 'http://127.0.0.1:'+str(sock.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(app,log_level='error'))
        thread = threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
        thread.start()
        while not server.started:
            time.sleep(.03)
        try:
            p = app.state.platform
            scope = p.scope('course-default')
            p.repo.put(scope,'document','textbook-fixture',{'id':'textbook-fixture','name':'数据结构教材.pdf',
                'kind':'pdf','fileHash':TEXTBOOK_HASH,'contentRevision':2,'archived':False,'status':'已解析','chunks':[]})
            sources = [{'id':'fixture-'+str(i),'quote':q['evidenceQuote'],'page':q['references'][0]['page'],
                        'location':'第 '+str(q['references'][0]['page'])+' 页'} for i,q in enumerate(package['questions'])]
            CuratedPractice(p,SimpleNamespace(sources=lambda *args,**kwargs:sources)).install(scope,package)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=CHROME,headless=True)
                context = browser.new_context(viewport={'width':1440,'height':1050},service_workers='block')
                context.add_init_script("""if(!localStorage.getItem('curated-fixture-ready')){localStorage.setItem('xueya-practice-v1:curriculum',JSON.stringify({filters:{hot100:{tag:'已淘汰的旧知识点',status:'pending'},basic:{status:'pending'}}}));localStorage.setItem('curated-fixture-ready','1');}""")
                context.request.post(base+'/api/account/register',data={'username':'curriculum','password':'Curriculum123','confirmPassword':'Curriculum123'})
                page = context.new_page()
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/#space/practice/hot100')
                page.evaluate("window.XueyaPreferences.applyTheme('dark')")
                expect(page.locator('.practice-row')).to_have_count(100)
                expect(page.locator('.practice-units button')).to_have_count(11)
                expect(page.locator('.practice-topic')).to_have_count(10)
                assert page.get_by_role('tab',name='面试题').count()==0
                page.screenshot(path=str(OUTPUT/'hot100-dark.png'))
                checks.append('real Hot100, ten ordered units, four question types and no interview tab')

                def choose(value):
                    field = page.locator('select[data-filter=type]')
                    label = field.locator(f'option[value="{value}"]').inner_text()
                    field.locator('..').get_by_role('combobox').click()
                    page.locator('.practice-select-menu').get_by_role('option',name=label,exact=True).click()

                def unit(name):
                    page.locator(f'.practice-units [data-unit="{name}"]').click()

                unit('图')
                expect(page.locator('.practice-row')).to_have_count(10)
                choose('multiple')
                expect(page.locator('.practice-row')).to_have_count(2)
                selected = page.locator('.practice-row.is-active').get_attribute('data-id')
                q = by_id[selected]
                for i in q['answer']:
                    page.locator(f'[data-action=pick][data-index="{i}"]').click()
                page.locator('[data-action=submit-single]').click()
                expect(page.locator('.practice-result')).to_contain_text('回答正确')
                page.locator('.practice-evidence summary').click()
                expect(page.locator('.practice-evidence')).to_contain_text('新编练习')
                assert page.locator('.practice-evidence blockquote').inner_text()
                checks.append('unit + subtype filter, actual multi-choice grading and textbook background')
                choose('code')
                expect(page.locator('.practice-row')).to_have_count(2)
                assert page.locator('a',has_text='在力扣打开').get_attribute('href').startswith('https://leetcode.cn/problems/')
                checks.append('selected classic questions retain original problem links')
                page.locator('[data-action=category][data-category=basic]').click()
                expect(page.locator('.practice-row')).to_have_count(100)
                unit('串与数组')
                choose('fill')
                expect(page.locator('.practice-row')).to_have_count(2)
                q = by_id[page.locator('.practice-row.is-active').get_attribute('data-id')]
                page.locator('[data-fill]').fill(q['answer'])
                page.locator('[data-action=submit-fill]').click()
                expect(page.locator('.practice-result')).to_contain_text('回答正确')
                checks.append('basic100 uses its own curriculum and fill-in accepted answers')
                unit('排序')
                choose('code')
                expect(page.locator('.practice-row')).to_have_count(1)
                page.locator('[data-action=reveal]').click()
                page.locator('[data-action=language][data-language=c]').click()
                expect(page.locator('.practice-code')).to_contain_text('void insertion_sort')
                page.screenshot(path=str(OUTPUT/'basic-c-dark.png'),full_page=True)
                checks.append('basic C reference code and complexity render correctly')
                choose('')
                unit('')
                expect(page.locator('.practice-row')).to_have_count(100)
                page.set_viewport_size({'width':390,'height':844})
                page.evaluate("window.XueyaPreferences.applyTheme('light')")
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(OUTPUT/'units-mobile-light.png'))
                page.reload()
                expect(page.locator('.practice-row')).to_have_count(100)
                expect(page.locator('.practice-units button')).to_have_count(11)
                checks.append('mobile wrapping, light theme and reload keep the installed curriculum')
                assert not errors,errors
                report={'status':'passed','checks':checks,'pageErrors':errors,'questions':200,'paidApiCalls':0,
                        'fixture':'actual authored/selected question package with isolated textbook source bindings'}
                (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(report,ensure_ascii=False))
                browser.close()
        finally:
            server.should_exit=True
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
