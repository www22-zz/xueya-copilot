"""Mock-API browser checks for the imported Figma orbit and dynamic plan data."""
import copy
import functools
import json
import os
import re
import threading
from datetime import date,timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright,expect
from scripts.check_plan_day_browser import QuietHandler,MOCK,ROOT

OUTPUT=ROOT/'test-results/learning-orbit'


def fixture():
    phases=[];days=[];order=0
    for phase_index,count in enumerate((1,2,7,3)):
        stages=[]
        for node_index in range(count):
            order+=1
            day=(date(2030,3,1)+timedelta(days=order-1)).isoformat()
            node=dict(id=f'n{order}',date=day,title=f'知识点{order}',minutes=30,questions=[],video=None,
                      completed=order==1,fixedPracticePrepared=True,requiredCount=0,submittedCount=0)
            stages.append(dict(id=f's{order}',title=f'学习任务{order}：数据结构与算法的完整长标题',nodes=[node],startDate=day,endDate=day))
            days.append(dict(date=day,isRestDay=False))
        phases.append(dict(title=f'阶段{phase_index+1}',startDate=stages[0]['startDate'],endDate=stages[-1]['endDate'],stages=stages,
                           report=dict(firstAccuracy=None,gradedQuestions=0,pendingQuestions=0,repeatAttempts=0,advice='继续学习',attempts=[])))
    days.append(dict(date='2030-03-14',isRestDay=True))
    plan=dict(id='active',title='星图学习计划',goal='用真实计划验证动态星图',status='active',revision=1,dailyMinutes=30,
              startDate='2030-03-01',endDate='2030-03-14',days=days,
              remaining=[dict(id='pending',title='<img src=x onerror=alert(1)> 待安排任务',phase='后续阶段',minutes=30)],
              learningRoute=dict(phases=phases,days=[],unallocatedTasks=1))
    return dict(ok=True,active=plan,drafts=[],history=[],jobs=[])


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    links=''.join(re.findall(r'<link rel="stylesheet"[^>]+>',(ROOT/'frontend/index.html').read_text(encoding='utf-8')))
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}/frontend/'
    html=f'''<html><head><meta charset="utf-8"><base href="{base}">{links}</head><body>
      <main id="preview" style="max-width:1300px;margin:20px auto;padding:0 12px"></main>
      <script src="js/ui/rich-content.js"></script><script src="js/study-quiz.js"></script><script src="js/learning-orbit.js"></script>
      <script src="js/learning-route.js"></script><script src="js/plan-view.js"></script></body></html>'''
    try:
        with sync_playwright() as p:
            executable=next((str(path) for path in (Path(os.environ.get('CHROME_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')),
                           Path('C:/Program Files/Google/Chrome/Application/chrome.exe')) if path.is_file()),None)
            browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
            for theme in ('dark','light'):
                for width in (1440,1024,390):
                    context=browser.new_context(viewport=dict(width=width,height=1000),timezone_id='Asia/Shanghai')
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.route('**/orbit-preview',lambda route:route.fulfill(content_type='text/html; charset=utf-8',body=html))
                    page.goto(base+'orbit-preview');page.evaluate('(t)=>document.documentElement.dataset.theme=t',theme)
                    page.evaluate(MOCK,fixture());page.wait_for_timeout(800)
                    expect(page.locator('.orbit-summary > div').nth(0)).to_contain_text('4')
                    expect(page.locator('.orbit-summary > div').nth(1)).to_contain_text('13')
                    expect(page.locator('.orbit-star-node')).to_have_count(13)
                    expect(page.locator('.orbit-star-node.is-done')).to_have_count(1)
                    expect(page.locator('.orbit-star-node.is-current')).to_have_count(1)
                    expect(page.locator('.orbit-star-node.is-pending')).to_have_count(11)
                    expect(page.locator('.orbit-route-links path')).to_have_count(12)
                    expect(page.locator('[data-orbit-zoom="fit"]')).to_be_visible()
                    expect(page.locator('.orbit-hero')).to_have_count(0)
                    expect(page.locator('.orbit-rest-footer')).to_contain_text('3月14日')
                    assert page.locator('.orbit-unscheduled img').count()==0
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    # All long labels fit their buttons and every label is visible by default.
                    assert page.locator('.orbit-canvas-node > strong').evaluate_all('els=>els.length===13&&els.every(e=>e.scrollWidth<=e.clientWidth+1)')
                    expect(page.locator('.orbit-node-time').last).to_have_css('opacity','1')
                    report=page.locator('[data-orbit-report]').nth(1)
                    report.click();expect(report).to_have_attribute('aria-expanded','true')
                    expect(page.locator('.orbit-report').nth(1)).to_be_visible();report.click()
                    page.screenshot(path=str(OUTPUT/f'{theme}-{width}.png'),full_page=True)
                    # A pending node can be opened with the keyboard; it is not falsely locked.
                    target=page.locator('[data-route-stage="s13"]');target.focus();page.wait_for_timeout(600)
                    target.press('Enter');before=page.evaluate('JSON.parse(sessionStorage.getItem("learning-route:active:position")).top')
                    expect(page.locator('.route-day-view')).to_be_visible();expect(page.locator('.route-day-view')).to_contain_text('2030-03-13')
                    expect(page.locator('.learning-orbit')).to_have_count(0)
                    page.locator('[data-node-back]').click();expect(page.locator('.learning-orbit')).to_be_visible();page.wait_for_timeout(800)
                    assert page.evaluate('document.activeElement.dataset.routeStage')=='s13'
                    assert abs(target.bounding_box()['y']-before)<5,(width,before,target.bounding_box(),page.evaluate('({point:JSON.parse(sessionStorage.getItem("learning-route:active:position")),scroll:scrollY,max:document.documentElement.scrollHeight-innerHeight,focus:document.activeElement.className})'))
                    page.emulate_media(reduced_motion='reduce')
                    expect(page.locator('.is-current .orbit-orb-ring')).to_have_css('animation-name','none')
                    # Fully completed and empty plans must not invent a current task or counters.
                    page.evaluate('''async()=>{fixture.active.learningRoute.phases.forEach(p=>p.stages.forEach(s=>s.nodes.forEach(n=>n.completed=true)));await ui.loadPlans();}''')
                    expect(page.locator('.orbit-star-node.is-done')).to_have_count(13);expect(page.locator('.is-current.orbit-star-node')).to_have_count(0)
                    page.evaluate('async()=>{fixture.active.learningRoute.phases=[];fixture.active.remaining=[];await ui.loadPlans();}')
                    expect(page.locator('.orbit-star-node')).to_have_count(0);expect(page.locator('.orbit-summary > div').first).to_contain_text('0')
                    assert not errors,errors
                    assert not page.evaluate('calls.some(c=>c.method!=="GET")')
                    context.close();print(theme,width,'PASS: dynamic counts, long labels, state, reports, keyboard, scroll recovery, reduced motion; no model calls')
            browser.close()
    finally:
        server.shutdown()


if __name__=='__main__':main()
