/* Portable module: browser script and CommonJS. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaLocalAnswer=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';

  function localAnswer(question,mode,hits){
    if(!hits.length)return '当前资料中没有找到足够依据。请补充具体的课程关键词，或者上传相关 TXT / MD 资料后再试。';
    if(mode==='quiz'){
      return `可以先用这个问题检验理解：\n${question}\n\n请结合下列原文，写出定义、适用条件和边界情况：\n${hits.map((s,i)=>`[${i+1}] ${s.quote}`).join('\n\n')}\n\n需要选择题和判题反馈，可以进入“练习与错题”的示例题库。`;
    }
    if(mode==='summarize'){
      return `知识卡片：${question}\n\n${hits.map((s,i)=>`重点 ${i+1}｜${s.quote}`).join('\n\n')}\n\n复习时，先遮住答案，用自己的话复述这些重点。`;
    }
    return `根据当前资料，可以从以下原文理解这个问题：\n\n${hits.map((s,i)=>`[${i+1}] ${s.quote}`).join('\n\n')}\n\n以上是本地检索摘录。点击引用可核对原文。`;
  }

return {localAnswer};
});
