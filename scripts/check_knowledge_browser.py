"""Actual Chrome acceptance: create/upload/parse/search/read/reload/course handoff.

Uses isolated storage and the normal host, with external RAG providers disabled.
Optional --materials imports a real private corpus into the temporary database.
"""
import argparse
import json
from pathlib import Path
import tempfile

from .check_learning_browser import Browser, server
from .import_knowledge_base import import_directory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--materials', type=Path)
    args = parser.parse_args()
    output = Path('test-results/knowledge-base/browser')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-knowledge-') as temporary:
        directory = Path(temporary)
        with server(directory) as (url, app):
            browser = Browser(directory)
            try:
                browser.call('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
                browser.call('Page.navigate', url=url+'/#space/knowledge')
                browser.wait('!!document.querySelector("#kbFiles") && !document.querySelector("#kbNotice").innerText.includes("加载")')
                browser.click('[data-kb=create]')
                browser.fill('#kbCreate [name=name]', '算法知识库验收')
                browser.fill('#kbCreate [name=description]', '验收课程，保留原课程')
                browser.click('#kbCreate button')
                browser.wait('document.querySelector("#kbBase option:checked")?.textContent === "算法知识库验收"')
                course_id = browser.evaluate('document.querySelector("#kbBase").value')
                path = directory/'week4 第3章_栈和队列.md'
                path.write_text('# 栈与队列\n栈遵循后进先出。队列遵循先进先出。\n顺序栈可以用数组实现。', encoding='utf-8')
                browser.file('#kbFiles', path)
                browser.wait('document.querySelector("#kbDocuments")?.innerText.includes("已解析，可检索")')
                browser.wait('document.querySelector("#kbChapter")?.innerText.includes("第3章")')
                # Standalone search was retired; lexical retrieval remains a backend contract.
                evidence = browser.evaluate("""(async()=>{const b=await(await fetch('/api/platform/bootstrap')).json();const r=await fetch('/api/platform/knowledge/search',{method:'POST',headers:{'Content-Type':'application/json','X-Xueya-Token':b.token},body:JSON.stringify({courseId:document.querySelector('#kbBase').value,query:'后进先出',mode:'lexical'})});return r.json();})()""")
                assert '后进先出' in json.dumps(evidence, ensure_ascii=False)
                browser.click('[data-kb=toggle-list]')
                browser.click('[data-kb=read]')
                browser.wait('document.querySelector("#kbDialog[open]")?.innerText.includes("后进先出")')
                browser.click('#kbDialog [data-kb=close]')
                browser.file('#kbFiles', path)
                browser.wait('document.querySelector("#kbNotice")?.innerText.includes("上传完成")')
                assert browser.evaluate('document.querySelectorAll(".kb-document").length') == 1
                assert browser.evaluate('document.querySelector("[data-kb=index]").disabled')
                browser.reload()
                browser.wait('document.querySelector("#kbBase")?.value === '+json.dumps(course_id)+' && !!document.querySelector(".kb-document")')
                browser.click('#kbDocuments [data-kb=chat]')
                browser.wait('location.hash==="#space/ask" && !!document.querySelector("#chatInput")')
                assert browser.evaluate('document.querySelector("#courseSelect").value') == course_id
                assert browser.evaluate('document.querySelector(".scope-picker").textContent.includes("栈和队列")')
                browser.evaluate('location.hash="space/knowledge"')
                browser.wait('!!document.querySelector(".kb-document")')
                browser.fill('#kbBase', 'course-default')
                browser.wait('document.querySelector("#kbBase")?.value === "course-default" && !document.querySelector(".kb-document")')
                browser.fill('#kbBase', course_id)
                browser.wait('!!document.querySelector(".kb-document")')
                checks = ['create', 'upload', 'parse', 'filename-chapter', 'lexical-search', 'citation-reader', 'duplicate-import', 'unconfigured-external-processing-disabled', 'reload', 'chat-course-handoff', 'course-isolation']
                if args.materials:
                    report = import_directory(args.materials, '数据结构与算法', url, output/'real-import.json')
                    assert report['status'] == 'passed', report['status']
                    browser.click('[data-kb=refresh]')
                    browser.wait('document.querySelector("#kbBase").innerText.includes("数据结构与算法")')
                    browser.fill('#kbBase', report['courseId'])
                    browser.wait('document.querySelectorAll(".kb-document").length === '+str(len(report['files'])))
                    browser.fill('#kbQuery', '哈夫曼')
                    browser.click('#kbSearch button')
                    browser.wait('!!document.querySelector(".kb-result")')
                    browser.click('[data-kb=source]')
                    browser.wait('document.querySelector("#kbDialog[open]")?.innerText.includes("实际第")')
                    browser.screenshot(output/'real-reader-desktop.png')
                    browser.click('#kbDialog [data-kb=close]')
                    checks += ['real-17-pptx-import', 'real-topic-search', 'real-slide-location']
                browser.screenshot(output/'desktop.png')
                browser.evaluate('document.querySelector(".kb-columns").scrollIntoView({block:"start"})')
                browser.screenshot(output/'documents-desktop.png')
                browser.evaluate('scrollTo(0,0)')
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                browser.screenshot(output/'mobile.png')
                browser.evaluate('scrollTo(0,0)')
                browser.evaluate('document.documentElement.dataset.theme="dark"')
                browser.screenshot(output/'mobile-dark.png')
                assert not browser.errors, browser.errors
                assert not app.state.platform.db.all('SELECT * FROM invocations'), 'Unexpected API invocation'
                checks += ['desktop', '390px', 'dark-mode', 'zero-api-invocations']
                (output/'report.json').write_text(json.dumps({'status': 'passed', 'paidApiCalls': 0, 'checks': checks}, ensure_ascii=False, indent=2), encoding='utf-8')
                print('Knowledge browser passed; '+str(len(checks))+' checks, paid calls: 0.')
            except BaseException:
                browser.screenshot(output/'failure.png')
                raise
            finally:
                browser.close()


if __name__ == '__main__':
    main()
