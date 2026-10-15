'use strict';

const {json}=require('./json.js');
const {LIMITS,normalizeChatRequest}=require('../../shared/contracts/index.js');

function readBody(req,res,limit,onBody){
  let bytes=0,chunks=[],tooLarge=false,aborted=false;
  req.on('aborted',()=>{aborted=true;chunks=[];});
  req.on('error',()=>{aborted=true;chunks=[];});
  req.on('data',chunk=>{
    bytes+=chunk.length;
    if(bytes>limit){tooLarge=true;chunks=[];json(res,413,{ok:false,error:limit===LIMITS.fileBytes?'FILE_TOO_LARGE':'REQUEST_TOO_LARGE'});}
    else if(!tooLarge&&!aborted)chunks.push(chunk);
  });
  req.on('end',()=>{
    if(tooLarge||aborted)return;
    Promise.resolve().then(()=>onBody(Buffer.concat(chunks))).catch(()=>{
      if(!res.headersSent)json(res,500,{ok:false,error:'INTERNAL_ERROR'});else if(!res.writableEnded)res.end();
    });
  });
}

function readJson(req,res,onInput,{requireQuestion=false}={}){
  readBody(req,res,LIMITS.requestBytes,buffer=>{
    let input;
    try{input=JSON.parse(buffer.toString('utf8'));}
    catch{return json(res,400,{ok:false,error:'INVALID_JSON'});}
    if(!input||typeof input!=='object'||Array.isArray(input))return json(res,400,{ok:false,error:requireQuestion?'EMPTY_QUESTION':'INVALID_REQUEST'});
    if(requireQuestion){try{normalizeChatRequest(input);}catch{return json(res,400,{ok:false,error:'EMPTY_QUESTION'});}}
    return onInput(input);
  });
}

module.exports={readBody,readJson};
