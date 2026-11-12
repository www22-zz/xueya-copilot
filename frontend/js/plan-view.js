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
          showCreateModal = false;formDraft=null;
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

    async function toggleTask(planId, taskId, currentStatus) {
      try {
        const headers = { 'Content-Type': 'application/json' };
        const res = await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/task/toggle', {
          method: 'POST',
          headers,
          body: JSON.stringify({ planId, taskId, completed: !currentStatus, expectedRevision:activePlan.revision, operationId:'complete-'+taskId+'-'+activePlan.revision+'-'+!currentStatus })
        });
        const data = await res.json();
        if (data.ok) {
          toast(!currentStatus ? '任务已完成！' : '已重置任务状态');
          await loadPlans();
        }
      } catch (error) { toast(error.message || '学习操作未完成'); }
    }

    async function delayTask(planId, taskId) {
      const newDate = prompt('请输入顺延的目标日期（格式 YYYY-MM-DD）：');
      if (!newDate || !/^\d{4}-\d{2}-\d{2}$/.test(newDate.trim())) return;
      try {
        const headers = { 'Content-Type': 'application/json' };
        const res = await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/task/delay', {
          method: 'POST',
          headers,
          body: JSON.stringify({ planId, taskId, newDate: newDate.trim(),expectedRevision:activePlan.revision,operationId:'delay-'+taskId+'-'+activePlan.revision+'-'+newDate.trim() })
        });
        const data = await res.json();
        if (data.ok) {
          toast('任务已成功调整到 ' + newDate.trim());
          await loadPlans();
        } else {
          toast('顺延失败：' + (data.error === 'CANNOT_DELAY_TO_REST_DAY' ? '目标日期为设定休息日' : '超出计划周期范围'));
        }
      } catch (error) { toast(error.message || '学习操作未完成'); }
    }

    async function previewAdjustment(formData) {
      try {
        loading=true;
        const response=await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/adjust-preview',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({planId:activePlan.id,expectedRevision:activePlan.revision,operationId:crypto.randomUUID(),
            dailyMinutes:formData.dailyMinutes,endDate:formData.endDate,restDays:formData.restDays})});
        const data=await response.json();if(!data.ok)throw Error(data.error);
        showCreateModal=false;adjusting=false;await loadPlans();toast('调整草稿已保存，查看差异后采用生效。');
      } catch(error){toast(error.message);}
      finally{loading=false;render();}
    }
    async function addTaskLink(taskId) {
      const url=prompt('添加学习资源链接（仅 http/https，显示为用户提供、未核验）：');if(!url)return;
      try {
        const response=await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/task/link',{
          method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({planId:activePlan.id,taskId,url,
            expectedRevision:activePlan.revision,operationId:crypto.randomUUID()})});
        const data=await response.json();if(!data.ok)throw Error(data.error);
        await loadPlans();toast('资源链接已保存');
      } catch(error){toast(error.message);}
    }
    function resourceLinks(task) {
      const links=[...(task.resource?.url?[task.resource]:[]),...(task.video?.url?[task.video]:[]),...(task.links||[])];
      return links.filter(link=>/^(#space\/|https?:\/\/)/.test(link.url||'')).map(link=>
        `<a class="button button-outline button-small" href="${e(link.url)}" ${link.type==='external'?'target="_blank" rel="noopener noreferrer"':''}>${e(link.title||'打开题目')}${link.type==='external'?'（用户链接，未核验）':''}</a>`).join('');
    }

    function render() {
      if (!container) return;
      if (loading) {
        container.innerHTML = '<div class="plan-loading">正在读取学习计划…</div>';
        return;
      }

      let allTasks = [];
      if (activePlan) {
        for (const d of activePlan.days || []) {
          allTasks.push(...(d.tasks || []));
        }
      }
      allTasks.push(...(activePlan?.completedHistory||[]));
      const doneCount = allTasks.filter(t => t.completed).length;
      const progressPercent = allTasks.length ? Math.round((doneCount / allTasks.length) * 100) : 0;

      container.innerHTML = `
        <div class="study-plan-container">
          <div class="plan-top-header">
            <div>
              <h2>${activePlan ? e(activePlan.title) : '我的学习计划'}</h2>
              <p>${activePlan ? e(activePlan.goal) + ' · 周期：' + e(activePlan.startDate) + ' 至 ' + e(activePlan.endDate) : '制定并执行个性化计算机考研与核心课程复习计划'}</p>
            </div>
            ${activePlan?'<button type="button" class="button button-outline button-small" data-adjust-plan>调整每日时间与日期</button>':''}
            <button type="button" class="button button-outline button-small" data-plan-connectivity>检查模型连接（不生成）</button>
            <button type="button" class="button button-blue button-small" data-open-create-plan>
              ＋ 制定新计划
            </button>
          </div>

          ${jobs.some(job=>['queued','running','cancelling','unknown','failed'].includes(job.status))?`<div class="panel" role="status">${jobs.filter(job=>['queued','running','cancelling','unknown','failed'].includes(job.status)).map(job=>`<p>${['unknown','failed'].includes(job.status)?e(failureText(job)):'计划生成：'+e(({queued:'等待处理',running:'生成中',cancelling:'正在取消'})[job.status])+' '+e(job.progress?.label||'')}</p>`).join('')}</div>`:''}
          ${activePlan ? `
            ${activePlan.frameworkStatus==='failed'?'<p>当前计划已采用并可执行；关联导图未完成，原失败记录保留，不会自动重新生成。</p>':''}
          <div class="plan-stats-panel panel">
              <div class="plan-stat-bar">
                <span>辅助任务清单进度：<strong>${doneCount} / ${allTasks.length} 项任务</strong> (${progressPercent}%)</span>
                <span>每日预算：${e(activePlan.dailyMinutes)} 分钟 · 保留历史完成 ${(activePlan.completedHistory||[]).length} 项</span>
              </div>
              <div class="plan-progress-track">
                <div class="plan-progress-fill" style="width: ${progressPercent}%;"></div>
              </div>
            </div>

            ${activePlan.completedHistory?.length?`<details class="panel"><summary>此前完成记录 (${activePlan.completedHistory.length})</summary>${activePlan.completedHistory.map(t=>`<p>${e(t.date||t.originalDate)} · ${e(t.title)} · 已完成${resourceLinks(t)}</p>`).join('')}</details>`:''}
            <div data-learning-route="${e(activePlan.id)}"></div><details><summary>日历与任务清单（辅助视图）</summary><div class="plan-days-list">
              ${(activePlan.days || []).map(day => `
                <div class="plan-day-card panel ${day.isRestDay ? 'is-rest-day' : ''}">
                  <div class="plan-day-head">
                    <span class="day-date">📅 ${e(day.date)} (周${['一','二','三','四','五','六','日'][day.weekday-1]})</span>
                    <span class="day-badge">${day.isRestDay ? '☕ 休息日' : '每日 ' + e(day.budgetMinutes) + ' 分钟'}</span>
                  </div>
                  <div class="plan-day-tasks">
                    ${day.tasks?.length ? day.tasks.map(t => `
                      <div class="plan-task-row ${t.completed ? 'is-done' : ''}">
                        <label class="task-checkbox-label">
                          <input type="checkbox" ${t.completed ? 'checked' : ''} data-toggle-task="${e(t.id)}">
                          <span class="task-title-text">${e(t.title)}</span>
                        </label>
                        <div class="task-actions-group">
                          <span class="task-minutes">${e(t.phase||'学习')} · ${e(t.minutes)} 分钟</span>${resourceLinks(t)}<button type="button" class="button button-outline button-small" data-task-link="${e(t.id)}">添加链接</button>
                          ${t.delayCount > 0 ? `<span class="task-delay-tag">已顺延 ${t.delayCount} 次</span>` : ''}
                          ${!t.completed ? `<button type="button" class="button button-outline button-small" data-delay-task="${e(t.id)}">顺延</button>` : ''}
                        </div>
                      </div>
                    `).join('') : '<p class="day-empty-hint">当日无安排任务，合理休息调节。</p>'}
                  </div>
                </div>
              `).join('')}
            </div></details>
          ` : `
            <div class="plan-empty panel">
              <h3>暂无正在执行的学习计划</h3>
              <p>点击上方「＋ 制定新计划」，输入目标和每日可用时间，AI 将自动为你排程。</p>
            </div>
          `}

          ${drafts.length ? `
            <div class="plan-section-drafts panel">
              <h3>待采用计划草稿 (${drafts.length})</h3>
              ${drafts.map(d => `
                <div class="draft-row">
                  <div>
                    <strong>${e(d.title)}</strong> - <small>${e(d.goal)} · ${d.daysCount}天</small>
                    <div data-learning-route="${e(d.id)}"></div><details class="plan-draft-preview"><summary>查看说明与每日安排</summary>
                      <p>${e(d.explanation)}</p><p>已安排 ${(d.days||[]).filter(day=>day.tasks?.length).length} 个学习日 / ${(d.days||[]).filter(day=>!day.isRestDay).length} 个可学习日，合计 ${(d.days||[]).reduce((sum,day)=>sum+(day.tasks||[]).reduce((n,t)=>n+t.minutes,0),0)} 分钟；${(d.days||[]).filter(day=>!day.isRestDay&&!day.tasks?.length).length} 个非休息日尚无任务。</p>${d.frameworkId?`<a href="#space/frameworks/${e(d.frameworkId)}">${d.frameworkCoverage?.partial?'打开资料关联局部图（'+e(d.frameworkCoverage.representedPhases)+'/'+e(d.frameworkCoverage.totalPhases)+'阶段）':'打开关联知识框架'}</a>`:d.frameworkStatus==='failed'?'<p>计划排程已保存，可以采用；关联导图未完成，不会自动重新调用AI。</p>':d.generationStatus?'<p>计划及关联导图仍在处理中，请等待当前作业结束。</p>':''}
                      ${d.changePreview?`<p>调整预览：每日 ${e(d.changePreview.dailyMinutes.before)} → ${e(d.changePreview.dailyMinutes.after)} 分钟；截止 ${e(d.changePreview.endDate.before)} → ${e(d.changePreview.endDate.after)}；保留已完成 ${d.changePreview.retainedCompleted} 项。采用前原计划继续执行。</p>`:''}
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
                  <label class="form-field" style="flex:1;">每日可用时间 (分钟)
                    <input type="number" name="dailyMinutes" min="15" max="480" value="${adjusting?activePlan.dailyMinutes:formDraft?.dailyMinutes||60}" required>
                  </label>
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
      container.querySelectorAll("[data-learning-route]").forEach(host=>{const plan=[activePlan,...drafts].find(p=>p?.id===host.dataset.learningRoute);if(plan)window.XueyaLearningRoute.mount(host,plan);});
    }

    function bindEvents() {
      container.querySelector('[data-adjust-plan]')?.addEventListener('click',()=>{adjusting=true;showCreateModal=true;render();});
      container.querySelectorAll('[data-task-link]').forEach(button=>button.onclick=()=>addTaskLink(button.dataset.taskLink));
      container.querySelector('[data-plan-connectivity]')?.addEventListener('click',async event=>{
        const button=event.currentTarget;button.disabled=true;
        try{const response=await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/connectivity');const value=await response.json();toast(value.ok?(value.connected===true?'模型站点连接正常；本次没有生成计划或调用推理接口。':'当前为受控测试模型，未验证外部连接。'):errorText(value.error));}
        catch{toast('连接检查未完成，请检查本地服务。');}finally{if(button.isConnected)button.disabled=false;}
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
          dailyMinutes: Number(fd.get('dailyMinutes')),
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

      container.querySelectorAll('[data-toggle-task]').forEach(chk => {
        chk.addEventListener('change', () => {
          if (activePlan) {
            toggleTask(activePlan.id, chk.dataset.toggleTask, !chk.checked);
          }
        });
      });

      container.querySelectorAll('[data-delay-task]').forEach(btn => {
        btn.addEventListener('click', () => {
          if (activePlan) {
            delayTask(activePlan.id, btn.dataset.delayTask);
          }
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
