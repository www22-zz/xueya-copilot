'use strict';

const {Client}=require('@modelcontextprotocol/client');
const {StdioClientTransport}=require('@modelcontextprotocol/client/stdio');
const {createLimiter}=require('./policy.js');
const {sdkAdapter}=require('./sdk-adapter.js');
const processes=createLimiter(4);

/** A real SDK connection: handshake, paginated discovery, calls and owned cleanup. */
async function connectStdio({command,args=[],cwd,env,timeoutMs=5000,signal,lifetimeMs=60000,limiter=processes}){
  signal?.throwIfAborted();
  if(typeof command!=='string'||!command||!Array.isArray(args)||args.some(arg=>typeof arg!=='string'))throw new Error('INVALID_MCP_COMMAND');
  const release=limiter.acquire();
  const client=new Client({name:'xueya-agent-host',version:'1.0.0'});
  const transport=new StdioClientTransport({command,args,cwd,env,stderr:'pipe'});
  // Stdout belongs to JSON-RPC. Drain stderr without logging private tool data.
  transport.stderr?.on('data',()=>{});
  let closed=false,timer;
  const onAbort=()=>{void close().catch(()=>{});};
  function cleanup(){closed=true;clearTimeout(timer);signal?.removeEventListener('abort',onAbort);release();}
  client.onclose=cleanup;
  async function close(){if(!closed){closed=true;try{await client.close();}finally{cleanup();}}}
  try{
    await client.connect(transport,{timeout:timeoutMs,signal});
    signal?.addEventListener('abort',onAbort,{once:true});
    if(signal?.aborted){await close();signal.throwIfAborted();}
    timer=setTimeout(onAbort,lifetimeMs);timer.unref();
    return sdkAdapter(client,{timeoutMs,signal,close,pid:()=>transport.pid});
  }catch(error){await close().catch(()=>{});throw error;}
}

module.exports={connectStdio,processStats:processes.stats};
