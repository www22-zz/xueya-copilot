const test=require('node:test');
const assert=require('node:assert/strict');
const L=require('../../shared/learning.js');
const {normalizeContext,CONTEXT_LIMITS}=require('../../shared/agent/context.js');
const {createLearningWorkflow,routeTask}=require('../../backend/agent/learning-workflow.js');

function mockSession(){
  let closed=0;
  const calls=[];
  return{calls,get closed(){return closed;},open:async context=>({
    listTools:async()=>[{name:'course__search_materials'}],
    call:async(name,args)=>{
      calls.push({name,args});
      if(name==='search_materials')return{sources:L.retrieve(args.query,context.library)};
      if(name==='read_source')return{source:context.library.find(source=>source.id===args.sourceId)};
      throw new Error('UNEXPECTED_TOOL');
    },
    close:async()=>{closed++;}
  })};
}

test('workflow routes learning tasks and honors explicit summary/quiz modes',()=>{
  assert.equal(routeTask('请安排未来一周的复习'),'plan');
  assert.equal(routeTask('我有哪些薄弱知识点'),'review');
  assert.equal(routeTask('总结二叉树知识'),'summarize');
  assert.equal(routeTask('出一道练习题'),'quiz');
  assert.equal(routeTask('复习计划','summarize'),'summarize');
  assert.equal(routeTask('二叉搜索树怎么查找'),'ask');
});

test('workflow context bounds data, ignores unknown records and never accepts an injected server date',()=>{
  const context=normalizeContext({library:Array.from({length:60},(_,i)=>({id:String(i),quote:'x'.repeat(5000)})),questions:[{id:'one',topic:'树'}],records:[{questionId:'unknown',correct:false},{questionId:'one',correct:true}],baseDate:'1900-01-01',minutes:999,examDate:'2026-02-30'});
  assert.equal(context.library.length,CONTEXT_LIMITS.sources);
  assert.equal(context.library[0].quote.length,CONTEXT_LIMITS.quote);
  assert.equal(context.records.length,1);
  assert.equal(context.baseDate,L.today());
  assert.equal(context.minutes,120);
  assert.ok(L.validDate(context.examDate));
});

test('Agent searches then reads actual passages before generation and returns a visible trace',async()=>{
  const session=mockSession();let observed;
  const workflow=createLearningWorkflow({openSession:session.open,model:{generate:async({messages})=>{
    observed=JSON.parse(messages.at(-1).content);
    assert.equal(session.closed,1,'MCP process should close before model generation');
    return{model:'controlled',content:JSON.stringify({answer:'查找复杂度取决于树高。',sources:['source-1','forged']})};
  }}});
  const result=await workflow.run({question:'二叉搜索树的查找复杂度？',sources:L.sources});
  assert.equal(session.calls[0].name,'search_materials');
  assert.ok(session.calls.slice(1).every(call=>call.name==='read_source'));
  assert.ok(observed.materials.every(source=>session.calls.some(call=>call.args?.sourceId===source.id)));
  assert.deepEqual(result.sources,['source-1']);
  assert.ok(result.workflow.steps.some(step=>step.stage==='validate'&&step.status==='completed'));
});

test('empty retrieval ends clearly without asking a model to fabricate evidence',async()=>{
  const session=mockSession();let modelCalls=0;
  const workflow=createLearningWorkflow({openSession:session.open,model:{generate:async()=>{modelCalls++;}}});
  const result=await workflow.run({question:'法国首都在哪里？',sources:L.sources});
  assert.equal(modelCalls,0);
  assert.equal(session.closed,1);
  assert.deepEqual(result.sources,[]);
  assert.match(result.answer,/没有找到足够依据/);
});

test('tool failure falls back honestly; model timeout and forged-only citations use actual excerpts',async()=>{
  const failing=createLearningWorkflow({openSession:async()=>{throw new Error('TOOL_TIMEOUT');},model:{generate:async()=>{throw new Error('offline');}}});
  const result=await failing.run({question:'二叉搜索树的查找复杂度？',sources:L.sources});
  assert.equal(result.engine,'local-workflow');
  assert.match(result.answer,/本地检索摘录/);
  assert.ok(result.workflow.steps.some(step=>step.stage==='tools'&&step.status==='degraded'));
  for(const generate of [async()=>{const error=new Error('timeout');error.name='AbortError';throw error;},async()=>({content:JSON.stringify({answer:'不可靠答案',sources:['forged']})})]){
    const session=mockSession();
    const workflow=createLearningWorkflow({openSession:session.open,model:{generate}});
    const fallback=await workflow.run({question:'二叉搜索树的查找复杂度？',sources:L.sources});
    assert.equal(fallback.engine,'local-workflow');
    assert.equal(fallback.answer.includes('不可靠答案'),false);
  }
});

test('workflow rejects cancelled requests without calling tools',async()=>{
  const controller=new AbortController();controller.abort();
  const workflow=createLearningWorkflow({openSession:async()=>assert.fail('called a tool after cancellation'),model:{}});
  await assert.rejects(workflow.run({question:'问题',sources:L.sources},{signal:controller.signal}),error=>error.name==='AbortError');
});

test('expired exam settings are preserved for explicit feedback instead of silently replacing the date',()=>{
  const examDate=L.addDays(L.today(),-1);
  assert.equal(normalizeContext({examDate}).examDate,examDate);
});

test('summary and quiz routes keep their own task instructions and grounded sources',async()=>{
  for(const [mode,pattern] of [['summarize',/知识卡片/],['quiz',/开放练习/]]){
    const session=mockSession();
    const workflow=createLearningWorkflow({openSession:session.open,model:{generate:async({messages})=>{
      assert.match(JSON.parse(messages.at(-1).content).task,pattern);
      return{model:'controlled',content:JSON.stringify({answer:'根据原文整理的学习内容。',sources:['source-1']})};
    }}});
    const result=await workflow.run({question:'二叉搜索树的查找复杂度',mode,sources:L.sources});
    assert.equal(result.workflow.intent,mode);
    assert.deepEqual(result.sources,['source-1']);
  }
});

test('generic follow-ups keep actual previous sources through MCP retrieval and repeated follow-ups',async()=>{
  const session=mockSession();let modelCalls=0;
  const workflow=createLearningWorkflow({openSession:session.open,model:{generate:async({messages})=>{
    modelCalls++;
    const input=JSON.parse(messages.at(-1).content);
    assert.equal(input.question,'请进一步解释这个问题，并给出资料中的依据。');
    assert.ok(input.materials.some(source=>source.id==='source-1'));
    return{model:'controlled',content:JSON.stringify({answer:'树的高度决定查找的路径长度。',sources:['source-1']})};
  }}});
  const result=await workflow.run({question:'请进一步解释这个问题，并给出资料中的依据。',sources:L.sources,history:[{role:'user',content:'二叉搜索树的查找复杂度？'},{role:'assistant',content:'This answer is context, not a source.'},{role:'user',content:'再解释一下'}],context:{library:L.sources,previousSourceIds:['source-1','forged']}});
  assert.equal(modelCalls,1);
  assert.equal(result.engine,'xiaomi-mimo');
  assert.deepEqual(result.sources,['source-1']);
  assert.match(session.calls[0].args.query,/二叉搜索树/);
});

test('follow-up can use known prior source IDs without history but never cites a missing source',async()=>{
  for(const previousSourceIds of [['source-1'],['deleted-source']]){
    const session=mockSession();let modelCalls=0;
    const workflow=createLearningWorkflow({openSession:session.open,model:{generate:async()=>{
      modelCalls++;return{content:JSON.stringify({answer:'依据当前原文解释。',sources:['source-1']})};
    }}});
    const result=await workflow.run({question:'再解释一下',context:{library:L.sources,previousSourceIds}});
    assert.equal(modelCalls,previousSourceIds[0]==='source-1'?1:0);
    assert.deepEqual(result.sources,previousSourceIds[0]==='source-1'?['source-1']:[]);
  }
});
