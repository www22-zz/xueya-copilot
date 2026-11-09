"""Isolated browser acceptance for the four document-requested workflows."""
import json
import runpy
import socket
import tempfile
import threading
import time
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright, expect
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.study_space_service import StudySpaceService
from backend.xueya.account_scope import account_owner
from .browser_runtime import browser_path

ROOT=Path(__file__).resolve().parents[1]
BaseModel=runpy.run_path(str(ROOT/'tests/python/test_material_learning.py'))['Model']


class Model(BaseModel):
    async def generate(self,messages,**kwargs):
        result=await super().generate(messages,**kwargs)
        data=json.loads(result['content'])
        for concept in data.get('concepts',[]):
            for q in concept['questions']:
                q.update(difficulty='简单',difficultyReason='单个概念的直接应用')
        result['content']=json.dumps(data,ensure_ascii=False)
        return result


def main():
    output=ROOT/'test-results/document-update-browser';output.mkdir(parents=True,exist_ok=True)
    model=Model()
    with tempfile.TemporaryDirectory(prefix='xueya-document-check-') as directory:
        app=create_app(Config(root=ROOT,data_dir=Path(directory),api_key='controlled',preserve_legacy_data=True,auto_import_demo=False),provider=model)
        sock=socket.socket();sock.bind(('127.0.0.1',0));base=f'http://127.0.0.1:{sock.getsockname()[1]}'
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',timeout_graceful_shutdown=3))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=browser_path(),headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1000})
                context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(base+'/') else r.abort())
                assert context.request.post(base+'/api/account/register',data={'username':'routecase','password':'Fixture123','confirmPassword':'Fixture123'}).ok
                token=context.request.get(base+'/api/platform/bootstrap').json()['token'];headers={'X-Xueya-Token':token}
                app.state.platform.repo.ensure_course(account_owner({'username':'routecase'}),{'id':'course-default','name':'数据结构'})
                assert context.request.post(base+'/api/platform/library/text',headers=headers,data={'courseId':'course-default','title':'第1章 队列','text':'# 队列\n'+('先进先出，队头出队，队尾入队。\n'*60),'idempotencyKey':'document-fixture'}).ok
                for _ in range(200):
                    rows=context.request.get(base+'/api/learning/space/materials',headers=headers).json()['materials']
                    if rows and rows[0]['concepts']:break
                    time.sleep(.1)
                assert rows[0]['concepts'],rows
                concept=rows[0]['concepts'][0];qid=concept['questionIds'][0]
                service=StudySpaceService(app.state.platform)
                plan=service.create_plan_draft('routecase',{'title':'队列学习路线','goal':'理解队列','subjects':['数据结构'],
                    'difficulty':'基础','startDate':'2026-11-06','daysCount':2,'dailyMinutes':20,'restDays':[],
                    'tasks':[{'key':'queue','title':'队列基础','subject':'数据结构','phase':'线性结构','minutes':20,'questionId':qid}]})
                service.adopt_plan('routecase',plan['id'],1,True,'browser-adopt')
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/#space/materials');expect(page.locator('[data-cg-book]')).to_have_count(1)
                page.locator('[data-cg-book]').click()
                canvas=page.locator('.cg-star-map');leaf=canvas.locator('[data-cg-node]')
                leaf.click();page.locator('[data-cg-practice]').click()
                expect(page.locator('[data-difficulty="简单"]')).to_contain_text('4题')
                expect(page.locator('[data-quiz-card]')).to_have_count(4)
                page.locator('[data-difficulty="困难"]').click();expect(page.locator('[data-concept-questions]')).to_contain_text('该难度暂无题目')
                page.locator('[data-difficulty="简单"]').click();page.screenshot(path=str(output/'concept.png'),full_page=True)
                page.locator('[data-cg-close-quiz]').click()
                original_pose=canvas.get_attribute('viewBox')
                page.locator('[data-concept-video]').click();expect(page.locator('[data-video-learning-return]')).to_be_visible()
                page.locator('[data-video-learning-return]').click();expect(canvas).to_be_visible()
                assert canvas.get_attribute('viewBox')==original_pose
                expect(leaf).to_have_count(1)
                leaf.click();page.locator('[data-cg-practice]').click()
                expect(page.locator('[data-difficulty="简单"]')).to_contain_text('4题')
                page.locator('[data-material-tab="video"]').click()
                page.locator('[data-course-card-id=mooc-ds]').click();expect(page.get_by_role('link',name='前往官方课程')).to_be_visible()
                page.screenshot(path=str(output/'video.png'),full_page=True)
                page.locator('[data-material-tab="plan"]').click();expect(page.locator('.route-stop')).to_have_count(1)
                assert page.locator('.route-heading h3').evaluate('(n)=>getComputedStyle(n).color')=='rgb(228, 237, 255)'
                page.screenshot(path=str(output/'route.png'),full_page=True)
                page.locator('[data-route-stage]').click();page.locator('[data-route-node]').click()
                expect(page.locator('[data-route-detail] [data-quiz-card]')).to_have_count(2)
                cards=page.locator('[data-route-detail] [data-quiz-card]')
                ids=cards.evaluate_all('(nodes)=>nodes.map(n=>n.dataset.quizCard)')
                for i in range(2):
                    card=cards.nth(i);expect(card.locator('form')).to_be_visible()
                    # Deliberately wrong first answer; completion is submission, not correctness.
                    if i==0:card.locator('input[name=answer][value="1"]').check()
                    else:
                        card.locator('input[name=answer][value="0"]').check();card.locator('input[name=answer][value="1"]').check()
                    card.locator('button[type=submit]').click();expect(card).to_contain_text('作答已保存')
                    fresh=context.request.get(base+'/api/learning/space/plan/list',headers=headers).json()['active']
                    assert fresh['learningRoute']['days'][0]['completed']==(i==1)
                page.locator('[data-node-back]').click();expect(page.locator('.route-days')).to_contain_text('学习已完成')
                page.reload();page.locator('[data-material-tab="plan"]').click();page.locator('[data-route-node]').click()
                assert page.locator('[data-route-detail] [data-quiz-card]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.quizCard)')==ids
                page.goto(base+'/#space/practice/hot100/h100-53');expect(page.get_by_role('link',name='打开交互演示')).to_be_visible()
                with context.expect_page() as new_page:page.get_by_role('link',name='打开交互演示').click()
                demo=new_page.value;demo.on('pageerror',lambda error:errors.append(str(error)))
                expect(demo.locator('.grid-scene .cube')).to_have_count(20)
                demo.locator('[data-sample]').select_option('1');expect(demo.locator('.example')).to_contain_text('预期输出 3')
                demo.locator('[data-next]').click();before=demo.locator('[data-step]').inner_text()
                demo.locator('[data-stage]').drag_to(demo.locator('[data-stage]'),source_position={'x':100,'y':100},target_position={'x':180,'y':140})
                assert demo.locator('[data-step]').inner_text()==before
                demo.locator('[data-play]').click();demo.wait_for_timeout(850);demo.locator('[data-play]').click()
                paused=demo.locator('[data-step]').inner_text();demo.wait_for_timeout(850);assert demo.locator('[data-step]').inner_text()==paused
                demo.screenshot(path=str(output/'dfs.png'),full_page=True)
                demo.locator('[data-reset]').click();expect(demo.locator('[data-step]')).to_contain_text('第 1 /')
                demo.goto(base+'/algorithm-demo.html?question=h100-63');expect(demo.locator('.array-cell')).to_have_count(5)
                demo.screenshot(path=str(output/'binary.png'),full_page=True)
                demo.set_viewport_size({'width':390,'height':844});demo.screenshot(path=str(output/'binary-mobile.png'),full_page=True)
                assert demo.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert model.calls==1,model.calls
                assert not errors,errors
                print(json.dumps({'ok':True,'controlledModelCalls':model.calls,'paidCalls':0,'browserErrors':errors,'screenshots':str(output)},ensure_ascii=False))
                browser.close()
        finally:
            server.should_exit=True;thread.join(timeout=10)
            if thread.is_alive():server.force_exit=True;thread.join(timeout=5)


if __name__=='__main__':main()
