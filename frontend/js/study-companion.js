/* A local UI companion. Animation/navigation never call a model. */
(() => {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  let instance;
  function create({ask, getCourseId = () => 'course-default', getBusy = () => false, navigate = hash => { location.hash = hash; }, openSource = () => {}} = {}) {
    const key = (window.XueyaDataKey || (k => k))('study-companion-v1');
    let preferences = {}, course = String(getCourseId()), messages = [], busy = false, controller, timer, speechTimer, destroyed = false;
    let todayPlan = null, todayStage = null, todayDate = '', tab = 'chat', opened = false, lastDrag = false;
    try { const saved = JSON.parse(localStorage.getItem(key) || '{}'); preferences = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {}; } catch {}
    const root = document.createElement('aside');
    root.className = 'study-companion'; root.dataset.state = 'idle'; root.setAttribute('aria-label', '小涯学习伙伴');
    root.innerHTML = `<div class="companion-dock" data-companion-dock>
      <span class="companion-speech" data-companion-speech hidden></span>
      <button type="button" class="companion-robot" data-companion-robot aria-label="打开小涯学习伙伴，可拖动移动" aria-expanded="false">
        <svg class="companion-art" viewBox="0 0 100 120" aria-hidden="true"><defs><linearGradient id="companion-shell" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#91acff"/><stop offset=".55" stop-color="#6877ed"/><stop offset="1" stop-color="#895bd6"/></linearGradient><linearGradient id="companion-screen" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#263966"/><stop offset="1" stop-color="#101b36"/></linearGradient></defs>
        <ellipse class="companion-shadow" cx="50" cy="111" rx="24" ry="4" fill="#8b8cfc" opacity=".2"/>
        <g class="companion-body"><path d="M50 18v-8" stroke="#b0bfff" stroke-width="3"/><circle cx="50" cy="8" r="4" fill="#9bf6ee"/>
          <g class="companion-arm companion-arm-left"><rect x="23" y="78" width="13" height="23" rx="6" fill="url(#companion-shell)" stroke="#42499c" stroke-width="2"/></g>
          <g class="companion-arm companion-arm-right"><rect x="64" y="78" width="13" height="23" rx="6" fill="url(#companion-shell)" stroke="#42499c" stroke-width="2"/></g>
          <rect x="34" y="74" width="32" height="30" rx="10" fill="url(#companion-shell)" stroke="#42499c" stroke-width="2"/>
          <path d="M43 86l5 4-5 4m10 0h6" fill="none" stroke="#d9ffff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
          <rect x="36" y="101" width="12" height="8" rx="4" fill="#727dde"/><rect x="53" y="101" width="12" height="8" rx="4" fill="#727dde"/>
          <path d="M24 30c-5-12 10-19 18-13 6-9 20-8 25 1 11-3 21 7 17 17 9 8 6 23-3 27 1 11-10 19-20 15-7 5-19 5-26-1-12 2-22-8-19-19-9-9-5-23 8-27Z" fill="url(#companion-shell)" stroke="#42499c" stroke-width="2"/>
          <path d="M26 30c2-5 6-7 11-7" fill="none" stroke="#c4d3ff" stroke-width="3" stroke-linecap="round" opacity=".8"/>
          <rect x="24" y="32" width="52" height="34" rx="10" fill="url(#companion-screen)" stroke="#a0b6ff" stroke-opacity=".55" stroke-width="1.5"/>
          <g class="companion-face"><path d="m35 43 8 6-8 6m19 1h10" fill="none" stroke="#a1fff2" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/></g>
          <g class="companion-thinking" fill="#a1fff2"><circle cx="37" cy="49" r="3"/><circle cx="50" cy="49" r="3"/><circle cx="63" cy="49" r="3"/></g>
        </g></svg>
      </button><div class="companion-dock-actions"><button type="button" data-companion-wave aria-label="和小涯打招呼">✦</button><button type="button" data-companion-open title="打开对话">小涯</button><button type="button" data-companion-minimize aria-label="收起小人物">−</button></div>
    </div><button type="button" class="companion-restore" data-companion-restore aria-label="展开小涯学习伙伴" hidden>✦ 小涯</button>
    <section class="companion-panel" data-companion-panel role="dialog" aria-modal="false" aria-labelledby="companionTitle" hidden>
      <header class="companion-header"><div><span class="companion-status-dot"></span><strong id="companionTitle">小涯</strong><small data-companion-status>你的学习伙伴</small></div><button type="button" data-companion-close aria-label="收起小涯对话">×</button></header>
      <nav class="companion-tabs" aria-label="学习伙伴功能"><button type="button" data-companion-tab="chat" aria-pressed="true">聊一聊</button><button type="button" data-companion-tab="today" aria-pressed="false">今日学习</button></nav>
      <div class="companion-chat" data-companion-chat><div class="companion-messages" data-companion-messages role="log" aria-label="小涯对话"></div>
        <form class="companion-form" data-companion-form><label class="visually-hidden" for="companionQuestion">向小涯提问</label><textarea id="companionQuestion" data-companion-input rows="2" maxlength="2000" placeholder="问我一道题，或聊聊学习…"></textarea>
          <div class="companion-send-row"><small>沿用学涯模型 · 发送时可能产生费用</small><button type="submit" data-companion-send disabled>发送</button><button type="button" data-companion-stop hidden>停止</button></div></form>
      </div><div class="companion-today" data-companion-today hidden></div>
    </section>`;
    document.body.append(root);
    const find = selector => root.querySelector(selector), dock = find('[data-companion-dock]'), panel = find('[data-companion-panel]'), input = find('[data-companion-input]');
    root.addEventListener('click', event => event.stopPropagation());
    function historyKey() { return key + ':chat:' + course; }
    function loadMessages() { try { const rows = JSON.parse(localStorage.getItem(historyKey()) || '[]'); messages = Array.isArray(rows) ? rows.filter(row => row && ['user','assistant'].includes(row.role) && typeof row.text === 'string').map(row => ({...row, sources:Array.isArray(row.sources) ? row.sources : []})) : []; } catch { messages = []; } }
    function saveMessages() { try { localStorage.setItem(historyKey(), JSON.stringify(messages.filter(row => !row.pending))); } catch { say('本机空间不足，本次对话暂未保存。'); } }
    function savePreferences() { try { localStorage.setItem(key, JSON.stringify(preferences)); } catch {} }
    function setState(value) { clearTimeout(timer); root.dataset.state = value; }
    function say(text) { clearTimeout(speechTimer); const speech = find('[data-companion-speech]'); speech.textContent = text; speech.hidden = false; const box = dock.getBoundingClientRect(); speech.style.transform = 'none'; speech.style.left = Math.max(12, Math.min(innerWidth - speech.offsetWidth - 12, box.left + 48 - speech.offsetWidth / 2)) - box.left + 'px'; speech.style.bottom = box.top < 70 ? 'auto' : '124px'; speech.style.top = box.top < 70 ? '124px' : 'auto'; speechTimer = setTimeout(() => { speech.hidden = true; }, 3200); }
    function placePanel() {
      const box = dock.getBoundingClientRect(), width = Math.min(360, innerWidth - 24), height = Math.min(510, innerHeight - 24);
      panel.style.width = width + 'px'; panel.style.height = height + 'px';
      panel.style.left = Math.max(12, Math.min(innerWidth - width - 12, box.left > innerWidth / 2 ? box.left - width - 12 : box.right + 12)) + 'px';
      panel.style.top = Math.max(12, Math.min(innerHeight - height - 12, box.bottom - height)) + 'px';
    }
    function placeDock(x = preferences.x, y = preferences.y) {
      x = Number.isFinite(x) ? x : innerWidth - 112; y = Number.isFinite(y) ? y : innerHeight - 140;
      preferences.x = Math.max(8, Math.min(innerWidth - 96, x)); preferences.y = Math.max(8, Math.min(innerHeight - 132, y));
      dock.style.left = preferences.x + 'px'; dock.style.top = preferences.y + 'px'; placePanel();
    }
    function controls() {
      find('[data-companion-send]').disabled = busy || getBusy() || !input.value.trim();
      find('[data-companion-send]').hidden = busy; find('[data-companion-stop]').hidden = !busy;
      find('[data-companion-status]').textContent = busy ? '正在思考…' : '你的学习伙伴';
    }
    function drawMessages() {
      const list = find('[data-companion-messages]'), nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
      list.innerHTML = messages.length ? messages.map((row, index) => `<article class="companion-message is-${row.role}${row.failed ? ' is-error' : ''}${row.pending ? ' is-pending' : ''}"><small>${row.role === 'user' ? '你' : '小涯'}${row.pending ? ' · 回答核对中' : ''}</small><div>${escape(row.text || '正在想一想…')}</div>${row.sources?.length ? `<details><summary>参考资料 ${row.sources.length} 处</summary>${row.sources.map((source, sourceIndex) => `<button type="button" data-companion-source="${index}:${sourceIndex}">${escape(source.title || '资料原文')} · ${escape(source.location || '查看出处')}</button>`).join('')}</details>` : ''}</article>`).join('') : '<div class="companion-welcome"><span>✦</span><strong>你好，我是小涯。</strong><p>可以陪你解题、梳理知识，也能帮你打开今天的学习任务。</p><small>点击发送后才会请求模型。</small></div>';
      list.querySelectorAll('[data-companion-source]').forEach(button => button.onclick = () => { const [row, source] = button.dataset.companionSource.split(':').map(Number); const value = messages[row]?.sources?.[source]; if (value) openSource(value); });
      if (nearBottom || busy) list.scrollTop = list.scrollHeight;
    }
    function sync() { if (destroyed) return; const next = String(getCourseId()); if (next !== course && !busy) { course = next; loadMessages(); drawMessages(); } controls(); }
    function toggle(force) { sync(); opened = force ?? !opened; panel.hidden = !opened; find('[data-companion-robot]').setAttribute('aria-expanded', String(opened)); if (opened) { placePanel(); if (tab === 'chat') input.focus(); else loadToday(); } }
    function wave() { if (busy) { say('我正在认真想这道题。'); return; } setState('wave'); say('你好呀，今天也一起学一点吧。'); timer = setTimeout(() => setState('idle'), 1800); }
    async function send(event) {
      event.preventDefault(); sync(); const question = input.value.trim();
      if (!question || busy || getBusy()) { if (getBusy()) say('主问答正在回答，请稍后再问。'); return; }
      if (typeof ask !== 'function') { say('问答服务还没准备好，请刷新后再试。'); return; }
      const history = messages.filter(row => !row.failed && !row.pending).slice(-12).map(row => ({role:row.role, content:row.text}));
      const previousSources = [...messages].reverse().find(row => row.sources?.length)?.sources || [];
      messages.push({role:'user', text:question}); const answer = {role:'assistant', text:'', pending:true}; messages.push(answer);
      input.value = ''; busy = true; setState('thinking'); saveMessages(); drawMessages(); controls(); controller = new AbortController();
      try {
        const result = await ask(question, {courseId:course, history, previousSources, signal:controller.signal, onUpdate(update) { if (destroyed) return; if (typeof update.answer === 'string') answer.text = update.answer; drawMessages(); }});
        if (destroyed) return;
        if (!result?.answer || result.answerStatus === 'unavailable') throw Error('AI_UNAVAILABLE');
        answer.text = result.answer; answer.sources = Array.isArray(result.sources) ? result.sources : []; setState('done'); say('回答好了，来看看吧。'); timer = setTimeout(() => setState('idle'), 2400);
      } catch (error) {
        if (destroyed) return;
        answer.failed = true; answer.text = controller.signal.aborted ? '已停止回答，不会自动重试。' : ({AI_UNAVAILABLE:'模型暂不可用，请检查学涯的模型配置。',AI_CONNECTION_FAILED:'暂时连接不上模型，请检查网络后再试。',AUTH_REQUIRED:'登录已失效，请重新登录后再问。'}[error.code || error.message] || '这次回答没有完成，请检查服务设置后再试。'); setState('idle');
      } finally { delete answer.pending; busy = false; controller = null; if (!destroyed) { saveMessages(); drawMessages(); sync(); } }
    }
    async function loadToday() {
      const target = find('[data-companion-today]'); target.innerHTML = '<p role="status">正在读取今日学习安排…</p>';
      try {
        const response = await window.XueyaPlatform.spaceFetch('/api/learning/space/plan/list'), value = await response.json();
        if (!response.ok || !value.ok) throw Error('READ_FAILED'); if (destroyed) return;
        todayPlan = value.active; todayDate = new Date().toLocaleDateString('en-CA', {timeZone:'Asia/Shanghai'});
        const day = todayPlan?.days?.find(row => row.date === todayDate), tasks = day?.tasks || [];
        todayStage = todayPlan?.learningRoute?.phases?.flatMap(phase => phase.stages || []).find(stage => stage.nodes?.some(node => node.date === todayDate && !node.completed)) || todayPlan?.learningRoute?.phases?.flatMap(phase => phase.stages || []).find(stage => stage.nodes?.some(node => node.date === todayDate));
        target.innerHTML = `<span class="companion-day-label">${escape(todayDate)} · 今日学习</span><h4>${escape(todayPlan?.title || '还没有正在执行的计划')}</h4>${tasks.length ? `<p>${tasks.filter(t => t.completed).length} / ${tasks.length} 项已完成 · 预计 ${tasks.reduce((sum, t) => sum + (t.minutes || 0), 0)} 分钟</p><ul>${tasks.map(task => `<li><span>${task.completed ? '✓' : '○'}</span>${escape(task.title)}</li>`).join('')}</ul>` : `<p>${day?.isRestDay ? '今天是休息日，好好放松一下。' : todayPlan ? '今天没有已安排的任务，可以查看完整计划。' : '先定一个学习目标，我会在这里帮你找到每天的任务。'}</p>`}<button type="button" data-companion-start>${tasks.length && todayStage ? '开始今日学习' : todayPlan ? '查看学习计划' : '去定制学习计划'} →</button>`;
        target.querySelector('[data-companion-start]').onclick = () => {
          if (todayStage && tasks.length) { const routeKey = (window.XueyaDataKey || (k => k))('learning-route:' + todayPlan.id); sessionStorage.setItem(routeKey, todayStage.id); sessionStorage.setItem(routeKey + ':date', todayDate); sessionStorage.removeItem(routeKey + ':node'); }
          toggle(false); navigate(todayPlan ? '#space/analysis/plans' : '#space/materials/plan');
        };
      } catch { if (!destroyed) { target.innerHTML = '<p>今日学习安排暂时无法读取。</p><button type="button" data-companion-retry>重试读取</button>'; target.querySelector('button').onclick = loadToday; } }
    }
    find('[data-companion-form]').onsubmit = send; input.oninput = controls;
    find('[data-companion-stop]').onclick = () => controller?.abort();
    input.onkeydown = event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); find('[data-companion-form]').requestSubmit(); } };
    find('[data-companion-close]').onclick = () => { toggle(false); find('[data-companion-robot]').focus(); };
    find('[data-companion-open]').onclick = () => toggle(); find('[data-companion-wave]').onclick = wave;
    find('[data-companion-minimize]').onclick = () => { toggle(false); preferences.compact = true; dock.hidden = true; find('[data-companion-restore]').hidden = false; savePreferences(); };
    find('[data-companion-restore]').onclick = () => { preferences.compact = false; dock.hidden = false; find('[data-companion-restore]').hidden = true; placeDock(); savePreferences(); };
    root.onkeydown = event => { if (event.key === 'Escape' && opened) { event.preventDefault(); event.stopPropagation(); toggle(false); find('[data-companion-robot]').focus(); } };
    root.querySelectorAll('[data-companion-tab]').forEach(button => button.onclick = () => { tab = button.dataset.companionTab; root.querySelectorAll('[data-companion-tab]').forEach(item => item.setAttribute('aria-pressed', String(item === button))); find('[data-companion-chat]').hidden = tab !== 'chat'; find('[data-companion-today]').hidden = tab !== 'today'; if (tab === 'today') loadToday(); else input.focus(); });
    const robot = find('[data-companion-robot]'); let drag;
    robot.onpointerdown = event => { if (event.button !== 0) return; event.preventDefault(); event.stopPropagation(); drag = {x:event.clientX, y:event.clientY, left:preferences.x, top:preferences.y}; lastDrag = false; try { robot.setPointerCapture(event.pointerId); } catch {} };
    const moveDrag = event => { if (!drag) return; const dx = event.clientX - drag.x, dy = event.clientY - drag.y; if (Math.hypot(dx,dy) > 6) lastDrag = true; if (lastDrag) placeDock(drag.left + dx, drag.top + dy); };
    const endDrag = () => { if (drag) savePreferences(); drag = null; };
    window.addEventListener('pointermove', moveDrag); window.addEventListener('pointerup', endDrag); window.addEventListener('pointercancel', endDrag);
    robot.onclick = () => { if (lastDrag) { lastDrag = false; return; } toggle(); };
    const resize = () => { placeDock(); savePreferences(); }; window.addEventListener('resize', resize);
    dock.hidden = Boolean(preferences.compact); find('[data-companion-restore]').hidden = !preferences.compact;
    placeDock(); loadMessages(); drawMessages(); controls();
    return {sync, destroy() { destroyed = true; controller?.abort(); clearTimeout(timer); clearTimeout(speechTimer); window.removeEventListener('resize', resize); window.removeEventListener('pointermove', moveDrag); window.removeEventListener('pointerup', endDrag); window.removeEventListener('pointercancel', endDrag); root.remove(); }};
  }
  window.XueyaStudyCompanion = {mount(options) { instance?.destroy(); instance = create(options); return instance; }, sync() { instance?.sync(); }, destroy() { instance?.destroy(); instance = null; }};
})();
