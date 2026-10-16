'use strict';
const {Worker}=require('node:worker_threads');
const path=require('node:path');
function parseArtifact(input,{signal}={}){
  signal?.throwIfAborted();
  return new Promise((resolve,reject)=>{
    const worker=new Worker(path.join(__dirname,'parse-worker.js'),{workerData:input,resourceLimits:{maxOldGenerationSizeMb:128}});let settled=false;
    function finish(error,value){if(settled)return;settled=true;signal?.removeEventListener('abort',abort);void worker.terminate().finally(()=>error?reject(error):resolve(value));}
    const abort=()=>finish(signal.reason||new Error('PARSE_ABORTED'));
    signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();
    worker.once('message',message=>message.ok?finish(null,message):finish(new Error(message.error||'PARSE_FAILED')));
    worker.once('error',()=>finish(new Error('PARSE_WORKER_FAILED')));
    worker.once('exit',()=>{if(!settled)finish(new Error('PARSE_WORKER_EXITED'));});
  });
}
module.exports={parseArtifact};
