const test=require('node:test');
const assert=require('node:assert/strict');
const {createChatService}=require('../../frontend/js/services/chat-service.js');
const L=require('../../shared/learning.js');

function body(text,step=1){
  const bytes=new TextEncoder().encode(text);
  return new ReadableStream({start(controller){for(let i=0;i<bytes.length;i+=step)controller.enqueue(bytes.slice(i,i+step));controller.close();}});
}
const event=value=>'data: '+JSON.stringify(value)+'\n\n';
const serviceFor=stream=>createChatService({fetchImpl:async()=>new Response(body(stream),{headers:{'Content-Type':'text/event-stream'}})});

test('draft events stream an unverified preview and the final done.answer overrides it',async()=>{
  const updates=[];
  const doneAnswer='队列是一种先进先出（FIFO）的线性表。';
  const stream=event({type:'workflow',stage:'generate',status:'running',label:'正在生成回答',model:'controlled'})
    +event({type:'draft',text:'队列是一种',draft:true,model:'controlled'})
    +event({type:'draft',text:'先进先出的线性表。',draft:true,model:'controlled'})
    +event({type:'done',ok:true,engine:'xiaomi-mimo',answer:doneAnswer,sources:[],knowledgePoints:[],model:'controlled'});
  const result=await serviceFor(stream).stream({question:'解释队列。',sources:[]},{onUpdate:update=>updates.push(update)});
  const drafts=updates.filter(update=>update.draft===true);
  assert.deepEqual(drafts.map(update=>update.answer),['队列是一种','队列是一种先进先出的线性表。']);
  assert.ok(drafts.every(update=>typeof update.progress==='string'));
  const finalUpdate=updates.at(-1);
  assert.equal(finalUpdate.draft,false);
  assert.equal(finalUpdate.answer,doneAnswer);
  assert.equal(updates.some(update=>update.draft===true&&update.answer===doneAnswer),false);
  assert.equal(result.answer,doneAnswer);
  assert.equal(result.online,true);
  assert.ok(!('draft'in result)||result.draft===false);
});

test('draft text is never parsed as a JSON answer',async()=>{
  const updates=[];
  const doneAnswer='真实最终回答。';
  const stream=event({type:'draft',text:'{"answer":"伪造的草稿答案"}',draft:true})
    +event({type:'done',ok:true,engine:'xiaomi-mimo',answer:doneAnswer,sources:[]});
  const result=await serviceFor(stream).stream({question:'解释队列。',sources:[]},{onUpdate:update=>updates.push(update)});
  assert.equal(updates.find(update=>update.draft===true).answer,'{"answer":"伪造的草稿答案"}');
  assert.equal(result.answer,doneAnswer);
  assert.equal(updates.at(-1).answer,doneAnswer);
  assert.equal(updates.at(-1).draft,false);
});

test('workflow resetAnswer discards the in-flight draft before a fresh stream',async()=>{
  const updates=[];
  const fallback={from:'course-rag',reason:'CLAIMS_NEED_REVIEW',attempts:1,sameRequestReplayed:false};
  const stream=event({type:'draft',text:'旧草稿片段',draft:true})
    +event({type:'workflow',stage:'general-fallback',status:'running',label:'切换模型自主回答',resetAnswer:true,fallback})
    +event({type:'draft',text:'新草稿片段',draft:true})
    +event({type:'done',ok:true,engine:'general-chat',answer:'模型自主回答：新的说明。',sources:[],
      verification:'general-knowledge-not-course-verified',fallback});
  const result=await serviceFor(stream).stream({question:'解释队列。',sources:[]},{workflow:true,onUpdate:update=>updates.push(update)});
  const resetIndex=updates.findIndex(update=>update.answer===''&&update.draft===false);
  assert.ok(resetIndex>0);
  const afterReset=updates.slice(resetIndex+1);
  assert.equal(afterReset.some(update=>update.answer?.includes('旧草稿片段')),false);
  assert.deepEqual(afterReset.filter(update=>update.draft===true).map(update=>update.answer),['新草稿片段']);
  assert.equal(result.answer,'模型自主回答：新的说明。');
  assert.equal(result.verification,'general-knowledge-not-course-verified');
});

test('resetAnswer followed by done without a new draft keeps only the done answer',async()=>{
  const updates=[];
  const stream=event({type:'draft',text:'旧草稿片段',draft:true})
    +event({type:'workflow',stage:'general-fallback',status:'running',label:'切换模型自主回答',resetAnswer:true})
    +event({type:'done',ok:true,engine:'general-chat',answer:'最终回答。',sources:[]});
  const result=await serviceFor(stream).stream({question:'解释队列。',sources:[]},{workflow:true,onUpdate:update=>updates.push(update)});
  const resetIndex=updates.findIndex(update=>update.answer===''&&update.draft===false);
  assert.ok(resetIndex>0);
  assert.equal(updates.slice(resetIndex+1).some(update=>update.answer!==undefined),false);
  assert.equal(result.answer,'最终回答。');
});

test('a stream that fails or ends after a draft discards the draft text and falls back locally',async()=>{
  const cases=[
    event({type:'draft',text:'未核对的草稿',draft:true})+event({type:'error',error:'AI_UNAVAILABLE'}),
    event({type:'draft',text:'未核对的草稿',draft:true})
  ];
  for(const stream of cases){
    const updates=[];
    const result=await serviceFor(stream).stream({question:'二叉搜索树的查找复杂度？',sources:L.sources},{onUpdate:update=>updates.push(update)});
    assert.equal(result.online,false);
    assert.equal(result.answer.includes('未核对的草稿'),false);
    assert.ok(result.sources.length);
    const cleared=updates.at(-1);
    assert.equal(cleared.answer,'');
    assert.equal(cleared.draft,false);
    assert.ok(updates.indexOf(cleared)>updates.findIndex(update=>update.draft===true));
  }
});

test('content-only streams keep the exact pre-draft onUpdate payloads',async()=>{
  const updates=[];
  const stream=event({type:'workflow',stage:'review',status:'running',label:'正在核对依据'})
    +event({type:'content',text:'{"answer":"查找需要'})
    +event({type:'content',text:' O(h)。","sources":["source-1"]}'})
    +event({type:'done',ok:true,engine:'xiaomi-mimo',answer:'查找需要 O(h)。',sources:['source-1'],knowledgePoints:[],model:'controlled'});
  const result=await serviceFor(stream).stream({question:'二叉搜索树的查找复杂度？',sources:L.sources},{onUpdate:update=>updates.push(update)});
  assert.equal(result.answer,'查找需要 O(h)。');
  assert.deepEqual(result.sources.map(source=>source.id),['source-1']);
  const answerUpdates=updates.filter(update=>'answer'in update);
  assert.deepEqual(answerUpdates.map(update=>update.answer),['查找需要','查找需要 O(h)。']);
  assert.deepEqual(answerUpdates.map(update=>Object.keys(update).sort()),[['answer','reasoning'],['answer','reasoning']]);
  assert.equal(updates.some(update=>'draft'in update),false);
  assert.equal(updates.filter(update=>update.answer==='').length,0);
});

test('a legacy resetAnswer without drafts emits the same payload as before',async()=>{
  const updates=[];
  const stream=event({type:'content',text:'{"answer":"旧片段'})
    +event({type:'workflow',stage:'review',status:'running',label:'正在核对依据',resetAnswer:true})
    +event({type:'done',ok:true,engine:'general-chat',answer:'最终回答。',sources:[]});
  const result=await serviceFor(stream).stream({question:'解释队列。',sources:[]},{workflow:true,onUpdate:update=>updates.push(update)});
  const reset=updates.find(update=>update.answer==='');
  assert.deepEqual(Object.keys(reset).sort(),['answer','reasoning']);
  assert.equal(updates.some(update=>'draft'in update),false);
  assert.equal(result.answer,'最终回答。');
});

test('draft reset clears the claim preview before the answer typewriter starts',async()=>{
  const updates=[];
  const stream=event({type:'draft',text:'先出现的 claims 摘录',draft:true})
    +event({type:'draft',text:'',draft:true,reset:true})
    +event({type:'draft',text:'真正的答案开头',draft:true})
    +event({type:'done',ok:true,engine:'xiaomi-mimo',answer:'真正的答案。',sources:[]});
  const result=await serviceFor(stream).stream({question:'解释队列。',sources:[]},{onUpdate:update=>updates.push(update)});
  const resetIndex=updates.findIndex(update=>update.answer===''&&update.draft===true);
  assert.ok(resetIndex>0);
  const after=updates.slice(resetIndex+1);
  assert.equal(after.some(update=>update.answer?.includes('claims 摘录')),false);
  assert.equal(after.find(update=>update.draft===true).answer,'真正的答案开头');
  assert.equal(result.answer,'真正的答案。');
});
