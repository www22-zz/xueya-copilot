'use strict';
const {randomUUID}=require('node:crypto');
const {createLearningWorkflow}=require('../agent/learning-workflow.js');
const {createPlatformSession}=require('../mcp/platform-session.js');
const {normalizeContext}=require('../../shared/agent/context.js');
const {hash}=require('./repository.js');
const C=require('../../shared/contracts/platform.js');
function createStoredWorkflow({platform,model,rag,fallback}){
  const {repository,db}=platform;
  return{
    async* stream(input,options={}){
      const stored=repository.getWorkspace(platform.userId);
      if(!stored){yield* fallback.stream(input,options);return;}
      const s=platform.scope(input.courseId||stored.data.activeId),course=stored.data.courses.find(c=>c.id===s.courseId);if(!course)throw new Error('COURSE_NOT_FOUND');
      const candidate=await rag.retrieve({question:input.question,sources:repository.all(s,'source')});
      const selectedIds=new Set((input.context?.library||input.sources||[]).map(source=>typeof source==='string'?source:source.id));
      const sources=selectedIds.size?repository.all(s,'source').filter(source=>selectedIds.has(source.id)):candidate;
      const context=normalizeContext({library:sources,questions:repository.all(s,'question'),records:repository.all(s,'attempt'),examDate:course.data.examDate,minutes:course.data.minutes,previousSourceIds:input.context?.previousSourceIds});
      const workflow=createLearningWorkflow({model:require('./api-provider.js').createTrackedProvider({platform,model,scope:s}),openSession:async(_,opts)=>createPlatformSession({scope:s,services:{...platform.services(s),searchMaterials:async({query,limit})=>({sources:(await rag.retrieve({question:query,sources:context.library})).slice(0,limit)}),readSource:async({sourceId})=>{const source=context.library.find(s=>s.id===sourceId);if(!source)throw new Error('SOURCE_NOT_FOUND');return{source};}},authority:platform.authority},opts)});
      const id='run-'+randomUUID();let version=repository.put({scope:s,kind:'run',entityId:id,expectedVersion:0,value:{status:'running',question:input.question,startedAt:C.now()}}).version;
      let done=false;
      try{for await(const event of workflow.stream({...input,context},options)){
        if(event.type==='workflow')repository.put({scope:s,kind:'checkpoint',entityId:id,value:{stage:event.stage,status:event.status,at:C.now()}});
        if(event.type==='done'){version=repository.put({scope:s,kind:'run',entityId:id,expectedVersion:version,value:{status:'succeeded',question:input.question,result:event,finishedAt:C.now()}}).version;done=true;}
        yield{...event,runId:id};
      }}finally{if(!done)repository.put({scope:s,kind:'run',entityId:id,expectedVersion:version,value:{status:options.signal?.aborted?'cancelled':'interrupted',question:input.question,finishedAt:C.now()}});}
    },
    async run(input,options){for await(const event of this.stream(input,options))if(event.type==='done'){const{type,...result}=event;return result;}throw new Error('AGENT_INCOMPLETE');}
  };
}
module.exports={createStoredWorkflow};
