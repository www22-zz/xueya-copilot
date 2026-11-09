const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function service(){const window={};vm.runInNewContext(fs.readFileSync('frontend/js/study-quiz.js','utf8'),{window});return window.XueyaStudyQuiz;}
const attempt=(id,at,source='objective',result={correct:false},status='graded')=>({id:id+'-'+at,questionId:id,createdAt:at,effectiveEvaluation:{source,status,result}});
test('wrong questions follow their actual material, algorithm and exam references',()=>{
  const questions=[{id:'m',sourceType:'ai-material'},{id:'h',originalQuestionId:'hot'},{id:'e',originalQuestionId:'exam'},{id:'chat',sourceType:'ai-generated'},{id:'historical',originalQuestionId:'old-hot'}];
  const bank=[{id:'hot',bankSource:'algorithm'},{id:'exam',bankSource:'exam408'},{id:'old-hot',bankSource:'legacy',category:'hot100'}];
  const rows=service().reviewRows({questions,attempts:questions.map(q=>attempt(q.id,'2026-11-05'))},bank);
  assert.deepEqual(Array.from(rows,r=>r.area),['materials','algorithms','exams','unclassified','materials']);
});
test('latest corrected, disputed or pending attempts never resurrect an older wrong answer',()=>{
  const ids=['corrected','disputed','pending','content','reference','manual'];
  const questions=ids.map(id=>({id,sourceType:'ai-material'}));
  const attempts=[...ids.map(id=>attempt(id,'2026-11-01')),
    attempt('corrected','2026-11-05','human',{correct:true}),
    attempt('disputed','2026-11-05','human',{},'disputed'),
    attempt('pending','2026-11-05','objective',{},'pending-review'),
    attempt('content','2026-11-05','ai-reference',{feedback:'Only comments'}),
    attempt('reference','2026-11-05','ai-review',{score:2,maxScore:5}),
    attempt('manual','2026-11-05','human',{correct:false})];
  const rows=service().reviewRows({questions,attempts});
  assert.deepEqual(Array.from(rows,r=>r.question.id),['reference','manual']);
  assert.equal(rows[0].objective,false);assert.equal(rows[1].objective,true);
});
