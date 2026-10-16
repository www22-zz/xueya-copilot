'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const {connectStdio,processStats}=require('../../backend/mcp/stdio-client.js');
const {createLimiter}=require('../../backend/mcp/policy.js');
const args=[path.resolve(__dirname,'../../backend/mcp/course-server.js')];
async function until(predicate){for(let i=0;i<100;i++){if(predicate())return;await new Promise(resolve=>setTimeout(resolve,10));}assert.fail('cleanup did not finish');}
test('crashed stdio process fails pending work and releases its owned permit',async()=>{
  const adapter=await connectStdio({command:process.execPath,args});const pid=adapter.pid;process.kill(pid,'SIGKILL');await until(()=>processStats().active===0);await assert.rejects(adapter.listTools());await adapter.close();assert.throws(()=>process.kill(pid,0));
});
test('stdio cancellation closes a live process; failure, limits and lifetime release permits',async()=>{
  const limiter=createLimiter(1),controller=new AbortController();
  const adapter=await connectStdio({command:process.execPath,args,signal:controller.signal,limiter});const pid=adapter.pid;
  await assert.rejects(connectStdio({command:process.execPath,args,limiter}),/MCP_BUSY/);
  controller.abort();await until(()=>limiter.stats().active===0);assert.throws(()=>process.kill(pid,0));await adapter.close();
  await assert.rejects(connectStdio({command:'xueya-missing-command',limiter,timeoutMs:100}));assert.equal(limiter.stats().active,0);
  const short=await connectStdio({command:process.execPath,args,limiter,lifetimeMs:25});await until(()=>limiter.stats().active===0);assert.throws(()=>process.kill(short.pid,0));await short.close();
});
