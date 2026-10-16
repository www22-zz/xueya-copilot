'use strict';
const {randomUUID}=require('node:crypto');
const C=require('../../shared/contracts/platform.js');
const {transaction}=require('./database.js');
function createJobQueue({repository,resources,leaseMs=15000,pollMs=100,jobTimeoutMs=90000,now=Date.now}={}){
  const db=repository.db,owner=randomUUID(),handlers=new Map(),active=new Map();let timer,stopped=false;
  function event(id,data){db.prepare('INSERT INTO job_events(job_id,event,at) VALUES(?,?,?)').run(id,JSON.stringify(data),C.now());}
  function get(id,userId){const row=db.prepare('SELECT * FROM jobs WHERE id=? AND user_id=?').get(id,userId);return row?{id:row.id,courseId:row.course_id,type:row.type,status:row.status,progress:JSON.parse(row.progress),checkpoint:JSON.parse(row.checkpoint),result:row.result?JSON.parse(row.result):null,error:row.error,attempts:row.attempts,resource:row.resource,leaseUntil:row.lease_until,createdAt:row.created_at,updatedAt:row.updated_at}:null;}
  function submit(userId,input){const args=C.job.parse(input);repository.requireCourse({userId,courseId:args.courseId});if(!handlers.has(args.type))throw new Error('JOB_TYPE_UNAVAILABLE');if(Buffer.byteLength(JSON.stringify(args.input))>131072)throw new Error('JOB_INPUT_TOO_LARGE');return transaction(db,()=>{const prior=db.prepare('SELECT id FROM jobs WHERE user_id=? AND course_id=? AND type=? AND idempotency_key=?').get(userId,args.courseId,args.type,args.idempotencyKey);if(prior){const existing=db.prepare('SELECT input,resource FROM jobs WHERE id=?').get(prior.id);if(existing.input!==JSON.stringify(args.input)||existing.resource!==resources.choose(args.resource))throw new Error('IDEMPOTENCY_CONFLICT');return get(prior.id,userId);}const id=randomUUID(),at=C.now();db.prepare('INSERT INTO jobs(id,user_id,course_id,type,input,resource,status,max_attempts,idempotency_key,available_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)').run(id,userId,args.courseId,args.type,JSON.stringify(args.input),resources.choose(args.resource),'queued',args.maxAttempts,args.idempotencyKey,now(),at,at);event(id,{status:'queued'});return get(id,userId);});}
  function recover(){return transaction(db,()=>{const rows=db.prepare("SELECT * FROM jobs WHERE status IN ('running','cancelling') AND lease_until<=?").all(now());for(const row of rows){const status=row.resource==='api'?'unknown':row.status==='cancelling'?'cancelled':row.attempts>=row.max_attempts?'failed':'queued';db.prepare('UPDATE jobs SET status=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?').run(status,C.now(),row.id);event(row.id,{status,recovered:true});}return rows.length;});}
  function update(id,field,value){if(!['progress','checkpoint'].includes(field))throw new Error('INVALID_JOB_FIELD');const payload=JSON.stringify(value);if(Buffer.byteLength(payload)>65536)throw new Error('JOB_UPDATE_TOO_LARGE');const result=db.prepare(`UPDATE jobs SET ${field}=?,updated_at=? WHERE id=? AND lease_owner=? AND status='running'`).run(payload,C.now(),id,owner);if(!result.changes)throw new Error('JOB_LEASE_LOST');event(id,{[field]:value});}
  async function execute(row,release){
    const controller=new AbortController();active.set(row.id,controller);
    const timeout=setTimeout(()=>controller.abort(new Error('JOB_TIMEOUT')),jobTimeoutMs);timeout.unref();
    const heartbeat=setInterval(()=>{const changed=db.prepare("UPDATE jobs SET lease_until=? WHERE id=? AND lease_owner=? AND status='running'").run(now()+leaseMs,row.id,owner);if(!changed.changes)controller.abort();},Math.max(50,Math.floor(leaseMs/3)));heartbeat.unref();
    try{
      const handler=handlers.get(row.type),scope={userId:row.user_id,courseId:row.course_id};repository.requireCourse(scope);
      const commit=fn=>transaction(db,()=>{const lease=db.prepare("SELECT lease_owner,lease_until,status FROM jobs WHERE id=?").get(row.id);if(!lease||lease.lease_owner!==owner||lease.status!=='running'||lease.lease_until<=now())throw new Error('JOB_LEASE_LOST');controller.signal.throwIfAborted();return fn();});
      const result=await handler({scope,input:JSON.parse(row.input),jobId:row.id,checkpoint:JSON.parse(row.checkpoint)},{signal:controller.signal,progress:value=>update(row.id,'progress',value),checkpoint:value=>update(row.id,'checkpoint',value),commit});
      controller.signal.throwIfAborted();if(Buffer.byteLength(JSON.stringify(result))>131072)throw new Error('JOB_RESULT_TOO_LARGE');
      transaction(db,()=>{const done=db.prepare("UPDATE jobs SET status='succeeded',result=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=? AND lease_owner=? AND status='running'").run(JSON.stringify(result),C.now(),row.id,owner);if(!done.changes)throw new Error('JOB_LEASE_LOST');event(row.id,{status:'succeeded',result});});
    }catch(error){
      const current=get(row.id,row.user_id);if(!current)return;
      const paidUnknown=error.code==='RESULT_UNKNOWN'||row.resource==='api'&&error.code!=='NOT_SENT',cancelled=controller.signal.aborted||current.status==='cancelling';
      const status=paidUnknown?'unknown':cancelled?'cancelled':row.attempts<row.max_attempts?'queued':'failed';
      const code=/^[A-Z_]{3,80}$/.test(error.message)?error.message:'JOB_FAILED';
      db.prepare('UPDATE jobs SET status=?,error=?,available_at=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=? AND lease_owner=?').run(status,code,now()+Math.min(30000,250*2**row.attempts),C.now(),row.id,owner);event(row.id,{status,error:code});
    }finally{clearTimeout(timeout);clearInterval(heartbeat);active.delete(row.id);release();}
  }
  async function tick(){if(stopped)return;recover();const rows=db.prepare("SELECT * FROM jobs WHERE status='queued' AND available_at<=? ORDER BY created_at LIMIT 50").all(now());for(const row of rows){if(!handlers.has(row.type)||active.has(row.id))continue;const release=resources.acquire(row.resource);if(!release)continue;const claimed=db.prepare("UPDATE jobs SET status='running',attempts=attempts+1,lease_owner=?,lease_until=?,updated_at=? WHERE id=? AND status='queued'").run(owner,now()+leaseMs,C.now(),row.id);if(!claimed.changes){release();continue;}row.attempts++;event(row.id,{status:'running',attempt:row.attempts});void execute(row,release);}}
  return{
    register(type,handler){if(handlers.has(type)||typeof handler!=='function')throw new Error('INVALID_JOB_HANDLER');handlers.set(type,handler);},submit,get,recover,tick,
    list:userId=>db.prepare('SELECT id FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 100').all(userId).map(row=>get(row.id,userId)),
    events:(id,userId,after=0)=>{if(!get(id,userId))throw new Error('JOB_NOT_FOUND');return db.prepare('SELECT seq,event,at FROM job_events WHERE job_id=? AND seq>? ORDER BY seq LIMIT 100').all(id,after).map(row=>({seq:row.seq,at:row.at,...JSON.parse(row.event)}));},
    cancel(id,userId){const row=get(id,userId);if(!row)throw new Error('JOB_NOT_FOUND');if(['succeeded','failed','cancelled','unknown'].includes(row.status))return row;const state=active.has(id)?'cancelling':'cancelled';db.prepare('UPDATE jobs SET status=?,updated_at=? WHERE id=? AND user_id=?').run(state,C.now(),id,userId);active.get(id)?.abort();event(id,{status:state});return get(id,userId);},
    retry(id,userId){const row=get(id,userId);if(!row||!['failed','cancelled'].includes(row.status))throw new Error('JOB_NOT_RETRYABLE');db.prepare("UPDATE jobs SET status='queued',attempts=0,error=NULL,available_at=?,updated_at=? WHERE id=? AND user_id=?").run(now(),C.now(),id,userId);event(id,{status:'queued',manualRetry:true});return get(id,userId);},
    start(){stopped=false;timer=setInterval(()=>{void tick().catch(()=>{});},pollMs);timer.unref();void tick();},
    async stop(){stopped=true;clearInterval(timer);for(const controller of active.values())controller.abort();const deadline=Date.now()+5000;while(active.size&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,10));if(active.size)throw new Error('WORKERS_NOT_STOPPED');},
    types:()=>[...handlers.keys()]
  };
}
module.exports={createJobQueue};
