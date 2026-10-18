"""G1/G2 actual browser flows; temporary data, no live providers."""
import json
from pathlib import Path
import tempfile
from .check_learning_browser import Browser, server


def main():
    output = Path('test-results/workbench')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-workbench-') as temporary:
        directory = Path(temporary)
        with server(directory) as (url, app):
            browser = Browser(directory)
            try:
                browser.call('Page.navigate', url=url+'/#space/memory')
                browser.wait('!!document.querySelector("#cLearning [data-c-form]")')
                assert browser.evaluate('!!document.querySelector(".wb-legacy:not([open])")')
                assert not browser.evaluate('document.body.innerText.includes("打开本页进阶学习功能")')
                browser.click('#workbenchSettings')
                browser.wait('document.querySelectorAll(".wb-capabilities article").length === 7')
                browser.click('[data-wb=check]')
                browser.wait('document.querySelector("#toast").textContent.includes("没有发送网络请求")')
                browser.click('[data-wb=tasks]')
                browser.wait('document.querySelector("#workbenchBody").innerText.includes("实际 API 用量")')
                browser.click('[data-wb=close]')
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                browser.screenshot(output/'mobile.png')
                browser.call('Page.reload')
                browser.wait('!!document.querySelector("#workbenchTasks")')
                assert not browser.errors, browser.errors
                (output/'report.json').write_text(json.dumps({'status': 'passed', 'paidApiCalls': 0, 'checks': ['primary-learning', 'legacy-preserved', 'capabilities', 'free-check', 'task-usage', 'reload', 'mobile']}), encoding='utf-8')
                print('G1 browser passed: primary learning, legacy records, settings, free check, tasks/usage, reload and mobile. Paid calls: 0.')
            finally:
                browser.close()


if __name__ == '__main__':
    main()
