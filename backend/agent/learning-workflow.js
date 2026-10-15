'use strict';

const L=require('../../shared/learning.js');
const {normalizeChatRequest}=require('../../shared/contracts/index.js');
const {normalizeContext}=require('../../shared/agent/context.js');
const {createCourseSession}=require('../mcp/course-session.js');
const {buildMessages}=require('./prompts.js');
const {groundedAnswer}=require('./index.js');
const {routeTask,refersToPrevious,retrievalQuery,localStudy,studyText}=require('../../shared/agent/tasks.js');

function createLearningWorkflow({model,openSession=createCourseSession,toolTimeoutMs=5000}){
  async function* stream(input,{signal}={}){
    signal?.throwIfAborted();
    const request=normalizeChatRequest(input);
    const context=normalizeContext({...input.context,library:input.context?.library??request.sources});
    const intent=routeTask(request.question,request.mode);
    const query=retrievalQuery(request,context.library);
    const previousIds=refersToPrevious(request.question)?context.previousSourceIds:[];
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
        const found=await session.call('search_materials',{query,limit:4});
        const ids=[...new Set((Array.isArray(found.sources)?found.sources:[]).map(source=>source.id))].slice(0,3);
        if(ids.some(id=>!actual.has(id)))throw new Error('MCP_INVALID_RESULT');
        if(!ids.length)ids.push(...previousIds);
        if(query!==request.question||previousIds.length)yield mark('context','已结合上一轮问题与有效原文理解追问','completed');
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
      else{
        evidence=L.retrieve(query,context.library).slice(0,3);
        if(!evidence.length)evidence=previousIds.map(id=>actual.get(id));
      }
    }finally{
      await session?.close().catch(()=>{});
    }
    signal?.throwIfAborted();
    const local=()=>study?studyText(intent,progress,plan,context.baseDate):L.localAnswer(request.question,intent,evidence);
    if(study){
      yield mark('validate','已核对作答统计和计划设置','completed');
      yield finish(local(),[],{artifacts:{progress,...(plan?{plan}:{})}});return;
    }
    if(!study&&!evidence.length){yield finish(local());return;}
    const messages=buildMessages({...request,mode:intent==='summarize'||intent==='quiz'?intent:'ask',sources:evidence});
    yield mark('generate','正在依据原文整理回答');
    try{
      let content='',modelName,received=0;
      if(typeof model.stream==='function'){
        for await(const event of model.stream({messages,signal})){
          signal?.throwIfAborted();
          if(['content','reasoning'].includes(event.type)&&typeof event.text==='string'){
            received+=event.text.length;
            if(received>200000)throw new Error('AI_INVALID_RESPONSE');
          }
          if(event.type==='content'&&typeof event.text==='string'){
            content+=event.text;
          }
          modelName=event.model||modelName;
          if(['content','reasoning'].includes(event.type)&&typeof event.text==='string')yield event;
        }
      }else{
        const response=await model.generate({messages,signal});
        content=response.content;modelName=response.model;
      }
      signal?.throwIfAborted();
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
