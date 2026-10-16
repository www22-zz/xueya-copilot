'use strict';
const {randomUUID,createHash}=require('node:crypto');
const z=require('zod');
const {scopeSchema,id,bytes}=require('./policy.js');
const {validDate}=require('../../shared/learning.js');
const note=z.object({title:z.string().min(1).max(200),content:z.string().max(30000),sourceIds:z.array(id).max(100).default([])}).strict();
const question=z.object({prompt:z.string().min(1).max(5000),answer:z.string().min(1).max(10000),sourceIds:z.array(id).min(1).max(30)}).strict();
const plan=z.object({title:z.string().min(1).max(200),days:z.array(z.object({date:z.string().refine(validDate),tasks:z.array(z.object({title:z.string().min(1).max(300),minutes:z.number().int().min(1).max(480)}).strict()).max(30)}).strict()).max(90)}).strict();
const schemas={note,question,plan};
const prepareSchema=z.object({kind:z.enum(['note','question','plan']),entityId:id,expectedVersion:z.number().int().min(0),after:z.record(z.string(),z.unknown())}).strict();
const actionSchema=z.object({actionId:z.string().uuid()}).strict();
function canonical(value){if(Array.isArray(value))return'['+value.map(canonical).join(',')+']';if(value&&typeof value==='object')return'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';return JSON.stringify(value);}
const digest=value=>createHash('sha256').update(canonical(value)).digest('hex');
const same=(a,b)=>a.userId===b.userId&&a.courseId===b.courseId;

/** Repository owns CAS + data + audit + receipt in ONE transaction. No storage engine here. */
function createActionAuthority({repository,ttlMs=300000,now=Date.now,maxPending=100}={}){
  if(!repository||!['read','applyConfirmed'].every(k=>typeof repository[k]==='function'))throw new Error('WRITE_REPOSITORY_REQUIRED');
  const actions=new Map();let preparing=0;
  function get(scope,actionId){scope=scopeSchema.parse(scope);const a=actions.get(actionId);if(!a||!same(a.scope,scope))throw new Error('ACTION_NOT_FOUND');return a;}
  function live(a){if(a.expiresAt<=now())throw new Error('ACTION_EXPIRED');if(!['preview','confirmed'].includes(a.state))throw new Error('ACTION_NOT_PENDING');}
  return{
    async prepare(scope,input,{signal}={}){
      scope=scopeSchema.parse(scope);const args=prepareSchema.parse(input),after=schemas[args.kind].parse(args.after);
      if(bytes(after)>48000)throw new Error('ACTION_TOO_LARGE');
      for(const [key,a] of actions)if(a.expiresAt<=now()&&!['executing','uncertain'].includes(a.state))actions.delete(key);
      if(actions.size+preparing>=maxPending)throw new Error('ACTION_CAPACITY');
      preparing++;
      try{
      signal?.throwIfAborted();
      const current=await repository.read({scope,kind:args.kind,entityId:args.entityId},{signal});
      if((current?.version||0)!==args.expectedVersion)throw new Error('VERSION_CONFLICT');
      const references=[];
      for(const sourceId of after.sourceIds||[]){
        if(typeof repository.readSource!=='function')throw new Error('REFERENCE_VALIDATOR_REQUIRED');
        const source=await repository.readSource({scope,sourceId},{signal});
        if(!source||source.id!==sourceId||typeof source.quote!=='string')throw new Error('SOURCE_NOT_FOUND');
        references.push({sourceId,version:source.version??null,quoteHash:digest(source.quote)});
      }
      signal?.throwIfAborted();
      const preview={actionId:randomUUID(),scope,kind:args.kind,entityId:args.entityId,expectedVersion:args.expectedVersion,before:current?.value||null,after,references,expiresAt:now()+ttlMs};
      preview.digest=digest(preview);
      actions.set(preview.actionId,{...structuredClone(preview),state:'preview'});
      return structuredClone(preview);
      }finally{preparing--;}
    },
    preview(scope,actionId){const a=get(scope,actionId);live(a);const{state,...preview}=a;return structuredClone(preview);},
    // HOST ONLY: call from an authenticated explicit UI confirmation route, NEVER register as a model tool.
    confirm(scope,{actionId,digest:expectedDigest}){const a=get(scope,actionId);live(a);if(a.state!=='preview')throw new Error('ACTION_ALREADY_CONFIRMED');if(a.digest!==expectedDigest)throw new Error('ACTION_CHANGED');a.state='confirmed';return{actionId,state:'confirmed'};},
    cancel(scope,actionId){const a=get(scope,actionId);live(a);a.state='cancelled';return{actionId,state:'cancelled'};},
    async apply(scope,actionId,{signal}={}){
      const a=get(scope,actionId);
      if(a.state==='applied')return structuredClone(a.receipt);
      live(a);if(a.state!=='confirmed')throw new Error('ACTION_CONFIRMATION_REQUIRED');
      signal?.throwIfAborted();a.state='executing';
      try{
        const receipt=await repository.applyConfirmed({scope:structuredClone(a.scope),actionId,kind:a.kind,entityId:a.entityId,expectedVersion:a.expectedVersion,after:structuredClone(a.after),references:structuredClone(a.references),audit:{actionId,digest:a.digest,actor:a.scope.userId,courseId:a.scope.courseId,kind:a.kind,entityId:a.entityId,at:new Date(now()).toISOString()}},{signal});
        if(!receipt||receipt.actionId!==actionId||receipt.version!==a.expectedVersion+1||receipt.auditId==null)throw new Error('INVALID_WRITE_RECEIPT');
        a.receipt=structuredClone(receipt);a.state='applied';return structuredClone(receipt);
      }catch(error){a.state='uncertain';throw error;}
    }
  };
}
module.exports={createActionAuthority,prepareSchema,actionSchema};
