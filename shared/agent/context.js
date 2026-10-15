/* Bounded per-request learning context, shared by the browser and Agent. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('../learning.js'));else root.XueyaContext=factory(root.XueyaLearning);})(typeof globalThis!=='undefined'?globalThis:this,function(L){
  'use strict';
  const CONTEXT_LIMITS=Object.freeze({sources:48,quote:1500,questions:100,records:120});

  function normalizeContext(input={}){
    if(!input||typeof input!=='object')input={};
    const library=[],ids=new Set();
    for(const item of (Array.isArray(input.library)?input.library:[])){
      if(library.length>=CONTEXT_LIMITS.sources)break;
      const source=typeof item==='string'?L.sources.find(source=>source.id===item):item;
      if(!source||typeof source.id!=='string'||typeof source.quote!=='string'||!source.quote.trim())continue;
      const id=source.id.slice(0,150);
      if(!id||ids.has(id))continue;
      ids.add(id);
      library.push({id,title:String(source.title||'课程资料').slice(0,200),location:String(source.location||'文本片段').slice(0,150),quote:source.quote.slice(0,CONTEXT_LIMITS.quote),keywords:Array.isArray(source.keywords)?source.keywords.filter(value=>typeof value==='string').slice(0,12).map(value=>value.slice(0,30)):[],sample:source.sample===true});
    }
    const questions=[],questionIds=new Set();
    for(const question of (Array.isArray(input.questions)?input.questions:L.questions).slice(0,CONTEXT_LIMITS.questions)){
      if(!question||typeof question.id!=='string'||typeof question.topic!=='string')continue;
      const id=question.id.slice(0,150);
      if(questionIds.has(id))continue;
      questionIds.add(id);
      questions.push({id,topic:question.topic.slice(0,80),sourceId:String(question.sourceId||'').slice(0,150)});
    }
    const records=(Array.isArray(input.records)?input.records:[]).slice(-CONTEXT_LIMITS.records)
      .filter(record=>record&&questionIds.has(record.questionId)&&typeof record.correct==='boolean')
      .map(record=>({questionId:record.questionId,correct:record.correct,...(typeof record.createdAt==='string'&&Number.isFinite(Date.parse(record.createdAt))?{createdAt:record.createdAt.slice(0,60)}:{})}));
    const baseDate=L.today();
    const examDate=L.validDate(input.examDate)?input.examDate:L.addDays(baseDate,21);
    const minutes=Math.max(15,Math.min(120,Math.round(Number(input.minutes)||30)));
    return{library,questions,records,baseDate,examDate,minutes};
  }

  return{CONTEXT_LIMITS,normalizeContext};
});
