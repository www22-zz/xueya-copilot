'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {createPlatformSession,connectionStats}=require('../../backend/mcp/platform-session.js');
const {createBusinessPorts,createWorkflowSessionFactory}=require('../../backend/mcp/business-ports.js');
const {createActionAuthority}=require('../../backend/mcp/actions.js');
const {createDiskRepository}=require('../helpers/mcp-repository.js');
const {createLearningWorkflow}=require('../../backend/agent/learning-workflow.js');
const alice={userId:'alice',courseId:'math'},bob={userId:'bob',courseId:'biology'};
async function fixture(t){const dir=await fs.mkdtemp(path.join(os.tmpdir(),'xueya-mcp-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));const repository=createDiskRepository(dir);return{repository,dir};}
const draft=(entityId='note-1',expectedVersion=0)=>({kind:'note',entityId,expectedVersion,after:{title:'Study note',content:'Actual saved note',sourceIds:[]}});

test('scoped SDK tools read durable data, paginate and reject model scope overrides',async t=>{
  const {repository}=await fixture(t);
  await repository.seed({scope:alice,sources:[{id:'a',title:'Math',location:'1',quote:'matrix multiplication'}]});
  await repository.seed({scope:bob,sources:[{id:'b',title:'Biology',location:'1',quote:'photosynthesis'}]});
  const authority=createActionAuthority({repository});
  const a=await createPlatformSession({scope:alice,services:createBusinessPorts({repository}),authority});t.after(()=>a.close());
  const b=await createPlatformSession({scope:bob,services:createBusinessPorts({repository}),authority});t.after(()=>b.close());
  const [ra,rb]=await Promise.all([a.call('search_materials',{query:'matrix'}),b.call('search_materials',{query:'photosynthesis'})]);
  assert.equal(ra.sources[0].id,'a');assert.equal(rb.sources[0].id,'b');
  await assert.rejects(b.call('read_source',{sourceId:'a'}),/SOURCE_NOT_FOUND/);
  await assert.rejects(a.call('list_notes',{scope:bob}),/INVALID_TOOL_ARGUMENTS/);
  for(const id of ['n1','n2']){const p=await a.call('prepare_action',draft(id));a.confirm(p);await a.call('apply_action',{actionId:p.actionId});}
  const first=await a.call('list_notes',{limit:1}),second=await a.call('list_notes',{limit:1,cursor:first.nextCursor});
  assert.equal(first.items[0].id,'n1');assert.equal(second.items[0].id,'n2');assert.equal(second.nextCursor,null);
  assert.equal((await b.call('list_notes')).items.length,0);
  assert.ok(!(await a.listTools()).some(tool=>/confirm|list_concepts/.test(tool.name)));
});

test('real SDK write preview -> host confirmation -> atomic data/audit/receipt; durable and idempotent',async t=>{
  const {repository,dir}=await fixture(t);const authority=createActionAuthority({repository});
  const session=await createPlatformSession({scope:alice,authority});t.after(()=>session.close());
  const p=await session.call('prepare_action',draft());assert.equal(p.before,null);
  assert.equal(await repository.read({scope:alice,kind:'note',entityId:'note-1'}),null);
  await assert.rejects(session.call('apply_action',{actionId:p.actionId}),/ACTION_CONFIRMATION_REQUIRED/);
  assert.throws(()=>session.confirm({...p,digest:'changed'}),/ACTION_CHANGED/);
  assert.throws(()=>authority.confirm(bob,p),/ACTION_NOT_FOUND/);
  // Caller mutation does not change the stored action.
  p.after.content='tampered';session.confirm(p);
  assert.throws(()=>session.confirm(p),/ACTION_ALREADY_CONFIRMED/);
  const receipt=await session.call('apply_action',{actionId:p.actionId});
  assert.deepEqual(await session.call('apply_action',{actionId:p.actionId}),receipt);
  const reloaded=createDiskRepository(dir),state=await reloaded.snapshot();
  assert.equal((await reloaded.read({scope:alice,kind:'note',entityId:'note-1'})).value.content,'Actual saved note');
  assert.equal(state.audits.length,1);assert.equal(state.audits[0].actor,'alice');assert.equal(receipt.auditId,state.audits[0].auditId);
  await session.close();assert.equal(connectionStats().active,0);
});

test('expiry, cancellation, changed versions, invalid dates and cross-course references prevent writes',async t=>{
  const {repository}=await fixture(t);let time=1000;const authority=createActionAuthority({repository,now:()=>time,ttlMs:10});
  const expired=await authority.prepare(alice,draft());time+=11;assert.throws(()=>authority.confirm(alice,expired),/ACTION_EXPIRED/);
  const cancelled=await authority.prepare(alice,draft('cancel'));authority.cancel(alice,cancelled.actionId);assert.throws(()=>authority.confirm(alice,cancelled),/ACTION_NOT_PENDING/);
  const p=await authority.prepare(alice,draft()),q=await authority.prepare(alice,draft());authority.confirm(alice,p);authority.confirm(alice,q);
  await authority.apply(alice,p.actionId);await assert.rejects(authority.apply(alice,q.actionId),/VERSION_CONFLICT/);await assert.rejects(authority.apply(alice,q.actionId),/ACTION_NOT_PENDING/);
  assert.equal((await repository.snapshot()).audits.length,1);
  await assert.rejects(authority.prepare(alice,{...draft(),expectedVersion:1,after:{title:'x',content:'x',sourceIds:['foreign']}}),/SOURCE_NOT_FOUND/);
  await assert.rejects(authority.prepare(alice,{kind:'plan',entityId:'p',expectedVersion:0,after:{title:'x',days:[{date:'2026-02-30',tasks:[]}]}}));
});

test('concurrent apply cannot execute twice and uncertain commits cannot auto-retry',async()=>{
  let finish,calls=0;const authority=createActionAuthority({repository:{read:async()=>null,applyConfirmed:async()=>{calls++;await new Promise(resolve=>finish=resolve);throw new Error('COMMIT_UNCERTAIN');}}});
  const p=await authority.prepare(alice,draft());authority.confirm(alice,p);const running=authority.apply(alice,p.actionId);
  await assert.rejects(authority.apply(alice,p.actionId),/ACTION_NOT_PENDING/);finish();await assert.rejects(running,/COMMIT_UNCERTAIN/);await assert.rejects(authority.apply(alice,p.actionId),/ACTION_NOT_PENDING/);assert.equal(calls,1);
});

test('existing Agent -> real MCP -> persisted RAG port -> original evidence is connected',async t=>{
  const {repository}=await fixture(t);const source={id:'own-source',title:'Biology',location:'1',quote:'光合作用发生在叶绿体。'};await repository.seed({scope:alice,sources:[source]});
  const openSession=createWorkflowSessionFactory({resolveScope:async()=>alice,servicesForScope:()=>createBusinessPorts({repository})});
  const workflow=createLearningWorkflow({openSession,model:{generate:async()=>({model:'controlled',content:JSON.stringify({answer:'发生在叶绿体。',sources:['own-source'],knowledgePoints:[]})})}});
  const answer=await workflow.run({question:'光合作用在哪里？',context:{library:[source]}});
  assert.deepEqual(answer.sources,['own-source']);assert.ok(answer.workflow.steps.some(s=>s.stage==='read'&&s.status==='completed'));assert.ok(!answer.workflow.steps.some(s=>s.status==='degraded'));
});

test('business port output validation catches bad pages, wrong scope and large results',async t=>{
  const session=await createPlatformSession({scope:alice,services:{listNotes:async()=>({items:[1,2]}),readSource:async()=>({source:{id:'x',quote:'y'},scope:bob}),analyzeProgress:async()=>({text:'x'.repeat(140000)})}});t.after(()=>session.close());
  await assert.rejects(session.call('list_notes',{limit:1}),/INVALID_BUSINESS_PAGE/);await assert.rejects(session.call('read_source',{sourceId:'x'}),/RESULT_SCOPE_MISMATCH/);await assert.rejects(session.call('analyze_progress'),/TOOL_RESULT_TOO_LARGE/);
});

test('real SDK cancellation reaches the injected business service signal',async t=>{
  let started,aborted=false;const ready=new Promise(resolve=>started=resolve);
  const session=await createPlatformSession({scope:alice,services:{listNotes:async(_,options)=>{started();await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{aborted=true;reject(new Error('CANCELLED'));},{once:true}));return{items:[]};}}});t.after(()=>session.close());
  const controller=new AbortController(),running=session.call('list_notes',{}, {signal:controller.signal});await ready;controller.abort();await assert.rejects(running,/TOOL_ABORTED/);await new Promise(resolve=>setImmediate(resolve));assert.equal(aborted,true);
});

test('question and plan writes use the same confirmation/CAS/audit pipeline',async t=>{
  const {repository}=await fixture(t);await repository.seed({scope:alice,sources:[{id:'own',quote:'actual reference'}]});
  const authority=createActionAuthority({repository}),session=await createPlatformSession({scope:alice,authority});t.after(()=>session.close());
  for(const [kind,after] of [['question',{prompt:'Where?',answer:'Here.',sourceIds:['own']}],['plan',{title:'Review',days:[{date:'2026-10-20',tasks:[{title:'Review actual notes',minutes:20}]}]}]]){
    const p=await session.call('prepare_action',{kind,entityId:kind+'-1',expectedVersion:0,after});session.confirm(p);await session.call('apply_action',{actionId:p.actionId});assert.equal((await repository.read({scope:alice,kind,entityId:kind+'-1'})).version,1);
  }
  assert.equal((await repository.snapshot()).audits.length,2);
});

test('all optional learning/section ports are discoverable and receive only immutable host scope',async t=>{
  const methods={list_sections:'listSections',read_section:'readSection',list_concepts:'listConcepts',get_prerequisites:'getPrerequisites',list_question_drafts:'listQuestionDrafts',list_attempts:'listAttempts',list_wrong_questions:'listWrongQuestions',list_reviews:'listReviews',list_plans:'listPlans'};
  const services=Object.fromEntries(Object.values(methods).map(method=>[method,async args=>{assert.deepEqual(args.scope,alice);args.scope.courseId='mutation';return{items:[],nextCursor:null};}]));
  const session=await createPlatformSession({scope:alice,services});t.after(()=>session.close());
  for(const name of Object.keys(methods)){const args=name==='read_section'?{sectionId:'s'}:name==='get_prerequisites'?{conceptId:'c'}:{};assert.deepEqual(await session.call(name,args),{items:[],nextCursor:null});}
  assert.equal((await session.listTools()).length,9);
});

test('waiting for user confirmation holds no MCP connection; confirmation resumes in a fresh session',async t=>{
  const {repository}=await fixture(t),authority=createActionAuthority({repository});
  const first=await createPlatformSession({scope:alice,authority}),preview=await first.call('prepare_action',draft());await first.close();assert.equal(connectionStats().active,0);
  authority.confirm(alice,preview);
  const resumed=await createPlatformSession({scope:alice,authority});t.after(()=>resumed.close());const receipt=await resumed.call('apply_action',{actionId:preview.actionId});assert.equal(receipt.version,1);
});

test('source revisions changed after preview cannot silently support a committed question',async t=>{
  const {repository}=await fixture(t);await repository.seed({scope:alice,sources:[{id:'s',quote:'old evidence',version:1}]});
  const authority=createActionAuthority({repository}),p=await authority.prepare(alice,{kind:'question',entityId:'q',expectedVersion:0,after:{prompt:'Why?',answer:'Because.',sourceIds:['s']}});authority.confirm(alice,p);
  await repository.seed({scope:alice,sources:[{id:'s',quote:'changed evidence',version:2}]});await assert.rejects(authority.apply(alice,p.actionId),/SOURCE_VERSION_CONFLICT/);assert.equal((await repository.snapshot()).audits.length,0);
});
