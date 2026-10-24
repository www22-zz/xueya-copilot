const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');
const {startPython,expandLegacyRecords}=require('./python-server.js');
const {sampleDocx,samplePdf}=require('../fixtures/documents.js');
const root=path.resolve(__dirname,'../..');
const outputDirectory=path.join(root,'test-results/browser');

(async()=>{
  // Controlled model exercises the complete application without a key or paid calls.
  const config={root,ai:{apiKey:'browser-test-only',model:'controlled'}};
  let resolveCancellation;
  const modelCancelled=new Promise(resolve=>{resolveCancellation=resolve;});
  const model={generate:async({messages})=>{
    const {materials}=JSON.parse(messages.at(-1).content);
    const source=materials.find(item=>item.title==='协作验证.md')||materials[0];
    if(messages[0].content.includes('知识点整理助手'))return{model:'controlled',content:JSON.stringify([{name:'拓扑排序',sourceId:source.id},{name:'入度',sourceId:source.id}])};
    if(messages[0].content.includes('出题助手'))return{model:'controlled',content:JSON.stringify([{topic:'拓扑排序',prompt:'拓扑排序首先选择哪类顶点？',options:['入度为零的顶点','出度最大的顶点','任意顶点','编号最大的顶点'],answer:0,explanation:'每轮选择入度为零的顶点。',sourceId:source.id}])};
    return{model:'controlled',content:JSON.stringify({answer:'受控问答：'+source.quote,sources:[source.id],knowledgePoints:[]})};
  }};
  model.stream=async function*({messages,signal}){
    if(JSON.parse(messages.at(-1).content).question.includes('慢一点')){
      yield{type:'content',text:'{"answer":"尚未校验的半段答案',model:'controlled'};
      await new Promise(resolve=>{if(signal.aborted)resolve();else signal.addEventListener('abort',resolve,{once:true});});
      resolveCancellation(signal.aborted);return;
    }
    const response=await model.generate({messages});
    for(let offset=0;offset<response.content.length;offset+=12)yield{type:'content',text:response.content.slice(offset,offset+12),model:'controlled'};
  };
  const server=await startPython({model});
  const base=server.base;
  let browser;
  try{
    const options={headless:true};
    if(process.env.CHROME_PATH)options.executablePath=process.env.CHROME_PATH;
    browser=await chromium.launch(options);
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    fs.mkdirSync(outputDirectory,{recursive:true});
    await expandLegacyRecords(page);
    await page.goto(base+'/');
    assert.equal(await page.locator('.hero h1').innerText(),'资料，读得懂。\n知识，用得上。');
    await page.getByRole('tab',{name:'记得牢固'}).click();
    assert.match(await page.locator('#demoContent').innerText(),/练习/);
    await page.getByRole('link',{name:'进入学习空间',exact:true}).click();
    await page.locator('#spacePage').waitFor({state:'visible'});

    await page.locator('.space-nav [data-view=knowledge]').click();
    await page.locator('#fileInput').setInputFiles({name:'协作验证.md',mimeType:'text/markdown',buffer:Buffer.from('拓扑排序每轮选择入度为零的顶点，移除该顶点和出边，再更新相邻顶点的入度。')});
    await page.waitForFunction(()=>document.querySelector('#documentList')?.textContent.includes('协作验证.md'));
    assert.match(await page.locator('#documentList').innerText(),/已解析，可检索/);
    await page.getByRole('link',{name:'问答',exact:true}).click();
    await page.locator('#chatInput').fill('拓扑排序如何选择顶点？');
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.ai-message:not(.loading-message)')?.textContent.includes('受控问答'));
    assert.match(await page.locator('.ai-message').last().innerText(),/入度为零/);
    await page.locator('.ai-message .workflow-details summary').first().click();
    assert.match(await page.locator('.ai-message .workflow-details').first().innerText(),/原文和引用位置已核对/);
    assert.match(await page.locator('#engineStatus').innerText(),/MiMo 在线/);
    await page.locator('.ai-message .citation-chip').first().click();
    assert.match(await page.locator('#sourceContent').innerText(),/协作验证.md/);
    await page.getByRole('button',{name:'关闭原文',exact:true}).click();
    await page.getByRole('link',{name:'练习',exact:true}).click();
    await page.waitForFunction(()=>document.querySelectorAll('#practiceModule .practice-row').length>0);
    await page.locator('#practiceModule .practice-row').first().click();
    await page.locator('#practiceModule .practice-note-input').fill('叶绿体是光合作用的场所。');
    await page.waitForTimeout(1400);
    await page.reload();
    await page.locator('#practiceModule .practice-row').first().click();
    assert.match(await page.locator('#practiceModule .practice-note-input').inputValue(),/叶绿体/);

    // The existing follow-up button must retain actual evidence through MCP.
    await page.getByRole('link',{name:'问答',exact:true}).click();
    await page.locator('.ai-message [data-followup]').last().click();
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();
    assert.match(await page.locator('.ai-message').last().innerText(),/受控问答.*入度为零/s);
    await page.locator('.ai-message .workflow-details summary').last().click();
    assert.match(await page.locator('.ai-message .workflow-details').last().innerText(),/上一轮/);
    assert.match(await page.locator('.ai-message .citation-chip').last().innerText(),/协作验证.md/);

    // Stop a real in-flight model request and retry without saving partial content.
    await page.locator('#chatInput').fill('请慢一点解释拓扑排序');
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('.ai-message .message-body')].at(-1)?.textContent.includes('尚未校验'));
    await page.getByRole('button',{name:'停止生成',exact:true}).click();
    await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();
    assert.match(await page.locator('.ai-message').last().innerText(),/已停止生成/);
    assert.equal(await page.locator('.ai-message').last().locator('.citation-chip,[data-save-message]').count(),0);
    assert.equal(await page.locator('#chatInput').inputValue(),'请慢一点解释拓扑排序');
    let cancellationTimer;
    try{assert.equal(await Promise.race([modelCancelled,new Promise((resolve,reject)=>{cancellationTimer=setTimeout(()=>reject(new Error('Stop button did not cancel server model')),1500);})]),true);}finally{clearTimeout(cancellationTimer);}
    assert.equal((await page.evaluate(()=>JSON.parse(localStorage.getItem('xueya-copilot-state-v2')).messages.at(-1))).text.includes('尚未校验'),false);
    await page.locator('#chatInput').fill('拓扑排序如何选择顶点？');
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();
    assert.match(await page.locator('.ai-message').last().innerText(),/受控问答/);

    // Force server failure: the same uploaded passage must remain available offline.
    await page.route('**/api/agent/stream',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:false,error:'AI_UNAVAILABLE',engine:'local-fallback'})}));
    await page.getByRole('link',{name:'问答',exact:true}).click();
    await page.getByRole('button',{name:'知识整理',exact:true}).click();
    await page.locator('#chatInput').fill('拓扑排序如何更新入度？');
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('.ai-message')].at(-1)?.textContent.includes('本地检索摘录'));
    assert.match(await page.locator('.ai-message').last().innerText(),/本地检索摘录/);
    assert.match(await page.locator('#engineStatus').innerText(),/本地检索模式/);
    await page.unroute('**/api/agent/stream');

    // PRD 4-8: the fixed bank, mutually exclusive status, auto wrong-book, and 错题重练.
    await page.getByRole('link',{name:'练习',exact:true}).click();
    await page.waitForFunction(()=>document.querySelectorAll('#practiceModule .practice-row').length>0);
    await page.locator('#practiceModule .practice-row').first().click();
    await page.locator('#practiceModule [data-action=language][data-language=cpp]').click();
    assert.match(await page.locator('#practiceModule .practice-code').innerText(),/class|vector|int/);
    await page.locator('#practiceModule .practice-option').first().click();
    await page.locator('#practiceModule [data-action=mark-wrong]').click();
    await page.locator('#practiceModule .practice-note-input').fill('这里容易搞混。');
    await page.waitForTimeout(1400);
    await page.getByRole('link',{name:'复习',exact:true}).click();
    await page.waitForFunction(()=>document.querySelectorAll('#practiceModule .practice-row').length>0);
    await page.locator('#practiceModule .practice-row').first().click();
    assert.match(await page.locator('#practiceModule .practice-note-input').inputValue(),/容易搞混/);
    await page.locator('#practiceModule [data-action=conquer]').click();
    await page.reload();
    await page.locator('.space-nav [data-view=knowledge]').click();
    await page.locator('#fileInput').setInputFiles([
      {name:'生物讲义.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:sampleDocx()},
      {name:'photosynthesis.pdf',mimeType:'application/pdf',buffer:samplePdf()}
    ]);
    await page.waitForFunction(()=>[...document.querySelectorAll('.document-row')].filter(row=>row.textContent.includes('已解析，可检索')).length===3);
    const docx=page.locator('.document-row').filter({hasText:'生物讲义.docx'});
    await docx.locator('[data-document]').click();
    assert.match(await page.locator('#sourceContent').innerText(),/叶绿体/);
    await page.getByRole('button',{name:'关闭原文',exact:true}).click();
    await page.getByRole('link',{name:'复习',exact:true}).click();
    await page.getByRole('link',{name:'复习',exact:true}).click();
    await page.waitForFunction(()=>!!document.querySelector('#practiceModule'));
    await page.getByRole('link',{name:'问答',exact:true}).click();
    await page.route('**/api/agent/stream',route=>route.abort('failed'));
    await page.locator('#chatInput').fill('帮我安排一份复习计划');
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();
    assert.match(await page.locator('.ai-message').last().innerText(),/尚未修改/);
    await page.locator('.ai-message .workflow-details summary').last().click();
    assert.match(await page.locator('.ai-message .workflow-details').last().innerText(),/本地学习记录/);
    const offlineState=await page.evaluate(()=>JSON.parse(localStorage.getItem('xueya-copilot-state-v2')));
    assert.equal(offlineState.messages.at(-1).artifacts.progress.total,offlineState.records.length);
    assert.deepEqual(offlineState.plan,savedPlan);
    await page.unroute('**/api/agent/stream');
    await page.getByRole('button',{name:'搜索资料与操作',exact:true}).click();
    await page.locator('#searchInput').fill('协作验证');
    assert.match(await page.locator('#searchResults').innerText(),/协作验证.md/);
    await page.getByRole('button',{name:'关闭搜索',exact:true}).click();
    assert.equal(await page.locator('#searchDialog').evaluate(dialog=>dialog.open),false);

    for(const width of [1440,768,375]){
      await page.setViewportSize({width,height:900});
      for(const view of ['overview','chat','library','cards','practice','memory','plan']){
        await page.goto(base+'/#space/'+view);
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,view+' overflows at '+width);
      }
    }
    await page.goto(base+'/#home');
    await page.locator('.hero h1').waitFor({state:'visible'});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(outputDirectory,'regression-mobile.png'),animations:'disabled'});
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:path.join(outputDirectory,'regression-desktop.png'),animations:'disabled'});
    await page.goto(base+'/#space/ask');
    await page.locator('#chatInput').waitFor({state:'visible'});
    await page.screenshot({path:path.join(outputDirectory,'regression-chat.png')});
    await page.goto(base+'/#space/review');
    await page.waitForFunction(()=>!!document.querySelector('#practiceModule'));
    await page.screenshot({path:path.join(outputDirectory,'regression-memory.png'),animations:'disabled'});
    assert.deepEqual(errors,[]);

    // Verify the advertised direct-file preview after splitting shared scripts.
    const filePage=await browser.newPage();
    const fileErrors=[],apiRequests=[];
    filePage.on('pageerror',error=>fileErrors.push(error.message));
    filePage.on('request',request=>{if(/^https?:/.test(request.url())&&request.url().includes('/api/'))apiRequests.push(request.url());});
    await filePage.goto(pathToFileURL(path.join(root,'frontend/index.html')).href+'#space/ask');
    await filePage.locator('#chatInput').fill('二叉搜索树的查找复杂度？');
    await filePage.getByRole('button',{name:'发送问题',exact:true}).click();
    await filePage.waitForSelector('.ai-message:not(.loading-message)');
    assert.match(await filePage.locator('.ai-message').innerText(),/本地检索摘录/);
    assert.match(await filePage.locator('.ai-message').innerText(),/O\(h\)/);
    await filePage.locator('#chatInput').fill('帮我安排一份复习计划');
    await filePage.getByRole('button',{name:'发送问题',exact:true}).click();
    await filePage.getByRole('button',{name:'发送问题',exact:true}).waitFor();
    await filePage.waitForFunction(()=>[...document.querySelectorAll('.ai-message .message-body')].at(-1)?.textContent.length>0);
    assert.match(await filePage.locator('.ai-message').last().innerText(),/尚未修改/);
    assert.deepEqual(apiRequests,[]);
    assert.deepEqual(fileErrors,[]);
    console.log('Browser passed: real MCP workflow, repeated follow-up evidence, stop cancels model, retry after stop, offline and file-preview study plans without saving, TXT/MD/PDF/DOCX, citations, cards, fallback, AI question bank, memory, practice, plan persistence, search and responsive pages.');
  }finally{
    if(browser)await browser.close();
    await server.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
