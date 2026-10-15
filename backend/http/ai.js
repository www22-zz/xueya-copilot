'use strict';

const {json}=require('./json.js');
const {LIMITS,normalizeChatRequest}=require('../../shared/contracts/index.js');

function createAIHandler(agent){
  return function handleAI(req,res){
    let bytes=0,chunks=[],tooLarge=false;
    req.on('data',chunk=>{
      bytes+=chunk.length;
      if(bytes>LIMITS.requestBytes){tooLarge=true;chunks=[];json(res,413,{ok:false,error:'REQUEST_TOO_LARGE'});}
      else if(!tooLarge)chunks.push(chunk);
    });
    req.on('end',async()=>{
      if(tooLarge)return;
      let input;
      try{input=JSON.parse(Buffer.concat(chunks).toString('utf8'));}
      catch{return json(res,400,{ok:false,error:'INVALID_JSON'});}
      try{normalizeChatRequest(input);}
      catch{return json(res,400,{ok:false,error:'EMPTY_QUESTION'});}
      try{json(res,200,await agent.run(input));}
      catch(error){
        const code=error.name==='AbortError'?'AI_TIMEOUT':['NO_SOURCES','EMPTY_QUESTION'].includes(error.message)?error.message:'AI_UNAVAILABLE';
        json(res,200,{ok:false,error:code,engine:'local-fallback'});
      }
    });
  };
}

module.exports={createAIHandler};
