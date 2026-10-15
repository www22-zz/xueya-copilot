/* Frontend ports. E binds these to frozen APIs; no guessed endpoint or paid call. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaWorkspaceService=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const names=['uploadDocument','listDocuments','updateDocument','removeDocument','imageChat','transcribe','video','speak','graph','original','correctOCR','variant'];
function normalizeDocument(doc){
  if(!doc||typeof doc.id!=='string'||typeof doc.name!=='string'||typeof doc.status!=='string')throw new Error('资料服务返回了不完整的文档信息。');
  const chunks=Array.isArray(doc.chunks)?doc.chunks:[];
  if(chunks.some(s=>!s||typeof s.id!=='string'||typeof s.quote!=='string'||typeof s.title!=='string'))throw new Error('资料正文缺少有效的来源标识或文本。');
  return{...doc,meta:String(doc.meta||''),tags:(Array.isArray(doc.tags)?doc.tags:[]).filter(t=>typeof t==='string'),chunks:chunks.map(s=>({...s,documentId:doc.id,location:String(s.location||''),keywords:(Array.isArray(s.keywords)?s.keywords:[]).filter(k=>typeof k==='string')}))};
}
function createService({adapter={},protocol=globalThis.location?.protocol||'http:',timeoutMs=90000}={}){
  const capabilities=Object.fromEntries(names.map(name=>[name,protocol!=='file:'&&typeof adapter[name]==='function']));
  capabilities.extendedPractice=Array.isArray(adapter.questionTypes)&&['multiple','short'].every(type=>adapter.questionTypes.includes(type));
  async function call(name,input,{signal,onProgress=()=>{}}={}){
    signal?.throwIfAborted();
    if(!capabilities[name]){const error=new Error('该能力尚未接通，请等待对应服务配置完成。');error.code='CAPABILITY_UNAVAILABLE';throw error;}
    const controller=new AbortController(),operationSignal=signal?AbortSignal.any([signal,controller.signal]):controller.signal;let timer,abort;
    try{
      const stopped=new Promise((resolve,reject)=>{abort=()=>reject(operationSignal.reason||new DOMException('已取消','AbortError'));if(operationSignal.aborted)abort();else operationSignal.addEventListener('abort',abort,{once:true});});
      timer=setTimeout(()=>controller.abort(new DOMException('处理超时，请重试。','TimeoutError')),timeoutMs);
      const result=await Promise.race([Promise.resolve().then(()=>adapter[name](input,{signal:operationSignal,onProgress:progress=>{if(!operationSignal.aborted)onProgress(progress);}})),stopped]);
      operationSignal.throwIfAborted();if(result===null||result===undefined)throw new Error('服务没有返回有效结果。');return result;
    }finally{clearTimeout(timer);if(abort)operationSignal.removeEventListener('abort',abort);controller.abort();}
  }
  return{capabilities,call};
}
return{createService,names,normalizeDocument};
});
