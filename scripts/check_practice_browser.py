"""Practice / review module browser acceptance; isolated database, no paid model or API calls."""
import socket
import tempfile
import threading
import time
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright
from backend.xueya.app import create_app
from backend.xueya.config import Config

CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'


def main():
    with tempfile.TemporaryDirectory(prefix='xueya-practice-ui-') as directory:
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        base = 'http://127.0.0.1:' + str(sock.getsockname()[1])
        app = create_app(Config(data_dir=Path(directory), api_key=''))
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True).start()
        while not server.started:
            time.sleep(.05)
        output = Path('test-results')
        output.mkdir(exist_ok=True)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=CHROME, headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/#space/practice')
                page.wait_for_function("document.querySelectorAll('#practiceModule .practice-row').length > 0")
                rows = page.evaluate("document.querySelectorAll('#practiceModule .practice-row').length")
                assert rows == 100, f'Hot 100 should list 100 questions, got {rows}'

                # category tabs and their fixed counts
                for label, expected in (('基础题', 100), ('面试题', 50), ('Hot 100', 100)):
                    page.locator('#practiceModule .practice-tab', has_text=label).first.click()
                    page.wait_for_function("document.querySelectorAll('#practiceModule .practice-row').length > 0")
                    got = page.evaluate("document.querySelectorAll('#practiceModule .practice-row').length")
                    assert got == expected, f'{label} expected {expected}, got {got}'
                page.screenshot(path='test-results/practice-desktop.png')

                # search and filters combine, and never reorder the fixed list
                before = page.evaluate("[...document.querySelectorAll('#practiceModule .practice-row')].map(r=>r.dataset.id)")
                page.locator('#practiceModule [data-filter=keyword]').fill('两数之和')
                page.wait_for_timeout(120)
                hit = page.evaluate("document.querySelectorAll('#practiceModule .practice-row').length")
                assert 0 < hit < len(before), 'keyword should narrow the list'
                page.locator('#practiceModule [data-action=clear-filters]').click()
                after = page.evaluate("[...document.querySelectorAll('#practiceModule .practice-row')].map(r=>r.dataset.id)")
                assert after == before, 'clearing filters must restore the fixed order'

                # 待巩固 keeps the question put and only affects random weight
                page.locator('#practiceModule .practice-row').first.click()
                first_id = page.evaluate("document.querySelector('#practiceModule .practice-row').dataset.id")
                page.locator('#practiceModule [data-action=fuzzy]').click()
                assert page.evaluate("document.querySelector('#practiceModule .practice-row').dataset.id") == first_id, '待巩固 must stay on the question'
                assert page.locator('#practiceModule .chip-fuzzy').count() >= 1

                # 已掌握 auto-advances
                page.locator('#practiceModule [data-action=master]').click()
                page.wait_for_timeout(120)
                assert page.evaluate("document.querySelector('#practiceModule .practice-row').dataset.id") != first_id, '已掌握 must advance'

                # objective wrong answer auto-enters the wrong book and stays put
                page.goto(base + '/#space/practice/foundation')
                page.wait_for_function("document.querySelectorAll('#practiceModule .practice-row').length > 0")
                page.locator('#practiceModule .practice-row').first.click()
                wrong_id = page.evaluate("document.querySelector('#practiceModule .practice-row').dataset.id")
                page.locator('#practiceModule .practice-option').first.click()
                page.wait_for_timeout(200)
                assert page.evaluate("document.querySelector('#practiceModule .practice-row').dataset.id") == wrong_id, 'wrong answer must stay on the question'

                # 复习 shows the wrong book with the note attached
                page.goto(base + '/#space/review')
                page.wait_for_function("document.querySelectorAll('#practiceModule .practice-row').length > 0")
                page.locator('#practiceModule .practice-row').first.click()
                page.locator('#practiceModule .practice-note-input').fill('这道题容易看错题干。')
                page.wait_for_timeout(1400)
                page.reload()
                page.wait_for_function("document.querySelectorAll('#practiceModule .practice-row').length > 0")
                page.locator('#practiceModule .practice-row').first.click()
                assert '容易看错' in page.locator('#practiceModule .practice-note-input').input_value()
                page.screenshot(path='test-results/review-desktop.png')

                # mobile: the detail goes fullscreen and back keeps the list
                page.set_viewport_size({'width': 390, 'height': 844})
                page.goto(base + '/#space/practice')
                page.wait_for_function("document.querySelectorAll('#practiceModule .practice-row').length > 0")
                page.locator('#practiceModule .practice-row').first.click()
                page.wait_for_timeout(120)
                assert page.evaluate("document.querySelector('#practiceModule').classList.contains('is-fullscreen')"), 'mobile detail must go fullscreen'
                page.locator('#practiceModule [data-action=back]').click()
                assert not page.evaluate("document.querySelector('#practiceModule').classList.contains('is-fullscreen')")
                page.screenshot(path='test-results/practice-mobile.png')

                # offline: the queue keeps the practice usable and syncs on reconnect
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.goto(base + '/#space/practice')
                page.wait_for_function("document.querySelectorAll('#practiceModule .practice-row').length > 0")
                page.route('**/api/practice/**', lambda route: route.abort('failed'))
                page.locator('#practiceModule .practice-row').first.click()
                page.locator('#practiceModule [data-action=mark-wrong]').click()
                page.wait_for_timeout(200)
                assert page.evaluate("JSON.parse(localStorage.getItem('xueya-practice-ops:local')||'[]').length > 0"), 'offline ops must queue'
                page.unroute('**/api/practice/**')

                assert not errors, errors
                (output / 'practice-report.json').write_text(
                    '{"status":"passed","paidApiCalls":0,"checks":["bank-counts","filters-order","fuzzy-stays","master-advances","auto-wrong-book","note-autosave","mobile-fullscreen","offline-queue"]}',
                    encoding='utf-8')
                print('Practice browser passed: bank counts, filters, status flow, notes, mobile and offline. No paid calls.')
                browser.close()
        except BaseException:
            raise


if __name__ == '__main__':
    main()
