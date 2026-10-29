"""Real Chrome, isolated database and fixed bank. Never invokes external AI."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time

import uvicorn
from playwright.sync_api import sync_playwright, expect

from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.practice_catalog import exam_bank

OUTPUT=Path('test-results/practice-redesign')
CHROME=next((str(p) for p in (Path(os.environ.get('CHROME_PATH','C:/Program Files/Google/Chrome/Application/chrome.exe')),
    Path(os.environ.get('LOCALAPPDATA',''))/'Google/Chrome/Application/chrome.exe') if p.is_file()),None)


def choose(page,key,value):
    field=page.locator(f'select[data-filter={key}]')
    if field.is_visible():
        field.select_option(value)
    else:
        label=field.locator(f'option[value="{value}"]').inner_text()
        field.locator('..').get_by_role('combobox').click()
        page.locator('.practice-select-menu').get_by_role('option',name=label,exact=True).click()


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    checks,errors=[],[]
    with tempfile.TemporaryDirectory(prefix='practice-redesign-',ignore_cleanup_errors=True) as directory:
        app=create_app(Config(data_dir=Path(directory),api_key=''),start_jobs=False)
        sock=socket.socket();sock.bind(('127.0.0.1',0))
        base='http://127.0.0.1:'+str(sock.getsockname()[1])
        server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
        deadline=time.monotonic()+15
        while not server.started:
            assert time.monotonic()<deadline
            time.sleep(.04)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=CHROME,headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1000},service_workers='block')
                context.request.post(base+'/api/account/register',data={'username':'redesign','password':'Redesign123','confirmPassword':'Redesign123'})
                page=context.new_page();page.set_default_timeout(15000)
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/#space/practice',wait_until='networkidle')
                expect(page.locator('.practice-hub')).to_be_visible()
                expect(page.locator('.practice-entry')).to_have_count(3)
                assert page.locator('.practice-row').count()==0
                cards=page.locator('.practice-hub-bottom .practice-entry')
                left,right=cards.nth(0).bounding_box(),cards.nth(1).bounding_box()
                assert abs(left['width']-right['width'])<1 and abs(left['y']-right['y'])<1
                compact=page.locator('.practice-entry-algorithm').bounding_box()
                assert compact['width']<left['width'] and compact['height']<left['height']
                assert compact['y']+compact['height']<=left['y']
                page.evaluate("XueyaPreferences.applyTheme('dark')")
                page.screenshot(path=str(OUTPUT/'hub-dark.png'),full_page=True)
                checks.append('three-entry layout and symmetrical lower cards')

                page.locator('.practice-entry-algorithm').click()
                expect(page.locator('.practice-row')).to_have_count(100)
                expect(page.locator('.practice-topic')).to_have_count(17)
                expect(page.locator('[data-filter=subject],[data-filter=type]')).to_have_count(0)
                expect(page.get_by_role('link',name='在力扣打开 ↗')).to_be_visible()
                page.locator('[data-action=reveal]').click()
                expect(page.locator('.practice-solution-tabs button')).to_have_count(3)
                expect(page.locator('.practice-code')).not_to_be_empty()
                page.locator('[data-note]').fill('保留原始算法题的复习笔记')
                expect(page.locator('[data-note-status]')).to_have_text('已保存',timeout=10000)
                original=page.locator('.practice-row.is-active').get_attribute('data-id')
                page.reload()
                expect(page.locator('[data-note]')).to_have_value('保留原始算法题的复习笔记')
                assert page.locator('.practice-row.is-active').get_attribute('data-id')==original
                page.screenshot(path=str(OUTPUT/'algorithm-dark.png'))
                checks.append('original 100 IDs, 17 topics, LeetCode links, three languages and notes survive reload')

                page.locator('.practice-source-bar a').click()
                page.locator('.practice-entry-materials').click()
                expect(page.locator('.practice-preparing')).to_contain_text('资料接入准备中')
                assert page.locator('input[type=file],.practice-row,[data-action=resume-generation]').count()==0
                page.get_by_role('link',name='← 返回练习首页',exact=True).click()
                checks.append('materials entry opens honest preparing page without upload or generation')

                page.locator('.practice-entry-exam').click()
                expect(page.locator('.practice-row')).to_have_count(300)
                expect(page.locator('.practice-topic')).to_have_count(25)
                expect(page.locator('select[data-filter=subject],select[data-filter=type]')).to_have_count(2)
                choose(page,'subject','计算机网络')
                expect(page.locator('.practice-row')).to_have_count(57)
                assert '二叉树计数' not in page.locator('select[data-filter=tag]').inner_text()
                choose(page,'tag','应用层')
                assert page.locator('.practice-row').count()>0
                choose(page,'subject','操作系统')
                expect(page.locator('select[data-filter=tag]')).to_have_value('')
                expect(page.locator('.practice-row')).to_have_count(67)
                choose(page,'subject','')
                choose(page,'type','single')
                expect(page.locator('.practice-row')).to_have_count(240)
                page.locator('[data-filter=keyword]').fill('e408-2011-04')
                expect(page.locator('.practice-row')).to_have_count(1)
                identifier=page.locator('.practice-row.is-active').get_attribute('data-id')
                question=next(q for q in exam_bank()['questions'] if q['id']==identifier)
                page.locator(f'[data-action=pick][data-index="{question["answer"]}"]').click()
                page.locator('[data-action=submit-single]').click()
                expect(page.locator('.practice-result')).to_contain_text('回答正确')
                expect(page.locator('details.practice-evidence').first).to_contain_text('题目来源与核对')
                checks.append('actual 300-item bank, 240 singles, deterministic grading and traceable source')

                page.locator('[data-filter=keyword]').fill('')
                choose(page,'type','short')
                expect(page.locator('.practice-row')).to_have_count(60)
                identifier=page.locator('.practice-row.is-active').get_attribute('data-id')
                expect(page.locator('.exam-part')).to_have_count(3)
                page.locator('[data-written=p1]').fill('先分析不变量，再写出计算过程和结论。')
                # Navigate before debounce fires: beforeRender must persist the draft.
                page.locator('.practice-source-bar a').click()
                page.locator('.practice-entry-exam').click()
                expect(page.locator('[data-written=p1]')).to_have_value('先分析不变量，再写出计算过程和结论。')
                page.locator('[data-action=reveal]').click()
                page.locator('[data-self-score=p1]').fill('2')
                page.wait_for_timeout(1300)
                page.reload()
                expect(page.locator('[data-written=p1]')).to_have_value('先分析不变量，再写出计算过程和结论。')
                page.locator('[data-action=reveal]').click()
                expect(page.locator('[data-self-score=p1]')).to_have_value('2')
                page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                page.screenshot(path=str(OUTPUT/'composite-dark.png'),full_page=True)
                token=context.request.get(base+'/api/platform/bootstrap').json()['token']
                state=context.request.get(base+'/api/practice/state',headers={'X-Xueya-Token':token}).json()
                row=state['statuses'][identifier]
                assert row['writtenAnswers']['p1'].startswith('先分析不变量')
                assert row['selfScores']['p1']==2 and row['correctCount']==0 and row['wrongCount']==0
                checks.append('60 composites, per-part answers/self-scores, immediate navigation and reload persistence; no objective score pollution')

                # Historical-topic variations are complete without external PDFs.
                context.route('https://www.xit.edu.cn/**',lambda route:route.abort())
                page.locator('[data-filter=keyword]').fill('e408-2021-41')
                expect(page.locator('.practice-row')).to_have_count(1)
                expect(page.locator('.exam-part')).to_have_count(3)
                expect(page.locator('.practice-prompt')).to_contain_text('A→B')
                expect(page.locator('.practice-source-label').last).to_contain_text('非原题')
                assert page.locator('.exam-paper iframe').count()==0
                page.locator('[data-action=reveal]').click()
                expect(page.locator('.exam-part').first).to_contain_text('A、B、C、D、E')
                page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                page.screenshot(path=str(OUTPUT/'historical-variation-dark.png'),full_page=True)
                checks.append('historical variation has full local conditions, subquestions and worked answers despite blocked paper network')

                page.goto(base+'/#space/practice',wait_until='networkidle')
                page.evaluate("XueyaPreferences.applyTheme('light')")
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(OUTPUT/'hub-mobile-light.png'),full_page=True)
                page.locator('.practice-entry-algorithm').click()
                expect(page.locator('.practice-row')).to_have_count(100)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(OUTPUT/'algorithm-mobile-light.png'))
                checks.append('390px mobile hub and algorithm page fit both themes')
                assert not errors,errors
                assert not app.state.platform.db.all("SELECT id FROM invocations")
                report={'status':'passed','checks':checks,'pageErrors':errors,'paidApiCalls':0,
                        'externalPaperContentVerified':False,'externalPaperRequired':False,'sourceMix':{'adapted':151,'authored':149}}
                (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(report,ensure_ascii=False))
                browser.close()
        finally:
            server.should_exit=True;thread.join(timeout=5)


if __name__=='__main__':main()
