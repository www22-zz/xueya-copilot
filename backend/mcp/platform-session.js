'use strict';
const {Client,InMemoryTransport}=require('@modelcontextprotocol/client');
const {createPlatformServer}=require('./platform-server.js');
const {sdkAdapter}=require('./sdk-adapter.js');
const {createToolGateway}=require('./index.js');
const {scopeSchema,createLimiter}=require('./policy.js');
const connections=createLimiter(8);

/** Real SDK in-process wire transport lets the host inject B/C/E ports without serializing private state. */
async function createPlatformSession({scope,services,authority,reference},{signal,timeoutMs=5000,onTrace,allowedTools,lifetimeMs=60000}={}){
  scope=scopeSchema.parse(scope);signal?.throwIfAborted();const release=connections.acquire();
  const server=createPlatformServer({scope,services,authority,reference});
  // McpServer.connect is the locked SDK's legacy/session transport entry.
  // Modern HTTP uses createMcpHandler, tested separately; business schema v2 is independent.
  const client=new Client({name:'xueya-platform-host',version:'2.0.0'});
  const [left,right]=InMemoryTransport.createLinkedPair();
  let closing,timer;
  const onAbort=()=>{void close().catch(()=>{});};
  function close(){if(!closing)closing=(async()=>{clearTimeout(timer);signal?.removeEventListener('abort',onAbort);try{await client.close();}finally{try{await server.close();}finally{release();}}})();return closing;}
  try{
    await server.connect(right);await client.connect(left,{timeout:timeoutMs,signal});
    const adapter=sdkAdapter(client,{timeoutMs,signal,close});
    const gateway=createToolGateway({timeoutMs,allowedTools,onTrace});
    await gateway.registerServer('course',adapter,{defaultRisk:'read',risks:{prepare_action:'write',apply_action:'write',lookup_reference:'external'}});
    signal?.addEventListener('abort',onAbort,{once:true});if(signal?.aborted){await close();signal.throwIfAborted();}
    timer=setTimeout(onAbort,lifetimeMs);timer.unref();
    return{
      listTools:gateway.listTools,close,stats:gateway.stats,
      async call(name,args={},options={}){const value=await gateway.callTool('course__'+name,args,{signal:options.signal||signal});if(value.isError)throw new Error(value.content[0]?.text||'MCP_TOOL_FAILED');return value.structuredContent.schemaVersion==='2.0'?value.structuredContent.data:value.structuredContent;},
      // Trusted application methods: never included in MCP tools/list.
      confirm:input=>{if(!authority)throw new Error('WRITE_DISABLED');return authority.confirm(scope,input);},
      cancelAction:actionId=>{if(!authority)throw new Error('WRITE_DISABLED');return authority.cancel(scope,actionId);}
    };
  }catch(error){await close().catch(()=>{});throw error;}
}
module.exports={createPlatformSession,connectionStats:connections.stats};
