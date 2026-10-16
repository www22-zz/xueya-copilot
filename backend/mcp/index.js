'use strict';
const {AjvJsonSchemaValidator}=require('@modelcontextprotocol/client/validators/ajv');
const {bytes,checkResult,createLimiter}=require('./policy.js');

/** Host policy is authoritative; remote annotations never grant privileges. */
function createToolGateway({timeoutMs=10000,maxDurationMs=60000,maxArgumentBytes=65536,maxResultBytes=131072,maxConcurrent=4,maxCalls=64,maxCostUnits=64,allowedTools,onTrace=()=>{}}={}){
  const tools=new Map(),ajv=new AjvJsonSchemaValidator(),limiter=createLimiter(maxConcurrent);
  let calls=0,cost=0;const deadline=Date.now()+maxDurationMs;
  function registerTool(definition,handler){
    if(!definition||!/^[-a-zA-Z0-9_]{1,150}$/.test(definition.name)||typeof handler!=='function')throw new Error('INVALID_TOOL');
    if(tools.has(definition.name))throw new Error('DUPLICATE_TOOL');
    const metadata=structuredClone({name:definition.name,description:definition.description||'',inputSchema:definition.inputSchema||{type:'object'},...(definition.annotations?{annotations:definition.annotations}:{}),_meta:{version:definition.version||'1.0.0',risk:definition.risk||'read'}});
    tools.set(definition.name,{metadata,handler,validate:ajv.getValidator(metadata.inputSchema),cost:definition.costUnits||1});
  }
  async function registerServer(serverId,adapter,{risks={},defaultRisk='unknown'}={}){
    if(!/^[a-zA-Z0-9_-]+$/.test(serverId)||typeof adapter?.listTools!=='function'||typeof adapter?.callTool!=='function')throw new Error('INVALID_MCP_ADAPTER');
    const definitions=await adapter.listTools();
    if(!Array.isArray(definitions)||definitions.some(d=>!d||typeof d.name!=='string'||!d.name))throw new Error('INVALID_MCP_ADAPTER');
    const names=definitions.map(d=>`${serverId}__${d.name}`);
    if(names.some(n=>!/^[-a-zA-Z0-9_]{1,150}$/.test(n)))throw new Error('INVALID_TOOL');
    if(new Set(names).size!==names.length||names.some(name=>tools.has(name)))throw new Error('DUPLICATE_TOOL');
    definitions.forEach(d=>ajv.getValidator(d.inputSchema||{type:'object'}));
    definitions.forEach((d,i)=>registerTool({...d,name:names[i],risk:risks[d.name]||defaultRisk},(args,options)=>adapter.callTool(d.name,args,options)));
  }
  async function callTool(name,args={},options={}){
    const tool=tools.get(name);
    if(!tool)throw new Error('TOOL_NOT_FOUND');
    if(allowedTools&&!allowedTools.includes(name))throw new Error('TOOL_FORBIDDEN');
    if(!args||typeof args!=='object'||Array.isArray(args)||!tool.validate(args).valid)throw new Error('INVALID_TOOL_ARGUMENTS');
    if(bytes(args)>maxArgumentBytes)throw new Error('TOOL_ARGUMENTS_TOO_LARGE');
    if(options.signal?.aborted)throw new Error('TOOL_ABORTED');
    if(Date.now()>=deadline||calls>=maxCalls||cost+tool.cost>maxCostUnits)throw new Error('TOOL_BUDGET_EXCEEDED');
    const release=limiter.acquire(),controller=new AbortController(),start=performance.now();
    calls++;cost+=tool.cost;
    let timer,onAbort,status='completed';
    const cancellation=new Promise((_,reject)=>{
      onAbort=()=>{controller.abort();reject(new Error('TOOL_ABORTED'));};
      options.signal?.addEventListener('abort',onAbort,{once:true});
      timer=setTimeout(()=>{controller.abort();reject(new Error('TOOL_TIMEOUT'));},Math.min(timeoutMs,Math.max(1,deadline-Date.now())));
    });
    // Non-cooperative handlers retain their permit; repeated timeouts cannot overrun them.
    const work=Promise.resolve().then(()=>{controller.signal.throwIfAborted();return tool.handler(structuredClone(args),{signal:controller.signal});}).finally(release);
    try{return checkResult(await Promise.race([work,cancellation]),maxResultBytes);}
    catch(error){status=/^[A-Z_]+$/.test(error.message)?error.message:'TOOL_FAILED';throw error;}
    finally{clearTimeout(timer);options.signal?.removeEventListener('abort',onAbort);try{onTrace({tool:name,status,durationMs:Math.round(performance.now()-start),calls,costUnits:cost});}catch{/* Logging cannot change tool semantics. */}}
  }
  return{registerTool,registerServer,listTools:async()=>[...tools.values()].filter(t=>!allowedTools||allowedTools.includes(t.metadata.name)).map(t=>structuredClone(t.metadata)),callTool,stats:()=>({...limiter.stats(),calls,costUnits:cost})};
}
module.exports={createToolGateway};
