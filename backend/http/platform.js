'use strict';
const {randomBytes}=require('node:crypto');
const {json}=require('./json.js');
const {createPlatformSession}=require('../mcp/platform-session.js');
const C=require('../../shared/contracts/platform.js');
function read(req,limit){return new Promise((resolve,reject)=>{let size=0,chunks=[];req.on('data',chunk=>{size+=chunk.length;if(size>limit){chunks=[];reject(new Error('REQUEST_TOO_LARGE'));}else chunks.push(chunk);});req.on('end',()=>resolve(Buffer.concat(chunks)));req.on('error',reject);req.on('aborted',()=>reject(new Error('REQUEST_ABORTED')));});}
function createPlatformHandler(platform){
  const token=randomBytes(32).toString('hex'),{repository,db,userId}=platform;
  return async function(req,res){
    const url=new URL(req.url,'http://'+req.headers.host),path=url.pathname.slice('/api/platform'.length),controller=new AbortController();
    res.on('close',()=>{if(!res.writableEnded)controller.abort();});
    const reply=value=>json(res,200,{ok:true,...value});
    try{
      if(!/^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/.test(req.headers.host||''))throw new Error('ORIGIN_FORBIDDEN');
      const origin=req.headers.origin;if(origin&&origin!=='http://'+req.headers.host)throw new Error('ORIGIN_FORBIDDEN');
      if(req.method==='GET'&&path==='/bootstrap')return reply({token,schemaVersion:C.VERSION,workspace:repository.getWorkspace(userId),courses:repository.courses(userId),jobs:platform.jobs.list(userId),resources:platform.resources.stats()});
      if(req.headers['x-xueya-token']!==token)throw new Error('AUTH_REQUIRED');
      let input={};if(req.method==='POST'||req.method==='PUT'){const binary=['/documents/upload','/documents/import-original'].includes(path);const body=await read(req,binary?10485760:25000000);if(!binary){try{input=JSON.parse(body.toString());}catch{throw new Error('INVALID_JSON');}}else input={buffer:body};}
      const courseId=input.courseId||url.searchParams.get('courseId')||'course-default';let s;const scope=()=>s||(s=platform.scope(courseId));
      if(path==='/workspace'&&req.method==='GET')return reply({workspace:repository.getWorkspace(userId)});
      if(path==='/workspace'&&req.method==='PUT')return reply({workspace:repository.saveWorkspace(userId,input.workspace,input.expectedVersion)});
      if(path==='/migration/preview'&&req.method==='POST')return reply({preview:platform.migration.preview(userId,input)});
      if(path==='/migration/apply'&&req.method==='POST')return reply(platform.migration.apply(userId,input));
      if(path==='/migration/backup'&&req.method==='GET')return reply({backup:platform.migration.backup(userId,url.searchParams.get('id'))});
      if(path==='/courses'&&req.method==='POST'){C.id.parse(input.id);if(!input.name||String(input.name).length>100)throw new Error('INVALID_COURSE');repository.ensureCourse(userId,input);return reply({courses:repository.courses(userId)});}
      if(path==='/documents/upload'&&req.method==='POST')return reply({job:platform.upload(scope(),{buffer:input.buffer,name:url.searchParams.get('name')||'',previousDocumentId:url.searchParams.get('previousDocumentId'),idempotencyKey:C.id.parse(req.headers['idempotency-key'])})});
      if(path==='/documents/import-original'&&req.method==='POST'){const doc=platform.document(scope(),url.searchParams.get('documentId')),file=platform.files.put(input.buffer);if(doc.fileHash&&doc.fileHash!==file.hash)throw new Error('ORIGINAL_CONFLICT');const saved=repository.put({scope:scope(),kind:'document',entityId:doc.id,value:{...doc,fileHash:file.hash,size:file.size,originalAvailable:true},expectedVersion:doc.version});return reply({document:{...saved.value,version:saved.version}});}
      if(path==='/documents'&&req.method==='GET')return reply({documents:repository.all(scope(),'document')});
      if(path==='/documents/original'&&req.method==='GET'){const doc=platform.document(scope(),url.searchParams.get('documentId')),buffer=platform.files.read(doc.fileHash);res.writeHead(200,{'Content-Type':'application/octet-stream','Content-Disposition':"attachment; filename*=UTF-8''"+encodeURIComponent(doc.name),'X-Content-Type-Options':'nosniff'});return res.end(buffer);}
      if(path==='/documents/update'&&req.method==='POST'){const doc=platform.document(scope(),input.documentId);if(!input.changes||typeof input.changes.name!=='string'||!input.changes.name.trim())throw new Error('INVALID_DOCUMENT');const saved=repository.put({scope:scope(),kind:'document',entityId:doc.id,expectedVersion:input.version,value:{...doc,name:input.changes.name.slice(0,200),tags:Array.isArray(input.changes.tags)?input.changes.tags.slice(0,30).map(String):doc.tags}});return reply({document:{...saved.value,version:saved.version}});}
      if(path==='/documents/remove'&&req.method==='POST'){repository.transaction(()=>{const doc=platform.document(scope(),input.documentId);repository.put({scope:scope(),kind:'document',entityId:doc.id,value:doc,expectedVersion:input.version,deleted:true});for(const source of repository.all(scope(),'source').filter(source=>source.documentId===doc.id))repository.put({scope:scope(),kind:'source',entityId:source.id,value:source,deleted:true});});return reply({removed:true,retainedForRecovery:true});}
      if(path==='/jobs'&&req.method==='GET')return reply({jobs:platform.jobs.list(userId)});
      if(path==='/jobs'&&req.method==='POST')return reply({job:platform.jobs.submit(userId,input)});
      if(path==='/jobs/status'&&req.method==='GET'){const job=platform.jobs.get(url.searchParams.get('id'),userId);if(!job)throw new Error('JOB_NOT_FOUND');return reply({job});}
      if(path==='/jobs/cancel'&&req.method==='POST')return reply({job:platform.jobs.cancel(input.id,userId)});
      if(path==='/jobs/retry'&&req.method==='POST')return reply({job:platform.jobs.retry(input.id,userId)});
      if(path==='/jobs/events'&&req.method==='GET'){
        const id=url.searchParams.get('id');let seq=Number(req.headers['last-event-id']||url.searchParams.get('after')||0);if(!Number.isSafeInteger(seq)||seq<0)throw new Error('INVALID_CURSOR');platform.jobs.events(id,userId,seq);
        res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-store','X-Accel-Buffering':'no'});const send=()=>{for(const event of platform.jobs.events(id,userId,seq)){seq=event.seq;res.write('id: '+seq+'\ndata: '+JSON.stringify(event)+'\n\n');}const job=platform.jobs.get(id,userId);if(['succeeded','failed','cancelled','unknown'].includes(job.status)){clearInterval(timer);res.end();}};const timer=setInterval(send,300);timer.unref();res.on('close',()=>clearInterval(timer));send();return;
      }
      if(path==='/tools'&&req.method==='GET'){const session=await createPlatformSession({scope:scope(),services:platform.services(scope()),authority:platform.authority});try{return reply({tools:await session.listTools()});}finally{await session.close();}}
      if(path==='/tools/call'&&req.method==='POST'){const session=await createPlatformSession({scope:scope(),services:platform.services(scope()),authority:platform.authority},{signal:controller.signal});try{return reply({data:await session.call(input.name,input.arguments||{})});}finally{await session.close();}}
      if(path==='/actions/confirm'&&req.method==='POST')return reply(platform.authority.confirm(scope(),input));
      if(path==='/actions/cancel'&&req.method==='POST')return reply(platform.authority.cancel(scope(),input.actionId));
      if(path==='/entities'&&req.method==='GET')return reply(repository.list({scope:scope(),kind:C.kind.parse(url.searchParams.get('kind')),cursor:url.searchParams.get('cursor'),limit:Number(url.searchParams.get('limit'))||20}));
      if(path==='/audit'&&req.method==='GET')return reply({audits:db.prepare('SELECT data FROM audits WHERE user_id=? AND course_id=? ORDER BY at DESC LIMIT 100').all(userId,scope().courseId).map(r=>JSON.parse(r.data))});
      if(path==='/invocations'&&req.method==='GET')return reply({invocations:db.prepare('SELECT id,course_id,status,provider,at,usage_json,billing_status FROM invocations WHERE user_id=? AND course_id=? ORDER BY at DESC LIMIT 100').all(userId,scope().courseId).map(r=>({id:r.id,courseId:r.course_id,status:r.status,provider:r.provider,at:r.at,usage:r.usage_json?JSON.parse(r.usage_json):null,billingStatus:r.billing_status}))});
      return json(res,404,{ok:false,error:'NOT_FOUND'});
    }catch(error){const code=/^[A-Z_]{3,80}$/.test(error.message)?error.message:error.name==='ZodError'?'INVALID_REQUEST':'PLATFORM_ERROR';return json(res,/AUTH|ORIGIN/.test(code)?403:/CONFLICT/.test(code)?409:/NOT_FOUND/.test(code)?404:/TOO_LARGE/.test(code)?413:400,{ok:false,error:code});}
  };
}
module.exports={createPlatformHandler};
