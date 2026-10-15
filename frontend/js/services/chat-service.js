/* Agent boundary for the UI: resolve passages, request AI, or return local excerpts. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('../../../shared/learning.js'),require('../../../shared/contracts/index.js'));else root.XueyaChat=factory(root.XueyaLearning,root.XueyaContracts);})(typeof globalThis!=='undefined'?globalThis:this,function(L,C){
  'use strict';

  function createChatService({fetchImpl=globalThis.fetch,protocol=globalThis.location?.protocol||'http:',timeoutMs=30000}={}){
    return{
      async ask(input){
        const request=C.normalizeChatRequest(input);
        let hits=L.retrieve(request.question,request.sources);
        if(!hits.length&&/它|这个|那么|继续|为什么|再解释/.test(request.question)&&input.previousSources?.length)hits=input.previousSources;
        try{
          if(protocol==='file:')throw new Error('LOCAL_PREVIEW');
          const response=await fetchImpl('/api/ai',{
            method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({...request,sources:hits}),signal:AbortSignal.timeout(timeoutMs)
          });
          const payload=await response.json();
          if(!response.ok||payload?.ok!==true||typeof payload.answer!=='string'||!payload.answer.trim()||!Array.isArray(payload.sources))throw new Error('AI_UNAVAILABLE');
          return{
            answer:payload.answer,sources:[...new Set(payload.sources)].map(id=>hits.find(s=>s.id===id)).filter(Boolean),
            engine:'MiMo 资料问答',online:true,knowledgePoints:payload.knowledgePoints||[],model:payload.model
          };
        }catch{
          return{answer:L.localAnswer(request.question,request.mode,hits),sources:hits,engine:'本地检索摘录',online:false,knowledgePoints:[]};
        }
      }
    };
  }

  return{createChatService};
});
