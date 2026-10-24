/* HTTP owner for /api/practice/*. Caches the fixed bank so practice keeps working offline. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaPracticeClient=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const BANK='xueya-practice-bank';
function createPracticeClient({request,storage=globalThis.localStorage,now=()=>new Date().toISOString()}={}){
  let token='',bank=null,bankVersion='',serverState={serverSeq:0,statuses:{},notes:{}},online=globalThis.navigator?globalThis.navigator.onLine!==false:true;
  const listeners=new Set();
  function emit(){for(const fn of listeners)try{fn({online,offline:!online})}catch{}}
  function loadCache(){
    try{const raw=JSON.parse(storage.getItem(BANK)||'null');if(raw&&Array.isArray(raw.questions)&&raw.version){bank=raw.questions;bankVersion=raw.version;return true;}}catch{}
    return false;
  }
  function saveCache(version,questions){
    bank=questions;bankVersion=version;
    try{storage.setItem(BANK,JSON.stringify({version,questions}));}catch{/* quota: keep the bank memory-only */}  }
  async function call(path,options={}){
    if(!request)throw Object.assign(new Error('NO_TRANSPORT'),{code:'NO_TRANSPORT'});
    const headers=Object.assign({'Content-Type':'application/json'},token?{'X-Xueya-Token':token}:{},options.headers||{});
    const body=options.body===undefined?undefined:JSON.stringify(options.body);
    return request('/api/practice'+path,{...options,headers,body});
  }
  async function initialize(){
    if(request){
      try{
        const boot=await request('/api/platform/bootstrap',{timeout:3000});
        token=boot&&boot.token||'';
      }catch{/* offline: fall back to whatever is cached */}
    }
    try{
      const catalog=await call('/bank');
      if(catalog&&catalog.ok)saveCache(catalog.version,catalog.questions);
    }catch(error){
      if(!loadCache())throw Object.assign(new Error('BANK_UNAVAILABLE'),{code:'BANK_UNAVAILABLE'});
      if(String(error.code||error.message)!=='BANK_UNAVAILABLE')offline();
    }
    try{
      const state=await call('/state');
      if(state&&state.ok)serverState={serverSeq:state.serverSeq||0,statuses:state.statuses||{},notes:state.notes||{}};
    }catch{/* the local queue keeps working without a fresh state snapshot */}
    online=true;emit();
    return {version:bankVersion,count:(bank||[]).length};
  }
  function offline(){online=false;emit();}
  return {
    initialize,
    bank(){return bank||[];},
    get version(){return bankVersion;},
    get online(){return online;},
    state(){return serverState;},
    subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},
    async submitOps(ops){
      try{
        const result=await call('/ops',{method:'POST',body:{ops,deviceTag:now()}});
        if(!result||!result.ok)throw Object.assign(new Error(result&&result.error||'PRACTICE_SYNC_FAILED'),{code:result&&result.error});
        online=true;emit();
        return result;
      }catch(error){offline();throw error;}
    },
    async note(questionId){
      const result=await call('/notes/'+encodeURIComponent(questionId));
      return result&&result.ok?result.note:null;
    },
    setToken(value){token=value||'';},
  };
}
return{createPracticeClient,BANK};
});
