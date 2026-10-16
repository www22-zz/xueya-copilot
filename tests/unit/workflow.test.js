const test=require('node:test');
const assert=require('node:assert/strict');
const L=require('../../shared/learning.js');
const {normalizeContext,CONTEXT_LIMITS}=require('../../shared/agent/context.js');

const {routeTask}=require('../../shared/agent/tasks.js');

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
