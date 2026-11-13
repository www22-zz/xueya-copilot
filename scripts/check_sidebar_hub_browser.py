"""Check the learning sidebar hub on overview, ask and learning-center pages.

Uses a temporary account/database, a seeded local workspace, mocked learning-space
plan/today endpoints, and blocks every non-local browser request. Never calls a
model, never touches the user's browser profile.
"""
import hashlib
import json
import re
import socket
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn
from playwright.sync_api import sync_playwright, expect

from backend.xueya.app import create_app
from backend.xueya.config import Config
from .browser_runtime import browser_path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'test-results/sidebar-hub'
USERNAME = 'sidebarfixture'


class NoModel:
    async def generate(self, *args, **kwargs):
        raise AssertionError('Sidebar rendering must not call an AI service')


def today():
    return datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()


def plan_payload(primary_done=False):
    return {
        'ok': True,
        'plan': {
            'id': 'plan-sidebar',
            'revision': 3,
            'status': 'active',
            'title': '本周学习计划',
            'days': [
                {'date': today(), 'tasks': [
                    {'id': 'task-review', 'title': '复习二叉树遍历', 'minutes': 20,
                     'kind': 'study', 'completed': primary_done},
                    {'id': 'task-wrong', 'title': '错题重练：链表', 'minutes': 15,
                     'kind': 'review', 'completed': True},
                    {'id': 'task-read', 'title': '阅读第 4 章讲义', 'minutes': 25,
                     'kind': 'study', 'completed': True},
                ]},
                {'date': '2999-01-01', 'tasks': [
                    {'id': 'task-later', 'title': '未来任务', 'minutes': 10,
                     'kind': 'study', 'completed': False}]},
            ],
        },
    }


def today_payload():
    tasks = plan_payload()['plan']['days'][0]['tasks']
    return {
        'ok': True,
        'date': today(),
        'hasActivePlan': True,
        'planTitle': '本周学习计划',
        'todayTasks': tasks,
        'completedTasksCount': sum(1 for task in tasks if task['completed']),
        'totalTasksCount': len(tasks),
        'continueLearning': {
            'suggestion': '继续学习《数据结构与算法》或复习近期错题',
            'courseView': '#space/courses',
            'practiceView': '#space/practice',
            'reviewView': '#space/review',
        },
        'lastCourse': {
            'courseId': 'cs-ds-algo',
            'episodeId': 'ep-tree',
            'title': '数据结构 · 树与二叉树',
            'url': '#space/courses/cs-ds-algo/ep-tree',
            'seconds': 312,
            'completed': False,
        },
    }


def workspace_seed(data_owner):
    sessions = [
        {'id': 's1', 'title': '二叉搜索树复杂度复盘', 'createdAt': '2026-11-12T08:00:00Z',
         'messages': [
             {'id': 'm1', 'role': 'user', 'text': '二叉搜索树查找复杂度为什么是 O(log n)？'},
             {'id': 'm2', 'role': 'ai', 'text': '先看树的高度。', 'engine': '资料问答', 'sources': []},
         ]},
        {'id': 's2', 'title': '虚拟内存段页式地址转换', 'createdAt': '2026-11-12T09:00:00Z',
         'messages': [
             {'id': 'm3', 'role': 'user', 'text': '段页式地址转换过程？'},
         ]},
        {'id': 's3', 'title': '新的对话', 'createdAt': '2026-11-12T10:00:00Z', 'messages': []},
    ]
    return {
        'version': 3,
        'activeId': 'course-default',
        'courses': [{
            'id': 'course-default', 'name': '数据结构', 'archived': False,
            'data': {'documents': [], 'documentCount': 2, 'messages': [],
                     'sessions': sessions, 'sessionId': 's3'},
        }],
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    owner = 'account-' + hashlib.sha256(USERNAME.encode()).hexdigest()[:40]
    key = 'xueya-copilot-workspace-v3:' + owner
    seed = workspace_seed(owner)
    seed_script = (
        "try{localStorage.setItem(" + json.dumps(key) + "," +
        json.dumps(json.dumps(seed, ensure_ascii=False)) + ");}catch(e){}"
    )
    checks, errors, external, toggles = [], [], [], []
    with tempfile.TemporaryDirectory(prefix='xueya-sidebar-hub-') as directory:
        app = create_app(Config(root=ROOT, data_dir=Path(directory), api_key='',
                                auto_import_demo=False, preserve_legacy_data=True), provider=NoModel())
        sock = socket.socket(); sock.bind(('127.0.0.1', 0))
        base = f'http://127.0.0.1:{sock.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=3))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            assert server.started
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=browser_path(), headless=True)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})

                def local_only(route):
                    if route.request.url.startswith(base + '/'):
                        route.continue_()
                    else:
                        external.append(route.request.url)
                        route.abort()

                def today_route(route):
                    route.fulfill(status=200, content_type='application/json',
                                  body=json.dumps(today_payload(), ensure_ascii=False))

                def active_route(route):
                    route.fulfill(status=200, content_type='application/json',
                                  body=json.dumps(plan_payload(), ensure_ascii=False))

                def toggle_route(route):
                    data = {}
                    try:
                        data = json.loads(route.request.post_data or '{}')
                    except ValueError:
                        pass
                    toggles.append(data)
                    route.fulfill(status=200, content_type='application/json',
                                  body=json.dumps(plan_payload(primary_done=bool(data.get('completed'))),
                                                  ensure_ascii=False))

                context.route('**/*', local_only)
                context.route('**/api/learning/space/today', today_route)
                context.route('**/api/learning/space/plan/active', active_route)
                context.route('**/api/learning/space/plan/task/toggle', toggle_route)
                context.add_init_script(seed_script)
                reply = context.request.post(base + '/api/account/register', data={
                    'username': USERNAME, 'password': 'Fixture123', 'confirmPassword': 'Fixture123'})
                assert reply.ok
                page = context.new_page()
                page.set_default_timeout(15000)
                page.on('pageerror', lambda error: errors.append(str(error)))

                def assert_no_page_overflow():
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')

                # ---------- desktop overview ----------
                page.goto(base + '/#space/overview')
                expect(page.locator('.stitch-overview-view')).to_be_visible()
                expect(page.locator('#stitchSidebar')).to_be_visible()
                assert page.locator('#stitchSidebar').bounding_box()['width'] == 260
                assert page.locator('.stitch-main-content').bounding_box()['x'] == 260
                expect(page.locator('#stitchSpaceCard')).to_be_visible()
                expect(page.locator('#stitchSpaceName')).to_have_text('数据结构')
                assert '份资料' in page.locator('#stitchSpaceMeta').inner_text()
                expect(page.locator('#stitchResumeTitle')).to_have_text('数据结构 · 树与二叉树')
                assert page.locator('#stitchResumeLink').get_attribute('href') == '#space/courses/cs-ds-algo/ep-tree'
                checks.append('space-card-course-and-resume')

                expect(page.locator('#stitchTodaySection')).to_be_visible()
                expect(page.locator('#stitchTodayCount')).to_have_text('2/3')
                tasks = page.locator('#stitchTodayTasks .sidebar-task')
                expect(tasks).to_have_count(3)
                expect(tasks.first).to_contain_text('复习二叉树遍历')
                expect(tasks.first).to_contain_text('20 分钟')
                checks.append('today-plan-mocked-tasks')

                page.locator('#stitchTodayTasks input[data-sidebar-task]').first.check()
                expect(page.locator('#stitchTodayCount')).to_have_text('3/3')
                assert toggles, 'Task toggle must call the learning-space endpoint'
                assert toggles[0]['taskId'] == 'task-review'
                assert toggles[0]['completed'] is True
                assert toggles[0]['expectedRevision'] == 3
                assert toggles[0]['planId'] == 'plan-sidebar'
                checks.append('today-plan-toggle-sync')

                expect(page.locator('#stitchNavSection')).to_be_hidden()
                expect(page.locator('[data-ai-session-section]')).to_be_visible()
                sessions = page.locator('#stitchRecentSessions .session-item-btn')
                expect(sessions).to_have_count(2)
                expect(page.locator('#stitchRecentSessions')).to_contain_text('二叉搜索树复杂度复盘')
                expect(page.locator('.sidebar-session-more')).to_be_visible()
                checks.append('overview-recent-sessions-and-nav-hidden')

                page.locator('.sidebar-account').click()
                expect(page.locator('#appSettingsDialog')).to_be_visible()
                page.locator('[data-settings-close]').click()
                expect(page.locator('#appSettingsDialog')).to_be_hidden()
                checks.append('footer-account-opens-settings')

                page.locator('.sidebar-space-main').click()
                expect(page.locator('#workspaceDialog')).to_be_visible()
                expect(page.locator('#workspaceDialog')).to_contain_text('管理课程')
                page.locator('#workspaceDialog [data-close-dialog]').first.click()
                expect(page.locator('#workspaceDialog')).to_be_hidden()
                checks.append('space-card-opens-course-manager')

                page.screenshot(path=str(OUT / 'overview-desktop-dark.png'), full_page=True)
                page.evaluate("window.XueyaPreferences.applyTheme('light')")
                page.wait_for_timeout(120)
                page.screenshot(path=str(OUT / 'overview-desktop-light.png'), full_page=True)
                page.evaluate("window.XueyaPreferences.applyTheme('dark')")

                page.locator('#stitchSidebarCollapseBtn').click()
                expect(page.locator('#stitchSidebar')).to_have_class(re.compile(r'(?:^|\s)collapsed(?:\s|$)'))
                page.wait_for_function(
                    'document.querySelector("#stitchSidebar").getBoundingClientRect().width === 72')
                page.screenshot(path=str(OUT / 'overview-desktop-collapsed.png'), full_page=True)
                expect(page.locator('#stitchTodaySection')).to_be_hidden()
                page.locator('#stitchSidebarCollapseBtn').click()
                expect(page.locator('#stitchSidebar')).not_to_have_class(re.compile(r'(?:^|\s)collapsed(?:\s|$)'))
                page.wait_for_function(
                    'document.querySelector("#stitchSidebar").getBoundingClientRect().width === 260')
                checks.append('sidebar-collapse-rail')

                # ---------- ask + learning center ----------
                page.goto(base + '/#space/ask')
                expect(page.locator('.chat-empty-workbench')).to_be_visible()
                expect(page.locator('[data-ai-session-section]')).to_be_visible()
                expect(page.locator('#stitchNavSection')).to_be_hidden()
                expect(page.locator('.session-archived-summary')).to_be_visible()
                assert_no_page_overflow()
                page.screenshot(path=str(OUT / 'ask-desktop.png'), full_page=True)
                checks.append('ask-shows-full-session-list')

                page.goto(base + '/#space/materials')
                expect(page.locator('#spaceContent')).to_be_visible()
                expect(page.locator('#stitchNavSection')).to_be_visible()
                expect(page.locator('.learning-center-nav')).to_be_visible()
                expect(page.locator('#stitchTodaySection')).to_be_hidden()
                expect(page.locator('[data-ai-session-section]')).to_be_hidden()
                expect(page.locator('#stitchSpaceCard')).to_be_visible()
                assert_no_page_overflow()
                page.screenshot(path=str(OUT / 'learning-center-desktop.png'), full_page=True)
                checks.append('learning-center-shows-navigation')

                # ---------- tablet / mobile drawer ----------
                for width, height, shot in ((768, 900, 'overview-tablet'), (390, 844, 'overview-mobile')):
                    page.set_viewport_size({'width': width, 'height': height})
                    page.goto(base + '/#space/overview')
                    expect(page.locator('.stitch-overview-view')).to_be_visible()
                    page.locator('#stitchSidebarToggle').click()
                    expect(page.locator('#stitchSidebar')).to_have_class(re.compile(r'(?:^|\s)mobile-open(?:\s|$)'))
                    page.wait_for_function(
                        'document.querySelector("#stitchSidebar").getBoundingClientRect().left === 0')
                    assert page.locator('#stitchSidebar').bounding_box()['width'] == 280
                    expect(page.locator('#stitchSpaceCard')).to_be_visible()
                    expect(page.locator('#stitchTodaySection')).to_be_visible()
                    assert_no_page_overflow()
                    page.screenshot(path=str(OUT / f'{shot}-drawer.png'), full_page=False)
                    page.locator('#stitchSidebarToggle').click()
                    page.wait_for_function(
                        'document.querySelector("#stitchSidebar").getBoundingClientRect().right <= 1')
                    assert_no_page_overflow()
                checks.append('tablet-and-mobile-drawer')

                assert not external, external
                assert not errors, errors
                browser.close()
            result = {'status': 'passed', 'checks': checks, 'pageErrors': errors,
                      'externalRequests': external, 'paidApiCalls': 0,
                      'screenshots': sorted(path.name for path in OUT.glob('*.png'))}
            (OUT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False))
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
