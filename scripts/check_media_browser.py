"""G5 actual Chrome acceptance; original PCM/WebM and controlled upstream only."""
import base64
import io
import json
from pathlib import Path
import tempfile
import wave
import zipfile

import httpx

from scripts.check_learning_browser import Browser
from scripts.check_search_browser import server
from backend.agent.media_service import MediaService
from backend.agent.media_audio import wav_info


def pcm(seconds=1):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as clip:
        clip.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        clip.writeframes(b'\0\0' * 8000 * seconds)
    return buffer.getvalue()


def main():
    output = Path('test-results/g5-browser'); output.mkdir(parents=True, exist_ok=True)
    (output/'report.json').write_text(json.dumps({'passed':False,'status':'running'}),encoding='utf-8')
    calls = []
    class Speech:
        async def transcribe(self, value):
            calls.append('asr'); return {'text': '队列遵循先进先出。'}
        async def synthesize(self, value):
            calls.append('tts'); return {'data': base64.b64encode(pcm()).decode(), 'mime': 'audio/wav'}
    class Image:
        async def generate(self, value):
            calls.append('image')
            return {'content': json.dumps({'observations': ['画面有彩色方块'], 'uncertainties': [], 'inferences': [], 'recognizedProblem': '采样画面'})}
    with tempfile.TemporaryDirectory(prefix='xueya-g5-browser-') as temporary:
        folder = Path(temporary)
        with server(folder) as (base, app):
            app.state.learning_media_factory = lambda host, course: MediaService(app.state.learning.pages.resolve_media, image_model=Image(), asr=Speech(), tts=Speech())
            p = app.state.platform; scope = p.scope()
            p.repo.put(scope, 'source', 'g5-source', {'id':'g5-source','documentId':'g5-doc','title':'队列','quote':'队列遵循先进先出。','location':'原文第一段'})
            p.repo.put(scope, 'document', 'g5-doc', {'id':'g5-doc','name':'队列.md','chunks':[]})
            with httpx.Client(base_url=base) as client:
                headers = {'X-Xueya-Token':client.get('/api/platform/bootstrap').json()['token']}
                draft = client.post('/api/learning/card/preview',headers=headers,json={'id':'g5-card','prompt':'队列的次序？','answer':'先进先出','evidence':[{'sourceId':'g5-source','quote':'队列遵循先进先出。'}]}).json()['result']
                response = client.post('/api/learning/draft/adopt',headers=headers,json={'draftId':draft['draftId'],'confirmed':True,'operationId':'g5-card-adopt'})
                assert response.status_code == 200, response.text
            browser = Browser(folder)
            try:
                browser.call('Browser.setDownloadBehavior', behavior='allow', downloadPath=str(folder/'downloads'))
                browser.call('Page.navigate',url=base+'/#space/media')
                browser.wait('!!document.querySelector("#g5Workspace [data-g5-form=upload]")')
                audio = folder/'lecture.wav';audio.write_bytes(pcm(61))
                browser.file('[data-g5-form=upload] [name=file]',audio)
                browser.fill('[data-g5-form=upload] [name=seconds]',30)
                browser.evaluate('document.querySelector("[data-g5-form=upload]").requestSubmit()')
                browser.wait('!!document.querySelector("#g5Workspace [data-g5=transcribe]")')
                assert not calls
                browser.click('[data-g5=transcribe]')
                browser.wait('document.querySelector("#g5Dialog")?.getAttribute("aria-busy")=="false"')
                browser.evaluate('document.querySelector("#g5Dialog [name=allowApi]").checked=true;document.querySelector("#g5Dialog form").requestSubmit()')
                browser.wait('!![...document.querySelectorAll("#g5Workspace article")].find(el=>el.querySelector("strong")?.textContent==="片段转写"&&el.innerText.includes("已完成"))')
                browser.evaluate('[...document.querySelectorAll("#g5Workspace article")].find(el=>el.querySelector("strong")?.textContent==="片段转写").querySelector("[data-g5=run]").click()')
                browser.wait('document.querySelectorAll("[data-g5-transcript]").length===3')
                browser.evaluate('document.querySelectorAll("[data-g5-transcript] textarea").forEach(el=>el.value+="已听原件核对。");document.querySelectorAll("#g5Dialog input[type=checkbox]").forEach(el=>el.checked=true);document.querySelector("#g5Dialog form").requestSubmit()')
                browser.wait('document.querySelector("#toast")?.textContent.includes("逐段修订已保存")')
                browser.click('#g5Dialog [data-g5=import]')
                browser.wait('document.querySelector("#toast")?.textContent.includes("转写已导入资料")',timeout=35)
                browser.click('#g5Dialog [data-g5=close]')
                print('G5 browser: real WAV upload/segmentation -> confirmed ASR -> correction -> B import and media links.',flush=True)

                browser.evaluate('document.querySelector("[data-g5-form=script] [name=style]").value="dialogue";document.querySelector("[data-g5-form=script] [name=documents]").value="g5-doc";document.querySelector("[data-g5-form=script] [name=cards]").value="g5-card";document.querySelector("[data-g5-form=script]").requestSubmit()')
                browser.wait('!!document.querySelector("#g5Dialog [data-g5-form=script-save]")')
                browser.click('#g5Dialog [data-g5=source]')
                browser.wait('document.querySelector("#g5SourceDialog")?.innerText.includes("队列遵循先进先出")')
                browser.click('#g5SourceDialog [data-g5=source-close]')
                browser.wait('document.querySelector("#g5Dialog")?.getAttribute("aria-busy")=="false"')
                browser.evaluate('document.querySelectorAll("#g5Dialog input[type=checkbox]").forEach(el=>el.checked=true);document.querySelector("#g5Dialog form").requestSubmit()')
                browser.wait('!!document.querySelector("#g5Workspace [data-g5=synthesize]")')
                browser.click('#g5Workspace [data-g5=synthesize]')
                browser.wait('!!document.querySelector("#g5Dialog [name=allowApi]")')
                browser.wait('document.querySelector("#g5Dialog")?.getAttribute("aria-busy")=="false"')
                browser.evaluate('document.querySelector("#g5Dialog [name=allowApi]").checked=true;document.querySelector("#g5Dialog form").requestSubmit()')
                browser.wait('!![...document.querySelectorAll("#g5Workspace article")].find(el=>el.querySelector("strong")?.textContent==="复习音频"&&el.innerText.includes("已完成"))')
                browser.evaluate('[...document.querySelectorAll("#g5Workspace article")].find(el=>el.querySelector("strong")?.textContent==="复习音频").querySelector("[data-g5=run]").click()')
                browser.wait('!!document.querySelector("#g5Dialog [data-g5=export]")')
                browser.evaluate('document.querySelector("#g5Player").muted=true')
                browser.wait('document.querySelector("#g5Dialog")?.getAttribute("aria-busy")==="false"')
                point=browser.evaluate('(()=>{const el=document.querySelector("#g5Dialog [data-g5=play]");el.scrollIntoView({block:"center"});const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
                browser.call('Input.dispatchMouseEvent',type='mousePressed',button='left',clickCount=1,**point)
                browser.call('Input.dispatchMouseEvent',type='mouseReleased',button='left',clickCount=1,**point)
                browser.wait('document.querySelector("#g5Player")?.currentTime>0')
                card = p.repo.read(scope,'artifact',app.state.learning.repo.key('g5-card'))['value']
                assert not card['content']['reviewEvents']
                browser.click('#g5Dialog [data-g5=export]')
                for _ in range(200):
                    files = list((folder/'downloads').glob('*.zip'))
                    if files:break
                    import time;time.sleep(.05)
                assert files
                with zipfile.ZipFile(files[0]) as archive:assert 'review.wav' in archive.namelist() and 'captions.srt' in archive.namelist()
                browser.click('#g5Dialog [data-g5=rate][data-rating="3"]')
                browser.wait('document.querySelector("#toast")?.textContent.includes("明确提交的自评")')
                card = p.repo.read(scope,'artifact',app.state.learning.repo.key('g5-card'))['value']
                assert len(card['content']['reviewEvents'])==1
                browser.click('#g5Dialog [data-g5=close]')
                browser.reload();browser.wait('!!document.querySelector("#g5Workspace [data-g5=synthesize]")')
                print('G5 browser: reviewed dialogue -> TTS -> real playback/ZIP/subtitles -> explicit FSRS self-rating; reload persists.',flush=True)

                # Generate an actual WebM with browser CPU drawing/encoding, not fabricated video bytes.
                encoded = browser.evaluate('''(async()=>{const c=document.createElement('canvas');c.width=160;c.height=90;const stream=c.captureStream(8),r=new MediaRecorder(stream,{mimeType:'video/webm'}),parts=[];r.ondataavailable=e=>parts.push(e.data);const finished=new Promise(resolve=>r.onstop=resolve);r.start();const ctx=c.getContext('2d');for(let i=0;i<12;i++){ctx.fillStyle=i%2?'#e55':'#55e';ctx.fillRect(0,0,160,90);await new Promise(resolve=>setTimeout(resolve,100));}r.stop();await finished;stream.getTracks().forEach(t=>t.stop());return await new Promise(resolve=>{const f=new FileReader();f.onload=()=>resolve(f.result);f.readAsDataURL(new Blob(parts,{type:'video/webm'}));});})()''')
                video=folder/'sample.webm';video.write_bytes(base64.b64decode(encoded.split(',',1)[1]))
                browser.file('[data-g5-form=video] [name=file]',video)
                browser.fill('[data-g5-form=video] [name=count]',2)
                browser.evaluate('document.querySelector("[data-g5-form=video]").requestSubmit()')
                browser.wait('!!document.querySelector("#g5Workspace [data-g5=analyze]")',timeout=30)
                browser.click('[data-g5=analyze]')
                browser.wait('document.querySelector("#g5Dialog")?.getAttribute("aria-busy")=="false"')
                browser.evaluate('document.querySelector("#g5Dialog [name=allowApi]").checked=true;document.querySelector("#g5Dialog form").requestSubmit()')
                browser.wait('!![...document.querySelectorAll("#g5Workspace article")].find(el=>el.querySelector("strong")?.textContent==="采样画面分析"&&el.innerText.includes("已完成"))')
                browser.evaluate('[...document.querySelectorAll("#g5Workspace article")].find(el=>el.querySelector("strong")?.textContent==="采样画面分析").querySelector("[data-g5=run]").click()')
                browser.wait('document.querySelector("#g5Dialog").innerText.includes("2 个采样画面")')
                browser.click('#g5Dialog [data-g5=seek]')
                browser.wait('(()=>{const v=document.querySelector("#g5VideoPlayer");return v&&v.currentTime>0&&!v.seeking&&v.readyState>=2;})()')
                browser.screenshot(output/'desktop.png')
                browser.call('Emulation.setDeviceMetricsOverride',width=390,height=844,deviceScaleFactor=1,mobile=True)
                assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                browser.screenshot(output/'mobile.png')
                browser.click('#g5Dialog [data-g5=close]')
                # Exercise the actual recording UI/MediaRecorder/Web Audio conversion
                # with an oscillator stream; never request the user's real microphone.
                point=browser.evaluate('(()=>{const el=document.querySelector("#g5Open");el.scrollIntoView({block:"center"});const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
                browser.call('Input.dispatchMouseEvent',type='mousePressed',button='left',clickCount=1,**point)
                browser.call('Input.dispatchMouseEvent',type='mouseReleased',button='left',clickCount=1,**point)
                browser.evaluate('''(async()=>{const a=new AudioContext();await a.resume();const d=a.createMediaStreamDestination(),o=a.createOscillator();o.connect(d);o.start();const silence=a.createGain();silence.gain.value=0;o.connect(silence);silence.connect(a.destination);window.g5TestAudio=a;window.g5TestOscillator=o;navigator.mediaDevices.getUserMedia=async()=>d.stream;})()''')
                browser.click('#g5Workspace [data-g5=record]')
                browser.wait('!document.querySelector("[data-g5=record-stop]").disabled')
                browser.wait('window.g5TestAudio.state==="running"&&window.g5TestAudio.currentTime>1.3')
                browser.click('#g5Workspace [data-g5=record-stop]')
                browser.wait('document.querySelector("#g5Workspace")?.innerText.includes("课堂录音.webm")',timeout=30)
                originals=[r for r in app.state.learning.repo.all(scope.course_id) if r['kind']=='media' and r['content'].get('name')=='课堂录音.webm']
                assert originals and originals[-1]['content'].get('processingMediaId')
                source=originals[-1]['content'];derived=p.repo.read(scope,'artifact',app.state.learning.repo.key('media:'+source['processingMediaId']))['value']
                assert source['fileHash']!=derived['content']['fileHash']
                assert wav_info(p.files.read(derived['content']['fileHash']))['rate']==16000
                browser.evaluate('window.g5TestOscillator.stop();window.g5TestAudio.close()')
                assert not browser.errors,browser.errors
                (output/'report.json').write_text(json.dumps({'passed':True,'paidApiCalls':0,'controlledCalls':calls,
                    'checks':['PCM split','ASR correction/import','dialogue review','TTS/playback/export','explicit FSRS only','refresh','real WebM sampling/seek','390px','recording UI with controlled stream and preserved original']},ensure_ascii=False,indent=2),encoding='utf-8')
                print('G5 browser: actual WebM sampling -> bounded analysis -> real original seek; desktop/390px, no runtime errors.',flush=True)
            finally:browser.close()


if __name__=='__main__':main()
