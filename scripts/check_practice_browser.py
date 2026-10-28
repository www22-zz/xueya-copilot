"""Real Chrome acceptance against an isolated local server. Never reads .env or production data."""
import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright, expect
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.practice_bank import bank as fixed_bank

CHROME = os.environ.get('CHROME_PATH', 'C:/Program Files/Google/Chrome/Application/chrome.exe')


def main():
    output = Path('test-results/practice-repair')
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with tempfile.TemporaryDirectory(prefix='xueya-practice-ui-', ignore_cleanup_errors=True) as directory:
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        base = 'http://127.0.0.1:' + str(sock.getsockname()[1])
        app = create_app(Config(data_dir=Path(directory), api_key=''))
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        while not server.started:
            time.sleep(.05)
        # Keep fixed IDs for the existing progress/offline regression scenarios.
        # Automatic document generation has its own end-to-end acceptance script.
        app.state.practice_generation.catalog = lambda account, course_id=None, history=False: {
            **fixed_bank(), 'questions': [] if history else fixed_bank()['questions'], 'generations': [], 'available': False}
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME, headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = context.new_page()
            page.set_default_timeout(12000)
            page.on('pageerror', lambda error: errors.append(str(error)))
            def action(name):
                return page.locator('#practiceModule [data-action="' + name + '"]')
            def select_filter(name, value):
                field = page.locator(f'select[data-filter="{name}"]')
                label = field.locator(f'option[value="{value}"]').inner_text()
                field.locator('..').get_by_role('combobox').click()
                page.locator('.practice-select-menu').get_by_role('option', name=label, exact=True).click()
            def go(route):
                page.goto(base + '/#space/' + route)
                expect(page.locator('#spacePage')).to_be_visible()
                page.wait_for_function("!document.querySelector('#practiceModule') || document.querySelectorAll('.practice-row').length > 0")
            def state():
                return page.evaluate("async()=>{const b=await(await fetch('/api/platform/bootstrap')).json();return(await fetch('/api/practice/state',{headers:{'X-Xueya-Token':b.token}})).json()}")
            def synced():
                page.wait_for_function("JSON.parse(localStorage.getItem('xueya-practice-ops:repairuser')||'[]').length===0")
            def current_id():
                return page.locator('.practice-detail-meta').inner_text().split(' · ')[0]
            def record(name):
                checks.append(name)
                print('PASS', name, flush=True)
            try:
                # No injected JS fixes: click the actual home-page entry, then register in the real dialog.
                page.goto(base)
                page.locator('.hero-actions a').first.click()
                expect(page.locator('#accountLoginDialog')).to_be_visible()
                page.locator('[data-auth-switch]').click()
                page.locator('#accountLoginDialog [name=username]').fill('repairuser')
                page.locator('#accountLoginDialog [name=password]').fill('Repair12345')
                page.locator('#accountLoginDialog [name=confirmPassword]').fill('Repair12345')
                page.locator('#accountLoginDialog button[type=submit]').click()
                expect(page.locator('#homePage')).to_be_hidden()
                expect(page.locator('#spacePage')).to_be_visible()
                record('home-start-login-opens-workspace')
                page.screenshot(path=str(output / 'overview.png'))
                go('practice/hot100')
                expect(page.locator('.practice-row')).to_have_count(100)
                expect(page.locator('.practice-row').first).to_be_visible()
                assert page.locator('.wb-legacy').count() == 0
                assert page.locator('.practice-code').count() == 0
                action('reveal').click()
                expect(page.locator('.practice-code')).to_be_visible()
                action('language').filter(has_text='Java').click()
                assert 'class Solution' in page.locator('.practice-code').inner_text()
                assert page.locator('a', has_text='在力扣打开').get_attribute('target') == '_blank'
                record('hot100-visible-folded-three-languages-original-link')
                action('category').filter(has_text='基础 100').click()
                expect(page.locator('.practice-row')).to_have_count(100)
                assert 'foundation' in page.url
                assert action('category').filter(has_text='面试题').count() == 0
                assert page.locator('.practice-answer').count() == 0
                first = current_id()
                action('mark-wrong').click()
                assert current_id() == first
                synced()
                assert state()['statuses'][first]['wrongCount'] == 0
                record('two-categories-no-interview-manual-wrong-entry-no-error-count')
                action('category').filter(has_text='Hot 100').click()
                search = page.locator('[data-filter=keyword]')
                search.fill('两数之和')
                expect(page.locator('.practice-row')).to_have_count(1)
                first = current_id()
                action('fuzzy').click()
                assert current_id() == first
                action('random').click()
                assert current_id() == first
                action('master').click()
                expect(page.locator('.practice-detail-pane')).to_contain_text('已刷完')
                action('show-mastered').first.click()
                expect(action('random')).to_have_text('随机回顾')
                action('random').click()
                assert current_id() == first
                synced()
                assert state()['statuses'][first]['status'] == 'mastered'
                action('reset').click()
                action('status').filter(has_text='待刷').click()
                action('clear-filters').first.click()
                record('combined-search-fuzzy-random-master-completion-recall-reset')
                # Save a note, immediately switch before the debounce, and prove it stays on the original question.
                page.locator('.practice-row').first.click()
                note_id = current_id()
                page.locator('[data-note]').fill('**原题笔记**\n\n- 注意边界')
                page.locator('.practice-row').nth(1).click()
                page.wait_for_timeout(1400)
                synced()
                assert state()['notes'][note_id]['text'].startswith('**原题笔记**')
                page.locator('[data-id="' + note_id + '"]').first.click()
                action('note-mode').click()
                expect(page.locator('.practice-note-preview strong')).to_have_text('原题笔记')
                action('note-mode').click()
                page.locator('[data-note]').fill('')
                page.wait_for_timeout(1400)
                synced()
                assert state()['notes'][note_id]['text'] == ''
                record('note-switch-before-debounce-markdown-preview-clear-save')
                # Correct and wrong objective attempts are exercised through the submit button.
                action('category').filter(has_text='基础 100').click()
                select_filter('type', 'single')
                expect(page.locator('.practice-row')).to_have_count(50)
                qid = current_id()
                bank = json.loads(Path('backend/xueya/data/practice_bank.json').read_text(encoding='utf-8'))['questions']
                q = next(q for q in bank if q['id'] == qid)
                action('pick').nth((q['answer'] + 1) % 4).click()
                action('submit-single').click()
                expect(page.locator('.practice-result')).to_contain_text('回答错误')
                assert current_id() == qid
                synced()
                assert state()['statuses'][qid]['wrongCount'] == 1
                action('re-answer').click()
                assert page.locator('.practice-answer').count() == 0
                action('pick').nth(q['answer']).click()
                action('submit-single').click()
                synced()
                assert state()['statuses'][qid]['status'] == 'wrong'
                record('single-submit-wrong-stays-reanswer-correct-remains-wrong')
                go('review')
                # Starting at the last wrong question must wrap to remaining earlier questions.
                last_wrong = page.locator('.practice-row').last.get_attribute('data-id')
                if last_wrong != qid:
                    page.locator('.practice-row').last.click()
                    action('conquer').click()
                    assert current_id() == qid
                page.locator('[data-id="' + qid + '"]').first.click()
                assert page.locator('.practice-answer').count() == 0
                action('conquer').click()
                synced()
                assert state()['statuses'][qid]['status'] == 'mastered'
                record('review-folded-conquer-advances')
                go('practice/foundation')
                select_filter('type', 'fill')
                qid = current_id()
                page.locator('[data-fill]').fill('a deliberately wrong answer')
                action('submit-fill').click()
                synced()
                action('also-correct').click()
                synced()
                row = state()['statuses'][qid]
                assert row['wrongCount'] == 0 and row['status'] == 'pending'
                record('fill-manual-equivalent-corrects-only-current-error')
                # Keep an offline note and state change, including refresh, then reconnect without duplicates.
                go('practice/hot100')
                page.locator('[data-filter=keyword]').fill('')
                page.locator('.practice-row').first.click()
                qid = current_id()
                page.wait_for_function('navigator.serviceWorker.controller !== null')
                context.set_offline(True)
                page.locator('[data-note]').fill('离线笔记')
                action('mark-wrong').click()
                page.wait_for_timeout(1300)
                expect(page.locator('.practice-sync')).to_contain_text('待同步')
                page.reload()
                expect(page.locator('.practice-detail-head')).to_contain_text('错题本')
                expect(page.locator('[data-note]')).to_have_value('离线笔记')
                context.set_offline(False)
                action('retry-sync').click()
                synced()
                assert state()['notes'][qid]['text'] == '离线笔记'
                assert state()['statuses'][qid]['wrongCount'] == 0
                record('offline-state-note-refresh-reconnect-deduplicate')
                # Actual mobile navigation and list-position restoration.
                go('practice/foundation')
                select_filter('type', 'fill')
                page.set_viewport_size({'width': 390, 'height': 844})
                page.locator('.practice-row').nth(2).click()
                expect(page.locator('.practice-module')).to_have_class(__import__('re').compile('is-fullscreen'))
                page.locator('[data-fill]').fill('not persistent')
                page.screenshot(path=str(output / 'mobile.png'), full_page=True)
                action('back').click()
                expect(page.locator('.practice-list-pane')).to_be_visible()
                page.reload()
                assert page.locator('[data-fill]').input_value() == ''
                assert page.locator('.practice-answer').count() == 0
                record('mobile-fullscreen-back-refresh-clears-transient')
                page.set_viewport_size({'width': 1440, 'height': 1000})
                go('review')
                page.screenshot(path=str(output / 'review.png'), full_page=True)
                go('practice/hot100')
                page.screenshot(path=str(output / 'practice.png'), full_page=True)
                # Two browser profiles edit the same question before either sees the other's revision.
                go('review')
                page.locator('[data-id="' + qid + '"]').first.click()
                sibling = browser.new_context(storage_state=context.storage_state(), viewport={'width':1440,'height':1000})
                peer = sibling.new_page()
                peer.goto(base + '/#space/review')
                expect(peer.locator('.practice-row').first).to_be_visible()
                peer.locator('[data-id="' + qid + '"]').first.click()
                peer.route('**/api/practice/ops', lambda route: route.abort('failed'))
                peer.locator('[data-note]').fill('另一浏览器副本')
                peer.wait_for_timeout(1300)
                page.locator('[data-note]').fill('当前浏览器版本')
                page.wait_for_timeout(1300)
                synced()
                peer.unroute('**/api/practice/ops')
                peer.locator('[data-action=retry-sync]').click()
                expect(peer.locator('.practice-conflicts')).to_be_visible()
                expect(peer.locator('.practice-conflicts')).to_contain_text('另一浏览器副本')
                expect(peer.locator('.practice-conflicts')).to_contain_text('当前浏览器版本')
                peer.locator('[data-action=keep-conflict]').click()
                expect(peer.locator('.practice-conflicts')).to_have_count(0)
                saved = state()['notes'][qid]
                assert saved['text'] == '另一浏览器副本' and saved['conflicts'] == []
                peer.reload()
                expect(peer.locator('[data-note]')).to_have_value('另一浏览器副本')
                sibling.close()
                record('two-browsers-note-conflict-both-copies-choice-persists')
                action('retry-sync').click()
                expect(page.locator('[data-note]')).to_have_value('另一浏览器副本')
                # Expire the actual local session, queue work, then log back into the same account.
                app.state.account.sessions.clear()
                page.locator('[data-note]').fill('登录失效时的草稿')
                page.wait_for_timeout(1300)
                expect(page.locator('[data-note-status]')).to_contain_text('保存失败')
                action('retry-sync').click()
                expect(action('login')).to_be_visible()
                action('login').click()
                expect(page.locator('#accountLoginDialog')).to_be_visible()
                page.locator('#accountLoginDialog [name=username]').fill('repairuser')
                page.locator('#accountLoginDialog [name=password]').fill('Repair12345')
                page.locator('#accountLoginDialog button[type=submit]').click()
                expect(page.locator('#accountLoginDialog')).to_have_count(0)
                expect(page.locator('[data-note]')).to_have_value('登录失效时的草稿')
                synced()
                assert state()['notes'][qid]['text'] == '登录失效时的草稿'
                record('expired-session-keeps-draft-relogin-original-account-syncs')
                # Switch actual courses through settings; the fixed bank remains account-wide.
                before_course = state()
                page.locator('#appSettingsButton').click()
                page.locator('[data-settings-tab=services]').click()
                page.locator('[data-manage-courses]').click()
                expect(page.locator('#workspaceDialog')).to_be_visible()
                page.locator('#workspaceDialog [name=name]').fill('跨课程验证')
                page.locator('#workspaceDialog button[type=submit]').click()
                expect(page.locator('#workspaceDialog')).to_be_hidden()
                assert state()['statuses'] == before_course['statuses']
                assert state()['notes'] == before_course['notes']
                # This state-regression fixture deliberately shares its catalog with
                # the second course; production courses begin empty until upload.
                course_id = page.evaluate("JSON.parse(localStorage.getItem('xueya-copilot-workspace-v3')).activeId")
                bootstrap = context.request.get(base + '/api/platform/bootstrap').json()
                prepared = context.request.post(base + '/api/platform/courses',
                    headers={'X-Xueya-Token': bootstrap['token']}, data={'id':course_id,'name':'跨课程验证'})
                assert prepared.ok
                go('practice/hot100')
                action('clear-filters').first.click()
                page.locator('.practice-row').first.click()
                selected_id = current_id()
                page.locator('.practice-list-pane').evaluate('(el)=>el.scrollTop=450')
                page.wait_for_timeout(200)
                saved_scroll = page.locator('.practice-list-pane').evaluate('(el)=>el.scrollTop')
                page.reload()
                expect(page.locator('.practice-detail-head')).to_be_visible()
                assert current_id() == selected_id
                restored_scroll = page.locator('.practice-list-pane').evaluate('(el)=>el.scrollTop')
                assert abs(saved_scroll - restored_scroll) < 2
                action('random').click()
                random_id = current_id()
                action('next').click()
                assert current_id() != random_id
                assert page.evaluate("JSON.parse(localStorage.getItem('xueya-practice-v1:repairuser')).ui.mode") == 'random'
                record('cross-course-shared-state-list-scroll-restore-random-continues')
                # A second real account must not see the first account's state or drafts.
                other = browser.new_context()
                second = other.new_page()
                response = second.request.post(base + '/api/account/register', data={'username': 'seconduser', 'password': 'Second12345', 'confirmPassword': 'Second12345'})
                assert response.ok
                second.goto(base + '/#space/practice/hot100')
                expect(second.locator('.practice-row')).to_have_count(100)
                assert second.evaluate('window.XueyaAccountId') == 'seconduser'
                assert second.evaluate("localStorage.getItem('xueya-practice-v1:repairuser')") is None
                boot = second.request.get(base + '/api/platform/bootstrap').json()
                isolated = second.request.get(base + '/api/practice/state', headers={'X-Xueya-Token': boot['token']}).json()
                assert isolated['statuses'] == {} and isolated['notes'] == {}
                other.close()
                record('second-account-isolated-server-state-and-local-drafts')
                assert not errors, errors
                report = {'status': 'passed', 'paidApiCalls': 0, 'checks': checks, 'pageErrors': errors}
                (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            except BaseException:
                page.screenshot(path=str(output / 'failure.png'), full_page=True)
                (output / 'failure.json').write_text(json.dumps({'checks': checks, 'errors': errors, 'url': page.url}, ensure_ascii=False, indent=2), encoding='utf-8')
                raise
            finally:
                context.tracing.stop(path=str(output / 'trace.zip'))
                browser.close()
                server.should_exit = True
                thread.join(timeout=5)
                app.state.platform.db.close()


if __name__ == '__main__':
    main()
