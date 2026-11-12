const test=require('node:test');
const assert=require('node:assert/strict');
const {createChatService,createTypewriter,prefersReducedMotion,applyStreamUpdate,requestSuggestions}=require('../../frontend/js/services/chat-service.js');
const rich=require('../../frontend/js/ui/rich-content.js');
const {createViews}=require('../../frontend/js/ui/workspace-views.js');
const L=require('../../shared/learning.js');

function body(text,step=1){
  const bytes=new TextEncoder().encode(text);
  return new ReadableStream({start(controller){for(let i=0;i<bytes.length;i+=step)controller.enqueue(bytes.slice(i,i+step));controller.close();}});
}
const event=value=>'data: '+JSON.stringify(value)+'\n\n';
const serviceFor=stream=>createChatService({fetchImpl:async()=>new Response(body(stream),{headers:{'Content-Type':'text/event-stream'}})});

async function streamResult(payload){
  return serviceFor(event({type:'done',...payload})).stream({question:'解释队列。',sources:[]},{});
}

test('the final-answer typewriter emits increasing partial text and ends with the exact answer',async()=>{
  const frames=[];
  const text='队列是一种先进先出的线性表，只允许在队尾插入、在队头删除。';
  const typewriter=createTypewriter({intervalMs:1,totalMs:8});
  const result=await typewriter.start(text,partial=>frames.push(partial));
  assert.equal(result,text);
  assert.ok(frames.length>2,'animation paints more than one partial frame');
  assert.equal(frames.at(-1),text);
  for(let index=1;index<frames.length;index++)assert.ok(frames[index].length>frames[index-1].length,'each frame reveals more text');
  assert.ok(frames[0].length<text.length,'the first frame is not the full answer');
  assert.equal(frames[0],text.slice(0,frames[0].length));
});

test('the typewriter respects reduced motion and an already painted verified prefix',async()=>{
  const instant=[];
  await createTypewriter({reducedMotion:true}).start('完整回答',partial=>instant.push(partial));
  assert.deepEqual(instant,['完整回答']);
  const frames=[];
  await createTypewriter({intervalMs:1,totalMs:20}).start('完整回答内容',partial=>frames.push(partial),{from:2});
  assert.equal(frames[0].slice(0,2),'完整','resumes after the prefix already shown by verified content events');
  assert.equal(frames.at(-1),'完整回答内容');
  assert.equal(prefersReducedMotion({matchMedia:()=>({matches:true})}),true);
  assert.equal(prefersReducedMotion({}),false);
});

test('an aborted typewriter settles on the exact final answer instead of hanging',async()=>{
  const controller=new AbortController();controller.abort();
  const frames=[];
  const answer=await createTypewriter({intervalMs:1,totalMs:20}).start('最终回答全文',partial=>frames.push(partial),{signal:controller.signal});
  assert.equal(answer,'最终回答全文');
  assert.deepEqual(frames,['最终回答全文']);
});

test('unverified draft text never becomes the answer text',()=>{
  const message={role:'ai',text:'',reasoning:'',sources:[]};
  applyStreamUpdate(message,{answer:'草稿原文第一段',draft:true,progress:'正在生成回答'});
  assert.equal(message.text,'','draft preview is not the answer area text');
  assert.equal(message.draft,true);
  assert.equal(message.organizing,true);
  assert.equal(message.progress,'正在生成回答');
  applyStreamUpdate(message,{answer:'草稿原文第一段第二段',draft:true,progress:'正在核对依据'});
  assert.equal(message.text,'');
  assert.equal(message.progress,'正在生成回答\n正在核对依据','workflow labels accumulate as thinking content');
  applyStreamUpdate(message,{answer:'最终回答。',draft:false,final:true});
  assert.equal(message.text,'','the final answer is revealed by the typewriter, not by the stream update');
  assert.equal(message.draft,false);
  assert.equal(message.organizing,false);
  applyStreamUpdate(message,{answer:'最终回答。'});
  assert.equal(message.text,'最终回答。');
});

test('reset and failure updates clear draft text while reasoning streams into the thinking panel',()=>{
  const message={role:'ai',text:'',reasoning:'',sources:[]};
  applyStreamUpdate(message,{answer:'旧草稿',draft:true});
  applyStreamUpdate(message,{answer:'',reasoning:'',draft:false});
  assert.equal(message.text,'');
  assert.equal(message.draft,false);
  applyStreamUpdate(message,{reasoning:'先分析队列的定义。'});
  assert.equal(message.reasoning,'先分析队列的定义。');
  applyStreamUpdate(message,{reasoning:'先分析队列的定义。再看操作。'});
  assert.equal(message.reasoning,'先分析队列的定义。再看操作。');
});

test('verified content-only streams still paint answer text through onUpdate',async()=>{
  const updates=[];
  const stream=event({type:'content',text:'{"answer":"查找需要'})
    +event({type:'content',text:' O(h)。","sources":[]}'})
    +event({type:'done',ok:true,engine:'xiaomi-mimo',answer:'查找需要 O(h)。',sources:[]});
  const message={role:'ai',text:'',reasoning:'',sources:[]};
  await serviceFor(stream).stream({question:'二叉搜索树的查找复杂度？',sources:[]},{onUpdate:update=>{applyStreamUpdate(message,update);updates.push(message.text);}});
  assert.deepEqual(updates,['查找需要','查找需要 O(h)。']);
  assert.equal(message.text,'查找需要 O(h)。');
});

test('draft and reasoning events from a real stream never leak into the answer text',async()=>{
  const stream=event({type:'reasoning',text:'先分析队列的定义。'})
    +event({type:'draft',text:'未核对的草稿原文',draft:true,progress:'正在组织答案'})
    +event({type:'draft',text:'未核对的草稿原文第二段',draft:true})
    +event({type:'done',ok:true,engine:'xiaomi-mimo',answer:'最终核对后的回答。',sources:[]});
  const message={role:'ai',text:'',reasoning:'',sources:[]};
  const seen=[];
  const result=await serviceFor(stream).stream({question:'解释队列。',sources:[]},{onUpdate:update=>{applyStreamUpdate(message,update);seen.push({...message});}});
  assert.equal(seen.some(snapshot=>String(snapshot.text).includes('未核对的草稿')),false);
  assert.equal(message.text,'','the final answer is revealed by the typewriter, not by draft text');
  assert.equal(message.reasoning,'先分析队列的定义。');
  assert.equal(result.answer,'最终核对后的回答。');
});

test('engine labels are generic and never carry model branding',async()=>{
  const cases=[
    [{engine:'xiaomi-mimo'},'资料问答'],
    [{engine:'general-chat'},'通用回答'],
    [{engine:'general-chat',fallback:{from:'course-rag',reason:'CLAIMS_NEED_REVIEW'}},'通用回答'],
    [{engine:'资料问答'},'资料问答'],
    [{engine:'通用回答'},'通用回答'],
    [{engine:'xiaomi-mimo',agent:{planRevision:1}},'AI 学习规划'],
    [{engine:'general-chat-unavailable'},'通用问答暂不可用'],
    [{engine:'assistant-info'},'应用信息']
  ];
  for(const [payload,expected] of cases){
    const result=await streamResult({ok:true,answer:'回答。',sources:[],knowledgePoints:[],...payload});
    assert.equal(result.engine,expected);
    assert.equal(result.engine.includes('MiMo'),false);
  }
  const fallback=await createChatService({fetchImpl:async()=>{throw new Error('offline');},protocol:'http:'}).stream({question:'二叉搜索树的查找复杂度？',sources:L.sources},{workflow:true});
  assert.equal(fallback.engine.includes('MiMo'),false);
});

test('done.suggestedQuestions is forwarded and capped at three strings',async()=>{
  const result=await streamResult({ok:true,engine:'xiaomi-mimo',answer:'回答。',sources:[],suggestedQuestions:['追问一','追问二','','追问三','追问四',42]});
  assert.deepEqual(result.suggestedQuestions,['追问一','追问二','追问三']);
  const absent=await streamResult({ok:true,engine:'xiaomi-mimo',answer:'回答。',sources:[]});
  assert.ok(!('suggestedQuestions'in absent));
});

test('LLM follow-up suggestions are fetched from /api/agent/suggestions with the agreed body',async()=>{
  const calls=[];
  const fetchImpl=async(url,options)=>{
    calls.push({url,body:JSON.parse(options.body),method:options.method});
    return new Response(JSON.stringify({ok:true,questions:['追问一','追问二','追问三']}),{status:200,headers:{'Content-Type':'application/json'}});
  };
  const history=[{role:'user',content:'解释队列。'}];
  const questions=await requestSuggestions({courseId:'course-default',question:'解释队列。',answer:'队列是先进先出。',history},{fetchImpl});
  assert.deepEqual(questions,['追问一','追问二','追问三']);
  assert.equal(calls.length,1);
  assert.equal(calls[0].url,'/api/agent/suggestions');
  assert.equal(calls[0].method,'POST');
  assert.deepEqual(calls[0].body,{question:'解释队列。',answer:'队列是先进先出。',history,courseId:'course-default'});
});

test('follow-up suggestion failures are ignored instead of blocking the answer',async()=>{
  const failing=[
    async()=>{throw new Error('offline');},
    async()=>new Response(JSON.stringify({ok:false,error:'AI_UNAVAILABLE'})),
    async()=>new Response('not json',{status:500}),
    async()=>new Response(JSON.stringify({ok:true,questions:[]})),
    async()=>new Response(JSON.stringify({ok:true,questions:['',42]}))
  ];
  for(const fetchImpl of failing){
    assert.equal(await requestSuggestions({question:'问题',answer:'回答',history:[]},{fetchImpl,timeoutMs:50}),null);
  }
  assert.equal(await requestSuggestions({question:'',answer:'回答'},{fetchImpl:async()=>assert.fail('no request for empty question')}),null);
});

function stateFor(messages){
  return{courses:[],courseId:'course-default',messages,sessions:[],sessionId:'session-1',pending:false,draft:'',followupIndex:null,
    sidebarAskOpen:false,sidebarAskText:'',sidebarAskDraft:'',webSearch:false,fastMode:false,mode:'ask',quizIndex:0,documents:[],selectedDocuments:[],suggestionOffset:0};
}
function viewsFor(state){
  const ctx={state,L,e:rich.escape,icon:()=>'',store:{},service:{capabilities:{}},rich,getAttachments:()=>[],getQueue:()=>[],getVoiceState:()=>({phase:'idle'})};
  return createViews(ctx,{titles:{},renders:{overview:()=>'',practice:()=>'',review:()=>''},currentQuestions:()=>[]});
}
const messageHtml=m=>viewsFor(stateFor([m])).renders.chat();

test('answer meta is generic and hides a zero source count',()=>{
  const html=messageHtml({id:'m1',role:'ai',text:'回答内容。',engine:'资料问答',sources:[],timings:{totalMs:1234}});
  assert.match(html,/资料问答 · 1\.2 秒/);
  assert.doesNotMatch(html,/0 个来源/);
  assert.doesNotMatch(html,/MiMo/);
  const legacy=messageHtml({id:'m2',role:'ai',text:'回答内容。',engine:'MiMo 通用问答',sources:[]});
  assert.doesNotMatch(legacy,/MiMo/);
  assert.match(legacy,/通用问答/);
  const sourced=messageHtml({id:'m3',role:'ai',text:'回答内容。',engine:'资料问答',sources:[{id:'s1',title:'教材',location:'第 2 章'}]});
  assert.match(sourced,/资料问答 · 1 个来源/);
});

test('web source chips show the site hostname while keeping the click target',()=>{
  const html=messageHtml({id:'m1',role:'ai',text:'回答内容。',engine:'资料问答',sources:[{id:'web-1',title:'示例页面',url:'https://www.example.com/a/b?q=1',isWeb:true}]});
  assert.match(html,/示例页面 · example\.com/);
  assert.doesNotMatch(html,/示例页面 · https:\/\/www\.example\.com/);
  assert.match(html,/data-citation="web-1"/);
  assert.match(html,/点击在新窗口打开网页：https:\/\/www\.example\.com\/a\/b\?q=1/);
});

test('LLM suggested questions render as follow-up chips and beat the static fallback',()=>{
  const html=messageHtml({id:'m1',role:'ai',text:'回答内容。',engine:'资料问答',sources:[],suggestedQuestions:['LLM 追问一','LLM 追问二','LLM 追问三']});
  for(const question of ['LLM 追问一','LLM 追问二','LLM 追问三'])assert.match(html,new RegExp('data-prompt="'+question+'"'));
  assert.doesNotMatch(html,/能为我针对刚才解释的要点，出一道经典考查题吗/);
});

test('thinking panel streams reasoning, collapses to 已思考 with duration, and falls back to workflow labels',()=>{
  const streaming=messageHtml({id:'m1',role:'ai',text:'',engine:'正在回答',reasoning:'正在分析队列的定义。',sources:[]});
  assert.match(streaming,/思考中…/);
  assert.match(streaming,/正在分析队列的定义。/);
  assert.match(streaming,/<details class="thinking-box" open>/);
  const done=messageHtml({id:'m2',role:'ai',text:'回答内容。',engine:'资料问答',reasoning:'完整推理过程。',thinkingSeconds:3,sources:[]});
  assert.match(done,/已思考（用时 3 秒）/);
  assert.match(done,/完整推理过程。/);
  assert.match(done,/<details class="thinking-box" >/);
  const progressOnly=messageHtml({id:'m3',role:'ai',text:'回答内容。',engine:'资料问答',progress:'正在核对引用依据',sources:[]});
  assert.match(progressOnly,/已思考/);
  assert.match(progressOnly,/正在核对引用依据/);
  const plain=messageHtml({id:'m4',role:'ai',text:'回答内容。',engine:'资料问答',sources:[]});
  assert.doesNotMatch(plain,/thinking-box/);
});
