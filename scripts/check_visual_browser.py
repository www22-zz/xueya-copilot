"""Actual Chrome visual-review preview/adopt/refresh/read flow; no model requests."""
import json
from pathlib import Path
import tempfile

import httpx

from .check_learning_browser import Browser, server
from .import_knowledge_base import checked


def main():
    # Reuse the authored CPU fixture. It is a transport/lifecycle test, not OCR quality.
    from test_visual_review import slides
    output = Path('test-results/visual-review/browser')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-visual-browser-') as temp:
        directory = Path(temp)
        with server(directory) as (url, app), httpx.Client(base_url=url, trust_env=False, timeout=30) as http:
            http.headers['X-Xueya-Token'] = checked(http.get('/api/platform/bootstrap'))['token']
            http.headers['Idempotency-Key'] = 'visual-browser-file'
            job = checked(http.post('/api/platform/knowledge/upload?name=Images.pptx', content=slides(True)))['job']
            import time
            for _ in range(200):
                job = checked(http.get('/api/platform/jobs/status', params={'id':job['id']}))['job']
                if job['status'] in ('succeeded','failed'):
                    break
                time.sleep(.05)
            assert job['status'] == 'succeeded', job
            doc = job['result']['documentId']
            pack = checked(http.get('/api/platform/knowledge/visual-pack', params={'documentId':doc}))['pack']
            review = {'documentId':doc,'version':pack['version'],'fileHash':pack['fileHash'],'reviewer':'assistant-in-session','pages':[
                {'page':1,'kind':'transcription','text':'图片转写：树结构的逻辑关系为双亲与孩子。','imageHashes':pack['pages'][0]['imageHashes']},
                {'page':2,'kind':'blank','text':'','imageHashes':[]}]}
            file = directory/'review.json'
            file.write_text(json.dumps(review,ensure_ascii=False),encoding='utf-8')
            browser = Browser(directory)
            try:
                browser.call('Emulation.setDeviceMetricsOverride',width=1365,height=950,deviceScaleFactor=1,mobile=False)
                browser.call('Page.navigate',url=url+'/#space/knowledge')
                browser.wait('document.querySelector("#kbDocuments")?.innerText.includes("2 页待识图")')
                browser.evaluate('document.querySelector(".kb-row-actions details").open=true')
                browser.click('[data-kb=visual-review]')
                browser.wait('!!document.querySelector("#kbVisualForm")')
                browser.file('#kbVisualFile',file)
                browser.wait('document.querySelector("#kbVisualForm textarea").value.includes("双亲")')
                browser.click('#kbVisualForm button')
                browser.wait('!!document.querySelector("[data-kb=visual-apply]")')
                assert app.state.rag.document(app.state.platform.scope(),doc)['contentRevision']==1
                browser.screenshot(output/'preview-desktop.png')
                browser.click('[data-kb=visual-apply]')
                browser.wait('!document.querySelector("#kbDialog").open && document.querySelector("#kbDocuments").innerText.includes("图片转写：1 页")')
                browser.reload()
                browser.wait('document.querySelector("#kbDocuments")?.innerText.includes("已核对 1 个空白页")')
                current = checked(http.get('/api/platform/knowledge/visual-pack', params={'documentId':doc}))['pack']
                hashes = current['pages'][2]['imageHashes']
                supplement = {**review,'version':current['version'],'pages':[{'page':3,'kind':'supplement','imageHashes':hashes,
                    'imageReviews':[{'imageHash':hashes[0],'kind':'diagram','text':'辅助图示：栈顶top的变化过程。','partial':True},
                                    {'imageHash':hashes[1],'kind':'decorative','text':'背景花纹不作为知识证据'}]}]}
                file.write_text(json.dumps(supplement,ensure_ascii=False),encoding='utf-8')
                browser.evaluate('document.querySelector(".kb-row-actions details").open=true')
                browser.click('[data-kb=visual-review]')
                browser.wait('!!document.querySelector("#kbVisualForm")')
                browser.file('#kbVisualFile',file)
                browser.wait('document.querySelector("#kbVisualForm textarea").value.includes("栈顶")')
                browser.click('#kbVisualForm button')
                browser.wait('document.querySelector("#kbDialog[open]")?.innerText.includes("追加图片补充")')
                browser.screenshot(output/'append-preview.png')
                browser.click('[data-kb=visual-apply]')
                browser.wait('!document.querySelector("#kbDialog").open && document.querySelector("#kbDocuments").innerText.includes("图片核查：2 个引用")')
                artifact=app.state.rag.artifact(app.state.platform.scope(),app.state.rag.document(app.state.platform.scope(),doc))
                assert '原有正文：栈后进先出。' in artifact['text'] and '背景花纹' not in artifact['text']
                browser.fill('#kbQuery','双亲')
                browser.click('#kbSearch button')
                browser.wait('!!document.querySelector(".kb-result")')
                assert '双亲' in browser.evaluate('document.querySelector("#kbResults").textContent')
                browser.click('[data-kb=source]')
                browser.wait('document.querySelector("#kbDialog[open]")?.innerText.includes("实际第 1 页")')
                browser.click('#kbDialog [data-kb=close]')
                browser.call('Emulation.setDeviceMetricsOverride',width=390,height=844,deviceScaleFactor=1,mobile=True)
                assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                browser.screenshot(output/'mobile.png')
                assert not browser.errors,browser.errors
                assert not app.state.platform.db.all('SELECT * FROM invocations')
                (output/'report.json').write_text(json.dumps({'status':'passed','modelRequests':0,'checks':['precise-page-warning','load-review-json','preview-before-write','explicit-adopt','rebuild-sources','reload','append-preview-and-adopt','preserve-existing-body','exclude-decoration-from-evidence','retrieve-transcribed-text','real-page-location','390px','no-provider-calls']},ensure_ascii=False,indent=2),encoding='utf-8')
                print('Visual browser passed: 13 checks; model requests: 0.')
            except BaseException:
                browser.screenshot(output/'failure.png')
                raise
            finally:
                browser.close()


if __name__=='__main__':
    main()
