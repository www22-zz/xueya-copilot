'use strict';

/** Model transport only. Inject fetchImpl for tests or a future provider adapter. */
function createMimoProvider({apiKey,baseURL,model,timeoutMs=25000},fetchImpl=globalThis.fetch){
  return{
    async generate({messages}){
      if(!apiKey)throw new Error('AI_UNAVAILABLE');
      const controller=new AbortController();
      const timer=setTimeout(()=>controller.abort(),timeoutMs);
      try{
        const response=await fetchImpl(baseURL.replace(/\/$/,'')+'/chat/completions',{
          method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+apiKey},
          body:JSON.stringify({model,temperature:.2,messages}),signal:controller.signal
        });
        if(!response.ok)throw new Error('AI_UNAVAILABLE');
        const payload=await response.json();
        const content=payload?.choices?.[0]?.message?.content;
        if(typeof content!=='string')throw new Error('AI_INVALID_RESPONSE');
        return{content,model};
      }finally{clearTimeout(timer);}
    }
  };
}

module.exports={createMimoProvider};
