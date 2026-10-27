/* Agent boundary for the UI: resolve passages and show explicit generation failures. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('../../../shared/learning.js'),require('../../../shared/contracts/index.js'),require('../../../shared/agent/sse.js'),require('../../../shared/agent/context.js'),require('../../../shared/agent/tasks.js'));else root.XueyaChat=factory(root.XueyaLearning,root.XueyaContracts,root.XueyaSSE,root.XueyaContext,root.XueyaTasks);})(typeof globalThis!=='undefined'?globalThis:this,function(L,C,SSE,Context,Tasks){
  'use strict';

  function createChatService({fetchImpl=globalThis.fetch,protocol=globalThis.location?.protocol||'http:',timeoutMs=30000,streamTimeoutMs=90000}={}){
    function prepare(input,{currentSourcesOnly=false}={}){
      const request=C.normalizeChatRequest(input);
      if(typeof input.courseId==='string')request.courseId=input.courseId.slice(0,150);
      if(Array.isArray(input.documentIds))request.documentIds=input.documentIds.filter(id=>typeof id==='string').slice(0,100);
      if(input.webSearch)request.webSearch=true;
      request.sources=request.sources.map(source=>typeof source==='string'?L.sources.find(item=>item.id===source):source).filter(source=>source&&typeof source.id==='string'&&typeof source.quote==='string');
      let hits=L.retrieve(Tasks.retrievalQuery(request,request.sources),request.sources);
      if(!hits.length&&Tasks.refersToPrevious(request.question)&&input.previousSources?.length){
        hits=currentSourcesOnly?input.previousSources.map(prior=>request.sources.find(source=>source.id===prior.id)).filter(Boolean):input.previousSources;
      }
      return{request,hits};
    }
    function success(payload,hits){
      if(payload?.ok!==true||typeof payload.answer!=='string'||!payload.answer.trim()||!Array.isArray(payload.sources))throw new Error('AI_UNAVAILABLE');
      const local=payload.engine==='local-workflow',unavailable=payload.engine==='general-chat-unavailable',incomplete=payload.answerStatus==='unavailable',info=payload.engine==='assistant-info',dynamic=payload.agent?.planRevision>0;
      const resolved=[...(Array.isArray(payload.sourceDetails)?payload.sourceDetails:[]),...(Array.isArray(payload.sourceObjects)?payload.sourceObjects:[])].filter(s=>s&&typeof s.id==='string'&&typeof s.quote==='string'&&typeof s.title==='string'&&typeof s.location==='string');
      const sources=[...new Set(payload.sources)].map(id=>resolved.find(source=>source.id===id)||hits.find(source=>source.id===id)).filter(Boolean);
      return{answer:payload.answer,sources,engine:incomplete?'回答未完成':info?'应用信息':dynamic?'AI 学习规划':unavailable?'通用问答暂不可用':local?'本地学习流程':payload.engine==='general-chat'?'MiMo 通用问答':'MiMo 资料问答',online:!incomplete&&!info&&(dynamic||!local&&!unavailable),knowledgePoints:payload.knowledgePoints||[],model:payload.model,...(payload.answerStatus?{answerStatus:payload.answerStatus}:{}),...(payload.reason?{reason:payload.reason}:{}),...(payload.timings?{timings:payload.timings}:{}),...(payload.agent?{agent:payload.agent}:{}),...(payload.workflow?{workflow:payload.workflow}:{}),...(payload.artifacts?{artifacts:payload.artifacts}:{})};
    }
    function fallback(request,hits,context){
      const greeting=Tasks.conversationReply(request.question,request.mode);
      if(greeting)return{answer:greeting,sources:[],reasoning:'',engine:'本地学习流程',online:false,knowledgePoints:[]};
      const intent=context?Tasks.routeTask(request.question,request.mode):request.mode;
      if(context&&(intent==='plan'||intent==='review')){
        const {progress,plan}=Tasks.localStudy(context,intent);
        return{answer:Tasks.studyText(intent,progress,plan,context.baseDate),sources:[],reasoning:'',engine:'本地学习流程',online:false,knowledgePoints:[],workflow:{intent,steps:[{stage:'tools',label:'连接暂不可用，已使用本地学习记录',status:'degraded'},{stage:'validate',label:'已核对作答统计和计划设置',status:'completed'}]},artifacts:{progress,...(plan?{plan}:{})}};
      }
      if(context&&intent==='ask'&&!hits.length&&!Tasks.requiresCourseEvidence(request.question,request.mode)&&!context.previousSourceIds.length){
        return{answer:'通用问答服务暂时不可用，请检查项目是否已启动或稍后重试。',sources:[],reasoning:'',engine:'通用问答暂不可用',answerStatus:'unavailable',online:false,knowledgePoints:[]};
      }
      if(protocol==='file:')return{answer:L.localAnswer(request.question,intent,hits),sources:hits,reasoning:'',engine:'离线检索预览',online:false,knowledgePoints:[]};
      return{answer:'这次 AI 回答未能完成。相关资料保留在下方供你核对。',sources:hits,reasoning:'',engine:'回答未完成',answerStatus:'unavailable',online:false,knowledgePoints:[]};
    }
    return{
      async ask(input){
        const {request,hits}=prepare(input);
        try{
          if(protocol==='file:')throw new Error('LOCAL_PREVIEW');
          const response=await fetchImpl('/api/ai',{
            method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({...request,sources:hits}),signal:AbortSignal.timeout(timeoutMs)
          });
          const payload=await response.json();
          if(!response.ok)throw new Error('AI_UNAVAILABLE');
          return success(payload,hits);
        }catch{return fallback(request,hits);}
      },
      async stream(input,{onUpdate=()=>{},workflow=false,signal}={}){
        signal?.throwIfAborted();
        const {request,hits}=prepare(input,{currentSourcesOnly:workflow});
        const context=workflow?Context.normalizeContext({...input.learning,library:[...hits,...request.sources],previousSourceIds:(input.previousSources||[]).map(source=>source.id)}):undefined;
        const catalog=workflow?[...hits,...context.library]:hits;
        const timeoutSignal=AbortSignal.timeout(streamTimeoutMs);
        const requestSignal=signal?AbortSignal.any([signal,timeoutSignal]):timeoutSignal;
        let agent,runId,toolCalls;
        try{
          if(protocol==='file:')throw new Error('LOCAL_PREVIEW');
          const response=await fetchImpl(workflow?'/api/agent/stream':'/api/ai/stream',{
            method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...request,sources:hits,...(context?{context}:{})}),signal:requestSignal
          });
          if(!response.ok||!response.headers.get('content-type')?.includes('text/event-stream'))throw new Error('AI_UNAVAILABLE');
          let content='',reasoning='',completed;
          for await(const data of SSE.readSSE(response.body,{signal:requestSignal})){
            requestSignal.throwIfAborted();
            let event;
            try{event=JSON.parse(data);}catch{throw new Error('AI_INVALID_RESPONSE');}
            if(event.type==='error')throw new Error(event.error||'AI_UNAVAILABLE');
            if(event.type==='workflow'){
              if(event.agent)agent=event.agent;
              if(event.toolCalls)toolCalls=event.toolCalls;
              if(event.runId)runId=event.runId;
              onUpdate({progress:typeof event.label==='string'?event.label:'',...(event.agent?{agent:event.agent}:{}),...(event.toolCalls?{toolCalls:event.toolCalls}:{}),...(runId?{runId}:{})});
              continue;
            }
            if(event.type==='done'){
              completed={...success(event,catalog),reasoning:event.engine==='local-workflow'?'':reasoning,...(event.toolCalls?{toolCalls:event.toolCalls}:{}),...(event.runId?{runId:event.runId}:{})};
              break;
            }
            if(event.type==='content'&&typeof event.text==='string')content+=event.text;
            if(event.type==='reasoning'&&typeof event.text==='string')reasoning+=event.text;
            if(content.length+reasoning.length>200000)throw new Error('AI_INVALID_RESPONSE');
            const fragment=content.match(/"answer"\s*:\s*"((?:[^"\\]|\\.)*)/s)?.[1];
            let answer='';
            if(fragment){try{answer=JSON.parse('"'+fragment.replace(/\\u[0-9a-fA-F]{0,3}$/,'')+'"');}catch{}}
            onUpdate({answer,reasoning});
          }
          if(!completed)throw new Error('AI_INCOMPLETE_STREAM');
          requestSignal.throwIfAborted();
          return completed;
        }catch(error){
          if(signal?.aborted)throw signal.reason;
          return {...fallback(request,hits,context),...(agent?{agent:{...agent,status:'partial',stopReason:error.message||'AI_INCOMPLETE_STREAM'}}:{}),...(toolCalls?{toolCalls:toolCalls.map(c=>c.status==='running'?{...c,status:'interrupted',data:{error:error.message||'AI_INCOMPLETE_STREAM'}}:c)}:{}),...(runId?{runId}:{})};
        }
      }
    };
  }

  return{createChatService};
});
