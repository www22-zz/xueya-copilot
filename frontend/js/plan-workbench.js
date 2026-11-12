/* Personalized learning workbench: goal form, program-side schedule projection,
   durable plan generation over the existing /api/learning/space/plan/generate
   job, generated draft review, adoption and study-route mind-map export.
   Data shown here comes from the local API; the right-hand projection is a
   program estimate only and never imitates model output. */
(function (root) {
  'use strict';

  const e = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const SUBJECTS_408 = ['数据结构', '计算机组成原理', '操作系统', '计算机网络'];
  const DIFFICULTIES = [
    { value: '基础', label: '基础通识', hint: '覆盖基本概念与常规练习，适合首轮学习。' },
    { value: '进阶', label: '进阶强化', hint: '在基础之上加入综合与跨知识点任务。' },
    { value: '挑战', label: '冲刺压轴', hint: '面向综合应用与压轴题型的强化安排。' }
  ];
  const WEEKDAYS = [
    { value: 1, label: '周一' }, { value: 2, label: '周二' }, { value: 3, label: '周三' },
    { value: 4, label: '周四' }, { value: 5, label: '周五' }, { value: 6, label: '周六' },
    { value: 7, label: '周日' }
  ];
  const TERMINAL = ['succeeded', 'failed', 'unknown', 'cancelled'];
  const ERROR_TEXT = {
    AI_CONNECTION_FAILED: '当前后台无法连接模型站点，本次未提交新的计划作业。请检查网络、代理及服务启动环境。',
    AI_UNAVAILABLE: '尚未配置可用模型，无法生成计划；请先在服务设置中配置模型。',
    AI_PLAN_RESPONSE_TIMEOUT: '模型响应超时，未生成可用计划。该请求的结果与费用仍待核对，不会自动重试。',
    AI_INVALID_RESPONSE: '模型返回格式未通过校验，未完成计划；不会自动重试。',
    AI_TIMEOUT: '模型调用超时，未拿到可用结果；不会自动重试。',
    PLAN_GOAL_REQUIRED: '请填写学习目标。',
    INVALID_PLAN_DATES: '日期范围不合法：请检查开始/结束日期（1–366 天）。',
    INVALID_DAILY_MINUTES: '每日可用时间需为 15–480 分钟。',
    INVALID_DIFFICULTY: '难度档位不合法。',
    INVALID_REST_DAYS: '固定休息日设置不合法。',
    INVALID_SUBJECTS: '学科/专题设置不合法。',
    IDEMPOTENCY_CONFLICT: '相同操作编号提交了不同条件，请重置表单后重新生成。',
    JOB_NOT_FOUND: '没有找到这次生成作业，可能已被清理。',
    PLAN_NOT_FOUND: '没有找到这份计划，可能已被删除或不属于当前账号。',
    PLAN_NOT_ACTIVE: '这份计划当前不在执行中。',
    PLAN_NOT_DRAFT: '这份计划已经不是草稿，无需再次采用。',
    PLAN_REVISION_CONFLICT: '计划版本已变化，请刷新后重试。',
    PLAN_CURRENT_CHANGED: '当前执行计划刚刚发生变化，本次没有替换。请再次点击“采用计划”，核对最新计划后确认。',
    INVALID_CURRENT_PLAN: '当前计划校验信息不完整，请刷新后重试。',
    REPLAN_SOURCE_CHANGED: '来源计划已变化，请刷新后重试。',
    GENERATION_NOT_COMPLETED: '计划仍在生成（或关联导图未完成），暂不能采用；请等待作业结束。',
    CONFIRMATION_REQUIRED: '需要明确确认后才能采用计划。',
    INVALID_MAP_REQUEST: '导出参数不完整，请先生成或选择一份计划。',
    METHOD_NOT_ALLOWED: '接口调用方式错误。',
    AUTH_REQUIRED: '登录状态已失效，请重新登录后再试。',
    SERVICE_UNAVAILABLE: '本地服务未连接，请刷新页面后重试。',
    INVALID_REQUEST: '提交内容格式不正确。',
    REQUEST_TOO_LARGE: '提交内容过大，请精简后重试。'
  };
  const errorText = code => ERROR_TEXT[code] || (typeof code === 'string' && code ? '操作未完成（' + code + '）' : '操作未完成，请稍后重试。');
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const uuid = () => (root.crypto && typeof root.crypto.randomUUID === 'function')
    ? root.crypto.randomUUID()
    : 'op-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);

  function localISO(date) {
    return String(date.getFullYear()) + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
  }
  function parseISO(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return null;
    const parts = value.split('-').map(Number);
    const date = new Date(parts[0], parts[1] - 1, parts[2]);
    return date.getFullYear() === parts[0] && date.getMonth() === parts[1] - 1 && date.getDate() === parts[2] ? date : null;
  }
  function addDays(value, days) {
    const date = parseISO(value);
    if (!date) return '';
    date.setDate(date.getDate() + days);
    return localISO(date);
  }
  function daysBetween(start, end) {
    const left = parseISO(start), right = parseISO(end);
    if (!left || !right || right < left) return 0;
    return Math.round((right - left) / 86400000) + 1;
  }
  function isoWeekday(value) {
    const date = parseISO(value);
    return date ? ((date.getDay() + 6) % 7) + 1 : 0;
  }
  function weekdayLabel(value) {
    return (WEEKDAYS.find(item => item.value === Number(value)) || {}).label || '';
  }
  function restDaysLabel(days) {
    const list = Array.isArray(days) ? days : [];
    return list.length ? list.map(weekdayLabel).filter(Boolean).join('、') : '无';
  }
  function minutesLabel(minutes) {
    const value = Number(minutes);
    if (!Number.isFinite(value) || value <= 0) return '—';
    if (value < 60) return value + ' 分钟';
    const hours = value / 60;
    return (Number.isInteger(hours) ? hours : hours.toFixed(1)) + ' 小时';
  }
  function clampText(value, limit) {
    const text = String(value == null ? '' : value).trim();
    return text.length > limit ? text.slice(0, limit) : text;
  }
  function safeUrl(value) {
    const url = String(value || '');
    return /^(#space\/|https?:\/\/)/.test(url) ? url : '';
  }
  function fileNameFromDisposition(header, fallback) {
    if (!header) return fallback;
    const utf = /filename\*=UTF-8''([^;]+)/i.exec(header);
    if (utf) { try { return decodeURIComponent(utf[1].trim()); } catch (_) { /* fall through */ } }
    const plain = /filename="?([^";]+)"?/i.exec(header);
    return plain ? plain[1].trim() : fallback;
  }
  function storeKey() {
    return (root.XueyaDataKey || (key => key))('xueya-plan-workbench-v1');
  }

  function defaultForm() {
    const today = localISO(new Date());
    return {
      title: '我的个性化学习计划',
      goal: '',
      difficulty: '基础',
      startDate: today,
      endDate: addDays(today, 13),
      daysCount: 14,
      dailyMinutes: 60,
      restDays: [7],
      subjects: [],
      customSubjects: ''
    };
  }

  function create({ toast = () => {}, navigate = () => {} } = {}) {
    let host = null;
    let stamp = 0;
    let timer = null;
    let controller = null;
    let reviewDialog = null;
    let reviewReturnToForm = false;
    let materials = { loaded: false, subjects: [], concepts: 0, questions: 0, available: false, error: '' };
    let state = {
      form: defaultForm(),
      step: 'form',            // form | submitting | polling | result | failed
      job: null,
      jobId: '',
      error: '',
      draft: null,
      jobs: [],
      tree: null,
      treeFor: '',
      treeOpen: false,
      busyAction: '',
      adoptError: '',
      notice: '',
      reviewOpen: false
    };

    const formDom = () => host && host.querySelector('[data-pw-form]');
    const subjectChips = () => host && host.querySelector('[data-pw-subjects]');
    const resultHost = () => host && host.querySelector('[data-pw-result]');

    function notify(message) { try { toast(message); } catch (_) { /* toast is optional */ } }
    function failureText(job) {
      if (!job) return '生成未完成，结果与费用待核对，不会自动重试。';
      if (job.checkpoint && job.checkpoint.stage === 'framework' && job.checkpoint.planId) {
        return '学习计划已保存，关联导图生成未完成；可先核对并采用计划，不会自动重新调用 AI。';
      }
      if (job.diagnosticCode === 'AI_PLAN_RESPONSE_TIMEOUT' || ['AI_PLAN_RESPONSE_TIMEOUT', 'JOB_TIMEOUT'].includes(job.error)) {
        return '模型响应超时，未生成可用计划。该请求的结果与费用仍待核对，不会自动重试。';
      }
      if (job.diagnosticCode === 'AI_CONNECTION_FAILED' || job.error === 'AI_CONNECTION_FAILED') {
        return '连接模型服务失败，未拿到可用结果。请先检查连接；历史调用费用待核对，不会自动重试。';
      }
      if (job.error === 'AI_INVALID_RESPONSE') return '模型返回格式未通过校验，未完成计划；不会自动重试。';
      return '生成未完成，结果与费用待核对，不会自动重试。';
    }

    // ---------------------------------------------------------------- storage
    function loadStore() {
      try {
        const saved = JSON.parse(sessionStorage.getItem(storeKey()) || '{}');
        if (!saved || typeof saved !== 'object') return {};
        if (saved.form && typeof saved.form === 'object') {
          const form = defaultForm();
          ['title', 'goal', 'difficulty', 'startDate', 'endDate', 'daysCount', 'dailyMinutes', 'customSubjects'].forEach(key => {
            if (typeof saved.form[key] === 'string' || typeof saved.form[key] === 'number') form[key] = saved.form[key];
          });
          if (Array.isArray(saved.form.subjects)) form.subjects = saved.form.subjects.filter(s => typeof s === 'string').slice(0, 20);
          if (Array.isArray(saved.form.restDays)) form.restDays = saved.form.restDays.filter(n => Number.isInteger(n) && n >= 1 && n <= 7);
          if (!parseISO(form.startDate)) form.startDate = defaultForm().startDate;
          if (!parseISO(form.endDate)) form.endDate = addDays(form.startDate, 13);
          if (!DIFFICULTIES.some(item => item.value === form.difficulty)) form.difficulty = '基础';
          const minutes = Number(form.dailyMinutes);
          form.dailyMinutes = Number.isFinite(minutes) ? Math.max(15, Math.min(480, Math.round(minutes / 5) * 5)) : 60;
          state.form = form;
        }
        return saved;
      } catch (_) { return {}; }
    }
    function saveStore(pendingOverride) {
      const saved = loadStoreRaw();
      const next = Object.assign({}, saved);
      next.form = state.form;
      if (pendingOverride !== undefined) {
        if (pendingOverride) next.pending = pendingOverride; else delete next.pending;
      }
      try { sessionStorage.setItem(storeKey(), JSON.stringify(next)); } catch (_) { /* storage may be full */ }
    }
    function loadStoreRaw() {
      try { const value = JSON.parse(sessionStorage.getItem(storeKey()) || '{}'); return value && typeof value === 'object' ? value : {}; } catch (_) { return {}; }
    }
    function pendingRequest() { const value = loadStoreRaw().pending; return value && typeof value === 'object' ? value : null; }
    function savePending(value) { saveStore(value); }

    // -------------------------------------------------------------------- api
    function platform() {
      const client = root.XueyaPlatform;
      if (!client || typeof client.spaceFetch !== 'function' || !client.available) return null;
      return client;
    }
    async function apiFetch(path, options) {
      const client = platform();
      if (!client) throw Object.assign(new Error('本地服务未连接，请刷新页面后重试。'), { code: 'SERVICE_UNAVAILABLE' });
      try { return await client.spaceFetch(path, options); }
      catch(error) { const code=error.code||error.message;if(ERROR_TEXT[code]){error.code=code;error.message=ERROR_TEXT[code];}throw error; }
    }
    async function apiJson(path, options) {
      const response = await apiFetch(path, options);
      let value = null;
      try { value = await response.json(); } catch (_) { value = null; }
      if (!value) throw Object.assign(new Error('服务返回内容无法解析。'), { code: 'SERVICE_UNAVAILABLE' });
      if (value.ok === false) throw Object.assign(new Error(errorText(value.error)), { code: value.error });
      return value;
    }

    // --------------------------------------------------------------- form ops
    function effectiveSubjects() {
      const chips = state.form.subjects.filter(s => typeof s === 'string' && s.trim());
      const custom = String(state.form.customSubjects || '')
        .split(/[,，、;；]+/).map(s => s.trim()).filter(Boolean);
      const result = [];
      chips.concat(custom).forEach(subject => {
        const value = clampText(subject, 40);
        if (value && !result.includes(value) && result.length < 20) result.push(value);
      });
      return result;
    }
    function subjectCatalog() {
      const list = SUBJECTS_408.slice();
      (materials.subjects || []).forEach(subject => { if (subject && !list.includes(subject)) list.push(subject); });
      state.form.subjects.forEach(subject => { if (subject && !list.includes(subject)) list.push(subject); });
      return list.slice(0, 40);
    }

    function projection() {
      const form = state.form;
      const start = parseISO(form.startDate);
      const end = parseISO(form.endDate);
      const rest = form.restDays.filter(day => Number.isInteger(day) && day >= 1 && day <= 7);
      let totalDays = 0, studyDays = 0, restCount = 0;
      if (start && end && end >= start) {
        totalDays = daysBetween(form.startDate, form.endDate);
        const cursor = new Date(start.getTime());
        for (let index = 0; index < totalDays; index += 1) {
          const weekday = ((cursor.getDay() + 6) % 7) + 1;
          if (rest.includes(weekday)) restCount += 1; else studyDays += 1;
          cursor.setDate(cursor.getDate() + 1);
        }
      }
      const dailyMinutes = Number(form.dailyMinutes) || 0;
      const totalMinutes = studyDays * dailyMinutes;
      const subjects = effectiveSubjects();
      let conceptCount = 0, questionCount = 0, materialCount = 0;
      if (materials.loaded) {
        (materials.items || []).forEach(material => {
          if (!material || material.ready !== true) return;
          if (subjects.length && !subjects.includes(material.subject)) return;
          const concepts = Array.isArray(material.concepts) ? material.concepts : [];
          materialCount += 1;
          conceptCount += concepts.length;
          concepts.forEach(concept => { questionCount += Array.isArray(concept.questionIds) ? concept.questionIds.length : 0; });
        });
      }
      return { totalDays, studyDays, restCount, dailyMinutes, totalMinutes, subjects, conceptCount, questionCount, materialCount };
    }

    function renderProjection() {
      const target = host && host.querySelector('[data-pw-projection]');
      if (!target) return;
      const value = projection();
      const available = materials.loaded ? (materials.available === true ? '' : '模型未配置：当前只能查看估算，不能生成草稿。') : '';
      const coverage = materials.loaded
        ? (value.materialCount
          ? `${value.conceptCount} 个知识点 / ${value.questionCount} 道本地题目（来自 ${value.materialCount} 份已就绪资料${value.subjects.length ? '，限定所选学科' : ''}）`
          : '本地暂无可关联的资料题目；生成的任务会标注“未绑定本地题目”。')
        : (materials.error ? '资料统计暂不可用（不影响生成）。' : '正在读取本地资料统计…');
      target.innerHTML = `
        <div class="pw-projection-head">
          <div><h3>AI 排程实时推演</h3><p>按当前表单条件由程序计算</p></div>
          <span class="pw-badge">程序估算</span>
        </div>
        <dl class="pw-projection-list">
          <div><dt>计划周期</dt><dd>${value.totalDays ? value.totalDays + ' 天' : '—'}</dd></div>
          <div><dt>可学习日</dt><dd>${value.totalDays ? value.studyDays + ' 天' : '—'}</dd></div>
          <div><dt>固定休息日</dt><dd>${value.totalDays ? value.restCount + ' 天' : '—'}</dd></div>
          <div><dt>每日可用时间</dt><dd>${value.dailyMinutes ? value.dailyMinutes + ' 分钟' : '—'}</dd></div>
          <div class="pw-projection-total"><dt>总可投入时间</dt><dd>${value.totalMinutes ? minutesLabel(value.totalMinutes) : '—'}</dd></div>
          <div class="pw-projection-wide"><dt>可关联资源上限</dt><dd>${e(coverage)}</dd></div>
          <div class="pw-projection-wide"><dt>难度档位</dt><dd>${e(difficultyHint())} 该档位只作为生成条件提交，程序无法预知模型会划分几个阶段。</dd></div>
        </dl>
        <p class="pw-projection-note" role="note">以上均为程序按表单条件计算的估算，不含模型输出；实际阶段、任务与资源绑定以模型生成并经程序校验后的草稿为准。</p>
        ${available ? `<p class="pw-projection-warn" role="status">${e(available)}</p>` : ''}
      `;
    }

    function difficultyHint() {
      const item = DIFFICULTIES.find(entry => entry.value === state.form.difficulty) || DIFFICULTIES[0];
      return item.hint;
    }

    function updateDateHints() {
      if (!host) return;
      const value = projection();
      const hint = host.querySelector('[data-pw-date-hint]');
      if (hint) {
        hint.textContent = value.totalDays
          ? `共 ${value.totalDays} 天，其中可学习 ${value.studyDays} 天、休息 ${value.restCount} 天。`
          : '日期范围不完整，无法计算学习天数。';
      }
    }

    function applyFormToDom() {
      const form = formDom();
      if (!form) return;
      form.querySelector('[data-pw-title]').value = state.form.title;
      form.querySelector('[data-pw-goal]').value = state.form.goal;
      form.querySelector('[data-pw-start]').value = state.form.startDate;
      form.querySelector('[data-pw-end]').value = state.form.endDate;
      form.querySelector('[data-pw-days]').value = state.form.daysCount;
      form.querySelector('[data-pw-minutes]').value = state.form.dailyMinutes;
      form.querySelector('[data-pw-minutes-out]').textContent = state.form.dailyMinutes + ' 分钟';
      form.querySelector('[data-pw-custom-subjects]').value = state.form.customSubjects;
      form.querySelector('[data-pw-goal-count]').textContent = state.form.goal.length + '/1000';
      renderDifficulty();
      renderRestDays();
      updateDateHints();
    }

    function renderDifficulty() {
      if (!host) return;
      host.querySelectorAll('[data-pw-difficulty]').forEach(button => {
        const active = button.dataset.pwDifficulty === state.form.difficulty;
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
        button.classList.toggle('is-active', active);
      });
      const hint = host.querySelector('[data-pw-difficulty-hint]');
      if (hint) hint.textContent = difficultyHint();
    }

    function renderRestDays() {
      if (!host) return;
      host.querySelectorAll('[data-pw-rest]').forEach(button => {
        const active = state.form.restDays.includes(Number(button.dataset.pwRest));
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
        button.classList.toggle('is-active', active);
      });
    }

    function renderSubjects() {
      const target = subjectChips();
      if (!target) return;
      const catalog = subjectCatalog();
      target.innerHTML = catalog.map(subject => {
        const active = state.form.subjects.includes(subject);
        return `<button type="button" class="pw-chip ${active ? 'is-active' : ''}" data-pw-subject="${e(subject)}" aria-pressed="${active ? 'true' : 'false'}">${e(subject)}</button>`;
      }).join('') || '<p class="pw-hint">暂无已识别学科，可留空或在上方自行填写。</p>';
      target.querySelectorAll('[data-pw-subject]').forEach(button => {
        button.onclick = () => {
          const subject = button.dataset.pwSubject;
          if (state.form.subjects.includes(subject)) state.form.subjects = state.form.subjects.filter(item => item !== subject);
          else if (state.form.subjects.length < 20) state.form.subjects = state.form.subjects.concat(subject);
          else notify('最多选择 20 个学科/专题');
          saveStore();
          renderSubjects();
          renderProjection();
        };
      });
    }

    // ------------------------------------------------------------ validation
    function validate() {
      const form = state.form;
      const errors = [];
      const invalid = [];
      const focus = selector => invalid.push(selector);
      const title = String(form.title || '').trim();
      if (!title) { errors.push('请填写计划名称。'); focus('[data-pw-title]'); }
      else if (title.length > 60) { errors.push('计划名称最多 60 个字符。'); focus('[data-pw-title]'); }
      const goal = String(form.goal || '').trim();
      if (!goal) { errors.push('请填写学习目标。'); focus('[data-pw-goal]'); }
      else if (goal.length > 1000) { errors.push('学习目标最多 1000 个字符。'); focus('[data-pw-goal]'); }
      const start = parseISO(form.startDate), end = parseISO(form.endDate);
      if (!start) { errors.push('开始日期不合法。'); focus('[data-pw-start]'); }
      if (!end) { errors.push('结束日期不合法。'); focus('[data-pw-end]'); }
      if (start && end && end < start) { errors.push('结束日期不能早于开始日期。'); focus('[data-pw-end]'); }
      const daysCount = Number(form.daysCount);
      if (!Number.isInteger(daysCount) || daysCount < 1 || daysCount > 366) { errors.push('持续天数需为 1–366 的整数。'); focus('[data-pw-days]'); }
      else if (start && end && daysBetween(form.startDate, form.endDate) !== daysCount) {
        errors.push('持续天数与起止日期不一致，请调整日期或天数。'); focus('[data-pw-days]');
      }
      if (start && end && end >= start) {
        let studyDays = 0;
        const cursor = new Date(start.getTime());
        const total = daysBetween(form.startDate, form.endDate);
        for (let index = 0; index < total; index += 1) {
          if (!form.restDays.includes(((cursor.getDay() + 6) % 7) + 1)) studyDays += 1;
          cursor.setDate(cursor.getDate() + 1);
        }
        if (studyDays === 0) { errors.push('固定休息日覆盖了整个周期，没有可学习的日子。'); focus('[data-pw-rest]'); }
      }
      const dailyMinutes = Number(form.dailyMinutes);
      if (!Number.isInteger(dailyMinutes) || dailyMinutes < 15 || dailyMinutes > 480) { errors.push('每日可用时间需为 15–480 分钟。'); focus('[data-pw-minutes]'); }
      if (!DIFFICULTIES.some(item => item.value === form.difficulty)) { errors.push('难度档位不合法。'); }
      if (!Array.isArray(form.restDays) || form.restDays.some(day => !Number.isInteger(day) || day < 1 || day > 7)) {
        errors.push('固定休息日设置不合法。'); focus('[data-pw-rest]');
      }
      const subjects = effectiveSubjects();
      if (subjects.length > 20) { errors.push('学科/专题最多 20 个。'); focus('[data-pw-custom-subjects]'); }
      if (subjects.some(subject => subject.length > 40)) { errors.push('单个学科/专题最多 40 个字符。'); focus('[data-pw-custom-subjects]'); }
      return {
        errors,
        invalid,
        value: {
          title,
          goal,
          difficulty: form.difficulty,
          startDate: form.startDate,
          endDate: form.endDate,
          daysCount,
          dailyMinutes,
          restDays: form.restDays.slice().sort((a, b) => a - b),
          subjects
        }
      };
    }

    function showFormError(messages, invalid) {
      const box = host && host.querySelector('[data-pw-form-error]');
      formDom()?.querySelectorAll('[aria-invalid="true"]').forEach(node => node.removeAttribute('aria-invalid'));
      (invalid || []).forEach(selector => {
        const node = host.querySelector(selector);
        if (node) node.setAttribute('aria-invalid', 'true');
      });
      if (!box) return;
      if (!messages || !messages.length) { box.hidden = true; box.textContent = ''; return; }
      box.hidden = false;
      box.innerHTML = '<strong>提交前需要修正：</strong><ul>' + messages.map(message => '<li>' + e(message) + '</li>').join('') + '</ul>';
      const first = (invalid || []).map(selector => host.querySelector(selector)).find(Boolean);
      if (first && typeof first.focus === 'function') first.focus();
    }

    // -------------------------------------------------------------- generate
    function formPayload() {
      const checked = validate();
      return checked;
    }

    async function generate() {
      if (state.step === 'submitting' || state.step === 'polling') return;
      const checked = formPayload();
      if (checked.errors.length) { showFormError(checked.errors, checked.invalid); notify(checked.errors[0]); return; }
      showFormError([], []);
      const value = checked.value;
      const signature = JSON.stringify(value);
      const prior = pendingRequest();
      const pending = (prior && prior.signature === signature) ? prior : { signature, operationId: uuid() };
      savePending(pending);
      state.step = 'submitting';
      state.job = null;
      state.jobId = '';
      state.error = '';
      state.notice = '';
      state.tree = null;
      renderResult();
      setBusy(true);
      try {
        const data = await apiJson('/api/learning/space/plan/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(Object.assign({}, value, { operationId: pending.operationId }))
        });
        if (!data.job || !data.job.id) throw Object.assign(new Error('服务未返回生成作业编号。'), { code: 'SERVICE_UNAVAILABLE' });
        pending.jobId = data.job.id;
        pending.createdAt = Date.now();
        savePending(pending);
        state.step = 'polling';
        state.jobId = data.job.id;
        state.job = data.job;
        notify('已提交后台生成作业；完成后核对草稿和资源绑定，再决定是否采用。');
        renderResult();
        startPolling();
      } catch (error) {
        state.step = 'form';
        state.error = error && error.code && error.code !== 'SERVICE_UNAVAILABLE' ? errorText(error.code) : (error && error.message) || '提交回执未确认，请先核对作业列表；再次提交相同条件会复用原请求，不会另开一份作业。';
        if (error && error.code === undefined) savePending(pending);
        renderResult();
        notify(state.error);
      } finally {
        setBusy(state.step === 'polling');
      }
    }

    function setBusy(busy) {
      const button = host && host.querySelector('[data-pw-generate]');
      if (!button) return;
      button.disabled = Boolean(busy);
      button.classList.toggle('is-loading', Boolean(busy));
      button.textContent = busy ? '正在提交…' : '生成草稿';
      const reset = host && host.querySelector('[data-pw-reset]');
      if (reset) reset.disabled = false;
    }

    function startPolling() {
      if (!state.jobId || !host) return;
      clearTimeout(timer);
      const current = ++stamp;
      controller = typeof AbortController === 'function' ? new AbortController() : null;
      let attempts = 0;
      const poll = async () => {
        if (!host || current !== stamp) return;
        attempts += 1;
        try {
          const data = await apiJson('/api/learning/space/jobs/' + encodeURIComponent(state.jobId),
            controller ? { signal: controller.signal } : undefined);
          if (!host || current !== stamp) return;
          state.job = data.job;
          if (TERMINAL.includes(data.job.status)) { await finishJob(data.job); return; }
          state.step = 'polling';
          renderResult();
          timer = setTimeout(poll, 2500);
        } catch (error) {
          if (!host || current !== stamp) return;
          if (attempts >= 8) {
            state.step = 'failed';
            state.error = '读取生成进度失败：' + (error && error.message ? error.message : '请稍后刷新查看作业状态。');
            renderResult();
            return;
          }
          timer = setTimeout(poll, Math.min(8000, 2500 * attempts));
        }
      };
      poll();
    }

    async function finishJob(job) {
      state.job = job;
      if (job && (job.status === 'succeeded' || (job.checkpoint && job.checkpoint.planId))) {
        const planId = (job.result && job.result.planId) || (job.checkpoint && job.checkpoint.planId) || '';
        state.step = 'result';
        state.error = '';
        state.notice = job.status === 'succeeded' ? '' : failureText(job);
        savePending(null);
        await loadDraft(planId);
        state.reviewOpen = Boolean(state.draft && state.draft.status !== 'active');
        if(state.draft?.status==='draft')notify('计划草稿已生成；请核对阶段、任务与资源绑定后再采用。');
      } else {
        state.step = 'failed';
        state.error = failureText(job);
      }
      if (state.step === 'result' && !state.draft) {
        state.step = 'failed';
        state.error = state.error || '草稿已生成，但没能读取到计划列表；请刷新后到“查看我的计划”核对。';
      }
      if (host) renderResult();
    }

    async function loadDraft(planId) {
      try {
        const data = await apiJson('/api/learning/space/plan/list');
        const all = []
          .concat(data.active ? [data.active] : [], data.drafts || [], data.history || []);
        state.jobs = data.jobs || [];
        const match = all.find(plan => plan && plan.id === planId) || (planId ? null : (data.drafts || [])[0] || null);
        if (match) {
          if(match.status!=='draft'){state.draft=null;state.step='form';state.reviewOpen=false;state.notice='';return match;}
          state.draft = match;
          state.tree = null;
          state.treeFor = '';
        } else if (planId) {
          state.draft = null;
        }
        return match;
      } catch (error) {
        if (!state.draft) state.error = '草稿已生成，但读取计划列表失败：' + (error && error.message ? error.message : '请刷新后重试。');
        return null;
      }
    }

    // ----------------------------------------------------------------- adopt
    async function adopt() {
      const draft = state.draft;
      if (!draft || !draft.id || state.busyAction) return;
      state.busyAction = 'adopt';
      state.adoptError = '';
      renderResult();
      try {
        const listing = await apiJson('/api/learning/space/plan/list');
        if(!host)return;
        const current=listing.active||null;
        if(current?.id===draft.id){adoptionSucceeded(current);return;}
        const latest=[...(listing.drafts||[]),...(listing.history||[])].find(p=>p.id===draft.id);
        if(!latest)throw Object.assign(new Error(ERROR_TEXT.PLAN_NOT_FOUND),{code:'PLAN_NOT_FOUND'});
        state.draft=latest;
        if(latest.revision!==draft.revision)throw Object.assign(new Error(ERROR_TEXT.PLAN_REVISION_CONFLICT),{code:'PLAN_REVISION_CONFLICT'});
        if(latest.status!=='draft')throw Object.assign(new Error(ERROR_TEXT.PLAN_NOT_DRAFT),{code:'PLAN_NOT_DRAFT'});
        if(latest.canAdopt===false)throw Object.assign(new Error(ERROR_TEXT.GENERATION_NOT_COMPLETED),{code:'GENERATION_NOT_COMPLETED'});
        const expectedCurrent=current?{id:current.id,revision:current.revision}:null;
        if(!root.confirm('确认采用“'+(latest.title||'这份草稿')+'”为当前执行计划吗？'+(current?'\n当前执行计划“'+(current.title||'未命名计划')+'”将转入历史，已有学习记录会保留。':'')))return;
        const data = await apiJson('/api/learning/space/plan/adopt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            planId: draft.id,
            expectedRevision: draft.revision,
            confirmed: true,
            expectedCurrent,
            operationId: 'workbench-adopt-' + draft.id + '-' + draft.revision + '-' + (current?current.id+'-'+current.revision:'none')
          })
        });
        adoptionSucceeded(data.plan);
      } catch (error) {
        state.adoptError=ERROR_TEXT[error.code||error.message]||error.message||'采用未完成，请稍后重试。';
        notify(state.adoptError);
      } finally {
        state.busyAction = '';
        if (host) renderResult();
      }
    }

    function adoptionSucceeded(plan) {
      state.draft=null;state.step='form';
      state.reviewOpen=false;state.adoptError='';state.notice='';state.error='';reviewDialog?.close();
      notify('采用成功');
      navigate('#space/analysis/plans');
    }

    // ------------------------------------------------------------------- map
    function treePayload() {
      const draft = state.draft;
      if (draft && draft.id) return { planId: draft.id };
      if (draft) return { draft: mapDraftShape(draft) };
      return null;
    }
    function mapDraftShape(draft) {
      return {
        title: draft.title, goal: draft.goal, difficulty: draft.difficulty,
        startDate: draft.startDate, endDate: draft.endDate, daysCount: draft.daysCount,
        dailyMinutes: draft.dailyMinutes, restDays: draft.restDays, subjects: draft.subjects,
        explanation: draft.explanation,
        days: (draft.days || []).map(day => ({
          date: day.date, isRestDay: day.isRestDay, budgetMinutes: day.budgetMinutes,
          tasks: (draft.days || []).map(day => ({
            date: day.date, isRestDay: day.isRestDay, budgetMinutes: day.budgetMinutes,
            tasks: (day.tasks || []).map(task => {
              const counted = task.resource && task.resource.type === 'question' ? 1 : 0;
              return {
                id: task.id, title: task.title, phase: task.phase, minutes: task.minutes,
                completed: task.completed, difficulty: task.difficulty, resource: task.resource,
                boundCount: counted, requiredCount: counted, submittedCount: counted
              };
            })
          })),
        })),
        learningRoute: draft.learningRoute || undefined
      };
    }
    async function fetchTree() {
      const payload = treePayload();
      if (!payload) throw Object.assign(new Error('先生成或选择一份计划，再预览思维导图。'), { code: 'INVALID_MAP_REQUEST' });
      const data = await apiJson('/api/learning/space/workbench/map/tree', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!data.tree || typeof data.tree !== 'object') throw Object.assign(new Error('思维导图数据为空。'), { code: 'INVALID_MAP_REQUEST' });
      state.tree = data.tree;
      state.treeFor = state.draft && state.draft.id ? state.draft.id : '';
    }
    async function togglePreview(button) {
      if (state.tree && state.treeFor === (state.draft && state.draft.id ? state.draft.id : '')) {
        state.treeOpen = !state.treeOpen;
        renderResult();
        return;
      }
      const original = button ? button.textContent : '';
      if (button) { button.disabled = true; button.textContent = '正在整理路线树…'; }
      try {
        await fetchTree();
        state.treeOpen = true;
        renderResult();
      } catch (error) {
        notify('预览失败：' + (error && error.message ? error.message : '请稍后重试。'));
        if (button && button.isConnected) { button.disabled = false; button.textContent = original; }
      }
    }

    async function download(format) {
      if (state.busyAction) return;
      const payload = treePayload();
      if (!payload) { notify('先生成或选择一份计划，再导出思维导图。'); return; }
      state.busyAction = 'download-' + format;
      renderResult();
      try {
        const response = await apiFetch('/api/learning/space/workbench/map/' + (format === 'mm' ? 'mm' : 'export'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const blob = await response.blob();
        const fallback = '学涯-学习计划.' + (format === 'mm' ? 'mm' : 'xmind');
        const name = fileNameFromDisposition(response.headers.get('content-disposition'), fallback);
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = name;
        link.rel = 'noopener';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        notify('已开始下载 ' + name + (format === 'mm'
          ? '（FreeMind 格式，可作 .xmind 的兜底）。'
          : '（XMind Zen 兼容格式；若打开异常请下载 .mm 或使用站内预览）。'));
      } catch (error) {
        notify('导出失败：' + (error && error.message ? error.message : '请稍后重试。'));
      } finally {
        state.busyAction = '';
        if (host) renderResult();
      }
    }

    // -------------------------------------------------------------- rendering
    function renderResult() {
      const target = resultHost();
      if (!target) return;
      target.innerHTML = resultMarkup();
      bindResult(target);
      setBusy(state.step === 'polling' || state.step === 'submitting');
      if (state.reviewOpen && state.step === 'result' && state.draft?.status==='draft') renderReview();
      else if (reviewDialog?.open) reviewDialog.close();
    }

    function renderReview() {
      if (!host) return;
      if (!reviewDialog) {
        reviewDialog = document.createElement('dialog');
        reviewDialog.className = 'pw-review-dialog';
        reviewDialog.setAttribute('aria-labelledby', 'pwReviewTitle');
        reviewDialog.innerHTML = `<header class="pw-review-header"><div><h2 id="pwReviewTitle">核对学习计划</h2><p>查看阶段安排，决定采用或调整条件后重新生成。</p></div><button type="button" class="pw-review-close" data-pw-review-close aria-label="关闭计划预览">×</button></header><div class="pw-review-content" data-pw-review-content></div><footer class="pw-review-footer"><p class="pw-adopt-error" data-pw-adopt-error role="alert" hidden></p><small>关闭窗口后，草稿仍会保留。</small><div><button type="button" class="button pw-regenerate" data-pw-regenerate>重新生成</button><button type="button" class="button pw-adopt-primary" data-pw-adopt>采用计划</button></div></footer>`;
        document.body.append(reviewDialog);
        reviewDialog.querySelector('[data-pw-review-close]').addEventListener('click', () => reviewDialog.close());
        reviewDialog.addEventListener('close', () => {
          state.reviewOpen = false;
          if (host) { renderResult(); host.querySelector(reviewReturnToForm ? '[data-pw-goal]' : '[data-pw-openreview]')?.focus({preventScroll:true}); }
          reviewReturnToForm = false;
        });
      }
      const scroll = reviewDialog.querySelector('[data-pw-review-content]');
      const oldScroll = scroll.scrollTop;
      scroll.innerHTML = (state.notice ? `<p class="pw-notice">${e(state.notice)}</p>` : '') + draftMarkup(state.draft);
      scroll.scrollTop = oldScroll;
      const errorMessage=reviewDialog.querySelector('[data-pw-adopt-error]');errorMessage.hidden=!state.adoptError;errorMessage.textContent=state.adoptError;
      const adoptButton = reviewDialog.querySelector('[data-pw-adopt]');
      adoptButton.disabled = Boolean(state.busyAction || state.draft.canAdopt === false || state.draft.status === 'active');
      adoptButton.textContent = state.busyAction === 'adopt' ? '正在采用…' : state.draft.status === 'active' ? '已采用' : '采用计划';
      reviewDialog.querySelector('[data-pw-regenerate]').disabled = Boolean(state.busyAction);
      bindResult(reviewDialog);
      if (!reviewDialog.open) reviewDialog.showModal();
    }

    function regenerate() {
      if (state.busyAction) return;
      state.reviewOpen = false;
      reviewReturnToForm = true;
      reviewDialog?.close();
      notify('已返回定制计划。原条件和草稿保留；调整后点击“生成草稿”。');
      const form = formDom();
      form?.scrollIntoView({block:'start',behavior:'smooth'});
      form?.querySelector('[data-pw-goal]')?.focus({preventScroll:true});
    }

    function jobBanner() {
      if (state.step === 'submitting') {
        return '<div class="pw-job panel" role="status"><span class="pw-spinner" aria-hidden="true"></span><div><strong>正在提交生成请求…</strong><p>提交成功后才会显示作业进度；不会自动重试付费请求。</p></div></div>';
      }
      if (state.step === 'polling' && state.job) {
        const progress = state.job.progress || {};
        const percent = Number.isFinite(Number(progress.percent)) ? Math.max(0, Math.min(100, Number(progress.percent))) : null;
        return `<div class="pw-job panel" role="status">
          <span class="pw-spinner" aria-hidden="true"></span>
          <div>
            <strong>后台作业${state.job.status === 'queued' ? '排队中' : '生成中'}…</strong>
            <p>${e(progress.label || '等待模型生成阶段任务')}</p>
            <div class="pw-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" ${percent === null ? '' : `aria-valuenow="${percent}"`}><span style="width:${percent === null ? '30' : percent}%"></span></div>
            <p class="pw-hint">作业编号 ${e(state.jobId || state.job.id)}。刷新页面会自动恢复进度；不会重复提交。</p>
          </div>
        </div>`;
      }
      if (state.error && (state.step === 'failed' || state.step === 'form')) {
        return `<div class="pw-job pw-job-error panel" role="alert">
          <span class="material-symbols-outlined" aria-hidden="true">error</span>
          <div><strong>${state.step === 'failed' ? '生成未完成' : '没有提交生成请求'}</strong><p>${e(state.error)}</p>
          ${state.step === 'failed' ? '<p class="pw-hint">可以调整条件后重新生成（会发起新的模型调用）；相同条件再次提交会复用原作业回执，不会重复计费。</p>' : ''}
          <div class="pw-job-actions"><button type="button" class="button button-outline button-small" data-pw-dismiss>清除失败提示</button><button type="button" class="button button-outline button-small" data-pw-view>查看我的计划</button></div></div>
        </div>`;
      }
      if (state.notice) return `<p class="pw-notice" role="status">${e(state.notice)}</p>`;
      return '';
    }

    function draftMarkup(draft) {
      if (!draft) return '';
      const route = draft.learningRoute && Array.isArray(draft.learningRoute.phases) ? draft.learningRoute.phases : [];
      const days = Array.isArray(draft.days) ? draft.days : [];
      const tasks = days.reduce((list, day) => list.concat((day.tasks || []).map(task => Object.assign({ date: day.date }, task))), []);
      const bound = tasks.filter(task => task.resource && task.resource.type === 'question').length;
      const unbound = tasks.length - bound;
      const studyDays = days.filter(day => !day.isRestDay).length;
      const scheduledDays = days.filter(day => (day.tasks || []).length).length;
      const phaseCards = route.map((phase, index) => {
        const stages = Array.isArray(phase.stages) ? phase.stages : [];
        const nodeCount = stages.reduce((count, stage) => count + (Array.isArray(stage.nodes) ? stage.nodes.length : 0), 0);
        const done = Boolean(phase.completed);
        return `<li class="pw-phase-card ${done ? 'is-done' : ''}">
          <span class="pw-phase-index" aria-hidden="true">${done ? '✓' : index + 1}</span>
          <div class="pw-phase-copy">
            <strong>${e(phase.title || '学习阶段')}</strong>
            <span>${e(phase.startDate || '—')} → ${e(phase.endDate || '—')}</span>
          </div>
          <div class="pw-phase-facts"><span>${stages.length} 任务组</span><span>${nodeCount} 知识点</span></div>
        </li>`;
      }).join('');
      const status = draft.status === 'active' ? '<span class="pw-badge is-active">当前执行中</span>'
        : draft.canAdopt === false ? '<span class="pw-badge is-warn">暂不可采用</span>'
          : '<span class="pw-badge">草稿待采用</span>';
      const canAdopt = draft.canAdopt !== false && draft.status !== 'active';
      const dayRows = days.map((day, dayIndex) => {
        const weekday = weekdayLabel(isoWeekday(day.date));
        const dateText = String(day.date || '');
        const dateLabel = dateText.length >= 10 ? dateText.slice(5) : (dateText || '日期未知');
        const count = (day.tasks || []).length;
        const items = (day.tasks || []).map(task => {
          const resource = task.resource || {};
          const url = safeUrl(resource.url);
          const binding = resource.type === 'question'
            ? (url ? `<a href="${e(url)}">${e(clampText(resource.title || '本地题目', 60))}</a>` : '本地固定题目')
            : resource.type === 'course'
              ? (url ? `<a href="${e(url)}">课程总览（非精确分集）</a>` : '课程总览（未提供链接）')
              : '未绑定本地题目';
          return `<li class="${task.completed ? 'is-done' : ''}">
            <span class="pw-task-title">${e(task.title || '学习任务')}</span>
            <span class="pw-task-meta"><span>${e(task.phase || '学习')}</span><span>${e(task.minutes == null ? '—' : task.minutes + ' 分钟')}</span></span>
            <span class="pw-task-resource">${binding}</span>
          </li>`;
        }).join('');
        return `<details class="pw-day ${day.isRestDay ? 'is-rest' : ''}" ${dayIndex === 0 ? 'open' : ''}>
          <summary>
            <span class="pw-day-date"><strong>${e(dateLabel)}</strong><span>${weekday ? e(weekday) : ''}</span></span>
            <span class="pw-day-meta">${day.isRestDay ? '固定休息日' : (day.budgetMinutes == null ? '预算未提供' : day.budgetMinutes + ' 分钟')}${count ? ' · ' + count + ' 个任务' : ' · 无任务'}</span>
          </summary>
          ${items ? '<ul class="pw-task-list">' + items + '</ul>' : '<p class="pw-hint">当日没有安排任务。</p>'}
        </details>`;
      }).join('');
      const remaining = Array.isArray(draft.remaining) ? draft.remaining.length : 0;
      const facts = [
        ['难度', draft.difficulty || '—'],
        ['周期', (draft.startDate || '—') + ' 至 ' + (draft.endDate || '—')],
        ['持续天数', draft.daysCount ? draft.daysCount + ' 天' : '—'],
        ['每日可用', draft.dailyMinutes ? draft.dailyMinutes + ' 分钟' : '—'],
        ['固定休息日', restDaysLabel(draft.restDays)],
        ['学科范围', (draft.subjects || []).join('、') || '未指定'],
      ];
      const framework = draft.frameworkId
        ? `<a href="#space/frameworks/${e(draft.frameworkId)}">打开关联知识框架${draft.frameworkCoverage && draft.frameworkCoverage.partial ? '（部分覆盖）' : ''}</a>`
        : draft.frameworkStatus === 'failed'
          ? '<span class="pw-hint">关联导图生成失败；计划排程已保存，可以采用，不会自动重新调用模型。</span>'
          : draft.generationStatus && draft.generationStatus !== 'completed'
            ? '<span class="pw-hint">计划与关联导图仍在处理中。</span>' : '';
      return `<section class="pw-draft pw-draft-v2" aria-label="生成的计划草稿">
        <header class="pw-draft-hero">
          <div class="pw-draft-hero-copy">
            <div class="pw-draft-eyebrow"><span class="pw-draft-kicker">个性化学习草稿</span>${status}</div>
            <h3>${e(draft.title || '学习计划草稿')}</h3>
            <p class="pw-draft-goal">${e(draft.goal || '学习目标未提供')}</p>
            <div class="pw-draft-meta">
              <span>${e(draft.difficulty || '—')}</span>
              <span>${e(draft.startDate || '—')} 至 ${e(draft.endDate || '—')}</span>
              <span>每日 ${e(draft.dailyMinutes || '—')} 分钟</span>
            </div>
          </div>
          <dl class="pw-draft-hero-stats">
            <div><dt>学习日</dt><dd>${scheduledDays}<small>/${studyDays}</small></dd></div>
            <div><dt>任务</dt><dd>${tasks.length}</dd></div>
            <div><dt>绑定题目</dt><dd>${bound}</dd></div>
            <div class="${unbound ? 'is-warn' : ''}"><dt>未绑定</dt><dd>${unbound}</dd></div>
          </dl>
        </header>
        <div class="pw-draft-columns">
          <div class="pw-draft-main">
            <section class="pw-draft-section">
              <header class="pw-section-head"><div><h4>阶段路线</h4><p>按依赖排序；点击下方每日排期可展开任务</p></div><span>${route.length} 个阶段</span></header>
              ${phaseCards ? `<ol class="pw-roadmap">${phaseCards}</ol>` : '<p class="pw-hint">这份计划没有可读取的阶段路线，下方每日排期仍可用于核对。</p>'}
              <p class="pw-hint">${draft.learningRoute && draft.learningRoute.selectionRule ? e(draft.learningRoute.selectionRule) : '阶段与知识点来自程序保存的学习路线，资源绑定以草稿任务为准。'}</p>
            </section>
            <section class="pw-draft-section">
              <header class="pw-section-head"><div><h4>每日排期</h4><p>共 ${days.length} 天，已安排 ${scheduledDays} 天</p></div><span>${tasks.length} 个任务</span></header>
              <details class="pw-daily-schedule"><summary>查看每日排期与任务（${days.length} 天）</summary><div class="pw-days">${dayRows || '<p class="pw-hint">草稿中暂无每日排期。</p>'}</div></details>
            </section>
          </div>
          <aside class="pw-draft-side">
            <section class="pw-side-card">
              <h5>计划信息</h5>
              <dl class="pw-facts">${facts.map(([label, value]) => `<div><dt>${e(label)}</dt><dd>${e(value)}</dd></div>`).join('')}</dl>
            </section>
            <section class="pw-side-card">
              <h5>说明与覆盖</h5>
              ${draft.explanation ? `<p class="pw-draft-explanation">${e(draft.explanation)}</p>` : ''}
              <div class="pw-draft-stats">
                <span>任务 ${tasks.length} 项</span>
                <span class="${unbound ? 'is-warn' : ''}">未绑定题目 ${unbound} 项</span>
                ${remaining ? `<span class="is-warn">另有 ${remaining} 项未排入</span>` : ''}
              </div>
              ${framework ? `<p class="pw-framework">${framework}</p>` : ''}
            </section>
            <section class="pw-side-card pw-side-actions">
              <h5>路线工具</h5>
              <div class="pw-draft-actions">
                <button type="button" class="button button-outline" data-pw-export ${state.busyAction === 'download-xmind' ? 'disabled' : ''}>${state.busyAction === 'download-xmind' ? '正在导出…' : '导出思维导图 (.xmind)'}</button>
                <button type="button" class="button button-outline" data-pw-mm ${state.busyAction === 'download-mm' ? 'disabled' : ''}>${state.busyAction === 'download-mm' ? '正在导出…' : '下载 .mm 兜底'}</button>
                <button type="button" class="button button-outline" data-pw-preview>${state.treeOpen ? '收起路线树预览' : '预览路线树'}</button>
              </div>
            </section>
            <p class="pw-hint">.xmind 为 XMind Zen（XMind 2020+）兼容的 JSON 工作簿格式；本站未在真实 XMind 客户端中验证打开效果，如打开异常请下载 .mm（FreeMind）或使用站内预览。</p>
            ${canAdopt ? '' : '<p class="pw-hint">草稿仍在生成或关联导图未完成时不能采用；采用后原计划会转入历史。</p>'}
          </aside>
        </div>
        ${mapPreviewMarkup()}
      </section>`;
    }

    function mapPreviewMarkup() {
      if (!state.treeOpen) return '';
      if (!state.tree) return '<section class="pw-map panel"><p class="pw-hint" role="status">正在整理路线树…</p></section>';
      const tree = state.tree;
      const stats = tree.stats || {};
      const legend = `<div class="pw-map-legend"><span class="pw-map-legend-item"><i class="pw-dot is-done"></i>已完成</span><span class="pw-map-legend-item"><i class="pw-dot"></i>未完成</span><span>连线表示计划层级；数据来自已保存计划，未调用模型。</span></div>`;
      return `<section class="pw-map panel" aria-label="学习路线思维导图预览">
        <header class="pw-map-head"><h4>学习路线树预览</h4><span>${e(stats.phases || 0)} 阶段 · ${e(stats.tasks || 0)} 个任务/知识点 · ${e(stats.completed || 0)} 个已完成 · 绑定题目 ${e(stats.questionRefs || 0)} 道</span></header>
        ${legend}
        ${tree.truncated ? '<p class="pw-hint is-warn">节点过多，已按上限截断导出；完整路线请查看计划详情。</p>' : ''}
        <div class="pw-map-scroll">${svgTree(tree.root)}</div>
      </section>`;
    }

    function svgTree(rootNode) {
      if (!rootNode || typeof rootNode !== 'object') return '<p class="pw-hint">没有可预览的路线节点。</p>';
      const COL = 214, ROW = 46, NODE_W = 168, NODE_H = 34, PAD = 18;
      const nodes = [];
      let leafIndex = 0;
      const walk = (node, depth) => {
        const children = (Array.isArray(node.children) ? node.children : []).filter(child => child && typeof child === 'object');
        let y;
        if (children.length) {
          const centers = children.map(child => walk(child, depth + 1));
          y = (centers[0] + centers[centers.length - 1]) / 2;
        } else {
          y = leafIndex * ROW;
          leafIndex += 1;
        }
        const item = { node, depth, x: PAD + depth * COL, y: PAD + y };
        nodes.push(item);
        children.forEach(child => { child.__parent = item; });
        return y;
      };
      walk(rootNode, 0);
      const maxDepth = nodes.reduce((max, item) => Math.max(max, item.depth), 0);
      const width = PAD * 2 + maxDepth * COL + NODE_W;
      const height = PAD * 2 + Math.max(leafIndex * ROW, NODE_H + ROW);
      const edges = nodes.map(item => {
        const parent = item.node.__parent;
        if (!parent) return '';
        const x1 = parent.x + NODE_W, y1 = parent.y + NODE_H / 2;
        const x2 = item.x, y2 = item.y + NODE_H / 2;
        const mid = (x1 + x2) / 2;
        return `<path class="pw-edge" d="M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}"/>`;
      }).join('');
      const boxes = nodes.map(item => {
        const node = item.node;
        const title = String(node.title || '未命名');
        const first = title.slice(0, 13);
        const second = title.length > 13 ? title.slice(13, 26) + (title.length > 26 ? '…' : '') : '';
        const done = node.completed === true;
        const titleMarkup = `<title>${e(title + (node.subtitle ? '\n' + node.subtitle : ''))}</title>`;
        const textY = item.y + (second ? NODE_H / 2 - 4 : NODE_H / 2 + 4);
        return `<g class="pw-node ${done ? 'is-done' : ''} ${item.depth === 0 ? 'is-root' : ''}">${titleMarkup}
          <rect class="pw-node-box" x="${item.x}" y="${item.y}" width="${NODE_W}" height="${NODE_H}" rx="9" ry="9"/>
          <text class="pw-node-text" x="${item.x + 10}" y="${textY}">${e(first)}${done ? ' ✓' : ''}</text>
          ${second ? `<text class="pw-node-text" x="${item.x + 10}" y="${textY + 13}">${e(second)}</text>` : ''}
        </g>`;
      }).join('');
      return `<svg class="pw-map-svg" viewBox="0 0 ${Math.max(320, width)} ${Math.max(120, height)}" width="${Math.max(320, width)}" height="${Math.max(120, height)}" role="img" aria-label="学习路线树，共 ${nodes.length} 个节点">
        <title>学习路线树预览</title>${edges}${boxes}</svg>`;
    }

    function resultMarkup() {
      const banner = state.notice && state.step !== 'result' ? `<p class="pw-notice" role="status">${e(state.notice)}</p>` : '';
      const failed = (state.step === 'failed' || (state.step === 'form' && state.error)) ? jobBanner() : '';
      const polling = (state.step === 'polling' || state.step === 'submitting') ? jobBanner() : '';
      const draft = state.step === 'result' && state.draft?.status==='draft' ? `<div class="pw-draft-resume"><div><strong>草稿已保存：${e(state.draft.title)}</strong><p>可打开预览，核对阶段与每日安排。</p></div><button type="button" class="button button-outline" data-pw-openreview>查看草稿</button></div>` : '';
      const empty = '';
      return banner + polling + failed + draft + empty;
    }

    function bindResult(target) {
      if (!target) return;
      const find = selector => target.querySelector(selector);
      const adoptButton = find('[data-pw-adopt]');if(adoptButton)adoptButton.onclick=adopt;
      const regenerateButton = find('[data-pw-regenerate]');if(regenerateButton)regenerateButton.onclick=regenerate;
      find('[data-pw-openreview]')?.addEventListener('click',()=>{state.reviewOpen=true;renderResult();});
      find('[data-pw-view]')?.addEventListener('click', () => { try { navigate('#space/analysis/plans'); } catch (_) { /* navigation optional */ } });
      find('[data-pw-export]')?.addEventListener('click', () => download('xmind'));
      find('[data-pw-mm]')?.addEventListener('click', () => download('mm'));
      find('[data-pw-dismiss]')?.addEventListener('click', async () => {
        savePending(null);
        state.error = '';
        state.notice = '';
        resultHost().innerHTML = '';
        await refreshDrafts();
      });
      const preview = find('[data-pw-preview]');
      if (preview) preview.addEventListener('click', () => togglePreview(preview));
    }

    async function refreshDrafts() {
      try {
        const data = await apiJson('/api/learning/space/plan/list');
        if (!host) return;
        state.jobs = data.jobs || [];
        const drafts = (Array.isArray(data.drafts) ? data.drafts : []).filter(plan=>plan.status==='draft'&&plan.id!==data.active?.id);
        if (drafts.length) {
          state.draft = drafts[0];
          state.step = 'result';
          state.notice = '';
        } else {
          state.draft = null;
          state.step = 'form';
          state.notice = '';
        }
        renderResult();
      } catch (error) {
        state.step = 'form';
        state.error = '读取计划列表失败：' + (error && error.message ? error.message : '请刷新后重试。');
        renderResult();
      }
    }

    // ---------------------------------------------------------------- context
    async function loadMaterials() {
      try {
        const data = await apiJson('/api/learning/space/materials');
        const rows = Array.isArray(data.materials) ? data.materials : [];
        const subjects = [];
        rows.forEach(material => {
          if (material && material.subject && !subjects.includes(material.subject)) subjects.push(material.subject);
        });
        materials = { loaded: true, available: data.available === true, subjects, items: rows, error: '' };
      } catch (error) {
        materials = {
          loaded: false,
          available: false,
          subjects: [],
          items: [],
          error: error && error.code ? errorText(error.code) : '资料列表读取失败'
        };
      }
      if (!host) return;
      renderSubjects();
      renderProjection();
      const availability = host.querySelector('[data-pw-availability]');
      if (availability) {
        availability.textContent = materials.loaded
          ? (materials.available ? '模型已配置；生成会调用外部模型并可能产生费用。' : '模型尚未配置，当前只能查看排程估算，不能生成草稿。')
          : '资料统计暂不可用；不影响填写目标与查看估算。';
        availability.hidden = false;
      }
    }

    async function resume() {
      const pending = pendingRequest();
      if (pending && pending.jobId) {
        state.jobId = pending.jobId;
        try {
          const data = await apiJson('/api/learning/space/jobs/' + encodeURIComponent(pending.jobId));
          if (!host) return;
          if (data.job && !TERMINAL.includes(data.job.status)) {
            state.step = 'polling';
            state.job = data.job;
            renderResult();
            startPolling();
            return;
          }
          if (data.job && data.job.status === 'succeeded') {
            savePending(null);
            state.step = 'result';
            await loadDraft((data.job.result && data.job.result.planId) || '');
            state.reviewOpen = Boolean(state.draft && state.draft.status !== 'active');
            renderResult();
            return;
          }
          if (data.job && data.job.checkpoint && data.job.checkpoint.planId) { await finishJob(data.job); return; }
          if (data.job) {
            state.step = 'failed';
            state.job = data.job;
            state.error = failureText(data.job);
            renderResult();
            return;
          }
        } catch (_) { /* fall back to the newest draft below */ }
        savePending(null);
      }
      await refreshDrafts();
    }

    // ------------------------------------------------------------------ shell
    function shellMarkup() {
      return `
<section class="plan-workbench" aria-label="个性化学习工作台">
  <header class="pw-header">
    <div>
      <h2>个性化学习</h2>
      <p>按学习目标生成阶段路线与每日排期；先看草稿，再决定是否采用。目标与学科可以只填文字，不要求先上传资料。</p>
    </div>
    <div class="pw-header-actions">
      <button type="button" class="button button-outline button-small" data-pw-connectivity>检查模型连接（不生成）</button>
    </div>
  </header>
  <nav class="pw-entry-nav" aria-label="个性化学习导航"><span aria-current="page">定制计划</span><a href="#space/analysis/plans" data-pw-my-plans>我的计划 <span aria-hidden="true">→</span></a></nav>
  <div class="pw-grid">
    <form class="pw-form panel" data-pw-form novalidate>
      <fieldset class="pw-fieldset">
        <legend>学科 / 专题（可多选，可不选）</legend>
        <div class="pw-chips" data-pw-subjects role="group" aria-label="学科与专题"><p class="pw-hint">正在读取学科…</p></div>
        <label class="form-field pw-inline">其他学科或专题（可选，逗号分隔）
          <input type="text" data-pw-custom-subjects maxlength="200" placeholder="例如：图论、动态规划" autocomplete="off">
        </label>
        <p class="pw-hint">不选学科也可以生成；服务端会在草稿中标注实际采用的学科范围。本机没有资料题目时，任务会标注“未绑定本地题目”。</p>
      </fieldset>
      <fieldset class="pw-fieldset">
        <legend>难度</legend>
        <div class="pw-segmented" role="group" aria-label="难度">
          ${DIFFICULTIES.map(item => `<button type="button" class="pw-segment" data-pw-difficulty="${e(item.value)}" aria-pressed="false">${e(item.label)}</button>`).join('')}
        </div>
        <p class="pw-hint" data-pw-difficulty-hint></p>
      </fieldset>
      <div class="pw-row">
        <label class="form-field">开始日期<input type="date" data-pw-start required></label>
        <label class="form-field">结束日期<input type="date" data-pw-end required></label>
        <label class="form-field">持续天数<input type="number" data-pw-days min="1" max="366" step="1" required></label>
      </div>
      <p class="pw-hint" data-pw-date-hint></p>
      <label class="form-field">计划名称<input type="text" data-pw-title maxlength="60" required></label>
      <label class="form-field">学习目标<textarea data-pw-goal rows="3" maxlength="1000" required placeholder="例如：两周内掌握图的遍历与最短路径，并完成配套练习"></textarea></label>
      <p class="pw-hint pw-counter" data-pw-goal-count>0/1000</p>
      <div class="pw-slider-field">
        <label for="pwDailyMinutes">每日可用时间 <output data-pw-minutes-out>60 分钟</output></label>
        <input id="pwDailyMinutes" type="range" data-pw-minutes min="15" max="480" step="5" value="60">
        <div class="pw-slider-scale"><span>15 分钟</span><span>4 小时</span><span>8 小时</span></div>
      </div>
      <fieldset class="pw-fieldset">
        <legend>固定休息日（可多选，当天不安排任务）</legend>
        <div class="pw-chips" role="group" aria-label="固定休息日">
          ${WEEKDAYS.map(day => `<button type="button" class="pw-chip" data-pw-rest="${day.value}" aria-pressed="false">${e(day.label)}</button>`).join('')}
        </div>
      </fieldset>
      <p class="pw-form-error" data-pw-form-error role="alert" hidden></p>
      <div class="pw-form-actions">
        <button type="submit" class="button button-blue" data-pw-generate>生成草稿</button>
        <button type="button" class="button button-outline" data-pw-reset>取消 / 重置</button>
      </div>
      <p class="pw-hint" data-pw-availability hidden></p>
    </form>
    <aside class="pw-projection panel" aria-label="AI 排程实时推演">
      <div data-pw-projection><p class="pw-hint">正在计算…</p></div>
    </aside>
  </div>
  <section class="pw-result" data-pw-result aria-live="polite"></section>
</section>`;
    }

    function bindShell() {
      const form = formDom();
      if (!form) return;
      const update = (mutate, options = {}) => {
        mutate();
        saveStore();
        if (options.projection !== false) renderProjection();
        if (options.subjects) renderSubjects();
        if (options.dates) updateDateHints();
        if (options.difficulty) renderDifficulty();
        if (options.rest) renderRestDays();
      };
      form.querySelector('[data-pw-title]').addEventListener('input', event => update(() => { state.form.title = clampText(event.target.value, 60); }));
      form.querySelector('[data-pw-goal]').addEventListener('input', event => {
        state.form.goal = String(event.target.value).slice(0, 1000);
        form.querySelector('[data-pw-goal-count]').textContent = state.form.goal.length + '/1000';
        saveStore();
      });
      form.querySelector('[data-pw-custom-subjects]').addEventListener('input', event => update(() => { state.form.customSubjects = clampText(event.target.value, 200); }));
      form.querySelector('[data-pw-start]').addEventListener('change', event => {
        update(() => {
          if (!parseISO(event.target.value)) return;
          state.form.startDate = event.target.value;
          const days = Number(state.form.daysCount);
          if (Number.isInteger(days) && days >= 1) state.form.endDate = addDays(state.form.startDate, days - 1);
          else state.form.endDate = addDays(state.form.startDate, 13);
        }, { dates: true });
        applyFormToDom();
      });
      form.querySelector('[data-pw-end]').addEventListener('change', event => {
        update(() => {
          if (!parseISO(event.target.value)) return;
          state.form.endDate = event.target.value;
          const days = daysBetween(state.form.startDate, state.form.endDate);
          if (days >= 1) state.form.daysCount = days;
        }, { dates: true });
        applyFormToDom();
      });
      form.querySelector('[data-pw-days]').addEventListener('change', event => {
        update(() => {
          const days = parseInt(event.target.value, 10);
          state.form.daysCount = Number.isInteger(days) ? Math.max(1, Math.min(366, days)) : state.form.daysCount;
          if (parseISO(state.form.startDate)) state.form.endDate = addDays(state.form.startDate, state.form.daysCount - 1);
        }, { dates: true });
        applyFormToDom();
      });
      form.querySelector('[data-pw-minutes]').addEventListener('input', event => {
        update(() => {
          const value = parseInt(event.target.value, 10);
          state.form.dailyMinutes = Number.isFinite(value) ? Math.max(15, Math.min(480, value)) : 60;
        });
        form.querySelector('[data-pw-minutes-out]').textContent = state.form.dailyMinutes + ' 分钟';
      });
      form.querySelectorAll('[data-pw-difficulty]').forEach(button => {
        button.addEventListener('click', () => update(() => { state.form.difficulty = button.dataset.pwDifficulty; }, { difficulty: true }));
      });
      form.querySelectorAll('[data-pw-rest]').forEach(button => {
        button.addEventListener('click', () => update(() => {
          const day = Number(button.dataset.pwRest);
          state.form.restDays = state.form.restDays.includes(day)
            ? state.form.restDays.filter(value => value !== day)
            : state.form.restDays.concat(day).sort((a, b) => a - b);
        }, { rest: true, dates: true }));
      });
      form.addEventListener('submit', event => { event.preventDefault(); generate(); });
      host.querySelector('[data-pw-reset]').addEventListener('click', () => {
        state.form = defaultForm();
        state.error = '';
        state.step = state.draft ? 'result' : 'form';
        saveStore();
        applyFormToDom();
        renderSubjects();
        renderProjection();
        showFormError([], []);
        renderResult();
        notify('已重置表单；已有草稿仍保留，可点击“查看草稿”。');
      });
      host.querySelector('[data-pw-connectivity]').addEventListener('click', async event => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          const data = await apiJson('/api/learning/space/plan/connectivity');
          notify(data.connected === true
            ? '模型站点连接正常；本次没有生成计划或调用推理接口。'
            : '当前为受控/测试模型，未验证外部连接。');
        } catch (error) {
          notify('连接检查未完成：' + (error && error.message ? error.message : '请检查本地服务。'));
        } finally {
          if (button.isConnected) button.disabled = false;
        }
      });
    }

    // ------------------------------------------------------------------- mount
    function mount(node) {
      if (!node) return;
      host = node;
      state.reviewOpen = false;
      stamp += 1;
      clearTimeout(timer);
      loadStore();
      host.innerHTML = shellMarkup();
      applyFormToDom();
      renderSubjects();
      renderProjection();
      renderResult();
      bindShell();
      loadMaterials();
      resume();
    }

    function unmount() {
      stamp += 1;
      clearTimeout(timer);
      if (controller) { try { controller.abort(); } catch (_) { /* ignore */ } controller = null; }
      host = null;
      state.reviewOpen = false;
      if(reviewDialog){reviewDialog.close();reviewDialog.remove();reviewDialog=null;}
    }

    return { mount, unmount };
  }

  root.XueyaPlanWorkbench = { create };
})(typeof window === 'undefined' ? globalThis : window);
