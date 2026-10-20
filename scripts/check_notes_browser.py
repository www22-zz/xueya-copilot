"""Real chapter-note editing, draft recovery and conflict protection; no AI calls."""
import json
from pathlib import Path
import tempfile
import httpx
from .check_learning_browser import Browser,server
from .seed_learning_demo import seed


def main():
    output=Path('test-results/chapter-notes');output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xueya-notes-') as temporary:
        directory=Path(temporary)
        with server(directory) as (url,app),httpx.Client(base_url=url,trust_env=False) as client:
            seed(url)
            client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
            browser=Browser(directory)
            try:
                browser.call('Emulation.setDeviceMetricsOverride',width=1440,height=1000,deviceScaleFactor=1,mobile=False)
                browser.call('Page.navigate',url=url+'/#space/cards')
                browser.wait('!!document.querySelector("#chapterNoteForm") && !!document.querySelector(".notes-list-item")')
                assert browser.evaluate('!document.querySelector("#g3Workspace") && !document.querySelector("#cLearning") && !document.querySelector(".wb-legacy")')
                browser.fill('#chapterNoteForm [name=chapter]','__new__')
                browser.fill('#chapterNoteForm [name=newChapter]','第25章 栈')
                browser.fill('#chapterNoteForm [name=title]','按章节记录我的理解')
                browser.fill('#chapterNoteForm [name=text]','栈遵循后进先出。最后放入的元素最先移除。')
                browser.click('#chapterNoteForm button[type=submit]')
                browser.wait('document.querySelector(".notes-items").innerText.includes("按章节记录我的理解")')
                browser.wait('!document.querySelector("#chapterNoteForm button[type=submit]").disabled')
                browser.reload()
                browser.wait('document.querySelector("#chapterNoteForm [name=text]")?.value.includes("后进先出")')
                browser.fill('#chapterNoteForm [name=text]','已保存的内容。还有一段尚未保存的草稿。')
                browser.reload()
                browser.wait('document.querySelector("#chapterNoteForm [name=text]")?.value.includes("尚未保存的草稿")')
                browser.click('#chapterNoteForm button[type=submit]')
                browser.wait('!document.querySelector("#chapterNoteForm button[type=submit]").disabled')
                browser.fill('#notesChapterFilter','第25章 栈')
                browser.wait('document.querySelectorAll(".notes-list-item").length === 1')
                browser.evaluate('window.XueyaPreferences.applyTheme("light")')
                browser.screenshot(output/'notes-light.png')
                browser.evaluate('window.XueyaPreferences.applyTheme("dark")')
                browser.screenshot(output/'notes-dark.png')
                browser.call('Emulation.setDeviceMetricsOverride',width=390,height=844,deviceScaleFactor=1,mobile=True)
                assert browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                browser.screenshot(output/'notes-mobile.png')
                rows=client.get('/api/learning/artifacts?kind=note').json()['result']['items']
                note=next(r for r in rows if r['content']['title']=='按章节记录我的理解')
                assert note['content']['chapter']=='第25章 栈' and note['revision']==2
                other=client.post('/api/learning/content/note/preview',json={'id':note['id'],'expectedRevision':2,'title':'另一处已保存版本','text':'并发保存的版本','chapter':'第25章 栈'}).json()['result']
                saved=client.post('/api/learning/draft/adopt',json={'draftId':other['draftId'],'operationId':'concurrent-notes-edit','confirmed':True})
                assert saved.status_code==200
                browser.fill('#chapterNoteForm [name=text]','不要覆盖别人刚保存的版本')
                browser.click('#chapterNoteForm button[type=submit]')
                browser.wait('document.querySelector("#chapterNoteForm .c-error").innerText.includes("已有新版本")')
                current=client.get('/api/learning/artifacts',params={'id':note['id']}).json()['result']
                assert current['content']['text']=='并发保存的版本'
                assert not browser.errors,browser.errors
                assert not app.state.platform.db.all('SELECT * FROM invocations')
                (output/'report.json').write_text(json.dumps({'status':'passed','paidApiCalls':0,'checks':['simple-chapter-editor','new-chapter-save','reload-saved-note','unsaved-draft-recovery','edit-version','filter-chapter','concurrent-conflict-no-overwrite','light-dark-mobile']},indent=2),encoding='utf-8')
                print('Chapter notes browser passed: save, edit, drafts, scope, conflict and themes. No paid calls.')
            except BaseException:
                browser.screenshot(output/'failure.png');raise
            finally:browser.close()


if __name__=='__main__':main()
