/* Compatibility facade: keep existing browser and Node learning APIs. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('./fixtures/course.js'),require('./rag/index.js'),require('./agent/local-answer.js'));else root.XueyaLearning=factory(root.XueyaCourse,root.XueyaRag,root.XueyaLocalAnswer);})(typeof globalThis!=='undefined'?globalThis:this,function(course,rag,answers){
'use strict';
const {documents,sources,questions}=course;
  function today(){const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));return `${p.year}-${p.month}-${p.day}`;}
  function validDate(value){if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;const d=new Date(value+'T00:00:00Z');return Number.isFinite(+d)&&d.toISOString().slice(0,10)===value;}
  function addDays(value,n){return new Date(Date.parse(value+'T00:00:00Z')+n*86400000).toISOString().slice(0,10);}
  function daysUntil(date,base=today()){return validDate(date)?Math.round((Date.parse(date+'T00:00:00Z')-Date.parse(base+'T00:00:00Z'))/86400000):null;}
  function wrongQuestions(records){return questions.filter(q=>{const last=[...records].reverse().find(r=>r.questionId===q.id);return last&&!last.correct;});}
  function buildPlan(examDate,minutes,records,base=today()){const remaining=daysUntil(examDate,base);if(remaining===null||remaining<0)return[];const count=Math.min(7,remaining+1);const weak=wrongQuestions(records).map(q=>q.topic);const topics=[...new Set([...weak,...questions.map(q=>q.topic)])];const daily=Math.max(15,Math.min(120,Number(minutes)||30));const output=[];for(let day=0;day<count;day++){const date=addDays(base,day);const topic=topics[day%topics.length];const first=Math.ceil(daily*.6),second=daily-first;output.push({date,tasks:[{id:`${date}-${topic}-read`,title:`${weak.includes(topic)?'回顾薄弱点':'理解'}：${topic}`,detail:'阅读课程原文，保存一张重点卡片',minutes:first},{id:`${date}-${topic}-practice`,title:`练习与复述：${topic}`,detail:'完成示例练习，用自己的话解释答案',minutes:second}]});}return output;}

return{documents,sources,questions,today,validDate,addDays,daysUntil,...rag,...answers,wrongQuestions,buildPlan};
});
