'use strict';

const {Client}=require('@modelcontextprotocol/client');
const {StdioClientTransport}=require('@modelcontextprotocol/client/stdio');

/** A real SDK connection: handshake, paginated discovery, calls and owned cleanup. */
async function connectStdio({command,args=[],cwd,env,timeoutMs=5000,signal}){
  signal?.throwIfAborted();
  const client=new Client({name:'xueya-agent-host',version:'1.0.0'});
  const transport=new StdioClientTransport({command,args,cwd,env,stderr:'pipe'});
  // Stdout belongs to JSON-RPC. Drain stderr without logging private tool data.
  transport.stderr?.on('data',()=>{});
  let closed=false;
  async function close(){if(!closed){closed=true;await client.close();}}
  try{
    await client.connect(transport,{timeout:timeoutMs,signal});
    return{
      get pid(){return transport.pid;},
      async listTools(){
        const tools=[],seen=new Set();
        let cursor;
        do{
          const page=await client.listTools(cursor?{cursor}:undefined,{timeout:timeoutMs,signal});
          tools.push(...page.tools);
          cursor=page.nextCursor;
          if(cursor){if(seen.has(cursor)||seen.size>=16)throw new Error('MCP_INVALID_PAGINATION');seen.add(cursor);}
        }while(cursor);
        return tools;
      },
      callTool:(name,args,{signal:callSignal}={})=>client.callTool({name,arguments:args},{timeout:timeoutMs,signal:callSignal||signal}),
      close
    };
  }catch(error){await close().catch(()=>{});throw error;}
}

module.exports={connectStdio};
