"""Actual Chrome acceptance: create/upload/parse/search/read/reload/course handoff.

Uses isolated storage and the normal host, with external RAG providers disabled.
Optional --materials imports a real private corpus into the temporary database.
"""
import argparse
import json
from pathlib import Path
import tempfile
import httpx

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
                browser.wait('!!document.querySelector("#kbUploadToggle") && !document.querySelector("#kbNotice").innerText.includes("加载")')
                browser.click('[data-kb=create]')
                browser.fill('#kbCreate [name=name]', '算法知识库验收')
                browser.fill('#kbCreate [name=description]', '验收课程，保留原课程')
                browser.click('#kbCreate button')
                browser.wait('document.querySelector("#courseSelect option:checked")?.textContent === "算法知识库验收"')
                course_id = browser.evaluate('document.querySelector("#courseSelect").value')
                path = directory/'week4 第3章_栈和队列.md'
                path.write_text('# 栈与队列\n栈遵循后进先出。队列遵循先进先出。\n顺序栈可以用数组实现。', encoding='utf-8')
                browser.click('#kbUploadToggle')
                invalid = directory/'unsupported.exe'
                invalid.write_bytes(b'not-a-supported-study-file')
                browser.file('#kbFiles', invalid)
                assert browser.evaluate('document.querySelector("#kbUploadStart").disabled')
                assert browser.evaluate('document.querySelector("#kbUploadMessage").textContent.includes("不支持")')
                browser.file('#kbFiles', path)
                assert browser.evaluate('document.querySelectorAll(".kb-document").length') == 0
                assert browser.evaluate('document.querySelector("#kbUploadSelection").textContent.includes("栈和队列.md")')
                browser.click('#kbUploadCancel')
                browser.click('#kbUploadToggle')
                assert browser.evaluate('document.querySelector("#kbUploadSelection").textContent.includes("栈和队列.md")')
                browser.click('[data-kb=upload-remove]')
                assert browser.evaluate('document.querySelector("#kbUploadStart").disabled')
                browser.file('#kbFiles', path)
                # A pre-send network failure keeps the selected file for retry.
                browser.evaluate("window.uploadTestFetch=window.fetch;window.fetch=(url,...args)=>String(url).includes('/knowledge/upload?')?Promise.reject(new TypeError('isolated test disconnect')):window.uploadTestFetch(url,...args)")
                browser.click('#kbUploadStart')
                browser.wait('document.querySelector("#kbUploadMessage")?.textContent.includes("上传未完成")')
                assert browser.evaluate('!document.querySelector("#kbUploadStart").disabled && document.querySelector("#kbUploadSelection").textContent.includes("栈和队列.md")')
                browser.evaluate('window.fetch=window.uploadTestFetch;delete window.uploadTestFetch')
                browser.evaluate("window.uploadTestFetch=window.fetch;window.fetch=(url,...args)=>String(url).includes('/knowledge/upload?')?new Promise(resolve=>{window.uploadTestRelease=()=>resolve(window.uploadTestFetch(url,...args))}):window.uploadTestFetch(url,...args)")
                browser.click('#kbUploadStart')
                browser.wait('typeof window.uploadTestRelease === "function"')
                browser.click('#kbUploadCancel')
                assert browser.evaluate('!document.querySelector("#kbUploadDialog[open]")')
                browser.click('#kbUploadToggle')
                assert browser.evaluate('document.querySelector("#kbUploadStart").disabled && document.querySelector("#kbUploadProgress").textContent.includes("正在上传")')
                browser.evaluate('window.uploadTestRelease()')
                browser.wait('document.querySelector("#kbUploadMessage")?.textContent.includes("已上传")')
                browser.evaluate('window.fetch=window.uploadTestFetch;delete window.uploadTestFetch;delete window.uploadTestRelease')
                browser.click('#kbUploadCancel')
                browser.wait('!!document.querySelector(".kb-document [data-kb=review]:not(:disabled)")')
                browser.click('[data-kb=review]')
                browser.wait('!!document.querySelector("#kbReviewConfirm")')
                browser.click('#kbReviewConfirm input[type=checkbox]')
                browser.click('#kbReviewConfirm button')
                browser.wait('!!document.querySelector(".kb-document [data-kb=chat]:not(:disabled)")')
                browser.wait('document.querySelector("#kbChapter")?.innerText.includes("第3章")')
                # Standalone search was retired; lexical retrieval remains a backend contract.
                evidence = browser.evaluate("""(async()=>{const b=await(await fetch('/api/platform/bootstrap')).json();const r=await fetch('/api/platform/knowledge/search',{method:'POST',headers:{'Content-Type':'application/json','X-Xueya-Token':b.token},body:JSON.stringify({courseId:document.querySelector('#courseSelect').value,query:'后进先出',mode:'lexical'})});return r.json();})()""")
                assert '后进先出' in json.dumps(evidence, ensure_ascii=False)
                # The personal file list is always visible.
                browser.click('[data-kb=read]')
                browser.wait('document.querySelector("#kbDialog[open]")?.innerText.includes("后进先出")')
                browser.click('#kbDialog [data-kb=close]')
                browser.click('#kbUploadToggle')
                browser.file('#kbFiles', path)
                browser.click('#kbUploadStart')
                browser.wait('document.querySelector("#kbUploadMessage")?.textContent.includes("已上传")')
                browser.click('#kbUploadCancel')
                browser.wait('document.querySelector("#kbNotice")?.innerText.includes("上传完成")')
                assert browser.evaluate('document.querySelectorAll(".kb-document").length') == 1
                assert browser.evaluate('document.querySelector("[data-kb=index]").disabled')
                browser.reload()
                browser.wait('document.querySelector("#courseSelect")?.value === '+json.dumps(course_id)+' && !!document.querySelector(".kb-document")')
                document_id = browser.evaluate('document.querySelector(".kb-document").dataset.documentId')
                browser.click('#kbDocuments [data-kb=chat]')
                browser.wait('location.hash==="#space/ask" && !!document.querySelector("#chatInput")')
                assert browser.evaluate('document.querySelector("#courseSelect").value') == course_id
                assert browser.evaluate('Object.keys(localStorage).filter(k=>k.includes('+json.dumps(course_id+':scope:')+')).some(k=>JSON.parse(localStorage.getItem(k)).includes('+json.dumps(document_id)+'))')
                browser.evaluate('location.hash="space/knowledge"')
                browser.wait('!!document.querySelector(".kb-document")')
                browser.fill('#courseSelect', 'course-default')
                browser.wait('document.querySelector("#courseSelect")?.value === "course-default" && !document.querySelector(".kb-document")')
                browser.fill('#courseSelect', course_id)
                browser.wait('!!document.querySelector(".kb-document")')
                checks = ['create', 'upload', 'parse', 'filename-chapter', 'lexical-search', 'citation-reader', 'duplicate-import', 'unconfigured-external-processing-disabled', 'reload', 'chat-course-handoff', 'course-isolation']
                if args.materials:
                    report = import_directory(args.materials, '数据结构与算法', url, output/'real-import.json')
                    assert report['status'] == 'passed', report['status']
                    browser.click('[data-kb=refresh]')
                    browser.wait('document.querySelector("#courseSelect").innerText.includes("数据结构与算法")')
                    browser.fill('#courseSelect', report['courseId'])
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
                browser.evaluate('document.querySelector(".lw-layout").scrollIntoView({block:"start"})')
                browser.screenshot(output/'documents-desktop.png')
                browser.evaluate('scrollTo(0,0)')
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                browser.screenshot(output/'mobile.png')
                browser.evaluate('scrollTo(0,0)')
                browser.evaluate('document.documentElement.dataset.theme="dark"')
                browser.screenshot(output/'mobile-dark.png')
                browser.click('[data-kb=delete]')
                browser.wait('!!document.querySelector("#kbDeleteConfirm")')
                assert browser.evaluate('document.querySelector("#kbDialog").textContent.includes("对应的向量索引将一同删除")')
                browser.screenshot(output/'delete-confirm-mobile.png')
                browser.click('#kbDeleteConfirm [data-kb=close]')
                assert browser.evaluate('document.querySelectorAll(".kb-document").length') == 1
                browser.click('[data-kb=delete]')
                browser.click('#kbDeleteConfirm button[type=submit]')
                browser.wait('!document.querySelector("#kbDialog[open]") && document.querySelectorAll(".kb-document").length === 0')
                assert browser.evaluate('document.querySelector("#lwScaleBody").textContent.includes("0")')
                browser.reload()
                browser.wait('!!document.querySelector("#kbUploadToggle") && document.querySelectorAll(".kb-document").length === 0')
                assert not browser.errors, browser.errors
                # Review confirmation can start the current teaching pipeline;
                # this fixture routes every text-model call to its local stub.
                assert isinstance(app.state.provider.transport, httpx.MockTransport)
                assert app.state.rag.embedding is None and app.state.rag.ocr is None and app.state.rag.rerank is None
                controlled = app.state.platform.db.one('SELECT count(*) AS n FROM invocations')['n']
                checks += ['desktop', '390px', 'dark-mode', 'zero-paid-api-calls']
                (output/'report.json').write_text(json.dumps({'status': 'passed', 'paidApiCalls': 0, 'controlledInvocations': controlled, 'checks': checks}, ensure_ascii=False, indent=2), encoding='utf-8')
                print('Knowledge browser passed; '+str(len(checks))+' checks, paid calls: 0.')
            except BaseException:
                browser.screenshot(output/'failure.png')
                raise
            finally:
                browser.close()


if __name__ == '__main__':
    main()
