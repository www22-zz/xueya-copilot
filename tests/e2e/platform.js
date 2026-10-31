'use strict';
const {chromium}=require('playwright'),assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {startPython,expandLegacyRecords}=require('./python-server.js');
(async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'xueya-e-browser-'));
  const server=await startPython({platform:true,dataDir:dir});let browser;
  try{
    browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await expandLegacyRecords(page);await server.authenticate(page);
    const identity=await page.request.get(server.base+'/api/account/status').then(r=>r.json());
    await page.addInitScript(({owner})=>{if(!localStorage.getItem('e-seeded')){localStorage.setItem('e-seeded','1');localStorage.setItem('xueya-copilot-state-v2'+':'+owner,JSON.stringify({documents:[],cards:[],messages:Array.from({length:35},(_,i)=>({id:'msg-'+i,role:'user',text:'历史'+i})),records:Array.from({length:350},()=>({questionId:'q1',correct:true,createdAt:new Date().toISOString()}))}));}},{owner:identity.dataOwner});
    const openSettings=async()=>{const current=page.locator('button[data-open-settings]:visible').first();if(await current.count())await current.click();else await page.locator('#appSettingsButton').click();};
    const base='http://127.0.0.1:'+server.address().port;await page.goto(base+'/#space/overview');await openSettings();await page.locator('[data-settings-tab=services]').click();await page.locator('#platformData').click();await page.locator('#platformPreview').click();await page.locator('#platformApply:not([hidden])').waitFor();assert.match(await page.locator('#platformPreviewText').textContent(),/35/);await page.locator('#platformApply').click();await page.waitForFunction(()=>document.querySelector('#platformStatus').textContent.includes('迁移完成'));
    const migrated=(await server.api('/workspace')).workspace.data.courses[0].data;assert.equal(migrated.records,undefined);assert.equal(migrated.messages.length,35);assert.equal(await page.locator('#platformNoteTitle').count(),0);
    await page.locator('#platformClose').click();await page.goto(base+'/#space/practice/hot100');await page.locator('[data-note]').fill('每题随手记保存验证');await page.waitForFunction(()=>JSON.parse(localStorage.getItem('xueya-practice-ops:browser-regression')||'[]').length===0&&JSON.parse(localStorage.getItem('xueya-practice-v1:browser-regression')||'{}').notes?.['h100-01']?.text==='每题随手记保存验证');await page.reload();assert.equal(await page.locator('[data-note]').inputValue(),'每题随手记保存验证');console.log('E browser: migration preserves conversations, retires old records; per-question note survives reload');
    await page.goto(base+'/#space/knowledge');await page.getByRole('button',{name:'上传资料',exact:true}).click();await page.locator('#kbFiles').setInputFiles({name:'新课程.md',mimeType:'text/markdown',buffer:Buffer.from('叶绿体是光合作用的重要场所。')});await page.getByRole('button',{name:'查看资料',exact:true}).click();await page.locator('.kb-document').filter({hasText:'新课程.md'}).locator('.kb-status').waitFor();
    let ingested;
    for(let check=0;check<100;check++){
      const catalog=await server.api('/knowledge/catalog');ingested=catalog.documents.find(item=>item.name==='新课程.md');
      if(ingested?.task?.status==='succeeded')break;
      assert.ok(!['failed','unknown','cancelled'].includes(ingested?.task?.status),'Document processing failed');
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    assert.equal(ingested?.task?.status,'succeeded');assert.ok(ingested.sourceCount>0);
    await page.waitForFunction(()=>localStorage.getItem(window.XueyaDataKey('xueya-platform-pending-v1'))===null);const doc=(await server.api('/entities?kind=document')).items.find(d=>d.name==='新课程.md');assert.ok(doc.fileHash);assert.ok(fs.readFileSync(path.join(dir,'files',doc.fileHash.slice(0,2),doc.fileHash),'utf8').includes('叶绿体'));assert.ok((await server.api('/entities?kind=source')).items.some(s=>s.documentId===doc.id));
    await page.reload();await page.locator('#platformData').waitFor({state:'attached'});await page.getByRole('button',{name:'查看资料',exact:true}).click();await page.locator('.kb-document').filter({hasText:'新课程.md'}).waitFor();console.log('E browser: upload -> real job -> originals/chunks -> automatic sync -> reload');
    await openSettings();await page.locator('[data-settings-tab=services]').click();await page.locator('#platformData').click();await page.locator('#platformClose').click();await page.screenshot({path:path.resolve('test-results/platform-desktop.png'),fullPage:true});
    await page.setViewportSize({width:375,height:812});await page.screenshot({path:path.resolve('test-results/platform-mobile.png'),fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);console.log('E browser: no runtime errors; desktop/mobile verified');
  }finally{await browser?.close();await server.close();assert.ok(dir.startsWith(path.join(os.tmpdir(),'xueya-e-browser-')));fs.rmSync(dir,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
