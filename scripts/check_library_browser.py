"""Real G2 import/read/organize/reuse UI, with a controlled public-page response."""
import json
from pathlib import Path
import tempfile
import wave
from unittest.mock import patch
from .check_learning_browser import Browser, server


def main():
    output = Path('test-results/library-workspace')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-library-') as temporary:
        directory = Path(temporary)
        snapshot = lambda url: {'text': '# Public lecture\nA stack uses last-in-first-out order.', 'title': 'Web lecture', 'originalUrl': url, 'finalUrl': url}
        with patch('backend.xueya.library_http.fetch_snapshot', snapshot), server(directory) as (url, app):
            browser = Browser(directory)
            try:
                browser.call('Page.navigate', url=url+'/#space/library')
                browser.wait('!!document.querySelector("[data-lib-form=text]")')
                browser.evaluate('(()=>{for(let p=document.querySelector("[data-lib-form=text]").parentElement;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;})()')
                browser.fill('[data-lib-form=text] [name=title]', 'My lecture')
                browser.fill('[data-lib-form=text] [name=chapter]', 'Chapter 1')
                browser.fill('[data-lib-form=text] [name=text]', '# Chapter 1\nA stack uses last-in-first-out order.\nA queue uses first-in-first-out order.')
                browser.click('[data-lib-form=text] button')
                browser.wait('document.querySelector("#libraryRows")?.innerText.includes("My lecture")')
                browser.click('#libraryRows [data-lib=read]')
                browser.wait('document.querySelector("#readerBlocks")?.innerText.includes("last-in-first-out")')
                browser.fill('#readerFind', 'stack')
                assert browser.evaluate('!!document.querySelector("#readerBlocks mark")')
                browser.screenshot(output/'reader.png')
                browser.click('#libraryReader [data-lib=close]')
                browser.evaluate('(()=>{for(let p=document.querySelector("[data-lib-form=url]").parentElement;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;})()')
                browser.fill('[data-lib-form=url] [name=url]', 'https://example.org/lecture')
                browser.evaluate('document.querySelector("[data-lib-form=url] [name=confirmed]").checked=true')
                browser.click('[data-lib-form=url] button')
                browser.wait('document.querySelector("#libraryRows")?.innerText.includes("Web lecture")')
                audio = directory/'lecture.wav'
                with wave.open(str(audio), 'wb') as sound:
                    sound.setnchannels(1)
                    sound.setsampwidth(2)
                    sound.setframerate(16000)
                    sound.writeframes(b'\x00\x00'*3200)
                browser.evaluate('(()=>{for(let p=document.querySelector("[data-lib-form=media]").parentElement;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;})()')
                browser.file('[data-lib-form=media] [name=file]', audio)
                browser.click('[data-lib-form=media] button')
                browser.wait('!!document.querySelector("[data-lib=media]")')
                browser.click('[data-lib=link]')
                browser.fill('[data-lib-form=link] [name=startMs]', '.05')
                browser.click('[data-lib-form=link] button')
                browser.wait('!document.querySelector("#libraryReader").open')
                browser.click('[data-lib=linked-media]')
                browser.wait('!!document.querySelector("#libraryReader audio") && document.querySelector("#libraryReader audio").readyState >= 1')
                browser.wait('document.querySelector("#libraryReader audio").currentTime >= .04')
                browser.click('#libraryReader [data-lib=close]')
                browser.click('#libraryRows [data-lib=archive]')
                browser.click('[data-lib-form=organize] button')
                browser.wait('!document.querySelector("#libraryReader").open')
                browser.fill('#libraryChapter', '__archived')
                browser.wait('!!document.querySelector("#libraryRows [data-lib=restore]")')
                browser.click('#libraryRows [data-lib=restore]')
                browser.click('[data-lib-form=organize] button')
                browser.wait('!document.querySelector("#libraryReader").open')
                browser.reload()
                browser.wait('document.querySelector("#libraryRows")?.innerText.includes("My lecture")')
                browser.click('#libraryRows [data-lib=learn]')
                browser.wait('location.hash === "#space/chat" && !!document.querySelector("#chatInput")')
                browser.route('library')
                browser.call('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
                assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                browser.screenshot(output/'library-mobile.png')
                assert not browser.errors, browser.errors
                (output/'report.json').write_text(json.dumps({'status': 'passed', 'paidApiCalls': 0, 'checks': ['text-import', 'web-snapshot-import-controlled', 'reader-search', 'media-original-upload', 'confirmed-media-link', 'actual-player-seek', 'archive-confirm', 'restore', 'reload', 'selected-material-to-chat', 'mobile']}), encoding='utf-8')
                print('G2 browser passed: imports, reader, archive/restore, reload, learning handoff and mobile. Paid calls: 0.')
            except BaseException:
                browser.screenshot(output/'failure.png')
                raise
            finally:
                browser.close()


if __name__ == '__main__':
    main()
