'use strict';

const L=require('../../shared/learning.js');
const {normalizeChatRequest}=require('../../shared/contracts/index.js');
const {normalizeContext}=require('../../shared/agent/context.js');
const {createCourseSession}=require('../mcp/course-session.js');
const {buildMessages}=require('./prompts.js');
const {groundedAnswer}=require('./index.js');

function routeTask(question,mode='ask'){
  if(mode==='summarize'||mode==='quiz')return mode;
  if(/(?:复习|学习|备考).{0,10}(?:计划|安排)|(?:计划|安排).{0,10}(?:复习|学习|备考)/.test(question))return'plan';
  if(/薄弱|弱项|掌握情况|错题分析|学习情况|学习进度|复习重点/.test(question))return'review';
  if(/总结|归纳|整理.{0,6}(?:重点|知识)/.test(question))return'summarize';
  if(/(?:出|生成).{0,4}(?:练习|题目|题)|练习题|测验/.test(question))return'quiz';
  return'ask';
}

function localStudy(context,intent){
  const weak=L.wrongQuestions(context.records,context.questions);
  const progress={total:context.records.length,correct:context.records.filter(record=>record.correct).length,weakTopics:[...new Set(weak.map(question=>question.topic))],dueTopics:L.memoryCards(context.records,context.baseDate,context.questions).filter(card=>card.due).map(card=>card.topic)};
  const plan=intent==='plan'?{examDate:context.examDate,minutes:context.minutes,days:L.buildPlan(context.examDate,context.minutes,context.records,context.baseDate,context.questions)}:undefined;
  return{progress,plan};
}

function studyText(intent,progress,plan){
  const summary=progress.total
    ?`最近 ${progress.total} 次作答中，答对 ${progress.correct} 次。\n当前待巩固：${progress.weakTopics.join('、')||'暂无未解决的错题'}。\n今日到期复习：${progress.dueTopics.join('、')||'暂无'}。`
    :'目前还没有可分析的作答记录。先完成一组练习，就能根据结果识别薄弱点。';
  if(intent!=='plan')return summary;
  if(plan&&plan.examDate<L.today())return summary+'\n\n考试日期已经过去，请先在复习计划中更新考试日期。当前计划未作修改。';
  if(!plan?.days?.length)return summary+'\n\n暂时没有可安排的任务，请先完成练习或检查考试日期。';
  return`复习计划预览（每天 ${plan.minutes} 分钟，考试日期 ${plan.examDate}）：\n\n`
    +plan.days.map(day=>`${day.date}\n${day.tasks.map(task=>`· ${task.title}（${task.minutes} 分钟）`).join('\n')}`).join('\n\n')
    +'\n\n'+summary+'\n\n这是一份预览，尚未修改你已有的复习计划。';
}

function createLearningWorkflow({model,openSession=createCourseSession,toolTimeoutMs=5000}){
  async function* stream(input,{signal}={}){
    signal?.throwIfAborted();
    const request=normalizeChatRequest(input);
    const context=normalizeContext({...input.context,library:input.context?.library??request.sources});
    const intent=routeTask(request.question,request.mode);
    const study=intent==='plan'||intent==='review';
    const trace=[];
    const mark=(stage,label,status='running')=>{
      const event={stage,label,status};trace.push(event);return{type:'workflow',...event};
    };
    const finish=(answer,sources=[],extra={})=>({type:'done',ok:true,answer,sources:sources.map(source=>source.id),knowledgePoints:[],model:'local-learning-tools',engine:'local-workflow',workflow:{intent,steps:trace},...extra});
    yield mark('route',study?'正在整理你的学习情况':'正在确定这次学习任务','completed');
    if(!study&&!context.library.length){
      yield mark('evidence','当前没有可检索的课程原文','completed');
      yield finish(L.localAnswer(request.question,request.mode,[]));return;
    }
    let session,evidence=[],progress,plan;
    const actual=new Map(context.library.map(source=>[source.id,source]));
    try{
      yield mark('connect','正在连接课程学习工具');
      session=await openSession(context,{signal,timeoutMs:toolTimeoutMs});
      const definitions=await session.listTools();
      if(!definitions.length)throw new Error('MCP_TOOL_MISSING');
      yield mark('connect','课程学习工具已就绪','completed');
      if(study){
        yield mark('analyze','正在分析近期作答和薄弱知识点');
        progress=await session.call('analyze_progress');
        yield mark('analyze','已整理近期学习情况','completed');
        if(intent==='plan'){
          yield mark('plan','正在按考试日期和每日时长安排复习');
          plan=context.examDate<context.baseDate?{examDate:context.examDate,minutes:context.minutes,days:[]}:await session.call('build_review_plan');
          yield mark('plan',plan.days.length?'复习计划预览已生成':'考试日期已过或暂无任务，请检查学习设置','completed');
        }
      }else{
        yield mark('retrieve','正在检索课程资料');
        const found=await session.call('search_materials',{query:request.question,limit:4});
        const ids=[...new Set((Array.isArray(found.sources)?found.sources:[]).map(source=>source.id))].slice(0,3);
        if(ids.some(id=>!actual.has(id)))throw new Error('MCP_INVALID_RESULT');
        yield mark('retrieve',ids.length?`找到 ${ids.length} 个相关原文片段`:'当前资料中没有找到足够依据','completed');
        if(!ids.length){yield finish(L.localAnswer(request.question,request.mode,[]));return;}
        yield mark('read','正在核对引用原文');
        for(const sourceId of ids){
          signal?.throwIfAborted();
          const {source}=await session.call('read_source',{sourceId});
          const original=actual.get(sourceId);
          if(source?.id!==sourceId||source?.quote!==original.quote)throw new Error('MCP_INVALID_RESULT');
          evidence.push(original);
        }
        yield mark('read','原文和引用位置已核对','completed');
      }
    }catch(error){
      if(signal?.aborted)throw error;
      yield mark('tools','课程工具暂不可用，已切换本地学习规则','degraded');
      if(study)({progress,plan}=localStudy(context,intent));
      else evidence=L.retrieve(request.question,context.library).slice(0,3);
    }finally{
      await session?.close().catch(()=>{});
    }
    signal?.throwIfAborted();
    const local=()=>study?studyText(intent,progress,plan):L.localAnswer(request.question,intent,evidence);
    if(study){
      yield mark('validate','已核对作答统计和计划设置','completed');
      yield finish(local(),[],{artifacts:{progress,...(plan?{plan}:{})}});return;
    }
    if(!study&&!evidence.length){yield finish(local());return;}
    const messages=buildMessages({...request,mode:intent==='summarize'||intent==='quiz'?intent:'ask',sources:evidence});
    yield mark('generate','正在依据原文整理回答');
    try{
      let content='',modelName;
      if(typeof model.stream==='function'){
        for await(const event of model.stream({messages,signal})){
          if(event.type==='content'&&typeof event.text==='string'){
            content+=event.text;
            if(content.length>200000)throw new Error('AI_INVALID_RESPONSE');
          }
          modelName=event.model||modelName;
          if(['content','reasoning'].includes(event.type))yield event;
        }
      }else{
        const response=await model.generate({messages,signal});
        content=response.content;modelName=response.model;
      }
      const result=groundedAnswer(content,evidence,modelName);
      if(!study&&!result.sources.length)throw new Error('AI_INVALID_RESPONSE');
      yield mark('validate','回答与来源检查完成','completed');
      yield{type:'done',...result,engine:'xiaomi-mimo',workflow:{intent,steps:trace}};
    }catch(error){
      if(signal?.aborted)throw error;
      yield mark('generate','生成服务暂不可用，已使用实际原文或学习规则','degraded');
      yield finish(local(),evidence);
    }
  }

  return{
    stream,
    async run(input,options){
      for await(const event of stream(input,options))if(event.type==='done'){const{type,...result}=event;return result;}
      throw new Error('AGENT_INCOMPLETE');
    }
  };
}

module.exports={createLearningWorkflow,routeTask};
