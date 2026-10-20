"""Real Chrome acceptance for C pages; isolated SQLite and controlled API only.

Run: python -m scripts.check_learning_browser
Uses Chrome DevTools via the small websockets test dependency, not a JS server.
"""
import base64
from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen, Request
import wave

import httpx
import uvicorn
from websockets.sync.client import connect
from backend.xueya.app import create_app
from backend.xueya.config import Config, ROOT
from backend.xueya.provider import MimoProvider
from backend.xueya.rag_http import install_rag
from backend.xueya.rag_service import RagService

sys.path.insert(0, str(ROOT/'tests/python'))
from test_learning_pages import upstream


@contextmanager
def server(directory, upstream_handler=None):
    config = Config(data_dir=directory/'data', api_key='controlled-test-only', model='mimo-v2.6-flash', base_url='https://controlled.invalid/v1')
    app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream_handler or upstream)))
    install_rag(app, service_factory=RagService)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    host = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    thread = threading.Thread(target=host.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if host.started:
                break
            time.sleep(.03)
        assert host.started
        yield f'http://127.0.0.1:{port}', app
    finally:
        host.should_exit = True
        thread.join(8)
        sock.close()
        assert not thread.is_alive()


class Browser:
    def __init__(self, directory):
        chrome = os.environ.get('CHROME_PATH', 'C:/Program Files/Google/Chrome/Application/chrome.exe')
        self.process = subprocess.Popen([chrome, '--headless=new', '--disable-gpu', '--no-first-run', '--disable-dev-shm-usage',
            '--remote-debugging-port=0', '--user-data-dir='+str(directory/'chrome'), 'about:blank'], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        file = directory/'chrome/DevToolsActivePort'
        for _ in range(200):
            if file.exists():
                break
            time.sleep(.04)
        port = int(file.read_text().splitlines()[0])
        tabs = json.load(urlopen(f'http://127.0.0.1:{port}/json/list', timeout=5))
        target = next(t for t in tabs if t['type'] == 'page')
        self.ws = connect(target['webSocketDebuggerUrl'], max_size=32*1024*1024, open_timeout=5)
        self.seq, self.errors = 0, []
        self.call('Runtime.enable')
        self.call('Page.enable')

    def call(self, method, **params):
        self.seq += 1
        key = self.seq
        self.ws.send(json.dumps({'id': key, 'method': method, 'params': params}))
        while True:
            result = json.loads(self.ws.recv(timeout=30))
            if result.get('method') == 'Runtime.exceptionThrown':
                self.errors.append(result['params']['exceptionDetails'])
            if result.get('id') == key:
                assert 'error' not in result, result
                return result.get('result', {})

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', expression=expression, returnByValue=True, awaitPromise=True)
        assert not result.get('exceptionDetails'), result
        return result.get('result', {}).get('value')

    def wait(self, expression, timeout=20):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            try:
                if self.evaluate(expression):
                    return
            except AssertionError as error:
                # CDP can briefly lose the old execution context during reload.
                # Retry only this protocol transition, never application errors.
                if '-32000' not in str(error) or not any(message in str(error) for message in ('Inspected target navigated or closed', 'Cannot find context', 'Execution context was destroyed')):
                    raise
            time.sleep(.1)
        raise AssertionError('Browser condition timed out: '+expression+'\n'+str(self.evaluate('document.body.innerText.slice(-4500)')))

    def click(self, selector):
        self.wait(f'(()=>{{const el=document.querySelector({json.dumps(selector)});if(!el||el.disabled||el.closest("dialog:not([open])"))return false;el.click();return true;}})()')

    def fill(self, selector, value):
        self.evaluate(f'''(()=>{{const el=document.querySelector({json.dumps(selector)});if(!el)throw Error('Missing field');el.value={json.dumps(str(value))};el.dispatchEvent(new Event('input',{{bubbles:true}}));el.dispatchEvent(new Event('change',{{bubbles:true}}));}})()''')

    def submit(self, name):
        self.evaluate(f'''(()=>{{const el=document.querySelector('form[data-c-form="{name}"]');for(let p=el.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;if(!el.checkValidity())throw Error('Invalid form: '+[...el.elements].filter(e=>e.willValidate&&!e.validity.valid).map(e=>e.name));el.requestSubmit();}})()''')
        self.wait('!document.querySelector("#cLearning .c-progress")')

    def route(self, view):
        self.evaluate(f'location.hash="space/{view}"')
        if view in ('overview','chat','library','cards'):
            selector={'overview':'[data-title-play]','chat':'#chatForm','library':'#libraryRows','cards':'#chapterNoteForm'}[view]
            self.wait(f'!!document.querySelector({json.dumps(selector)})')
            return
        form = {'practice': 'generate', 'memory': 'memory-preview', 'graph': 'concept-new', 'plan': 'plan-preview', 'cards': 'note-new', 'media': 'media-image'}.get(view)
        self.wait(f'!!document.querySelector("#cLearning [data-c-form={form}]")' if form else '!!document.querySelector("#cLearning [data-c-action=chapter]")')

    def file(self, selector, file):
        root = self.call('DOM.getDocument')['root']['nodeId']
        node = self.call('DOM.querySelector', nodeId=root, selector=selector)['nodeId']
        self.call('DOM.setFileInputFiles', nodeId=node, files=[str(file)])

    def screenshot(self, file):
        result = self.call('Page.captureScreenshot', format='png', captureBeyondViewport=False)
        file.write_bytes(base64.b64decode(result['data']))

    def reload(self):
        previous = self.evaluate('performance.timeOrigin')
        self.call('Page.reload')
        self.wait(f'performance.timeOrigin !== {previous} && document.readyState === "complete"')

    def close(self):
        try:
            self.ws.close()
        finally:
            if self.process.poll() is None:
                if os.name == 'nt':
                    # Only this test's isolated browser tree; Crashpad can retain
                    # a profile handle after terminating the parent alone.
                    subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=10, check=False)
                else:
                    self.process.terminate()
            self.process.wait(timeout=10)


def main():
    output = ROOT/'test-results/c-learning-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-c-browser-') as name:
        directory = Path(name)
        assert directory.resolve().parent == Path(tempfile.gettempdir()).resolve() and directory.name.startswith('xueya-c-browser-')
        with server(directory) as (url, app):
            with httpx.Client(base_url=url) as http:
                token = http.get('/api/platform/bootstrap').json()['token']
                headers = {'X-Xueya-Token': token, 'Idempotency-Key': 'browser-upload'}
                job = http.post('/api/platform/rag/upload?name=Trees.md', content=b'# Trees\nA tree consists of nodes and edges.', headers=headers).json()['job']
                for _ in range(300):
                    job = http.get('/api/platform/jobs/status?id='+job['id'], headers=headers).json()['job']
                    if job['status'] in ('succeeded', 'failed'):
                        break
                    time.sleep(.05)
                assert job['status'] == 'succeeded', job
            browser = Browser(directory)
            try:
                browser.call('Emulation.setDeviceMetricsOverride', width=1365, height=950, deviceScaleFactor=1, mobile=False)
                browser.call('Page.navigate', url=url+'/#space/chapters')
                browser.wait('!!document.querySelector("#cLearning [data-c-action=chapter]")')
                browser.click('[data-c-action=chapter]')
                browser.wait('!!document.querySelector("[data-c-action=run-preview]")', timeout=30)
                browser.click('[data-c-action=run-preview]')
                browser.wait('!!document.querySelector("#cLearningDialog[open]")')
                browser.click('[data-c-action=adopt]')
                browser.wait('document.querySelector("#cLearning")?.textContent.includes("已完成")', timeout=30)
                browser.reload()
                browser.wait('document.querySelector("#cLearning")?.innerText.includes("章节学习包")')
                print('C browser: real chapter job, explicit confirmation, reload persistence', flush=True)

                browser.route('practice')
                browser.submit('generate')
                browser.wait('!!document.querySelector("[data-c-form=question-review]")')
                browser.fill('[data-c-form=question-review] [name=reason]', '已核对原文与答案')
                browser.submit('question-review')
                browser.wait('!!document.querySelector("[name=questions]")')
                browser.submit('quiz-preview')
                browser.wait('!!document.querySelector("#cLearningDialog[open] [data-c-action=adopt]")')
                browser.click('#cLearningDialog [data-c-action=adopt]')
                browser.wait('!!document.querySelector("[data-c-action=take-quiz]")')
                browser.click('[data-c-action=take-quiz]')
                browser.wait('!!document.querySelector("[data-c-form=quiz-submit]")')
                browser.click('[data-c-form=quiz-submit] input[type=radio][value="1"]')
                browser.reload()
                browser.wait('!!document.querySelector("[data-c-form=quiz-submit]")')
                assert browser.evaluate('document.querySelectorAll("[data-c-form=quiz-submit] input[type=radio]")[1].checked')
                browser.submit('quiz-submit')
                browser.wait('!!document.querySelector("[data-c-form=diagnosis]")')
                browser.fill('[data-c-form=diagnosis] [name=reason]', '我重新核对了题干')
                browser.submit('diagnosis')
                browser.wait('document.querySelector("#cLearningDialog")?.innerText.includes("已确认错因")')
                browser.click('#cLearningDialog [data-c-action=close]')
                print('C browser: model candidates -> human review -> quiz -> scoring -> diagnosis correction', flush=True)

                browser.route('memory')
                browser.fill('[data-c-form=memory-preview] [name=prompt]', 'What is a tree?')
                browser.fill('[data-c-form=memory-preview] [name=answer]', 'Nodes and edges')
                source = browser.evaluate('document.querySelector("[data-c-form=memory-preview] [name=sourceId]").value')
                quote = app.state.platform.repo.read_source(app.state.platform.scope(), source)['quote']
                browser.fill('[data-c-form=memory-preview] [name=quote]', quote)
                browser.submit('memory-preview')
                browser.click('#cLearningDialog [data-c-action=adopt]')
                browser.wait('!!document.querySelector("[data-c-action=review-history]")')
                browser.click('[data-c-action=review-queue]')
                browser.wait('!!document.querySelector("[data-c-action=rate]")')
                browser.click('[data-c-action=rate][data-rating="3"]')
                browser.wait('!document.querySelector("#cLearning .c-progress")')
                browser.click('[data-c-action=review-history]')
                browser.wait('document.querySelector("#cLearningDialog")?.innerText.includes("py-fsrs")')
                browser.click('#cLearningDialog [data-c-action=close]')
                print('C browser: saved memory card, due queue, FSRS rating and durable review history', flush=True)

                browser.route('graph')
                browser.fill('[data-c-form=concept-new] [name=name]', 'Nodes')
                browser.fill('[data-c-form=concept-new] [name=quote]', quote)
                browser.submit('concept-new')
                browser.click('#cLearningDialog [data-c-action=adopt]')
                browser.wait('document.querySelector("#cLearning")?.innerText.includes("Nodes")')
                browser.route('plan')
                browser.submit('plan-preview')
                browser.click('#cLearningDialog [data-c-action=adopt]')
                browser.wait('!!document.querySelector("[data-c-action=replan]")')
                browser.click('[data-c-action=replan]')
                browser.submit('replan')
                browser.click('#cLearningDialog [data-c-action=adopt]')
                browser.wait('!document.querySelector("#cLearning .c-progress")')
                print('C browser: evidence-backed graph -> plan preview/adopt -> replan', flush=True)

                browser.route('cards')
                browser.fill('[data-c-form=note-new] [name=title]', 'Learning note')
                browser.fill('[data-c-form=note-new] [name=text]', 'My verified study note')
                browser.submit('note-new')
                browser.reload()
                browser.wait('!!document.querySelector("#cLearningDialog[open] [data-c-action=adopt]")')
                assert browser.evaluate('document.querySelector("#cLearningDialog").innerText.includes("My verified study note")')
                browser.click('#cLearningDialog [data-c-action=adopt]')
                browser.wait('document.querySelector("#cLearning")?.innerText.includes("Learning note")')
                browser.route('media')
                png = directory/'question.png'
                png.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jvWQAAAAASUVORK5CYII='))
                browser.file('[data-c-form=media-image] input[type=file]', png)
                browser.submit('media-image')
                browser.wait('!!document.querySelector("[data-c-form=recognition-confirm]")')
                browser.fill('[data-c-form=recognition-confirm] [name=correctedProblem]', '已人工校正的题干')
                browser.submit('recognition-confirm')
                browser.wait('!!document.querySelector("[data-c-form=photo-diagnose]")')
                wav = directory/'course.wav'
                with wave.open(str(wav), 'wb') as audio:
                    audio.setparams((1, 2, 8000, 8000, 'NONE', 'not compressed'))
                    audio.writeframes(b'\0\0'*8000)
                browser.file('[data-c-form=media-audio] input[type=file]', wav)
                browser.submit('media-audio')
                browser.wait('document.querySelector("#cLearningDialog")?.innerText.includes("核对转写文字")')
                browser.click('#cLearningDialog [data-c-action=close]')
                print('C browser: native image API, recognition correction, audio transcription, no billed calls', flush=True)

                browser.route('library')
                material = directory/'correction.md'
                material.write_text('🌿 '+'A test leaf converts sunlight into sugar. '*20, encoding='utf-8')
                browser.file('#fileInput', material)
                browser.wait('JSON.parse(localStorage.getItem("xueya-copilot-workspace-v3")).courses[0].data.documents.some(d=>d.name==="correction.md"&&d.chunks?.length)')
                doc_id = browser.evaluate('JSON.parse(localStorage.getItem("xueya-copilot-workspace-v3")).courses[0].data.documents.find(d=>d.name==="correction.md").id')
                previous = app.state.rag.document(app.state.platform.scope(), doc_id)
                original = app.state.rag.artifact(app.state.platform.scope(), previous)['text']
                first_chunk = previous['chunks'][0]
                browser.click('[data-document="'+doc_id+'"]')
                browser.click('[data-correct-source="'+doc_id+'"]')
                browser.fill('#workspaceForm [name=text]', 'A verified leaf converts sunlight into sugar.')
                browser.evaluate('document.querySelector("#workspaceForm").requestSubmit()')
                browser.wait('!document.querySelector("#workspaceDialog").open')
                current = app.state.rag.document(app.state.platform.scope(), doc_id)
                assert current['contentRevision'] == 2 and 'verified leaf' in current['chunks'][0]['quote']
                assert app.state.rag.artifact(app.state.platform.scope(), current)['text'] == original[:first_chunk['start']]+'A verified leaf converts sunlight into sugar.'+original[first_chunk['end']:]
                browser.click('#sourceDialog [data-close-dialog]')
                browser.route('chapters')
                browser.click('[data-c-action=refresh]')
                browser.wait('!!document.querySelector("[data-c-form=rag-job]")')
                assert browser.evaluate('!document.querySelector("[data-c-form=rag-job] [name=confirmed]").checked')
                browser.screenshot(output/'library-rag-desktop.png')
                print('B/A browser: default upload -> structured artifact -> correction -> new source revision; paid work requires confirmation', flush=True)

                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                browser.evaluate('document.querySelector("#cLearning").scrollIntoView()')
                assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                browser.screenshot(output/'media-mobile.png')
                browser.route('chapters')
                browser.evaluate('document.querySelector("#cLearning").scrollIntoView()')
                browser.screenshot(output/'overview-mobile.png')
                browser.call('Emulation.setDeviceMetricsOverride', width=1365, height=950, deviceScaleFactor=1, mobile=False)
                browser.evaluate('document.querySelector("#cLearning").scrollIntoView()')
                browser.screenshot(output/'overview-desktop.png')
                assert not browser.errors, browser.errors
                report = {'status': 'passed', 'runtimeErrors': 0, 'paidApiCalls': 0, 'checks': ['chapter-confirm-reload', 'question-review-quiz-correction', 'memory-fsrs', 'graph-plan-replan', 'notes', 'image-correction', 'audio-transcription', 'default-upload-and-source-correction', 'rag-config-and-confirmation', 'mobile-overflow']}
                (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                print('C browser acceptance passed: desktop/mobile, no runtime errors.', flush=True)
            except BaseException:
                browser.screenshot(output/'failure.png')
                raise
            finally:
                browser.close()


if __name__ == '__main__':
    main()
