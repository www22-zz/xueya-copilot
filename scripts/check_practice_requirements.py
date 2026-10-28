"""Regression acceptance for all eleven audited defects, using real Chrome and isolated data."""
import sys,json,socket,tempfile,threading,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.practice_bank import bank
out=Path('test-results/practice-requirements');out.mkdir(parents=True,exist_ok=True);results={}
with tempfile.TemporaryDirectory(prefix='requirements-audit-',ignore_cleanup_errors=True) as d:
 sock=socket.socket();sock.bind(('127.0.0.1',0));base='http://127.0.0.1:'+str(sock.getsockname()[1])
 app=create_app(Config(data_dir=Path(d),api_key=''))
 server=uvicorn.Server(uvicorn.Config(app,log_level='error'));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
 while not server.started:time.sleep(.02)
 # Fixed-ID state-regression fixture; generated banks are covered separately.
 app.state.practice_generation.catalog=lambda account,course_id=None,history=False:{**bank(),'questions':[] if history else bank()['questions'],'generations':[],'available':False}
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
  ctx=browser.new_context(viewport={'width':390,'height':844},service_workers='block');page=ctx.new_page();page.set_default_timeout(12000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  ctx.tracing.start(screenshots=True,snapshots=True,sources=True)
  ctx.request.post(base+'/api/account/register',data={'username':'auditor','password':'Audit12345','confirmPassword':'Audit12345'})
  boot=ctx.request.get(base+'/api/platform/bootstrap').json();headers={'X-Xueya-Token':boot['token']}
  def post(ops):return ctx.request.post(base+'/api/practice/ops',headers=headers,data={'ops':ops}).json()
  def op(oid,kind,qid,payload=None,at=None):return {'opId':oid,'kind':kind,'questionId':qid,'payload':payload or {},**({'clientTs':at} if at else {})}
  def go(route):
   page.goto(base+'/#space/'+route);page.wait_for_function("document.querySelectorAll('.practice-row').length>0")
  def select_filter(name,value):
   field=page.locator(f'select[data-filter="{name}"]');label=field.locator(f'option[value="{value}"]').inner_text()
   field.locator('..').get_by_role('combobox').click()
   page.locator('.practice-select-menu').get_by_role('option',name=label,exact=True).click()
  try:
   go('practice/hot100');page.locator('[data-action=random]').click()
   results['mobile_random']={'fullscreen':page.locator('.practice-module').evaluate("e=>e.classList.contains('is-fullscreen')"),'detail_visible':page.locator('.practice-detail-pane').is_visible()}
   page.screenshot(path=str(out/'mobile-random.png'),full_page=True)
   print('MOBILE_RANDOM',results['mobile_random'],flush=True)
   page.set_viewport_size({'width':1440,'height':1000})
   catalog=ctx.request.get(base+'/api/practice/bank',headers=headers).json()['questions']
   hot=[q for q in catalog if q['category']=='hot100']
   assert len(hot)==len({q['leetcodeUrl'] for q in hot})==100
   manifest=json.loads(Path('backend/xueya/data/hot100_official.json').read_text(encoding='utf-8'))['questions']
   assert {q['leetcodeNumber'] for q in hot}=={q['number'] for q in manifest}
   headings=page.locator('.practice-topic').all_text_contents()
   assert headings==list(dict.fromkeys(q['topic'] for q in manifest)),headings
   results['official_bank_and_topic_groups']={'unique_official_questions':100,'visible_groups':len(headings)}
   # Correct the current attempt, after another browser already submitted a later wrong answer.
   q='b-dsa-f01'
   post([op('answer-A','answer',q,{'result':'wrong','questionType':'fill','selected':'A'},'2026-01-01T00:00:01.000Z'),op('answer-B','answer',q,{'result':'wrong','questionType':'fill','selected':'B'},'2026-01-01T00:00:02.000Z')])
   snapshot=ctx.request.get(base+'/api/practice/state',headers=headers).json()
   results['correction_queue']=page.evaluate('''async({snapshot,token})=>{
     const storage=()=>{const m=new Map();return {getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v)}};
     const make=()=>{const s=XueyaPracticeStore.createStore({storage:storage(),accountId:'auditor'});s.applyServer(snapshot);return s};
     const a=make(),b=make();const client={submitOps:async ops=>(await fetch('/api/practice/ops',{method:'POST',headers:{'Content-Type':'application/json','X-Xueya-Token':token},body:JSON.stringify({ops})})).json()};
     a.push('correct','b-dsa-f01',{questionType:'fill',attemptId:'answer-A'});await a.flush(client);
     b.push('correct','b-dsa-f01',{questionType:'fill',attemptId:'answer-B'});
     let error='';try{await b.flush(client)}catch(e){error=e.message}
     const c=make();c.push('correct','b-dsa-f01',{questionType:'fill',attemptId:'nonexistent-attempt'});
     c.pushNote('h100-01','accepted note after rejected correction',0);
     try{await c.flush(client)}catch(e){error=e.message}
     const left=c.pendingOps;try{await c.flush(client)}catch{}
     if(c.state.rejectedOps?.length!==1)throw Error('missing rejected receipt');
     const server=await(await fetch('/api/practice/state',{headers:{'X-Xueya-Token':token}})).json();
     return {error,wrongCount:server.statuses['b-dsa-f01'].wrongCount,lastResult:server.statuses['b-dsa-f01'].lastResult,pendingAfterAcceptedNote:left,pendingAfterRetry:c.pendingOps,noteActuallySaved:server.notes['h100-01']?.text};
   }''',{'snapshot':snapshot,'token':boot['token']})
   print('CORRECTION_QUEUE',results['correction_queue'],flush=True)
   # Re-entering an older wrong question should sort by its new entry time.
   post([op('oldwrong','answer','b-dsa-f02',{'questionType':'fill','result':'wrong'},'2026-02-01T00:00:00.000Z'),op('resetold','reset','b-dsa-f02',{},'2026-02-02T00:00:00.000Z'),op('otherwrong','mark-wrong','b-dsa-f03',{},'2026-02-03T00:00:00.000Z'),op('readdold','mark-wrong','b-dsa-f02',{},'2026-02-04T00:00:00.000Z')])
   go('review');select_filter('type','fill')
   visible=page.locator('.practice-row').evaluate_all('es=>es.map(e=>e.dataset.id)')
   results['wrong_sort']={'actual':visible,'expected_first':'b-dsa-f02'}
   print('WRONG_SORT',results['wrong_sort'],flush=True)
   # A focused, idle search input prevents the periodic state snapshot from rerendering.
   go('practice/hot100');page.locator('[data-filter=keyword]').fill('h100-01')
   post([op('remote-master','master','h100-01')])
   page.wait_for_function("JSON.parse(localStorage.getItem('xueya-practice-v1:auditor')).statuses['h100-01']?.status==='mastered'",timeout=15000)
   results['stale_visible_list']={'rows':page.locator('.practice-row').count(),'detail_status':page.locator('.practice-detail-head .chip').all_text_contents(),'stored_status':page.evaluate("JSON.parse(localStorage.getItem('xueya-practice-v1:auditor')).statuses['h100-01'].status"),'focused_field':page.evaluate('document.activeElement.dataset.filter')}
   page.screenshot(path=str(out/'stale-search.png'),full_page=True)
   print('STALE_LIST',results['stale_visible_list'],flush=True)
   # Completion does not revive when another browser puts the question back in pending.
   page.locator('[data-action=clear-filters]').first.click();page.locator('[data-filter=keyword]').fill('h100-04')
   page.locator('[data-action=master]').click();expect(page.locator('.practice-detail-pane')).to_contain_text('已刷完')
   post([op('remote-reset','reset','h100-04')]);page.locator('[data-action=retry-sync]').click();page.wait_for_timeout(500)
   results['stuck_completion']={'rows':page.locator('.practice-row').count(),'detail':page.locator('.practice-detail-pane').inner_text()[:80]}
   print('COMPLETION',results['stuck_completion'],flush=True)
   # Two independent browser contexts correct their own submitted answer via the real UI.
   other=browser.new_context(storage_state=ctx.storage_state(),viewport={'width':1440,'height':1000},service_workers='block')
   page2=other.new_page();page2.on('pageerror',lambda e:errors.append(str(e)))
   for current_page in (page,page2):
    current_page.goto(base+'/#space/practice/foundation')
    current_page.locator('[data-filter=keyword]').fill('b-dsa-f04')
    expect(current_page.locator('[data-fill]')).to_be_visible()
   for current_page in (page,page2):
    current_page.locator('[data-fill]').fill('not-canonical-'+str(current_page==page2))
    current_page.locator('[data-action=submit-fill]').click()
    expect(current_page.locator('.practice-result')).to_contain_text('回答错误')
    current_page.wait_for_function("JSON.parse(localStorage.getItem('xueya-practice-ops:auditor')||'[]').length===0")
    print('UI_ANSWER',current_page==page2,current_page.evaluate('window.XueyaAccountId'),ctx.request.get(base+'/api/practice/state',headers=headers).json()['statuses'].get('b-dsa-f04'),flush=True)
   for current_page in (page,page2):
    current_page.locator('[data-action=also-correct]').click()
    current_page.wait_for_function("JSON.parse(localStorage.getItem('xueya-practice-ops:auditor')||'[]').length===0")
    expect(current_page.locator('.practice-result')).to_contain_text('回答正确')
    print('UI_CORRECTION',current_page==page2,ctx.request.get(base+'/api/practice/state',headers=headers).json()['statuses'].get('b-dsa-f04'),flush=True)
   corrected=ctx.request.get(base+'/api/practice/state',headers=headers).json()['statuses']['b-dsa-f04']
   assert corrected['wrongCount']==0 and corrected['correctCount']==2 and corrected['status']=='pending',corrected
   results['two_browser_ui_corrections']=corrected
   other.close()
   go('practice/hot100')
   # Independent note writing remains reachable through the settings menu.
   page.locator('#appSettingsButton').click();page.locator('[data-settings-tab=services]').click();page.locator('#platformData').click()
   results['legacy_note_entry']={'title_visible':page.locator('#platformNoteTitle').count()>0,'preview_visible':page.locator('#platformNotePreview').count()>0}
   page.screenshot(path=str(out/'legacy-note-entry.png'),full_page=True)
   print('LEGACY_NOTE',results['legacy_note_entry'],flush=True)
   page.locator('#platformClose').click()
   # Old raw storage survives the runtime normalizer.
   page.evaluate("localStorage.setItem('xueya-copilot-state-v1',JSON.stringify({cards:[{text:'OLD_NOTE_SENTINEL'}],bank:[{id:'old-question'}],records:[{questionId:'old-question'}]}))")
   page.reload();page.wait_for_function("document.querySelector('.practice-module')")
   results['legacy_raw_storage_retained']='OLD_NOTE_SENTINEL' in page.evaluate("localStorage.getItem('xueya-copilot-state-v1')||''")
   # Simulate browser storage quota while typing a new note.
   page.locator('[data-action=clear-filters]').first.click();page.locator('.practice-row').first.click()
   page.evaluate("()=>{window.auditSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(typeof k==='string'&&k.startsWith('xueya-practice'))throw new DOMException('quota','QuotaExceededError');return window.auditSetItem.call(this,k,v)};return true}")
   page.route('**/api/practice/ops',lambda route:route.abort())
   page.locator('[data-note]').fill('QUOTA_NEW_NOTE');page.wait_for_timeout(1300)
   results['quota_failure']={'label':page.locator('[data-note-status]').inner_text(),'toast':page.locator('#toast').inner_text(),'uncaught_errors':list(errors)}
   page.reload();page.wait_for_function("document.querySelector('[data-note]')")
   results['quota_failure']['draft_after_reload']=page.locator('[data-note]').input_value()
   assert '保存失败' in results['quota_failure']['label']
   assert results['quota_failure']['toast']
   # A new unsaved draft must survive closing the entire tab, even with localStorage
   # still unavailable. It cannot recover from the previous tab's sessionStorage.
   ctx.route('**/api/practice/ops',lambda route:route.abort())
   page.evaluate("()=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage&&k.startsWith('xueya-practice'))throw new DOMException('quota','QuotaExceededError');return original.call(this,k,v)};return true}")
   page.locator('[data-note]').fill('QUOTA_TAB_CLOSED_DRAFT')
   page.wait_for_function("async()=>new Promise(resolve=>{const r=indexedDB.open('xueya-practice-recovery',1);r.onsuccess=()=>{const db=r.result,t=db.transaction('records'),g=t.objectStore('records').get('xueya-practice-v1:auditor');g.onsuccess=()=>resolve((g.result||'').includes('QUOTA_TAB_CLOSED_DRAFT'));t.oncomplete=()=>db.close();};r.onerror=()=>resolve(false);})")
   assert 'QUOTA_TAB_CLOSED_DRAFT' not in page.evaluate("localStorage.getItem('xueya-practice-v1:auditor')||''")
   old_url=page.url;page.close();page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(old_url);expect(page.locator('[data-note]')).to_have_value('QUOTA_TAB_CLOSED_DRAFT')
   results['quota_failure']['closed_tab_draft_restored']=True
   ctx.unroute('**/api/practice/ops')
   page.locator('[data-action=retry-sync]').click()
   page.wait_for_function("!Object.keys(JSON.parse(localStorage.getItem('xueya-practice-v1:auditor')).drafts).length")
   saved=ctx.request.get(base+'/api/practice/state',headers=headers).json()
   assert any(n['text']=='QUOTA_TAB_CLOSED_DRAFT' for n in saved['notes'].values())
   results['quota_failure']['reconnected_server_saved']=True
   print('QUOTA',results['quota_failure'],flush=True)
   assert results['mobile_random']['fullscreen'] and results['mobile_random']['detail_visible']
   correction=results['correction_queue']
   assert correction['wrongCount']==0 and correction['lastResult']=='correct',correction
   assert correction['pendingAfterAcceptedNote']==correction['pendingAfterRetry']==0,correction
   assert correction['noteActuallySaved']=='accepted note after rejected correction'
   assert results['wrong_sort']['actual'][0]==results['wrong_sort']['expected_first']
   assert results['stale_visible_list']['rows']==0 and results['stale_visible_list']['focused_field']=='keyword'
   assert '已刷完' not in results['stuck_completion']['detail']
   assert not any(results['legacy_note_entry'].values())
   assert results['legacy_raw_storage_retained'] is False
   assert results['quota_failure']['draft_after_reload']=='QUOTA_NEW_NOTE'
   assert not errors,errors
   results['all_assertions_passed']=True
   print('PASS all audited browser regressions',flush=True)
  finally:
   (out/'evidence.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
   ctx.tracing.stop(path=str(out/'trace.zip'))
   browser.close();server.should_exit=True;thread.join(5);app.state.platform.db.close()
