'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),http=require('node:http');
const {createPlatformHttpHandler}=require('../../backend/mcp/http-server.js');
const {connectHttp,httpConnectionStats}=require('../../backend/mcp/http-client.js');
async function endpoint(t,{services}={}){
  const requests=[];let endpoint;
  const server=http.createServer(async(req,res)=>{
    try{
      const chunks=[];for await(const chunk of req)chunks.push(chunk);
      const controller=new AbortController();res.on('close',()=>{if(!res.writableEnded)controller.abort();});
      const request=new Request('http://127.0.0.1:'+server.address().port+req.url,{method:req.method,headers:req.headers,signal:controller.signal,...(req.method==='POST'?{body:Buffer.concat(chunks)}:{})});
      requests.push({method:req.method,protocol:req.headers['mcp-protocol-version'],rpc:req.headers['mcp-method'],name:req.headers['mcp-name']});
      const response=await endpoint.fetch(request);res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));
    }catch{res.writeHead(500);res.end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base='http://127.0.0.1:'+server.address().port;
  endpoint=createPlatformHttpHandler({allowedHosts:[new URL(base).host],authenticate:async request=>request.headers.get('authorization')==='Bearer test-token'?{userId:'u',courseId:'course'}:null,servicesForScope:scope=>services||({listNotes:async()=>({items:[{id:'note',courseId:scope.courseId}],nextCursor:null})})});
  t.after(async()=>{await endpoint.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));});return{url:base+'/mcp',origin:base,requests,endpoint};
}
test('real HTTP SDK modern stateless discovery, bearer auth and routing headers',async t=>{
  const e=await endpoint(t);const adapter=await connectHttp({url:e.url,allowedOrigins:[e.origin],token:'test-token',allowLocalhost:true});t.after(()=>adapter.close());
  assert.equal((await adapter.listTools())[0].name,'list_notes');const result=await adapter.callTool('list_notes',{limit:1});assert.equal(result.structuredContent.data.items[0].courseId,'course');
  assert.equal((await adapter.health()).ok,true);
  assert.ok(e.requests.some(r=>r.rpc==='server/discover'));assert.ok(e.requests.some(r=>r.rpc==='tools/call'&&r.name==='list_notes'));assert.ok(e.requests.filter(r=>r.method==='POST').every(r=>r.protocol==='2026-07-28'));
  assert.ok(e.requests.every(r=>r.method==='POST'));await adapter.close();assert.equal(httpConnectionStats().active,0);
});
test('real HTTP SDK legacy stateless compatibility remains available',async t=>{
  const e=await endpoint(t);const adapter=await connectHttp({url:e.url,allowedOrigins:[e.origin],token:'test-token',allowLocalhost:true,protocol:'legacy'});t.after(()=>adapter.close());assert.equal((await adapter.listTools()).length,1);assert.equal((await adapter.callTool('list_notes',{})).structuredContent.data.items.length,1);
  const response=await fetch(e.url,{headers:{Authorization:'Bearer test-token',Accept:'text/event-stream'}});assert.equal(response.status,405);
});
test('HTTP rejects missing auth, unapproved URL/origin, oversized bodies and redirects',async t=>{
  const e=await endpoint(t);
  await assert.rejects(connectHttp({url:e.url,allowedOrigins:[e.origin],allowLocalhost:true,timeoutMs:1000}));
  await assert.rejects(connectHttp({url:'http://169.254.169.254/mcp',allowedOrigins:[],allowLocalhost:true}),/MCP_URL_FORBIDDEN/);
  assert.equal((await fetch(e.url,{headers:{Authorization:'Bearer test-token',Origin:'https://evil.example'}})).status,403);
  assert.equal((await fetch(e.origin+'/other',{headers:{Authorization:'Bearer test-token'}})).status,404);
  assert.equal((await fetch(e.url,{method:'POST',headers:{Authorization:'Bearer test-token'},body:'x'.repeat(262145)})).status,413);
  let redirectMode;await assert.rejects(connectHttp({url:e.url,allowedOrigins:[e.origin],allowLocalhost:true,token:'test-token',fetchImpl:async(url,init)=>{redirectMode=init.redirect;throw new Error('REDIRECT_BLOCKED');}}));assert.equal(redirectMode,'error');
});

test('modern HTTP cancellation aborts the real server business call',async t=>{
  let ready,aborted=false;const started=new Promise(resolve=>ready=resolve);
  const e=await endpoint(t,{services:{listNotes:async(_,options)=>{ready();await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{aborted=true;reject(new Error('CANCELLED'));},{once:true}));return{items:[]};}}});
  const adapter=await connectHttp({url:e.url,allowedOrigins:[e.origin],token:'test-token',allowLocalhost:true});t.after(()=>adapter.close());const controller=new AbortController();
  const pending=adapter.callTool('list_notes',{}, {signal:controller.signal});await started;controller.abort();await assert.rejects(pending);
  for(let i=0;i<100&&!aborted;i++)await new Promise(resolve=>setTimeout(resolve,10));assert.equal(aborted,true);
});
