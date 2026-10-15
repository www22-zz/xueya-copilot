const test=require('node:test');
const assert=require('node:assert/strict');
const http=require('node:http');
const path=require('node:path');
const {createApp}=require('../../backend/app.js');
const L=require('../../shared/learning.js');

test('Agent HTTP uses real MCP retrieval, validates citations, and emits workflow stages',async()=>{
  let observed;
  const model={generate:async({messages})=>{
    observed=JSON.parse(messages.at(-1).content);
    return{model:'controlled',content:JSON.stringify({answer:'查找复杂度为 O(h)。',sources:['source-1','forged']})};
  }};
  const server=http.createServer(createApp({config:{root:path.resolve(__dirname,'../..'),ai:{apiKey:'',model:'test'}},model}));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  const request={question:'二叉搜索树的查找复杂度？',sources:['source-1']};
  try{
    const result=await (await fetch(base+'/api/agent',{method:'POST',body:JSON.stringify(request)})).json();
    assert.equal(result.ok,true);
    assert.deepEqual(result.sources,['source-1']);
    assert.match(observed.materials[0].quote,/O\(h\)/);
    assert.ok(result.workflow.steps.some(step=>step.stage==='read'&&step.status==='completed'));
    const response=await fetch(base+'/api/agent/stream',{method:'POST',body:JSON.stringify(request)});
    const events=(await response.text()).split('\n\n').filter(line=>line.startsWith('data: ')).map(line=>JSON.parse(line.slice(6)));
    assert.ok(events.some(event=>event.type==='workflow'&&event.stage==='retrieve'));
    assert.equal(events.at(-1).type,'done');
    assert.deepEqual(events.at(-1).sources,['source-1']);
    assert.equal((await fetch(base+'/api/agent',{method:'POST',body:'{'})).status,400);
    assert.equal((await fetch(base+'/backend/mcp/course-server.js')).status,404);
  }finally{await new Promise(resolve=>server.close(resolve));}
});

test('Agent produces a genuine local plan preview through MCP without an AI key',async()=>{
  const config={root:path.resolve(__dirname,'../..'),ai:{apiKey:'',model:'test'}};
  const server=http.createServer(createApp({config,model:{generate:async()=>assert.fail('Plan arithmetic should not need a model')}}));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try{
    const request={question:'帮我安排一份复习计划',sources:[],context:{examDate:L.addDays(L.today(),4),minutes:45,records:[{questionId:'q3',correct:false,createdAt:new Date().toISOString()}]}};
    const result=await (await fetch(`http://127.0.0.1:${server.address().port}/api/agent`,{method:'POST',body:JSON.stringify(request)})).json();
    assert.equal(result.ok,true);
    assert.equal(result.engine,'local-workflow');
    assert.equal(result.workflow.intent,'plan');
    assert.equal(result.artifacts.progress.total,1);
    assert.match(result.artifacts.plan.days[0].tasks[0].title,/薄弱点.*中序遍历/);
    assert.match(result.answer,/预览/);
    assert.match(result.answer,/尚未修改/);
  }finally{await new Promise(resolve=>server.close(resolve));}
});
