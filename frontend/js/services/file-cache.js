(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaFileCache=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
function createCache({indexedDB=globalThis.indexedDB,accountId=globalThis.XueyaDataOwner||''}={}){
  let connection;
  function db(){if(!indexedDB)return Promise.reject(new Error('原件缓存不可用，请保留本地文件。'));if(!connection)connection=new Promise((resolve,reject)=>{const req=indexedDB.open('xueya-originals-v1'+(accountId?':'+accountId:''),1);req.onupgradeneeded=()=>req.result.createObjectStore('files');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);req.onblocked=()=>reject(new Error('原件缓存被其他页面占用，请关闭旧页面重试。'));});return connection;}
  async function run(mode,key,value){const database=await db();return new Promise((resolve,reject)=>{const tx=database.transaction('files',mode),store=tx.objectStore('files');let result;const request=mode==='readonly'?store.get(key):value===null?store.delete(key):store.put(value,key);request.onsuccess=()=>{result=request.result;};tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('原件保存中断'));});}
  return{put:(key,file)=>run('readwrite',key,file),get:key=>run('readonly',key),remove:key=>run('readwrite',key,null)};
}
return{createCache};
});
