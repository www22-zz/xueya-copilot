'use strict';
const {checkResult,bytes}=require('./policy.js');
function sdkAdapter(client,{timeoutMs=5000,signal,close,pid}={}){
  return{
    get pid(){return typeof pid==='function'?pid():pid;},
    async listTools(){
      const tools=[],seen=new Set(),names=new Set();let cursor;
      do{
        const page=await client.listTools(cursor?{cursor}:undefined,{timeout:timeoutMs,signal});
        if(bytes(page)>262144||!Array.isArray(page.tools))throw new Error('MCP_DISCOVERY_TOO_LARGE');
        for(const tool of page.tools){if(names.has(tool.name))throw new Error('MCP_DUPLICATE_TOOL');names.add(tool.name);tools.push(tool);}
        if(tools.length>128)throw new Error('MCP_DISCOVERY_TOO_LARGE');
        cursor=page.nextCursor;
        if(cursor){if(seen.has(cursor)||seen.size>=16)throw new Error('MCP_INVALID_PAGINATION');seen.add(cursor);}
      }while(cursor);
      return tools;
    },
    async callTool(name,args,{signal:callSignal}={}){
      if(bytes(args)>262144)throw new Error('TOOL_ARGUMENTS_TOO_LARGE');
      return checkResult(await client.callTool({name,arguments:args},{timeout:timeoutMs,signal:callSignal||signal}));
    },
    // tools/list works in both eras; ping was removed from the modern protocol.
    health:async()=>{await client.listTools(undefined,{timeout:timeoutMs,signal});return{ok:true};},
    close
  };
}
module.exports={sdkAdapter};
