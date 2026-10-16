'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),http=require('node:http');
const {createPlatform}=require('../../backend/platform/index.js');
const {createRagService}=require('../../backend/rag/index.js');
const {createApp}=require('../../backend/app.js');
const {createBackup,restoreBackup}=require('../../backend/platform/backup.js');
const {createJobQueue}=require('../../backend/platform/jobs.js');
const {createResources}=require('../../backend/platform/resources.js');
const root=path.resolve(__dirname,'../..');
const workspace=()=>({version:3,activeId:'course-default',courses:[{id:'course-default',name:'数据结构',archived:false,data:{documents:[],cards:[],bank:[],records:[],messages:Array.from({length:40},(_,i)=>({id:'m'+i,role:'user',text:'历史'+i})),sessions:[],plan:[]}}]});
async function fixture(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'xueya-platform-test-'));let platform=createPlatform({dataDir:path.join(dir,'data'),rag:createRagService()});t.after(async()=>{await platform.close();assert.ok(dir.startsWith(path.join(os.tmpdir(),'xueya-platform-test-')));fs.rmSync(dir,{recursive:true,force:true});});return{dir,get p(){return platform;},async restart(){await platform.close();platform=createPlatform({dataDir:path.join(dir,'data'),rag:createRagService()});}};}
async function waitJob(p,id){for(let i=0;i<100;i++){const job=p.jobs.get(id,p.userId);if(['succeeded','failed','cancelled','unknown'].includes(job.status))return job;await new Promise(resolve=>setTimeout(resolve,20));}throw new Error('JOB_WAIT_TIMEOUT');}
test('migration preserves full browser data/raw backup, is reentrant and CAS-safe after restart',async t=>{
  const f=await fixture(t),w=workspace();w.courses[0].data.records=Array.from({length:400},(_,i)=>({questionId:'q1',correct:!!(i%2),createdAt:new Date().toISOString()}));
  const preview=f.p.migration.preview(f.p.userId,{workspace:w,raw:{v2:'original bytes'}});assert.equal(preview.counts.messages,40);assert.equal(preview.counts.records,400);
  const applied=f.p.migration.apply(f.p.userId,{id:preview.id,hash:preview.hash});assert.equal(applied.version,1);assert.equal(f.p.migration.apply(f.p.userId,{id:preview.id,hash:preview.hash}).alreadyImported,true);
  assert.equal(f.p.migration.backup(f.p.userId,applied.backupId).raw.v2,'original bytes');await f.restart();assert.equal(f.p.repository.getWorkspace(f.p.userId).data.courses[0].data.records.length,400);
  assert.throws(()=>f.p.repository.saveWorkspace(f.p.userId,w,0),/VERSION_CONFLICT/);assert.equal(f.p.repository.getWorkspace(f.p.userId).version,1);
});
test('repository isolates courses, cursor scope, archived writes, revisions and transaction rollback',async t=>{
  const {p}=await fixture(t),r=p.repository,s=p.scope('course-default');r.ensureCourse(p.userId,{id:'other',name:'另课'});const other=p.scope('other');
  for(const id of ['a','b'])r.put({scope:s,kind:'note',entityId:id,expectedVersion:0,value:{title:id}});
  const first=r.list({scope:s,kind:'note',limit:1});assert.equal(first.items[0].id,'a');assert.throws(()=>r.list({scope:other,kind:'note',cursor:first.nextCursor}),/INVALID_CURSOR/);assert.equal(r.all(other,'note').length,0);
  assert.throws(()=>r.transaction(()=>{r.put({scope:s,kind:'note',entityId:'rollback',value:{}});throw new Error('ROLLBACK');}));assert.equal(r.read({scope:s,kind:'note',entityId:'rollback'}),null);
  r.ensureCourse(p.userId,{id:'other',name:'另课',archived:true});assert.throws(()=>r.put({scope:other,kind:'note',entityId:'x',value:{}}),/COURSE_ARCHIVED/);
  assert.throws(()=>p.files.read('../../.env'),/INVALID_FILE_HASH/);
});
test('real parse job saves original/chunks, idempotency, events and completed state across restart',async t=>{
  const f=await fixture(t),s=f.p.scope('course-default'),input={name:'课程.md',buffer:Buffer.from('光合作用发生在叶绿体。'),idempotencyKey:'upload-one'};
  const job=f.p.upload(s,input);assert.equal(f.p.upload(s,input).id,job.id);const done=await waitJob(f.p,job.id);assert.equal(done.status,'succeeded');const doc=f.p.document(s,done.result.documentId);assert.ok(doc.chunks.length);assert.equal(f.p.files.read(doc.fileHash).toString(),'光合作用发生在叶绿体。');const events=f.p.jobs.events(job.id,f.p.userId);assert.equal(f.p.jobs.events(job.id,f.p.userId,events[0].seq).length,events.length-1);
  await f.restart();assert.equal(f.p.jobs.get(job.id,f.p.userId).status,'succeeded');assert.equal(f.p.document(s,doc.id).chunks[0].quote,'光合作用发生在叶绿体。');
});
test('real SQLite MCP confirmation atomically saves audit/receipt and updates browser-compatible workspace',async t=>{
  const {p}=await fixture(t);p.repository.saveWorkspace(p.userId,workspace(),0);const s=p.scope('course-default'),a=p.authority;
  const preview=await a.prepare(s,{kind:'note',entityId:'note-1',expectedVersion:0,after:{title:'重点',content:'原始内容',sourceIds:[]}});assert.equal(p.repository.all(s,'note').length,0);a.confirm(s,preview);const receipt=await a.apply(s,preview.actionId);assert.deepEqual(await a.apply(s,preview.actionId),receipt);
  assert.equal(p.db.prepare('SELECT COUNT(*) AS n FROM audits').get().n,1);assert.equal(p.repository.getWorkspace(p.userId).data.courses[0].data.cards[0].text,'原始内容');
  assert.throws(()=>p.repository.saveWorkspace(p.userId,workspace(),1),/VERSION_CONFLICT/);
});
test('backup/restore retains SQLite and originals and rejects corrupted or existing destinations',async t=>{
  const {p,dir}=await fixture(t);p.repository.saveWorkspace(p.userId,workspace(),0);const file=p.files.put(Buffer.from('recoverable original'));const backup=path.join(dir,'backup'),restore=path.join(dir,'restored');await createBackup(p,backup);restoreBackup(backup,restore);
  const restored=createPlatform({dataDir:restore,rag:createRagService(),startJobs:false});try{assert.equal(restored.files.read(file.hash).toString(),'recoverable original');assert.equal(restored.repository.getWorkspace(p.userId).data.courses[0].data.messages.length,40);}finally{await restored.close();}
  assert.throws(()=>restoreBackup(backup,restore),/RESTORE_REQUIRES_NEW_DIRECTORY/);fs.appendFileSync(path.join(backup,'workspace.sqlite'),'tamper');assert.throws(()=>restoreBackup(backup,path.join(dir,'bad')),/BACKUP_CHECKSUM_MISMATCH/);
});
test('persistent queue retries CPU work, checkpoints, recovers leases, cancels, and never retries unknown paid API results',async t=>{
  const {p}=await fixture(t);let attempts=0;p.jobs.register('retry-cpu',async(_,ctx)=>{ctx.checkpoint({phase:++attempts});if(attempts===1)throw new Error('RETRYABLE');return{done:true};});const j=p.jobs.submit(p.userId,{type:'retry-cpu',courseId:'course-default',idempotencyKey:'cpu'});assert.equal((await waitJob(p,j.id)).status,'succeeded');assert.equal(attempts,2);
  p.jobs.register('paid-api',async()=>{throw new Error('NETWORK_AMBIGUOUS');});const paid=p.jobs.submit(p.userId,{type:'paid-api',courseId:'course-default',idempotencyKey:'paid',resource:'api'});assert.equal((await waitJob(p,paid.id)).status,'unknown');assert.throws(()=>p.jobs.retry(paid.id,p.userId),/JOB_NOT_RETRYABLE/);
  p.jobs.register('recover-test',async()=>({ok:true}));const stale=p.jobs.submit(p.userId,{type:'recover-test',courseId:'course-default',idempotencyKey:'stale'});p.db.prepare("UPDATE jobs SET status='running',lease_owner='dead',lease_until=0,attempts=1,checkpoint='{\"phase\":1}' WHERE id=?").run(stale.id);assert.equal(p.jobs.recover(),1);assert.equal(p.jobs.get(stale.id,p.userId).checkpoint.phase,1);
  const cancelled=p.jobs.submit(p.userId,{type:'recover-test',courseId:'course-default',idempotencyKey:'cancel'});assert.equal(p.jobs.cancel(cancelled.id,p.userId).status,'cancelled');assert.equal(p.resources.stats().inference,'external-api-only');assert.throws(()=>p.resources.choose('gpu'),/RESOURCE_UNSUPPORTED/);
  const lost=p.jobs.submit(p.userId,{type:'paid-api',courseId:'course-default',idempotencyKey:'lost-paid',resource:'api'});p.db.prepare("UPDATE jobs SET status='running',lease_owner='dead',lease_until=0,attempts=1 WHERE id=?").run(lost.id);p.jobs.recover();assert.equal(p.jobs.get(lost.id,p.userId).status,'unknown');
});
test('HTTP platform migration, actual Agent/MCP persisted retrieval, API ledger, CSRF and private paths',async t=>{
  const {p}=await fixture(t),model={generate:async()=>({model:'controlled',content:JSON.stringify({answer:'树高决定查找复杂度。',sources:['source-1'],knowledgePoints:[]})})};
  const app=createApp({config:{root,ai:{apiKey:'',model:'controlled'}},platform:p,model}),server=http.createServer(app);await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>{server.closeAllConnections();server.close(resolve);}));const base='http://127.0.0.1:'+server.address().port;
  const bootstrap=await fetch(base+'/api/platform/bootstrap').then(r=>r.json()),headers={'Content-Type':'application/json','X-Xueya-Token':bootstrap.token};
  assert.equal((await fetch(base+'/api/platform/workspace',{method:'PUT',body:'{}'})).status,403);
  const preview=await fetch(base+'/api/platform/migration/preview',{method:'POST',headers,body:JSON.stringify({workspace:workspace()})}).then(r=>r.json());assert.ok(preview.preview);
  assert.equal((await fetch(base+'/api/platform/migration/apply',{method:'POST',headers,body:JSON.stringify(preview.preview)})).status,200);
  const answer=await fetch(base+'/api/agent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({courseId:'course-default',question:'二叉搜索树的查找复杂度',sources:['source-1']})}).then(r=>r.json());assert.ok(answer.ok);assert.deepEqual(answer.sources,['source-1']);assert.ok(!answer.workflow.steps.some(step=>step.status==='degraded'));assert.equal(p.repository.all(p.scope('course-default'),'run')[0].status,'succeeded');assert.equal(p.db.prepare('SELECT status FROM invocations').get().status,'succeeded');
  assert.equal((await fetch(base+'/.xueya-data/workspace.sqlite')).status,404);assert.equal((await fetch(base+'/api/platform/bootstrap',{headers:{Origin:'https://evil.example'}})).status,403);
});

test('active cancellation fences business writes and API slots remain bounded with recorded usage',async t=>{
  const {p}=await fixture(t);let started,finish;const ready=new Promise(resolve=>started=resolve),block=new Promise(resolve=>finish=resolve);
  p.jobs.register('cancel-active',async({scope:s},ctx)=>{started();await block;return ctx.commit(()=>{p.repository.put({scope:s,kind:'note',entityId:'forbidden',value:{}});return{ok:true};});});
  const job=p.jobs.submit(p.userId,{type:'cancel-active',courseId:'course-default',idempotencyKey:'cancel-active'});await ready;p.jobs.cancel(job.id,p.userId);finish();assert.equal((await waitJob(p,job.id)).status,'cancelled');assert.equal(p.repository.read({scope:p.scope('course-default'),kind:'note',entityId:'forbidden'}),null);
  const {createTrackedProvider}=require('../../backend/platform/api-provider.js');let release;const waiting=new Promise(resolve=>release=resolve),provider=createTrackedProvider({platform:p,scope:p.scope('course-default'),model:{generate:async()=>{await waiting;return{content:'result',usage:{total_tokens:20}};}}});
  const first=provider.generate({messages:[]}),second=provider.generate({messages:[]});await assert.rejects(provider.generate({messages:[]}),/API_BUSY/);release();await Promise.all([first,second]);assert.equal(p.resources.stats().active.api,0);assert.equal(JSON.parse(p.db.prepare('SELECT usage_json FROM invocations LIMIT 1').get().usage_json).total_tokens,20);
});

test('ordinary Node parsing worker handles invalid encoding and terminates on cancellation without a model runtime',async()=>{
  const {parseArtifact}=require('../../backend/platform/file-worker.js');
  await assert.rejects(parseArtifact({buffer:Buffer.from([255]),kind:'txt',document:{id:'d',name:'bad.txt'}}),/INVALID_TEXT_ENCODING/);
  const controller=new AbortController(),running=parseArtifact({buffer:Buffer.from('plain text'),kind:'md',document:{id:'d',name:'cancel.md'}},{signal:controller.signal});controller.abort();await assert.rejects(running,error=>error.name==='AbortError');
});
