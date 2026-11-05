"""Real Edge upload-to-graph-to-quiz check against isolated controlled services."""
import json
from pathlib import Path
import runpy
import socket
import tempfile
import threading
import time
import uvicorn
from playwright.sync_api import sync_playwright, expect
from backend.xueya.app import create_app
from backend.xueya.config import Config
from .browser_runtime import browser_path

ROOT=Path(__file__).resolve().parents[1]


def main():
    output=ROOT/'test-results/material-browser';output.mkdir(parents=True,exist_ok=True)
    model=runpy.run_path(str(ROOT/'tests/python/test_material_learning.py'))['Model']()
    with tempfile.TemporaryDirectory(prefix='xueya-material-browser-') as directory:
        app=create_app(Config(root=ROOT,data_dir=Path(directory),api_key='controlled',
                             preserve_legacy_data=True,auto_import_demo=False),provider=model)
        sock=socket.socket();sock.bind(('127.0.0.1',0));base=f'http://127.0.0.1:{sock.getsockname()[1]}'
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',timeout_graceful_shutdown=3))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            assert server.started
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=browser_path(),headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1000})
                context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                assert context.request.post(base+'/api/account/register',data={
                    'username':'materialcase','password':'Fixture123','confirmPassword':'Fixture123'}).ok
                token=context.request.get(base+'/api/platform/bootstrap').json()['token']
                assert context.request.post(base+'/api/platform/library/text',headers={'X-Xueya-Token':token},data={
                    'courseId':'course-default','title':'队列讲义','text':'# 队列\n'+('先进先出，队头出队，队尾入队。\n'*60),
                    'idempotencyKey':'browser-upload'}).ok
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/#space/materials')
                page.locator('.materials-list button').filter(has_text='队列讲义').click()
                expect(page.locator('[data-material-practice]')).to_be_visible(timeout=20000)
                assert page.locator('.material-graph svg').bounding_box()['height']>150
                assert page.locator('.learning-center-nav .sidebar-text').all_text_contents()==['课程资料学习','算法学习','408考研学习']
                viewbox=page.locator('.material-graph svg').get_attribute('viewBox')
                page.locator('[data-graph-zoom="0.8"]').click()
                assert page.locator('.material-graph svg').get_attribute('viewBox')!=viewbox
                page.locator('[data-graph-reset]').click()
                assert page.locator('.material-graph svg').get_attribute('viewBox')=='0 0 640 420'
                page.locator('#materialLearning [data-node]').first.click()
                page.locator('[data-material-practice]').click()
                expect(page.locator('[data-quiz-card]')).to_have_count(4)
                forms=page.locator('[data-quiz-answer]')
                expect(forms).to_have_count(4)
                forms.nth(0).locator('input').first.check()
                forms.nth(0).locator('button[type=submit]').click()
                expect(page.locator('[data-quiz-card]').nth(0)).to_contain_text('判定正确')
                forms.nth(1).locator('input').nth(0).check();forms.nth(1).locator('input').nth(1).check()
                forms.nth(1).locator('button[type=submit]').click()
                expect(page.locator('[data-quiz-card]').nth(1)).to_contain_text('判定正确')
                forms.nth(2).locator('input').first.check();forms.nth(2).locator('button[type=submit]').click()
                expect(page.locator('[data-quiz-card]').nth(2)).to_contain_text('判定正确')
                forms.nth(3).locator('input').fill('先进先出');forms.nth(3).locator('button[type=submit]').click()
                expect(page.locator('[data-quiz-card]').nth(3)).to_contain_text('判定正确')
                page.locator('[data-attendance]').click()
                expect(page.locator('[data-attendance]')).to_have_text('今日已签到')
                page.reload();expect(page.locator('[data-attendance]')).to_have_text('今日已签到')
                expect(page.locator('[data-material-practice]')).to_be_visible()
                assert model.calls==1,model.calls
                page.goto(base+'/#space/analysis/plans')
                page.locator('[data-open-create-plan]').click()
                page.locator('[name=subjects]').select_option(label='队列')
                page.locator('[name=goal]').fill('理解队列并完成对应练习')
                page.locator('[name=startDate]').fill('2026-11-10')
                page.locator('[name=endDate]').fill('2026-11-20')
                page.locator('#createPlanForm button[type=submit]').click()
                expect(page.locator('[data-adopt-draft]')).to_be_visible(timeout=20000)
                page.locator('details').filter(has=page.locator('a[href^="#space/practice/ai/"]')).locator('summary').first.click()
                expect(page.locator('a[href^="#space/practice/ai/"]').first).to_be_visible()
                page.locator('a[href^="#space/frameworks/"]').first.click()
                expect(page.locator('a[href^="#space/materials/"]').first).to_be_visible()
                page.goto(base+'/#space/exams')
                page.locator('[data-create-exam] [name=count]').fill('2')
                page.locator('[data-create-exam] .practice-select').filter(has=page.locator('[name=mode]')).locator('.practice-select-trigger').click()
                page.get_by_role('option',name='AI选题模拟卷（调用模型）',exact=True).click()
                page.locator('[data-create-exam] button[type=submit]').click()
                link=page.locator('a[href^="#space/exams/exam-"]').first
                expect(link).to_be_visible(timeout=15000);link.click()
                page.locator('[data-exam-start]').click()
                expect(page.locator('[data-exam-answer]').first).to_be_visible()
                page.locator('[data-exam-answer]').first.check()
                expect(page.locator('[data-exam-submit]')).to_be_enabled()
                page.reload()
                expect(page.locator('[data-exam-answer]').first).to_be_checked()
                page.locator('[data-exam-submit]').click()
                expect(page.locator('#examLearning')).to_contain_text('得分：')
                expect(page.locator('#examLearning')).to_contain_text('正确答案：')
                page.goto(base+'/#space/algorithms/bubble')
                expect(page.locator('[data-demo-next]')).to_be_visible()
                page.locator('[data-demo-next]').click()
                expect(page.locator('#algorithmLearning')).to_contain_text('第2/')
                page.locator('[data-demo-reset]').click()
                expect(page.locator('#algorithmLearning')).to_contain_text('第1/')
                assert page.evaluate("XueyaAlgorithmDemo.trace('bubble').at(-1).result.join(',')")=='1,2,3,4,5'
                assert page.evaluate("XueyaAlgorithmDemo.trace('bfs').at(-1).result.join(',')")=='0,1,2,3'
                page.goto(base+'/#space/materials')
                page.locator('.materials-list button').filter(has_text='队列讲义').click()
                expect(page.locator('[data-material-practice]')).to_be_visible()
                for width in (1440,390):
                    page.set_viewport_size({'width':width,'height':1000})
                    page.wait_for_function("document.getAnimations().filter(a=>a.effect?.getTiming().iterations!==Infinity).every(a=>a.playState!=='running')")
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    page.screenshot(path=str(output/f'graph-{width}.png'),full_page=True)
                assert model.calls==3,model.calls
                assert not errors,errors
                browser.close()
            print(json.dumps({'passed':True,'controlledCalls':model.calls,'paidApiCalls':0,'runtimeErrors':errors}))
        finally:
            server.should_exit=True;thread.join(timeout=5)


if __name__=='__main__':main()
