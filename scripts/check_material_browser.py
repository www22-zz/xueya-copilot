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
                from backend.xueya.account_scope import account_owner
                from backend.xueya.common import Scope
                app.state.platform.repo.ensure_course(account_owner({'username':'materialcase'}),{'id':'course-default','name':'数据结构'})
                app.state.platform.repo.put(Scope(user_id=account_owner({'username':'materialcase'}),course_id='course-default'),'document','controlled-example',{'name':'示例记录.pdf','status':'示例已索引'},0)
                token=context.request.get(base+'/api/platform/bootstrap').json()['token']
                assert context.request.post(base+'/api/platform/library/text',headers={'X-Xueya-Token':token},data={
                    'courseId':'course-default','title':'队列讲义','text':'# 队列\n'+('先进先出，队头出队，队尾入队。\n'*60),
                    'idempotencyKey':'browser-upload'}).ok
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                polling_fixture={'active':False}
                def catalog_fixture(route):
                    response=route.fetch();payload=response.json()
                    for material in payload.get('materials',[]):
                        for concept in material.get('concepts',[]):
                            concept['label']='二叉树的顺序存储与链式存储结构及指针变化'
                    if polling_fixture['active'] and payload.get('materials'):
                        extra={**payload['materials'][0],'id':'controlled-pending','documentId':'controlled-pending','name':'后台解析状态夹具','concepts':[],'status':'parsing','ready':False}
                        payload['materials'].append(extra)
                    route.fulfill(response=response,json=payload)
                page.route('**/api/learning/space/materials?*',catalog_fixture)
                def graph_fixture(route):
                    response=route.fetch();payload=response.json()
                    # A parsed document without questions precedes the usable
                    # one, matching the formal bookshelf's introduction lesson.
                    payload['documents'].insert(0,{'id':'controlled-no-questions',
                        'name':'已解析但尚未出题的课件','subject':'数据结构','ready':True,'ranges':1})
                    # Deliberately shuffled chapter/part names must sort naturally.
                    payload['documents'].extend({'id':f'order-{i}','name':name,'subject':'数据结构','ready':True,'ranges':1} for i,name in enumerate(['week6_第4章_数组.pptx','week4 第3章_栈和队列.pptx','week3-第2章线性表（2）链表.pptx','week1 第1章_绪论.pptx','week2-第2章线性表（1）-顺序表.pptx']))
                    route.fulfill(response=response,json=payload)
                page.route('**/api/learning/space/course-graph?*',graph_fixture)

                page.goto(base+'/#space/materials')
                expect(page.locator('.cg-books')).to_be_visible()
                # Shelf groups real documents by subject, then opens a mind map.
                expect(page.locator('[data-cg-book]')).to_have_count(1)
                expect(page.locator('[data-cg-count]')).to_contain_text('4道题',timeout=20000)
                expect(page.locator('.cg-reader')).to_have_count(0)
                page.screenshot(path=str(output/'course-bookshelf.png'),full_page=True)
                page.locator('[data-cg-book]').click()
                expect(page.locator('.cg-mindmap')).to_be_visible()
                expect(page.locator('[data-cg-concept]')).to_have_count(1)
                order=page.locator('[data-cg-document]').all_text_contents()
                assert ['绪论','顺序表','链表','栈和队列','数组']==[next(x for x in ['绪论','顺序表','链表','栈和队列','数组'] if x in name) for name in order[:5]],order
                expect(page.locator('[data-ai-session-section]')).to_be_hidden()
                assert page.locator('.learning-secondary-tools').count()==0
                # Parsed, empty sources remain visible without fabricated points.
                page.locator('[data-cg-node=controlled-no-questions]').click()
                expect(page.locator('[data-cg-detail]')).to_contain_text('尚无已保存知识点')
                expect(page.locator('[data-cg-practice]')).to_have_count(0)
                page.locator('[data-cg-overview]').click()
                view=page.locator('.cg-mindmap').get_attribute('viewBox')
                page.locator('[data-cg-zoom="0.8"]').click()
                assert page.locator('.cg-mindmap').get_attribute('viewBox')!=view
                page.locator('[data-cg-fit]').click()
                assert page.locator('.cg-mindmap').get_attribute('viewBox')==view
                page.locator('[data-cg-concept]').focus()
                page.keyboard.press('Enter')
                expect(page.locator('[data-cg-practice]')).to_be_visible()
                expect(page.locator('[data-cg-video]')).to_contain_text('尚未定位')
                page.locator('[data-cg-practice]').click()
                expect(page.locator('[data-cg-questions] [data-quiz-answer]')).to_have_count(4)
                page.locator('[data-cg-close-quiz]').click()
                page.locator('[data-cg-search]').fill('队列')
                expect(page.locator('[data-cg-result]')).to_have_count(1)
                page.locator('[data-cg-result]').click()
                expect(page.locator('[data-cg-practice]')).to_be_visible()
                for theme in ('light','dark'):
                    page.evaluate("theme=>document.documentElement.dataset.theme=theme",theme)
                    for width in (2560,1440,390):
                        page.set_viewport_size({'width':width,'height':1000})
                        page.wait_for_function("document.getAnimations().filter(a=>a.effect?.getTiming().iterations!==Infinity).every(a=>a.playState!=='running')")
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (theme,width,page.evaluate("[...document.querySelectorAll('#materialLearning *')].filter(e=>e.getBoundingClientRect().right>innerWidth+2).slice(0,12).map(e=>[e.tagName,e.className.baseVal??e.className,e.getBoundingClientRect().width])"))
                        assert page.locator('.cg-mindmap text').evaluate_all("els=>els.every(e=>getComputedStyle(e).stroke==='none')")
                        page.screenshot(path=str(output/f'course-map-{theme}-{width}.png'),full_page=True)
                page.set_viewport_size({'width':1440,'height':1000})
                page.locator('[data-cg-back]').click()
                expect(page.locator('.cg-books')).to_be_visible()
                page.locator('[data-material-tab=graph]').click()
                expect(page.locator('[data-material-practice]')).to_be_visible(timeout=20000)
                page.locator('.materials-list button').filter(has_text='示例记录 · 无原件').first.click()
                expect(page.locator('#materialLearning')).to_contain_text('没有本地原文件')
                page.locator('.materials-list button').filter(has_text='队列讲义').click()
                expect(page.locator('[data-material-practice]')).to_be_visible(timeout=20000)
                assert page.locator('.material-graph svg').bounding_box()['height']>150
                assert page.locator('.material-graph svg text').evaluate_all("els=>els.every(e=>getComputedStyle(e).stroke==='none')")
                assert page.locator('.material-graph svg [data-node] text').evaluate_all("els=>els.every(e=>e.getBBox().width<90 && e.getBBox().height<80)")
                material_requests=[]
                page.on('request',lambda request:material_requests.append(request.url) if '/space/materials?' in request.url else None)
                page.locator('[data-material-tab=video]').click()
                expect(page.locator('.material-video')).to_have_count(1)
                assert page.locator('.material-video').first.get_attribute('target')=='_blank'
                assert page.url.endswith('#space/materials')
                page.locator('[data-material-tab=graph]').click()
                assert len(material_requests)<=1,material_requests

                assert page.locator('.learning-center-nav .sidebar-text').all_text_contents()==['课程资料学习','算法学习','408考研学习','错题本']
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
                # Simulate another parsing document and a real polling interval.
                # The same live form/input must survive the response unchanged.
                polling_fixture['active']=True
                page.evaluate("window.__answerForm=document.querySelector('[data-quiz-answer]');window.__answerForm.dataset.retention='keep';XueyaMaterialLearning.mount(document.querySelector('#materialLearning'))")
                page.wait_for_timeout(8500)
                assert page.evaluate("window.__answerForm===document.querySelector('[data-quiz-answer]') && window.__answerForm.dataset.retention==='keep'")
                polling_fixture['active']=False

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
                # Wrong material answers use the same original Question/Attempt.
                forms.nth(0).locator('input').nth(1).check()
                forms.nth(0).locator('button[type=submit]').click()
                expect(page.locator('[data-quiz-card]').nth(0)).to_contain_text('判定错误')
                page.goto(base+'/#space/review/materials')
                expect(page.locator('[data-wrong-quiz]')).to_have_count(1)
                expect(page.locator('[data-ai-session-section]')).to_be_hidden()
                page.locator('[data-wrong-quiz]').click()
                form=page.locator('[data-wrong-detail] [data-quiz-answer]')
                expect(form).to_be_visible()
                form.locator('input').first.check();form.locator('button[type=submit]').click()
                expect(page.locator('[data-wrong-detail]')).to_contain_text('判定正确')
                page.locator('[data-wrong-refresh]').click()
                expect(page.locator('[data-wrong-quiz]')).to_have_count(0)
                page.reload();expect(page.locator('[data-wrong-quiz]')).to_have_count(0)
                page.goto(base+'/#space/practice/hot100')
                expect(page.locator('[data-action=mark-wrong]').first).to_be_visible()
                algorithm_id=page.locator('.practice-row.is-active').get_attribute('data-id')
                page.locator('[data-action=mark-wrong]').first.click()
                page.goto(base+'/#space/review/algorithms')
                expect(page.locator('.practice-row')).to_have_count(1)
                assert page.locator('.practice-row').get_attribute('data-id')==algorithm_id
                page.screenshot(path=str(output/'wrong-algorithms.png'),full_page=True)
                page.goto(base+'/#space/review/exams')
                expect(page.locator('.practice-row')).to_have_count(0)
                expect(page.locator('[data-wrong-quiz]')).to_have_count(0)
                page.goto(base+'/#space/ask')
                expect(page.locator('[data-ai-session-section]')).to_be_visible()
                page.goto(base+'/#space/materials')
                page.locator('[data-attendance]').click()
                expect(page.locator('[data-attendance]')).to_have_text('今日已签到')
                page.reload();expect(page.locator('[data-attendance]')).to_have_text('今日已签到')
                page.locator('[data-material-tab=graph]').click()
                expect(page.locator('[data-material-practice]')).to_be_visible()
                assert model.calls==1,model.calls
                page.locator('[data-material-tab=plan]').click()
                assert '#space/materials' in page.url
                page.locator('[data-open-create-plan]').click()
                page.locator('[name=subjects]').select_option(label='数据结构')
                page.locator('[name=goal]').fill('理解队列并完成对应练习')
                page.locator('[name=startDate]').fill('2026-11-10')
                page.locator('[name=endDate]').fill('2026-11-20')
                page.locator('#createPlanForm button[type=submit]').click()
                expect(page.locator('[data-adopt-draft]')).to_be_visible(timeout=20000)
                page.locator('details').filter(has=page.locator('a[href^="#space/practice/ai/"]')).locator('summary').first.click()
                expect(page.locator('a[href^="#space/practice/ai/"]').first).to_be_visible()
                page.locator('a[href^="#space/frameworks/"]').first.click()
                expect(page.locator('.material-return a')).to_be_visible()
                expect(page.locator('.kf-node-actions a[href^="#space/practice/ai/"]').first).to_be_visible()
                expect(page.locator('.kf-node-actions a[href^="#space/courses/"]').first).to_be_visible()
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
                from backend.xueya.practice_catalog import exam_question
                exam_question_id=page.locator('[data-exam-answer]').first.get_attribute('name')
                wrong_option=(exam_question(exam_question_id)['answer']+1)%4
                page.locator('[data-exam-answer]').nth(wrong_option).check()
                expect(page.locator('[data-exam-submit]')).to_be_enabled()
                page.reload()
                expect(page.locator('[data-exam-answer]').nth(wrong_option)).to_be_checked()
                page.locator('[data-exam-submit]').click()
                expect(page.locator('#examLearning')).to_contain_text('得分：')
                expect(page.locator('#examLearning')).to_contain_text('正确答案：')
                page.goto(base+'/#space/review/exams')
                expect(page.locator('[data-wrong-quiz]')).to_have_count(1)
                expect(page.locator('.practice-row')).to_have_count(0)
                page.reload();expect(page.locator('[data-wrong-quiz]')).to_have_count(1)
                page.locator('[data-wrong-quiz]').click()
                expect(page.locator('[data-wrong-detail] [data-quiz-answer]')).to_be_visible()
                for theme in ('light','dark'):
                    page.evaluate("theme=>document.documentElement.dataset.theme=theme",theme)
                    for width in (1440,390):
                        page.set_viewport_size({'width':width,'height':1000})
                        page.wait_for_function("document.getAnimations().filter(a=>a.effect?.getTiming().iterations!==Infinity).every(a=>a.playState!=='running')")
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(theme,width)
                        page.screenshot(path=str(output/f'wrong-exams-{theme}-{width}.png'),full_page=True)
                page.set_viewport_size({'width':1440,'height':1000})
                page.goto(base+'/#space/review/algorithms')
                expect(page.locator('.practice-row')).to_have_count(1)
                expect(page.locator('[data-wrong-quiz]')).to_have_count(0)
                page.goto(base+'/#space/review/materials')
                expect(page.locator('.practice-row')).to_have_count(0)
                expect(page.locator('[data-wrong-quiz]')).to_have_count(0)
                page.goto(base+'/#space/algorithms/bubble')
                expect(page.locator('[data-demo-next]')).to_be_visible()
                page.locator('[data-demo-next]').click()
                expect(page.locator('#algorithmLearning')).to_contain_text('第2/')
                page.locator('[data-demo-reset]').click()
                expect(page.locator('#algorithmLearning')).to_contain_text('第1/')
                assert page.evaluate("XueyaAlgorithmDemo.trace('bubble').at(-1).result.join(',')")=='1,2,3,4,5'
                assert page.evaluate("XueyaAlgorithmDemo.trace('bfs').at(-1).result.join(',')")=='0,1,2,3'
                page.goto(base+'/#space/materials')
                page.locator('[data-material-tab=graph]').click()
                page.locator('.materials-list button').filter(has_text='队列讲义').click()
                expect(page.locator('[data-material-practice]')).to_be_visible()
                for theme in ('light','dark'):
                    page.evaluate("theme=>document.documentElement.dataset.theme=theme",theme)
                    for width in (2560,1440,390):
                        page.set_viewport_size({'width':width,'height':1000})
                        page.wait_for_function("document.getAnimations().filter(a=>a.effect?.getTiming().iterations!==Infinity).every(a=>a.playState!=='running')")
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (theme,width,page.evaluate("[...document.querySelectorAll('#materialLearning *')].filter(e=>e.getBoundingClientRect().right>innerWidth+2).slice(0,12).map(e=>[e.tagName,e.className.baseVal??e.className,e.getBoundingClientRect().width])"))
                        assert page.locator('.material-graph svg text').evaluate_all("els=>els.every(e=>getComputedStyle(e).stroke==='none')")
                        assert page.locator('.material-graph svg [data-node] text').evaluate_all("els=>els.every(e=>e.getBBox().width<90 && e.getBBox().height<80)")
                        page.screenshot(path=str(output/f'graph-{theme}-{width}.png'),full_page=True)
                assert model.calls==3,model.calls
                assert not errors,errors
                browser.close()
            print(json.dumps({'passed':True,'controlledCalls':model.calls,'paidApiCalls':0,'runtimeErrors':errors}))
        finally:
            server.should_exit=True;thread.join(timeout=5)


if __name__=='__main__':main()
