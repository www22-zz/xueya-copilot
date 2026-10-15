/* RAG owner: browser file ingestion. UI owns persistence, lists and notifications. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('../../../shared/learning.js'),require('../../../shared/contracts/index.js'));else root.XueyaLibrary=factory(root.XueyaLearning,root.XueyaContracts);})(typeof globalThis!=='undefined'?globalThis:this,function(L,C){
  'use strict';

  function invalid(message){const error=new Error(message);error.code='INVALID_DOCUMENT';throw error;}

  async function prepareDocument(file,{fetchImpl=globalThis.fetch,protocol=globalThis.location?.protocol||'http:'}={}){
    const ext=file.name.split('.').pop().toLowerCase();
    if(!['txt','md','pdf','docx'].includes(ext))invalid(`${file.name} 不支持，请选择 TXT、MD、PDF 或 DOCX。`);
    const isText=['txt','md'].includes(ext);
    if(file.size>(isText?C.LIMITS.textBytes:C.LIMITS.fileBytes))invalid(`${file.name} 超出大小限制。`);
    const doc={
      id:'upload-'+globalThis.crypto.randomUUID(),name:file.name,bytes:file.size,
      status:isText?'已解析，可检索':'内容待解析',
      meta:`${ext.toUpperCase()} · ${(file.size/1024).toFixed(1)} KB · ${L.today()}`
    };
    if(isText){
      const text=await file.text();
      if(!text.trim())invalid(`${file.name} 没有可读取的正文。`);
      if(text.length>C.LIMITS.textCharacters)invalid(`${file.name} 文本过长，请分成不超过 12 万字的文件。`);
      doc.chunks=L.extractChunks(text,doc);
    }else if(protocol!=='file:'){
      try{
        const response=await fetchImpl('/api/parse?type='+ext,{
          method:'POST',headers:{'Content-Type':'application/octet-stream'},body:await file.arrayBuffer(),signal:AbortSignal.timeout(30000)
        });
        const payload=await response.json();
        if(response.ok&&payload?.ok&&typeof payload.text==='string'&&payload.text.trim()){
          doc.chunks=L.extractChunks(payload.text.slice(0,C.LIMITS.parsedCharacters),doc);
          doc.status='已解析，可检索';
        }else if(response.ok&&payload?.ok&&payload.empty){
          doc.status='未识别到文字';
          doc.meta=`${ext.toUpperCase()} · 可能是扫描版或无正文 · 内容待解析`;
        }
      }catch{doc.status='内容待解析';}
    }
    return doc;
  }

  return{prepareDocument};
});
