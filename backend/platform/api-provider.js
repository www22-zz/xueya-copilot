'use strict';
const {randomUUID}=require('node:crypto');
const C=require('../../shared/contracts/platform.js');
const {hash}=require('./repository.js');
function createTrackedProvider({platform,model,scope:s}){
  const db=platform.db;
    const start=messages=>{const release=platform.resources.acquire('api');if(!release)throw new Error('API_BUSY');const id=randomUUID();try{db.prepare('INSERT INTO invocations(id,user_id,course_id,status,provider,request_hash,at,updated_at) VALUES(?,?,?,?,?,?,?,?)').run(id,s.userId,s.courseId,'pending','mimo',hash(messages),C.now(),C.now());}catch(error){release();throw error;}return{id,release};};
    const finish=(request,status,usage)=>{try{db.prepare('UPDATE invocations SET status=?,updated_at=?,usage_json=?,billing_status=? WHERE id=?').run(status,C.now(),usage?JSON.stringify(usage):null,status==='unknown'?'unknown':'not_reported',request.id);}finally{request.release();}};
    return{
      async generate(input){const request=start(input.messages);try{const result=await model.generate(input);finish(request,'succeeded',result.usage);return result;}catch(error){finish(request,'unknown');throw error;}},
      async* stream(input){const request=start(input.messages);let complete=false,usage;try{if(typeof model.stream==='function')for await(const event of model.stream(input)){if(event.type==='usage')usage=event.usage;yield event;}else{const result=await model.generate(input);usage=result.usage;yield{type:'content',text:result.content,model:result.model};}complete=true;}finally{finish(request,complete?'succeeded':'unknown',usage);}}
    };
}
module.exports={createTrackedProvider};
