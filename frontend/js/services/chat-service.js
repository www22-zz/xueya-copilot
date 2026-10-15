/* Agent boundary for the UI: resolve passages, request AI, or return local excerpts. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('../../../shared/learning.js'),require('../../../shared/contracts/index.js'),require('../../../shared/agent/sse.js'));else root.XueyaChat=factory(root.XueyaLearning,root.XueyaContracts,root.XueyaSSE);})(typeof globalThis!=='undefined'?globalThis:this,function(L,C,SSE){
  'use strict';

  function createChatService({fetchImpl=globalThis.fetch,protocol=globalThis.location?.protocol||'http:',timeoutMs=30000}={}){
    function prepare(input){
      const request=C.normalizeChatRequest(input);
      let hits=L.retrieve(request.question,request.sources);
      if(!hits.length&&/它|这个|那么|继续|为什么|再解释/.test(request.question)&&input.previousSources?.length)hits=input.previousSources;
      return{request,hits};
    }
    function success(payload,hits){
      if(payload?.ok!==true||typeof payload.answer!=='string'||!payload.answer.trim()||!Array.isArray(payload.sources))throw new Error('AI_UNAVAILABLE');
      return{answer:payload.answer,sources:[...new Set(payload.sources)].map(id=>hits.find(source=>source.id===id)).filter(Boolean),engine:'MiMo 资料问答',online:true,knowledgePoints:payload.knowledgePoints||[],model:payload.model};
    }
    function fallback(request,hits){
      return{answer:L.localAnswer(request.question,request.mode,hits),sources:hits,reasoning:'',engine:'本地检索摘录',online:false,knowledgePoints:[]};
    }
    return{
      async ask(input){
        const {request,hits}=prepare(input);
        try{
          if(protocol==='file:')throw new Error('LOCAL_PREVIEW');
          const response=await fetchImpl('/api/ai',{
            method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({...request,sources:hits}),signal:AbortSignal.timeout(timeoutMs)
          });
          const payload=await response.json();
          if(!response.ok)throw new Error('AI_UNAVAILABLE');
          return success(payload,hits);
        }catch{return fallback(request,hits);}
      },
      async stream(input,{onUpdate=()=>{}}={}){
        const {request,hits}=prepare(input);
        try{
          if(protocol==='file:')throw new Error('LOCAL_PREVIEW');
          const response=await fetchImpl('/api/ai/stream',{
            method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...request,sources:hits}),signal:AbortSignal.timeout(90000)
          });
          if(!response.ok||!response.headers.get('content-type')?.includes('text/event-stream'))throw new Error('AI_UNAVAILABLE');
          let content='',reasoning='',completed;
          for await(const data of SSE.readSSE(response.body)){
            let event;
            try{event=JSON.parse(data);}catch{throw new Error('AI_INVALID_RESPONSE');}
            if(event.type==='error')throw new Error(event.error||'AI_UNAVAILABLE');
            if(event.type==='done'){
              completed={...success(event,hits),reasoning};
              break;
            }
            if(event.type==='content'&&typeof event.text==='string')content+=event.text;
            if(event.type==='reasoning'&&typeof event.text==='string')reasoning+=event.text;
            const fragment=content.match(/"answer"\s*:\s*"((?:[^"\\]|\\.)*)/s)?.[1];
            let answer='';
            if(fragment){try{answer=JSON.parse('"'+fragment.replace(/\\u[0-9a-fA-F]{0,3}$/,'')+'"');}catch{}}
            onUpdate({answer,reasoning});
          }
          if(!completed)throw new Error('AI_INCOMPLETE_STREAM');
          return completed;
        }catch{return fallback(request,hits);}
      }
    };
  }

  return{createChatService};
});
