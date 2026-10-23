"""Sent image lifecycle: pending, preview, failure and refresh. No real API calls."""
import asyncio
import json
from pathlib import Path
import struct
import tempfile
import time
import zlib

import httpx

from scripts.check_learning_browser import Browser, server


def picture(color):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows=b''.join(b'\0'+bytes(color if y<40 else (240,243,250))*320 for y in range(180))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',320,180,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')


def main():
    output=Path('test-results/sent-images');output.mkdir(parents=True,exist_ok=True)
    control={'hold':True,'fail':False};calls=[]
    async def upstream(request):
        value=json.loads(request.content);calls.append(value)
        for _ in range(300):
            if not control['hold']:break
            await asyncio.sleep(.05)
        if control['fail']:return httpx.Response(503)
        answer=json.dumps({'answer':'受控图文回答，已收到图片。','sources':[]},ensure_ascii=False)
        return httpx.Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':answer}}]})+'\n\ndata: [DONE]\n\n',headers={'Content-Type':'text/event-stream'})
    with tempfile.TemporaryDirectory(prefix='xueya-sent-images-') as temporary:
        directory=Path(temporary)
        with server(directory, upstream) as (base,app):
            browser=Browser(directory)
            def files(paths):
                root=browser.call('DOM.getDocument')['root']['nodeId']
                node=browser.call('DOM.querySelector',nodeId=root,selector='#imageInput')['nodeId']
                browser.call('DOM.setFileInputFiles',nodeId=node,files=[str(p) for p in paths])
            try:
                browser.call('Emulation.setDeviceMetricsOverride',width=1440,height=1000,deviceScaleFactor=1,mobile=False)
                browser.call('Page.navigate',url=base+'/#space/overview')
                browser.wait('!!document.querySelector("#imageInput")')
                first=directory/'image1.png';first.write_bytes(picture((75,90,210)))
                second=directory/'课程截图.png';second.write_bytes(picture((55,150,120)))
                files([first,second]);browser.wait('document.querySelectorAll(".attachment-list img").length===2')
                browser.fill('#chatInput','请看看这两张图片。');browser.click('#chatForm .send-button')
                browser.wait('document.querySelectorAll("#chatThread .sent-image-thumb img").length===2')
                browser.wait('[...document.querySelectorAll("[data-sent-image]")].every(i=>i.complete&&i.naturalWidth===320)')
                assert browser.evaluate('!!document.querySelector(".stop-button") && document.querySelectorAll(".attachment-list img").length===0')
                assert browser.evaluate('document.querySelector(".sent-image-thumb").title==="image1.png" && !document.querySelector(".user-message").innerText.includes("附件：")')
                browser.evaluate('document.querySelector(".sent-image-gallery").scrollIntoView({block:"center",behavior:"instant"})')
                browser.screenshot(output/'pending-images.png')
                browser.click('.sent-image-thumb')
                browser.wait('document.querySelector("#messageImageDialog")?.open && document.querySelector("#messageImageDialog img").naturalWidth===320')
                assert browser.evaluate('document.querySelector("#messageImageDialog strong").textContent==="image1.png"')
                browser.screenshot(output/'enlarged.png')
                browser.call('Input.dispatchKeyEvent',type='keyDown',key='Escape')
                browser.wait('!document.querySelector("#messageImageDialog").open')
                control['hold']=False
                browser.wait('!document.querySelector(".stop-button") && document.querySelector("#chatThread").innerText.includes("已收到图片")')
                assert len(calls)==1
                session=browser.evaluate('document.querySelector("#chatThread").dataset.sessionId')
                saved=browser.evaluate('JSON.stringify(JSON.parse(localStorage.getItem("xueya-copilot-state-v2")).messages)')
                assert 'chat-image:' in saved and 'blob:' not in saved and 'data:image' not in saved
                browser.reload()
                browser.wait('document.querySelectorAll("[data-sent-image]").length===2 && [...document.querySelectorAll("[data-sent-image]")].every(i=>i.complete&&i.naturalWidth===320)')
                browser.click('.sent-image-thumb');browser.wait('document.querySelector("#messageImageDialog")?.open')
                browser.click('[data-close-message-image]')
                browser.click('[data-new-session]');browser.wait('!document.querySelector("[data-sent-image]")')
                browser.click('[data-session="'+session+'"]')
                browser.wait('document.querySelectorAll("[data-sent-image]").length===2')
                # Failure does not put a sent attachment back into the composer.
                control['fail']=True;files([first]);browser.wait('document.querySelectorAll(".attachment-list img").length===1')
                browser.fill('#chatInput','这张图是什么？');browser.click('#chatForm .send-button')
                browser.wait('!document.querySelector(".stop-button") && document.querySelector("#chatThread").innerText.includes("回答未完成")')
                assert browser.evaluate('document.querySelectorAll("[data-sent-image]").length===3 && !document.querySelector(".attachment-list img")')
                for theme in ('light','dark'):
                    browser.evaluate('window.XueyaPreferences.applyTheme('+json.dumps(theme)+')')
                    browser.call('Emulation.setDeviceMetricsOverride',width=390,height=844,deviceScaleFactor=1,mobile=True)
                    assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    browser.click('.sent-image-thumb');browser.wait('document.querySelector("#messageImageDialog")?.open')
                    assert browser.evaluate('document.querySelector("#messageImageDialog").getBoundingClientRect().width<=innerWidth')
                    browser.screenshot(output/f'mobile-{theme}.png');browser.click('[data-close-message-image]')
                assert not browser.errors,browser.errors
                (output/'report.json').write_text(json.dumps({'passed':True,'paidApiCalls':0,'checks':['immediate-send-transfer','visible-while-pending','filename-tooltip','enlarge-and-Escape','cache-separate-from-message-JSON','refresh-restores-images','session-isolation','failure-keeps-sent-image','390px-light-dark']},indent=2),encoding='utf-8')
                print('Sent image browser passed: immediate transfer, thumbnails/title/enlarge, refresh/session/failure and mobile. No paid calls.')
            except BaseException:
                browser.screenshot(output/'failure.png');raise
            finally:
                control['hold']=False;browser.close()


if __name__=='__main__':main()
