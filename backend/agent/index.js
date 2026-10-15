'use strict';

const {normalizeChatRequest,LIMITS}=require('../../shared/contracts/index.js');
const {buildMessages}=require('./prompts.js');
const {parseModelJSON}=require('./json.js');
const {createPracticeTasks}=require('./practice.js');

function groundedAnswer(content,sources,model){
  const parsed=parseModelJSON(content);
  if(!parsed||typeof parsed.answer!=='string'||!parsed.answer.trim())throw new Error('AI_INVALID_RESPONSE');
  const allowed=new Set(sources.map(source=>source.id));
  return{
    ok:true,answer:parsed.answer.slice(0,LIMITS.answer),
    sources:[...new Set((Array.isArray(parsed.sources)?parsed.sources:[]).filter(id=>allowed.has(id)))],
    knowledgePoints:Array.isArray(parsed.knowledgePoints)?parsed.knowledgePoints.filter(point=>typeof point==='string').slice(0,8):[],model
  };
}

/** Agent owner: orchestration and answer policy. HTTP and model transport stay outside. */
function createAgent({rag,model,tools}){
  async function prepare(input){
    const request=normalizeChatRequest(input);
    const sources=await rag.prepareSources(request.sources);
    if(!sources.length)throw new Error('NO_SOURCES');
    return{sources,messages:buildMessages({...request,sources})};
  }
  return{
    async run(input,{signal}={}){
      const {sources,messages}=await prepare(input);
      const response=await model.generate({messages,signal});
      signal?.throwIfAborted();
      return groundedAnswer(response.content,sources,response.model);
    },
    async *stream(input,{signal}={}){
      const {sources,messages}=await prepare(input);
      if(typeof model.stream!=='function'){
        const response=await model.generate({messages,signal});
        signal?.throwIfAborted();
        yield{type:'done',...groundedAnswer(response.content,sources,response.model)};
        return;
      }
      let content='',modelName,received=0;
      for await(const event of model.stream({messages,signal})){
        signal?.throwIfAborted();
        if(['content','reasoning'].includes(event.type)&&typeof event.text==='string'){
          received+=event.text.length;
          if(received>200000)throw new Error('AI_INVALID_RESPONSE');
        }
        if(event.type==='content'&&typeof event.text==='string'){
          content+=event.text;
        }
        modelName=event.model||modelName;
        if(['content','reasoning'].includes(event.type)&&typeof event.text==='string')yield event;
      }
      signal?.throwIfAborted();
      yield{type:'done',...groundedAnswer(content,sources,modelName)};
    },
    ...createPracticeTasks({rag,model}),
    // Explicit extension points. The current grounded-Q&A workflow never
    // executes tools just because course text or model output mentions one.
    listTools:()=>tools.listTools(),
    callTool:(name,args,options)=>tools.callTool(name,args,options)
  };
}

module.exports={createAgent,groundedAnswer};
