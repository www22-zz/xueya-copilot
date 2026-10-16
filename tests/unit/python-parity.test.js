/* Shared frozen cases bind Python server rules to the unchanged browser rules. */
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const L=require('../../shared/learning.js');
const read=relative=>JSON.parse(fs.readFileSync(path.resolve(__dirname,'../..',relative),'utf8'));

test('Python public course fixture matches the browser course exactly',()=>{
  const fixture=read('backend/xueya/data/course.json');
  assert.deepEqual(fixture.sources,L.sources);
  assert.deepEqual(fixture.questions,L.questions);
});

test('browser and Python share the same frozen memory, wrong-question and plan baseline',()=>{
  const expected=read('tests/fixtures/legacy-node-v3/expected.json');
  assert.deepEqual(L.wrongQuestions(expected.records),expected.wrong);
  assert.deepEqual(L.memoryCards(expected.records,expected.base),expected.memory);
  assert.deepEqual(L.buildPlan('2026-10-20',45,expected.records,expected.base),expected.plan);
});
