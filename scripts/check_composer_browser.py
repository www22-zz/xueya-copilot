"""Actual microphone/file composer acceptance; isolated host and controlled APIs only."""
import base64
import io
import json
from pathlib import Path
import tempfile
import time
import wave

import httpx

from scripts.check_learning_browser import Browser, server, upstream


def real_click(browser, selector):
    point=browser.evaluate('(()=>{const el=document.querySelector('+json.dumps(selector)+');el.scrollIntoView({block:"center",behavior:"instant"});const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
    browser.call('Input.dispatchMouseEvent',type='mousePressed',button='left',clickCount=1,**point)
    browser.call('Input.dispatchMouseEvent',type='mouseReleased',button='left',clickCount=1,**point)


STREAM = '''navigator.mediaDevices.getUserMedia=async()=>{
 const context=new AudioContext();await context.resume();const target=context.createMediaStreamDestination(),oscillator=context.createOscillator();
 oscillator.connect(target);oscillator.start();window.composerTest={context,oscillator,stream:target.stream};return target.stream;
};'''


def main():
    output=Path('test-results/composer-input');output.mkdir(parents=True,exist_ok=True)
    calls=[];control={'failAsr':False}
    def controlled(request):
        value=json.loads(request.content);calls.append(value)
        if value['model']=='mimo-v2.5-asr':
            audio=value['messages'][0]['content'][0]['input_audio']['data']
            assert audio.startswith('data:audio/wav;base64,')
            with wave.open(io.BytesIO(base64.b64decode(audio.split(',',1)[1]))) as clip:
                assert clip.getnchannels()==1 and clip.getsampwidth()==2 and clip.getframerate()==16000 and clip.getnframes()>0
            if control['failAsr']:
                control['failAsr']=False;return httpx.Response(503)
            return httpx.Response(200,json={'model':value['model'],'choices':[{'message':{'content':'请解释队列的先进先出。'},'finish_reason':'stop'}]})
        image=any(isinstance(m.get('content'),list) and any(p.get('type')=='image_url' for p in m['content']) for m in value['messages'])
        if value.get('stream') or image:
            assert value['model']=='mimo-v2.6-flash'
            sources=[]
            for message in value['messages']:
                try:
                    content=json.loads(message.get('content',''))
                    sources.extend(s for s in content.get('materials',[]) if isinstance(s,dict) and s.get('id'))
                except (TypeError,ValueError,AttributeError):pass
            answer=json.dumps({'answer':'队列遵循先进先出，这是受控测试回答。','sources':[sources[0]['id']] if sources else []},ensure_ascii=False)
            if not value.get('stream'):
                return httpx.Response(200,json={'model':value['model'],'choices':[{'message':{'content':answer},'finish_reason':'stop'}]})
            return httpx.Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':answer}}]})+'\n\ndata: [DONE]\n\n',headers={'Content-Type':'text/event-stream'})
        return upstream(request)

    with tempfile.TemporaryDirectory(prefix='xueya-composer-') as temporary:
        folder=Path(temporary)
        with server(folder) as (base,app):
            app.state.provider.transport=httpx.MockTransport(controlled)
            browser=Browser(folder)
            try:
                browser.call('Emulation.setDeviceMetricsOverride',width=1440,height=1000,deviceScaleFactor=1,mobile=False)
                browser.call('Page.navigate',url=base+'/#space/overview')
                browser.wait('!!document.querySelector(".composer-add")')
                assert browser.evaluate('document.querySelector(".composer-add").getAttribute("aria-label")==="添加文件或图片" && !!document.querySelector(".composer-mic svg rect")')
                browser.screenshot(output/'desktop-light.png')
                browser.evaluate('navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException("denied","NotAllowedError")}')
                real_click(browser,'[data-add-audio]')
                browser.wait('document.querySelector("[data-voice-status]")?.textContent.includes("允许麦克风")')
                assert not calls
                browser.click('[data-cancel-voice]')
                browser.evaluate(STREAM)
                browser.fill('#chatInput','原有草稿。')
                real_click(browser,'[data-add-audio]')
                browser.wait('document.querySelector(".composer-mic").getAttribute("aria-pressed")==="true"')
                browser.wait('window.composerTest.context.currentTime>.5')
                assert browser.evaluate('document.querySelector("#chatForm .send-button").disabled && document.querySelector("#courseSelect").disabled')
                browser.screenshot(output/'recording.png')
                real_click(browser,'[data-add-audio]')
                browser.wait('document.querySelector("#chatInput")?.value.includes("请解释队列")')
                assert [c['model'] for c in calls]==['mimo-v2.5-asr'], 'ASR must not auto-call LLM'
                assert browser.evaluate('document.querySelector("#chatInput").value.startsWith("原有草稿。") && !window.composerTest.stream.active')
                browser.fill('#chatInput','请解释队列的先进先出，并给出例子。')
                real_click(browser,'#chatForm .send-button')
                browser.wait('document.querySelector("#chatThread")?.innerText.includes("受控测试回答")')
                browser.wait('!document.querySelector("#chatForm .stop-button")')
                assert calls[-1]['model']=='mimo-v2.6-flash'
                assert '并给出例子' in json.dumps(calls[-1],ensure_ascii=False)
                browser.evaluate('window.composerTest.oscillator.stop();window.composerTest.context.close()')
                before=len(calls)
                browser.evaluate(STREAM);real_click(browser,'[data-add-audio]')
                browser.wait('document.querySelector(".composer-mic").getAttribute("aria-pressed")==="true"')
                browser.click('[data-cancel-voice]')
                browser.wait('!document.querySelector("[data-voice-status]")')
                assert len(calls)==before and browser.evaluate('!window.composerTest.stream.active')
                browser.evaluate('window.composerTest.oscillator.stop();window.composerTest.context.close()')
                # Leaving the page releases tracks and never posts the abandoned recording.
                browser.evaluate(STREAM);real_click(browser,'[data-add-audio]')
                browser.wait('document.querySelector(".composer-mic").getAttribute("aria-pressed")==="true"')
                browser.evaluate('location.hash="space/library"')
                browser.wait('!!document.querySelector("#libraryRows") && !window.composerTest.stream.active')
                assert len(calls)==before
                browser.evaluate('window.composerTest.oscillator.stop();window.composerTest.context.close();location.hash="space/chat"')
                browser.wait('!!document.querySelector(".composer-mic") && !document.querySelector("#chatForm .send-button").disabled')
                # A permission prompt resolved after cancellation must also release its stream.
                browser.evaluate('navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>window.composerLateGrant=resolve)')
                real_click(browser,'[data-add-audio]')
                browser.wait('document.querySelector("[data-voice-status]")?.textContent.includes("允许浏览器")')
                browser.click('[data-cancel-voice]')
                browser.evaluate('window.lateAudio=new AudioContext();window.lateStream=window.lateAudio.createMediaStreamDestination().stream;window.composerLateGrant(window.lateStream)')
                browser.wait('!window.lateStream.active');browser.evaluate('window.lateAudio.close()')
                assert len(calls)==before
                # One failed request stays failed; retry requires an explicit click.
                control['failAsr']=True;browser.evaluate(STREAM);real_click(browser,'[data-add-audio]')
                browser.wait('document.querySelector(".composer-mic").getAttribute("aria-pressed")==="true"')
                browser.wait('window.composerTest.context.currentTime>.5');real_click(browser,'[data-add-audio]')
                browser.wait('!!document.querySelector("[data-retry-voice]")')
                before=len(calls);time.sleep(.5);assert len(calls)==before
                browser.click('[data-retry-voice]')
                browser.wait('document.querySelector("#chatInput")?.value.includes("请解释队列")')
                assert len(calls)==before+1
                browser.evaluate('window.composerTest.oscillator.stop();window.composerTest.context.close()')
                browser.fill('#chatInput','')

                browser.call('Page.setInterceptFileChooserDialog',enabled=True)
                browser.evaluate('document.querySelector("#imageInput").addEventListener("click",()=>window.pickerOpened=true)')
                real_click(browser,'.composer-add');browser.wait('window.pickerOpened===true')
                lecture=folder/'队列附件.md';lecture.write_text('# 队列\n队列遵循先进先出，先入队的元素先出队。',encoding='utf-8')
                browser.file('#imageInput',lecture)
                browser.wait('document.querySelector(".attachment-list")?.innerText.includes("队列附件.md")')
                browser.fill('#chatInput','根据附件解释队列的顺序。');real_click(browser,'#chatForm .send-button')
                browser.wait('!document.querySelector("#chatForm .stop-button") && !document.querySelector("[data-remove-image]")')
                docs=app.state.platform.repo.list(app.state.platform.scope(),'document')['items']
                assert any(d['name']=='队列附件.md' for d in docs)
                assert browser.evaluate('document.querySelector("#chatThread").innerText.includes("受控测试回答")')
                assert browser.evaluate('document.querySelectorAll("#chatThread .citation-chip").length>0'), 'Attached document must remain a real citation'
                picture=folder/'picture.png';picture.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jR3sAAAAASUVORK5CYII='))
                browser.file('#imageInput',picture);browser.wait('!!document.querySelector(".attachment-list img")')
                browser.click('[data-remove-image]')
                # Use native ClipboardEvent/DataTransfer without touching the user's OS clipboard.
                image_data=base64.b64encode(picture.read_bytes()).decode()
                browser.fill('#chatInput','前后')
                browser.evaluate('document.querySelector("#chatInput").setSelectionRange(1,1)')
                paste=r'''(()=>{const data=new DataTransfer();data.items.add(new File([Uint8Array.from(atob(IMAGE),x=>x.charCodeAt(0))],'粘贴图片.png',{type:'image/png'}));if(TEXT)data.setData('text/plain',TEXT);const event=new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true});document.querySelector('#chatInput').dispatchEvent(event);return event.defaultPrevented;})()'''
                assert browser.evaluate(paste.replace('IMAGE',json.dumps(image_data)).replace('TEXT',json.dumps('中间')))
                browser.wait('document.querySelectorAll(".attachment-list img").length===1')
                assert browser.evaluate('document.querySelector("#chatInput").value==="前中间后" && document.activeElement.id==="chatInput" && document.querySelector("#chatInput").selectionStart===3')
                browser.click('[data-remove-image]')
                # A plain-text paste remains the browser's responsibility.
                assert browser.evaluate('(()=>{const data=new DataTransfer();data.setData("text/plain","普通文字");const event=new ClipboardEvent("paste",{clipboardData:data,bubbles:true,cancelable:true});document.querySelector("#chatInput").dispatchEvent(event);return !event.defaultPrevented;})()')
                browser.fill('#chatInput','粘贴的图片里是什么？')
                assert browser.evaluate(paste.replace('IMAGE',json.dumps(image_data)).replace('TEXT','""'))
                browser.wait('document.querySelectorAll(".attachment-list img").length===1')
                browser.click('#chatForm .send-button')
                browser.wait('!document.querySelector("#chatForm .stop-button") && !document.querySelector(".attachment-list img")')
                assert any(any(isinstance(m.get('content'),list) and any(p.get('type')=='image_url' for p in m['content']) for m in c['messages']) for c in calls), 'Pasted image must reach the image conversation'
                for theme in ('light','dark'):
                    browser.evaluate('window.XueyaPreferences.applyTheme('+json.dumps(theme)+')')
                    browser.screenshot(output/f'desktop-{theme}-chat.png')
                    browser.call('Emulation.setDeviceMetricsOverride',width=390,height=844,deviceScaleFactor=1,mobile=True)
                    assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    browser.evaluate('document.querySelector("#chatForm").scrollIntoView({block:"center",behavior:"instant"})')
                    browser.wait('(()=>{const r=document.querySelector("#chatForm .composer-bottom").getBoundingClientRect();return r.top>70&&r.bottom<innerHeight;})()')
                    browser.wait('!document.querySelector("#toast").classList.contains("show")')
                    browser.screenshot(output/f'mobile-{theme}.png')
                    browser.call('Emulation.setDeviceMetricsOverride',width=1440,height=1000,deviceScaleFactor=1,mobile=False)
                assert not browser.errors,browser.errors
                (output/'report.json').write_text(json.dumps({'passed':True,'paidApiCalls':0,'models':[c['model'] for c in calls],'checks':['plus-picker','permission-denied','actual-MediaRecorder-PCM16k-mono','ASR-only-before-send','edit-then-LLM','cancel-stops-tracks','navigation-stops-recording','late-permission-cancel','explicit-retry','document-upload-and-real-citation','image-preview-remove','paste-image-and-mixed-text-caret','plain-text-paste-default','pasted-image-reaches-provider','390px-light-dark']},ensure_ascii=False,indent=2),encoding='utf-8')
                print('Composer browser passed: files/images, recording/PCM/ASR, editable draft then LLM, permission/cancel/retry and mobile themes; no paid APIs.')
            except BaseException:
                browser.screenshot(output/'failure.png');raise
            finally:browser.close()


if __name__=='__main__':main()
