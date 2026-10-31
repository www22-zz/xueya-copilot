"""Exercise learning-center navigation and real HTTP wiring in isolated Chrome.

No private database or live model services are used.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time

for key in ('MIMO_API_KEY', 'RAG_OCR_API_KEY', 'RAG_EMBEDDING_API_KEY', 'RAG_RERANK_API_KEY', 'TAVILY_API_KEY'):
    os.environ[key] = ''

import uvicorn
from playwright.sync_api import sync_playwright, expect
from backend.xueya.app import create_app
from backend.xueya.config import Config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'test-results/repair-learning-space'


class Model:
    calls = 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        await asyncio.sleep(.2)
        if '拆解可执行任务' in messages[0]['content']:
            from backend.xueya.practice_catalog import exam_bank
            question=next(q for q in exam_bank()['questions'] if q['subject']=='操作系统')
            value = {'explanation': '先理解进程状态，再完成回忆练习。', 'tasks': [
                {'title': '理解进程状态转换', 'subject': '操作系统', 'minutes': 30},
                {'title': '练习：'+question['title'], 'subject': '操作系统', 'minutes': 30, 'questionId':question['id'], 'phase':'巩固'}]}
        elif '生成一道可独立解答的练习' in messages[0]['content']:
            kind=json.loads(messages[1]['content'])['type']
            value={'prompt':'解释临界区互斥的含义。','rubric':[{'id':'one','description':'互斥约束和适用条件','points':4}],'explanation':'同一时刻仅一个进程访问临界资源。'} if kind=='short' else {'prompt':'临界区互斥要求什么？','options':['同时访问','互斥访问'],'answer':1,'explanation':'同一时刻仅一个进程进入相关临界区。'}
        elif '评阅学生答案' in messages[0]['content']:
            payload=json.loads(messages[1]['content'])
            value={'feedback':'说明了互斥限制，适用条件还需补充。','rubricPoints':[{'id':r['id'],'earned':r['points']/2} for r in payload['rubric']]}
        else:
            value = {'title': '进程知识框架', 'nodes': [
                {'id': 'root', 'label': '进程管理', 'parentId': None},
                {'id': 'states', 'label': '进程状态', 'parentId': 'root'}]}
        return {'content': json.dumps(value, ensure_ascii=False), 'model': 'controlled'}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-repair-browser-') as directory:
        model = Model()
        app = create_app(Config(root=ROOT, data_dir=Path(directory), auto_import_demo=False,
                                preserve_legacy_data=True), provider=model)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=3))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started: break
                time.sleep(.05)
            assert server.started
            base = f'http://127.0.0.1:{port}'
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=__import__('scripts.browser_runtime', fromlist=['browser_path']).browser_path(), headless=True)
                context = browser.new_context(viewport={'width': 1400, 'height': 950})
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
                reply = context.request.post(base+'/api/account/register', data={
                    'username': 'repaircase', 'password': 'Fixture123', 'confirmPassword': 'Fixture123'})
                assert reply.ok
                page = context.new_page(); errors=[];page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base+'/#space/courses')
                nav = page.locator('.learning-center-nav')
                expect(nav).to_be_visible()
                assert nav.locator('a').all_text_contents() == ['课程学习', '练习', '复习', '学习分析']
                assert nav.evaluate("node => node.parentElement.classList.contains('learning-center-shell')")
                assert nav.bounding_box()['x'] < page.locator('#spaceContent').bounding_box()['x']
                assert page.locator('.workspace-primary > a').all_text_contents() == ['AI 助手', '学习中心']
                page.locator('.workspace-primary > a').first.click()
                expect(page.locator('#chatThread')).to_be_visible();expect(nav).to_be_hidden()
                assert page.locator('#chatThread').bounding_box()['height'] > 100
                assert page.locator('#chatThread').bounding_box()['y'] < 600
                page.goto(base+'/#space/frameworks')
                expect(page.locator('[data-kf-generate]')).to_be_visible()
                assert model.calls == 0, 'Opening history must not generate content'
                page.locator('[data-kf-generate]').click()
                expect(page.locator('.kf-node-card').first).to_contain_text('进程管理')
                def accept_dialog(dialog):
                    if dialog.type!='prompt':dialog.accept();return
                    if '添加学习资源链接' in dialog.message:dialog.accept('https://docs.python.org/3/tutorial/')
                    elif '输入修正参考分' in dialog.message:dialog.accept('3')
                    else:dialog.accept('用户补充概念')
                page.on('dialog',accept_dialog)
                page.locator('[data-kf-add-child]').first.click()
                expect(page.locator('.kf-node-card')).to_have_count(3)
                page.locator('.kf-node-card').last.drag_to(page.locator('.kf-node-card').nth(1))
                expect(page.locator('.kf-node-card').last.locator('.kf-node-badge')).to_have_text('L2')
                page.locator('[data-kf-collapse]').first.click()
                expect(page.locator('.kf-node-card')).to_have_count(1)
                page.locator('[data-kf-collapse]').first.click()
                expect(page.locator('.kf-node-card')).to_have_count(3)
                page.reload()
                expect(page.locator('.kf-node-card')).to_have_count(3)
                page.goto(base+'/#space/analysis')
                page.locator('[data-tab-switch=plan]').click()
                page.locator('[data-open-create-plan]').click()
                page.locator('[name=goal]').fill('复习进程和线程')
                page.locator('#createPlanForm button[type=submit]').click()
                expect(page.locator('[data-adopt-draft]')).to_be_visible()
                page.locator('[data-adopt-draft]').click()
                expect(page.locator('[data-toggle-task]').first).to_be_visible()
                page.locator('[data-toggle-task]').first.check()
                expect(page.locator('[data-toggle-task]').first).to_be_checked()
                page.screenshot(path=str(OUT/'learning-center-desktop.png'), full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                expect(page.locator('.learning-center-nav')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                page.screenshot(path=str(OUT/'learning-center-mobile.png'), full_page=True)
                page.evaluate("document.documentElement.dataset.theme='dark'")
                page.screenshot(path=str(OUT/'learning-center-mobile-dark.png'), full_page=True)
                page.goto(base+'/#space/ask')
                expect(page.locator('.learning-shortcuts')).to_contain_text('今日任务')
                expect(page.locator('[data-shortcut-task]').first).to_be_checked()
                page.locator('[data-shortcut-task]').last.check()
                page.locator('[data-shortcut-task]').last.uncheck()
                page.locator('[data-open-my-plan]').click()
                expect(page.locator('[data-toggle-task]').first).to_be_visible()
                for view in ('courses','practice','review','analysis'):
                    page.locator(f'.learning-center-nav a[data-view={view}]').click()
                    expect(page.locator(f'.learning-center-nav a[data-view={view}]')).to_have_attribute('aria-current','page')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                page.locator('[data-tab-switch=plan]').click()
                resource=page.locator('.plan-task-row a[href^="#space/practice/exam408/"]').first
                href=resource.get_attribute('href');assert href
                question_id=href.rsplit('/',1)[-1]
                from backend.xueya.practice_catalog import exam_bank
                expected_question=next(q for q in exam_bank()['questions'] if q['id']==question_id)
                resource.click();expect(page.locator('.practice-detail h2')).to_have_text(expected_question['title'])
                page.reload();expect(page.locator('.practice-detail h2')).to_have_text(expected_question['title'])
                page.goto(base+'/#space/analysis');page.locator('[data-tab-switch=plan]').click()
                page.locator('[data-task-link]').first.click()
                expect(page.locator('.plan-task-row')).to_contain_text(['用户链接，未核验',''])
                page.locator('[data-adjust-plan]').click();page.locator('[name=dailyMinutes]').fill('15')
                page.locator('#createPlanForm button[type=submit]').click()
                expect(page.locator('[data-adopt-draft]')).to_be_visible()
                page.locator('.plan-draft-preview summary').click()
                expect(page.locator('.plan-draft-preview')).to_contain_text('保留已完成 1 项')
                expect(page.locator('.plan-stat-bar')).to_contain_text('每日预算：60 分钟')
                page.locator('[data-adopt-draft]').click()
                expect(page.locator('.plan-stat-bar')).to_contain_text('每日预算：15 分钟')
                expect(page.locator('.plan-stat-bar')).to_contain_text('保留历史完成 1 项')
                page.reload();page.locator('[data-tab-switch=plan]').click()
                expect(page.locator('.plan-stat-bar')).to_contain_text('保留历史完成 1 项')
                # Chat intake must reuse known conditions. Refresh an actual
                # queued job; recovery may read it but cannot resubmit models.
                page.goto(base+'/#space/ask')
                page.locator('#chatInput').fill('帮我规划操作系统，每天45分钟')
                page.get_by_role('button',name='发送问题',exact=True).click()
                expect(page.locator('.ai-message').last).to_contain_text('还需要期限或持续天数')
                assert model.calls==3
                page.locator('[data-plan-defaults]').last.click()
                page.wait_for_function("JSON.parse(localStorage.getItem(window.XueyaDataKey('xueya-copilot-workspace-v3'))).courses.some(c=>c.data.messages.some(m=>m.artifacts?.studyPlanning?.status==='queued'))")
                page.reload()
                card=page.locator('[data-study-plan]').filter(has=page.get_by_role('link',name='查看草稿与采用')).last
                expect(card).to_be_visible()
                chat_plan_id=card.get_attribute('data-study-plan');assert chat_plan_id
                expect(page.locator('.ai-message').last).to_contain_text('计划草稿已保存')
                assert model.calls==5, 'Refresh must not restart the two generation calls'
                card.get_by_role('link',name='打开关联知识框架').click()
                expect(page.locator('.kf-node-card').first).to_contain_text('进程管理')
                page.get_by_role('link',name='查看关联计划').click()
                expect(page.locator(f'[data-adopt-draft="{chat_plan_id}"]')).to_be_visible()
                assert model.calls==5
                page.goto(base+'/#space/ask')
                page.locator('#chatInput').fill('请生成一道操作系统主观题')
                page.get_by_role('button',name='发送问题',exact=True).click()
                short=page.locator('[data-quiz-card]').last
                expect(short.locator('textarea[name=answer]')).to_be_visible()
                short.locator('textarea[name=answer]').fill('同一时刻最多一个进程进入相关临界区。')
                short.get_by_role('button',name='保存并提交作答',exact=True).click()
                expect(short.locator('.quiz-evaluation')).to_contain_text('2 / 4')
                short.locator('[data-quiz-review]').click()
                expect(short.locator('.quiz-evaluation')).to_have_count(2)
                expect(short.locator('.quiz-evaluation').last).to_contain_text('graded')
                short.locator('[data-quiz-correct]').click()
                expect(short.locator('.quiz-evaluation')).to_have_count(3)
                expect(short.locator('.quiz-evaluation').last).to_contain_text('人工修正')
                expect(short.locator('.quiz-evaluation').last).to_contain_text('3 / 4')
                attempt_id=short.get_attribute('data-attempt-id');question_id=short.get_attribute('data-quiz-card')
                short.get_by_role('link',name='在练习打开同一次作答').click()
                expect(page.locator('[data-quiz-card]')).to_have_attribute('data-attempt-id',attempt_id)
                expect(page.locator('.quiz-evaluation')).to_have_count(3)
                page.reload();expect(page.locator('.quiz-evaluation')).to_have_count(3)
                assert model.calls==8,'Review must not create another attempt or replay on refresh'
                page.goto(base+'/#space/ask')
                restored=page.locator(f'[data-quiz-card="{question_id}"]')
                expect(restored).to_have_attribute('data-attempt-id',attempt_id)
                page.locator('#chatInput').fill('请生成一道操作系统单选题')
                page.get_by_role('button',name='发送问题',exact=True).click()
                objective=page.locator('[data-quiz-card]').last
                expect(objective.locator('input[type=radio]')).to_have_count(2)
                objective.locator('input[value="0"]').check()
                objective.get_by_role('button',name='保存并提交作答',exact=True).click()
                expect(objective.locator('.quiz-evaluation')).to_contain_text('判定错误')
                assert model.calls==9,'Objective scoring must not call the model'
                objective_id=objective.get_attribute('data-quiz-card')
                page.goto(base+'/#space/review')
                expect(page.locator(f'a[href^="#space/practice/ai/{objective_id}/"]')).to_be_visible()
                page.screenshot(path=str(OUT/'chat-quiz-mobile.png'),full_page=True)
                assert not errors, errors
                browser.close()
                result={'navigation': 'passed', 'framework_history_and_generation': 'passed',
                                  'plan_create_adopt_complete': 'passed', 'mobile': 'passed',
                                  'real_question_jump_and_adjustment':'passed',
                                  'chat_intake_job_refresh_and_framework':'passed',
                                  'chat_quiz_practice_and_evaluation_versions':'passed',
                                  'page_errors':errors,'controlled_model_calls':model.calls,'paid_calls':0}
                (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(result))
        finally:
            server.should_exit=True;thread.join(10);sock.close()


if __name__ == '__main__':
    main()
