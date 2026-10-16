'use strict';
const {Client,StreamableHTTPClientTransport}=require('@modelcontextprotocol/client');
const {sdkAdapter}=require('./sdk-adapter.js');
const {createLimiter}=require('./policy.js');
const connections=createLimiter(4);

/** URLs/tokens are host configuration. Model arguments never select endpoints or credentials. */
async function connectHttp({url,allowedOrigins=[],token,timeoutMs=5000,signal,protocol='2026-07-28',allowLocalhost=false,fetchImpl=fetch}={}){
  const endpoint=new URL(url);
  if(endpoint.username||endpoint.password||endpoint.hash||endpoint.search||!allowedOrigins.includes(endpoint.origin)||!(endpoint.protocol==='https:'||(allowLocalhost&&endpoint.protocol==='http:'&&['127.0.0.1','[::1]'].includes(endpoint.hostname))))throw new Error('MCP_URL_FORBIDDEN');
  if(!['2026-07-28','legacy'].includes(protocol))throw new Error('MCP_PROTOCOL_FORBIDDEN');
  signal?.throwIfAborted();const release=connections.acquire();
  const client=new Client({name:'xueya-remote-host',version:'2.0.0'},{versionNegotiation:{mode:protocol==='legacy'?'legacy':{pin:protocol}}});
  const transport=new StreamableHTTPClientTransport(endpoint,{
    requestInit:{redirect:'error'},
    ...(token?{authProvider:{token:async()=>token}}:{}),
    fetch:async(input,init)=>{
      if(new URL(typeof input==='string'?input:input.url||input.href).href!==endpoint.href)throw new Error('MCP_URL_FORBIDDEN');
      const response=await fetchImpl(input,{...init,redirect:'error',signal:AbortSignal.any([...(init?.signal?[init.signal]:[]),...(signal?[signal]:[]),AbortSignal.timeout(timeoutMs)])});
      // Per-exchange streaming budget (including SSE); no unbounded response buffering.
      if(!response.body)return response;
      let bytes=0;const bounded=response.body.pipeThrough(new TransformStream({transform(chunk,controller){bytes+=chunk.byteLength;if(bytes>524288)throw new Error('MCP_RESPONSE_TOO_LARGE');controller.enqueue(chunk);}}));
      return new Response(bounded,{status:response.status,statusText:response.statusText,headers:response.headers});
    }
  });
  let closing,timer;
  const onAbort=()=>{void close().catch(()=>{});};
  function close(){if(!closing)closing=(async()=>{clearTimeout(timer);signal?.removeEventListener('abort',onAbort);try{await client.close();}finally{release();}})();return closing;}
  try{
    await client.connect(transport,{timeout:timeoutMs,signal});
    signal?.addEventListener('abort',onAbort,{once:true});if(signal?.aborted){await close();signal.throwIfAborted();}
    timer=setTimeout(onAbort,60000);timer.unref();
    return sdkAdapter(client,{timeoutMs,signal,close});
  }catch(error){await close().catch(()=>{});throw error;}
}
module.exports={connectHttp,httpConnectionStats:connections.stats};
