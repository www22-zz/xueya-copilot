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
test('memory cards remind sooner after mistakes and reset after a correct answer',()=>{
  const wrongs=[{questionId:'q1',correct:false,createdAt:'2026-10-10T02:00:00Z'},{questionId:'q1',correct:false,createdAt:'2026-10-11T02:00:00Z'}];
  const repeated=L.memoryCards(wrongs,'2026-10-14').find(c=>c.topic==='树的高度');
  assert.equal(repeated.wrongCount,2);
  assert.equal(repeated.nextReview,'2026-10-13');
  assert.equal(repeated.due,true);
  const cleared=L.memoryCards([...wrongs,{questionId:'q1',correct:true,createdAt:'2026-10-14T02:00:00Z'}],'2026-10-14').find(c=>c.topic==='树的高度');
  assert.equal(cleared.wrongCount,0);
  assert.equal(cleared.nextReview,'2026-10-21');
  assert.equal(cleared.due,false);
  assert.equal(L.memoryCards([],'2026-10-14').every(c=>c.due===false&&c.lastReviewed===null),true);
});

test('generated questions join wrong-question review, memory scheduling and plan priorities',()=>{
  const bank={id:'bank-test',topic:'拓扑排序',sourceId:'upload-notes-chunk-0'};
  const pool=[...L.questions,bank];
  const records=[{questionId:bank.id,correct:false,createdAt:'2026-10-14T02:00:00Z'}];
  assert.equal(L.wrongQuestions(records,pool).at(-1).id,bank.id);
  const card=L.memoryCards(records,'2026-10-15',pool).find(item=>item.topic===bank.topic);
  assert.equal(card.wrongCount,1);
  assert.equal(card.nextReview,'2026-10-17');
  assert.match(L.buildPlan('2026-10-20',30,records,'2026-10-15',pool)[0].tasks[0].title,/薄弱点.*拓扑排序/);
  assert.equal(L.wrongQuestions([...records,{questionId:bank.id,correct:true}],pool).length,0);
});
