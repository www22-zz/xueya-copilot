const test=require('node:test'),assert=require('node:assert/strict'),http=require('node:http');
// Controlled local upstream exercises the proxy without calling a paid service.
let observed;
const upstream=http.createServer((req,res)=>{let body='';req.on('data',c=>body+=c);req.on('end',()=>{observed=JSON.parse(body);res.setHeader('Content-Type','application/json');res.end(JSON.stringify({choices:[{message:{content:JSON.stringify({answer:'光合作用发生在叶绿体。',sources:['custom-1','invented-source']})}}]}));});});
test('proxy carries text and history, validates citations, and protects private files',async()=>{
  await new Promise(r=>upstream.listen(0,'127.0.0.1',r));
  process.env.MIMO_API_KEY='local-test-only';process.env.MIMO_BASE_URL=`http://127.0.0.1:${upstream.address().port}`;
  const {server}=require('../../backend/server.js');await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
  try{
    const response=await fetch(base+'/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:'它发生在哪里？',sources:[{id:'custom-1',title:'生物笔记',quote:'光合作用发生在叶绿体。'}],history:[{role:'user',content:'光合作用'}]})});
    const result=await response.json();assert.equal(result.ok,true);assert.deepEqual(result.sources,['custom-1']);assert.equal(observed.messages[1].content,'光合作用');assert.match(observed.messages.at(-1).content,/叶绿体/);
    for(const file of ['/.env','/.git/config','/backend/server.js','/README.md','/docs/verification.md','/shared/private.js'])assert.equal((await fetch(base+file)).status,404);
    const homepage=await fetch(base+'/');assert.equal(homepage.status,200);
    const html=await homepage.text();
    for(const asset of ['/css/styles.css','/js/app.js','/js/visual.js','/js/motion.js','/js/pointer.js','/shared/learning.js','/assets/mark.svg'])assert.equal((await fetch(base+asset)).status,200,asset);
    assert.match(html,/css\/styles\.css/);assert.match(html,/shared\/learning\.js/);assert.match(html,/js\/app\.js/);
    assert.equal((await fetch(base+'/css/styles.css',{method:'HEAD'})).status,200);
    assert.equal((await fetch(base+'/api/ai',{method:'POST',body:'{'})).status,400);
    const empty=await (await fetch(base+'/api/ai',{method:'POST',body:JSON.stringify({question:'无资料问题',sources:[]})})).json();assert.equal(empty.error,'NO_SOURCES');
  }finally{await new Promise(r=>server.close(r));await new Promise(r=>upstream.close(r));}
});
test('question endpoint returns validated questions from the model',async()=>{
  const qUpstream=http.createServer((req,res)=>{let body='';req.on('data',c=>body+=c);req.on('end',()=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify({choices:[{message:{content:JSON.stringify([{topic:'树',prompt:'二叉树的查找复杂度是？',options:['O(1)','O(h)','O(n²)'],answer:1,explanation:'查找沿一条路径进行。',sourceId:'invented'},{topic:'坏题',prompt:'无选项',options:[],answer:9,explanation:'',sourceId:'custom-1'}])}}]}));});});
  await new Promise(r=>qUpstream.listen(0,'127.0.0.1',r));
  process.env.MIMO_API_KEY='local-test-only';process.env.MIMO_BASE_URL=`http://127.0.0.1:${qUpstream.address().port}`;
  delete require.cache[require.resolve('../../backend/server.js')];
  const {server}=require('../../backend/server.js');await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
  try{
    const result=await (await fetch(base+'/api/questions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sources:[{id:'custom-1',title:'笔记',quote:'内容'}],count:3})})).json();
    assert.equal(result.ok,true);
    assert.equal(result.questions.length,1);
    assert.equal(result.questions[0].sourceId,'custom-1');
    assert.equal(result.questions[0].answer,1);
    const noSources=await (await fetch(base+'/api/questions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sources:[]})})).json();
    assert.equal(noSources.error,'NO_SOURCES');
  }finally{await new Promise(r=>server.close(r));await new Promise(r=>qUpstream.close(r));}
});
test('streaming endpoint emits content, filters invented citations, and finishes',async()=>{
  const streamUpstream=http.createServer((req,res)=>{let body='';req.on('data',c=>body+=c);req.on('end',()=>{res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify({choices:[{delta:{content:'{"answer":"光合作用发生'}}]})+'\n\n');res.write('data: '+JSON.stringify({choices:[{delta:{content:'在叶绿体。","sources":["custom-1","invented"],"knowledgePoints":["光合作用"]}'}}]})+'\n\n');res.end();});});
  await new Promise(r=>streamUpstream.listen(0,'127.0.0.1',r));
  process.env.MIMO_API_KEY='local-test-only';process.env.MIMO_BASE_URL=`http://127.0.0.1:${streamUpstream.address().port}`;
  delete require.cache[require.resolve('../../backend/server.js')];
  const {server}=require('../../backend/server.js');await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
  try{
    const response=await fetch(base+'/api/ai/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:'它发生在哪里？',sources:[{id:'custom-1',title:'生物笔记',quote:'光合作用发生在叶绿体。'}]})});
    assert.match(response.headers.get('content-type'),/text\/event-stream/);
    const events=(await response.text()).split(/\n\n/).map(s=>s.trim()).filter(Boolean).filter(s=>s.startsWith('data: ')).map(s=>JSON.parse(s.slice(6)));
    assert.equal(JSON.parse(events.filter(e=>e.type==='content').map(e=>e.text).join('')).answer,'光合作用发生在叶绿体。');
    const done=events.find(e=>e.type==='done');
    assert.equal(done.ok,true);
    assert.deepEqual(done.sources,['custom-1']);
    assert.equal(events.some(e=>e.type==='error'),false);
  }finally{server.closeAllConnections?.();await new Promise(r=>server.close(r));await new Promise(r=>streamUpstream.close(r));}
});
test('topics endpoint extracts and cleans knowledge points from the material',async()=>{
  const topicsUpstream=http.createServer((req,res)=>{let body='';req.on('data',c=>body+=c);req.on('end',()=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify({choices:[{message:{content:JSON.stringify([{name:'树的高度',sourceId:'custom-1'},{name:'树的遍历',sourceId:'invented'},{name:'树的高度',sourceId:'custom-1'}])}}]}));});});
  await new Promise(r=>topicsUpstream.listen(0,'127.0.0.1',r));
  process.env.MIMO_API_KEY='local-test-only';process.env.MIMO_BASE_URL=`http://127.0.0.1:${topicsUpstream.address().port}`;
  delete require.cache[require.resolve('../../backend/server.js')];
  const {server}=require('../../backend/server.js');await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
  try{
    const result=await (await fetch(base+'/api/topics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sources:[{id:'custom-1',title:'笔记',quote:'内容'}]})})).json();
    assert.equal(result.ok,true);
    assert.equal(result.topics.length,2);
    assert.equal(result.topics[0].name,'树的高度');
    assert.equal(result.topics[0].sourceId,'custom-1');
    assert.equal(result.topics[1].sourceId,'custom-1');
    const none=await (await fetch(base+'/api/topics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sources:[]})})).json();
    assert.equal(none.error,'NO_SOURCES');
  }finally{server.closeAllConnections?.();await new Promise(r=>server.close(r));await new Promise(r=>topicsUpstream.close(r));}
});
