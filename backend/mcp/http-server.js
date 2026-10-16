'use strict';
const {createMcpHandler}=require('@modelcontextprotocol/server');
const {createPlatformServer}=require('./platform-server.js');
const {scopeSchema,createLimiter}=require('./policy.js');

/** Fetch-shaped endpoint for E's HTTP assembly. Authentication is host-owned, never model-owned. */
function createPlatformHttpHandler({authenticate,servicesForScope,authority,reference,allowedHosts=[],allowedOrigins=[],path='/mcp',legacy='stateless',maxConcurrent=8,maxRequestsPerMinute=120}={}){
  if(typeof authenticate!=='function'||typeof servicesForScope!=='function')throw new Error('MCP_AUTH_REQUIRED');
  const limiter=createLimiter(maxConcurrent);
  const rates=new Map();
  const handler=createMcpHandler(async ctx=>{
    const scope=scopeSchema.parse(ctx.authInfo?.extra?.scope);
    return createPlatformServer({scope,services:await servicesForScope(scope),authority,reference});
  },{legacy,onerror:()=>{}});
  return{
    close:handler.close,stats:limiter.stats,
    async fetch(request){
      const url=new URL(request.url),origin=request.headers.get('origin');
      const host=request.headers.get('host');
      if(!allowedHosts.includes(url.host)||host&&host!==url.host||origin&&!allowedOrigins.includes(origin))return new Response('Forbidden',{status:403});
      if(url.pathname!==path||url.search)return new Response('Not found',{status:404});
      let identity;
      try{identity=await authenticate(request);if(!identity)throw new Error();identity=scopeSchema.parse(identity);}catch{return new Response('Unauthorized',{status:401,headers:{'WWW-Authenticate':'Bearer'}});}
      const now=Date.now(),key=JSON.stringify(identity);
      for(const [key,entry] of rates)if(entry.expiresAt<=now)rates.delete(key);
      if(!rates.has(key)){if(rates.size>=1000)return new Response('Busy',{status:429});rates.set(key,{calls:0,expiresAt:now+60000});}
      if(++rates.get(key).calls>maxRequestsPerMinute)return new Response('Rate limited',{status:429});
      let release;
      try{
        release=limiter.acquire();
        let parsedBody;
        if(request.method==='POST'){
          if(Number(request.headers.get('content-length'))>262144)return new Response('Too large',{status:413});
          const reader=request.body?.getReader();let size=0,text='';const decoder=new TextDecoder();
          if(reader)try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>262144)return new Response('Too large',{status:413});text+=decoder.decode(value,{stream:true});}text+=decoder.decode();}finally{await reader.cancel().catch(()=>{});}
          try{parsedBody=JSON.parse(text);}catch{return new Response('Invalid JSON',{status:400});}
        }
        return await handler.fetch(request,{parsedBody,authInfo:{token:'verified-by-host',clientId:identity.userId,scopes:[],extra:{scope:identity}}});
      }catch(error){return new Response(error.message==='MCP_BUSY'?'Busy':'MCP failure',{status:error.message==='MCP_BUSY'?429:500});}
      finally{release?.();}
    }
  };
}
module.exports={createPlatformHttpHandler};
