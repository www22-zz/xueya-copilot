"""Chrome acceptance for conversation actions and speech, using an isolated mock upstream."""
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import wave

import httpx
import uvicorn
from playwright.sync_api import sync_playwright, expect

from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider


def main():
    output = Path('test-results/workspace-updates')
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, speech_requests = [], [], []
    wav = io.BytesIO()
    with wave.open(wav, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b'\0\0' * 800)
    encoded = base64.b64encode(wav.getvalue()).decode()

    async def upstream(request):
        payload = json.loads(request.content)
        if payload['model'] == 'mimo-v2.5-tts':
            speech_requests.append(payload)
            await asyncio.sleep(.3)
            return httpx.Response(200, json={'choices': [{'message': {'audio': {'data': encoded}}, 'finish_reason': 'stop'}]})
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"受控回答"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')

    with tempfile.TemporaryDirectory(prefix='xueya-workspace-updates-', ignore_cleanup_errors=True) as directory:
        config = Config(data_dir=Path(directory), api_key='controlled-only')
        app = create_app(config, provider=MimoProvider(config, transport=httpx.MockTransport(upstream)))
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        base = 'http://127.0.0.1:' + str(sock.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started:
            assert time.monotonic() < deadline
            time.sleep(.05)
        with sync_playwright() as playwright:
            chrome=next((str(p) for p in (Path(os.environ.get('CHROME_PATH','C:/Program Files/Google/Chrome/Application/chrome.exe')),Path(os.environ.get('LOCALAPPDATA',''))/'Google/Chrome/Application/chrome.exe') if p.is_file()),None)
            browser = playwright.chromium.launch(executable_path=chrome,
                                                  headless=True, args=['--autoplay-policy=no-user-gesture-required'])
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            messages = [{'id': 'user-one', 'role': 'user', 'text': '解释队列'},
                        {'id': 'answer-one', 'role': 'ai', 'text': '队列是先进先出的线性表。\n\n从队尾加入，从队首离开。', 'engine': '受控回答', 'sources': []}]
            seed = {'documents': [], 'feedback': [], 'sessionId': 'one', 'sessions': [
                {'id': 'one', 'title': '解释队列', 'messages': messages}, {'id': 'two', 'title': '第二个对话', 'messages': []}]}
            context.add_init_script("if(!localStorage.getItem('xueya-copilot-workspace-v3'))localStorage.setItem('xueya-copilot-state-v2'," + json.dumps(json.dumps(seed, ensure_ascii=False)) + ");")
            page = context.new_page()
            page.set_default_timeout(15000)
            page.on('pageerror', lambda error: errors.append(str(error)))

            def menu(session):
                row = page.locator('.session-item-row').filter(has=page.locator('[data-session="' + session + '"]'))
                row.hover()
                row.locator('[data-session-menu]').click()

            try:
                assert context.request.post(base + '/api/account/register', data={
                    'username': 'workspaceuser', 'password': 'Workspace123', 'confirmPassword': 'Workspace123'}).ok
                page.goto(base + '/#space/ask')
                expect(page.locator('.session-item-btn')).to_have_count(2)
                menu('one')
                page.locator('[data-pin-session="one"]').click()
                expect(page.locator('[title="已置顶"]')).to_have_count(1)
                menu('one')
                page.locator('[data-rename-session="one"]').click()
                page.locator('#workspaceForm [name=title]').fill('保留的自定义标题')
                page.locator('#workspaceForm [type=submit]').click()
                expect(page.locator('#workspaceDialog')).not_to_be_visible()
                expect(page.locator('[data-session="one"]')).to_contain_text('保留的自定义标题')
                page.reload()
                expect(page.locator('[data-session="one"]')).to_contain_text('保留的自定义标题')
                checks.append('pin-and-rename-persist-after-reload')

                page.locator('.ai-message').hover()
                page.locator('[data-branch="1"]').click()
                expect(page.locator('.session-item-btn')).to_have_count(3)
                active = page.locator('.session-item-btn.active')
                expect(active).to_contain_text('分支')
                branch = active.get_attribute('data-session')
                page.reload()
                expect(page.locator('.session-item-btn.active')).to_contain_text('分支')
                menu(branch)
                page.locator('.session-dropdown-menu [data-archive-session]').click()
                expect(page.locator('.session-archived-summary')).to_contain_text('(1)')
                page.locator('.session-archived-summary').click()
                menu(branch)
                page.locator('[data-delete-session]').click()
                page.locator('#workspaceForm [type=submit]').click()
                expect(page.locator('.session-item-btn')).to_have_count(2)
                expect(page.locator('.ai-message')).to_have_count(1)
                checks.append('branch-history-archive-and-confirmed-delete')

                page.evaluate("""()=>{const p=document.querySelector('.ai-message .rich-content p');const r=document.createRange();r.selectNodeContents(p);const s=getSelection();s.removeAllRanges();s.addRange(r);document.dispatchEvent(new Event('selectionchange'));}""")
                expect(page.locator('#selectionTooltip')).to_be_visible()
                page.locator('#selectionTooltip [data-action=followup]').click()
                expect(page.locator('#chatInput')).to_have_value('关于「队列是先进先出的线性表。」：')
                checks.append('selected-text-followup')

                page.locator('.ai-message').hover()
                page.locator('[data-tts-read="1"]').click()
                page.wait_for_function('window.XueyaTTS.getStatus()==="playing" || document.querySelector("#toast").textContent.includes("不支持")')
                page.wait_for_function('window.XueyaTTS.getStatus()==="idle"')
                assert len(speech_requests) == 1
                page.evaluate("window.__latePlayback=0;window.XueyaTTS.subscribe(s=>{if(s==='playing')window.__latePlayback++});void window.XueyaTTS.speak('待取消的朗读')")
                page.wait_for_function('window.XueyaTTS.getStatus()==="loading"')
                page.evaluate('window.XueyaTTS.stop()')
                page.wait_for_timeout(600)
                assert page.evaluate('window.__latePlayback===0 && window.XueyaTTS.getStatus()==="idle"')
                checks.append('tracked-tts-and-stopped-request-cannot-play-later')

                page.locator('[data-toggle-sidebar]').click()
                page.wait_for_function('document.body.classList.contains("sidebar-collapsed")')
                page.reload()
                page.wait_for_function('document.body.classList.contains("sidebar-collapsed")')
                page.locator('[data-toggle-sidebar]').click()
                page.wait_for_function('!document.body.classList.contains("sidebar-collapsed")')
                page.locator('.ai-message').scroll_into_view_if_needed()
                expect(page.locator('.ai-message')).to_be_visible()
                page.wait_for_timeout(350)
                page.screenshot(path=str(output / 'desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                page.locator('[data-history-open]').click()
                page.wait_for_function('document.body.classList.contains("history-drawer-open")')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(output / 'mobile.png'), full_page=True)
                page.locator('[data-history-close]').first.click()
                page.wait_for_function('!document.body.classList.contains("history-drawer-open")')
                checks.append('sidebar-collapse-restore-and-mobile-drawer')

                page.goto(base + '/#space/overview')
                page.locator('[data-daily-checkin]').click()
                expect(page.locator('[data-daily-checkin]')).to_contain_text('已打卡')
                page.reload()
                expect(page.locator('[data-daily-checkin]')).to_contain_text('已打卡')
                checks.append('daily-checkin-persists')
                assert not errors, errors
                result = {'status': 'passed', 'checks': checks, 'pageErrors': errors, 'paidApiCalls': 0}
                (output / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps(result, ensure_ascii=False), flush=True)
            except BaseException:
                page.screenshot(path=str(output / 'failure.png'), full_page=True)
                (output / 'failure.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False), encoding='utf-8')
                raise
            finally:
                browser.close()
                server.should_exit = True
                thread.join(timeout=5)


if __name__ == '__main__':
    main()
