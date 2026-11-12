/* Figma Make's learning orbit, adapted to persisted platform plans.
   Rendering is local; it never generates questions or changes completion. */
(() => {
  'use strict';
  const e = window.XueyaRich.escape;
  const icons = {
    spark: '<path d="m12 3 1.4 4.1 4.1 1.4-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4Z"/><path d="m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7Z"/>',
    calendar: '<path d="M8 2v4M16 2v4M3 10h18"/><rect x="3" y="4" width="18" height="18" rx="3"/>',
    play: '<path d="m9 7 8 5-8 5Z"/>',
    pending: '<circle cx="12" cy="12" r="4"/>',
    done: '<path d="m6 12 4 4 8-8"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  };
  const icon = name => `<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${icons[name] || ''}</svg>`;
  const dateLabel = value => {
    const parts = String(value || '').split('-');
    return parts.length === 3 ? `${Number(parts[1])}月${Number(parts[2])}日` : String(value || '未定日期');
  };

  function entriesFor(phase) {
    return (phase.stages || []).flatMap(stage => [...new Set((stage.nodes || []).map(n => n.date))].map(date => {
      const items = stage.nodes.filter(n => n.date === date);
      return {stageId: stage.id, date, title: stage.title, items,
        completed: items.length > 0 && items.every(n => n.completed === true),
        minutes: items.reduce((sum, n) => sum + (n.minutes || 0), 0)};
    }));
  }

  function reportMarkup(phase, id) {
    const report = phase.report;
    if (!report) return '';
    return `<div class="orbit-report" id="${e(id)}" hidden>
      <h4>${phase.completed ? '阶段学情分析' : '阶段作答进展'}</h4>
      <p>首次正确率：${report.firstAccuracy == null ? '依据不足' : Math.round(report.firstAccuracy * 100) + '%'} · 已判定 ${e(report.gradedQuestions || 0)} 题 · 待判定 ${e(report.pendingQuestions || 0)} 题 · 重练 ${e(report.repeatAttempts || 0)} 次</p>
      <p>${e(report.advice)}</p>
      ${(report.attempts || []).map(a => `<a href="#space/practice/ai/${e(a.questionId)}/${e(a.attemptId)}">${e(a.title)} · ${a.correct == null ? '待判定' : a.correct ? '首次正确' : '首次错误'} · 查看原作答 ↗</a>`).join('')}
    </div>`;
  }

  function render(plan) {
    const phases = plan.learningRoute?.phases || [];
    const groups = phases.map(entriesFor);
    const entries = groups.flat();
    const today = new Date().toLocaleDateString('en-CA');
    const current = entries.find(n => n.date === today && !n.completed) || entries.find(n => !n.completed);
    const restDates = (plan.days || []).filter(d => d.isRestDay).map(d => d.date);
    const remaining = plan.remaining || [];
    let order = 0;

    function starRow(row, phaseIndex) {
      const offsets = [[43,18,68,38,70],[88,28,70,38,60],[48,20,76,28,70]][phaseIndex % 3];
      const points = row.map((entry, index) => ({x: (index + .5) * 1000 / row.length,
        y: offsets[index] + (entry === current ? 29 : 24)}));
      const path = points.map((point, index) => {
        if (!index) return `M${point.x},${point.y}`;
        const prev = points[index - 1], dx = (point.x - prev.x) * .45;
        return `C${prev.x + dx},${prev.y - 30} ${point.x - dx},${point.y + 30} ${point.x},${point.y}`;
      }).join(' ');
      return `<div class="orbit-star-path" style="--orbit-node-count:${row.length}">
        <svg class="orbit-path-curve" viewBox="0 0 1000 220" preserveAspectRatio="none" aria-hidden="true"><path d="${path}"/></svg>
        ${row.map((entry, index) => {
          order++;
          const state = entry.completed ? 'done' : entry === current ? 'current' : 'pending';
          const label = {done: '已完成', current: '当前任务', pending: '待学习'}[state];
          return `<button type="button" class="orbit-star-node is-${state}" data-route-stage="${e(entry.stageId)}" data-route-date="${e(entry.date)}" style="--orbit-node-y:${offsets[index]}px;--orbit-node-index:${index}" ${state === 'current' ? 'aria-current="step"' : ''} aria-label="${e(entry.date + '，' + entry.title + '，' + label)}">
            <span class="orbit-star-orb">${icon(state === 'current' ? 'play' : state === 'done' ? 'done' : 'pending')}<span class="orbit-orb-ring"></span></span>
            <span class="orbit-star-copy"><span class="orbit-star-index">${String(order).padStart(2, '0')} · ${e(dateLabel(entry.date))}</span><strong>${e(entry.title)}</strong><span class="orbit-star-meta">${e(entry.minutes)} 分钟 · ${label}</span></span>
          </button>`;
        }).join('')}
      </div>`;
    }

    return `<section class="learning-orbit" aria-label="学习星图">
      <header class="orbit-hero">
        <div class="orbit-eyebrow">${icon('spark')} PERSONAL LEARNING ORBIT</div>
        <div class="orbit-hero-heading"><div><h3>${e(plan.title)}</h3><p>${e(plan.goal)}</p></div>
          <div class="orbit-plan-range">${icon('calendar')}<div><span>学习周期</span><strong>${e(dateLabel(plan.startDate))} — ${e(dateLabel(plan.endDate))}</strong></div></div>
        </div>
        <div class="orbit-summary" aria-label="计划概况"><div><strong>${phases.length}</strong><span>学习阶段</span></div><div><strong>${entries.length}</strong><span>学习任务</span></div><div><strong>${e(plan.dailyMinutes || 0)}</strong><span>分钟 / 天</span></div>
          <div class="orbit-legend"><span><i class="orbit-status-dot is-current"></i>当前任务</span><span><i class="orbit-status-dot is-pending"></i>待学习</span>${entries.some(n => n.completed) ? '<span><i class="orbit-status-dot is-done"></i>已完成</span>' : ''}</div>
        </div>
      </header>
      <div class="orbit-map"><div class="orbit-line" aria-hidden="true"></div>
        ${phases.map((phase, index) => {
          const group = groups[index], rows = [];
          for (let offset = 0; offset < group.length; offset += 5) rows.push(group.slice(offset, offset + 5));
          const reportId = `orbit-report-${plan.id}-${index}`;
          const rests = restDates.filter(date => date >= (index ? phases[index - 1].endDate : plan.startDate) && date <= phase.endDate);
          return `<section class="orbit-phase" style="--orbit-phase-index:${index}">
            <${phase.report ? 'button type="button"' : 'div'} class="orbit-phase-label" ${phase.report ? `data-orbit-report aria-controls="${e(reportId)}" aria-expanded="false"` : ''}>
              <span class="orbit-phase-number">${String(index + 1).padStart(2, '0')}</span><span><small>PHASE ${index + 1}</small><strong>${e(phase.title)}</strong></span><span class="orbit-phase-dates">${e(dateLabel(phase.startDate))} — ${e(dateLabel(phase.endDate))}</span>${phase.report ? '<span class="orbit-phase-expand" aria-hidden="true">⌄</span>' : ''}
            </${phase.report ? 'button' : 'div'}>
            ${rows.map(row => starRow(row, index)).join('')}
            ${rests.length ? `<div class="orbit-rest-note"><span></span>${rests.map(date => `<small>${e(dateLabel(date))} · 休息日</small>`).join('')}<span></span></div>` : ''}
            ${reportMarkup(phase, reportId)}
          </section>`;
        }).join('')}
      </div>
      ${restDates.filter(date => !phases.length || date > phases.at(-1).endDate).length ? `<p class="orbit-rest-footer">休息日：${restDates.filter(date => !phases.length || date > phases.at(-1).endDate).map(date => e(dateLabel(date))).join('、')}</p>` : ''}
      ${remaining.length ? `<section class="orbit-unscheduled"><header><div><span class="orbit-eyebrow">NEXT ORBIT</span><h4>待安排</h4></div><p>这些任务尚无日期，可在调整计划时安排</p></header><div class="orbit-unscheduled-grid">${remaining.map(node => `<article><span>${e(node.phase || '学习任务')}</span><h5>${e(node.title)}</h5><p>${icon('clock')}${e(node.minutes)} 分钟 · 日期未定</p></article>`).join('')}</div></section>` : ''}
      <p data-route-status role="status"></p>
    </section>`;
  }

  function bind(host) {
    host.querySelectorAll('[data-orbit-report]').forEach(button => button.addEventListener('click', () => {
      const report = host.querySelector('#' + CSS.escape(button.getAttribute('aria-controls')));
      if (report) { report.hidden = !report.hidden; button.setAttribute('aria-expanded', String(!report.hidden)); }
    }));
  }
  window.XueyaLearningOrbit = {render, bind};
})();
