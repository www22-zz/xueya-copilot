'use strict';

const {readSSE}=require('../../shared/agent/sse.js');

function requestControl(timeoutMs,signal){
  const controller=new AbortController();
  const abort=()=>controller.abort();
  if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(abort,timeoutMs);
  return{signal:controller.signal,cleanup(){clearTimeout(timer);signal?.removeEventListener('abort',abort);}};
}

/** Model transport only. Inject fetchImpl for tests or a future provider adapter. */
function createMimoProvider({apiKey,baseURL,model,timeoutMs=25000},fetchImpl=globalThis.fetch){
  function request(messages,signal,temperature,stream=false){
    if(!apiKey)throw new Error('AI_UNAVAILABLE');
    return fetchImpl(baseURL.replace(/\/$/,'')+'/chat/completions',{
      method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+apiKey},
      body:JSON.stringify({model,temperature,messages,...(stream?{stream:true}:{})}),signal
    });
  }

  return{
    async generate({messages,temperature=.2,timeoutMs:limit=timeoutMs,signal}){
      const control=requestControl(limit,signal);
      try{
        const response=await request(messages,control.signal,temperature);
        if(!response.ok)throw new Error('AI_UNAVAILABLE');
        const payload=await response.json();
        const content=payload?.choices?.[0]?.message?.content;
        if(typeof content!=='string')throw new Error('AI_INVALID_RESPONSE');
        return{content,model};
      }finally{control.cleanup();}
    },
    async *stream({messages,signal,timeoutMs:limit=60000}){
      const control=requestControl(limit,signal);
      try{
        const response=await request(messages,control.signal,.2,true);
        if(!response.ok||!response.body)throw new Error('AI_UNAVAILABLE');
        for await(const data of readSSE(response.body)){
          if(data==='[DONE]')break;
          let payload;
          try{payload=JSON.parse(data);}catch{continue;}
          const delta=payload?.choices?.[0]?.delta;
          if(typeof delta?.reasoning_content==='string'&&delta.reasoning_content)yield{type:'reasoning',text:delta.reasoning_content,model};
          if(typeof delta?.content==='string'&&delta.content)yield{type:'content',text:delta.content,model};
        }
      }finally{control.cleanup();}
    }
  };
}

module.exports={createMimoProvider};
