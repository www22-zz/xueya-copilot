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
    for(const asset of ['/css/styles.css','/js/app.js','/js/visual.js','/shared/learning.js','/assets/mark.svg'])assert.equal((await fetch(base+asset)).status,200,asset);
    assert.match(html,/css\/styles\.css/);assert.match(html,/shared\/learning\.js/);assert.match(html,/js\/app\.js/);
    assert.equal((await fetch(base+'/css/styles.css',{method:'HEAD'})).status,200);
    assert.equal((await fetch(base+'/api/ai',{method:'POST',body:'{'})).status,400);
    const empty=await (await fetch(base+'/api/ai',{method:'POST',body:JSON.stringify({question:'无资料问题',sources:[]})})).json();assert.equal(empty.error,'NO_SOURCES');
  }finally{await new Promise(r=>server.close(r));await new Promise(r=>upstream.close(r));}
});
