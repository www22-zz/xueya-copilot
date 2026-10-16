'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {Client,InMemoryTransport}=require('@modelcontextprotocol/client');
const {createPlatformServer}=require('../../backend/mcp/platform-server.js');
async function session(t,reference){const server=createPlatformServer({scope:{userId:'u',courseId:'c'},reference});const client=new Client({name:'test',version:'1'}),[a,b]=InMemoryTransport.createLinkedPair();await server.connect(b);await client.connect(a);t.after(async()=>{await client.close();await server.close();});return client;}
test('reference connector is opt-in and bounds DOI-only outbound requests and metadata',async t=>{
  const disabled=await session(t);assert.equal((await disabled.listTools()).tools.length,0);
  let called;const client=await session(t,{enabled:true,fetchImpl:async(url,init)=>{called={url,init};return Response.json({message:{DOI:'10.1000/test',title:['Public paper'],publisher:'Publisher',published:{'date-parts':[[2026]]}}});}});
  const answer=await client.callTool({name:'lookup_reference',arguments:{doi:'10.1000/test'}});assert.equal(answer.structuredContent.title,'Public paper');assert.equal(answer.structuredContent.courseEvidence,false);assert.equal(called.url,'https://api.crossref.org/works/10.1000%2Ftest');assert.equal(called.init.redirect,'error');assert.ok(!JSON.stringify(called).includes('Authorization'));
  assert.equal((await client.callTool({name:'lookup_reference',arguments:{doi:'http://localhost/secret'}})).isError,true);
});
test('reference connector rejects mismatched/large results and reports external failure honestly',async t=>{
  for(const fetchImpl of [async()=>Response.json({message:{DOI:'10.1000/other'}}),async()=>new Response('x'.repeat(262145)),async()=>new Response('',{status:404})]){
    const client=await session(t,{enabled:true,fetchImpl});assert.equal((await client.callTool({name:'lookup_reference',arguments:{doi:'10.1000/test'}})).isError,true);
  }
});
