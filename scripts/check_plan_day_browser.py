"""Browser regression for daily plan focus, real quiz cards, and draft previews.

Uses saved-question fixtures only. No model calls or private backend writes.
Run with the project's Python environment (requires playwright and a browser).
"""
import copy
import functools
import json
import os
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'test-results' / 'plan-day'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def fixtures():
    video = {'title': '数据结构：逻辑结构与存储结构', 'url': '#space/courses/ds/intro', 'courseId': 'ds'}
    nodes = [
        dict(id='n1', date='2026-11-12', title='逻辑结构', minutes=30, questions=[dict(id='q1', revision=1)], video=video),
        dict(id='n2', date='2026-11-13', title='次日任务', minutes=30, questions=[dict(id='q2', revision=1)], video=video),
        dict(id='n3', date='2026-11-12', title='存储结构', minutes=20, questions=[dict(id='q3', revision=1)], video=video),
    ]
    for node in nodes:
        node.update(description='不应展示的教材描述', difficulty='简单', requiredCount=1, missingCount=0,
                    submittedCount=0, readiness='ready', completed=False)
    stage = dict(id='stage', title='逻辑结构与存储结构', startDate='2026-11-12', endDate='2026-11-13',
                 nodes=nodes, minutes=80, questionCount=3, prerequisites=[], reason='不应展示的排程理由')
    report = dict(firstAccuracy=None, gradedQuestions=0, pendingQuestions=0, repeatAttempts=0, advice='继续学习', attempts=[])
    plan = dict(id='active', title='当前计划', status='active', goal='学会数据结构', revision=1,
                startDate='2026-11-12', endDate='2026-11-13', dailyMinutes=60, days=[], completedHistory=[],
                learningRoute=dict(phases=[dict(title='基础概念', stages=[stage], report=report)], days=[], unallocatedTasks=0))
    draft = copy.deepcopy(plan)
    draft.update(id='draft', title='待采用草稿', status='draft', canAdopt=True)
    other = copy.deepcopy(draft)
    other.update(id='other', title='另一份草稿')
    return dict(ok=True, active=plan, drafts=[draft, other], history=[], jobs=[])


MOCK = r"""async fixture => {
  window.fixture=fixture;window.attempts=[];window.calls=[];
  window.XueyaPlatform={spaceFetch:async(url,options={})=>{
    const body=options.body?JSON.parse(options.body):null;
    calls.push({url,method:options.method||'GET',body});
    let value;
    if(url.endsWith('/plan/list'))value=fixture;
    else if(/\/plan\/[^/]+\/practice$/.test(url)){
      const id=url.split('/').at(-2),plan=[fixture.active,...fixture.drafts].find(p=>p.id===id);
      plan.learningRoute.phases.forEach(p=>p.stages.forEach(s=>s.nodes.forEach(n=>{if(body.nodeIds.includes(n.id))n.fixedPracticePrepared=true;})));
      value={ok:true,plan};
    }
    else if(url.includes('/quiz/question/')){
      const id=url.split('/').at(-1);
      value={ok:true,question:{id,revision:1,type:'single',sourceType:'fixed',subject:'数据结构',
        prompt:id==='q2'?'只属于次日的练习':id==='q3'?'存储结构主要描述什么？':'逻辑结构主要描述什么？',
        options:['数据元素之间的关系','机器型号'],limitations:[]}};
    }else if(url.endsWith('/quiz/list'))value={ok:true,attempts};
    else if(url.endsWith('/quiz/attempts')&&body){
      const attempt={id:'answer-'+body.nodeId,questionId:body.questionId,questionRevision:1,
        planId:body.planId,nodeId:body.nodeId,answer:body.answer,revision:1,createdAt:'2026-11-12T02:00:00Z',
        effectiveEvaluation:{status:'graded'},evaluations:[{status:'graded',source:'objective',
          createdAt:'2026-11-12T02:00:00Z',result:{correct:true,explanation:'回答正确'}}]};
      attempts.push(attempt);value={ok:true,attempt};
    }else if(url.endsWith('/materials'))value={ok:true,materials:[]};
    else throw Error('Unexpected request: '+url);
    return {json:async()=>value};
  }};
  window.ui=XueyaPlan.create();await ui.mount(document.querySelector('#preview'));
}"""


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    browser_path = next((str(path) for path in (
        Path(os.environ.get('CHROME_PATH', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')),
        Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Google/Chrome/Application/chrome.exe',
    ) if path.is_file()), None)
    links = ''.join(re.findall(r'<link rel="stylesheet"[^>]+>', (ROOT/'frontend/index.html').read_text(encoding='utf-8')))
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}/frontend/'
    html = f'''<html><head><meta charset="utf-8"><base href="{base}">{links}</head><body>
      <main id="preview" style="max-width:1200px;margin:20px auto;padding:0 12px"></main>
      <script src="js/ui/rich-content.js"></script><script src="js/study-quiz.js"></script>
      <script src="js/learning-orbit.js"></script><script src="js/learning-route.js"></script><script src="js/plan-view.js"></script></body></html>'''
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, **({'executable_path':browser_path} if browser_path else {}))
            for theme in ('dark', 'light'):
                for width in (1440, 390):
                    context = browser.new_context(viewport={'width':width, 'height':1000}, timezone_id='Asia/Shanghai')
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.route('**/plan-day-preview', lambda route: route.fulfill(content_type='text/html; charset=utf-8', body=html))
                    page.goto(base+'plan-day-preview')
                    page.evaluate('(t)=>document.documentElement.dataset.theme=t', theme)
                    page.evaluate(MOCK, fixtures())
                    page.locator('[data-route-date="2026-11-12"]').click()
                    expect(page.locator('.route-day-view')).to_be_visible()
                    expect(page.locator('[data-route-video]')).to_have_count(1)
                    expect(page.locator('[data-quiz-answer]')).to_have_count(2)
                    expect(page.locator('[data-quiz-card="q2"]')).to_have_count(0)
                    assert page.locator('.route-mindmap,.route-phases,.route-days,.route-node-detail').count()==0
                    assert '教材描述' not in page.locator('.route-day-view').inner_text()
                    expect(page.locator('.plan-top-header')).to_be_hidden()
                    expect(page.locator('.plan-view-tabs')).to_be_hidden()
                    expect(page.locator('.plan-request-log')).to_be_hidden()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(OUTPUT/f'{theme}-{width}-day.png'), full_page=True)
                    # Submission retains the exact plan, node and question version.
                    page.locator('[data-quiz-card="q3"] input[value="0"]').check()
                    page.locator('[data-quiz-card="q3"] button[type="submit"]').click()
                    expect(page.locator('[data-quiz-card="q3"]')).to_contain_text('作答已保存')
                    body=page.evaluate('calls.find(c=>c.method==="POST").body')
                    assert {k:body[k] for k in ('questionId','questionRevision','planId','nodeId')}==dict(questionId='q3',questionRevision=1,planId='active',nodeId='n3')
                    # Remounting keeps the selected day and restores the saved answer.
                    page.evaluate('ui.loadPlans()')
                    expect(page.locator('[data-quiz-card="q3"]')).to_contain_text('作答已保存')
                    page.locator('[data-node-back]').click()
                    expect(page.locator('.plan-view-tabs')).to_be_visible()
                    page.locator('[data-route-date="2026-11-13"]').click()
                    expect(page.locator('[data-quiz-card="q2"]')).to_be_visible()
                    expect(page.locator('[data-quiz-card="q1"]')).to_have_count(0)
                    page.locator('[data-node-back]').click()
                    # Draft day is read-only but actually displays the question and options.
                    page.locator('[data-plan-view="drafts"]').click()
                    page.locator('[data-learning-route="draft"] [data-route-date="2026-11-12"]').click()
                    expect(page.locator('.route-preview-options')).to_have_count(2)
                    expect(page.locator('[data-quiz-answer]')).to_have_count(0)
                    expect(page.locator('.route-day-view')).to_contain_text('逻辑结构主要描述什么')
                    expect(page.locator('[data-adopt-draft="draft"]')).to_be_hidden()
                    expect(page.locator('[data-learning-route="other"]')).to_be_hidden()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(OUTPUT/f'{theme}-{width}-draft.png'), full_page=True)
                    page.locator('[data-node-back]').click()
                    expect(page.locator('[data-adopt-draft="draft"]')).to_be_visible()
                    # Empty bindings have short, honest empty states and no paid generation.
                    page.evaluate('''async()=>{fixture.active.learningRoute.phases[0].stages[0].nodes.forEach(n=>{n.questions=[];n.video=null;});await ui.loadPlans();}''')
                    page.locator('[data-plan-view="current"]').click()
                    page.locator('[data-route-date="2026-11-12"]').click()
                    expect(page.locator('.route-day-view')).to_contain_text('暂未匹配到')
                    expect(page.locator('.route-day-view')).to_contain_text('暂未匹配')
                    assert not errors, errors
                    posts=page.evaluate('calls.filter(c=>c.method==="POST")')
                    assert len([p for p in posts if p['url'].endswith('/quiz/attempts')])==1 and all(p['url'].endswith('/quiz/attempts') or p['url'].endswith('/practice') for p in posts)
                    context.close()
                    print(theme, width, 'PASS: day isolation, answer binding/recovery, draft preview, empty states; no model calls')
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
