(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaWorkspaceViews=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
function createViews(ctx,base){
  const {state,L,e,icon,store,service,rich,getAttachments,getQueue}=ctx;
  const button=(label,attrs='',style='button-outline')=>`<button type="button" class="button button-small ${style}" ${attrs}>${label}</button>`;
  const heading=(title,description,actions='')=>`<div class="view-heading"><div><h1>${title}</h1><p>${description}</p></div><div class="heading-actions">${actions}</div></div>`;
  const citations=sources=>`<div class="citations">${(sources||[]).map(s=>{
    const isWeb=Boolean(s.isWeb||s.url||s.location?.startsWith('http')||s.id?.startsWith('web-'));
    return `<button type="button" class="citation-chip ${isWeb?'citation-web':''}" data-citation="${e(s.id)}" title="${isWeb?'点击在新窗口打开网页：'+e(s.url||s.location):s.isPlatform?'查看公共资料来源与位置':'点击查看课程资料原文'}">${isWeb?'🌐 ':icon('file')} ${e(s.title)} · ${e(s.location||'原文片段')}${s.isPlatform&&s.originCourseName?' · '+e(s.originCourseName):''}</button>`;
  }).join('')}</div>`;
  const unavailable=label=>`<p class="capability-note">${e(label)}的这个入口尚未接通。可使用本页“进阶学习功能”中的对应操作；原有浏览器内容仍可使用。</p>`;
  const cartoonAvatarSvg = `<svg class="doubao-user-avatar" viewBox="0 0 100 100" width="36" height="36" aria-hidden="true"><defs><linearGradient id="dbAvatarBg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#6366f1"/><stop offset="100%" stop-color="#a855f7"/></linearGradient><linearGradient id="dbHoodie" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#3b82f6"/><stop offset="100%" stop-color="#2563eb"/></linearGradient><linearGradient id="dbHair" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#334155"/><stop offset="100%" stop-color="#1e293b"/></linearGradient></defs><circle cx="50" cy="50" r="50" fill="url(#dbAvatarBg)"/><path d="M22 92 C22 75 35 68 50 68 C65 68 78 75 78 92 Z" fill="url(#dbHoodie)"/><path d="M42 68 L50 82 L58 68 Z" fill="#ffffff" opacity="0.9"/><rect x="44" y="60" width="12" height="12" rx="3" fill="#fed7aa"/><ellipse cx="50" cy="46" rx="22" ry="24" fill="#ffedd5"/><ellipse cx="36" cy="51" rx="4.5" ry="2.5" fill="#f43f5e" opacity="0.4"/><ellipse cx="64" cy="51" rx="4.5" ry="2.5" fill="#f43f5e" opacity="0.4"/><path d="M45 54 Q50 60 55 54" stroke="#e11d48" stroke-width="2.5" stroke-linecap="round" fill="none"/><ellipse cx="38" cy="44" rx="3" ry="4" fill="#0f172a"/><circle cx="37" cy="42" r="1.2" fill="#ffffff"/><ellipse cx="62" cy="44" rx="3" ry="4" fill="#0f172a"/><circle cx="61" cy="42" r="1.2" fill="#ffffff"/><rect x="31" y="38" width="15" height="12" rx="4" fill="none" stroke="#0284c7" stroke-width="2"/><rect x="54" y="38" width="15" height="12" rx="4" fill="none" stroke="#0284c7" stroke-width="2"/><line x1="46" y1="44" x2="54" y2="44" stroke="#0284c7" stroke-width="2"/><path d="M28 42 C26 28 35 18 50 18 C65 18 74 28 72 42 C68 30 60 26 50 26 C40 26 32 30 28 42 Z" fill="url(#dbHair)"/><path d="M32 34 C38 28 46 32 48 38 C42 36 36 38 32 34 Z" fill="url(#dbHair)"/><path d="M50 18 Q53 10 60 12" stroke="#334155" stroke-width="2.5" stroke-linecap="round" fill="none"/></svg>`;
  const chatBubbleSvg = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  const leafBranchSvg = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>';
  const pinIconSvg = '<svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor" aria-hidden="true"><path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/></svg>';
  const dotsIconSvg = '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><circle cx="12" cy="12" r="2"/><circle cx="5" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>';
  const archiveIconSvg = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8"/><line x1="10" y1="12" x2="14" y2="12"/></svg>';

  function renderSessionItem(s){
    const isSelected = s.id === state.sessionId;
    const isMenuOpen = state.activeSessionMenuId === s.id;
    const userCount = (s.messages || []).filter(m => m.role === "user").length;
    const isBranch = Boolean(s.parentSessionId);
    return `<div class="session-item-row ${isSelected?'active':''} ${isMenuOpen?'is-menu-open':''}">`+
      `<button type="button" data-session="${e(s.id)}" class="session-item-btn ${isSelected?'active':''}" aria-pressed="${isSelected}" ${state.pending?'disabled':''} title="${e(s.title)}">`+
        `<span class="session-bubble-badge ${isBranch?'badge-branch':'badge-chat'}">${isBranch?leafBranchSvg:chatBubbleSvg}</span>`+
        `<span class="session-title">${e(s.title)}</span>`+
        `<span class="session-count-tag">${userCount} 问</span>`+
        (s.pinned?`<span class="session-pinned-tag" title="已置顶">${pinIconSvg}</span>`:'')+
      `</button>`+
      `<div class="session-hover-actions">`+
        `<button type="button" class="session-hover-btn" data-archive-session="${e(s.id)}" title="${s.archived?'取消归档':'归档对话'}" aria-label="${s.archived?'取消归档':'归档对话'}">${archiveIconSvg}</button>`+
        `<button type="button" class="session-hover-btn session-menu-trigger" data-session-menu="${e(s.id)}" aria-label="更多操作" title="更多操作">${dotsIconSvg}</button>`+
      `</div>`+
      (isMenuOpen?`<div class="session-dropdown-menu" role="menu" data-session-dropdown="${e(s.id)}">`+
        `<button type="button" class="menu-item" data-pin-session="${e(s.id)}" role="menuitem"><span class="menu-icon">${s.pinned?'📌':'📍'}</span><span>${s.pinned?'取消置顶':'置顶'}</span></button>`+
        `<button type="button" class="menu-item" data-rename-session="${e(s.id)}" role="menuitem"><span class="menu-icon">✏️</span><span>重命名</span></button>`+
        `<button type="button" class="menu-item" data-branch-session="${e(s.id)}" role="menuitem"><span class="menu-icon">🔀</span><span>在新对话中继续</span></button>`+
        `<button type="button" class="menu-item" data-archive-session="${e(s.id)}" role="menuitem"><span class="menu-icon">🗃️</span><span>${s.archived?'取消归档':'归档对话'}</span></button>`+
        `<div class="menu-divider"></div>`+
        `<button type="button" class="menu-item menu-item-danger" data-delete-session="${e(s.id)}" role="menuitem"><span class="menu-icon">🗑️</span><span>删除</span></button>`+
      `</div>`:'')+
    `</div>`;
  }

  function sessions(){
    const q = (state.sessionQuery || '').trim().toLowerCase();
    const filtered = state.sessions.filter(s => {
      if (!q) return true;
      const fullText = (s.title + ' ' + (s.messages || []).map(m => m.text).join(' ')).toLowerCase();
      return fullText.includes(q);
    });
    const activeSessions = filtered.filter(s => !s.archived);
    const pinnedList = activeSessions.filter(s => s.pinned);
    const recentList = activeSessions.filter(s => !s.pinned);
    const archivedList = filtered.filter(s => s.archived);

    const listHtml = (activeSessions.length || archivedList.length) ? (
      (pinnedList.length ? `<div class="session-group-title">已置顶</div>${pinnedList.map(renderSessionItem).join('')}` : '') +
      (recentList.length ? `<div class="session-group-title">最近</div>${recentList.map(renderSessionItem).join('')}` : '') +
      `<details class="session-group-archived" ${state.archivedOpen || archivedList.some(s=>s.id===state.sessionId)?'open':''}>`+
        `<summary class="session-group-title session-archived-summary" data-toggle-archived>`+
          `<span class="archived-summary-left">${archiveIconSvg}<span>已归档对话 (${archivedList.length})</span></span>`+
          `<span class="archived-arrow">▾</span>`+
        `</summary>`+
        `<div class="archived-session-list">`+
          (archivedList.length ? archivedList.map(renderSessionItem).join('') : '<p class="panel-description panel-description-sm">暂无已归档对话</p>')+
        `</div>`+
      `</details>`
    ) : '<p class="panel-description">没有匹配的对话。</p>';

    const userFooterHtml = `<div class="doubao-user-profile" data-open-settings role="button" tabindex="0" title="点击打开系统设置">`+
      `<div class="user-avatar-wrap">${cartoonAvatarSvg}</div>`+
      `<div class="user-info">`+
        `<div class="user-name-row"><span class="user-nickname">学涯学习者</span><span class="user-arrow">›</span></div>`+
        `<span class="user-badge">AI 伴学中</span>`+
      `</div>`+
      `<button type="button" class="user-settings-btn" data-open-settings aria-label="系统设置" title="系统设置">`+
        `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`+
      `</button>`+
    `</div>`;

    return `<aside id="chatHistoryPanel" class="session-panel panel doubao-sidebar" aria-label="历史对话">`+
      `<div class="doubao-sidebar-header">`+
        `<div class="doubao-brand"><span class="doubao-brand-title">学涯 Copilot</span></div>`+
        `<div class="doubao-header-actions">`+
          `<button type="button" class="doubao-icon-btn ${state.sessionSearchOpen?'is-active':''}" data-toggle-session-search title="搜索历史对话" aria-label="搜索历史对话"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></button>`+
          `<button type="button" class="doubao-icon-btn history-mobile-close" data-history-close aria-label="关闭对话历史">×</button>`+
        `</div>`+
      `</div>`+
      `<button type="button" class="doubao-new-chat-btn" data-new-session aria-label="开启新对话" ${state.pending?'disabled':''}>`+
        `<span class="doubao-new-chat-icon"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></span>`+
        `<span class="doubao-new-chat-text">新对话</span>`+
        `<span class="doubao-new-chat-shortcut"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg></span>`+
      `</button>`+
      `<div class="doubao-search-box ${state.sessionSearchOpen||state.sessionQuery?'is-open':''}">`+
        `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" class="doubao-search-icon" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`+
        `<input class="filter-input doubao-search-input" id="sessionSearch" aria-label="搜索历史对话" placeholder="搜索标题与内容" value="${e(state.sessionQuery||'')}">`+
        (state.sessionQuery?`<button type="button" class="doubao-search-clear" data-clear-session-search aria-label="清空搜索">×</button>`:'')+
      `</div>`+
      `<div class="session-list">${listHtml}</div>`+
      userFooterHtml+
      `<div role="separator" aria-orientation="vertical" aria-label="调整对话历史宽度" aria-controls="chatHistoryPanel" tabindex="0" title="拖动调整宽度，双击恢复默认" data-history-resize></div>`+
    `</aside>`+
    `<button type="button" class="history-backdrop" data-history-close aria-label="关闭对话历史"></button>`;
  }
  function composer(){
    const voice=ctx.getVoiceState?.()||{phase:'idle'},recording=voice.phase==='recording',voiceBusy=['requesting','recording','transcribing'].includes(voice.phase),locked=state.pending||voiceBusy;
    const mic='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3"/></svg>';
    return `<form id="chatForm" class="composer"><label class="sr-only" for="chatInput">输入课程问题</label><textarea id="chatInput" aria-label="输入课程问题" placeholder="问一个问题，或选择一条旧回答继续追问…" rows="3" maxlength="4000">${e(state.draft)}</textarea>${state.followupIndex!==null&&state.followupIndex!==undefined?`<div class="reply-context">正在追问：${e(state.messages[state.followupIndex]?.title||'指定回答')}${button('取消','data-cancel-followup')}</div>`:''}<div class="attachment-list">${getAttachments().map((a,i)=>`<div class="image-attachment">${a.file.type.startsWith('audio/')||/\.(wav|mp3)$/i.test(a.file.name)?`<audio controls preload="metadata" src="${e(a.url)}" aria-label="待提问语音：${e(a.file.name)}"></audio>`:a.file.type.startsWith('image/')?`<img src="${e(a.url)}" alt="待提问图片：${e(a.file.name)}">`:'<span class="composer-file-icon" aria-hidden="true">'+icon('file')+'</span>'}<span>${e(a.file.name)}</span><button type="button" data-remove-image="${i}" aria-label="移除附件 ${e(a.file.name)}" ${locked?'disabled':''}>×</button></div>`).join('')}</div><input id="imageInput" type="file" accept="image/png,image/jpeg,image/webp,.pdf,.docx,.txt,.md,.markdown" multiple hidden><input id="audioInput" type="file" accept="audio/wav,audio/mpeg,.wav,.mp3" hidden><div class="composer-bottom"><div class="composer-tools"><button type="button" class="composer-icon-button composer-add" data-add-images aria-label="添加文件或图片" title="添加文件或图片（PDF、Word、TXT、Markdown）" ${locked?'disabled':''}><span aria-hidden="true">＋</span></button><button type="button" class="composer-icon-button composer-mic ${recording?'is-recording':''}" data-add-audio aria-label="${recording?'停止录音并识别':voice.phase==='transcribing'?'正在识别语音':'开始录音'}" title="录音停止后识别为文字，核对后发送" aria-pressed="${recording}" ${state.pending||['requesting','transcribing'].includes(voice.phase)?'disabled':''}>${recording?'<span class="record-stop" aria-hidden="true"></span>':mic}</button><button type="button" class="composer-web ${state.webSearch?'is-active':''}" data-toggle-web-search aria-label="全网搜索" title="${state.webSearch?'全网搜索已开启（联网获取最新信息）':'开启全网搜索（联网获取最新信息）'}" aria-pressed="${Boolean(state.webSearch)}" ${locked?'disabled':''}>🌐 <span class="web-search-text">全网搜索</span></button><span class="composer-note">${state.pending?'正在处理，可随时停止':getAttachments().length&&!window.XueyaPlatform?.available?'启动本地服务后可发送附件':'Enter 发送 · Shift + Enter 换行'}</span></div>${state.pending?'<button class="stop-button" type="button" data-stop-chat>停止生成</button>':`<button class="send-button" type="submit" aria-label="发送问题" ${voiceBusy?'disabled':''}>${icon('arrow')}</button>`}</div>${voice.phase!=='idle'?`<div class="composer-voice-status" role="status"><span data-voice-status>${e(voice.phase==='requesting'?'请允许浏览器使用麦克风…':recording?'正在录音 · 停止后识别，核对后发送':voice.phase==='transcribing'?'正在识别语音，识别后可编辑文字…':voice.error)}</span>${voice.phase==='error'&&voice.canRetry?button('重试识别','data-retry-voice'):''}${button('取消','data-cancel-voice')}</div>`:''}</form>`;
  }

  const XueyaDailyCheckin = {
    getToday: function() {
      const d = new Date();
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${y}-${m}-${day}`;
    },
    getYesterday: function() {
      const d = new Date();
      d.setDate(d.getDate() - 1);
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${y}-${m}-${day}`;
    },
    load: function() {
      try {
        const raw = localStorage.getItem('xueya_daily_checkin');
        if (raw) return JSON.parse(raw);
      } catch(e) {}
      return { streak: 0, total: 0, lastDate: '', history: [] };
    },
    save: function(data) {
      try {
        localStorage.setItem('xueya_daily_checkin', JSON.stringify(data));
      } catch(e) {}
    },
    getStatus: function() {
      const data = this.load();
      const today = this.getToday();
      const yesterday = this.getYesterday();
      const isCheckedToday = data.lastDate === today;
      let streak = Number(data.streak) || 0;
      if (!isCheckedToday && data.lastDate && data.lastDate !== yesterday) {
        streak = 0;
      }
      const history = Array.isArray(data.history) ? data.history : [];
      return {
        isCheckedToday,
        streak,
        total: data.total || history.length || 0,
        lastDate: data.lastDate,
        history
      };
    },
    checkin: function() {
      const status = this.getStatus();
      if (status.isCheckedToday) {
        return { already: true, streak: status.streak, total: status.total };
      }
      const today = this.getToday();
      const yesterday = this.getYesterday();
      const data = this.load();
      const wasYesterday = data.lastDate === yesterday;
      const newStreak = wasYesterday ? (Number(data.streak) || 0) + 1 : 1;
      const history = Array.isArray(data.history) ? [...data.history] : [];
      if (!history.includes(today)) history.push(today);
      const updated = {
        streak: newStreak,
        total: history.length,
        lastDate: today,
        history
      };
      this.save(updated);
      return { success: true, streak: newStreak, total: history.length, already: false };
    },
    getWeekDays: function(history) {
      const d = new Date();
      const currentDay = d.getDay();
      const mondayOffset = currentDay === 0 ? -6 : 1 - currentDay;
      const dayNames = ['一', '二', '三', '四', '五', '六', '日'];
      const todayStr = this.getToday();
      const week = [];
      for (let i = 0; i < 7; i++) {
        const target = new Date();
        target.setDate(d.getDate() + mondayOffset + i);
        const yr = target.getFullYear();
        const mo = String(target.getMonth() + 1).padStart(2, '0');
        const da = String(target.getDate()).padStart(2, '0');
        const dateStr = `${yr}-${mo}-${da}`;
        week.push({
          label: dayNames[i],
          dayNum: target.getDate(),
          dateStr,
          isToday: dateStr === todayStr,
          isPast: dateStr < todayStr,
          isChecked: history.includes(dateStr)
        });
      }
      return week;
    },
    celebrate: function(targetEl) {
      try {
        const card = document.querySelector('#dailyCheckinCard');
        if (card) {
          card.classList.remove('checkin-celebrating');
          void card.offsetWidth;
          card.classList.add('checkin-celebrating');
        }
        const rect = targetEl ? targetEl.getBoundingClientRect() : (card ? card.getBoundingClientRect() : null);
        const x = rect ? rect.left + rect.width / 2 : window.innerWidth / 3;
        const y = rect ? rect.top + rect.height / 2 : window.innerHeight / 3;
        const colors = ['#6366f1', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6'];
        for (let i = 0; i < 18; i++) {
          const p = document.createElement('div');
          p.className = 'checkin-confetti-particle';
          const angle = (Math.PI * 2 * i) / 18 + (Math.random() - 0.5) * 0.4;
          const dist = 35 + Math.random() * 55;
          const tx = Math.cos(angle) * dist;
          const ty = Math.sin(angle) * dist - 25;
          p.style.setProperty('--tx', `${tx}px`);
          p.style.setProperty('--ty', `${ty}px`);
          p.style.setProperty('--bg', colors[i % colors.length]);
          p.style.left = `${x}px`;
          p.style.top = `${y}px`;
          document.body.appendChild(p);
          setTimeout(() => p.remove(), 850);
        }
      } catch(e) {}
    }
  };
  globalThis.XueyaDailyCheckin = XueyaDailyCheckin;

  function renderCheckinWidget() {
    const status = XueyaDailyCheckin.getStatus();
    const week = XueyaDailyCheckin.getWeekDays(status.history);
    const weekHtml = week.map(day => {
      let statusClass = '';
      let iconMarkup = '';
      if (day.isChecked) {
        statusClass = 'is-checked';
        iconMarkup = '<svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
      } else if (day.isToday) {
        statusClass = 'is-today';
        iconMarkup = '<span class="today-dot"></span>';
      } else if (day.isPast) {
        statusClass = 'is-missed';
        iconMarkup = '';
      } else {
        statusClass = 'is-future';
        iconMarkup = '';
      }
      return `<div class="checkin-week-item ${statusClass}" title="${day.dateStr} (周${day.label})${day.isChecked ? ' · 已打卡' : (day.isToday ? ' · 今日待打卡' : '')}">`+
        `<span class="week-day-label">周${day.label}</span>`+
        `<div class="week-day-dot">${iconMarkup}</div>`+
      `</div>`;
    }).join('');

    return `<div class="overview-top-bar">`+
      `<div class="daily-checkin-card" id="dailyCheckinCard">`+
        `<div class="checkin-main-row">`+
          `<div class="checkin-icon-badge" aria-hidden="true">`+
            `<svg class="checkin-flame-icon" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">`+
              `<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>`+
            `</svg>`+
          `</div>`+
          `<div class="checkin-content">`+
            `<div class="checkin-title-line">`+
              `<span class="checkin-heading">每日打卡</span>`+
              `<span class="checkin-streak-tag">已坚持学习 <strong class="streak-num">${status.streak}</strong> 天</span>`+
            `</div>`+
            `<p class="checkin-subtitle">${status.isCheckedToday ? '今日已打卡 · 每天进步一点点' : '今日未打卡 · 坚持是最好的习惯'}</p>`+
          `</div>`+
          `<button type="button" class="checkin-action-btn ${status.isCheckedToday ? 'is-checked' : ''}" data-daily-checkin aria-label="${status.isCheckedToday ? '今日已打卡' : '立即打卡'}" title="${status.isCheckedToday ? '今日已打卡，明天继续保持！' : '点击完成今日学习打卡'}">`+
            (status.isCheckedToday ?
              `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg> <span>已打卡</span>` :
              `<span class="checkin-spark-icon" aria-hidden="true">✨</span> <span>立即打卡</span>`
            )+
          `</button>`+
        `</div>`+
        `<div class="checkin-week-bar" role="group" aria-label="本周打卡记录">`+
          weekHtml+
        `</div>`+
      `</div>`+
    `</div>`;
  }

  function overview(){
    const bottomBarHtml = `<div class="overview-bottom-bar">`+
      `<div class="overview-account-card" data-open-settings role="button" tabindex="0" title="点击打开系统设置">`+
        `<div class="user-avatar-wrap">${cartoonAvatarSvg}</div>`+
        `<div class="user-info">`+
          `<div class="user-name-row"><span class="user-nickname">学涯学习者</span><span class="user-arrow">›</span></div>`+
          `<span class="user-badge">AI 伴学中</span>`+
        `</div>`+
        `<button type="button" class="overview-settings-btn" data-open-settings aria-label="系统设置" title="系统设置">`+
          `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`+
          `<span>设置</span>`+
        `</button>`+
      `</div>`+
      `<a href="#home" class="overview-home-btn" title="回到首页">`+
        `<span>回到首页</span>`+
        `<span class="home-arrow" aria-hidden="true">↗</span>`+
      `</a>`+
    `</div>`;
    return renderCheckinWidget() + base.renders.overview().replace(/<form id="chatForm"[\s\S]*?<\/form>/,composer()) + bottomBarHtml;
  }

  function getFollowupQuestions(m, state) {
    if (Array.isArray(m.suggestedQuestions) && m.suggestedQuestions.length) {
      return m.suggestedQuestions;
    }
    const text = (m.text || '') + ' ' + (m.title || '');
    const questions = [];
    if (/二叉搜索树|BST|二叉树|树高|AVL|平衡树|红黑树/i.test(text)) {
      questions.push('如果二叉搜索树极度倾斜退化为链表，该如何恢复平衡？');
      questions.push('AVL 树与红黑树在插入和查找性能上有什么核心区别？');
      questions.push('如何在代码中用非递归方式实现二叉树遍历？');
    } else if (/快速排序|归并排序|堆排序|冒泡|排序算法|时间复杂度|O\(n/i.test(text)) {
      questions.push('快速排序在什么特殊数据分布下会退化到 O(n²)？');
      questions.push('归并排序和堆排序各自适用的工业级场景是什么？');
      questions.push('这几种排序算法的空间复杂度和稳定性如何对比？');
    } else if (/哈希|散列表|hash|冲突|拉链法|开放寻址/i.test(text)) {
      questions.push('哈希冲突的常见解决方式（拉链法 vs 开放寻址）各有什么优缺点？');
      questions.push('当哈希表的装载因子过高时，rehash 的渐进式扩容是如何实现的？');
      questions.push('在 Java HashMap 或 Python dict 中底层是如何优化的？');
    } else if (/进程|线程|死锁|互斥|并发|CPU|调度/i.test(text)) {
      questions.push('死锁产生的四个必要条件是什么，如何在设计中预防？');
      questions.push('进程上下文切换与线程切换在性能开销上有何本质差异？');
      questions.push('常见的进程间通信方式（IPC）有哪些，各自速度如何？');
    } else if (/TCP|UDP|握手|挥手|HTTP|网络/i.test(text)) {
      questions.push('为什么 TCP 挥手需要经历 TIME_WAIT 状态（2MSL）？');
      questions.push('TCP 的拥塞控制机制（慢启动、拥塞避免、快重传）是如何协同工作的？');
      questions.push('HTTP/2 的多路复用与 HTTP/3 基于 QUIC 的改进有什么关键点？');
    } else if (/动态规划|DP|背包|贪心|状态转移/i.test(text)) {
      questions.push('如何判断一个问题是否满足“最优子结构”和“重叠子问题”？');
      questions.push('动态规划的状态转移方程在推导时有哪些系统化的思路？');
      questions.push('空间压缩技巧：如何将二维 DP 数组优化为一维？');
    } else {
      const prevUser = [...(state.messages || [])].reverse().find(msg => msg.role === 'user' && msg.text !== m.title);
      if (prevUser && prevUser.text) {
        questions.push(`结合刚才讨论的「${prevUser.text.slice(0, 16)}」，这个方案有什么优化空间？`);
      } else {
        questions.push('能为我针对刚才解释的要点，出一道经典考查题吗？');
      }
      questions.push('在实际工业生产环境或大型项目中，通常怎么落地该技术？');
      questions.push('这个概念最容易混淆的误区或踩坑点有哪些？');
    }
    m.suggestedQuestions = questions.slice(0, 3);
    return m.suggestedQuestions;
  }

  function getInitialCourseSuggestions(state) {
    const list = [];
    const docs = state.documents || [];
    const docNames = docs.map(d => d.name).join(' ');

    if (/树|二叉/i.test(docNames) || state.courseId === 'course-default') {
      list.push('二叉搜索树查找的时间复杂度为什么是 O(log n)？');
      list.push('平衡二叉树（AVL）失衡时如何进行单旋和双旋？');
      list.push('红黑树相比 AVL 树为什么在插入删除频繁时性能更好？');
      list.push('哈夫曼树的构造规则与带权路径长度（WPL）如何计算？');
    } else if (/系统|进程|内存/i.test(docNames)) {
      list.push('进程与线程的核心区别及各自的内存模型是什么？');
      list.push('虚拟内存分页管理中，快表（TLB）是如何加速地址转换的？');
      list.push('死锁的四大必要条件是什么，有哪些常用的预防策略？');
    } else if (/网络|TCP|HTTP/i.test(docNames)) {
      list.push('为什么 TCP 握手需要三次，而挥手需要四次？');
      list.push('TCP 拥塞控制机制（慢启动、拥塞避免、快重传）是如何协同工作的？');
      list.push('HTTP/2 与 HTTP/3 在解决队头阻塞上有何不同策略？');
    } else {
      list.push('二叉搜索树的查找复杂度与二分查找有什么联系？');
      list.push('快速排序在什么情况下会发生性能退化？');
      list.push('如何用动态规划求解经典的 0-1 背包问题？');
      list.push('哈希冲突时拉链法与开放寻址法各自适用的场景是什么？');
    }

    // Inspect history memory from past sessions
    const pastUserQuestions = (state.sessions || [])
      .filter(s => s.id !== state.sessionId)
      .flatMap(s => (s.messages || []).filter(m => m.role === 'user').map(m => m.text))
      .filter(Boolean);

    if (pastUserQuestions.length) {
      const recent = pastUserQuestions[pastUserQuestions.length - 1];
      if (recent && !list.includes(recent)) {
        list.unshift(`继续深入探索上次学习的：「${recent.slice(0, 20)}」`);
      }
    }
    return list.slice(0, 4);
  }

  function getSelectionQuestions(rawText) {
    const text = (rawText || '').trim();
    if (/树|AVL|红黑树|平衡/i.test(text)) {
      return [
        '为什么需要这种平衡机制，与普通二叉树有何区别？',
        '失衡调整时的旋转操作与复杂度是如何保证的？',
        '在工业级软件（如数据库/Linux内核）中如何应用？',
        '有哪些经典考查题型与易错点？'
      ];
    }
    if (/O\(|复杂度|时间|空间/i.test(text)) {
      return [
        '最坏情况、最好情况与均摊复杂度各是多少？',
        '在海量数据或极端分布下是否会发生性能退化？',
        '有没有空间换时间或进一步常数级优化的策略？',
        '如何通过推导或数学归纳法证明这一复杂度？'
      ];
    }
    if (/TCP|HTTP|网络|握手|协议/i.test(text)) {
      return [
        '该协议机制的设计初衷和要解决的核心痛点是什么？',
        '报文交互的具体流程与状态转换是怎样的？',
        '当网络出现丢包、超时或高延迟时如何应对？',
        '与其它同类协议相比有什么优劣势？'
      ];
    }
    if (/进程|线程|锁|并发|内存/i.test(text)) {
      return [
        '它在操作系统底层是如何调度和分配资源的？',
        '高并发场景下可能产生什么竞态条件或死锁风险？',
        '硬件 CPU 或内核做了哪些加速优化？',
        '有什么最佳实践来保障并发安全性？'
      ];
    }
    return [
      '请用通俗的语言深度剖析其核心含义',
      '它的工作底层原理与算法执行流程是什么？',
      '在实际生产工程或系统设计中有哪些应用？',
      '有哪些常见的设计陷阱或易错考点？'
    ];
  }

  function sidebarAskPanel() {
    return `<aside id="chatSidebarAskPanel" class="chat-sidebar-ask-panel ${state.sidebarAskOpen?'is-open':''}" aria-label="侧边栏划词提问" ${state.sidebarAskOpen?'':'hidden'}>`+
      `<div class="sidebar-ask-header">`+
        `<div class="sidebar-ask-title-group">`+
          `<span class="sidebar-ask-badge">划词提问</span>`+
          `<h3 class="sidebar-ask-title">侧边提问助手</h3>`+
        `</div>`+
        `<button type="button" class="sidebar-ask-close" data-close-sidebar-ask aria-label="关闭侧边提问">×</button>`+
      `</div>`+
      `<div class="sidebar-ask-body">`+
        (state.sidebarAskText ? `
          <div class="sidebar-ask-quote-card">
            <div class="quote-card-header">
              <span class="quote-icon">“</span>
              <span>选中的重点内容</span>
            </div>
            <blockquote class="quote-card-text">${e(state.sidebarAskText)}</blockquote>
          </div>
          <div class="sidebar-ask-prompt-section">
            <div class="sidebar-section-title">
              <span class="sparkle-icon">💡</span>
              <span>针对所选词句的提问推荐：</span>
            </div>
            <div class="sidebar-prompt-chips">
              ${getSelectionQuestions(state.sidebarAskText).map(q => `
                <button type="button" class="sidebar-suggest-chip" data-sidebar-quick-ask="${e(q)}" data-prompt="关于「${e(state.sidebarAskText.length > 50 ? state.sidebarAskText.slice(0, 50) + '…' : state.sidebarAskText)}」：${e(q)}" title="点击立即向 Copilot 提问">
                  <span>${e(q)}</span>
                  <span class="chip-arrow">↗</span>
                </button>
              `).join('')}
            </div>
          </div>
        ` : `
          <div class="sidebar-ask-empty-guide">
            <div class="empty-guide-icon">💡</div>
            <h4>划词提问助手已就绪</h4>
            <p>在左侧对话中用鼠标划选任意词句，点击浮动菜单中的<strong>【侧边提问】</strong>，即可针对所选内容在此深度剖析。</p>
          </div>
        `)+
        `<form id="sidebarAskForm" class="sidebar-ask-form">`+
          `<label class="sr-only" for="sidebarAskInput">侧边提问输入框</label>`+
          `<textarea id="sidebarAskInput" class="sidebar-ask-textarea" placeholder="${state.sidebarAskText ? '输入你想对选中内容具体追问的问题…' : '输入你想提问的课程问题…'}" rows="3" maxlength="4000">${e(state.sidebarAskDraft||'')}</textarea>`+
          `<div class="sidebar-ask-actions">`+
            (state.sidebarAskText ? `<button type="button" class="button button-outline button-small" data-sidebar-fill-composer>填入主输入框</button>` : '')+
            `<button type="submit" class="button button-blue button-small" ${state.pending?'disabled':''}>立即提问</button>`+
          `</div>`+
        `</form>`+
      `</div>`+
    `</aside>`;
  }

  function message(m,index){
    if(m.role==='user')return `<article class="message user-message"><div class="message-body">${m.images?.length?`<div class="sent-image-gallery">${m.images.map(ref=>`<button type="button" class="sent-image-thumb" data-message-image="${e(ref.key)}" title="${e(ref.name)}" aria-label="放大图片 ${e(ref.name)}"><img data-sent-image="${e(ref.key)}" ${ctx.getMessageImage?.(ref)?`src="${e(ctx.getMessageImage(ref))}"`:'hidden'} alt="${e(ref.name)}" title="${e(ref.name)}"><span data-image-missing ${ctx.getMessageImage?.(ref)?'hidden':''}>${e(ref.name)} · 读取图片</span></button>`).join('')}</div>`:''}<p>${e(m.text)}</p>${(m.attachmentNames||m.imageNames)?.length?`<small>附件：${(m.attachmentNames||m.imageNames).map(e).join('、')}</small>`:''}${m.transcript?`<details><summary>已核对的语音文字</summary><p>${e(m.transcript)}</p></details>`:''}</div></article>`;
    const interactive=Boolean(state.agentFeatures?.interactive&&state.agentFeatures?.configured);
    const isThinking=m.engine==='正在回答';
    const durationSec=Number.isFinite(m.thinkingSeconds)?m.thinkingSeconds:Number.isFinite(m.timings?.phasesMs?.evidenceReview||m.timings?.totalMs)?Math.max(1,Math.round((m.timings.phasesMs?.evidenceReview||m.timings?.totalMs)/1000)):null;
    const hasReasoning=Boolean(m.reasoning||(isThinking&&(m.progress||!m.text)));
    const thinkingLabel=isThinking?(m.reasoning?'思考中…':(m.progress||'思考中…')):('已深度思考'+(durationSec?` (用时 ${durationSec} 秒)`:''));
    const thinkingText=m.reasoning||m.progress||'正在思考并核查课程依据…';
    const thinkingBlock=hasReasoning?`<details class="thinking-box" ${isThinking?'open':''}><summary class="thinking-summary"><span class="thinking-spark">✳</span><span class="thinking-label">${e(thinkingLabel)}</span><span class="thinking-arrow">▾</span></summary><div class="thinking-content">${e(thinkingText)}</div></details>`:'';
    const renderedBody=m.text?rich.render(m.text):(isThinking&&!hasReasoning?'<p class="streaming-placeholder">正在组织回答…</p>':'');
    const isReadingThis=Boolean(ctx.isSpeaking?.(m.text)||globalThis.XueyaTTS?.isPlaying?.(m.text));
    const myFeedback=state.feedback?.find(f=>f.messageId===(m.id||String(index)));
    const copySvg='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
    const ttsSvg=isReadingThis?'<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><rect x="15" y="9" width="6" height="6" rx="1" fill="currentColor"/></svg>':'<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>';
    const thumbUpSvg=`<svg viewBox="0 0 24 24" width="16" height="16" fill="${myFeedback?.rating==='helpful'?'currentColor':'none'}" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>`;
    const thumbDownSvg=`<svg viewBox="0 0 24 24" width="16" height="16" fill="${myFeedback?.rating==='unhelpful'?'currentColor':'none'}" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>`;
    const alertSvg=`<svg viewBox="0 0 24 24" width="16" height="16" fill="${myFeedback?.rating==='incorrect'?'currentColor':'none'}" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
    const branchSvg='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>';
    const regenSvg='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>';
    const actionButtons=!isThinking&&!m.failed&&!m.cancelled?`<div class="message-actions doubao-action-bar" role="toolbar" aria-label="回答操作"><button type="button" class="action-icon-btn" data-copy-message="${index}" title="复制回答" aria-label="复制回答">${copySvg}</button><button type="button" class="action-icon-btn ${isReadingThis?'is-playing':''}" data-tts-read="${index}" title="${isReadingThis?'停止朗读':'语音朗读'}" aria-label="${isReadingThis?'停止朗读':'语音朗读'}">${ttsSvg}</button><button type="button" class="action-icon-btn ${myFeedback?.rating==='helpful'?'is-active is-helpful':''}" data-feedback="${index}" data-rating="helpful" title="赞" aria-label="赞">${thumbUpSvg}</button><button type="button" class="action-icon-btn ${myFeedback?.rating==='unhelpful'?'is-active is-unhelpful':''}" data-feedback="${index}" data-rating="unhelpful" title="踩" aria-label="踩">${thumbDownSvg}</button><button type="button" class="action-icon-btn" data-branch="${index}" title="新建分支（从此处开启新对话）" aria-label="新建分支（从此处开启新对话）">${branchSvg}</button><button type="button" class="action-icon-btn action-icon-warn ${myFeedback?.rating==='incorrect'?'is-active':''}" data-feedback="${index}" data-rating="incorrect" title="引用或内容有误（报错）" aria-label="引用或内容有误（报错）">${alertSvg}</button><button type="button" class="action-icon-btn" data-regenerate="${index}" title="重新生成" aria-label="重新生成">${regenSvg}</button></div>`:'';
    const followupBlock = (!isThinking && !m.failed && !m.cancelled && m.text && !m.artifacts?.studyPlanning && !m.artifacts?.quiz) ?
      `<div class="suggested-followup-box" data-parent-index="${index}"><div class="suggested-followup-title"><span class="suggested-spark">✦</span><span>用户可能会提问的问题：</span></div><div class="suggested-chips">${getFollowupQuestions(m, state).map(q => `<button type="button" class="suggested-chip" data-prompt="${e(q)}" title="点击直接向 Copilot 提问"><span>${e(q)}</span><span class="chip-arrow" aria-hidden="true">↗</span></button>`).join('')}</div></div>` : '';
    return `<article class="message ai-message ${isThinking?'loading-message':''}" data-message-index="${index}"><div class="message-avatar">${icon('spark')}</div><div class="message-body"><div class="message-meta"><strong>学涯 Copilot</strong><span ${isThinking?'hidden':''}>${e(m.engine||'本地检索摘录')} · ${m.sources?.length||0} 个来源${Number.isFinite(m.timings?.totalMs)?' · '+(m.timings.totalMs/1000).toFixed(1)+' 秒':''}</span></div>${thinkingBlock}<div class="rich-content">${renderedBody}${isThinking&&m.text?'<span class="stream-cursor" aria-hidden="true"></span>':''}</div>${citations(m.sources)}${globalThis.XueyaStudyChat?.markup(m)||''}${globalThis.XueyaStudyQuiz?.markup(m)||''}${globalThis.XueyaAgentRuns?.markup(m,index,interactive)||''}${actionButtons}${followupBlock}</div></article>`;
  }
  function explicitScope(){try{const v=JSON.parse(localStorage.getItem((window.XueyaDataKey||((key)=>key))('xueya-c-learning:'+state.courseId+':scope:'+state.sessionId)));return Array.isArray(v)?v:null;}catch{return null;}}
  function chat(){
    return `<div class="chat-history-toolbar"><button type="button" class="button button-outline button-small history-mobile-toggle" data-history-open aria-controls="chatHistoryPanel" aria-expanded="false">对话历史</button></div>`+
      `<div class="workspace-chat">${sessions()}<div class="chat-main">`+
        `<div class="chat-top-external-bar" role="toolbar" aria-label="快捷操作">`+
          `<button type="button" class="sidebar-ext-btn sidebar-toggle-btn" data-toggle-sidebar title="收起/展开侧边栏" aria-label="收起/展开侧边栏"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4" ry="4"/><line x1="9" y1="3" x2="9" y2="21"/></svg></button>`+
          `<button type="button" class="sidebar-ext-btn sidebar-new-btn" data-new-session title="新对话" aria-label="开启新对话" ${state.pending?'disabled':''}><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>`+
          `<button type="button" class="sidebar-ext-btn sidebar-ask-btn ${state.sidebarAskOpen?'is-active':''}" data-toggle-sidebar-ask title="打开/收起划词提问侧边栏" aria-label="打开/收起划词提问侧边栏"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="12" y1="7" x2="12" y2="13"/></svg></button>`+
        `</div>`+
        `<div class="chat-mode-tabs" role="group" aria-label="问答模式">${[['ask','资料问答'],['summarize','知识整理'],['quiz','开放练习']].map(([mode,label])=>`<button type="button" class="${mode===state.mode?'active':''}" aria-pressed="${mode===state.mode}" data-mode="${mode}">${label}</button>`).join('')}${button('新对话','data-clear-chat '+(state.pending?'disabled':''))}</div>`+
        `<details class="scope-picker"><summary>资料范围：${explicitScope()!==null?explicitScope().length+' 份资料':state.selectedDocuments.length?state.selectedDocuments.length+' 份资料':'当前课程全部有效资料'}</summary><div>${state.documents.filter(d=>!d.superseded&&!d.archived).map(d=>`<label><input type="checkbox" data-scope="${e(d.id)}" ${(explicitScope()===null&&!state.selectedDocuments.length||state.selectedDocuments.includes(d.id))?'checked':''} ${state.pending?'disabled':''}>${e(d.name)}</label>`).join('')||'<p>请先添加资料。</p>'}</div></details>`+
        `<div class="chat-thread" id="chatThread" data-session-id="${e(state.sessionId)}" tabindex="0" aria-label="对话记录" aria-live="polite" aria-busy="${state.pending}">${state.messages.length?state.messages.map(message).join(''):`<div class="chat-empty"><span class="chat-empty-symbol">${icon('spark')}</span><h2>从一个问题开始，走向真正理解。</h2><p>围绕课程资料与计算机核心知识点，学涯 Copilot 为你逐层剖析依据。</p><div class="chat-starter-suggested"><div class="starter-suggested-header"><span class="starter-spark">✦</span><span>猜你想问 · 根据课程与历史记忆推荐：</span></div><div class="starter-chips">${getInitialCourseSuggestions(state).map(q => `<button type="button" class="suggested-chip" data-prompt="${e(q)}" title="点击直接提问"><span>${e(q)}</span><span class="chip-arrow" aria-hidden="true">↗</span></button>`).join('')}</div></div><div class="chat-empty-links"><a class="text-link" href="#space/knowledge">整理课程资料 →</a><a class="text-link" href="#space/courses">进入课程视频学堂 →</a></div></div>`}</div>`+
        composer()+
      `</div>`+sidebarAskPanel()+`</div>`;
  }
  function documentRows(query=''){
    const list=state.documents.filter(d=>(!globalThis.XueyaPlatform?.available||!d.remote)&&((d.name+' '+(d.tags||[]).join(' ')+' '+(d.chapter||'')).toLowerCase().includes(query.toLowerCase())));
    return list.length?list.map(d=>`<article class="document-row ${d.superseded?'document-history':''}"><span class="document-icon">${icon('file')}</span><div class="document-copy"><strong>${e(d.name)}</strong><small>${e(d.meta||'')} · v${Number(d.version)||1}${d.superseded?' · 历史版本':''}</small><div class="document-tags">${(d.tags||[]).map(t=>`<span>${e(t)}</span>`).join('')}${d.chapter?`<span>${e(d.chapter)}</span>`:''}</div></div><span class="status-pill ${!d.chunks?.length&&!L.sources.some(s=>s.documentId===d.id)?'pending':''}">${e(d.status)}</span><div class="row-actions">${d.chunks?.length&&!d.superseded?button('生成题库',`data-generate-questions="${e(d.id)}"`):''}${button('原文',`data-document="${e(d.id)}" aria-label="查看 ${e(d.name)}"`)}${button('整理',`data-edit-document="${e(d.id)}"`)}${!L.documents.some(s=>s.id===d.id)?`${button('新版本',`data-version-document="${e(d.id)}"`)}${!d.chunks?.length?button('重选原件',`data-retry-document="${e(d.id)}"`):''}${button('移除',`data-remove-document="${e(d.id)}" aria-label="移除 ${e(d.name)}"`)}`:''}</div></article>`).join(''):'<div class="empty-state"><h2>这里还没有资料</h2><p>添加讲义或笔记，也可换个关键词搜索。</p></div>';
  }
  function queue(){return getQueue().length?`<section class="panel upload-progress" aria-label="资料处理进度"><h2>资料处理</h2>${getQueue().map(item=>`<div class="queue-item"><strong>${e(item.name)}</strong><span role="status">${e(item.status)}</span><progress max="100" value="${item.progress}" aria-label="${e(item.name)}处理进度"></progress>${item.failed?button('重试',`data-retry-upload="${e(item.id)}"`):''}</div>`).join('')}</section>`:'';}
  function library(){const local=state.documents.filter(d=>!d.remote);return `${heading('课程资料','上传讲义或笔记，开始学习。')}<input type="file" id="fileInput" accept=".txt,.md,.pdf,.docx${service.capabilities.uploadDocument?',.pptx':''}" multiple hidden><div class="upload-zone library-primary-upload" id="uploadZone"><div class="upload-zone-left">${icon('upload')}<div><h2>上传你的课程资料</h2><p>支持拖入文件或批量选择 · TXT / MD / PDF / DOCX${service.capabilities.uploadDocument?' / PPTX':''}</p></div></div>${button('上传资料','data-upload','button-blue')}</div><div id="uploadProgress">${queue()}</div><details id="localLibraryRecords" class="library-local-records"><summary>内置示例与本地旧资料 · ${local.length} 份</summary><section class="panel"><div class="list-toolbar"><input type="search" class="filter-input" id="librarySearch" placeholder="搜索本地资料" aria-label="搜索课程资料" value="${e(state.libraryQuery)}"></div><div id="documentList">${documentRows(state.libraryQuery)}</div></section></details><p class="library-note">上传后自动解析并显示在下方。扫描件需要配置文字识别服务。</p>`;}
  function practice(){return base.renders.practice();}
  function review(){return base.renders.review();}
  function media(){return `${heading('图片、声音，也能成为学习材料。','选择文件后预览，再交给已接通的学习服务。')}<div class="media-grid">${[['transcribe','课程录音','audio/*','上传音频并转写'],['video','课程片段','video/*','提取片段要点']].map(([name,title,accept,label])=>`<section class="panel media-panel"><h2>${title}</h2><p class="panel-description">${name==='transcribe'?'保留原音频与实际片段时间，转写可修改。':'片段分析会标明实际采样与时间，不等于观察所有帧。'}</p><label class="form-field">选择本地文件<input type="file" data-media-file="${name}" accept="${accept}"></label><span class="media-filename">${e(state.mediaFiles?.[name]||'尚未选择文件')}</span>${state.mediaPreviews?.[name]?`<${name==='video'?'video':'audio'} id="mediaPreview-${name}" class="media-preview" controls preload="metadata" src="${e(state.mediaPreviews[name])}" aria-label="本地${title}预览"></${name==='video'?'video':'audio'}>`:''}${button(label,`data-media-run="${name}" ${service.capabilities[name]?'':'disabled'}`,'button-blue')}${service.capabilities[name]?'':unavailable(title+'服务')}</section>`).join('')}<section class="panel media-panel"><h2>语音讲解</h2><label class="form-field">想听的内容<textarea id="speechText" rows="4" maxlength="6000" placeholder="粘贴或输入需要讲解的重点">${e(state.speechText||'')}</textarea></label>${button('生成语音',`data-media-run="speak" ${service.capabilities.speak?'':'disabled'}`,'button-blue')}${service.capabilities.speak?'':unavailable('语音合成')}</section><section class="panel media-panel"><h2>拍照与图表问答</h2><p class="panel-description">在资料问答中添加图片，选择课程资料作为依据；先确认图像服务已接通。</p><a class="button button-outline button-small" href="#space/ask">进入图文问答 →</a>${service.capabilities.imageChat?'':unavailable('图像理解')}</section></div><div id="mediaJob">${state.mediaJob?`<section class="panel media-job" role="status"><strong>${e(state.mediaJob.label)}</strong>${state.mediaJob.running?button('停止处理','data-stop-media'):''}${state.mediaJob.error?`<p>${e(state.mediaJob.error)}</p>`:''}</section>`:''}</div>${state.mediaResults?.length?`<section class="panel media-results"><h2>处理结果</h2>${state.mediaResults.map((r,i)=>`<article><h3>${e(r.title)}</h3><div class="rich-content">${rich.render(r.text)}</div>${r.audioURL?`<audio controls src="${e(r.audioURL)}"></audio>`:''}${Array.isArray(r.segments)?r.segments.map(s=>`<p>${Number.isFinite(Number(s.start))&&r.inputToken&&r.inputToken===state.mediaTokens?.[r.kind]?button(Number(s.start).toFixed(1)+'s',`data-seek-media="${i}" data-seconds="${Math.max(0,Number(s.start))}"`):Number.isFinite(Number(s.start))?Number(s.start).toFixed(1)+'s':'时间未提供'} · ${e(s.text)}</p>`).join(''):''}${button('编辑并保存笔记',`data-media-note="${i}"`)}</article>`).join('')}</section>`:''}`;}
  return{titles:{...base.titles,media:'录音与视频工具'},renders:{...base.renders,overview,ask:chat,chat,library,practice,review,media},documentRows,currentQuestions:base.currentQuestions};
}
return{createViews};
});
