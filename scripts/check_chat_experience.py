"""Real browser acceptance for home, compact navigation, image and voice chat."""
import base64
import json
from pathlib import Path
import tempfile
import wave

import httpx
from .check_learning_browser import Browser, server, upstream


def controlled(request):
    payload = json.loads(request.content)
    image = any(isinstance(m.get('content'), list) and any(p.get('type') == 'image_url' for p in m['content']) for m in payload.get('messages', []))
    if image or payload.get('stream'):
        answer = json.dumps({'answer': '图片显示一个三角形。' if image else '已根据你核对的语音回答：三角形有三条边。', 'sources': []}, ensure_ascii=False)
        frame = {'choices': [{'delta': {'content': answer}}]}
        return httpx.Response(200, text='data: '+json.dumps(frame)+'\n\ndata: [DONE]\n\n', headers={'Content-Type': 'text/event-stream'})
    return upstream(request)


def main():
    output = Path('test-results/chat-experience')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-chat-experience-') as temporary:
        directory = Path(temporary)
        with server(directory, controlled) as (url, app):
            browser = Browser(directory)
            try:
                browser.call('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
                browser.call('Page.navigate', url=url+'/#home')
                browser.wait('!!document.querySelector("#knowledgeCanvas") && !document.querySelector("#homePage").hidden')
                browser.screenshot(output/'globe-home.png')
                browser.route('overview')
                assert browser.evaluate('!document.querySelector("#cLearning")')
                browser.wait('!!document.querySelector("[data-title-play]") && !!document.querySelector("#workspaceMore")')
                browser.evaluate('(()=>{const el=document.querySelector("[data-title-play]");const r=el.getBoundingClientRect();el.dispatchEvent(new PointerEvent("pointermove",{bubbles:true,clientX:r.left+70,clientY:r.top+30}));})()')
                browser.wait('getComputedStyle(document.querySelector(".title-lens")).opacity === "1"')
                browser.screenshot(output/'title-desktop.png')
                assert browser.evaluate('document.querySelectorAll(".workspace-main > .space-nav > a").length === 6')
                assert browser.evaluate('(()=>{const links=[...document.querySelectorAll(".space-nav>a")];return links.every(el=>Math.abs(el.getBoundingClientRect().top-links[0].getBoundingClientRect().top)<2);})()')
                assert browser.evaluate('document.querySelector("#coursePicker").getBoundingClientRect().bottom < document.querySelector(".space-nav").getBoundingClientRect().top')
                assert browser.evaluate('!!document.querySelector("#workspaceServices #workbenchSettings") && !document.querySelector("#workspaceMore #workbenchSettings") && document.querySelector("[data-view=memory]").nextElementSibling.id === "workspaceMore"')
                browser.click('#workspaceMore > summary')
                browser.wait('document.querySelector("#workspaceMore").open')
                assert browser.evaluate('(()=>{const el=document.querySelector("#workspaceMore [data-view=chapters]"),r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));})()'), 'Menu hidden behind content'
                browser.screenshot(output/'more-menu.png')
                browser.call('Input.dispatchKeyEvent', type='keyDown', key='Escape')
                browser.wait('!document.querySelector("#workspaceMore").open')
                browser.click('#workspaceMore > summary')
                browser.click('.space-nav [data-view=cards]')
                browser.wait('location.hash.includes("cards") && !!document.querySelector("#chapterNoteForm")')
                browser.route('chat')
                assert browser.evaluate('!document.querySelector("#cLearning")')
                # Valid one-pixel PNG; provider responses are controlled.
                picture = directory/'figure.png'
                picture.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jR3sAAAAASUVORK5CYII='))
                browser.file('#imageInput', picture)
                browser.wait('document.querySelectorAll(".attachment-list img").length === 1')
                browser.fill('#chatInput', '这张图里有什么？')
                browser.click('#chatForm .send-button')
                browser.wait('document.querySelector("#chatThread").innerText.includes("三角形")')
                browser.wait('!document.querySelector("#chatForm .stop-button")')
                audio = directory/'question.wav'
                with wave.open(str(audio), 'wb') as sound:
                    sound.setnchannels(1)
                    sound.setsampwidth(2)
                    sound.setframerate(16000)
                    sound.writeframes(b'\x00\x00'*3200)
                browser.file('#audioInput', audio)
                browser.wait('!!document.querySelector(".attachment-list audio")')
                browser.fill('#chatInput', '')
                browser.click('#chatForm .send-button')
                browser.wait('document.querySelector("#voiceTranscriptDialog")?.open')
                browser.fill('#voiceTranscriptDialog textarea', '什么是三角形？')
                browser.click('#voiceTranscriptDialog button[type=submit]')
                browser.wait('document.querySelector("#chatThread").innerText.includes("三条边")')
                browser.wait('!document.querySelector("#chatForm .stop-button")')
                browser.screenshot(output/'attachments-chat.png')
                browser.reload()
                browser.wait('document.querySelector("#chatThread")?.innerText.includes("三条边")')
                assert browser.evaluate('document.querySelector("#chatThread").innerText.includes("已核对的语音文字")')
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                browser.wait('document.documentElement.scrollWidth <= innerWidth+1')
                browser.click('#appSettingsButton')
                browser.click('[data-settings-tab=services]')
                browser.wait('document.querySelector("#appSettingsDialog").open')
                assert browser.evaluate('(()=>{const el=document.querySelector("#workspaceServices #workbenchSettings"),r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));})()')
                browser.screenshot(output/'mobile-services.png')
                browser.call('Input.dispatchKeyEvent', type='keyDown', key='Escape')
                browser.wait('!document.querySelector("#appSettingsDialog").open')
                browser.click('.space-nav [data-view="library"]')
                browser.wait('location.hash.includes("library") && !!document.querySelector("#libraryRows")')
                assert browser.evaluate('document.querySelectorAll("#spaceContent [data-upload]").length === 1 && !document.querySelector("#libraryWorkspace [data-lib=tasks]") && !document.querySelector("[data-lib-form=files]")')
                assert browser.evaluate('(()=>{const el=document.querySelector("[data-upload]"),r=el.getBoundingClientRect();return r.width>0 && !el.closest("details:not([open])");})()')
                browser.screenshot(output/'library-simple-empty.png')
                lecture=directory/'课程上传验证.md'
                lecture.write_text('# 栈与队列\n栈遵循后进先出，队列遵循先进先出。',encoding='utf-8')
                browser.file('#fileInput', lecture)
                browser.wait('document.querySelector("#libraryRows")?.innerText.includes("课程上传验证.md") && document.querySelector("#libraryRows").innerText.includes("已解析")')
                browser.click('#libraryRows [data-lib=read]')
                browser.wait('document.querySelector("#libraryReader")?.open && document.querySelector("#readerBlocks").innerText.includes("后进先出")')
                browser.click('#libraryReader [data-lib=close]')
                browser.screenshot(output/'library-simple-uploaded.png')
                assert browser.evaluate('!document.querySelector("#cLearning") && !document.querySelector(".experience-study-tools")')
                browser.click('#workspaceMore > summary')
                browser.click('#workspaceMore [data-view=chapters]')
                browser.wait('location.hash.includes("chapters") && !!document.querySelector("#cLearning [data-c-action=chapter]")')
                browser.click('[data-c-action=chapter]')
                browser.wait('!!document.querySelector("[data-c-action=run-preview]")',timeout=30)
                browser.click('[data-c-action=run-preview]')
                browser.wait('!!document.querySelector("#cLearningDialog[open]")')
                browser.click('[data-c-action=adopt]')
                browser.wait('document.querySelector("#cLearning")?.textContent.includes("已完成")',timeout=30)
                browser.reload()
                browser.wait('document.querySelector("#cLearning")?.innerText.includes("章节学习包")')
                browser.screenshot(output/'chapters-mobile.png')
                browser.wait('document.documentElement.scrollWidth <= innerWidth+1')
                browser.screenshot(output/'mobile-chat.png')
                assert browser.evaluate('getComputedStyle(document.querySelector("#workspaceMore>summary")).fontWeight === "650"')
                assert browser.evaluate('!document.querySelector("#workspaceMore #g3Entry") && !document.querySelector(".space-top-right #searchTrigger")')
                browser.call('Emulation.setDeviceMetricsOverride',width=1440,height=1000,deviceScaleFactor=1,mobile=False)
                browser.click('#coursePicker > summary')
                browser.wait('document.querySelector("#coursePicker").open')
                browser.screenshot(output/'course-picker.png')
                browser.click('#coursePicker [data-course-option]')
                browser.click('#appSettingsButton')
                browser.click('[data-settings-tab=general]')
                browser.click('[data-theme-choice=dark]')
                browser.wait('document.documentElement.dataset.theme === "dark"')
                browser.screenshot(output/'settings-dark.png')
                browser.click('[data-settings-close]')
                browser.reload()
                browser.wait('!!document.querySelector("#cLearning [data-c-action=chapter]")')
                assert browser.evaluate('document.documentElement.dataset.theme === "dark"')
                browser.screenshot(output/'chapters-dark.png')
                browser.click('#appSettingsButton')
                browser.click('[data-settings-tab=general]')
                browser.click('[data-theme-choice=light]')
                browser.click('[data-settings-tab=account]')
                browser.wait('!!document.querySelector("[data-account-action=setup]")')
                browser.fill('[data-account-action=setup] [name=username]','test-shared-team')
                browser.fill('[data-account-action=setup] [name=password]','controlled-team-password')
                browser.click('[data-account-action=setup] button')
                browser.wait('!!document.querySelector("[data-account-logout]")')
                browser.click('[data-account-logout]')
                browser.wait('document.querySelector("#accountLoginDialog")?.open')
                assert browser.evaluate('(async()=> (await fetch("/api/platform/bootstrap")).status === 401)()')
                browser.fill('[data-account-action=login] [name=password]','controlled-team-password')
                browser.click('[data-account-action=login] button')
                browser.wait('!!document.querySelector("#cLearning [data-c-action=chapter]") && !document.querySelector("#accountLoginDialog")')
                browser.screenshot(output/'team-login-restored.png')
                assert not browser.errors, browser.errors
                (output/'report.json').write_text(json.dumps({'status': 'passed', 'paidApiCalls': 0,
                    'checks': ['globe-home', 'compact-header-more-escape', 'six-main-sections', 'title-pointer-effect', 'image-in-chat', 'voice-transcribe-confirm-chat', 'refresh-history', '390px-no-overflow','no-duplicated-chapter-panel','chapter-menu-confirm-reload','single-library-upload-read','course-picker','theme-persist','settings-mobile','more-active','shared-account-logout-login']}, indent=2), encoding='utf-8')
                print('Chat experience browser passed: globe, menu, title, image/voice conversation, refresh and mobile. No paid calls.')
            except BaseException:
                browser.screenshot(output/'failure.png')
                raise
            finally:
                browser.close()


if __name__ == '__main__':
    main()
