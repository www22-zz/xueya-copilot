"""Shared Chrome regression helpers retained after retiring the old C pages.

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

def upstream(request):
    payload = json.loads(request.content)
    system = str(payload['messages'][0]['content'])
    if payload['model'] == 'mimo-v2.5-asr':
        content, audio = '转写后的课程内容', None
    elif payload['model'] == 'mimo-v2.5-tts':
        content, audio = '', {'data': base64.b64encode(b'RIFF-test-audio').decode()}
    elif 'observations' in system:
        content, audio = json.dumps({'observations': ['图中有一道题'], 'uncertainties': ['符号需核对'], 'inferences': [], 'recognizedProblem': '树由什么组成？'}, ensure_ascii=False), None
    elif '逐项结论' in system or '"claims"' in system:
        user = json.loads(payload['messages'][-1]['content'])
        sources = user.get('materials', user.get('sources', []))
        content, audio = json.dumps({'claims': [{'text': s['quote'], 'evidence': [{'sourceId': s['id'], 'quote': s['quote']}]} for s in sources], 'concepts': []}), None
    elif '候选题' in system:
        source = json.loads(payload['messages'][-1]['content'])['materials'][0]
        content, audio = json.dumps({'questions': [{'type': 'single', 'prompt': 'What is in a tree?', 'options': ['Nodes and edges', 'No nodes'], 'answer': 0,
            'explanation': 'According to the source.', 'evidenceQuote': source['quote'], 'sourceId': source['id'], 'conceptIds': [], 'difficulty': 'easy'}]}), None
    else:
        content, audio = '{}', None
    return httpx.Response(200, json={'model': payload['model'], 'choices': [{'message': {'content': content, **({'audio': audio} if audio else {})}, 'finish_reason': 'stop'}], 'usage': {'total_tokens': 10}})



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
        port = None
        for _ in range(200):
            try:
                port = int(file.read_text().splitlines()[0])
                break
            except (OSError, ValueError, IndexError):
                pass  # Chrome can briefly hold the new file open on Windows.
            time.sleep(.04)
        if port is None:
            self.process.terminate()
            self.process.wait(timeout=10)
            raise RuntimeError('Test browser did not publish its debugging port')
        tabs = json.load(urlopen(f'http://127.0.0.1:{port}/json/list', timeout=5))
        target = next(t for t in tabs if t['type'] == 'page')
        self.ws = connect(target['webSocketDebuggerUrl'], max_size=32*1024*1024, open_timeout=5)
        self.seq, self.errors = 0, []
        self.call('Runtime.enable')
        self.call('Page.enable')

    def call(self, method, **params):
        # Legacy regression fixtures are isolated. Authenticate before the first app navigation.
        if method == 'Page.navigate' and params.get('url', '').startswith('http://127.0.0.1:'):
            from urllib.parse import urlsplit
            from urllib.error import HTTPError
            parts = urlsplit(params['url'])
            origin = parts.scheme + '://' + parts.netloc
            if getattr(self, '_authenticated_origin', None) != origin:
                credentials = {'username': 'browser-fixture', 'password': 'Browser12345', 'confirmPassword': 'Browser12345'}
                for action in ('register', 'login'):
                    try:
                        response = urlopen(Request(origin+'/api/account/'+action, data=json.dumps(credentials).encode(), headers={'Content-Type':'application/json'}), timeout=10)
                        cookie = response.headers.get('Set-Cookie', '').split(';', 1)[0]
                        if cookie:
                            name, value = cookie.split('=', 1)
                            self.call('Network.setCookie', name=name, value=value, url=origin, httpOnly=True)
                        self._authenticated_origin = origin
                        break
                    except HTTPError:
                        continue
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



if __name__ == '__main__':
    from scripts.check_practice_browser import main
    main()
