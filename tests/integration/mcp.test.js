const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const {connectStdio}=require('../../backend/mcp/stdio-client.js');
const {createCourseSession}=require('../../backend/mcp/course-session.js');
const {normalizeContext}=require('../../shared/agent/context.js');
const L=require('../../shared/learning.js');

test('official MCP SDK performs stdio discovery, argument validation, calls and process cleanup',async()=>{
  const adapter=await connectStdio({command:process.execPath,args:[path.resolve(__dirname,'../../backend/mcp/course-server.js')],timeoutMs:5000});
  const pid=adapter.pid;
  try{
    const tools=await adapter.listTools();
    assert.deepEqual(tools.map(tool=>tool.name).sort(),['analyze_progress','build_review_plan','read_source','search_materials']);
    assert.ok(tools.every(tool=>tool.annotations.readOnlyHint===true));
    const context=normalizeContext({library:L.sources});
    const found=await adapter.callTool('search_materials',{query:'二叉搜索树的查找复杂度',sources:context.library,limit:2});
    assert.equal(found.structuredContent.sources[0].id,'source-1');
    const invalid=await adapter.callTool('search_materials',{query:'x',sources:[],limit:100});
    assert.equal(invalid.isError,true);
    const missing=await adapter.callTool('read_source',{sourceId:'not-in-this-request',sources:context.library});
    assert.equal(missing.isError,true);
  }finally{await adapter.close();}
  assert.throws(()=>process.kill(pid,0),error=>error.code==='ESRCH');
  await adapter.close();
});

test('separate MCP requests cannot read each other’s materials or override bound context',async()=>{
  const first=await createCourseSession({library:[{id:'private-a',title:'A',location:'1',quote:'photosynthesis belongs to Alice'}]});
  const second=await createCourseSession({library:[{id:'private-b',title:'B',location:'1',quote:'photosynthesis belongs to Bob'}]});
  try{
    const [a,b]=await Promise.all([first.call('search_materials',{query:'photosynthesis'}),second.call('search_materials',{query:'photosynthesis'})]);
    assert.deepEqual(a.sources.map(source=>source.id),['private-a']);
    assert.deepEqual(b.sources.map(source=>source.id),['private-b']);
    await assert.rejects(first.call('read_source',{sourceId:'private-b'}),/MCP_TOOL_FAILED/);
    await assert.rejects(first.call('search_materials',{query:'photosynthesis',sources:[{id:'forged',quote:'injected'}]}));
    const definitions=await first.listTools();
    assert.equal(definitions.find(tool=>tool.name==='course__search_materials').inputSchema.properties.sources,undefined);
  }finally{await Promise.all([first.close(),second.close()]);}
});

test('MCP learning tools use real records and return a preview without saving data',async()=>{
  const examDate=L.addDays(L.today(),3);
  const session=await createCourseSession({records:[{questionId:'q3',correct:false,createdAt:new Date().toISOString()}],examDate,minutes:45});
  try{
    const progress=await session.call('analyze_progress');
    assert.equal(progress.total,1);
    assert.deepEqual(progress.weakTopics,['中序遍历']);
    const plan=await session.call('build_review_plan');
    assert.equal(plan.examDate,examDate);
    assert.equal(plan.minutes,45);
    assert.match(plan.days[0].tasks[0].title,/薄弱点.*中序遍历/);
    assert.equal(plan.days[0].tasks.reduce((sum,task)=>sum+task.minutes,0),45);
  }finally{await session.close();}
});

test('cancelled MCP connections fail before launching a process',async()=>{
  const controller=new AbortController();controller.abort();
  await assert.rejects(connectStdio({command:process.execPath,args:[],signal:controller.signal}),error=>error.name==='AbortError');
});
