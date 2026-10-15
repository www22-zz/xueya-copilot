/* UTF-8 SSE framing shared by the model adapter and browser chat service. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaSSE=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';

  function eventData(block){
    const lines=block.split(/\r?\n/).filter(line=>line.startsWith('data:'));
    return lines.length?lines.map(line=>line.slice(5).replace(/^ /,'')).join('\n'):null;
  }

  async function* readSSE(stream){
    if(!stream?.getReader)throw new Error('INVALID_STREAM');
    const reader=stream.getReader(),decoder=new TextDecoder();
    let buffer='';
    try{
      while(true){
        const {done,value}=await reader.read();
        buffer+=done?decoder.decode():decoder.decode(value,{stream:true});
        let boundary;
        while((boundary=/\r?\n\r?\n/.exec(buffer))){
          const data=eventData(buffer.slice(0,boundary.index));
          buffer=buffer.slice(boundary.index+boundary[0].length);
          if(data!==null)yield data;
        }
        if(buffer.length>1048576)throw new Error('STREAM_TOO_LARGE');
        if(done)break;
      }
      const data=eventData(buffer);
      if(data!==null)yield data;
    }finally{
      try{await reader.cancel();}catch{}
      reader.releaseLock();
    }
  }

  return{readSSE};
});
