/* A's real-browser acceptance. Optional injected ports are controlled fixtures, not model evaluation. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {createApp}=require('../../backend/app.js');
const root=path.resolve(__dirname,'../..'),output=path.join(root,'test-results/workspace');

(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const server=http.createServer(createApp({config:{root,ai:{apiKey:'',model:'no-paid-api'}}}));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  let browser,page;
  try{
    browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
    page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(12000);
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    const nav=async view=>{await page.goto(base+'/#space/'+view);await page.locator('#spacePage').waitFor({state:'visible'});};
    const close=()=>page.getByRole('button',{name:'关闭编辑面板',exact:true}).click();
    const dialog=()=>page.locator('#workspaceDialog');
    const submit=()=>dialog().getByRole('button',{name:'保存',exact:true}).click();
    const saved=()=>page.evaluate(()=>JSON.parse(localStorage.getItem('xueya-copilot-state-v2')));
    const phase=name=>console.log('A browser:',name);

    phase('documents, originals, metadata and versions');
    await nav('library');
    const text='拓扑排序每轮选择入度为零的顶点。更新入度，移除出边。\n'.repeat(35);
    await page.locator('#fileInput').setInputFiles({name:'课程原文.md',mimeType:'text/markdown',buffer:Buffer.from(text)});
    const row=()=>page.locator('.document-row').filter({hasText:'课程原文.md'}).filter({has:page.locator('[data-version-document]')}).first();
    await row().getByText('已解析，可检索',{exact:true}).waitFor();
    await row().getByRole('button',{name:'整理',exact:true}).click();
    await dialog().locator('[name=tags]').fill('图论，期中');await dialog().locator('[name=chapter]').fill('第六章');await submit();
    assert.match(await row().innerText(),/图论/);
    await row().locator('[data-document]').click();
    await page.locator('#readerSearch').fill('拓扑');assert.ok(await page.locator('#readerPassage mark').count()>0);
    await page.locator('#readerSection').selectOption('1');assert.match(await page.locator('#readerPassage').innerText(),/入度/);
    const original=page.waitForEvent('download');await page.getByRole('button',{name:'下载原件',exact:true}).click();assert.equal((await original).suggestedFilename(),'课程原文.md');
    await page.getByRole('button',{name:'纠错草稿',exact:true}).click();await dialog().locator('[name=text]').fill('人工核对：每次选择入度为零的顶点。');await submit();
    assert.equal((await saved()).documents[0].corrections[0].applied,false);
    await page.getByRole('button',{name:'关闭原文',exact:true}).click();
    const chooser=page.waitForEvent('filechooser');await row().getByRole('button',{name:'新版本',exact:true}).click();
    await (await chooser).setFiles({name:'课程原文.md',mimeType:'text/markdown',buffer:Buffer.from('新版：拓扑排序需要维护顶点入度，并依次移除零入度顶点。')});
    await page.waitForFunction(()=>JSON.parse(localStorage.getItem('xueya-copilot-state-v2')).documents.some(d=>d.version===2));
    const documents=(await saved()).documents;assert.equal(documents.filter(d=>d.name==='课程原文.md').length,2);assert.equal(documents.find(d=>d.version===1).superseded,true);
    await page.reload();await row().locator('[data-document]').click();assert.match(await page.locator('#sourceContent').innerText(),/新版/);await page.getByRole('button',{name:'关闭原文',exact:true}).click();

    phase('safe rich notes, editing, historical restore');
    await nav('cards');await page.getByRole('button',{name:'新建笔记',exact:true}).click();
    await dialog().locator('[name=title]').fill('拓扑学习札记');
    await dialog().locator('[name=text]').fill('# 要点\n**零入度**\n\n|算法|复杂度|\n|---|---|\n|拓扑排序|$O(V+E)$|\n\n$$\\frac{a^2}{b}$$\n\n```js\nconst ready = [];\n```\n<img src=x onerror="window.hacked=1">');
    await submit();assert.equal(await page.locator('#cardList table').count(),1);assert.equal(await page.locator('#cardList math').count(),2);assert.equal(await page.locator('#cardList img').count(),0);assert.equal(await page.evaluate(()=>window.hacked),undefined);
    await page.locator('#cardList [data-edit-card]').click();await dialog().locator('[name=text]').fill('第二版笔记');await submit();
    await page.locator('#cardList [data-card-history]').click();assert.match(await dialog().innerText(),/零入度/);await dialog().getByRole('button',{name:'恢复为新版本',exact:true}).click();assert.equal((await saved()).cards[0].version,3);
    await page.reload();assert.match(await page.locator('#cardList').innerText(),/零入度/);

    phase('sessions, pinned follow-up, source scope, feedback');
    await nav('chat');const requests=[];
    await page.route('**/api/agent/stream',route=>{requests.push(route.request().postDataJSON());return route.continue();});
    async function ask(question){await page.locator('#chatInput').fill(question);await page.getByRole('button',{name:'发送问题',exact:true}).click();await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();}
    await ask('拓扑排序每次如何选择顶点？');const first=(await saved()).messages.find(m=>m.role==='ai');assert.ok(first.sources.length);
    await ask('AVL树通过什么方法保持平衡？');
    await page.locator('[data-followup="1"]').click();await ask('请解释这个问题，并给出资料依据。');
    assert.ok(requests.at(-1).context.previousSourceIds.includes(first.sources[0].id));assert.equal(requests.at(-1).history.some(m=>m.role==='user'&&m.content==='AVL树通过什么方法保持平衡？'),false);
    await page.locator('[data-feedback][data-rating=incorrect]').first().click();await dialog().locator('[name=text]').fill('请核对引用的课程版本。');await submit();assert.equal((await saved()).feedback.length,1);
    const firstSession=(await saved()).sessionId;await page.locator('[data-new-session]').click();assert.equal(await page.locator('.message').count(),0);
    await page.locator(`[data-session="${firstSession}"]`).click();assert.ok(await page.locator('.message').count()>=6);
    await page.locator('.scope-picker summary').click();const scopeDoc=(await saved()).documents.find(d=>d.version===2);await page.locator(`[data-scope="${scopeDoc.id}"]`).check();await ask('拓扑排序如何维护入度？');assert.equal(requests.at(-1).context.library.length>0&&requests.at(-1).context.library.every(s=>scopeDoc.chunks.some(c=>c.id===s.id)),true);
    await page.unroute('**/api/agent/stream');

    phase('question authoring, draft recovery, multiple/short scoring and correction');
    await nav('practice');await page.getByRole('button',{name:'新建自测题',exact:true}).click();
    await dialog().locator('[name=type]').selectOption('multiple');await dialog().locator('[name=topic]').fill('拓扑排序');await dialog().locator('[name=prompt]').fill('选择正确描述');await dialog().locator('[name=options]').fill('有向无环图可拓扑排序\n需要维护入度\n必须存在环');await dialog().locator('[name=answer]').fill('1,2');await dialog().locator('[name=explanation]').fill('零入度队列逐步消除顶点。');await submit();
    await page.locator('[data-multiple-answer="0"]').check();await page.reload();assert.equal(await page.locator('[data-multiple-answer="0"]').isChecked(),true);
    await page.locator('[data-multiple-answer="1"]').check();await page.getByRole('button',{name:'提交答案',exact:true}).click();assert.equal((await saved()).records.at(-1).correct,true);
    await page.getByRole('button',{name:'记录错因与订正',exact:true}).click();await dialog().locator('[name=text]').fill('复习入度的定义，不能把出度当入度。');await submit();assert.match(await page.locator('.correction-list').innerText(),/出度/);
    await page.getByRole('button',{name:'新建自测题',exact:true}).click();await dialog().locator('[name=type]').selectOption('short');await dialog().locator('[name=topic]').fill('入度');await dialog().locator('[name=prompt]').fill('解释入度');await dialog().locator('[name=answerText]').fill('指向顶点的边数');await dialog().locator('[name=explanation]').fill('结合原图核对');await submit();
    await page.locator('#shortAnswer').fill('所有指向该顶点的边的数量。');await page.getByRole('button',{name:'提交答案',exact:true}).click();await page.getByRole('button',{name:'对照后：已掌握',exact:true}).click();assert.equal((await saved()).records.at(-1).selfAssessed,true);

    phase('plan preview, adoption, deferral and version history');
    await nav('plan');const oldPlan=(await saved()).plan;await page.locator('#dailyMinutes').selectOption('45');await page.getByRole('button',{name:'预览新的安排',exact:true}).click();assert.deepEqual((await saved()).plan,oldPlan);assert.ok(await page.locator('[data-adopt-plan]').count());await page.locator('[data-adopt-plan]').click();assert.equal((await saved()).minutes,45);assert.ok((await saved()).planHistory.length);
    const taskId=(await saved()).plan[0].tasks[0].id;await page.locator(`[data-task="${taskId}"]`).check();await page.locator(`[data-defer-task="${taskId}"]`).click();await page.reload();assert.equal((await saved()).completed[taskId],true);assert.equal((await saved()).plan.some(d=>d.tasks.some(t=>t.id===taskId)),true);

    phase('graph evidence, explicit prerequisite relations, cycle rejection');
    await nav('graph');assert.ok(await page.locator('.learning-graph circle').count()>2);await page.getByRole('button',{name:'添加先修关系',exact:true}).click();const ids=await dialog().locator('[name=from] option').evaluateAll(options=>options.map(o=>o.value));await dialog().locator('[name=from]').selectOption(ids[0]);await dialog().locator('[name=to]').selectOption(ids[1]);await submit();assert.equal((await saved()).relations.length,1);
    await page.getByRole('button',{name:'添加先修关系',exact:true}).click();await dialog().locator('[name=from]').selectOption(ids[1]);await dialog().locator('[name=to]').selectOption(ids[0]);await submit();assert.match(await page.locator('#editorError').innerText(),/循环/);await close();

    phase('course isolation, archive/restore and unavailable capabilities');
    await page.getByRole('button',{name:'管理课程',exact:true}).click();await dialog().locator('[name=name]').fill('数学课程');await dialog().getByRole('button',{name:'创建课程',exact:true}).click();const mathCourse=(await saved()).courseId;assert.equal((await saved()).cards.length,0);assert.equal((await saved()).documents.length,0);assert.equal((await saved()).messages.length,0);
    await page.locator('#courseSelect').selectOption('course-default');assert.equal((await saved()).cards[0].title,'拓扑学习札记');await page.getByRole('button',{name:'管理课程',exact:true}).click();await dialog().locator(`[data-archive-course="${mathCourse}"]`).click();assert.equal(await page.locator(`#courseSelect option[value="${mathCourse}"]`).count(),0);await dialog().locator(`[data-restore-course="${mathCourse}"]`).click();await close();
    await nav('media');assert.equal(await page.locator('[data-media-run=transcribe]').isDisabled(),true);assert.match(await page.locator('.media-grid').innerText(),/尚未接通/);

    phase('responsive layout, keyboard, screenshots');
    for(const width of [1440,768,375]){
      await page.setViewportSize({width,height:1000});
      for(const view of ['overview','chat','library','cards','practice','memory','plan','graph','media']){
        await nav(view);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,view+' overflows at '+width);
      }
      await nav('chat');await page.screenshot({path:path.join(output,`chat-${width}.png`),fullPage:true,animations:'disabled'});
    }
    await page.setViewportSize({width:1440,height:1000});await nav('graph');await page.screenshot({path:path.join(output,'graph-desktop.png'),fullPage:true,animations:'disabled'});
    await page.keyboard.press('Control+k');assert.equal(await page.locator('#searchDialog').evaluate(el=>el.open),true);await page.keyboard.press('Escape');assert.equal(await page.locator('#searchDialog').evaluate(el=>el.open),false);

    phase('injected image/audio ports, cancellation without a partial result');
    const mediaPage=await browser.newPage({viewport:{width:1440,height:900}});mediaPage.setDefaultTimeout(12000);mediaPage.on('pageerror',error=>errors.push(error.message));
    await mediaPage.addInitScript(()=>{window.remoteDocuments=[{id:'remote-doc',name:'服务端课程.md',status:'等待解析',meta:'受控资料服务',chunks:[]}];window.XueyaWorkspaceBackend={
      async listDocuments(){return{documents:window.remoteDocuments};},
      async uploadDocument(input,{onProgress}){onProgress({label:'受控资料解析',percent:60});const doc={id:'remote-upload',name:input.file.name,status:'已解析，可检索',chunks:[{id:'remote-source',documentId:'remote-upload',title:input.file.name,location:'片段1',quote:await input.file.text()}]};window.remoteDocuments.push(doc);return doc;},
      async updateDocument(input){Object.assign(window.remoteDocuments.find(doc=>doc.id===input.documentId),input.metadata);return{updated:true};},
      async removeDocument(input){window.remoteDocuments=window.remoteDocuments.filter(doc=>doc.id!==input.documentId);return{removed:true};},
      async graph(){if(window.deferNextGraph){window.deferNextGraph=false;return new Promise(resolve=>{window.deliverStaleGraph=()=>resolve({nodes:[{id:'stale',label:'陈旧图谱'}],edges:[]});});}return{nodes:[{id:'g1',label:'服务端概念',sourceId:'source-1',records:3,mastery:{score:.6,confidence:.8}},{id:'g2',label:'后继概念',records:'<img src=x onerror="window.hacked=1">'}],edges:[{from:'g1',to:'g2',type:'prerequisite'}],paths:[{title:'受控学习路径',nodeIds:['g1','g2']}]};},
      async imageChat(input){window.imageNames=input.images.map(file=>file.name);return{answer:'受控图像接口：已收到图片。',sources:[input.sources[0].id,'forged']};},
      async transcribe(input,{onProgress}){onProgress('受控转写进行中');if(window.slowAudio)await new Promise(resolve=>setTimeout(resolve,1500));return{text:'受控音频接口返回的转写',segments:[{start:0,end:3,text:'课程片段'}]};},
      async video(){return{summary:'受控视频片段摘要',segments:[{start:2,end:4,text:'原片段要点'}]};},
      async speak(){return{audio:new Blob(['controlled fixture'],{type:'audio/wav'}),text:'受控语音结果'};}
    };});
    await mediaPage.goto(base+'/#space/chat');await mediaPage.locator('#imageInput').setInputFiles({name:'图表.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kP6kAAAAASUVORK5CYII=','base64')});await mediaPage.locator('#chatInput').fill('解释图片');await mediaPage.getByRole('button',{name:'发送问题',exact:true}).click();await mediaPage.getByText('受控图像接口：已收到图片。',{exact:true}).waitFor();assert.deepEqual(await mediaPage.evaluate(()=>window.imageNames),['图表.png']);assert.equal(await mediaPage.locator('.citation-chip').count(),1);
    await mediaPage.goto(base+'/#space/library');await mediaPage.locator('[data-refresh-documents]').click();await mediaPage.getByText('服务端课程.md',{exact:true}).waitFor();await mediaPage.locator('#fileInput').setInputFiles({name:'远程上传.md',mimeType:'text/markdown',buffer:Buffer.from('受控上传接口原文')});await mediaPage.waitForFunction(()=>JSON.parse(localStorage.getItem('xueya-copilot-state-v2')).documents.some(doc=>doc.id==='remote-upload'));const remoteRow=mediaPage.locator('.document-row').filter({hasText:'远程上传.md'});await remoteRow.getByRole('button',{name:'整理',exact:true}).click();await mediaPage.locator('#workspaceDialog [name=tags]').fill('同步标签');await mediaPage.locator('#workspaceDialog').getByRole('button',{name:'保存',exact:true}).click();assert.deepEqual(await mediaPage.evaluate(()=>window.remoteDocuments.find(doc=>doc.id==='remote-upload').tags),['同步标签']);await mediaPage.locator('#fileInput').setInputFiles({name:'重复版本.md',mimeType:'text/markdown',buffer:Buffer.from('不能覆盖原件')});await mediaPage.getByText('资料服务必须为新版本提供独立记录ID，本次未覆盖已有原件。',{exact:true}).waitFor();assert.equal(await mediaPage.evaluate(()=>JSON.parse(localStorage.getItem('xueya-copilot-state-v2')).documents.filter(doc=>doc.id==='remote-upload').length),1);assert.equal(await mediaPage.evaluate(async()=>await(await window.XueyaFileCache.createCache().get('remote-upload')).text()),'受控上传接口原文');await remoteRow.locator('[data-remove-document]').click();await mediaPage.locator('#workspaceDialog').getByRole('button',{name:'确认移除',exact:true}).click();assert.equal(await mediaPage.evaluate(()=>window.remoteDocuments.some(doc=>doc.id==='remote-upload')),false);
    await mediaPage.goto(base+'/#space/graph');await mediaPage.locator('.concept-list').getByText('受控学习路径',{exact:true}).waitFor();assert.equal(await mediaPage.locator('.learning-graph circle').count(),2);assert.match(await mediaPage.locator('.concept-list').innerText(),/60%/);assert.equal(await mediaPage.locator('.concept-list img').count(),0);assert.equal(await mediaPage.evaluate(()=>window.hacked),undefined);await mediaPage.evaluate(()=>{window.deferNextGraph=true;});await mediaPage.locator('[data-refresh-graph]').click();await mediaPage.waitForFunction(()=>typeof window.deliverStaleGraph==='function');await mediaPage.locator('[data-refresh-graph]').click();await mediaPage.locator('.concept-list').getByText('受控学习路径',{exact:true}).waitFor();await mediaPage.evaluate(async()=>{window.deliverStaleGraph();await new Promise(requestAnimationFrame);});assert.doesNotMatch(await mediaPage.locator('.concept-list').innerText(),/陈旧图谱/);
    await mediaPage.goto(base+'/#space/media');const audioFile={name:'课程.wav',mimeType:'audio/wav',buffer:Buffer.from('controlled audio fixture')};await mediaPage.locator('[data-media-file=transcribe]').setInputFiles(audioFile);await mediaPage.locator('[data-media-run=transcribe]').click();await mediaPage.locator('.media-results').getByText('受控音频接口返回的转写',{exact:true}).waitFor();await mediaPage.locator('[data-media-note="0"]').click();await mediaPage.locator('#workspaceDialog').getByRole('button',{name:'保存',exact:true}).click();
    await mediaPage.locator('[data-media-file=video]').setInputFiles({name:'课堂.mp4',mimeType:'video/mp4',buffer:Buffer.from('controlled video fixture')});await mediaPage.locator('[data-media-run=video]').click();await mediaPage.locator('.media-results').getByText('受控视频片段摘要',{exact:true}).waitFor();await mediaPage.locator('#speechText').fill('需要朗读的重点');await mediaPage.locator('[data-media-run=speak]').click();await mediaPage.locator('.media-results audio').waitFor();await mediaPage.reload();await mediaPage.locator('.media-results audio').waitFor();
    const completedMedia=await mediaPage.evaluate(()=>JSON.parse(localStorage.getItem('xueya-copilot-state-v2')).mediaResults.length);await mediaPage.locator('[data-media-file=transcribe]').setInputFiles(audioFile);await mediaPage.evaluate(()=>{window.slowAudio=true;});await mediaPage.locator('[data-media-run=transcribe]').click();await mediaPage.locator('[data-stop-media]').click();await mediaPage.getByText('已停止处理',{exact:true}).waitFor();assert.equal(await mediaPage.evaluate(()=>JSON.parse(localStorage.getItem('xueya-copilot-state-v2')).mediaResults.length),completedMedia);
    await mediaPage.goto(base+'/#space/cards');await mediaPage.evaluate(()=>{window.originalSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key==='xueya-copilot-workspace-v3')throw new DOMException('controlled quota','QuotaExceededError');return window.originalSetItem.call(this,key,value);};});await mediaPage.getByRole('button',{name:'新建笔记',exact:true}).click();await mediaPage.locator('#workspaceDialog [name=title]').fill('未持久保存的草稿');await mediaPage.locator('#workspaceDialog [name=text]').fill('浏览器容量不足时必须明确提示');await mediaPage.locator('#workspaceDialog').getByRole('button',{name:'保存',exact:true}).click();assert.equal(await mediaPage.locator('#storageNotice').isVisible(),true);await mediaPage.evaluate(()=>{Storage.prototype.setItem=window.originalSetItem;});
    assert.deepEqual(errors,[]);

    phase('direct-file preview with no HTTP API calls');
    const filePage=await browser.newPage();const apis=[];filePage.on('pageerror',error=>errors.push(error.message));filePage.on('request',request=>{if(/^https?:/.test(request.url())&&request.url().includes('/api/'))apis.push(request.url());});await filePage.goto(pathToFileURL(path.join(root,'frontend/index.html')).href+'#space/graph');await filePage.locator('.learning-graph').waitFor();await filePage.goto(pathToFileURL(path.join(root,'frontend/index.html')).href+'#space/media');assert.equal(await filePage.locator('[data-media-run=video]').isDisabled(),true);assert.deepEqual(apis,[]);assert.deepEqual(errors,[]);
    console.log('A browser acceptance passed; local functions and controlled optional ports verified separately.');
  }catch(error){if(page)await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});throw error;}
  finally{if(browser)await browser.close();server.closeAllConnections?.();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
