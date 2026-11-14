/* Xueya Study Plan Workspace UI (Section 8).
   Single active execution plan per account, multiple drafts, history, constraint schedule. */
(function(root) {
  'use strict';
  const e = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function createPlanUI({ toast = () => {}, navigate = () => {} } = {}) {
    let container = null;
    let generation = 0;
    let activePlan = null;
    let drafts = [];
    let history = [];
    let selectedView = 'current', requestLogOpen = false, connectionCheck = null;
    let loading = false;
    let showCreateModal = false;
    let adjusting = false;
    let jobs=[],pollTimer;
    let availableSubjects=[],formDraft=null;
    const pendingKey=()=> (root.XueyaDataKey||((key)=>key))('xueya-plan-pending');
    let pendingRequests={};
    try{
      const saved=JSON.parse(sessionStorage.getItem(pendingKey())||'{}');
      if(saved&&typeof saved==='object'&&!Array.isArray(saved))pendingRequests=saved;
      const last=Object.values(pendingRequests).at(-1);
      if(last&&typeof last.goal==='string'&&typeof last.operationId==='string'){
        const {operationId,...conditions}=last;formDraft=conditions;
      }
    }catch{}
    const savePending=()=>{try{sessionStorage.setItem(pendingKey(),JSON.stringify(pendingRequests));}catch{}};
    const failureText=job=>job.checkpoint?.stage==='framework'&&job.checkpoint?.planId?'学习计划已保存，关联导图生成未完成；可先核对并采用计划，不会自动重新调用AI。':job.diagnosticCode==='AI_PLAN_RESPONSE_TIMEOUT'||['AI_PLAN_RESPONSE_TIMEOUT','JOB_TIMEOUT'].includes(job.error)?'模型响应超时，未生成可用计划。该请求的结果与费用仍待核对，不会自动重试。':job.diagnosticCode==='AI_CONNECTION_FAILED'||job.error==='AI_CONNECTION_FAILED'?'连接模型服务失败，未拿到可用结果。请先检查连接；历史调用费用待核对，不会自动重试。':job.error==='AI_INVALID_RESPONSE'?'模型返回格式未通过校验，未完成计划；不会自动重试。':'生成未完成，结果与费用待核对，不会自动重试。';
    const errorText=code=>({AI_CONNECTION_FAILED:'当前后台无法连接模型站点，本次未提交新的计划作业。请检查网络、代理及服务启动环境。',AI_UNAVAILABLE:'尚未配置可用模型，请检查服务设置。'}[code]||code||'操作未完成');

    async function loadPlans() {
      const stamp=generation;
      try {
        loading = true;
        const headers = {  };
        const res = await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/list', { headers });
        const data = await res.json();
        if(stamp!==generation)return;
        if (data.ok) {
          activePlan = data.active;
          drafts = data.drafts || [];
          history = data.history || [];jobs=data.jobs||[];
          try{const response=await window.XueyaPlatform.spaceFetch('/api/learning/space/materials');const catalog=await response.json();availableSubjects=[...new Set((catalog.materials||[]).filter(m=>m.ready).map(m=>m.subject))];}catch{}
        }
      } catch (error) { toast(error.message || '学习操作未完成'); }
      finally {
        if(stamp===generation){loading=false;render();clearTimeout(pollTimer);if(jobs.some(job=>['queued','running','cancelling'].includes(job.status)))pollTimer=setTimeout(loadPlans,2000);}
      }
    }

    async function createDraft(formData) {
      if(loading)return;
      formDraft=formData;
      const signature=JSON.stringify(formData);
      const request=pendingRequests[signature]||{...formData,operationId:crypto.randomUUID()};
      pendingRequests[signature]=request;savePending();
      try {
        loading = true;
        render();
        const headers = { 'Content-Type': 'application/json' };
        const res = await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/generate', {
          method: 'POST',
          headers,
          body: JSON.stringify(request)
        });
        const data = await res.json();
        if (data.ok) {
          toast('已提交后台生成作业，完成后核对草稿和知识框架，再明确采用。');
          showCreateModal = false;formDraft=null;selectedView='drafts';
          delete pendingRequests[signature];savePending();
          await loadPlans();
        } else {
          toast('生成草稿失败：' + errorText(data.error));
        }
      } catch {
        toast('提交回执未确认，请先核对作业列表；再次提交相同条件会复用原请求，不会另开一份作业。');
      } finally {
        loading = false;
        render();
      }
    }

    async function adopt(planId, expectedRevision) {
      if(loading)return;
      try {
        loading = true;
        render();
        const listing=await(await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/list')).json();
        if(!listing.ok)throw Error(listing.error||'SERVICE_UNAVAILABLE');
        const current=listing.active||null;
        if(current?.id===planId){toast('采用成功');await loadPlans();return;}
        const latest=(listing.drafts||[]).find(p=>p.id===planId);
        if(!latest)throw Error('PLAN_NOT_DRAFT');
        if(latest.revision!==expectedRevision)throw Error('PLAN_REVISION_CONFLICT');
        if(!confirm('确认采用“'+(latest.title||'这份草稿')+'”为当前执行计划吗？'+(current?'\n当前计划“'+(current.title||'未命名计划')+'”将转入历史，学习记录保留。':'')))return;
        const expectedCurrent=current?{id:current.id,revision:current.revision}:null;
        const headers = { 'Content-Type': 'application/json' };
        const res = await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/adopt', {
          method: 'POST',
          headers,
          body: JSON.stringify({ planId, expectedRevision, confirmed: true, expectedCurrent, operationId:'adopt-'+planId+'-'+expectedRevision+'-'+(current?current.id+'-'+current.revision:'none') })
        });
        const data = await res.json();
        if (data.ok) {
          toast('采用成功');
          selectedView='current';
          await loadPlans();
        } else {
          throw Error(data.error||'PLAN_REVISION_CONFLICT');
        }
      } catch(error) {
        const message={PLAN_CURRENT_CHANGED:'当前执行计划刚刚发生变化，本次未替换。请再次点击采用并核对。',PLAN_REVISION_CONFLICT:'草稿已更新，请刷新后重新核对。',PLAN_NOT_DRAFT:'该草稿的状态已变化，请刷新后核对。'}[error.code||error.message]||errorText(error.code||error.message);
        toast('采用未完成：'+message);
      } finally {
        loading = false;
        render();
      }
    }

    async function previewAdjustment(formData) {
      try {
        loading=true;
        const response=await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/adjust-preview',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({planId:activePlan.id,expectedRevision:activePlan.revision,operationId:crypto.randomUUID(),
            schedulingMode:'by-days',endDate:formData.endDate,restDays:formData.restDays})});
        const data=await response.json();if(!data.ok)throw Error(data.error);
        showCreateModal=false;adjusting=false;selectedView='drafts';await loadPlans();toast('调整草稿已保存，查看差异后采用生效。');
      } catch(error){toast(error.message);}
      finally{loading=false;render();}
    }
    function resourceLinks(task) {
      const links=[...(task.resource?.url?[task.resource]:[]),...(task.video?.url?[task.video]:[]),...(task.links||[])];
      return links.filter(link=>/^(#space\/|https?:\/\/)/.test(link.url||'')).map(link=>
        `<a class="button button-outline button-small" href="${e(link.url)}" ${link.type==='external'?'target="_blank" rel="noopener noreferrer"':''}>${e(link.title||'打开题目')}${link.type==='external'?'（用户链接，未核验）':''}</a>`).join('');
    }

    function requestTime(value) {
      if (!value) return '未记录';
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? '未记录' : date.toLocaleString('zh-CN', {hour12:false});
    }

    function requestLog() {
      const names = {queued:'等待处理',running:'生成中',cancelling:'正在取消',succeeded:'已完成',failed:'失败',unknown:'结果待核对',cancelled:'已取消'};
      const records = [...jobs].sort((a,b)=>(Date.parse(b.createdAt)||0)-(Date.parse(a.createdAt)||0));
      return `<details class="plan-request-log panel" ${requestLogOpen?'open':''}>
        <summary>AI 请求记录与连接检查 <span>${records.length} 条记录</span></summary>
        <div class="plan-connection-tools">
          <button type="button" class="button button-outline button-small" data-plan-connectivity>检查模型连接（不生成）</button>
          <p data-plan-connection-result role="status">${connectionCheck?e(connectionCheck.message)+' · 检查时间 '+e(requestTime(connectionCheck.at)):'按需检查连接；下方记录保留每次计划生成请求的状态。'}</p>
        </div>
        <p class="plan-request-note">时间按本机时区显示；状态更新时间为后台最后记录时间。未记录的时间不会补写。</p>
        <div class="plan-request-list">${records.map(job=>`<article class="plan-request-row">
          <div class="plan-request-heading"><strong>计划生成请求</strong><span class="plan-request-badge">${e(names[job.status]||job.status)}</span></div>
          <div class="plan-request-times"><span>提交：${e(requestTime(job.createdAt))}</span><span>状态更新：${e(requestTime(job.updatedAt))}</span></div>
          <p>${['failed','unknown'].includes(job.status)?e(failureText(job)):e(job.progress?.label||names[job.status]||'')}</p>
          <small>请求编号：${e(job.id)}</small>
        </article>`).join('')||'<p>暂无计划生成请求记录。</p>'}</div>
      </details>`;
    }

    function render() {
      if (!container) return;
      if (loading) {
        container.innerHTML = '<div class="plan-loading">正在读取学习计划…</div>';
        return;
      }

      container.innerHTML = `
        <div class="study-plan-container">
          <div class="plan-top-header">
            <div>
              <h2>我的学习计划</h2>
              <p>查看当前安排，或切换到草稿与历史计划。</p>
            </div>
            ${activePlan&&selectedView==='current'?'<button type="button" class="button button-outline button-small" data-adjust-plan>调整学习周期与休息日</button>':''}
            <button type="button" class="button button-blue button-small" data-open-create-plan>
              ＋ 制定新计划
            </button>
          </div>

          <nav class="plan-view-tabs" aria-label="计划分类">
            ${[['current','当前计划',activePlan?1:0],['drafts','待采用草稿',drafts.length],['history','历史计划',history.length]].map(([key,label,count])=>`<button type="button" class="button button-small" data-plan-view="${key}" aria-pressed="${selectedView===key}">${label}<span>${count}</span></button>`).join('')}
          </nav>
          <section class="plan-view-panel" aria-label="当前计划" ${selectedView==='current'?'':'hidden'}>
          ${jobs.some(job=>['queued','running','cancelling'].includes(job.status))?'<p class="plan-running-note" role="status">有计划正在生成，可在页底「AI 请求记录与连接检查」查看进度。</p>':''}
          ${activePlan ? `
            ${activePlan.frameworkStatus==='failed'?'<p>当前计划已采用并可执行；关联导图未完成，原失败记录保留，不会自动重新生成。</p>':''}
            <div data-learning-route="${e(activePlan.id)}"></div>
          ` : `
            <div class="plan-empty panel">
              <h3>暂无正在执行的学习计划</h3>
              <p>点击上方「＋ 制定新计划」，输入目标和每日可用时间，AI 将自动为你排程。</p>
            </div>
          `}

          </section>
          <section class="plan-view-panel" aria-label="待采用草稿" ${selectedView==='drafts'?'':'hidden'}>
          ${drafts.length ? `
            <div class="plan-section-drafts panel">
              <h3>待采用计划草稿 (${drafts.length})</h3>
              ${drafts.map(d => `
                <div class="draft-row">
                  <div>
                    <div class="plan-draft-heading"><strong>${e(d.title)}</strong> - <small>${e(d.goal)} · ${d.daysCount}天</small></div>
                    <div data-learning-route="${e(d.id)}"></div><details class="plan-draft-preview"><summary>查看说明与每日安排</summary>
                      <p>${e(d.explanation)}</p><p>已安排 ${(d.days||[]).filter(day=>day.tasks?.length).length} 个学习日 / ${(d.days||[]).filter(day=>!day.isRestDay).length} 个可学习日，合计 ${(d.days||[]).reduce((sum,day)=>sum+(day.tasks||[]).reduce((n,t)=>n+t.minutes,0),0)} 分钟；${(d.days||[]).filter(day=>!day.isRestDay&&!day.tasks?.length).length} 个非休息日尚无任务。</p>${d.frameworkId?`<a href="#space/frameworks/${e(d.frameworkId)}">${d.frameworkCoverage?.partial?'打开资料关联局部图（'+e(d.frameworkCoverage.representedPhases)+'/'+e(d.frameworkCoverage.totalPhases)+'阶段）':'打开关联知识框架'}</a>`:d.frameworkStatus==='failed'?'<p>计划排程已保存，可以采用；关联导图未完成，不会自动重新调用AI。</p>':d.generationStatus?'<p>计划及关联导图仍在处理中，请等待当前作业结束。</p>':''}
                      ${d.changePreview?`<p>调整预览：日均预计 ${e(d.changePreview.dailyMinutes.before)} → ${e(d.changePreview.dailyMinutes.after)} 分钟；截止 ${e(d.changePreview.endDate.before)} → ${e(d.changePreview.endDate.after)}；保留已完成 ${d.changePreview.retainedCompleted} 项。采用前原计划继续执行。</p>`:''}
                      ${(d.days||[]).map(day=>`<p><strong>${e(day.date)}</strong> · ${day.isRestDay?'休息日':e(day.budgetMinutes)+' 分钟'}<br>${(day.tasks||[]).map(t=>e(t.title)+'（'+e(t.minutes)+' 分钟）'+resourceLinks(t)).join('<br>')||'无任务'}</p>`).join('')}
                      ${d.remaining?.length?`<p>时间不足，另有 ${d.remaining.length} 项任务尚未排入。请增加天数或每日时间后重新生成。</p>`:''}
                    </details>
                  </div>
                  <button type="button" class="button button-blue button-small" data-adopt-draft="${e(d.id)}" data-rev="${d.revision}" ${d.canAdopt===false||(d.canAdopt===undefined&&d.generationStatus&&d.generationStatus!=='completed')?'disabled':''}>
                    采用此计划
                  </button>
                </div>
              `).join('')}
            </div>
          ` : ''}

          ${!drafts.length?'<div class="plan-empty panel"><h3>暂无待采用草稿</h3><p>制定新计划后，可在这里核对并采用。</p></div>':''}
          </section>
          <section class="plan-view-panel" aria-label="历史计划" ${selectedView==='history'?'':'hidden'}>
          ${!history.length?'<div class="plan-empty panel"><h3>暂无历史计划</h3><p>采用新计划后，被替换的计划会保留在这里。</p></div>':''}
          ${history.length ? `
            <div class="plan-section-history panel">
              <h3>历史计划 (${history.length})</h3>
              ${history.map(h => `
                <div class="history-plan-row">
                  <details><summary>${e(h.title)} (${e(h.startDate)} ~ ${e(h.endDate)})</summary>${[...(h.completedHistory||[]),...(h.days||[]).flatMap(day=>(day.tasks||[]).map(t=>({...t,date:day.date})))].map(t=>`<p>${e(t.date||t.originalDate)} · ${e(t.title)} · ${t.completed?'已完成':'未完成'}${resourceLinks(t)}</p>`).join('')}</details>
                  <span class="history-badge">已归档</span>
                </div>
              `).join('')}
            </div>
          ` : ''}
          </section>
          ${requestLog()}
        </div>

        ${showCreateModal ? `
          <div class="modal-backdrop">
            <div class="modal-card panel">
              <h3>${adjusting?'调整当前计划（先预览）':'制定新学习计划'}</h3>
              <form id="createPlanForm">
                ${!adjusting?`<label class="form-field">选择学科 / 专题（可多选）<select name="subjects" multiple required>${availableSubjects.map(s=>`<option value="${e(s)}" ${(formDraft?.subjects||[]).includes(s)?'selected':''}>${e(s)}</option>`).join('')}</select></label><label class="form-field">难度<select name="difficulty">${['基础','进阶','挑战'].map(d=>`<option ${formDraft?.difficulty===d?'selected':''}>${d}</option>`).join('')}</select></label><label class="form-field">开始日期<input type="date" name="startDate" required value="${e(formDraft?.startDate||new Date().toLocaleDateString('en-CA'))}"></label><label class="form-field">结束日期<input type="date" name="endDate" required value="${e(formDraft?.endDate||'')}"></label>`:''}
                <label class="form-field">计划名称
                  <input name="title" required value="${e(adjusting?activePlan.title:formDraft?.title||'我的个性化学习计划')}" ${adjusting?'readonly':''}>
                </label>
                <label class="form-field">学习目标
                  <textarea name="goal" rows="2" required ${adjusting?'readonly':''}>${e(adjusting?activePlan.goal:formDraft?.goal||'完成所选科目与专题的学习和练习')}</textarea>
                </label>
                <div class="form-row" style="display:flex;gap:12px;">
                  <p>按可学习天数均分全部待完成任务，每天显示预计耗时；休息日不安排任务。</p>
                  ${adjusting?`<label class="form-field" style="flex:1;">新的截止日期<input type="date" name="endDate" value="${e(activePlan.endDate)}" required></label>`:`<label class="form-field" style="flex:1;">持续天数<input type="number" name="daysCount" min="1" max="366" value="${e(formDraft?.daysCount||14)}" required></label>`}
                </div>
                <fieldset><legend>休息日</legend>${['一','二','三','四','五','六','日'].map((name,i)=>`<label><input type="checkbox" name="restDays" value="${i+1}" ${(adjusting?activePlan.restDays:formDraft?.restDays||[7]).includes(i+1)?'checked':''}>周${name} </label>`).join('')}</fieldset>
                <div class="modal-actions" style="display:flex;gap:12px;margin-top:16px;">
                  <button type="button" class="button button-outline" data-close-create-modal>取消</button>
                  <button type="submit" class="button button-blue">生成排程草稿</button>
                </div>
              </form>
            </div>
          </div>
        ` : ''}
      `;

      bindEvents();
      const routes=new Map();
      const workspace=container.querySelector('.study-plan-container');
      function focusRoute(target,focused){
        if(!focused&&!target.classList.contains('is-focused-route'))return;
        workspace.classList.toggle('is-day-focus',focused);
        workspace.querySelectorAll('.plan-focus-path,.is-focused-route').forEach(el=>el.classList.remove('plan-focus-path','is-focused-route'));
        workspace.classList.remove('plan-focus-path');
        if(focused){
          routes.forEach((ui,other)=>{if(other!==target)ui?.reset();});
          target.classList.add('is-focused-route');
          for(let el=target.parentElement;el&&workspace.contains(el);el=el.parentElement)el.classList.add('plan-focus-path');
        }
      }
      container.querySelectorAll('.plan-view-panel:not([hidden]) [data-learning-route]').forEach(target=>{
        const plan=[activePlan,...drafts].find(p=>p?.id===target.dataset.learningRoute);
        if(plan)routes.set(target,window.XueyaLearningRoute.mount(target,plan,{onFocusChange:focused=>focusRoute(target,focused),onPlanUpdate:fresh=>{if(activePlan?.id===fresh.id)activePlan=fresh;drafts=drafts.map(d=>d.id===fresh.id?fresh:d);}}));
      });
    }

    function bindEvents() {
      container.querySelectorAll('[data-plan-view]').forEach(button=>button.addEventListener('click',()=>{selectedView=button.dataset.planView;render();container.querySelector(`[data-plan-view="${selectedView}"]`)?.focus();}));
      container.querySelector('.plan-request-log')?.addEventListener('toggle',event=>{requestLogOpen=event.currentTarget.open;});
      container.querySelector('[data-adjust-plan]')?.addEventListener('click',()=>{adjusting=true;showCreateModal=true;render();});
      container.querySelector('[data-plan-connectivity]')?.addEventListener('click',async event=>{
        const button=event.currentTarget;button.disabled=true;
        const showResult=message=>{
          connectionCheck={message,at:new Date().toISOString()};
          const result=container?.querySelector('[data-plan-connection-result]');
          if(result)result.textContent=message+' · 检查时间 '+requestTime(connectionCheck.at);
        };
        try{const response=await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/connectivity');const value=await response.json();showResult(value.ok?(value.connected===true?'模型站点连接正常；本次没有生成计划。':'当前为受控测试模型，未验证外部连接。'):errorText(value.error));}
        catch{showResult('连接检查未完成，请检查本地服务。');}finally{if(button.isConnected)button.disabled=false;}
      });
      container.querySelector('[data-open-create-plan]')?.addEventListener('click', () => {
        adjusting=false;showCreateModal = true;
        render();
      });

      container.querySelector('[data-close-create-modal]')?.addEventListener('click', () => {
        showCreateModal = false;
        render();
      });

      container.querySelector('#createPlanForm')?.addEventListener('submit', (ev) => {
        ev.preventDefault();
        const fd = new FormData(ev.target);
        (adjusting?previewAdjustment:createDraft)({
          title: fd.get('title'),
          goal: fd.get('goal'),
          schedulingMode: 'by-days',
          daysCount: fd.get('startDate')&&fd.get('endDate')?Math.round((Date.parse(fd.get('endDate'))-Date.parse(fd.get('startDate')))/86400000)+1:Number(fd.get('daysCount')),endDate:fd.get('endDate'),
          ...(adjusting?{}:{startDate:fd.get('startDate'),subjects:fd.getAll('subjects'),difficulty:fd.get('difficulty')}),
          restDays: fd.getAll('restDays').map(Number)
        });
      });

      container.querySelectorAll('[data-adopt-draft]').forEach(btn => {
        btn.addEventListener('click', () => {
          adopt(btn.dataset.adoptDraft, Number(btn.dataset.rev));
        });
      });


    }

    async function mount(targetNode) {
      generation++;container = targetNode;
      await loadPlans();
    }

    return { mount, loadPlans, unmount(){generation++;clearTimeout(pollTimer);container=null;} };
  }

  root.XueyaPlan = { create: createPlanUI };
})(typeof globalThis !== 'undefined' ? globalThis : window);
