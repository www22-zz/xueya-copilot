/* Chat planning uses the same saved plan and framework objects as 学习分析. */
(function(root){
  'use strict';
  const e=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const restoring=new Set();
  async function api(path,body,signal){
    const response=await root.XueyaPlatform.spaceFetch('/api/learning/space/'+path,{
      ...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal});
    const value=await response.json();if(!value.ok)throw Error(value.error);return value;
  }
  async function result(jobId,signal){
    while(true){
      signal?.throwIfAborted();
      const {job}=await api('jobs/'+encodeURIComponent(jobId),undefined,signal);
      if(job.status==='succeeded'){
        const {plan}=await api('plan/'+encodeURIComponent(job.result.planId),undefined,signal);
        const days=plan.days.filter(day=>day.tasks.length).slice(0,7).map(day=>day.date+'：'+day.tasks.map(t=>t.title+'（'+t.minutes+'分钟）').join('；'));
        return {answer:'计划草稿已保存，采用后才进入当前任务。\n\n'+plan.explanation+'\n\n'+days.join('\n')+(plan.remaining.length?'\n另有 '+plan.remaining.length+' 项未排入，请调整时间或范围。':''),sources:[],engine:'AI 学习规划',online:true,
          artifacts:{studyPlanning:{status:'succeeded',jobId,planId:plan.id,revision:plan.revision,frameworkId:plan.frameworkId}}};
      }
      if(['failed','cancelled','unknown'].includes(job.status))return {answer:'本次规划尚未完整完成（'+job.status+'）。已提交的付费请求不会自动重发。'+(job.checkpoint?.planId?'部分计划草稿已保留，可到“我的计划”核对。':''),sources:[],engine:'规划未完成',online:false,answerStatus:'unavailable',
        artifacts:{studyPlanning:{status:job.status,jobId,planId:job.checkpoint?.planId}}};
      await new Promise(resolve=>setTimeout(resolve,300));
    }
  }
  async function handle(input,{signal,onReference=()=>{}}={}){
    const value=await api('chat/plan',input,signal);
    if(!value.handled)return null;
    if(value.status==='collecting')return {answer:value.answer,sources:[],engine:'规划条件待补齐',online:false,
      artifacts:{studyPlanning:{status:'collecting',conditions:value.conditions,missing:value.missing}}};
    const reference={status:'queued',jobId:value.jobId};onReference(reference);
    const cancel=()=>{api('jobs/'+encodeURIComponent(value.jobId)+'/cancel',{}).catch(()=>{});};
    signal?.addEventListener('abort',cancel,{once:true});
    try{return await result(value.jobId,signal);}finally{signal?.removeEventListener('abort',cancel);}
  }
  function markup(message){
    const ref=message.artifacts?.studyPlanning;if(!ref)return '';
    return `<section class="study-chat-card panel" data-study-plan="${e(ref.planId||'')}" aria-label="学习规划产物">
      ${ref.status==='collecting'?'<button class="button button-small button-outline" type="button" data-plan-defaults>按默认条件安排</button>':`<p>${ref.status==='succeeded'?'草稿与知识框架已保存':'作业状态：'+e(ref.status)}</p>`}
      ${ref.planId?'<a class="button button-small button-blue" href="#space/analysis/plans">查看草稿与采用</a>':''}
      ${ref.frameworkId?`<a class="button button-small button-outline" href="#space/frameworks/${e(ref.frameworkId)}">打开关联知识框架</a>`:''}
    </section>`;
  }
  function recover(state,persist,render){
    if(state.pending||!root.XueyaPlatform?.available)return;
    for(const message of state.messages){
      const ref=message.artifacts?.studyPlanning;
      if(!ref?.jobId||ref.status!=='queued'||restoring.has(ref.jobId))continue;
      restoring.add(ref.jobId);
      result(ref.jobId).then(value=>{
        const apply=target=>Object.assign(target,{text:value.answer,engine:value.engine,failed:value.answerStatus==='unavailable',artifacts:value.artifacts});
        state.messages.filter(m=>m.id===message.id).forEach(apply);
        for(const session of state.sessions)session.messages.filter(m=>m.id===message.id).forEach(apply);
        persist();render();
      }).catch(()=>{}).finally(()=>restoring.delete(ref.jobId));
    }
  }
  document.addEventListener('click',event=>{if(event.target.closest('[data-plan-defaults]'))root.XueyaAsk?.('按默认条件安排');});
  root.XueyaStudyChat={handle,markup,recover};
})(window);
