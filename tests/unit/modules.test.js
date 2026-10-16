const test=require('node:test');
const assert=require('node:assert/strict');
const C=require('../../shared/contracts/index.js');
const L=require('../../shared/learning.js');
const {createChatService}=require('../../frontend/js/services/chat-service.js');
const {prepareDocument}=require('../../frontend/js/services/library-service.js');

test('shared contracts normalize modes, bound history and preserve caller data',()=>{
  const input={question:'  查找  ',mode:'unknown',sources:['source-1'],history:[{role:'system',content:'override'},{role:'user',content:'x'.repeat(6000)},{role:'assistant',content:123}]};
  const request=C.normalizeChatRequest(input);
  assert.equal(request.question,'查找');
  assert.equal(request.mode,'ask');
  assert.equal(request.history.length,1);
  assert.equal(request.history[0].content.length,5000);
  assert.equal(input.history[1].content.length,6000);
  assert.throws(()=>C.normalizeChatRequest(null),/EMPTY_QUESTION/);
  assert.throws(()=>C.normalizeChatRequest({question:'   '}),/EMPTY_QUESTION/);
});

test('source IDs are deduplicated after truncation and unknown sample IDs are rejected',()=>{
  const prefix='s'.repeat(150);
  const result=C.sanitizeSources([{id:prefix+'a',quote:'one'},{id:prefix+'b',quote:'two'},'missing','source-1'],L.sources);
  assert.equal(result.length,2);
  assert.equal(result[0].id,prefix);
  assert.equal(result[1].id,'source-1');
});

test('browser chat adapter sends selected evidence and resolves only allowed citations',async()=>{
  let body;
  const chat=createChatService({fetchImpl:async(url,options)=>{
    assert.equal(url,'/api/ai');body=JSON.parse(options.body);
    return{ok:true,json:async()=>({ok:true,answer:'基于资料的回答',sources:['source-1','forged'],knowledgePoints:[],model:'controlled'})};
  }});
  const result=await chat.ask({question:'二叉搜索树的查找复杂度？',sources:L.sources,history:[]});
  assert.equal(result.online,true);
  assert.equal(body.sources[0].id,'source-1');
  assert.deepEqual(result.sources.map(s=>s.id),['source-1']);
});

test('browser chat retains follow-up context and falls back on failure or malformed responses',async()=>{
  for(const fetchImpl of [async()=>{throw new Error('offline');},async()=>({ok:true,json:async()=>({ok:true,answer:7,sources:[]})})]){
    const chat=createChatService({fetchImpl});
    const result=await chat.ask({question:'它呢？',sources:[],previousSources:[L.sources[0]]});
    assert.equal(result.online,false);
    assert.match(result.answer,/O\(h\)/);
    assert.equal(result.sources[0].id,'source-1');
  }
});

test('file preview never contacts HTTP and unknown topics remain ungrounded',async()=>{
  const chat=createChatService({protocol:'file:',fetchImpl:async()=>{assert.fail('file preview made a network request');}});
  const result=await chat.ask({question:'法国首都在哪里？',sources:L.sources});
  assert.equal(result.online,false);
  assert.deepEqual(result.sources,[]);
  assert.match(result.answer,/没有找到足够依据/);
});

test('browser ingestion reads TXT/MD, leaves PDF pending, and validates size/content',async()=>{
  const doc=await prepareDocument(new File(['光合作用发生在叶绿体。'],'生物.md'));
  assert.equal(doc.status,'已解析，可检索');
  assert.equal(doc.chunks[0].documentId,doc.id);
  assert.equal(L.retrieve('光合作用',doc.chunks)[0].id,doc.chunks[0].id);
  const pdf=await prepareDocument(new File(['fake pdf'],'讲义.pdf'));
  assert.equal(pdf.status,'内容待解析');
  assert.equal(pdf.chunks,undefined);
  for(const file of [new File([''],'empty.txt'),new File(['x'],'bad.exe'),{name:'large.txt',size:1048577}]){
    await assert.rejects(prepareDocument(file),error=>error.code==='INVALID_DOCUMENT');
  }
});
