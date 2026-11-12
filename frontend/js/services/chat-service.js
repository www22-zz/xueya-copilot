/* Agent boundary for the UI: resolve passages and show explicit generation failures. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('../../../shared/learning.js'),require('../../../shared/contracts/index.js'),require('../../../shared/agent/sse.js'),require('../../../shared/agent/context.js'),require('../../../shared/agent/tasks.js'));else root.XueyaChat=factory(root.XueyaLearning,root.XueyaContracts,root.XueyaSSE,root.XueyaContext,root.XueyaTasks);})(typeof globalThis!=='undefined'?globalThis:this,function(L,C,SSE,Context,Tasks){
  'use strict';

  function createChatService({fetchImpl=globalThis.fetch,protocol=globalThis.location?.protocol||'http:',timeoutMs=30000,streamTimeoutMs=240000}={}){
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
      const local=payload.engine==='local-workflow',unavailable=payload.engine==='general-chat-unavailable',incomplete=payload.answerStatus==='unavailable',info=payload.engine==='assistant-info',dynamic=payload.agent?.planRevision>0,autonomous=payload.engine==='general-chat'&&Boolean(payload.fallback);
      const genericEngine=['资料问答','通用回答','自主回答'].includes(payload.engine)?payload.engine:null;
      const engine=incomplete?'回答未完成':info?'应用信息':autonomous?'通用回答':dynamic?'AI 学习规划':unavailable?'通用问答暂不可用':local?'本地学习流程':genericEngine||(payload.engine==='general-chat'?'通用回答':payload.engine==='web-search-synthesized'?'联网回答':'资料问答');
      const resolved=[...(Array.isArray(payload.sourceDetails)?payload.sourceDetails:[]),...(Array.isArray(payload.sourceObjects)?payload.sourceObjects:[])].filter(s=>s&&typeof s.id==='string'&&typeof s.title==='string').map(s=>({location:'资料依据',quote:'',...s}));
      const sources=[...new Set(payload.sources)].map(id=>resolved.find(source=>source.id===id)||hits.find(source=>source.id===id)).filter(Boolean);
      const suggested=Array.isArray(payload.suggestedQuestions)?payload.suggestedQuestions.filter(item=>typeof item==='string'&&item.trim()).map(item=>item.trim()).slice(0,3):[];
      return{answer:payload.answer,sources:autonomous?[]:sources,engine,online:!incomplete&&!info&&(dynamic||!local&&!unavailable),knowledgePoints:payload.knowledgePoints||[],model:payload.model,...(suggested.length?{suggestedQuestions:suggested}:{}),...(payload.answerStatus?{answerStatus:payload.answerStatus}:{}),...(payload.reason?{reason:payload.reason}:{}),...(payload.verification?{verification:payload.verification}:{}),...(payload.fallback?{fallback:payload.fallback}:{}),...(payload.timings?{timings:payload.timings}:{}),...(payload.agent?{agent:payload.agent}:{}),...(payload.workflow?{workflow:payload.workflow}:{}),...(payload.artifacts?{artifacts:payload.artifacts}:{})};
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
        let agent,runId,toolCalls,draft='',drafting=false,progress='',contentUpdates=0;
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
            if(event.type==='draft'){/* unverified preview: never parsed as an answer and never saved to history */
              if(event.reset===true){
                draft='';drafting=true;
                onUpdate({answer:'',draft:true,progress});
                continue;
              }
              if(event.draft!==false&&typeof event.text==='string'&&event.text){
                draft+=event.text;
                if(draft.length>200000)throw new Error('AI_INVALID_RESPONSE');
                drafting=true;
                onUpdate({answer:draft,draft:true,progress});
              }
              continue;
            }
            if(event.type==='workflow'){
              progress=typeof event.label==='string'?event.label:'';
              if(event.resetAnswer===true){
                content='';reasoning='';draft='';
                const hadDraft=drafting;drafting=false;
                onUpdate({answer:'',reasoning:'',...(hadDraft?{draft:false}:{})});
              }
              if(event.agent)agent=event.agent;
              if(event.toolCalls)toolCalls=event.toolCalls;
              if(event.runId)runId=event.runId;
              onUpdate({progress,...(event.agent?{agent:event.agent}:{}),...(event.toolCalls?{toolCalls:event.toolCalls}:{}),...(runId?{runId}:{})});
              continue;
            }
            if(event.type==='done'){
              completed={...success(event,catalog),streamed:contentUpdates>=3,reasoning:event.engine==='local-workflow'?'':reasoning,...(event.toolCalls?{toolCalls:event.toolCalls}:{}),...(event.runId?{runId:event.runId}:{})};
              if(drafting){
                drafting=false;draft='';
                onUpdate({answer:completed.answer,draft:false,final:true,reasoning:completed.reasoning||''});
              }
              break;
            }
            if(event.type==='content'&&typeof event.text==='string')content+=event.text;
            if(event.type==='reasoning'&&typeof event.text==='string')reasoning+=event.text;
            if(content.length+reasoning.length>200000)throw new Error('AI_INVALID_RESPONSE');
            const fragment=content.match(/"answer"\s*:\s*"((?:[^"\\]|\\.)*)/s)?.[1];
            let answer='';
            if(fragment){try{answer=JSON.parse('"'+fragment.replace(/\\u[0-9a-fA-F]{0,3}$/,'')+'"');}catch{}}
            if(answer&&answer!==undefined)contentUpdates+=1;
            onUpdate(drafting?{answer:answer||draft,reasoning,draft:true,progress}:{answer,reasoning});
          }
          if(!completed)throw new Error('AI_INCOMPLETE_STREAM');
          requestSignal.throwIfAborted();
          return completed;
        }catch(error){
          if(signal?.aborted)throw signal.reason;
          if(drafting){drafting=false;draft='';onUpdate({answer:'',reasoning:'',draft:false});}
          return {...fallback(request,hits,context),...(agent?{agent:{...agent,status:'partial',stopReason:error.message||'AI_INCOMPLETE_STREAM'}}:{}),...(toolCalls?{toolCalls:toolCalls.map(c=>c.status==='running'?{...c,status:'interrupted',data:{error:error.message||'AI_INCOMPLETE_STREAM'}}:c)}:{}),...(runId?{runId}:{})};
        }
      }
    };
  }

  function prefersReducedMotion(win=globalThis){
    try{return Boolean(win?.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches);}catch{return false;}
  }
  /* Character-by-character reveal for the verified final answer. Pure timers, no DOM. */
  function createTypewriter({intervalMs=40,totalMs=1500,reducedMotion=false,setTimeoutImpl=globalThis.setTimeout,clearTimeoutImpl=globalThis.clearTimeout}={}){
    function start(text,onFrame,{from=0,signal}={}){
      const value=typeof text==='string'?text:'';
      const chars=Array.from(value);
      const emit=partial=>{try{onFrame(partial);}catch{}};
      if(!chars.length||reducedMotion){emit(value);return Promise.resolve(value);}
      const startIndex=Math.max(0,Math.min(chars.length,Number.isFinite(from)?Math.trunc(from):0));
      const remaining=chars.length-startIndex;
      if(remaining<=0){emit(value);return Promise.resolve(value);}
      const frames=Math.max(1,Math.min(remaining,Math.ceil(totalMs/Math.max(1,intervalMs))));
      const step=Math.max(1,Math.ceil(remaining/frames));
      const delay=Math.max(16,Math.min(intervalMs,Math.floor(totalMs/frames)));
      return new Promise(resolve=>{
        let shown=startIndex,timer=null,settled=false;
        function settle(){if(settled)return;settled=true;if(timer!==null){clearTimeoutImpl(timer);timer=null;}if(shown<chars.length)emit(value);resolve(value);}
        function tick(){
          if(settled)return;
          if(signal?.aborted){settle();return;}
          shown=Math.min(chars.length,shown+step);
          emit(chars.slice(0,shown).join(''));
          if(shown>=chars.length){settle();return;}
          timer=setTimeoutImpl(tick,delay);
        }
        tick();
      });
    }
    return{start};
  }
  /* Applies one stream onUpdate to an in-flight assistant message. Draft previews only
     set the "organizing" indicator and never become the answer text; the verified final
     answer arrives with final:true and is painted by the typewriter afterwards. */
  function applyStreamUpdate(message,update){
    if(!message||!update||typeof update!=='object')return message;
    if(typeof update.draft==='boolean')message.draft=update.draft;
    if(typeof update.reasoning==='string')message.reasoning=update.reasoning;
    if(update.progress){
      const previous=typeof message.progress==='string'?message.progress:'';
      const parts=previous?previous.split('\n'):[];
      if(parts[parts.length-1]!==update.progress)parts.push(update.progress);
      message.progress=parts.join('\n');
    }
    if(update.final===true){message.organizing=false;return message;}
    if(update.draft===true){message.organizing=true;return message;}
    if(typeof update.answer==='string'){message.text=update.answer;message.organizing=false;}
    return message;
  }
  /* Best-effort LLM follow-up questions; never throws and never blocks the answer. */
  async function requestSuggestions(input,{fetchImpl=globalThis.fetch,timeoutMs=8000}={}){
    const {courseId,question,answer,history}=input||{};
    if(typeof fetchImpl!=='function'||typeof question!=='string'||!question.trim()||typeof answer!=='string'||!answer.trim())return null;
    const body={question,answer,history:Array.isArray(history)?history:[]};
    if(typeof courseId==='string'&&courseId)body.courseId=courseId;
    let timer=null,controller=null;
    try{
      const options={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
      if(Number.isFinite(timeoutMs)&&timeoutMs>0&&typeof AbortController==='function'){
        controller=new AbortController();options.signal=controller.signal;
        timer=setTimeout(()=>{try{controller.abort();}catch{}},timeoutMs);
      }
      const response=await fetchImpl('/api/agent/suggestions',options);
      if(!response||response.ok===false)return null;
      const payload=await response.json();
      if(payload?.ok!==true||!Array.isArray(payload.questions))return null;
      const questions=payload.questions.filter(item=>typeof item==='string'&&item.trim()).map(item=>item.trim()).slice(0,3);
      return questions.length?questions:null;
    }catch{return null;}
    finally{if(timer!==null){try{clearTimeout(timer);}catch{}}}
  }

  return{createChatService,createTypewriter,prefersReducedMotion,applyStreamUpdate,requestSuggestions};
});
