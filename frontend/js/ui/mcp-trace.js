/* Actual host observations, never model reasoning or simulated tool activity. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaMCPTrace=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const names={search_materials:'查找课程资料',read_source:'读取引用原文',search_web:'全网搜索',analyze_progress:'分析学习记录',build_review_plan:'生成复习预览',list_wrong_questions:'读取错题',get_review_queue:'查看到期复习卡',get_course_graph:'读取知识图谱'};
  const statuses={running:'调用中',completed:'成功',failed:'失败',duplicate:'已跳过重复调用',interrupted:'未完成',cancelled:'已停止',unknown:'结果未知'};
  const runStatuses={running:'正在执行',queued:'等待执行',completed:'本轮已完成',partial:'本轮未完成',awaiting_user:'等待补充信息',awaiting_confirmation:'等待确认',failed:'执行失败',unknown:'结果待确认',paused:'已暂停',cancelled:'已停止'};

  function collect(previous=[],agent={}){
    const calls=new Map(previous.map(c=>[c.id,{...c}]));
    const decisions=(agent.decisions||[]).filter(d=>d.type==='call_tool');
    for(const d of decisions){
      const id=String(d.round??d.stepId);
      calls.set(id,{...calls.get(id),id,round:d.round,stepId:d.stepId,tool:d.tool,arguments:d.arguments??calls.get(id)?.arguments??{},status:calls.get(id)?.status||'running'});
    }
    for(const o of agent.observations||[]){
      if(!o.tool)continue;
      const d=decisions.findLast(d=>d.stepId===o.stepId&&d.tool===o.tool);
      const id=String(o.round??d?.round??o.stepId);
      calls.set(id,{...calls.get(id),...o,id});
    }
    if(agent.status&& !['running','queued'].includes(agent.status))for(const c of calls.values()){
      if(c.status==='running'){c.status=agent.status==='cancelled'?'cancelled':'interrupted';c.data={error:agent.stopReason||'TOOL_RESULT_NOT_RECEIVED'};}
    }
    return [...calls.values()].slice(-24);
  }
  function safe(value,depth=0){
    if(depth>10)return '[层级过深，已省略]';
    if(Array.isArray(value))return value.slice(0,100).map(v=>safe(v,depth+1));
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).slice(0,100).map(([k,v])=>[k,/(api.?key|token|password|secret|authorization|cookie)/i.test(k)?'[已隐藏]':safe(v,depth+1)]));
    return typeof value==='string'?value.slice(0,12000):value;
  }
  function json(value){const text=JSON.stringify(safe(value??{}),null,2);return escape(text.length>20000?text.slice(0,20000)+'\n… 内容较长，已截取显示':text);}
  function summary(c){
    if(c.status==='running')return '已发起调用，等待服务返回。';
    if(c.status==='duplicate')return '相同请求已处理，本次没有重复执行。';
    if(c.data?.error)return '错误：'+c.data.error;
    const d=c.data||{};
    if(c.tool==='search_materials')return `找到 ${d.sources?.length||0} 条原文线索`;
    if(c.tool==='search_web')return `检索到 ${d.sources?.length||0} 条全网网页线索`;
    if(c.tool==='read_source')return [d.source?.title,d.source?.location].filter(Boolean).join(' · ')||'原文已读取';
    if(c.tool==='analyze_progress')return `读取 ${d.total??0} 次作答，答对 ${d.correct??0} 次`;
    if(c.tool==='build_review_plan')return `生成 ${d.days?.length||0} 天复习预览，尚未保存`;
    if(c.tool==='list_wrong_questions')return `本页返回 ${d.items?.length||0} 道错题`;
    if(c.tool==='get_review_queue')return `当前返回 ${d.count??d.cards?.length??0} 张到期复习卡`;
    if(c.tool==='get_course_graph')return `${d.conceptCount??0} 个概念，${d.edgeCount??0} 条关系`;
    return '已收到工具结果';
  }
  function render(message){
    const agent={...(message.agent||{}),...(message.cancelled?{status:'cancelled'}:message.failed?{status:'failed'}:{})},calls=collect(message.toolCalls,agent);
    if(!calls.length&&!agent.plan)return '';
    const status=message.cancelled?'cancelled':message.failed?'failed':message.engine==='正在回答'?'running':agent.status||(calls.some(c=>['failed','interrupted'].includes(c.status))?'partial':calls.every(c=>['completed','duplicate'].includes(c.status))?'completed':'unknown');
    return `<details class="mcp-trace" data-trace-key="root" open><summary><span>MCP 工具调用 <small>${calls.length} 步</small></span><span class="mcp-run-status">${escape(runStatuses[status]||status)}</span></summary><div class="mcp-trace-body">${agent.plan?`<p class="mcp-goal">${escape(agent.plan.goal)}</p>`:''}${calls.length?`<ol class="mcp-call-list">${calls.map((c,i)=>`<li class="mcp-call" data-tool="${escape(c.tool)}" data-status="${escape(c.status)}"><div class="mcp-call-heading"><span class="mcp-call-number">${i+1}</span><strong>${escape(names[c.tool]||c.tool)}</strong><span class="mcp-call-status">${escape(statuses[c.status]||c.status)}</span></div><code class="mcp-tool-name">${escape(c.tool)}</code><p class="mcp-result-summary">${escape(summary(c))}</p>${c.data?.source?.quote?`<blockquote>${escape(c.data.source.quote.slice(0,500))}</blockquote>`:''}${c.data?.sources?.length?`<ul class="mcp-found-sources">${c.data.sources.map(s=>`<li><strong>${escape(s.title||s.id)}</strong>${s.location?` · ${escape(s.location)}`:''}<p>${escape(s.excerpt||'')}</p></li>`).join('')}</ul>`:''}${c.data?.warnings?.length?`<p class="mcp-warning">提示：${c.data.warnings.map(escape).join('、')}</p>`:''}<details class="mcp-call-data" data-trace-key="call-${escape(c.id)}"><summary>查看参数与返回结果</summary><h4>调用参数</h4><pre>${json(c.arguments)}</pre><h4>${c.status==='running'?'等待返回':'工具返回（服务端已限制长度）'}</h4>${c.status==='running'?'<p>尚未收到结果，不计为成功。</p>':`<pre>${json(c.data)}</pre>`}</details></li>`).join('')}</ol>`:'<p>正在制定计划，尚未发起工具调用。</p>'}${agent.stopReason&&agent.stopReason!=='FINISHED'?`<p class="mcp-stop-reason">停止原因：${escape(agent.stopReason)}</p>`:''}<p class="mcp-trace-note">记录来自实际工具执行。空结果、失败和未完成会如实显示；生成计划预览不会自动保存。</p></div></details>`;
  }
  function mount(container,message){
    if(!container)return;
    const open=new Map([...container.querySelectorAll('details[data-trace-key]')].map(el=>[el.dataset.traceKey,el.open]));
    container.innerHTML=render(message);
    for(const el of container.querySelectorAll('details[data-trace-key]'))if(open.has(el.dataset.traceKey))el.open=open.get(el.dataset.traceKey);
  }
  return {collect,render,mount};
});
