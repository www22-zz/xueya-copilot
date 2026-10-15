/* Public contracts shared by browser and Node. Changes require cross-module review. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaContracts=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  /**
   * @typedef {Object} Source
   * @property {string} id Stable citation identifier; never renumber stored sources.
   * @property {string} title
   * @property {string} location Human-readable location; never invent a PDF page.
   * @property {string} quote Actual source text.
   * @property {string} [documentId]
   * @property {string[]} [keywords]
   * @property {boolean} [sample]
   *
   * @typedef {Object} ChatRequest
   * @property {string} question
   * @property {'ask'|'summarize'|'quiz'} [mode]
   * @property {Array<Source|string>} sources Selected passages, or built-in source IDs.
   * @property {Array<{role:'user'|'assistant',content:string}>} [history]
   *
   * @typedef {Object} ChatSuccess
   * @property {true} ok
   * @property {string} answer
   * @property {string[]} sources IDs from this request's actual source passages.
   * @property {string[]} knowledgePoints
   * @property {string} model
   *
   * @typedef {{ok:false,error:string,engine:'local-fallback'}} ChatFailure
   * @typedef {{name:string,description:string,inputSchema:Object}} ToolDefinition
   * @typedef {{content:Array<Object>,isError?:boolean,structuredContent?:Object}} ToolResult
   */
  const MODES=Object.freeze(['ask','summarize','quiz']);
  const LIMITS=Object.freeze({question:4000,history:8,historyContent:5000,sources:6,quote:3000,answer:16000,requestBytes:524288,textBytes:1048576,fileBytes:10485760,textCharacters:120000,parsedCharacters:1200000});

  function normalizeChatRequest(input){
    if(!input||typeof input!=='object'||Array.isArray(input))throw new Error('EMPTY_QUESTION');
    const question=String(input.question||'').trim().slice(0,LIMITS.question);
    if(!question)throw new Error('EMPTY_QUESTION');
    const history=(Array.isArray(input.history)?input.history:[]).slice(-LIMITS.history)
      .filter(m=>m&&['user','assistant'].includes(m.role)&&typeof m.content==='string')
      .map(m=>({role:m.role,content:m.content.slice(0,LIMITS.historyContent)}));
    return{question,mode:MODES.includes(input.mode)?input.mode:'ask',sources:Array.isArray(input.sources)?input.sources:[],history};
  }

  function sanitizeSources(input,catalog=[]){
    if(!Array.isArray(input))return[];
    const out=[];
    for(const item of input.slice(0,LIMITS.sources)){
      const source=typeof item==='string'?catalog.find(s=>s.id===item):item;
      if(!source||typeof source.id!=='string'||typeof source.quote!=='string')continue;
      const id=source.id.slice(0,150);
      if(out.some(s=>s.id===id))continue;
      out.push({id,title:String(source.title||'课程资料').slice(0,200),location:String(source.location||'').slice(0,150),quote:source.quote.slice(0,LIMITS.quote)});
    }
    return out;
  }

  return{MODES,LIMITS,normalizeChatRequest,sanitizeSources};
});
