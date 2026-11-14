/* Persisted learning tasks on one connected, zoomable route. No model calls. */
(() => {
  'use strict';
  const e = window.XueyaRich.escape;
  const dateLabel = value => {
    const parts = String(value || '').split('-');
    return parts.length === 3 ? `${Number(parts[1])}月${Number(parts[2])}日` : String(value || '日期未定');
  };
  const icon = state => `<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24">${state === 'current' ? '<path d="m9 7 8 5-8 5Z"/>' : state === 'done' ? '<path d="m6 12 4 4 8-8"/>' : '<circle cx="12" cy="12" r="4"/>'}</svg>`;

  function render(plan) {
    const phases = plan.learningRoute?.phases || [];
    const entries = phases.flatMap((phase, phaseIndex) => (phase.stages || []).flatMap(stage =>
      [...new Set((stage.nodes || []).map(n => n.date))].map(date => {
        const items = stage.nodes.filter(n => n.date === date);
        return {stageId: stage.id, date, title: stage.title, phase: phase.title, phaseIndex,
          completed: items.length > 0 && items.every(n => n.completed === true),
          minutes: items.reduce((sum, n) => sum + (n.minutes || 0), 0)};
      })));
    const today = new Date().toLocaleDateString('en-CA');
    const current = entries.find(n => n.date === today && !n.completed) || entries.find(n => !n.completed);
    const columns = Math.min(6, Math.max(1, Math.ceil(Math.sqrt(entries.length * 1.3))));
    const width = columns * 220 + 36, height = Math.max(210, Math.ceil(entries.length / columns) * 190 + 60);
    const wave = [8, -18, 22, -10, 18, 0];
    const points = entries.map((entry, index) => {
      const row = Math.floor(index / columns), column = index % columns;
      const visualColumn = row % 2 ? columns - 1 - column : column;
      return {entry, row, x: 24 + visualColumn * 220, y: 46 + row * 190 + wave[visualColumn] * (row % 2 ? -1 : 1)};
    });
    const links = points.slice(1).map((point, index) => {
      const previous = points[index], x1 = previous.x + 95, y1 = previous.y + 26, x2 = point.x + 95, y2 = point.y + 26;
      const dx = x2 - x1;
      // Horizontal tangents flow gently through each node; row turns sweep
      // outside the labels instead of cutting down through the task text.
      const turn = point.row !== previous.row, side = previous.row % 2 ? -1 : 1;
      const path = turn
        ? `M${x1},${y1} C${x1+side*140},${y1-46} ${x2+side*140},${y2+46} ${x2},${y2}`
        : `M${x1},${y1} C${x1+dx*.38},${y1-28} ${x2-dx*.38},${y2+28} ${x2},${y2}`;
      return `<path d="${path}" class="${previous.entry.completed ? 'is-done' : previous.entry === current ? 'is-current' : ''}"/>`;
    }).join('');
    const reports = phases.map((phase, index) => {
      if (!phase.report) return '';
      const report = phase.report, id = `orbit-report-${plan.id}-${index}`;
      return `<section class="orbit-phase orbit-compact-phase"><button type="button" class="orbit-phase-label" data-orbit-report aria-controls="${e(id)}" aria-expanded="false">阶段 ${index + 1} · ${e(phase.title)} · 查看学情</button>
        <div class="orbit-report" id="${e(id)}" hidden><h4>${phase.completed ? '阶段学情分析' : '阶段作答进展'}</h4>
        <p>首次正确率：${report.firstAccuracy == null ? '依据不足' : Math.round(report.firstAccuracy * 100) + '%'} · 已判定 ${e(report.gradedQuestions || 0)} 题 · 待判定 ${e(report.pendingQuestions || 0)} 题 · 重练 ${e(report.repeatAttempts || 0)} 次</p>
        <p>${e(report.advice || '')}</p>${(report.attempts || []).map(a => `<a href="#space/practice/ai/${e(a.questionId)}/${e(a.attemptId)}">${e(a.title)} · 查看原作答 ↗</a>`).join('')}</div></section>`;
    }).join('');
    const rests = (plan.days || []).filter(d => d.isRestDay).map(d => d.date);
    const gradientId = 'orbit-flow-' + String(plan.id).replace(/[^a-zA-Z0-9_-]/g, '');
    return `<section class="learning-orbit orbit-connected" aria-label="学习星图" data-orbit-plan="${e(plan.id)}">
      <header class="orbit-compact-heading"><h3>${e(plan.title)}</h3><span>${e(dateLabel(plan.startDate))} — ${e(dateLabel(plan.endDate))}</span></header>
      <div class="orbit-summary" aria-label="计划概况"><div><strong>${phases.length}</strong><span>学习阶段</span></div><div><strong>${entries.length}</strong><span>学习任务</span></div><div><strong>${e(plan.dailyMinutes || 0)}</strong><span>${plan.schedulingMode === 'by-days' ? '日均预计分钟' : '分钟 / 天'}</span></div>
        <div class="orbit-legend"><span><i class="orbit-status-dot is-current"></i>当前任务</span><span><i class="orbit-status-dot is-pending"></i>待学习</span><span><i class="orbit-status-dot is-done"></i>已完成</span></div></div>
      <div class="orbit-canvas-tools" role="group" aria-label="学习路线缩放">
        <button type="button" data-orbit-zoom="out" aria-label="缩小学习路线">−</button><output data-orbit-scale aria-live="polite">100%</output><button type="button" data-orbit-zoom="in" aria-label="放大学习路线">+</button>
        <button type="button" data-orbit-zoom="reset">恢复 100%</button><button type="button" data-orbit-zoom="fit">查看全部节点</button>
        <span>按编号顺序连接 · 拖动空白处或滚动查看 · 点击节点学习</span></div>
      ${entries.length ? `<div class="orbit-canvas-viewport" tabindex="0" role="region" aria-label="可缩放的连续学习路线">
        <div class="orbit-canvas-size"><div class="orbit-canvas-stage" data-width="${width}" data-height="${height}" style="width:${width}px;height:${height}px">
          <svg class="orbit-route-links" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" aria-hidden="true"><defs><linearGradient id="${gradientId}" gradientUnits="userSpaceOnUse" x1="24" y1="0" x2="${width-24}" y2="${height}"><stop stop-color="var(--orbit-blue)" stop-opacity=".8"/><stop offset=".5" stop-color="var(--orbit-accent)" stop-opacity=".65"/><stop offset="1" stop-color="var(--orbit-blue)" stop-opacity=".8"/></linearGradient></defs><g stroke="url(#${gradientId})">${links}</g></svg>
          ${points.map(({entry, x, y}, index) => {
            const state = entry.completed ? 'done' : entry === current ? 'current' : 'pending';
            const label = {done:'已完成', current:'当前任务', pending:'待学习'}[state];
            return `<button type="button" class="orbit-star-node orbit-canvas-node is-${state}" data-route-stage="${e(entry.stageId)}" data-route-date="${e(entry.date)}" style="left:${x}px;top:${y}px" ${state === 'current' ? 'aria-current="step"' : ''} title="${e(entry.title)}" aria-label="${e(entry.date + '，' + entry.title + '，' + label)}">
              <span class="orbit-star-orb">${icon(state)}<span class="orbit-orb-ring"></span></span>
              <small class="orbit-node-phase">${String(index + 1).padStart(2,'0')} · ${e(entry.phase)}</small><strong>${e(entry.title)}</strong>
              <span class="orbit-node-time">${e(dateLabel(entry.date))} · ${e(entry.minutes)} 分钟 · ${label}</span></button>`;
          }).join('')}</div></div></div>` : '<p class="orbit-rest-footer">当前没有可显示的学习节点。</p>'}
      ${reports ? `<div class="orbit-phase-reports">${reports}</div>` : ''}
      ${rests.length ? `<p class="orbit-rest-footer">休息日：${rests.map(date => e(dateLabel(date))).join('、')}</p>` : ''}
      ${plan.remaining?.length ? `<section class="orbit-unscheduled"><h4>待安排</h4><p>这些任务尚无日期，可在调整周期时安排。</p><div class="orbit-unscheduled-grid">${plan.remaining.map(node => `<article><span>${e(node.phase || '学习任务')}</span><h5>${e(node.title)}</h5><p>${e(node.minutes)} 分钟 · 日期未定</p></article>`).join('')}</div></section>` : ''}
      <p data-route-status role="status"></p></section>`;
  }

  function bind(host) {
    host.querySelectorAll('[data-orbit-report]').forEach(button => button.addEventListener('click', () => {
      const report = host.querySelector('#' + CSS.escape(button.getAttribute('aria-controls')));
      if (report) { report.hidden = !report.hidden; button.setAttribute('aria-expanded', String(!report.hidden)); }
    }));
    const orbit = host.querySelector('.orbit-connected'), viewport = orbit?.querySelector('.orbit-canvas-viewport');
    if (!viewport) return;
    const stage = viewport.querySelector('.orbit-canvas-stage'), size = viewport.querySelector('.orbit-canvas-size');
    const width = Number(stage.dataset.width), height = Number(stage.dataset.height);
    const key = (window.XueyaDataKey || (k => k))('orbit-canvas:' + orbit.dataset.orbitPlan);
    let scale = 1, autoFit = true, saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(key) || 'null'); } catch {}
    const save = () => { if (!viewport.isConnected) return; try { sessionStorage.setItem(key, JSON.stringify({scale, autoFit, left:viewport.scrollLeft, top:viewport.scrollTop})); } catch {} };
    function setScale(value, fit = false) {
      if (!viewport.isConnected) return;
      const centerX = (viewport.scrollLeft + viewport.clientWidth / 2) / scale, centerY = (viewport.scrollTop + viewport.clientHeight / 2) / scale;
      if (!fit) viewport.style.height = '';
      scale = fit ? Math.max(.01, value) : Math.max(.1, Math.min(2, value));
      autoFit = fit;
      stage.style.transform = `scale(${scale})`;
      size.style.width = width * scale + 'px'; size.style.height = height * scale + 'px';
      viewport.scrollLeft = fit ? 0 : centerX * scale - viewport.clientWidth / 2;
      viewport.scrollTop = fit ? 0 : centerY * scale - viewport.clientHeight / 2;
      orbit.querySelector('[data-orbit-scale]').textContent = Math.round(scale * 100) + '%';
      orbit.querySelector('[data-orbit-zoom="out"]').disabled = scale <= .1;
      orbit.querySelector('[data-orbit-zoom="in"]').disabled = scale >= 2;
      save();
    }
    const fit = () => {
      const maxHeight = Math.max(280, Math.min(640, window.innerHeight * .62));
      const fitted = Math.min(1, (viewport.clientWidth - 16) / width, (maxHeight - 18) / height);
      viewport.style.height = Math.max(240, Math.min(maxHeight, height * fitted + 18)) + 'px';
      setScale(fitted, true);
    };
    orbit.querySelectorAll('[data-orbit-zoom]').forEach(button => button.addEventListener('click', event => {
      event.stopPropagation();
      const action = button.dataset.orbitZoom;
      if (action === 'fit') fit(); else setScale(action === 'reset' ? 1 : scale * (action === 'in' ? 1.25 : .8));
    }));
    viewport.addEventListener('scroll', save, {passive:true});
    let drag = null;
    viewport.addEventListener('pointerdown', event => {
      if (event.pointerType !== 'mouse' || event.button !== 0 || event.target.closest('button,a')) return;
      drag = {x:event.clientX, y:event.clientY, left:viewport.scrollLeft, top:viewport.scrollTop};
      viewport.setPointerCapture(event.pointerId); viewport.classList.add('is-dragging'); event.preventDefault();
    });
    viewport.addEventListener('pointermove', event => { if (drag) { viewport.scrollLeft = drag.left + drag.x - event.clientX; viewport.scrollTop = drag.top + drag.y - event.clientY; } });
    const stopDrag = () => { drag = null; viewport.classList.remove('is-dragging'); };
    viewport.addEventListener('pointerup', stopDrag); viewport.addEventListener('pointercancel', stopDrag);
    viewport.addEventListener('keydown', event => {
      if (event.target !== viewport || !['+','=','-','0'].includes(event.key)) return;
      event.preventDefault(); setScale(event.key === '0' ? 1 : scale * (event.key === '-' ? .8 : 1.25));
    });
    requestAnimationFrame(() => {
      if (saved && Number.isFinite(saved.scale) && saved.autoFit === false) {
        setScale(saved.scale); viewport.scrollLeft = Number(saved.left) || 0; viewport.scrollTop = Number(saved.top) || 0;
      } else fit();
    });
    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(() => {
        if (!viewport.isConnected) { observer.disconnect(); return; }
        if (autoFit && viewport.clientWidth) fit();
      });
      observer.observe(viewport);
    }
  }
  window.XueyaLearningOrbit = {render, bind};
})();
