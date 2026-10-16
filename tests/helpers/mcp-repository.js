'use strict';
// Durable test adapter for E's transaction contract, NOT an application database.
const fs=require('node:fs/promises');
const path=require('node:path');
const {createHash}=require('node:crypto');
function createDiskRepository(directory){
  const file=path.join(directory,'state.json');let queue=Promise.resolve();
  const key=(scope,kind,id)=>JSON.stringify([scope.userId,scope.courseId,kind,id]);
  async function load(){try{return JSON.parse(await fs.readFile(file,'utf8'));}catch(e){if(e.code==='ENOENT')return{entities:{},receipts:{},audits:[],sources:{}};throw e;}}
  function transaction(fn){const result=queue.then(async()=>{const state=await load(),value=await fn(state);await fs.writeFile(file+'.tmp',JSON.stringify(state));await fs.rename(file+'.tmp',file);return value;});queue=result.catch(()=>{});return result;}
  return{
    file,
    snapshot:load,
    seed:({scope,sources})=>transaction(state=>{state.sources[key(scope,'sources','all')]=sources;}),
    async listSources({scope}){return(await load()).sources[key(scope,'sources','all')]||[];},
    async readSource({scope,sourceId}){return(await this.listSources({scope})).find(s=>s.id===sourceId)||null;},
    async read({scope,kind,entityId}){return(await load()).entities[key(scope,kind,entityId)]||null;},
    async listNotes({scope,limit,cursor}){const state=await load();const prefix=JSON.stringify([scope.userId,scope.courseId,'note']).slice(0,-1)+',';const all=Object.entries(state.entities).filter(([k])=>k.startsWith(prefix)).map(([k,v])=>({id:JSON.parse(k)[3],...v}));const offset=cursor?Number(cursor):0;if(!Number.isInteger(offset)||offset<0)throw new Error('INVALID_CURSOR');return{items:all.slice(offset,offset+limit),nextCursor:offset+limit<all.length?String(offset+limit):null};},
    applyConfirmed:request=>transaction(state=>{
      const receiptKey=key(request.scope,'receipt',request.actionId);if(state.receipts[receiptKey])return state.receipts[receiptKey];
      const entityKey=key(request.scope,request.kind,request.entityId),current=state.entities[entityKey];
      if((current?.version||0)!==request.expectedVersion)throw new Error('VERSION_CONFLICT');
      for(const reference of request.references||[]){const source=(state.sources[key(request.scope,'sources','all')]||[]).find(s=>s.id===reference.sourceId);if(!source||(source.version??null)!==reference.version||createHash('sha256').update(JSON.stringify(source.quote)).digest('hex')!==reference.quoteHash)throw new Error('SOURCE_VERSION_CONFLICT');}
      const version=request.expectedVersion+1,auditId='audit-'+(state.audits.length+1);
      state.entities[entityKey]={version,value:request.after};state.audits.push({...request.audit,auditId});
      return state.receipts[receiptKey]={actionId:request.actionId,version,auditId};
    })
  };
}
module.exports={createDiskRepository};
