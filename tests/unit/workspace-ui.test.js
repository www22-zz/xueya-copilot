const test=require('node:test');
const assert=require('node:assert/strict');
const L=require('../../shared/learning.js');
const {createStore,KEY,LEGACY}=require('../../frontend/js/state/workspace-store.js');
const rich=require('../../frontend/js/ui/rich-content.js');
const {createService,normalizeDocument}=require('../../frontend/js/services/workspace-service.js');

function storage(initial={}){const data=new Map(Object.entries(initial));return{getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value),data};}
function setup(initial={}){let counter=0;const disk=storage(initial),store=createStore({storage:disk,learning:L,id:()=>String(++counter)});return{disk,store};}

test('server course names replace stale labels without losing local conversations',()=>{
  const {store}=setup();store.state.messages.push({role:'user',text:'保留对话'});
  const sessionId=store.state.sessionId;
  assert.ok(store.adoptCourse({id:'course-default',name:'栈与队列知识库'}));
  assert.equal(store.courses[0].name,'栈与队列知识库');
  assert.equal(store.state.sessionId,sessionId);
  assert.equal(store.state.messages[0].text,'保留对话');
});

test('fresh and migrated workspaces do not count fixture names as uploaded files',()=>{
  const fresh=setup().store;
  assert.deepEqual(fresh.state.documents,[]);
  assert.equal(fresh.courses[0].name,'个人参考资料');
  const real={id:'real',name:'真实笔记.md',chunks:[{text:'笔记正文'}]};
  const migrated=setup({[LEGACY]:JSON.stringify({documents:[...L.documents,real]})}).store;
  assert.deepEqual(migrated.state.documents,[real]);
});

test('account workspaces preserve unknown legacy data without sharing conversations',()=>{
  const orphan=JSON.stringify({version:3,activeId:'course-default',courses:[{id:'course-default',name:'旧空间',data:{messages:[{role:'user',text:'unknown legacy private'}]}}]});
  const disk=storage({[KEY]:orphan});
  let counter=0;const create=accountId=>createStore({storage:disk,learning:L,accountId,id:()=>String(++counter)});
  const alice=create('owner-alice');assert.equal(alice.state.messages.length,0);
  alice.state.messages.push({id:'private-message',role:'user',text:'alice private'});assert.ok(alice.persist());
  const bob=create('owner-bob');assert.equal(bob.state.messages.length,0);assert.ok(bob.persist());
  assert.equal(create('owner-alice').state.messages[0].text,'alice private');
  assert.equal(disk.getItem(KEY),orphan);
  assert.ok(!disk.getItem(KEY+':owner-bob').includes('alice private'));
});

test('course completion toggles once after repeated workspace mounts',()=>{
  const vm=require('node:vm'),fs=require('node:fs');
  const disk=storage(),container=new EventTarget();
  const sandbox={localStorage:disk,AbortController,setTimeout,document:{getElementById:id=>id==='spaceContent'?container:null}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../../frontend/js/courses-workspace.js'),'utf8'),sandbox);
  let ui;ui=sandbox.XueyaCourses.create({render(){ui.render();ui.mount();}});
  ui.mount();ui.mount();
  function click(selector,dataset){
    const event=new Event('click');
    Object.defineProperty(event,'target',{value:{closest:query=>query===selector?{dataset}:null}});
    container.dispatchEvent(event);
  }
  click('[data-enter-course], [data-course-card-id]',{enterCourse:'cs-ds-algo'});
  click('[data-toggle-ep-complete]',{toggleEpComplete:'ds-ep-1'});
  assert.equal(JSON.parse(disk.getItem('xueya-video-progress-v1'))['cs-ds-algo'].episodes['ds-ep-1'].completed,true);
  click('[data-toggle-ep-complete]',{toggleEpComplete:'ds-ep-1'});
  assert.equal(JSON.parse(disk.getItem('xueya-video-progress-v1'))['cs-ds-algo'].episodes['ds-ep-1'].completed,false);
});

test('custom course titles, tags and attributes render as text',()=>{
  const vm=require('node:vm'),fs=require('node:fs');
  const malicious='<img src=x onerror=alert(1)>',disk=storage({'xueya-video-courses-v1':JSON.stringify([{id:'custom-1',title:malicious,category:'theory',categoryName:'custom',instructor:'" autofocus onfocus="alert(1)',tags:[malicious],description:malicious,episodes:[]}])});
  const sandbox={localStorage:disk};
  vm.runInNewContext(fs.readFileSync(require.resolve('../../frontend/js/courses-workspace.js'),'utf8'),sandbox);
  const html=sandbox.XueyaCourses.create({}).render();
  assert.doesNotMatch(html,/<img src=x/);
  assert.match(html,/&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(html,/&quot; autofocus onfocus=&quot;alert\(1\)/);
});

test('conversation actions preserve messages, custom titles and course boundaries after reload',()=>{
  const {store,disk}=setup();
  store.state.messages.push({role:'user',text:'原始问题'},{role:'ai',text:'完整回答',sources:[]});store.persist();
  const source=store.state.sessionId;
  store.updateSession(source,{title:'手动命名',pinned:true});store.persist();
  assert.equal(store.state.sessions.find(s=>s.id===source).title,'手动命名');
  const copy=store.copySession(source,{activate:true});
  assert.deepEqual(store.state.messages,store.state.sessions.find(s=>s.id===source).messages);
  store.updateSession(copy.id,{archived:true});
  const target=store.addCourse('另一课程');store.switchCourse('course-default');
  assert.equal(store.moveSession(source,target.id),true);
  assert.equal(store.state.sessions.some(s=>s.id===source),false);
  store.switchCourse(target.id);
  const moved=store.state.sessions.find(s=>s.title==='手动命名');
  assert.equal(moved.messages.length,2);assert.deepEqual(moved.scopeDocumentIds,[]);
  const reopened=createStore({storage:disk,learning:L});
  assert.equal(reopened.state.sessions.find(s=>s.id===moved.id).messages[1].text,'完整回答');
  reopened.removeSession(reopened.state.sessionId);assert.ok(reopened.state.sessionId);
  reopened.switchCourse('course-default');
  assert.equal(reopened.state.sessions.find(s=>s.id===copy.id).archived,true);
});

test('ordinary conversation follow-up carries its kind through the browser request',async t=>{
  const savedService=globalThis.XueyaWorkspaceService,savedCache=globalThis.XueyaFileCache;
  t.after(()=>{globalThis.XueyaWorkspaceService=savedService;globalThis.XueyaFileCache=savedCache;});
  globalThis.XueyaWorkspaceService={createService:()=>({capabilities:{}})};
  globalThis.XueyaFileCache={createCache:()=>({})};
  const {createWorkspace}=require('../../frontend/js/workspace-controller.js');
  const {createChatService}=require('../../frontend/js/services/chat-service.js');
  const state={messages:[{role:'user',text:'给我一个 JSON 示例'},{role:'ai',engine:'通用回答',text:'```json\n{"name":"张三"}\n```',sources:[]}]};
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
  state.messages.push({role:'ai',engine:'资料问答',text:'课程原文',sources:[{id:'source-1'}]});
  assert.equal(workspace.historyFor('再解释一下').previousAnswerKind,undefined);
  state.messages.push({role:'ai',engine:'自主回答',text:'自主解释，未引用课程。',sources:[]});
  const autonomous=workspace.historyFor('那再举个例子');
  assert.equal(autonomous.previousAnswerKind,'general');
  assert.deepEqual(autonomous.previousSources,[],'do not resurrect an older RAG citation');
  state.messages.push({role:'ai',engine:'MiMo 自主回答',text:'旧版本保存的自主回答。',sources:[]});
  assert.equal(workspace.historyFor('旧记录还能继续追问吗').previousAnswerKind,'general','legacy branded engines keep their general meaning');
});

test('workspace migration preserves messages and materials while retiring old learning records',()=>{
  const legacy={messages:Array.from({length:52},(_,i)=>({role:'user',text:'message '+i})),records:Array.from({length:450},(_,i)=>({questionId:'q1',correct:i%2===0})),documents:[{id:'private',name:'my course.md',chunks:[]}],cards:[{id:'card',title:'mine',text:'note'}]};
  const original=JSON.stringify(legacy),{store,disk}=setup({[LEGACY]:original});
  assert.equal(store.state.messages.length,52);assert.equal(store.state.records,undefined);assert.equal(store.state.cards,undefined);
  const cleaned=JSON.parse(disk.getItem(LEGACY));assert.equal(cleaned.cards,undefined);assert.equal(cleaned.records,undefined);assert.deepEqual(cleaned.messages,legacy.messages);assert.deepEqual(cleaned.documents,legacy.documents);
  assert.equal(store.persist(),true);
  const reopened=createStore({storage:disk,learning:L});
  assert.equal(reopened.state.messages.length,52);assert.equal(reopened.state.records,undefined);assert.equal(reopened.state.cards,undefined);
  assert.equal(reopened.state.documents[0].id,'private');assert.equal(JSON.parse(disk.getItem(LEGACY)).messages.length,52);
});

test('course/session switches preserve their own data and cannot run during generation',()=>{
  const {store,disk}=setup();store.state.messages.push({role:'user',text:'original question'});store.state.documents.push({id:'one',name:'first.md'});store.persist();
  const oldSession=store.state.sessionId;store.newSession();store.state.messages.push({role:'user',text:'second question'});store.persist();
  store.selectSession(oldSession);assert.equal(store.state.messages[0].text,'original question');
  const course=store.addCourse('数学');assert.equal(store.state.documents.length,0);assert.equal(store.state.cards,undefined);assert.equal(store.state.messages.length,0);
  store.state.documents.push({id:'math',name:'math.md'});store.persist();store.state.pending=true;
  assert.equal(store.switchCourse('course-default'),false);assert.equal(store.newSession(),false);
  store.state.pending=false;store.switchCourse('course-default');assert.ok(store.state.documents.some(d=>d.id==='one'));assert.equal(store.state.messages[0].text,'original question');
  const reopened=createStore({storage:disk,learning:L});reopened.switchCourse(course.id);assert.equal(reopened.state.documents[0].id,'math');
  assert.equal(store.archive('course-default'),true);assert.equal(store.archive(course.id),false,'cannot archive the last active course');
  assert.equal(store.restoreCourse('course-default'),true);
});

test('failed durable save is reported without deleting the previous workspace',()=>{
  const {store,disk}=setup();store.persist();const previous=disk.getItem(KEY);
  disk.setItem=()=>{throw new Error('quota');};store.state.documents.push({id:'new',name:'unsaved.md'});
  assert.equal(store.persist(),false);assert.match(store.error,/导出备份/);assert.equal(disk.getItem(KEY),previous);
  assert.equal(JSON.parse(store.exportData()).courses[0].data.documents.at(-1).id,'new');
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
  const {createPracticeClient}=require('../../frontend/js/services/practice-client.js');let complete;
  const service=createPracticeClient({storage:storage(),request:()=>new Promise(resolve=>{complete=resolve;})});
  const controller=new AbortController(),call=service.note('h100-01',{signal:controller.signal});controller.abort();complete({ok:true,note:{text:'late'}});
  await assert.rejects(call,error=>error.name==='AbortError');
});

test('refresh marks in-flight chat interrupted while preserving materials and dropping retired learning data',()=>{
  const {store,disk}=setup();store.state.messages.push({role:'ai',text:'partial',engine:'正在回答'});store.state.documents.push({id:'saved',name:'saved.md'});store.persist();
  const reopened=createStore({storage:disk,learning:L});assert.equal(reopened.state.messages[0].failed,true);assert.doesNotMatch(reopened.state.messages[0].text,/partial/);
  assert.equal(reopened.state.documents.at(-1).id,'saved');assert.equal(reopened.state.quizDraft,undefined);assert.equal(reopened.state.planHistory,undefined);
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
