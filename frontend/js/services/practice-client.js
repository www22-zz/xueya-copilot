/* HTTP owner for /api/practice/*. Caches the fixed bank so practice keeps working offline. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaPracticeClient=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const BANK='xueya-practice-bank';
function createPracticeClient({request,storage=globalThis.localStorage,accountId='local',getCourseId=null,now=()=>new Date().toISOString()}={}){
  let token='',loaded=false,bank=null,bankVersion='',serverState={serverSeq:0,statuses:{},notes:{}},online=globalThis.navigator?globalThis.navigator.onLine!==false:true;
  const listeners=new Set();
  let catalogInfo={generations:[]},loadedCourse=null;
  const course=()=>getCourseId?.()||'';
  const cacheKey=()=>getCourseId?BANK+':'+accountId+':'+course():BANK;
  function emit(){for(const fn of listeners)try{fn({online,offline:!online})}catch{}}
  function loadCache(){
    try{const raw=JSON.parse(storage.getItem(cacheKey())||'null');if(raw&&Array.isArray(raw.questions)&&raw.version){bank=raw.questions;bankVersion=raw.version;loadedCourse=course();catalogInfo={generations:raw.generations||[]};return true;}}catch{}
    return false;
  }
  function saveCache(version,questions,info={}){
    bank=questions;bankVersion=version;loadedCourse=course();catalogInfo=info;
    try{storage.setItem(cacheKey(),JSON.stringify({version,questions,generations:info.generations||[]}));}catch{/* quota: keep the bank memory-only */}
  }
  /* Transport: prefer an injected request, otherwise use fetch against the same origin. */
  async function send(path,options={}){
    const headers=Object.assign({'Content-Type':'application/json'},token?{'X-Xueya-Token':token}:{},options.headers||{});
    const body=options.body===undefined?undefined:JSON.stringify(options.body);
    options.signal?.throwIfAborted();
    if(request){const result=await request(path,{...options,headers,body});options.signal?.throwIfAborted();return result;}
    const response=await fetch(path,{method:options.method||'GET',headers,body,signal:options.signal||AbortSignal.timeout(options.timeout||5000)});
    let data;try{data=await response.json();}catch{throw Object.assign(new Error('PRACTICE_RESPONSE_INVALID'),{code:'PRACTICE_RESPONSE_INVALID'});}
    if(!response.ok||!data.ok)throw Object.assign(new Error(data.error||'PRACTICE_REQUEST_FAILED'),{code:data.error||'PRACTICE_REQUEST_FAILED'});
    return data;
  }
  function call(path,options={}){return send('/api/practice'+path,options);}
  async function authenticate(){
    const status=await send('/api/account/status',{timeout:3000});
    if((status.username||'local')!==accountId||(status.configured&&!status.authenticated))throw Object.assign(Error('请重新登录原账号后同步'),{code:'AUTH_REQUIRED'});
    const boot=await send('/api/platform/bootstrap',{timeout:3000});token=boot.token||'';
  }
  async function refreshState(){await authenticate();const result=await call('/state');serverState=result;loaded=true;online=true;return result;}
  async function refreshBank(){
    const requestedCourse=course();
    const catalog=await call('/bank'+(getCourseId?'?courseId='+encodeURIComponent(requestedCourse):''));
    if(requestedCourse===course()&&catalog?.ok)saveCache(catalog.version,catalog.questions,catalog);
    return catalog;
  }
  async function initialize(){
    try{await authenticate();}catch{offline();}
    try{
      await refreshBank();
    }catch(error){
      if(!loadCache())throw Object.assign(new Error('BANK_UNAVAILABLE'),{code:'BANK_UNAVAILABLE'});
      offline();
    }
    try{
      const state=await call('/state');
      if(state&&state.ok){serverState=state;loaded=true;online=true;}
    }catch{offline();}
    emit();
    return {version:bankVersion,count:(bank||[]).length};
  }
  function offline(){online=false;emit();}
  return {
    initialize,refreshState,refreshBank,
    get loaded(){return loaded;},
    bank(){return loadedCourse===course()?bank||[]:[];},
    catalog(){return loadedCourse===course()?catalogInfo:{generations:[]};},
    async resumeGeneration(id){await authenticate();return call('/generation/'+encodeURIComponent(id)+'/resume',{method:'POST',body:{}});},
    async cancelGeneration(id){await authenticate();return call('/generation/'+encodeURIComponent(id)+'/cancel',{method:'POST',body:{}});},
    get version(){return (getCourseId?loadedCourse+':':'')+bankVersion;},
    get online(){return online;},
    state(){return serverState;},
    subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},
    async submitOps(ops){
      try{
        await authenticate();
        const result=await call('/ops',{method:'POST',body:{ops,deviceTag:now()}});
        online=true;emit();
        return result;
      }catch(error){offline();throw error;}
    },
    async note(questionId,{signal}={}){
      const result=await call('/notes/'+encodeURIComponent(questionId),{signal});
      return result&&result.ok?result.note:null;
    },
    setToken(value){token=value||'';},
    async analysisList(){await authenticate();return call('/analysis');},
    async analysisReport(id){await authenticate();return call('/analysis/reports/'+encodeURIComponent(id));},
    async analysisJob(id){await authenticate();return call('/analysis/jobs/'+encodeURIComponent(id));},
    async createAnalysis(value){await authenticate();return call('/analysis',{method:'POST',body:value,timeout:15000});},
    async askAnalysis(id,value){await authenticate();return call('/analysis/reports/'+encodeURIComponent(id)+'/chat',{method:'POST',body:value,timeout:15000});},
  };
}
return{createPracticeClient,BANK};
});
