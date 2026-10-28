/* Floating action tooltip on text selection (Doubao-style): Copy, Read Aloud (TTS with mimo-v2.5-tts), Follow-up */
(() => {
  'use strict';

  // --- TTS Engine (mimo-v2.5-tts with browser Web Speech fallback) ---
  const listeners = new Set();
  let activeAudio = null;
  let activeUtterance = null;
  let speechRequest = null;
  let playbackVersion = 0;
  let currentText = '';
  let status = 'idle'; // 'idle' | 'loading' | 'playing'

  function cleanSpeechText(text) {
    if (!text) return '';
    let t = String(text);
    t = t.replace(/```[\s\S]*?```/g, '代码片段已省略。');
    t = t.replace(/`([^`]+)`/g, '$1');
    t = t.replace(/\[\d+\]/g, '');
    t = t.replace(/[*#_~>|]/g, '');
    t = t.replace(/https?:\/\/[^\s]+/g, '网页链接');
    t = t.replace(/\s+/g, ' ').trim();
    return t;
  }

  function notify() {
    for (const fn of listeners) {
      try { fn(status, currentText); } catch {}
    }
  }

  function stopTTS() {
    playbackVersion++;
    speechRequest?.abort();
    speechRequest = null;
    if (activeAudio) {
      activeAudio.pause();
      activeAudio.src = '';
      activeAudio.onplay = null;
      activeAudio.onended = null;
      activeAudio.onerror = null;
      activeAudio = null;
    }
    if ('speechSynthesis' in window) {
      if (activeUtterance) activeUtterance.onstart = activeUtterance.onend = activeUtterance.onerror = null;
      try { window.speechSynthesis.cancel(); } catch {}
      activeUtterance = null;
    }
    status = 'idle';
    currentText = '';
    notify();
  }

  function fallbackSpeech(text) {
    if (!('speechSynthesis' in window)) {
      stopTTS();
      (window.toast || alert)('当前浏览器环境不支持语音朗读');
      return;
    }
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'zh-CN';
      u.rate = 1.0;
      u.pitch = 1.0;
      activeUtterance = u;
      u.onstart = () => {
        status = 'playing';
        notify();
      };
      u.onend = () => {
        stopTTS();
      };
      u.onerror = () => {
        stopTTS();
      };
      window.speechSynthesis.speak(u);
    } catch {
      stopTTS();
    }
  }

  async function speakText(rawText) {
    const text = cleanSpeechText(rawText);
    if (!text) return;

    if (status !== 'idle' && currentText === rawText) {
      stopTTS();
      return;
    }

    stopTTS();
    const version = playbackVersion;
    const controller = new AbortController();
    speechRequest = controller;
    status = 'loading';
    currentText = rawText;
    notify();

    // 1. Try backend MiMo TTS (mimo-v2.5-tts)
    try {
      const bootstrap = await fetch('/api/platform/bootstrap', {signal: controller.signal});
      if (!bootstrap.ok) throw Error('TTS_BOOTSTRAP_UNAVAILABLE');
      const credentials = await bootstrap.json();
      if (version !== playbackVersion) return;
      const resp = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Xueya-Token': credentials.token },
        signal: controller.signal,
        body: JSON.stringify({ text: text.slice(0, 1000), voice: 'mimo_default' })
      });
      if (version !== playbackVersion) return;
      if (resp.ok) {
        const data = await resp.json();
        if (version !== playbackVersion) return;
        if (data.ok && data.audio) {
          const audio = new Audio(data.audio);
          activeAudio = audio;
          audio.onplay = () => {
            status = 'playing';
            notify();
          };
          audio.onended = () => {
            stopTTS();
          };
          audio.onerror = () => {
            activeAudio = null;
            fallbackSpeech(text);
          };
          await audio.play();
          return;
        }
      }
    } catch {
      if (controller.signal.aborted || version !== playbackVersion) return;
      // Backend unavailable or network error -> fallback
    }

    // 2. Fallback to Web Speech API
    if (version === playbackVersion) fallbackSpeech(text);
  }

  window.XueyaTTS = {
    speak: speakText,
    stop: stopTTS,
    isPlaying: (text) => (status === 'playing' || status === 'loading') && (!text || currentText === text),
    getStatus: () => status,
    getCurrentText: () => currentText,
    subscribe: (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    }
  };

  // --- Floating Selection Menu ---
  let menuEl = null;
  let currentSelectionText = '';
  let currentMessageEl = null;
  let isPointerSelecting = false;
  let hideTimer = null;

  function ensureMenu() {
    if (menuEl) return menuEl;
    menuEl = document.createElement('div');
    menuEl.id = 'selectionTooltip';
    menuEl.className = 'selection-tooltip';
    menuEl.setAttribute('role', 'toolbar');
    menuEl.setAttribute('aria-label', '选中文本操作');
    menuEl.hidden = true;

    menuEl.innerHTML = `
      <button type="button" class="selection-tooltip-btn" data-action="copy" title="复制选中文本">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
        <span>复制</span>
      </button>
      <div class="selection-tooltip-divider"></div>
      <button type="button" class="selection-tooltip-btn" data-action="read" title="朗读选中文本 (mimo-v2.5-tts)">
        <svg class="tts-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>
        <span class="tts-label">朗读</span>
      </button>
      <div class="selection-tooltip-divider"></div>
      <button type="button" class="selection-tooltip-btn" data-action="followup" title="基于所选内容进行追问">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 10 4 15 9 20"></polyline><path d="M20 4v7a4 4 0 0 1-4 4H4"></path></svg>
        <span>追问</span>
      </button>
    `;

    document.body.appendChild(menuEl);

    menuEl.addEventListener('mousedown', (e) => {
      // Prevent clicking the menu from clearing the selection
      e.preventDefault();
    });

    menuEl.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const action = btn.dataset.action;
      handleMenuAction(action);
    });

    // Update TTS button state when TTS plays/stops
    window.XueyaTTS.subscribe((st, txt) => {
      if (!menuEl) return;
      const readBtn = menuEl.querySelector('[data-action="read"]');
      if (!readBtn) return;
      const isReadingThis = (st === 'playing' || st === 'loading') && txt === currentSelectionText;
      readBtn.classList.toggle('is-playing', isReadingThis);
      const label = readBtn.querySelector('.tts-label');
      if (label) {
        label.textContent = isReadingThis ? (st === 'loading' ? '加载中' : '停止') : '朗读';
      }
    });

    return menuEl;
  }

  function hideMenu() {
    if (!menuEl || menuEl.hidden) return;
    menuEl.classList.remove('is-visible');
    hideTimer = setTimeout(() => {
      if (menuEl) menuEl.hidden = true;
    }, 150);
  }

  function showMenuAt(rect) {
    ensureMenu();
    clearTimeout(hideTimer);
    menuEl.hidden = false;

    // Trigger reflow for transition
    void menuEl.offsetWidth;

    const menuWidth = menuEl.offsetWidth || 184;
    const menuHeight = menuEl.offsetHeight || 34;

    let top = rect.top - menuHeight - 8;
    let left = rect.left + rect.width / 2;

    // If too close to viewport top, show below selection
    if (top < 10) {
      top = rect.bottom + 8;
    }

    // Keep horizontally within viewport boundaries
    const halfWidth = menuWidth / 2;
    if (left - halfWidth < 12) {
      left = halfWidth + 12;
    } else if (left + halfWidth > window.innerWidth - 12) {
      left = window.innerWidth - halfWidth - 12;
    }

    menuEl.style.top = Math.round(top) + 'px';
    menuEl.style.left = Math.round(left) + 'px';
    menuEl.classList.add('is-visible');

    // Update read button label if already playing
    const readBtn = menuEl.querySelector('[data-action="read"]');
    if (readBtn) {
      const isReadingThis = window.XueyaTTS.isPlaying(currentSelectionText);
      readBtn.classList.toggle('is-playing', isReadingThis);
      const label = readBtn.querySelector('.tts-label');
      if (label) label.textContent = isReadingThis ? '停止' : '朗读';
    }
  }

  function checkSelection() {
    if (isPointerSelecting) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
      hideMenu();
      return;
    }

    const text = selection.toString().trim();
    if (!text || text.length < 1) {
      hideMenu();
      return;
    }

    const range = selection.getRangeAt(0);
    const container = range.commonAncestorContainer;
    const el = container.nodeType === Node.ELEMENT_NODE ? container : container.parentElement;

    // Do NOT trigger inside inputs or textareas or settings
    if (el.closest('input, textarea, [contenteditable="true"], .composer')) {
      hideMenu();
      return;
    }

    // Trigger only for messages and chat thread
    const messageBody = el.closest('.message-body, .chat-thread, .rich-content, .workspace-chat');
    if (!messageBody) {
      hideMenu();
      return;
    }

    currentSelectionText = text;
    currentMessageEl = el.closest('.message');

    const rect = range.getBoundingClientRect();
    if (!rect || (rect.width === 0 && rect.height === 0)) {
      hideMenu();
      return;
    }

    showMenuAt(rect);
  }

  function handleMenuAction(action) {
    const text = currentSelectionText;
    if (!text) {
      hideMenu();
      return;
    }

    if (action === 'copy') {
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(text).catch(() => {});
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        try { document.execCommand('copy'); } catch {}
        textarea.remove();
      }
      (window.toast || alert)('已复制选中文本');
      hideMenu();
    } else if (action === 'read') {
      window.XueyaTTS.speak(text);
    } else if (action === 'followup') {
      const msgIndex = currentMessageEl?.dataset?.messageIndex !== undefined ? Number(currentMessageEl.dataset.messageIndex) : null;
      window.dispatchEvent(new CustomEvent('xueya:followup-selection', {
        detail: {
          text,
          messageIndex: Number.isInteger(msgIndex) ? msgIndex : null
        }
      }));
      hideMenu();
    }
  }

  // --- Global Event Bindings ---
  document.addEventListener('pointerdown', (e) => {
    if (e.target.closest('#selectionTooltip')) return;
    isPointerSelecting = true;
  });

  document.addEventListener('pointerup', () => {
    isPointerSelecting = false;
    setTimeout(checkSelection, 30);
  });

  document.addEventListener('selectionchange', () => {
    if (!isPointerSelecting) {
      setTimeout(checkSelection, 50);
    }
  });

  window.addEventListener('resize', hideMenu);
  window.addEventListener('scroll', hideMenu, true);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideMenu();
  });
})();
