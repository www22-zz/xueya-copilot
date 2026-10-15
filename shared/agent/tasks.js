/* Shared task rules: online and offline learning use the same calculations. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('../learning.js'));else root.XueyaTasks=factory(root.XueyaLearning);})(typeof globalThis!=='undefined'?globalThis:this,function(L){
  'use strict';

  function routeTask(question,mode='ask'){
    if(mode==='summarize'||mode==='quiz')return mode;
    if(/(?:复习|学习|备考).{0,10}(?:计划|安排)|(?:计划|安排).{0,10}(?:复习|学习|备考)/.test(question))return'plan';
    if(/薄弱|弱项|掌握情况|错题分析|学习情况|学习进度|复习重点/.test(question))return'review';
    if(/总结|归纳|整理.{0,6}(?:重点|知识)/.test(question))return'summarize';
    if(/(?:出|生成).{0,4}(?:练习|题目|题)|练习题|测验/.test(question))return'quiz';
    return'ask';
  }

  function refersToPrevious(question){
    return /它|这个|这些|这种|这样|那个|那些|上述|刚才|上面|前面|继续|进一步|再解释|再说|展开讲|换个说法|举个例|举一个例|^(?:为什么|为何|怎么理解)[呢吗？?。！!\s]*$/.test(question);
  }

  function retrievalQuery({question,history=[]},library){
    if(!refersToPrevious(question)||L.retrieve(question,library).length)return question;
    const anchor=[...history].reverse().find(message=>message.role==='user'&&L.retrieve(message.content,library).length);
    return anchor?`${anchor.content.slice(0,3000)}\n追问：${question}`.slice(0,4000):question;
  }

  // Context is normalized at the browser/server boundary before reaching here.
  function localStudy(context,intent){
    const weak=L.wrongQuestions(context.records,context.questions);
    const progress={total:context.records.length,correct:context.records.filter(record=>record.correct).length,weakTopics:[...new Set(weak.map(question=>question.topic))],dueTopics:L.memoryCards(context.records,context.baseDate,context.questions).filter(card=>card.due).map(card=>card.topic)};
    const plan=intent==='plan'?{examDate:context.examDate,minutes:context.minutes,days:context.questions.length?L.buildPlan(context.examDate,context.minutes,context.records,context.baseDate,context.questions):[]}:undefined;
    return{progress,plan};
  }

  function studyText(intent,progress,plan,baseDate=L.today()){
    const summary=progress.total
      ?`最近 ${progress.total} 次作答中，答对 ${progress.correct} 次。\n当前待巩固：${progress.weakTopics.join('、')||'暂无未解决的错题'}。\n今日到期复习：${progress.dueTopics.join('、')||'暂无'}。`
      :'目前还没有可分析的作答记录。先完成一组练习，就能根据结果识别薄弱点。';
    if(intent!=='plan')return summary;
    if(plan&&plan.examDate<baseDate)return summary+'\n\n考试日期已经过去，请先在复习计划中更新考试日期。当前计划未作修改。';
    if(!plan?.days?.length)return summary+'\n\n暂时没有可安排的任务，请先完成练习或检查考试日期。';
    return`复习计划预览（每天 ${plan.minutes} 分钟，考试日期 ${plan.examDate}）：\n\n`
      +plan.days.map(day=>`${day.date}\n${day.tasks.map(task=>`· ${task.title}（${task.minutes} 分钟）`).join('\n')}`).join('\n\n')
      +'\n\n'+summary+'\n\n这是一份预览，尚未修改你已有的复习计划。';
  }

  return{routeTask,refersToPrevious,retrievalQuery,localStudy,studyText};
});
