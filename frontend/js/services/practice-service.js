/* Agent owner: topic/question HTTP calls. Page state and dialogs remain in the UI. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaPractice=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';

  function createPracticeService({fetchImpl=globalThis.fetch,protocol=globalThis.location?.protocol||'http:'}={}){
    async function post(endpoint,input,timeoutMs,signal){
      signal?.throwIfAborted();
      if(protocol==='file:')throw new Error('AI_UNAVAILABLE');
      const response=await fetchImpl(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(timeoutMs)]):AbortSignal.timeout(timeoutMs)});
      const payload=await response.json();
      signal?.throwIfAborted();
      if(!response.ok||payload?.ok!==true)throw new Error(payload?.error||'AI_UNAVAILABLE');
      return payload;
    }
    return{
      async questions({sources,topic,focus,count=5,courseId},{signal}={}){
        const payload=await post('/api/questions',{sources,topic,focus,count,...(typeof courseId==='string'?{courseId}:{})},65000,signal);
        if(!Array.isArray(payload.questions)||!payload.questions.length)throw new Error('AI_EMPTY');
        return payload.questions;
      },
      async topics(sources,{signal,courseId}={}){
        const payload=await post('/api/topics',{sources,...(typeof courseId==='string'?{courseId}:{})},50000,signal);
        if(!Array.isArray(payload.topics))throw new Error('AI_INVALID_RESPONSE');
        return payload.topics;
      }
    };
  }

  return{createPracticeService};
});
