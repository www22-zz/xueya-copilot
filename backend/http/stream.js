'use strict';

const {readJson}=require('./body.js');

function createStreamHandler(agent){
  return(req,res)=>readJson(req,res,async input=>{
    const controller=new AbortController();
    const abort=()=>{if(!res.writableEnded)controller.abort();};
    res.on('close',abort);
    res.writeHead(200,{'Content-Type':'text/event-stream; charset=utf-8','Cache-Control':'no-store','Connection':'keep-alive','X-Accel-Buffering':'no'});
    const send=event=>{if(!res.writableEnded&&!res.destroyed)res.write(`data: ${JSON.stringify(event)}\n\n`);};
    try{
      for await(const event of agent.stream(input,{signal:controller.signal})){
        if(controller.signal.aborted)break;
        send(event);
      }
    }catch(error){
      const code=error.name==='AbortError'?'AI_TIMEOUT':['NO_SOURCES','EMPTY_QUESTION','AI_INVALID_RESPONSE'].includes(error.message)?error.message:'AI_UNAVAILABLE';
      send({type:'error',error:code});
    }finally{
      res.removeListener('close',abort);
      if(!res.writableEnded)res.end();
    }
  },{requireQuestion:true});
}

module.exports={createStreamHandler};
