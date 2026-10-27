"""Real-browser acceptance for verified streaming; temporary data, controlled upstream."""
import asyncio
import json
from pathlib import Path
import socket
import tempfile
import threading
import time

import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from backend.xueya.app import create_app
from backend.xueya.common import dumps
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider
from scripts.readonly_agent_fixture import planner_response


class HeldStream(httpx.AsyncByteStream):
    def __init__(self, source, release, text=None):
        self.source, self.release = source, release
        self.text = text or source['quote']

    async def __aiter__(self):
        source = self.source
        claim = {'text': self.text, 'kind': 'paraphrase', 'evidence': [{'sourceId': source['id'], 'quote': source['quote']}]}
        prefix = '{"claims":['+dumps(claim)
        yield ('data: '+dumps({'choices': [{'delta': {'content': prefix}}]})+'\n\n').encode()
        while not self.release.is_set():
            await asyncio.sleep(.01)
        tail = '],"answer":'+dumps(self.text)+',"sources":'+dumps([source['id']])+'}'
        yield ('data: '+dumps({'choices': [{'delta': {'content': tail}, 'finish_reason': 'stop'}]})+'\n\ndata: [DONE]\n\n').encode()


def main():
    with tempfile.TemporaryDirectory(prefix='xueya-fast-qa-') as directory:
        release, calls = threading.Event(), []
        async def upstream(request):
            payload = json.loads(request.content)
            calls.append(payload)
            if '证据核对员' in payload['messages'][0]['content']:
                batch = json.loads(payload['messages'][-1]['content'])['claims']
                assert len(batch) == 1 and '先进先出' in batch[0]['evidence'][0]['quote']
                verdict = dumps({'verdicts': [{'index': 0, 'status': 'supported'}]})
                return httpx.Response(200, json={'choices': [{'message': {'content': verdict}, 'finish_reason': 'stop'}]})
            planned = planner_response(payload)
            if planned is not None:
                return planned
            source = json.loads(payload['messages'][-1]['content'])['materials'][0]
            question = json.loads(payload['messages'][-1]['content'])['question']
            explanation = '可以把队列想成排队的队伍：先到的先离开，后来的人接在队伍末尾。' if '简单' in question else None
            return httpx.Response(200, stream=HeldStream(source, release, explanation), headers={'Content-Type': 'text/event-stream'})
        config = Config(data_dir=Path(directory), api_key='controlled-only')
        app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)))
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        base = 'http://127.0.0.1:'+str(sock.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            while not server.started:
                time.sleep(.02)
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                assert page.request.post(base+'/api/account/register', data={'username': 'qa-browser', 'password': 'Learning123', 'confirmPassword': 'Learning123'}).ok
                page.goto(base+'/#space/knowledge')
                page.get_by_role('button', name='上传资料', exact=True).click()
                page.locator('#kbFiles').set_input_files({'name': '队列.md', 'mimeType': 'text/markdown', 'buffer': '队列遵循先进先出。队尾入队，队首出队。'.encode()})
                page.get_by_role('button', name='查看资料', exact=True).click()
                page.get_by_role('heading', name='队列.md', exact=True).wait_for()
                page.wait_for_function("document.querySelector('.kb-status')?.textContent.includes('解析')")
                page.get_by_role('button', name='用于问答', exact=True).click()
                page.locator('#chatInput').fill('队列是什么？')
                page.get_by_role('button', name='发送问题', exact=True).click()
                try:
                    page.locator('.ai-message.loading-message .rich-content').filter(has_text='队列遵循先进先出').wait_for(timeout=8000)
                except Exception:
                    page.screenshot(path='test-results/fast-qa-failure.png', full_page=True)
                    print('QA browser errors:', errors)
                    print('QA chat:', page.locator('#spaceContent').inner_text()[-1600:])
                    print('Controlled model calls:', len(calls))
                    raise
                assert not release.is_set() and len(calls) == 1
                assert page.get_by_role('button', name='停止生成', exact=True).is_visible()
                release.set()
                page.locator('.ai-message:not(.loading-message) .rich-content').filter(has_text='队列遵循先进先出').wait_for()
                message = page.locator('.ai-message').last
                assert '秒' in message.locator('.message-meta').inner_text()
                message.locator('[data-citation]').first.click()
                page.locator('#sourceDialog').wait_for(state='visible')
                assert '队列遵循先进先出' in page.locator('#sourceDialog').inner_text()
                page.locator('#sourceDialog [data-close-dialog]').click()
                page.locator('#chatInput').fill('用简单的话解释队列')
                page.get_by_role('button', name='发送问题', exact=True).click()
                page.locator('.ai-message:not(.loading-message) .rich-content').filter(has_text='可以把队列想成排队的队伍').wait_for()
                assert '可以把队列想成排队的队伍' in page.locator('.ai-message').last.inner_text()
                page.locator('.ai-message').last.locator('[data-citation]').first.click()
                page.locator('#sourceDialog').wait_for(state='visible')
                assert '队列遵循先进先出' in page.locator('#sourceDialog').inner_text()
                page.locator('#sourceDialog [data-close-dialog]').click()
                page.locator('#chatInput').fill('跨章节综合分析队列')
                page.get_by_role('button', name='发送问题', exact=True).click()
                page.wait_for_function("document.querySelectorAll('.ai-message').length===3 && !document.querySelector('.loading-message')")
                stored = page.evaluate("JSON.parse(localStorage.getItem('xueya-copilot-state-v2')).messages.filter(m=>m.role==='ai')")
                assert stored[0]['timings']['route'] == 'fast-qa'
                assert stored[0]['timings']['modelCalls'] == 1
                assert stored[1]['timings']['route'] == 'fast-qa'
                assert stored[1]['timings']['modelCalls'] == 2
                assert stored[2]['timings']['route'] == 'agent'
                assert stored[2]['timings']['modelCalls'] > 1
                print('Browser verified:', [{'route': m['timings']['route'], 'modelCalls': m['timings']['modelCalls']} for m in stored])
                page.set_viewport_size({'width': 375, 'height': 812})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path='test-results/fast-qa-mobile.png', full_page=True)
                assert not errors, errors
                browser.close()
        finally:
            release.set()
            server.should_exit = True
            thread.join(10)
            sock.close()


if __name__ == '__main__':
    main()
