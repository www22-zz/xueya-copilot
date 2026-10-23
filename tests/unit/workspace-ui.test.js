const test=require('node:test');
const assert=require('node:assert/strict');
const L=require('../../shared/learning.js');
const {createStore,KEY,LEGACY}=require('../../frontend/js/state/workspace-store.js');
const rich=require('../../frontend/js/ui/rich-content.js');
const {createService,normalizeDocument}=require('../../frontend/js/services/workspace-service.js');

function storage(initial={}){const data=new Map(Object.entries(initial));return{getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value),data};}
function setup(initial={}){let counter=0;const disk=storage(initial),store=createStore({storage:disk,learning:L,id:()=>String(++counter)});return{disk,store};}

test('ordinary conversation follow-up carries its kind through the browser request',async t=>{
  const savedService=globalThis.XueyaWorkspaceService,savedCache=globalThis.XueyaFileCache;
  t.after(()=>{globalThis.XueyaWorkspaceService=savedService;globalThis.XueyaFileCache=savedCache;});
  globalThis.XueyaWorkspaceService={createService:()=>({capabilities:{}})};
  globalThis.XueyaFileCache={createCache:()=>({})};
  const {createWorkspace}=require('../../frontend/js/workspace-controller.js');
  const {createChatService}=require('../../frontend/js/services/chat-service.js');
  const state={messages:[{role:'user',text:'给我一个 JSON 示例'},{role:'ai',engine:'MiMo 通用问答',text:'```json\n{"name":"张三"}\n```',sources:[]}]};
  const workspace=createWorkspace({state});
  const input=workspace.historyFor('把代码块里的 name 改成小明');
  assert.equal(input.previousAnswerKind,'general');
  let sent;
  const service=createChatService({fetchImpl:async(url,options)=>{
    sent=JSON.parse(options.body);
    return new Response('data: '+JSON.stringify({type:'done',ok:true,answer:'小明',sources:[],engine:'general-chat'})+'\n\n',{headers:{'Content-Type':'text/event-stream'}});
  }});
  await service.stream(input,{workflow:true});
  assert.equal(sent.previousAnswerKind,'general');
  assert.deepEqual(sent.history,input.history);
  state.messages.push({role:'ai',engine:'MiMo 资料问答',text:'课程原文',sources:[{id:'source-1'}]});
  assert.equal(workspace.historyFor('再解释一下').previousAnswerKind,undefined);
});

test('workspace migration retains full existing messages, records and original v2 content',()=>{
  const legacy={messages:Array.from({length:52},(_,i)=>({role:'user',text:'message '+i})),records:Array.from({length:450},(_,i)=>({questionId:'q1',correct:i%2===0})),documents:[{id:'private',name:'my course.md',chunks:[]}],cards:[{id:'card',title:'mine',text:'note'}]};
  const original=JSON.stringify(legacy),{store,disk}=setup({[LEGACY]:original});
  assert.equal(store.state.messages.length,52);assert.equal(store.state.records.length,450);
  assert.equal(disk.getItem(LEGACY),original,'reading must not overwrite the legacy key');
  assert.equal(store.persist(),true);
  const reopened=createStore({storage:disk,learning:L});
  assert.equal(reopened.state.messages.length,52);assert.equal(reopened.state.records.length,450);
  assert.equal(reopened.state.documents[0].id,'private');assert.equal(JSON.parse(disk.getItem(LEGACY)).messages.length,52);
});

test('course/session switches preserve their own data and cannot run during generation',()=>{
  const {store,disk}=setup();store.state.messages.push({role:'user',text:'original question'});store.state.cards.push({id:'one',title:'first',text:'notes'});store.persist();
  const oldSession=store.state.sessionId;store.newSession();store.state.messages.push({role:'user',text:'second question'});store.persist();
  store.selectSession(oldSession);assert.equal(store.state.messages[0].text,'original question');
  const course=store.addCourse('数学');assert.equal(store.state.documents.length,0);assert.equal(store.state.cards.length,0);assert.equal(store.state.messages.length,0);
  store.state.documents.push({id:'math',name:'math.md'});store.persist();store.state.pending=true;
  assert.equal(store.switchCourse('course-default'),false);assert.equal(store.newSession(),false);
  store.state.pending=false;store.switchCourse('course-default');assert.equal(store.state.cards[0].id,'one');assert.equal(store.state.messages[0].text,'original question');
  const reopened=createStore({storage:disk,learning:L});reopened.switchCourse(course.id);assert.equal(reopened.state.documents[0].id,'math');
  assert.equal(store.archive('course-default'),true);assert.equal(store.archive(course.id),false,'cannot archive the last active course');
  assert.equal(store.restoreCourse('course-default'),true);
});

test('failed durable save is reported without deleting the previous workspace',()=>{
  const {store,disk}=setup();store.persist();const previous=disk.getItem(KEY);
  disk.setItem=()=>{throw new Error('quota');};store.state.cards.push({id:'new',text:'unsaved'});
  assert.equal(store.persist(),false);assert.match(store.error,/导出备份/);assert.equal(disk.getItem(KEY),previous);
  assert.equal(JSON.parse(store.exportData()).courses[0].data.cards[0].id,'new');
});

test('source selection belongs to its conversation and survives reload/course changes',()=>{
  const {store,disk}=setup();const first=store.state.sessionId;store.state.selectedDocuments=['doc-1'];store.persist();store.newSession();assert.deepEqual(store.state.selectedDocuments,[]);
  store.state.selectedDocuments=['doc-2'];store.persist();store.selectSession(first);assert.deepEqual(store.state.selectedDocuments,['doc-1']);
  const reopened=createStore({storage:disk,learning:L});assert.deepEqual(reopened.state.selectedDocuments,['doc-1']);
  reopened.addCourse('another');reopened.switchCourse('course-default');assert.deepEqual(reopened.state.selectedDocuments,['doc-1']);
});

test('server document adapters reject incomplete evidence and normalize optional metadata',()=>{
  assert.throws(()=>normalizeDocument({id:'doc',name:'missing status'}),/不完整/);
  assert.throws(()=>normalizeDocument({id:'doc',name:'ok',status:'done',chunks:[{id:'s',quote:null,title:'t'}]}),/来源标识/);
  const doc=normalizeDocument({id:'doc',name:'ok',status:'done',tags:['course',{}],chunks:[{id:'s',title:'ok',quote:'real passage',keywords:'bad'}]});
  assert.deepEqual(doc.tags,['course']);assert.deepEqual(doc.chunks[0].keywords,[]);assert.equal(doc.chunks[0].documentId,'doc');
});

test('question adapter honors cancellation even if transport resolves late',async()=>{
  const {createPracticeService}=require('../../frontend/js/services/practice-service.js');let complete;
  const service=createPracticeService({protocol:'http:',fetchImpl:()=>new Promise(resolve=>{complete=resolve;})});
  const controller=new AbortController(),call=service.questions({sources:[]},{signal:controller.signal});controller.abort();complete({ok:true,json:async()=>({ok:true,questions:[{prompt:'late'}]})});
  await assert.rejects(call,error=>error.name==='AbortError');
});

test('refresh marks in-flight generations interrupted, while notes, drafts and versions persist',()=>{
  const {store,disk}=setup();store.state.messages.push({role:'ai',text:'partial',engine:'正在回答'});store.state.quizDraft.q1={answer:1,submitted:false};store.state.planHistory.push({version:1,days:[]});store.state.corrections.push({text:'my correction'});store.persist();
  const reopened=createStore({storage:disk,learning:L});assert.equal(reopened.state.messages[0].failed,true);assert.doesNotMatch(reopened.state.messages[0].text,/partial/);
  assert.equal(reopened.state.quizDraft.q1.answer,1);assert.equal(reopened.state.corrections[0].text,'my correction');assert.equal(reopened.state.planHistory.length,1);
});

test('rich rendering escapes HTML, code, unsafe links and attribute injection',()=>{
  const output=rich.render('<img src=x onerror=alert(1)>\n\n[unsafe](javascript:alert)\n[ok](https://example.com/x?q=1)\n\n```html\n<script>attack()</script>\n```\n\n**<svg/onload=1>**');
  assert.doesNotMatch(output,/<img|<script|<svg|href="javascript:/);assert.match(output,/&lt;img/);assert.match(output,/&lt;script&gt;/);assert.match(output,/rel="noopener noreferrer"/);
  assert.equal(rich.safeURL('data:text/html,<script>'), '');assert.equal(rich.safeURL('https://user:secret@example.com'), '');
  assert.doesNotMatch(rich.render('$\\text{<img src=x onerror=1>}$'),/<img/);
});

test('Markdown headings, table, code and supported math render as semantic safe content',()=>{
  const output=rich.render('# 比较\n\n|算法|复杂度|\n|---|---|\n|平衡树|$O(\\log n)$|\n\n- 第一项\n- 第二项\n\n$$\\frac{a^2}{\\sqrt{b}}$$');
  for(const expected of ['<h2>','<table>','scope="col"','<ul>','<math','<mfrac>','<msup>','<msqrt>'])assert.ok(output.includes(expected),expected);
  assert.ok(rich.math('{'.repeat(40)+'x'+'}'.repeat(40)).length<10000,'deep formulas fall back safely');
});

test('frontend capability ports stay unavailable without a real adapter, including file preview',async()=>{
  const local=createService({protocol:'http:'});assert.equal(local.capabilities.transcribe,false);await assert.rejects(local.call('transcribe',{}),/尚未接通/);
  let calls=0;const preview=createService({protocol:'file:',adapter:{transcribe(){calls++;}}});await assert.rejects(preview.call('transcribe',{}),/尚未接通/);assert.equal(calls,0);
});

test('capability cancellation and timeout reject late results from a noncooperating adapter',async()=>{
  const controller=new AbortController();let complete;
  const service=createService({adapter:{video:()=>new Promise(resolve=>{complete=resolve;})},protocol:'http:',timeoutMs:1000});
  const call=service.call('video',{}, {signal:controller.signal});await Promise.resolve();controller.abort();await assert.rejects(call,error=>error.name==='AbortError');complete({text:'late'});
  const timeout=createService({adapter:{speak:()=>new Promise(()=>{})},protocol:'http:',timeoutMs:10});await assert.rejects(timeout.call('speak',{}),error=>error.name==='TimeoutError');
  let invoked=0;const aborted=new AbortController();aborted.abort();const guard=createService({adapter:{graph:()=>{invoked++;}},protocol:'http:'});await assert.rejects(guard.call('graph',{}, {signal:aborted.signal}));assert.equal(invoked,0);
  let progress;const updates=[];const finished=createService({adapter:{graph:async(input,options)=>{progress=options.onProgress;progress('live');return{nodes:[],edges:[]};}},protocol:'http:'});await finished.call('graph',{}, {onProgress:value=>updates.push(value)});progress('late');assert.deepEqual(updates,['live']);
});
