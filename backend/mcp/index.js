'use strict';

/**
 * MCP owner: transport-neutral tool gateway. No server is connected by default.
 * A real SDK client is adapted via registerServer; this is not a wire-protocol client.
 */
function createToolGateway({timeoutMs=10000}={}){
  const tools=new Map();

  function registerTool(definition,handler){
    if(!definition||typeof definition.name!=='string'||!definition.name||typeof handler!=='function')throw new Error('INVALID_TOOL');
    if(tools.has(definition.name))throw new Error('DUPLICATE_TOOL');
    const metadata=structuredClone({name:definition.name,description:definition.description||'',inputSchema:definition.inputSchema||{type:'object'}});
    tools.set(definition.name,{metadata,handler});
  }

  async function registerServer(serverId,adapter){
    if(!/^[a-zA-Z0-9_-]+$/.test(serverId)||typeof adapter?.listTools!=='function'||typeof adapter?.callTool!=='function')throw new Error('INVALID_MCP_ADAPTER');
    const definitions=await adapter.listTools();
    if(!Array.isArray(definitions)||definitions.some(d=>!d||typeof d.name!=='string'||!d.name))throw new Error('INVALID_MCP_ADAPTER');
    const names=definitions.map(d=>`${serverId}__${d.name}`);
    if(new Set(names).size!==names.length||names.some(name=>tools.has(name)))throw new Error('DUPLICATE_TOOL');
    definitions.forEach((definition,index)=>registerTool({...definition,name:names[index]},(args,options)=>adapter.callTool(definition.name,args,options)));
  }

  async function callTool(name,args={},options={}){
    const tool=tools.get(name);
    if(!tool)throw new Error('TOOL_NOT_FOUND');
    if(!args||typeof args!=='object'||Array.isArray(args))throw new Error('INVALID_TOOL_ARGUMENTS');
    const controller=new AbortController();
    let timer,onAbort;
    const cancellation=new Promise((resolve,reject)=>{
      onAbort=()=>{reject(new Error('TOOL_ABORTED'));controller.abort();};
      if(options.signal?.aborted){onAbort();return;}
      options.signal?.addEventListener('abort',onAbort,{once:true});
      timer=setTimeout(()=>{reject(new Error('TOOL_TIMEOUT'));controller.abort();},timeoutMs);
    });
    try{
      const result=await Promise.race([
        cancellation,
        Promise.resolve().then(()=>{
          if(controller.signal.aborted)throw new Error('TOOL_ABORTED');
          return tool.handler(args,{signal:controller.signal});
        })
      ]);
      if(!result||!Array.isArray(result.content))throw new Error('INVALID_TOOL_RESULT');
      return result;
    }finally{
      clearTimeout(timer);
      options.signal?.removeEventListener('abort',onAbort);
    }
  }

  return{registerTool,registerServer,listTools:async()=>[...tools.values()].map(t=>structuredClone(t.metadata)),callTool};
}

module.exports={createToolGateway};
