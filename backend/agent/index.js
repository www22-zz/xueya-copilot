'use strict';

const {normalizeChatRequest,LIMITS}=require('../../shared/contracts/index.js');
const {buildMessages}=require('./prompts.js');

/** Agent owner: orchestration and answer policy. HTTP and model transport stay outside. */
function createAgent({rag,model,tools}){
  return{
    async run(input){
      const request=normalizeChatRequest(input);
      const sources=await rag.prepareSources(request.sources);
      if(!sources.length)throw new Error('NO_SOURCES');
      const response=await model.generate({messages:buildMessages({...request,sources})});
      let parsed;
      try{parsed=JSON.parse(response.content.replace(/^\s*```(?:json)?\s*/i,'').replace(/\s*```\s*$/,''));}
      catch{throw new Error('AI_INVALID_RESPONSE');}
      if(!parsed||typeof parsed.answer!=='string'||!parsed.answer.trim())throw new Error('AI_INVALID_RESPONSE');
      const allowed=new Set(sources.map(s=>s.id));
      const ids=[...new Set((Array.isArray(parsed.sources)?parsed.sources:[]).filter(id=>allowed.has(id)))];
      return{
        ok:true,answer:parsed.answer.slice(0,LIMITS.answer),sources:ids,
        knowledgePoints:Array.isArray(parsed.knowledgePoints)?parsed.knowledgePoints.filter(p=>typeof p==='string').slice(0,8):[],
        model:response.model
      };
    },
    // Explicit extension points. The current grounded-Q&A workflow never
    // executes tools just because course text or model output mentions one.
    listTools:()=>tools.listTools(),
    callTool:(name,args,options)=>tools.callTool(name,args,options)
  };
}

module.exports={createAgent};
