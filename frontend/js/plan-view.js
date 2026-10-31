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
          history = data.history || [];
        }
      } catch (error) { toast(error.message || '学习操作未完成'); }
      finally {
        loading = false;
        if(stamp===generation)render();
      }
    }

    async function createDraft(formData) {
      try {
        loading = true;
        render();
        const headers = { 'Content-Type': 'application/json' };
        const res = await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/draft', {
          method: 'POST',
          headers,
          body: JSON.stringify(formData)
        });
        const data = await res.json();
        if (data.ok) {
          toast('计划草稿已生成，请核对排程后点击采用！');
          showCreateModal = false;
          await loadPlans();
        } else {
          toast('生成草稿失败：' + (data.error || '参数有误'));
        }
      } catch {
        toast('网络异常，请重试');
      } finally {
        loading = false;
        render();
      }
    }

    async function adopt(planId, expectedRevision) {
      if (!confirm('确认将此草稿设定为当前执行计划吗？原有计划将自动转入历史。')) return;
      try {
        loading = true;
        render();
        const headers = { 'Content-Type': 'application/json' };
        const res = await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/adopt', {
          method: 'POST',
          headers,
          body: JSON.stringify({ planId, expectedRevision, confirmed: true })
        });
        const data = await res.json();
        if (data.ok) {
          toast('已成功采用为当前执行计划！');
          await loadPlans();
        } else {
          toast('采用失败：' + (data.error || '版本冲突'));
        }
      } catch {
        toast('网络异常，请重试');
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
          body: JSON.stringify({ planId, taskId, completed: !currentStatus })
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
          body: JSON.stringify({ planId, taskId, newDate: newDate.trim() })
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
      const doneCount = allTasks.filter(t => t.completed).length;
      const progressPercent = allTasks.length ? Math.round((doneCount / allTasks.length) * 100) : 0;

      container.innerHTML = `
        <div class="study-plan-container">
          <div class="plan-top-header">
            <div>
              <h2>${activePlan ? e(activePlan.title) : '我的学习计划'}</h2>
              <p>${activePlan ? e(activePlan.goal) + ' · 周期：' + e(activePlan.startDate) + ' 至 ' + e(activePlan.endDate) : '制定并执行个性化计算机考研与核心课程复习计划'}</p>
            </div>
            <button type="button" class="button button-blue button-small" data-open-create-plan>
              ＋ 制定新计划
            </button>
          </div>

          ${activePlan ? `
            <div class="plan-stats-panel panel">
              <div class="plan-stat-bar">
                <span>总完成进度：<strong>${doneCount} / ${allTasks.length} 项任务</strong> (${progressPercent}%)</span>
                <span>每日预算：${e(activePlan.dailyMinutes)} 分钟</span>
              </div>
              <div class="plan-progress-track">
                <div class="plan-progress-fill" style="width: ${progressPercent}%;"></div>
              </div>
            </div>

            <div class="plan-days-list">
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
                          <span class="task-minutes">${e(t.minutes)} 分钟</span>
                          ${t.delayCount > 0 ? `<span class="task-delay-tag">已顺延 ${t.delayCount} 次</span>` : ''}
                          ${!t.completed ? `<button type="button" class="button button-outline button-small" data-delay-task="${e(t.id)}">顺延</button>` : ''}
                        </div>
                      </div>
                    `).join('') : '<p class="day-empty-hint">当日无安排任务，合理休息调节。</p>'}
                  </div>
                </div>
              `).join('')}
            </div>
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
                    <details class="plan-draft-preview"><summary>查看说明与每日安排</summary>
                      <p>${e(d.explanation)}</p>
                      ${(d.days||[]).map(day=>`<p><strong>${e(day.date)}</strong> · ${day.isRestDay?'休息日':e(day.budgetMinutes)+' 分钟'}<br>${(day.tasks||[]).map(t=>e(t.title)+'（'+e(t.minutes)+' 分钟）').join('<br>')||'无任务'}</p>`).join('')}
                      ${d.remaining?.length?`<p>时间不足，另有 ${d.remaining.length} 项任务尚未排入。请增加天数或每日时间后重新生成。</p>`:''}
                    </details>
                  </div>
                  <button type="button" class="button button-blue button-small" data-adopt-draft="${e(d.id)}" data-rev="${d.revision}">
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
                  <span>${e(h.title)} (${e(h.startDate)} ~ ${e(h.endDate)})</span>
                  <span class="history-badge">已归档</span>
                </div>
              `).join('')}
            </div>
          ` : ''}
        </div>

        ${showCreateModal ? `
          <div class="modal-backdrop">
            <div class="modal-card panel">
              <h3>制定新学习计划</h3>
              <form id="createPlanForm">
                <label class="form-field">计划名称
                  <input name="title" required value="计算机考研基础强化计划">
                </label>
                <label class="form-field">学习目标
                  <textarea name="goal" rows="2" required>完成408数据结构、计组、操作系统与网络系统复习</textarea>
                </label>
                <div class="form-row" style="display:flex;gap:12px;">
                  <label class="form-field" style="flex:1;">每日可用时间 (分钟)
                    <input type="number" name="dailyMinutes" min="15" max="360" value="60" required>
                  </label>
                  <label class="form-field" style="flex:1;">持续天数
                    <input type="number" name="daysCount" min="1" max="366" value="14" required>
                  </label>
                </div>
                <fieldset><legend>休息日</legend>${['一','二','三','四','五','六','日'].map((name,i)=>`<label><input type="checkbox" name="restDays" value="${i+1}" ${i===6?'checked':''}>周${name} </label>`).join('')}</fieldset>
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
    }

    function bindEvents() {
      container.querySelector('[data-open-create-plan]')?.addEventListener('click', () => {
        showCreateModal = true;
        render();
      });

      container.querySelector('[data-close-create-modal]')?.addEventListener('click', () => {
        showCreateModal = false;
        render();
      });

      container.querySelector('#createPlanForm')?.addEventListener('submit', (ev) => {
        ev.preventDefault();
        const fd = new FormData(ev.target);
        createDraft({
          title: fd.get('title'),
          goal: fd.get('goal'),
          dailyMinutes: Number(fd.get('dailyMinutes')),
          daysCount: Number(fd.get('daysCount')),
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

    return { mount, loadPlans, unmount(){generation++;container=null;} };
  }

  root.XueyaPlan = { create: createPlanUI };
})(typeof globalThis !== 'undefined' ? globalThis : window);
