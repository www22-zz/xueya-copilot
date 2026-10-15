const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');
const {createApp}=require('../../backend/app.js');
const {sampleDocx,samplePdf}=require('../fixtures/documents.js');
const root=path.resolve(__dirname,'../..');
const outputDirectory=path.join(root,'test-results/browser');

(async()=>{
  // Controlled model exercises the complete application without a key or paid calls.
  const config={root,ai:{apiKey:'browser-test-only',model:'controlled'}};
  const model={generate:async({messages})=>{
    const {materials}=JSON.parse(messages.at(-1).content);
    const source=materials.find(item=>item.title==='协作验证.md')||materials[0];
    if(messages[0].content.includes('知识点整理助手'))return{model:'controlled',content:JSON.stringify([{name:'拓扑排序',sourceId:source.id},{name:'入度',sourceId:source.id}])};
    if(messages[0].content.includes('出题助手'))return{model:'controlled',content:JSON.stringify([{topic:'拓扑排序',prompt:'拓扑排序首先选择哪类顶点？',options:['入度为零的顶点','出度最大的顶点','任意顶点','编号最大的顶点'],answer:0,explanation:'每轮选择入度为零的顶点。',sourceId:source.id}])};
    return{model:'controlled',content:JSON.stringify({answer:'受控问答：'+source.quote,sources:[source.id],knowledgePoints:[]})};
  }};
  model.stream=async function*({messages}){
    const response=await model.generate({messages});
    for(let offset=0;offset<response.content.length;offset+=12)yield{type:'content',text:response.content.slice(offset,offset+12),model:'controlled'};
  };
  const server=http.createServer(createApp({config,model}));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base='http://127.0.0.1:'+server.address().port;
  let browser;
  try{
    const options={headless:true};
    if(process.env.CHROME_PATH)options.executablePath=process.env.CHROME_PATH;
    browser=await chromium.launch(options);
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    fs.mkdirSync(outputDirectory,{recursive:true});
    await page.goto(base+'/');
    assert.equal(await page.locator('.hero h1').innerText(),'资料，读得懂。\n知识，用得上。');
    await page.getByRole('tab',{name:'记得牢固'}).click();
    assert.match(await page.locator('#demoContent').innerText(),/知识卡片/);
    await page.getByRole('link',{name:'进入学习空间',exact:true}).click();

    await page.getByRole('link',{name:/课程资料/}).first().click();
    await page.locator('#fileInput').setInputFiles({name:'协作验证.md',mimeType:'text/markdown',buffer:Buffer.from('拓扑排序每轮选择入度为零的顶点，移除该顶点和出边，再更新相邻顶点的入度。')});
    await page.waitForFunction(()=>document.querySelector('#documentList')?.textContent.includes('协作验证.md'));
    assert.match(await page.locator('#documentList').innerText(),/已解析，可检索/);
    await page.getByRole('link',{name:'资料问答',exact:true}).click();
    await page.locator('#chatInput').fill('拓扑排序如何选择顶点？');
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.ai-message:not(.loading-message)')?.textContent.includes('受控问答'));
    assert.match(await page.locator('.ai-message').last().innerText(),/入度为零/);
    assert.match(await page.locator('#engineStatus').innerText(),/MiMo 在线/);
    await page.locator('.ai-message .citation-chip').first().click();
    assert.match(await page.locator('#sourceContent').innerText(),/协作验证.md/);
    await page.locator('#sourceSave').click();
    await page.getByRole('button',{name:'关闭原文',exact:true}).click();
    await page.getByRole('link',{name:'知识卡片',exact:true}).click();
    assert.match(await page.locator('#cardList').innerText(),/拓扑排序/);
    await page.reload();
    assert.match(await page.locator('#cardList').innerText(),/拓扑排序/);

    // Force server failure: the same uploaded passage must remain available offline.
    await page.route('**/api/ai/stream',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:false,error:'AI_UNAVAILABLE',engine:'local-fallback'})}));
    await page.getByRole('link',{name:'资料问答',exact:true}).click();
    await page.getByRole('button',{name:'知识整理',exact:true}).click();
    await page.locator('#chatInput').fill('拓扑排序如何更新入度？');
    await page.getByRole('button',{name:'发送问题',exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('.ai-message')].at(-1)?.textContent.includes('本地检索摘录'));
    assert.match(await page.locator('.ai-message').last().innerText(),/本地检索摘录/);
    assert.match(await page.locator('.ai-message').last().innerText(),/知识卡片：/);
    assert.match(await page.locator('#engineStatus').innerText(),/本地检索模式/);

    await page.getByRole('link',{name:'练习与错题',exact:true}).click();
    await page.locator('[data-option="0"]').click();
    await page.getByRole('button',{name:'提交答案',exact:true}).click();
    assert.match(await page.locator('.quiz-feedback').innerText(),/再学一次/);
    await page.getByRole('link',{name:'记忆卡片',exact:true}).click();
    const memoryCard=page.locator('.memory-card').filter({hasText:'树的高度'});
    assert.match(await memoryCard.innerText(),/答错 1 次/);
    await memoryCard.getByRole('button',{name:'去练一题',exact:true}).click();
    await page.locator('[data-option="1"]').click();
    await page.getByRole('button',{name:'提交答案',exact:true}).click();
    assert.match(await page.locator('.quiz-feedback').innerText(),/回答正确/);

    await page.getByRole('button',{name:/^AI 题库/}).click();
    await page.locator('.quiz-panel [data-open-bank-dialog]').click();
    await page.locator('#bankTopics input[data-topic="拓扑排序"]').check();
    await page.getByRole('button',{name:'生成 1 个知识点的题目',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.question-topic')?.textContent.includes('AI 生成'));
    assert.match(await page.locator('.quiz-panel h2').innerText(),/拓扑排序/);
    await page.locator('[data-option="1"]').click();
    await page.getByRole('button',{name:'提交答案',exact:true}).click();
    assert.match(await page.locator('.quiz-feedback').innerText(),/再学一次/);
    await page.getByRole('button',{name:'错题回顾 (1)',exact:true}).click();
    assert.match(await page.locator('.quiz-panel h2').innerText(),/拓扑排序/);
    await page.getByRole('link',{name:'记忆卡片',exact:true}).click();
    const bankMemory=page.locator('.memory-card').filter({hasText:'拓扑排序'});
    assert.match(await bankMemory.innerText(),/答错 1 次/);
    await bankMemory.getByRole('button',{name:'去练一题',exact:true}).click();
    await page.locator('[data-option="0"]').click();
    await page.getByRole('button',{name:'提交答案',exact:true}).click();
    assert.match(await page.locator('.quiz-feedback').innerText(),/回答正确/);
    await page.reload();
    await page.getByRole('button',{name:'AI 题库 (1)',exact:true}).click();
    assert.match(await page.locator('.quiz-panel h2').innerText(),/拓扑排序/);

    await page.getByRole('link',{name:/课程资料/}).first().click();
    await page.locator('#fileInput').setInputFiles([
      {name:'生物讲义.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:sampleDocx()},
      {name:'photosynthesis.pdf',mimeType:'application/pdf',buffer:samplePdf()}
    ]);
    await page.waitForFunction(()=>[...document.querySelectorAll('.document-row')].filter(row=>row.textContent.includes('已解析，可检索')).length===3);
    const docx=page.locator('.document-row').filter({hasText:'生物讲义.docx'});
    await docx.locator('[data-document]').click();
    assert.match(await page.locator('#sourceContent').innerText(),/叶绿体/);
    await page.getByRole('button',{name:'关闭原文',exact:true}).click();
    await page.getByRole('link',{name:'复习计划',exact:true}).click();
    await page.locator('[data-task]').first().check();
    await page.reload();
    assert.equal(await page.locator('[data-task]').first().isChecked(),true);
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
    await page.goto(base+'/#space/chat');
    await page.locator('#chatInput').waitFor({state:'visible'});
    await page.screenshot({path:path.join(outputDirectory,'regression-chat.png')});
    await page.goto(base+'/#space/memory');
    await page.locator('.memory-card').first().waitFor({state:'visible'});
    await page.screenshot({path:path.join(outputDirectory,'regression-memory.png'),animations:'disabled'});
    assert.deepEqual(errors,[]);

    // Verify the advertised direct-file preview after splitting shared scripts.
    const filePage=await browser.newPage();
    const fileErrors=[],apiRequests=[];
    filePage.on('pageerror',error=>fileErrors.push(error.message));
    filePage.on('request',request=>{if(/^https?:/.test(request.url())&&request.url().includes('/api/'))apiRequests.push(request.url());});
    await filePage.goto(pathToFileURL(path.join(root,'frontend/index.html')).href+'#space/chat');
    await filePage.locator('#chatInput').fill('二叉搜索树的查找复杂度？');
    await filePage.getByRole('button',{name:'发送问题',exact:true}).click();
    await filePage.waitForSelector('.ai-message:not(.loading-message)');
    assert.match(await filePage.locator('.ai-message').innerText(),/本地检索摘录/);
    assert.match(await filePage.locator('.ai-message').innerText(),/O\(h\)/);
    assert.deepEqual(apiRequests,[]);
    assert.deepEqual(fileErrors,[]);
    console.log('Browser passed: TXT/MD/PDF/DOCX upload, streamed grounded answer, citations, cards, fallback, AI question bank, topic selection, memory cards, practice, plan persistence, search, responsive pages and direct-file preview.');
  }finally{
    if(browser)await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
