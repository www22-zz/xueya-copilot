/* Agent boundary for the UI: resolve passages, request AI, or return local excerpts. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('../../../shared/learning.js'),require('../../../shared/contracts/index.js'),require('../../../shared/agent/sse.js'),require('../../../shared/agent/context.js'),require('../../../shared/agent/tasks.js'));else root.XueyaChat=factory(root.XueyaLearning,root.XueyaContracts,root.XueyaSSE,root.XueyaContext,root.XueyaTasks);})(typeof globalThis!=='undefined'?globalThis:this,function(L,C,SSE,Context,Tasks){
  'use strict';

  function createChatService({fetchImpl=globalThis.fetch,protocol=globalThis.location?.protocol||'http:',timeoutMs=30000,streamTimeoutMs=90000}={}){
    function prepare(input,{currentSourcesOnly=false}={}){
      const request=C.normalizeChatRequest(input);
      request.sources=request.sources.map(source=>typeof source==='string'?L.sources.find(item=>item.id===source):source).filter(source=>source&&typeof source.id==='string'&&typeof source.quote==='string');
      let hits=L.retrieve(Tasks.retrievalQuery(request,request.sources),request.sources);
      if(!hits.length&&Tasks.refersToPrevious(request.question)&&input.previousSources?.length){
        hits=currentSourcesOnly?input.previousSources.map(prior=>request.sources.find(source=>source.id===prior.id)).filter(Boolean):input.previousSources;
      }
      return{request,hits};
    }
    function success(payload,hits){
      if(payload?.ok!==true||typeof payload.answer!=='string'||!payload.answer.trim()||!Array.isArray(payload.sources))throw new Error('AI_UNAVAILABLE');
      const local=payload.engine==='local-workflow';
      return{answer:payload.answer,sources:[...new Set(payload.sources)].map(id=>hits.find(source=>source.id===id)).filter(Boolean),engine:local?'本地学习流程':'MiMo 资料问答',online:!local,knowledgePoints:payload.knowledgePoints||[],model:payload.model,...(payload.workflow?{workflow:payload.workflow}:{}),...(payload.artifacts?{artifacts:payload.artifacts}:{})};
    }
    function fallback(request,hits,context){
      const intent=context?Tasks.routeTask(request.question,request.mode):request.mode;
      if(context&&(intent==='plan'||intent==='review')){
        const {progress,plan}=Tasks.localStudy(context,intent);
        return{answer:Tasks.studyText(intent,progress,plan,context.baseDate),sources:[],reasoning:'',engine:'本地学习流程',online:false,knowledgePoints:[],workflow:{intent,steps:[{stage:'tools',label:'连接暂不可用，已使用本地学习记录',status:'degraded'},{stage:'validate',label:'已核对作答统计和计划设置',status:'completed'}]},artifacts:{progress,...(plan?{plan}:{})}};
      }
      return{answer:L.localAnswer(request.question,intent,hits),sources:hits,reasoning:'',engine:'本地检索摘录',online:false,knowledgePoints:[]};
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
              onUpdate({progress:typeof event.label==='string'?event.label:''});
              continue;
            }
            if(event.type==='done'){
              completed={...success(event,catalog),reasoning:event.engine==='local-workflow'?'':reasoning};
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
          return fallback(request,hits,context);
        }
      }
    };
  }

  return{createChatService};
});
