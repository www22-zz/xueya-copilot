/* Durable learning controls reuse the authenticated platform client and chat store. */
(function(root){
  'use strict';
  const labels={queued:'等待执行',running:'正在推进',paused:'已暂停',unknown:'上次请求结果待确认',failed:'执行未完成',partial:'本轮准备未完成',awaiting_user:'等待你补充',awaiting_confirmation:'等待你确认',completed:'本轮已完成',cancelled:'已取消'};
  const causes={'knowledge-gap':'知识理解有缺口',misread:'审题有误',calculation:'计算有误',method:'方法不合适',notation:'符号理解有误','input-error':'输入或点击失误',uncertain:'还不确定'};
  const e=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const button=(label,index,action)=>`<button type="button" class="subtle-button" data-agent-index="${index}" data-agent-action="${action}">${label}</button>`;
  function plan(value){
    if(!value?.days)return '';
    return `<p>考试日期：${e(value.examDate)} · 每日 ${e(value.minutes)} 分钟</p>${value.days.length?`<ol>${value.days.slice(0,14).map(d=>`<li>${e(d.date)}：${d.tasks.map(t=>`${e(t.title||t.conceptId||'记忆卡')} ${e({read:'阅读',practice:'练习',review:'复习','card-review':'记忆复习'}[t.kind]||t.kind||'')} ${e(t.minutes)} 分钟`).join('；')}</li>`).join('')}</ol>`:'<p>当前没有可排入的任务。</p>'}${value.days.length>14?'<p>其余日期可在复习计划页查看。</p>':''}${value.unallocatedMinutes?`<p>仍有 ${e(value.unallocatedMinutes)} 分钟任务未排入，请调整时间。</p>`:''}`;
  }
  function quiz(value,answer=false){
    return (value?.questions||[]).map((q,i)=>`<fieldset><legend>${i+1}. ${e(q.prompt)}</legend>${!answer?(q.options||[]).map(o=>`<p>${e(o)}</p>`).join(''):q.type==='single'||q.type==='multiple'?(q.options||[]).map((o,j)=>`<label><input type="${q.type==='single'?'radio':'checkbox'}" name="q${i}" value="${j}" ${q.type==='single'?'required':''}> ${e(o)}</label>`).join(''):q.type==='boolean'?`<select name="q${i}" required aria-label="第 ${i+1} 题答案"><option value="">请选择</option><option value="true">正确</option><option value="false">错误</option></select>`:q.type==='fill'?Array.from({length:q.blankCount},(_,j)=>`<input name="q${i}-${j}" required aria-label="第 ${i+1} 题第 ${j+1} 空">`).join(''):`<textarea name="q${i}" required maxlength="8000" aria-label="第 ${i+1} 题答案"></textarea>`}${answer?`<label>解题过程（选填）<textarea name="reason${i}" maxlength="8000"></textarea></label>`:''}</fieldset>`).join('');
  }
  function markup(message,index,enabled){
    const run=message.agentRun;
    if(!run)return enabled&&!message.failed&&!message.cancelled&&message.engine!=='正在回答'?`<div class="message-actions">${button('开始章节学习',index,'start-chapter')}${button('错题巩固',index,'start-wrong')}${button('跨章节备考',index,'start-exam')}</div>`:'';
    const s=run.state||{},interaction=run.interaction||{},form=(kind,content,label)=>`<form data-agent-form="${kind}" data-agent-index="${index}">${content}<button class="button button-small button-blue" type="submit">${label}</button></form>`;
    let body='';
    if(interaction.kind==='confirmation')body=`${interaction.explanation?`<p>${e(interaction.explanation)}</p>`:''}${interaction.grades?`<p>本次得分：${interaction.grades.map(g=>`${e(g.grade.score??'待评')}/${e(g.grade.maxScore)}`).join('，')}</p>`:''}${interaction.artifactKind==='quiz'?quiz(interaction.preview):plan(interaction.preview)}${interaction.changes?.previous?`<details><summary>查看原安排</summary>${plan(interaction.changes.previous)}</details>`:''}${interaction.limitation?`<p>${e(interaction.limitation)}</p>`:''}${button('确认并保存此预览',index,'confirm')}${button('重新预览',index,'refresh')}`;
    else if(interaction.kind==='quiz')body=form('answer',quiz(interaction.quiz,true),'提交实际作答');
    else if(interaction.kind==='diagnosis')body=form('diagnose',`<p>${e(interaction.limitation)}</p><p>原答案：${e(typeof interaction.answer==='object'?JSON.stringify(interaction.answer):interaction.answer)}</p><p>${e(interaction.reasoning)}</p><label>实际错因<select name="cause" required>${interaction.causes.map(c=>`<option value="${e(c)}">${e(causes[c])}</option>`).join('')}</select></label><label>确认理由<textarea name="reason" required maxlength="2000"></textarea></label>`,'确认错因并准备巩固');
    else if(['missing_questions','missing_graph','awaiting_review'].includes(interaction.kind))body=button('补充完成，更新结果',index,'refresh');
    else if(run.status==='awaiting_user'&&!interaction.kind)body=form('resume','<label>补充信息<textarea name="userInput" required maxlength="2000"></textarea></label>','补充并继续');
    if(run.scenario==='exam'&&['completed','awaiting_confirmation'].includes(run.status))body+=form('replan','<label>每日分钟数<input name="minutes" type="number" min="1" max="480" required></label><label>考试日期（选填）<input name="examDate" type="date"></label>','按最新成绩和时间重新预览');
    let controls=button('更新状态',index,'reload');
    if(['queued','running'].includes(run.status))controls+=button('暂停',index,'pause');
    if(['paused','failed'].includes(run.status))controls+=button('继续',index,'resume');
    if(run.status==='unknown')controls+=form('unknown','<p>上次请求可能已经计费。继续会发起新的规划请求，原请求不会重放。</p><label><input type="checkbox" name="acknowledge" required> 我理解并确认继续</label>','确认后继续');
    if(!['running','completed','cancelled'].includes(run.status))controls+=button('取消本轮',index,'cancel');
    return `<section class="agent-run panel" aria-label="持续学习任务"><strong>${e(labels[run.status]||run.status)}</strong>${s.plan?`<p>计划第 ${e(s.planRevision)} 版 · 已完成 ${s.completedStepIds?.length||0}/${s.plan.steps.length} 步</p><ol>${s.plan.steps.map(t=>`<li>${s.completedStepIds?.includes(t.id)?'✓ ':''}${e(t.title)}</li>`).join('')}</ol>`:''}${run.result?.answer?`<details><summary>查看资料核对结果</summary><p>${e(run.result.answer)}</p></details>`:''}${interaction.title?`<h3>${e(interaction.title)}</h3>`:''}${body}<div class="message-actions">${controls}</div></section>`;
  }
  function create({state,persist,render,toast}){
    const polling=new Map(),busy=new Set();let mounted=false;
    const request=(path,courseId,body)=>root.XueyaPlatform.learningRequest('agent-runs'+path,{courseId,method:body===undefined?'GET':'POST',body});
    function update(message,run){message.agentRun=run;persist();if(state.messages.includes(message))render();if(['queued','running'].includes(run.status))watch(message);}
    function watch(message){
      const run=message.agentRun,key=run.id;if(polling.has(key))return;
      polling.set(key,setTimeout(async()=>{polling.delete(key);if(!state.messages.includes(message))return;try{const value=await request('/'+encodeURIComponent(key),run.courseId);if(value.revision!==message.agentRun.revision)update(message,value);else if(['queued','running'].includes(value.status))watch(message);}catch{toast('学习任务仍保存在本机服务，可稍后更新状态。');}},1000));
    }
    async function action(index,kind,form){
      const message=state.messages[index];if(!message||busy.has(message))return;busy.add(message);
      try{
        if(kind.startsWith('start-')){
          const previous=state.messages.slice(0,index).reverse().find(m=>m.role==='user');
          const run=await request('',state.courseId,{id:'agent-'+crypto.randomUUID(),scenario:kind.slice(6),
            question:previous?.text||'根据当前课程准备学习',...(kind==='start-chapter'&&message.sources?.length?{sourceIds:message.sources.map(s=>s.id)}:{}),context:{examDate:state.examDate,minutes:state.minutes}});
          update(message,run);return;
        }
        const run=message.agentRun;if(!run)return;
        if(kind==='reload'){update(message,await request('/'+encodeURIComponent(run.id),run.courseId));return;}
        let body={revision:run.revision},endpoint=kind;
        if(kind==='confirm')Object.assign(body,{confirmed:true,digest:run.interaction.digest});
        if(kind==='unknown'){endpoint='resume';body.acknowledgeUnknown=Boolean(new FormData(form).get('acknowledge'));}
        if(kind==='resume'&&form)body.userInput=new FormData(form).get('userInput');
        if(kind==='diagnose')Object.assign(body,{confirmed:true,cause:new FormData(form).get('cause'),reason:new FormData(form).get('reason')});
        if(kind==='replan'){const data=new FormData(form);body.settings={minutes:Number(data.get('minutes')),...(data.get('examDate')?{examDate:data.get('examDate')}:{})};}
        if(kind==='answer'){
          const data=new FormData(form);body.responses=run.interaction.quiz.questions.map((q,i)=>({questionId:q.id,
            answer:q.type==='single'?Number(data.get('q'+i)):q.type==='multiple'?data.getAll('q'+i).map(Number):q.type==='boolean'?data.get('q'+i)==='true':q.type==='fill'?Array.from({length:q.blankCount},(_,j)=>data.get(`q${i}-${j}`)):data.get('q'+i),reasoning:data.get('reason'+i)||''}));
        }
        update(message,await request('/'+encodeURIComponent(run.id)+'/'+endpoint,run.courseId,body));
      }catch(error){toast(({RUN_CONFLICT:'任务已更新，请先更新状态再操作。',LEARNING_STATE_CHANGED:'学习记录已更新，请重新预览后确认。',STALE_EVIDENCE:'资料已变化，请基于新资料开始新任务。',AGENT_DISABLED:'持续学习功能暂未启用，原有问答可继续使用。',AGENT_INTERACTIVE_DISABLED:'交互学习暂未启用。'}[error.code])||'操作未完成，请更新状态后重试。');}
      finally{busy.delete(message);}
    }
    return{refresh(){for(const message of state.messages)if(['queued','running'].includes(message.agentRun?.status))watch(message);},mount(){if(mounted)return;mounted=true;
      document.addEventListener('click',event=>{const b=event.target.closest('[data-agent-action]');if(b)void action(Number(b.dataset.agentIndex),b.dataset.agentAction);});
      document.addEventListener('submit',event=>{const form=event.target.closest('[data-agent-form]');if(form){event.preventDefault();void action(Number(form.dataset.agentIndex),form.dataset.agentForm,form);}});
      for(const message of state.messages)if(['queued','running'].includes(message.agentRun?.status))watch(message);
      if(root.XueyaPlatform?.available)request('/features',state.courseId).then(features=>{state.agentFeatures=features;render();}).catch(()=>{});
    }};
  }
  root.XueyaAgentRuns={create,markup};
})(globalThis);
