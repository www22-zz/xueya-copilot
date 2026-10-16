'use strict';
// Ordinary file parsing only. No AI model, GPU runtime, Python or network access.
const {parentPort,workerData}=require('node:worker_threads');
const {createRagService}=require('../rag/index.js');
(async()=>{
  const rag=createRagService(),buffer=Buffer.from(workerData.buffer),{kind,document}=workerData;
  let text;
  if(['txt','md'].includes(kind)){try{text=new TextDecoder('utf-8',{fatal:true}).decode(buffer);}catch{throw new Error('INVALID_TEXT_ENCODING');}}
  else text=(await rag.parseDocument({buffer,kind})).text;
  if(!text.trim())throw new Error('NO_EXTRACTABLE_TEXT');if(text.length>1200000)throw new Error('TEXT_TOO_LARGE');
  parentPort.postMessage({ok:true,...await rag.ingest({text,document})});
})().catch(error=>parentPort.postMessage({ok:false,error:/^[A-Z_]+$/.test(error.message)?error.message:'PARSE_FAILED'}));
