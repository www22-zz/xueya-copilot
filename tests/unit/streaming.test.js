const test=require('node:test');
const assert=require('node:assert/strict');
const {readSSE}=require('../../shared/agent/sse.js');
const {createChatService}=require('../../frontend/js/services/chat-service.js');
const {prepareDocument}=require('../../frontend/js/services/library-service.js');
const {createPracticeClient}=require('../../frontend/js/services/practice-client.js');
const L=require('../../shared/learning.js');

function body(text,step=1){
  const bytes=new TextEncoder().encode(text);
  return new ReadableStream({start(controller){for(let i=0;i<bytes.length;i+=step)controller.enqueue(bytes.slice(i,i+step));controller.close();}});
}
const event=value=>'data: '+JSON.stringify(value)+'\n\n';

test('SSE framing preserves split UTF-8, CRLF, comments, multiline data and a final partial frame',async()=>{
  const text=': keepalive\r\n\r\ndata: {"answer":\r\ndata: "中文原文"}\r\n\r\ndata: [DONE]';
  const data=[];
  for await(const item of readSSE(body(text)))data.push(item);
  assert.deepEqual(JSON.parse(data[0]),{answer:'中文原文'});
  assert.equal(data[1],'[DONE]');
});

test('streamed chat renders answer text and accepts only a validated completion with known citations',async()=>{
  let sent,updates=[];
  const content=event({type:'content',text:'{"answer":"查找需要'})
    +event({type:'content',text:' O(h)。","sources":["source-1"]}'})
    +event({type:'done',ok:true,answer:'查找需要 O(h)。',sources:['source-1','forged'],knowledgePoints:[],model:'controlled'});
  const service=createChatService({fetchImpl:async(url,options)=>{
    assert.equal(url,'/api/ai/stream');sent=JSON.parse(options.body);
    return new Response(body(content),{headers:{'Content-Type':'text/event-stream'}});
  }});
  const result=await service.stream({question:'二叉搜索树的查找复杂度？',sources:L.sources},{onUpdate:update=>updates.push(update)});
  assert.equal(result.online,true);
  assert.deepEqual(result.sources.map(source=>source.id),['source-1']);
  assert.ok(updates.some(update=>update.answer.includes('查找需要')));
  assert.equal(updates.some(update=>update.answer.includes('"answer"')),false);
  assert.equal(sent.sources[0].id,'source-1');
});

test('stream EOF, malformed events and server errors show failure while retaining reference passages',async()=>{
  const cases=[event({type:'content',text:'{"answer":"半段回答'}),'data: broken JSON\n\n',event({type:'error',error:'AI_UNAVAILABLE'})];
  for(const stream of cases){
    const service=createChatService({fetchImpl:async()=>new Response(body(stream),{headers:{'Content-Type':'text/event-stream'}})});
    const result=await service.stream({question:'二叉搜索树的查找复杂度？',sources:L.sources});
    assert.equal(result.online,false);
    assert.equal(result.answerStatus,'unavailable');
    assert.equal(result.engine,'回答未完成');
    assert.equal(result.answer.includes(result.sources[0]?.quote),false);
    assert.equal(result.answer.includes('半段回答'),false);
    assert.ok(result.sources.length);
  }
});

test('PDF/DOCX browser service sends binary data, handles empty text and retains file preview fallback',async()=>{
  const file=new File(['binary'],'讲义.docx');
  const doc=await prepareDocument(file,{fetchImpl:async(url,options)=>{
    assert.equal(url,'/api/parse?type=docx');assert.ok(options.body instanceof ArrayBuffer);
    return new Response(JSON.stringify({ok:true,text:'光合作用发生在叶绿体。',kind:'docx'}));
  }});
  assert.equal(doc.status,'已解析，可检索');
  assert.match(doc.chunks[0].quote,/叶绿体/);
  const empty=await prepareDocument(file,{fetchImpl:async()=>new Response(JSON.stringify({ok:true,text:'',empty:true}))});
  assert.equal(empty.status,'未识别到文字');
  const local=await prepareDocument(file,{protocol:'file:',fetchImpl:async()=>assert.fail('file preview contacted parse API')});
  assert.equal(local.status,'内容待解析');
});

test('fixed practice client loads the built-in bank and uses its cached copy offline',async()=>{
  const cache=new Map(),storage={getItem:k=>cache.get(k),setItem:(k,v)=>cache.set(k,v)};
  const service=createPracticeClient({storage,request:async(path)=>{
    if(path==='/api/account/status')return {ok:true,configured:false,authenticated:true};
    if(path==='/api/platform/bootstrap')return {ok:true,token:'controlled'};
    if(path==='/api/practice/bank')return {ok:true,version:'test-bank',questions:[{id:'h100-01'}]};
    return {ok:true,statuses:{},notes:{},serverSeq:0};
  }});
  await service.initialize();assert.equal(service.bank()[0].id,'h100-01');
  const offline=createPracticeClient({storage,request:async()=>{throw Error('offline');}});
  await offline.initialize();assert.equal(offline.bank()[0].id,'h100-01');assert.equal(offline.online,false);
});

test('workspace practice rejects an old backend and incomplete cached bank instead of an empty 408 list',async()=>{
  const cache=new Map(),storage={getItem:k=>cache.get(k),setItem:(k,v)=>cache.set(k,v)};
  const request=async path=>path==='/api/account/status'?{ok:true,configured:false}:path==='/api/platform/bootstrap'?{ok:true,token:'controlled'}:path.includes('/bank')?{ok:true,version:'old',questions:[{id:'h100-01',category:'hot100'}]}:{ok:true,statuses:{},notes:{},serverSeq:0};
  cache.set('xueya-practice-bank:local:workspace-v1',JSON.stringify({version:'bad-cache',questions:[{id:'h100-01'}]}));
  const outdated=createPracticeClient({storage,request,workspaceMode:true});
  await assert.rejects(outdated.initialize(),{code:'WORKSPACE_BANK_OUTDATED'});
  assert.equal(outdated.bank().length,0);
  const questions=[...Array.from({length:100},(_,i)=>({id:'h'+i,bankSource:'algorithm'})),...Array.from({length:300},(_,i)=>({id:'e'+i,bankSource:'exam408'}))];
  const current=createPracticeClient({storage,workspaceMode:true,request:async path=>path.includes('/bank')?{ok:true,version:'current',questions}:request(path)});
  await current.initialize();
  const offline=createPracticeClient({storage,workspaceMode:true,request:async()=>{throw Error('offline');}});
  await offline.initialize();
  assert.equal(offline.bank().filter(q=>q.bankSource==='exam408').length,300);
  assert.equal(offline.online,false);
});

test('offline workflow keeps real learning analysis and plan preview instead of course excerpts',async()=>{
  for(const protocol of ['file:','http:']){
    const service=createChatService({protocol,fetchImpl:async()=>{throw new Error('offline');}});
    const input={question:'帮我安排一份复习计划',sources:L.sources,learning:{questions:L.questions,records:[{questionId:'q3',correct:false,createdAt:new Date().toISOString()}],examDate:L.addDays(L.today(),3),minutes:45}};
    const result=await service.stream(input,{workflow:true});
    assert.equal(result.online,false);
    assert.equal(result.workflow?.intent,'plan');
    assert.equal(result.artifacts?.progress.total,1);
    assert.deepEqual(result.artifacts.progress.weakTopics,['中序遍历']);
    assert.equal(result.artifacts.plan.days[0].tasks.reduce((sum,task)=>sum+task.minutes,0),45);
    assert.match(result.answer,/尚未修改/);
    assert.deepEqual(result.sources,[]);
    assert.equal(input.learning.minutes,45);
  }
});

test('browser stream cancellation rejects without offline fallback and releases a blocked reader',async()=>{
  const controller=new AbortController();let cancelled=false,requestSignal;
  const stream=new ReadableStream({start(target){target.enqueue(new TextEncoder().encode(event({type:'content',text:'{"answer":"未验证的半段'})));},cancel(){cancelled=true;}});
  const service=createChatService({fetchImpl:async(url,options)=>{requestSignal=options.signal;return new Response(stream,{headers:{'Content-Type':'text/event-stream'}});}});
  const pending=service.stream({question:'二叉搜索树',sources:L.sources},{signal:controller.signal,onUpdate(){controller.abort();}});
  await assert.rejects(pending,error=>error.name==='AbortError');
  assert.equal(requestSignal.aborted,true);
  assert.equal(cancelled,true);
});

test('an already cancelled chat never sends a request',async()=>{
  const controller=new AbortController();controller.abort();
  const service=createChatService({fetchImpl:async()=>assert.fail('request sent after cancellation')});
  await assert.rejects(service.stream({question:'问题',sources:L.sources},{signal:controller.signal}),error=>error.name==='AbortError');
});

test('SSE rejects a complete oversized event and cancels a reader blocked before its first frame',async()=>{
  await assert.rejects(async()=>{for await(const data of readSSE(body('data: '+'x'.repeat(1048577)+'\n\n',2097152)))assert.fail('accepted oversized frame');},/STREAM_TOO_LARGE/);
  const controller=new AbortController();let cancelled=false;
  const blocked=new ReadableStream({cancel(){cancelled=true;}});
  const pending=(async()=>{for await(const data of readSSE(blocked,{signal:controller.signal}))assert.fail('unexpected frame');})();
  controller.abort();
  await assert.rejects(pending,error=>error.name==='AbortError');
  assert.equal(cancelled,true);
});

test('workflow browser includes valid previous sources but does not resurrect deleted materials',async()=>{
  for(const sources of [L.sources,[]]){
    let sent;
    const service=createChatService({fetchImpl:async(url,options)=>{
      sent=JSON.parse(options.body);throw new Error('offline');
    }});
    const result=await service.stream({question:'再解释一下',sources,previousSources:[L.sources[0]]},{workflow:true});
    assert.deepEqual(sent.context.previousSourceIds,sources.length?['source-1']:[]);
    assert.deepEqual(result.sources.map(source=>source.id),sources.length?['source-1']:[]);
  }
});

test('stream timeout falls back locally while a user cancellation wins over a queued completion',async()=>{
  const stalled=createChatService({streamTimeoutMs:15,fetchImpl:async()=>new Response(new ReadableStream(),{headers:{'Content-Type':'text/event-stream'}})});
  const result=await stalled.stream({question:'二叉搜索树',sources:L.sources});
  assert.equal(result.online,false);
  assert.ok(result.sources.length);
  const controller=new AbortController();
  const service=createChatService({fetchImpl:async()=>new Response(body(event({type:'content',text:'{"answer":"partial'})+event({type:'done',ok:true,answer:'should be cancelled',sources:[]})),{headers:{'Content-Type':'text/event-stream'}})});
  await assert.rejects(service.stream({question:'二叉搜索树',sources:L.sources},{signal:controller.signal,onUpdate(){controller.abort();}}),error=>error.name==='AbortError');
});
