const test=require('node:test');
const assert=require('node:assert/strict');
const L=require('../../shared/learning.js');

test('uploaded text is retrieved with its own citation and unknown topics stay empty',()=>{
  const doc={id:'notes',name:'生物笔记.md'};
  const chunks=L.extractChunks('光合作用发生在叶绿体。光反应产生 ATP 和 NADPH，暗反应固定二氧化碳。',doc);
  const hits=L.retrieve('光合作用发生在哪里？',[...L.sources,...chunks]);
  assert.equal(hits[0].documentId,'notes');
  assert.equal(hits[0].location,'文本片段 1');
  assert.deepEqual(L.retrieve('法国首都在哪里？',L.sources),[]);
  assert.match(L.localAnswer('法国首都','ask',[]),/没有找到足够依据/);
});
test('long text keeps overlapping context and unique source identifiers',()=>{
  const chunks=L.extractChunks('a'.repeat(1300),{id:'long',name:'notes.txt'});
  assert.equal(chunks.length,3);
  assert.equal(new Set(chunks.map(c=>c.id)).size,3);
  assert.equal(chunks[0].quote.length,600);
  assert.equal(chunks[2].quote.length,260);
});
test('dates reject calendar rollovers and use date boundaries',()=>{
  assert.equal(L.validDate('2026-02-30'),false);
  assert.equal(L.validDate('2028-02-29'),true);
  assert.equal(L.daysUntil('2026-10-15','2026-10-14'),1);
  assert.equal(L.addDays('2026-12-31',1),'2027-01-01');
});
test('latest result resolves wrong questions and drives plan priorities',()=>{
  const wrong=[{questionId:'q3',correct:false}];
  assert.equal(L.wrongQuestions(wrong)[0].id,'q3');
  const plan=L.buildPlan('2026-10-16',30,wrong,'2026-10-14');
  assert.equal(plan.length,3);
  assert.match(plan[0].tasks[0].title,/薄弱点.*中序遍历/);
  assert.equal(plan[0].tasks.reduce((n,t)=>n+t.minutes,0),30);
  assert.deepEqual(L.wrongQuestions([...wrong,{questionId:'q3',correct:true}]),[]);
  assert.deepEqual(L.buildPlan('2026-10-13',30,[],'2026-10-14'),[]);
  assert.equal(L.buildPlan('2026-10-14',15,[],'2026-10-14').length,1);
});
