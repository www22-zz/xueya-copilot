/* Sidebar learning hub: current course, resume learning, today's plan tasks, recent-chat entry.
   Reads only existing workspace state and the existing /api/learning/space endpoints. */
(() => {
  'use strict';

  const CN_DATE = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' });
  const todayKey = () => CN_DATE.format(new Date());
  const escape = value => (window.XueyaRich?.escape ? window.XueyaRich.escape(String(value ?? '')) : String(value ?? ''));
  const text = (selector, value) => {
    const node = document.querySelector(selector);
    if (node) node.textContent = value;
  };

  function create({ state, store, toast, platform }) {
    let plan = null;
    let planLoaded = false;
    let planFailed = false;
    let planAt = 0;
    let planRequest = null;
    let resume = null;
    let resumeAt = 0;

    const available = () => Boolean(platform?.available);

    function currentCourse() {
      return (store?.courses || []).find(course => course.id === state.courseId) || null;
    }

    function documentCount() {
      if (Number.isInteger(state.documentCount)) return state.documentCount;
      return (state.documents || []).filter(doc => !doc.superseded && !doc.archived).length;
    }

    function syncSpaceCard() {
      const name = currentCourse()?.name || '数据结构';
      text('#stitchSpaceName', name);
      text('#stitchSpaceInitial', Array.from(name)[0] || '学');
      text('#stitchSpaceMeta', documentCount() + ' 份资料');
    }

    function syncResume() {
      const link = document.querySelector('#stitchResumeLink');
      if (!link) return;
      const title = document.querySelector('#stitchResumeTitle');
      const label = document.querySelector('#stitchResumeLabel');
      if (resume?.url) {
        link.href = resume.url;
        if (title) title.textContent = resume.title || '继续上次学习';
        if (label) label.textContent = '继续上次学习';
        link.dataset.hasResume = 'true';
      } else {
        link.href = '#space/courses';
        if (title) title.textContent = '打开课程学习中心';
        if (label) label.textContent = '开始学习';
        delete link.dataset.hasResume;
      }
    }

    async function loadResume(force) {
      if (!available()) {
        syncResume();
        return;
      }
      if (!force && Date.now() - resumeAt < 30000) return;
      try {
        const response = await platform.spaceFetch('/api/learning/space/today');
        const data = await response.json();
        resume = data?.lastCourse || null;
        resumeAt = Date.now();
      } catch {
        /* Keep the local fallback; the sidebar must never block the page. */
      }
      syncResume();
    }

    function planLink(label) {
      return escape(label) + '<span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span>';
    }

    function renderPlan() {
      const section = document.querySelector('#stitchTodaySection');
      const tasksNode = document.querySelector('#stitchTodayTasks');
      const countNode = document.querySelector('#stitchTodayCount');
      const link = document.querySelector('#stitchTodayPlanLink');
      if (!section || !tasksNode || !countNode || !link) return;
      if (state.view !== 'overview' || !available()) {
        section.hidden = true;
        return;
      }
      section.hidden = false;
      link.href = '#space/analysis/plans';

      if (!planLoaded) {
        countNode.textContent = '…';
        tasksNode.innerHTML = '<p class="sidebar-empty"><strong>正在同步今日计划</strong>马上就好。</p>';
        link.innerHTML = planLink('打开学习计划');
        return;
      }
      if (planFailed) {
        countNode.textContent = '—';
        tasksNode.innerHTML = '<p class="sidebar-empty"><strong>今日计划暂未同步</strong>学习服务暂时不可用。<button type="button" class="sidebar-inline-action" data-sidebar-retry-plan>重新同步</button></p>';
        link.innerHTML = planLink('打开学习计划');
        return;
      }
      if (!plan) {
        countNode.textContent = '0/0';
        tasksNode.innerHTML = '<p class="sidebar-empty"><strong>还没有学习计划</strong>先定一个今天能完成的小目标。</p>';
        link.innerHTML = planLink('制定学习计划');
        return;
      }
      const day = (plan.days || []).find(item => item.date === todayKey());
      const tasks = Array.isArray(day?.tasks) ? day.tasks : [];
      if (!tasks.length) {
        countNode.textContent = '0/0';
        tasksNode.innerHTML = '<p class="sidebar-empty"><strong>今天没有安排任务</strong>可以提前看看后续安排。</p>';
        link.innerHTML = planLink('查看完整计划');
        return;
      }
      const done = tasks.filter(task => task.completed).length;
      countNode.textContent = done + '/' + tasks.length;
      tasksNode.innerHTML = tasks.slice(0, 4).map(task => (
        '<label class="sidebar-task' + (task.completed ? ' is-done' : '') + '">' +
          '<input type="checkbox" data-sidebar-task="' + escape(task.id) + '"' + (task.completed ? ' checked' : '') + '>' +
          '<span class="sidebar-task-copy">' +
            '<span class="sidebar-task-title">' + escape(task.title) + '</span>' +
            '<span class="sidebar-task-meta">' + (Number(task.minutes) || 0) + ' 分钟' + (task.completed ? ' · 已完成' : '') + '</span>' +
          '</span>' +
        '</label>'
      )).join('');
      link.innerHTML = planLink('查看完整计划');
    }

    function loadPlan(force) {
      if (!available()) {
        planLoaded = true;
        renderPlan();
        return Promise.resolve();
      }
      if (!force && planLoaded && Date.now() - planAt < 8000) {
        renderPlan();
        return Promise.resolve();
      }
      if (planRequest) return planRequest;
      planRequest = (async () => {
        try {
          const response = await platform.spaceFetch('/api/learning/space/plan/active');
          const data = await response.json();
          plan = data?.plan || null;
          planFailed = false;
        } catch {
          planFailed = true;
        } finally {
          planLoaded = true;
          planAt = Date.now();
          planRequest = null;
          renderPlan();
        }
      })();
      return planRequest;
    }

    async function toggleTask(input) {
      if (!plan?.id) return;
      const taskId = input.dataset.sidebarTask;
      input.disabled = true;
      try {
        const response = await platform.spaceFetch('/api/learning/space/plan/task/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            planId: plan.id,
            taskId,
            completed: input.checked,
            expectedRevision: plan.revision,
            operationId: 'sidebar-' + taskId + '-' + plan.revision + '-' + input.checked,
          }),
        });
        const value = await response.json();
        if (value?.plan) plan = value.plan;
        planLoaded = true;
        planFailed = false;
        planAt = Date.now();
        renderPlan();
        toast?.('已同步到我的计划');
      } catch (error) {
        input.checked = !input.checked;
        input.disabled = false;
        toast?.(error?.message || '任务同步失败，请稍后重试');
      }
    }

    function handleClick(event) {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest('[data-sidebar-retry-plan]')) {
        event.preventDefault();
        planLoaded = false;
        planFailed = false;
        void loadPlan(true);
        return;
      }
      const recentSession = target.closest('#stitchRecentSessions .session-item-btn');
      if (recentSession && state.view === 'overview') {
        setTimeout(() => {
          if (location.hash !== '#space/ask') location.hash = 'space/ask';
        }, 0);
      }
    }

    function handleChange(event) {
      const target = event.target instanceof Element ? event.target : null;
      const input = target?.closest('[data-sidebar-task]');
      if (input) void toggleTask(input);
    }

    document.addEventListener('click', handleClick);
    document.addEventListener('change', handleChange);

    function sync(view) {
      syncSpaceCard();
      syncResume();
      const section = document.querySelector('#stitchTodaySection');
      if (view !== 'overview') {
        if (section) section.hidden = true;
        return;
      }
      renderPlan();
      if (available()) {
        void loadPlan(false);
        void loadResume(false);
      }
    }

    return { sync };
  }

  window.XueyaSidebarHub = { create };
})();
