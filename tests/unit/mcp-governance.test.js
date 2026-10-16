'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {createToolGateway}=require('../../backend/mcp/index.js');
const {sdkAdapter}=require('../../backend/mcp/sdk-adapter.js');
const {createLimiter}=require('../../backend/mcp/policy.js');
const result=value=>({content:[{type:'text',text:value}]});
test('schema dialect validation, allowlist, argument/result/step/cost budgets and safe traces',async()=>{
  const traces=[],gateway=createToolGateway({allowedTools:['safe'],maxArgumentBytes:60,maxResultBytes:100,maxCalls:2,onTrace:trace=>traces.push(trace)});
  gateway.registerTool({name:'safe',inputSchema:{type:'object',properties:{term:{type:'string'}},required:['term'],additionalProperties:false}},async args=>result(args.term));
  gateway.registerTool({name:'hidden'},async()=>result('x'));
  assert.equal((await gateway.listTools()).length,1);await assert.rejects(gateway.callTool('hidden'),/TOOL_FORBIDDEN/);
  await assert.rejects(gateway.callTool('safe',{term:2}),/INVALID_TOOL_ARGUMENTS/);await assert.rejects(gateway.callTool('safe',{term:'x'.repeat(100)}),/TOOL_ARGUMENTS_TOO_LARGE/);
  await gateway.callTool('safe',{term:'secret text'});await gateway.callTool('safe',{term:'secret text'});await assert.rejects(gateway.callTool('safe',{term:'x'}),/TOOL_BUDGET_EXCEEDED/);
  assert.ok(!JSON.stringify(traces).includes('secret'));assert.equal(traces[1].calls,2);
  const costs=createToolGateway({maxCostUnits:2});costs.registerTool({name:'expensive',costUnits:3},async()=>result('x'));await assert.rejects(costs.callTool('expensive'),/TOOL_BUDGET_EXCEEDED/);
  const large=createToolGateway({maxResultBytes:60});large.registerTool({name:'large'},async()=>result('x'.repeat(100)));await assert.rejects(large.callTool('large'),/TOOL_RESULT_TOO_LARGE/);
  const malformed=createToolGateway();malformed.registerTool({name:'bad'},async()=>({content:[{type:'text',text:{command:'run'}}]}));await assert.rejects(malformed.callTool('bad'),/INVALID_TOOL_RESULT/);
});
test('timed-out non-cooperative adapters stay quarantined within concurrency bound',async()=>{
  let finish;const gateway=createToolGateway({timeoutMs:15,maxConcurrent:1});gateway.registerTool({name:'slow'},()=>new Promise(resolve=>finish=resolve));
  await assert.rejects(gateway.callTool('slow'),/TOOL_TIMEOUT/);assert.equal(gateway.stats().active,1);await assert.rejects(gateway.callTool('slow'),/MCP_BUSY/);finish(result('late'));await new Promise(resolve=>setImmediate(resolve));assert.equal(gateway.stats().active,0);
});
test('in-flight cancellation propagates without recording private error messages',async()=>{
  const controller=new AbortController(),traces=[];let aborted=false;
  const gateway=createToolGateway({onTrace:t=>traces.push(t)});gateway.registerTool({name:'cancel'},(_,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{aborted=true;reject(new Error('PRIVATE secret'));},{once:true})));
  const work=gateway.callTool('cancel',{}, {signal:controller.signal});await new Promise(resolve=>setImmediate(resolve));controller.abort();await assert.rejects(work,/TOOL_ABORTED/);assert.equal(aborted,true);assert.ok(!JSON.stringify(traces).includes('PRIVATE'));
});
test('SDK adapter bounds discovery pages, repeated cursors, duplicate names and payloads',async()=>{
  const adapter=sdkAdapter({listTools:async()=>({tools:[{name:'one'}],nextCursor:'loop'})});await assert.rejects(adapter.listTools(),/MCP_DUPLICATE_TOOL/);
  let page=0;const loop=sdkAdapter({listTools:async()=>({tools:[{name:'t'+page++}],nextCursor:'same'})});await assert.rejects(loop.listTools(),/MCP_INVALID_PAGINATION/);
  const huge=sdkAdapter({listTools:async()=>({tools:[{name:'x',description:'x'.repeat(262144)}]})});await assert.rejects(huge.listTools(),/MCP_DISCOVERY_TOO_LARGE/);
});
test('limiter release is idempotent and records peak usage',()=>{const limiter=createLimiter(1),release=limiter.acquire();assert.throws(()=>limiter.acquire(),/MCP_BUSY/);release();release();assert.deepEqual(limiter.stats(),{active:0,peak:1,total:1,max:1});});
