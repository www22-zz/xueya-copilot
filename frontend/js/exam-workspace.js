/* 408 exam workbench: two-card landing, mock-exam dialog and full-screen sitting.
   Every number comes from GET /api/learning/space/exams; unsupported metrics show "—".
   Answers, deadlines and grades are always reloaded from the server record. */
(() => {
  'use strict';
  const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const LETTERS='ABCDEF';
  const STATUS_LABEL={ready:'未开始',running:'计时中',submitted:'已交卷'};
  const JOB_LABEL={queued:'排队中',running:'生成中',succeeded:'已完成',failed:'生成失败',cancelled:'已取消',unknown:'结果未知'};
  const SAVE_ICON={idle:'cloud_upload',saving:'cloud_sync',saved:'cloud_done',error:'cloud_off'};
  const ERROR_TEXT={
    SERVICE_UNAVAILABLE:'本地服务未连接，请确认服务已启动并刷新页面。',
    AUTH_REQUIRED:'访问令牌已失效，请刷新页面后重试。',
    ORIGIN_FORBIDDEN:'当前页面来源不被服务端允许，请使用本机地址打开。',
    AI_UNAVAILABLE:'AI 模型未配置或不可用，请改用程序选编，或在服务端配置外部 API。',
    AI_TIMEOUT:'AI 请求超时；后台不会自动重复付费重试。',
    INSUFFICIENT_EXAM_QUESTIONS:'该科目可用的固定单选题不足，请减少题量或改为全部 408 科目。',
    INVALID_EXAM_DURATION:'时长需为 1–180 分钟的整数。',
    INVALID_EXAM_MODE:'组卷方式无效。',
    INVALID_SUBJECT:'科目参数无效。',
    EXAM_NOT_FOUND:'试卷不存在或不属于当前账号。',
    EXAM_REVISION_CONFLICT:'试卷已在其他窗口更新，请刷新后再操作。',
    EXAM_NOT_STARTED:'考试尚未开始计时。',
    EXAM_ALREADY_STARTED:'考试已经开始计时。',
    INVALID_ANSWER:'答案格式无效。',
    QUESTION_NOT_IN_EXAM:'答案对应的题目不在本试卷中。',
    IDEMPOTENCY_CONFLICT:'相同的操作编号被用于不同请求，请重试。',
    JOB_TYPE_UNAVAILABLE:'后台暂不支持该类型组卷任务。',
    INVALID_JOB:'组卷任务参数无效。',
    INVALID_REQUEST:'请求参数无效，请检查题量与时长。',
    EXAM_RESPONSE_INVALID:'服务端返回格式不正确，请刷新页面重试。'
  };
  let generation=0,activeDialog=null,visibilityHandler=null;
  const timers={clock:null,poll:null,retry:null};
  const clearTimer=key=>{if(timers[key]){clearTimeout(timers[key]);clearInterval(timers[key]);timers[key]=null;}};
  const clearTimers=()=>Object.keys(timers).forEach(clearTimer);
  function errorText(error){
    const code=(error&&(error.code||error.message))||String(error||'');
    return ERROR_TEXT[code]||String((error&&error.message)||code||'未知错误');
  }
  function operationId(){
    try{if(window.crypto&&typeof window.crypto.randomUUID==='function')return window.crypto.randomUUID();}catch{}
    return 'exam-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,12);
  }
  function safeUrl(value){const url=String(value??'');const isHttp=/^https?:\/\//i.test(url);return isHttp?e(url):'#';}
  function formatDate(value){
    if(!value)return '';
    const date=new Date(value);
    if(Number.isNaN(date.getTime()))return '';
    try{return new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(date);}catch{return '';}
  }
  function formatClock(seconds){
    const safe=Math.max(0,Number(seconds)||0);
    const h=Math.floor(safe/3600),m=Math.floor(safe%3600/60),s=safe%60;
    return (h?String(h).padStart(2,'0')+':':'')+String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
  }
  const timestamp=()=>{try{return new Date().toLocaleTimeString('zh-CN',{hour12:false});}catch{return '';}};
  function api(path,options){return window.XueyaPlatform.spaceFetch('/api/learning/space/'+path,options);}
  async function getJSON(path){return (await api(path)).json();}
  async function postJSON(path,body){return (await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();}
  const activeJobs=data=>(Array.isArray(data.jobs)?data.jobs:[]).filter(job=>['queued','running','cancelling'].includes(job.status));
  function sessionBreakdown(sessions){
    if(!sessions.length)return '仅本站生成的模拟卷';
    const count=status=>sessions.filter(session=>session.status===status).length;
    return `${count('ready')} 份未开始 · ${count('running')} 份进行中 · ${count('submitted')} 份已交卷`;
  }
  function paperSubjects(paper){
    const subjects=[...new Set((paper.questions||[]).map(question=>question.subject).filter(Boolean))];
    return subjects.join(' · ')||'408 综合';
  }
  function destroyDialog(dialog){
    if(!dialog)return;
    if(activeDialog===dialog)activeDialog=null;
    try{if(dialog.open)dialog.close();}catch{}
    setTimeout(()=>{try{dialog.remove();}catch{}},0);
  }
  function openDialog(markup,{className='ew-dialog',onClose=null}={}){
    if(activeDialog)destroyDialog(activeDialog);
    const dialog=document.createElement('dialog');
    dialog.className=className;
    dialog.innerHTML=markup;
    dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
    dialog.addEventListener('close',()=>{
      if(activeDialog===dialog)activeDialog=null;
      setTimeout(()=>{try{dialog.remove();}catch{}},0);
      if(!dialog._ewSilent&&typeof onClose==='function'){try{onClose();}catch{}}
    });
    document.body.append(dialog);
    activeDialog=dialog;
    if(typeof dialog.showModal==='function'){try{dialog.showModal();}catch{dialog.setAttribute('open','');}}else{dialog.setAttribute('open','');}
    return dialog;
  }
  function confirmAction({title,message,confirmLabel='确认',cancelLabel='取消',danger=false}){
    return new Promise(resolve=>{
      let settled=false;
      const settle=value=>{if(settled)return;settled=true;resolve(value);};
      const dialog=openDialog(`<div class="ew-dialog-shell ew-confirm-shell">
          <header class="ew-dialog-head">
            <h2 id="ew-confirm-title">${e(title)}</h2>
            <button type="button" class="ew-icon-btn" data-ew-confirm-cancel aria-label="取消并关闭"><span class="material-symbols-outlined" aria-hidden="true">close</span></button>
          </header>
          <div class="ew-dialog-body">
            <p class="ew-confirm-text">${e(message)}</p>
            <div class="ew-dialog-actions">
              <button type="button" class="ew-btn ew-btn-outline" data-ew-confirm-cancel>${e(cancelLabel)}</button>
              <button type="button" class="ew-btn ${danger?'ew-btn-danger':'ew-btn-primary'}" data-ew-confirm-yes>${e(confirmLabel)}</button>
            </div>
          </div>
        </div>`,
        {className:'ew-dialog ew-dialog--confirm',onClose:()=>settle(false)});
      dialog.setAttribute('aria-labelledby','ew-confirm-title');
      const finish=value=>{
        if(settled)return;
        settled=true;
        resolve(value);
        try{if(dialog.open)dialog.close();else dialog.remove();}catch{}
      };
      dialog.querySelectorAll('[data-ew-confirm-cancel]').forEach(button=>{button.onclick=()=>finish(false);});
      const yes=dialog.querySelector('[data-ew-confirm-yes]');
      if(yes)yes.onclick=()=>finish(true);
      const cancel=dialog.querySelector('[data-ew-confirm-cancel]');
      if(cancel)try{cancel.focus();}catch{}
    });
  }
  function loadingMarkup(text){
    return `<div class="ew-page"><div class="ew-loading" role="status" aria-live="polite"><span class="ew-spinner" aria-hidden="true"></span><span>${e(text)}</span></div></div>`;
  }
  function errorMarkup(message,{detail=false,retry=true}={}){
    return `<div class="ew-page">${detail?'<div class="ew-sitting">':''}<section class="ew-error-panel" role="alert">
        <span class="material-symbols-outlined ew-error-icon" aria-hidden="true">error</span>
        <h1>${detail?'试卷暂时不可用':'408 工作台暂时不可用'}</h1>
        <p>${e(message)}</p>
        <p class="ew-error-hint">页面不会展示估算数字，也不会假装保存成功；请确认本地服务正在运行后重试。</p>
        <div class="ew-error-actions">
          ${retry?`<button type="button" class="ew-btn ew-btn-primary" data-ew-retry>${detail?'重新读取试卷':'重新加载工作台'}</button>`:''}
          <a class="ew-btn ew-btn-outline" href="#space/exams">返回试卷列表</a>
        </div>
      </section>${detail?'</div>':''}</div>`;
  }
  function saveStatusMarkup(saveState,saveText){
    const text=saveState==='saving'?'正在保存…':saveState==='saved'?'已保存到服务端':saveState==='error'?(saveText||'保存失败，请核对服务端记录'):'选择答案后自动保存';
    return `<p class="ew-save" data-ew-save data-state="${e(saveState)}" role="status" aria-live="polite"><span class="material-symbols-outlined" aria-hidden="true">${SAVE_ICON[saveState]||'cloud_upload'}</span><span data-ew-save-text>${e(text)}</span></p>`;
  }

  /* ---------- landing ---------- */
  function landingMarkup(data){
    const sessions=Array.isArray(data.sessions)?data.sessions:[];
    const subjects=Array.isArray(data.subjects)?data.subjects:[];
    const originals=(Array.isArray(data.originalPapers)?data.originalPapers:[]).filter(item=>item&&typeof item==='object');
    const verification=(originals.find(item=>item.verification)||{}).verification||'';
    return `<div class="ew-page" data-ew-page>
      <section class="ew-hero" aria-labelledby="ew-title">
        <div class="ew-hero-copy">
          <span class="ew-eyebrow"><span class="material-symbols-outlined" aria-hidden="true">target</span> EXAM 408 · 计算机学科专业基础</span>
          <h1 id="ew-title">408 考研智能备考工作台</h1>
          <p class="ew-hero-lede">把 408 的练习、模拟与复盘收进一个本地优先的工作台。站内题目是 408 考点的<strong>改编/原创模拟题</strong>，不是历年真题；历年原卷与整理解析仅提供<strong>外部链接</strong>，原卷未结构化接入站内自动评分。</p>
          <div class="ew-meta-row" aria-label="工作台特性">
            <span><span class="material-symbols-outlined" aria-hidden="true">cloud_done</span>服务端权威计时</span>
            <span><span class="material-symbols-outlined" aria-hidden="true">save</span>逐题自动保存</span>
            <span><span class="material-symbols-outlined" aria-hidden="true">sync</span>刷新可恢复</span>
          </div>
        </div>
        <aside class="ew-boundary" aria-label="数据与评分边界">
          <span class="material-symbols-outlined ew-boundary-icon" aria-hidden="true">verified_user</span>
          <div>
            <strong>先说明数据与评分边界</strong>
            <ul>
              <li>站内题是改编/原创模拟题，不冒充历年真题。</li>
              <li>原卷与解析来自外部公开资料，仅用于追溯考点。</li>
              <li>本页统计只取接口实时返回值，未接入指标显示“—”。</li>
            </ul>
          </div>
        </aside>
      </section>

      <section class="ew-stats" aria-label="备考数据概览">
        <div class="ew-stat">
          <span class="material-symbols-outlined ew-stat-icon" aria-hidden="true">library_books</span>
          <span class="ew-stat-label">我的模拟卷</span>
          <strong class="ew-stat-value" data-ew-stat="sessions">${sessions.length}</strong>
          <small class="ew-stat-note" data-ew-stat-note="sessions">${e(sessionBreakdown(sessions))}</small>
        </div>
        <div class="ew-stat">
          <span class="material-symbols-outlined ew-stat-icon" aria-hidden="true">category</span>
          <span class="ew-stat-label">可用科目</span>
          <strong class="ew-stat-value" data-ew-stat="subjects">${subjects.length}</strong>
          <small class="ew-stat-note" data-ew-stat-note="subjects">${e(subjects.join(' · '))||'暂无可用科目'}</small>
        </div>
        <div class="ew-stat">
          <span class="material-symbols-outlined ew-stat-icon" aria-hidden="true">link</span>
          <span class="ew-stat-label">原卷外部链接</span>
          <strong class="ew-stat-value" data-ew-stat="papers">${originals.length}</strong>
          <small class="ew-stat-note">仅外部链接 · 未接入站内评分</small>
        </div>
        <div class="ew-stat is-unavailable">
          <span class="material-symbols-outlined ew-stat-icon" aria-hidden="true">insights</span>
          <span class="ew-stat-label">预测估分</span>
          <strong class="ew-stat-value" data-ew-stat="score">—</strong>
          <small class="ew-stat-note">未接入 · 不做估算</small>
        </div>
      </section>

      <section class="ew-modes" aria-label="选择备考方式">
        <article class="ew-mode ew-mode--practice">
          <div class="ew-mode-top"><span class="ew-mode-icon material-symbols-outlined" aria-hidden="true">menu_book</span><span class="ew-mode-label">Self-Paced</span></div>
          <h2>自主练习</h2>
          <p>按科目与章节自由练习 408 固定题库，先建立稳定手感，再回到错题逐个解决。</p>
          <ul class="ew-mode-list">
            <li><span class="material-symbols-outlined" aria-hidden="true">check_circle</span>四科分章，单选与综合应用分开练习</li>
            <li><span class="material-symbols-outlined" aria-hidden="true">check_circle</span>综合题按小问保存过程，对照评分点自评</li>
            <li><span class="material-symbols-outlined" aria-hidden="true">check_circle</span>错题进入统一错题本，按真实作答记录复习</li>
          </ul>
          <a class="ew-btn ew-btn-primary ew-btn-lg ew-mode-cta" href="#space/practice/exam408"><span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span>进入自主练习</a>
        </article>
        <article class="ew-mode ew-mode--simulation">
          <div class="ew-mode-top"><span class="ew-mode-icon material-symbols-outlined" aria-hidden="true">timer</span><span class="ew-mode-label">Exam Simulation</span></div>
          <h2>模拟考试</h2>
          <p>按真实考试节奏组一卷：服务端计时、逐题保存、交卷评分，用来检验阶段水平。</p>
          <div class="ew-mode-facts"><span><strong>1–40</strong> 题</span><span><strong>1–180</strong> 分钟</span><span><strong>2</strong> 种组卷</span></div>
          <p class="ew-mode-hint">程序选编不调用 AI；AI 选题会调用外部模型，可能产生 API 费用。</p>
          <button type="button" class="ew-btn ew-btn-primary ew-btn-lg ew-mode-cta" data-ew-action="open-dialog"><span class="material-symbols-outlined" aria-hidden="true">tune</span>设置并开始模拟</button>
        </article>
      </section>

      <section class="ew-section" data-ew-papers aria-labelledby="ew-papers-title">
        <div class="ew-section-head">
          <div><span class="ew-eyebrow">My Papers</span><h2 id="ew-papers-title">我的试卷</h2></div>
          <div class="ew-section-tools">
            <span class="ew-chip" data-ew-session-count>${sessions.length} 份</span>
            <button type="button" class="ew-btn ew-btn-outline ew-btn-sm" data-ew-action="refresh"><span class="material-symbols-outlined" aria-hidden="true">refresh</span>刷新</button>
          </div>
        </div>
        <div class="ew-jobs" data-ew-jobs>${jobsMarkup(data)}</div>
        <div data-ew-sessions>${papersMarkup(data)}</div>
      </section>

      <details class="ew-original">
        <summary class="ew-original-summary">
          <span class="material-symbols-outlined" aria-hidden="true">description</span>
          <span><strong>真题原卷与整理解析</strong><small>外部链接 · ${originals.length} 份年份资料 · 未接入站内自动评分</small></span>
          <span class="ew-chevron material-symbols-outlined" aria-hidden="true">expand_more</span>
        </summary>
        <div class="ew-original-body">
          <p class="ew-original-status">${e(data.originalPaperStatus||'原卷与整理解析来自外部公开资料；站内题目为改编/原创，不能冒充对应年份原题。')}</p>
          <div class="ew-original-grid">${originals.map(originalRow).join('')}</div>
          ${verification?`<p class="ew-original-note">链接核验：${e(verification)}</p>`:''}
        </div>
      </details>

      <p class="ew-footnote">页面数字仅来自接口实时返回；接口未提供的指标（如预测估分、真题总量）显示“—”，不做估算。模拟卷题目为固定题的改编/原创快照，交卷后由服务端判定客观题得分。</p>
    </div>`;
  }
  function originalRow(item){
    return `<div class="ew-original-row">
      <span class="ew-year">${e(item.year)}</span>
      <a href="${safeUrl(item.paper)}" target="_blank" rel="noopener noreferrer"><span class="material-symbols-outlined" aria-hidden="true">picture_as_pdf</span>原卷 PDF</a>
      <a href="${safeUrl(item.answers)}" target="_blank" rel="noopener noreferrer"><span class="material-symbols-outlined" aria-hidden="true">fact_check</span>整理解析（非官方评分）</a>
    </div>`;
  }
  function papersMarkup(data){
    const sessions=(Array.isArray(data.sessions)?data.sessions.slice():[]).sort((a,b)=>String(b.createdAt||'').localeCompare(String(a.createdAt||'')));
    if(!sessions.length)return `<div class="ew-empty"><span class="material-symbols-outlined" aria-hidden="true">assignment</span><div><strong>还没有模拟试卷</strong><p>创建一份模拟卷后，可以从这里继续作答或查看交卷结果。</p></div><button type="button" class="ew-btn ew-btn-primary ew-btn-sm" data-ew-action="open-dialog">创建第一份</button></div>`;
    return `<div class="ew-paper-list">${sessions.map(session=>{
      const status=STATUS_LABEL[session.status]||session.status||'未知状态';
      const questions=Array.isArray(session.questions)?session.questions.length:0;
      const result=session.result;
      return `<a class="ew-paper" href="#space/exams/${e(session.id)}">
        <span class="ew-status-pill is-${e(session.status||'ready')}">${e(status)}</span>
        <span class="ew-paper-main"><strong>${e(session.label||'模拟卷')}</strong><small>${e(paperSubjects(session))} · ${questions} 题 · ${e(session.minutes)} 分钟${session.createdAt?` · ${e(formatDate(session.createdAt))}`:''}</small></span>
        <span class="ew-paper-side">${session.status==='submitted'&&result?`<strong>${e(result.score)}</strong><small>/${e(result.maxScore)} 分</small>`:'<span class="ew-paper-enter">继续 <span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span></span>'}</span>
      </a>`;
    }).join('')}</div>`;
  }
  function jobsMarkup(data){
    const jobs=(Array.isArray(data.jobs)?data.jobs:[]).filter(job=>job&&job.status!=='succeeded').slice(0,4);
    if(!jobs.length)return '';
    return jobs.map(job=>{
      const status=JOB_LABEL[job.status]||job.status||'未知状态';
      const pending=['queued','running','cancelling'].includes(job.status);
      const note=pending?'后台正在组卷，页面会自动刷新；关闭弹窗与刷新页面都不会重复付费。':job.status==='failed'?(job.error?`失败原因：${e(errorText({message:job.error,code:job.error}))}。未自动重试。`:'后台未返回详细错误；未自动重试。'):job.status==='cancelled'?'任务已取消，不会重试。':'结果未知，不会自动重试；请稍后刷新核对。';
      return `<div class="ew-job is-${e(job.status||'unknown')}"><span class="material-symbols-outlined" aria-hidden="true">${pending?'hourglass_top':job.status==='failed'?'error':'help'}</span><div><strong>AI 组卷 · ${e(status)}</strong><small>${note}</small></div></div>`;
    }).join('');
  }
  function applyLanding(container,data){
    container._ewData=data;
    const sessions=Array.isArray(data.sessions)?data.sessions:[];
    const subjects=Array.isArray(data.subjects)?data.subjects:[];
    const originals=(Array.isArray(data.originalPapers)?data.originalPapers:[]).filter(Boolean);
    const set=(selector,value)=>{const node=container.querySelector(selector);if(node)node.textContent=String(value);};
    set('[data-ew-stat="sessions"]',sessions.length);
    set('[data-ew-stat="subjects"]',subjects.length);
    set('[data-ew-stat="papers"]',originals.length);
    set('[data-ew-stat-note="sessions"]',sessionBreakdown(sessions));
    set('[data-ew-stat-note="subjects"]',subjects.join(' · ')||'暂无可用科目');
    set('[data-ew-session-count]',sessions.length+' 份');
    const jobs=container.querySelector('[data-ew-jobs]');
    const jobSignature=(Array.isArray(data.jobs)?data.jobs:[]).map(job=>`${job.id}:${job.status}`).join('|');
    if(jobs&&container._ewJobSignature!==jobSignature){container._ewJobSignature=jobSignature;jobs.innerHTML=jobsMarkup(data);}
    const list=container.querySelector('[data-ew-sessions]');
    const sessionSignature=sessions.map(session=>`${session.id}:${session.status}`).join('|');
    if(list&&container._ewSessionSignature!==sessionSignature){container._ewSessionSignature=sessionSignature;list.innerHTML=papersMarkup(data);}
  }
  function scheduleLandingPoll(container,stamp,data){
    clearTimer('poll');
    if(!activeJobs(data).length)return;
    timers.poll=setTimeout(()=>pollLanding(container,stamp),2500);
  }
  async function pollLanding(container,stamp){
    timers.poll=null;
    if(stamp!==generation||!container.isConnected)return;
    try{
      const data=await getJSON('exams');
      if(stamp!==generation||!container.isConnected)return;
      applyLanding(container,data);
      scheduleLandingPoll(container,stamp,data);
    }catch(error){
      if(stamp!==generation||!container.isConnected)return;
      const region=container.querySelector('[data-ew-jobs]');
      if(region&&!region.querySelector('[data-ew-job-error]'))region.insertAdjacentHTML('beforeend',`<p class="ew-job-error" data-ew-job-error role="alert">组卷状态刷新失败：${e(errorText(error))}；页面会继续重试。</p>`);
      scheduleLandingPoll(container,stamp,container._ewData||{});
    }
  }
  async function refreshLandingOnce(container,stamp){
    if(!container.isConnected||stamp!==generation)return;
    try{
      const data=await getJSON('exams');
      if(stamp!==generation||!container.isConnected)return;
      applyLanding(container,data);
      scheduleLandingPoll(container,stamp,data);
    }catch{}
  }
  async function mountLanding(container,stamp){
    container.onclick=null;container.onchange=null;
    container.innerHTML=loadingMarkup('正在读取 408 备考数据…');
    let data;
    try{data=await getJSON('exams');}
    catch(error){
      if(stamp!==generation||!container.isConnected)return;
      container.innerHTML=errorMarkup(errorText(error));
      container.onclick=event=>{if(event.target.closest('[data-ew-retry]')&&container.isConnected)mount(container);};
      return;
    }
    if(stamp!==generation||!container.isConnected)return;
    drawLanding(container,data,stamp);
  }
  function drawLanding(container,data,stamp){
    container._ewData=data;
    container.innerHTML=landingMarkup(data);
    container.onclick=event=>{
      const trigger=event.target.closest('[data-ew-action]');
      if(!trigger)return;
      const action=trigger.dataset.ewAction;
      if(action==='open-dialog'){event.preventDefault();openCreateDialog(container,stamp);}
      else if(action==='refresh'||action==='retry'){mount(container);}
    };
    scheduleLandingPoll(container,stamp,data);
  }

  /* ---------- mock-exam dialog ---------- */
  function createDialogMarkup(data){
    const subjects=Array.isArray(data.subjects)?data.subjects:[];
    return `<div class="ew-dialog-shell">
      <header class="ew-dialog-head">
        <div><span class="ew-eyebrow">Exam Simulation</span><h2 id="ew-dialog-title">设置模拟考试</h2></div>
        <button type="button" class="ew-icon-btn" data-ew-dialog-close aria-label="关闭模拟考试设置"><span class="material-symbols-outlined" aria-hidden="true">close</span></button>
      </header>
      <form class="ew-dialog-body" data-ew-form>
        <p class="ew-dialog-note" id="ew-dialog-note">题目来自站内固定 408 题库的改编/原创模拟题，交卷后由服务端判定客观题并保存作答记录。</p>
        <div class="ew-form-grid">
          <label class="ew-field"><span>科目</span><select name="subject"><option value="">全部 408 科目</option>${subjects.map(subject=>`<option value="${e(subject)}">${e(subject)}</option>`).join('')}</select></label>
          <label class="ew-field"><span>题量<small>1–40 题</small></span><input name="count" type="number" min="1" max="40" step="1" value="10" inputmode="numeric" required></label>
          <label class="ew-field"><span>时长<small>1–180 分钟</small></span><input name="minutes" type="number" min="1" max="180" step="1" value="30" inputmode="numeric" required></label>
        </div>
        <fieldset class="ew-fieldset">
          <legend>组卷方式</legend>
          <label class="ew-mode-choice"><input type="radio" name="mode" value="fixed" checked><span class="ew-mode-choice-body"><strong>程序选编 · 不调用 AI</strong><small>从固定题库按科目与题量选编，不产生模型费用。</small></span></label>
          <label class="ew-mode-choice"><input type="radio" name="mode" value="ai"><span class="ew-mode-choice-body"><strong>AI 选题 · 调用外部模型</strong><small>后台调用模型选题，可能产生 API 费用；结果仍是固定题快照，不标为真题。</small></span></label>
        </fieldset>
        <p class="ew-form-status" data-ew-status role="status" aria-live="polite"></p>
        <div class="ew-dialog-actions">
          <button type="button" class="ew-btn ew-btn-outline" data-ew-dialog-close>取消</button>
          <button type="submit" class="ew-btn ew-btn-primary" data-ew-submit><span class="material-symbols-outlined" aria-hidden="true">bolt</span>生成模拟卷</button>
        </div>
      </form>
    </div>`;
  }
  function openCreateDialog(container,stamp){
    const data=container._ewData||{};
    const dialog=openDialog(createDialogMarkup(data),{
      className:'ew-dialog',
      onClose:()=>{stopJobPoll();refreshLandingOnce(container,stamp);}
    });
    const form=dialog.querySelector('[data-ew-form]');
    dialog.setAttribute('aria-labelledby','ew-dialog-title');
    dialog.setAttribute('aria-describedby','ew-dialog-note');
    const status=dialog.querySelector('[data-ew-status]');
    const submit=dialog.querySelector('[data-ew-submit]');
    let jobPoll=null,submitting=false;
    const stopJobPoll=()=>{if(jobPoll){clearTimeout(jobPoll);jobPoll=null;}};
    const closeDialog=()=>{try{if(dialog.open)dialog.close();else dialog.remove();}catch{}};
    const setStatus=(text,kind='')=>{status.textContent=text;status.dataset.kind=kind;};
    const restoreSubmit=()=>{
      if(!submit.isConnected)return;
      submit.disabled=false;
      submit.innerHTML='<span class="material-symbols-outlined" aria-hidden="true">bolt</span>生成模拟卷';
    };
    dialog.querySelectorAll('[data-ew-dialog-close]').forEach(button=>{button.onclick=closeDialog;});
    const subjectSelect=form.querySelector('select[name=subject]');
    if(subjectSelect)try{subjectSelect.focus();}catch{}
    const finishWithSession=session=>{
      stopJobPoll();
      setStatus('模拟卷已生成，正在打开…','success');
      const id=session&&session.id;
      if(!id){setStatus('服务端返回的试卷缺少编号，请刷新后在「我的试卷」中查看。','error');restoreSubmit();return;}
      closeDialog();
      location.hash='space/exams/'+id;
    };
    const jobFailed=(text)=>{
      stopJobPoll();
      submitting=false;
      setStatus(text,'error');
      restoreSubmit();
    };
    const jobSucceeded=session=>{
      stopJobPoll();
      submitting=false;
      setStatus('模拟卷已生成：'+(session.label||'模拟卷')+'。','success');
      if(!submit.isConnected)return;
      const link=document.createElement('a');
      link.className='ew-btn ew-btn-primary';
      link.href='#space/exams/'+encodeURIComponent(session.id);
      link.innerHTML='<span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span>打开试卷';
      submit.replaceWith(link);
    };
    const scheduleJobPoll=jobId=>{
      const baseline=new Set(((container._ewData||{}).sessions||[]).map(session=>session.id));
      let attempts=0;
      const tick=async()=>{
        jobPoll=null;
        if(!dialog.isConnected){stopJobPoll();return;}
        attempts++;
        let next;
        try{next=await getJSON('exams');}
        catch(error){
          if(!dialog.isConnected)return;
          setStatus('状态刷新失败：'+errorText(error)+'；页面会继续重试。','error');
          if(attempts<60)jobPoll=setTimeout(tick,2500);
          return;
        }
        if(!dialog.isConnected)return;
        if(container.isConnected)applyLanding(container,next);
        const created=(Array.isArray(next.sessions)?next.sessions:[]).find(session=>!baseline.has(session.id));
        if(created){jobSucceeded(created);return;}
        const job=(Array.isArray(next.jobs)?next.jobs:[]).find(item=>item.id===jobId);
        if(!job){jobFailed('未找到该组卷任务；请关闭弹窗后刷新「我的试卷」核对。');return;}
        if(['failed','cancelled','unknown'].includes(job.status)){
          const reason=job.error?errorText({message:job.error,code:job.error}):'后台未返回详细错误';
          jobFailed('AI 组卷'+(JOB_LABEL[job.status]||job.status)+'：'+reason+'。可改用「程序选编」重试。');
          return;
        }
        if(job.status==='succeeded'){
          setStatus('AI 组卷已完成，正在读取试卷…','pending');
        }else{
          setStatus('AI 组卷'+(JOB_LABEL[job.status]||job.status)+'…后台任务已提交，页面会自动刷新；关闭弹窗不会取消任务。','pending');
        }
        if(attempts>=90){setStatus('组卷仍在后台进行。可关闭弹窗，稍后在「我的试卷」中刷新查看。','error');stopJobPoll();return;}
        jobPoll=setTimeout(tick,2000);
      };
      jobPoll=setTimeout(tick,1500);
    };
    form.onsubmit=async event=>{
      event.preventDefault();
      if(submitting)return;
      const values=new FormData(form);
      const subject=String(values.get('subject')||'');
      const count=Number(values.get('count'));
      const minutes=Number(values.get('minutes'));
      const mode=String(values.get('mode')||'fixed');
      if(!Number.isInteger(count)||count<1||count>40){setStatus('题量需为 1–40 的整数。','error');form.querySelector('input[name=count]')?.focus();return;}
      if(!Number.isInteger(minutes)||minutes<1||minutes>180){setStatus('时长需为 1–180 分钟的整数。','error');form.querySelector('input[name=minutes]')?.focus();return;}
      submitting=true;
      stopJobPoll();
      submit.disabled=true;
      submit.innerHTML='<span class="ew-spinner" aria-hidden="true"></span>正在生成…';
      setStatus('正在请求服务端生成模拟卷…','pending');
      refreshLandingOnce(container,stamp);
      let keepDisabled=false;
      try{
        const result=await postJSON('exams',{mode,subject,count,minutes,operationId:operationId()});
        if(result.session){keepDisabled=true;finishWithSession(result.session);return;}
        if(result.job){
          keepDisabled=true;
          setStatus('AI 组卷已提交：'+(JOB_LABEL[result.job.status]||result.job.status||'排队中')+'。页面会自动刷新真实状态。','pending');
          refreshLandingOnce(container,stamp);
          scheduleJobPoll(result.job.id);
          return;
        }
        throw new Error('EXAM_RESPONSE_INVALID');
      }catch(error){
        setStatus('生成失败：'+errorText(error)+'。','error');
      }finally{
        submitting=keepDisabled;
        if(!keepDisabled)restoreSubmit();
      }
    };
  }

  /* ---------- full-screen sitting ---------- */
  async function mountSitting(container,id,stamp){
    container.onclick=null;container.onchange=null;
    container.innerHTML=loadingMarkup('正在读取试卷与作答记录…');
    let data;
    try{data=await getJSON('exams/'+encodeURIComponent(id));}
    catch(error){
      if(stamp!==generation||!container.isConnected)return;
      container.innerHTML=errorMarkup(errorText(error),{detail:true});
      container.onclick=event=>{if(event.target.closest('[data-ew-retry]')&&container.isConnected)mount(container,id);};
      return;
    }
    if(stamp!==generation||!container.isConnected)return;
    if(!data.session){
      container.innerHTML=errorMarkup('服务端没有返回该试卷的记录。',{detail:true});
      container.onclick=event=>{if(event.target.closest('[data-ew-retry]')&&container.isConnected)mount(container,id);};
      return;
    }
    startSitting(container,id,stamp,data.session);
  }
  function startSitting(container,id,stamp,initial){
    let paper=initial;
    let viewIndex=0;
    let saveState='idle';
    let saveText='';
    let actionBusy=false;
    let saveChain=Promise.resolve();
    let clockOffsetMs=typeof paper.serverNow==='number'?paper.serverNow*1000-Date.now():0;
    let deadlineArmed=false;
    let deadlineRetries=0;
    const remaining=()=>{
      if(paper.status!=='running'||typeof paper.deadline!=='number')return null;
      return Math.max(0,Math.ceil((paper.deadline*1000-(Date.now()+clockOffsetMs))/1000));
    };
    const answeredCount=()=>(paper.questions||[]).filter(question=>paper.answers&&paper.answers[question.id]!==undefined).length;
    function setActionStatus(text,kind=''){
      container.querySelectorAll('[data-ew-action-status]').forEach(node=>{node.textContent=text;node.dataset.kind=kind;});
    }
    function setSaveState(state,text){
      saveState=state;
      if(text!==undefined)saveText=text;
      const node=container.querySelector('[data-ew-save]');
      if(node){
        node.dataset.state=state;
        const textNode=node.querySelector('[data-ew-save-text]');
        if(textNode)textNode.textContent=state==='saving'?'正在保存…':state==='saved'?'已保存到服务端':state==='error'?(saveText||'保存失败，请核对服务端记录'):'选择答案后自动保存';
        const iconNode=node.querySelector('.material-symbols-outlined');
        if(iconNode)iconNode.textContent=SAVE_ICON[state]||'cloud_upload';
      }
    }
    function statusPill(){
      const status=paper.status||'ready';
      return `<span class="ew-status-pill is-${e(status)}">${e(STATUS_LABEL[status]||status)}</span>`;
    }
    function clockMarkup(){
      return `<div class="ew-clock" data-ew-clock role="timer" aria-label="服务器计时剩余时间"><span class="material-symbols-outlined" aria-hidden="true">timer</span><div><strong data-ew-clock-value>--:--</strong><small>服务器计时</small></div></div>`;
    }
    function headMarkup(){
      return `<header class="ew-sit-head">
        <div class="ew-sit-id">
          <div class="ew-sit-eyebrow">${statusPill()}<span>模拟考试 · 改编/原创模拟题</span></div>
          <h1 class="ew-sit-title">${e(paper.label||'模拟考试')}</h1>
          <p class="ew-sit-meta">${e(paperSubjects(paper))} · ${paper.questions.length} 题 · ${e(paper.minutes)} 分钟</p>
        </div>
        <div class="ew-sit-tools">
          ${paper.status==='running'?clockMarkup():''}
          ${paper.status==='submitted'?'<a class="ew-btn ew-btn-tonal" href="#space/exams"><span class="material-symbols-outlined" aria-hidden="true">list_alt</span>返回试卷列表</a>':'<button type="button" class="ew-btn ew-btn-outline" data-ew-exit><span class="material-symbols-outlined" aria-hidden="true">logout</span>退出考试</button>'}
        </div>
      </header>`;
    }
    function navMarkup(){
      const answered=answeredCount(),total=paper.questions.length;
      return `<aside class="ew-nav" aria-label="题目导航">
        <div class="ew-nav-head"><h2>题目导航</h2><span class="ew-nav-count" data-ew-answered-text>已答 ${answered}/${total}</span></div>
        <div class="ew-bottom-track" aria-hidden="true"><i data-ew-progress style="width:${total?answered/total*100:0}%"></i></div>
        <div class="ew-nav-grid" data-ew-nav-grid>${paper.questions.map((question,index)=>{
          const done=Boolean(paper.answers&&paper.answers[question.id]!==undefined);
          return `<button type="button" class="ew-nav-btn ${done?'is-answered':''} ${index===viewIndex?'is-current':''}" data-ew-nav="${index}" aria-label="第 ${index+1} 题，${done?'已作答':'未作答'}"${index===viewIndex?' aria-current="true"':''}>${index+1}</button>`;
        }).join('')}</div>
        <div class="ew-nav-legend"><span><i class="is-answered" aria-hidden="true"></i>已答</span><span><i aria-hidden="true"></i>未答</span><span><i class="is-current" aria-hidden="true"></i>当前</span></div>
      </aside>`;
    }
    function questionMarkup(question,index){
      const selected=paper.answers?paper.answers[question.id]:undefined;
      const options=Array.isArray(question.options)?question.options:[];
      return `<article class="ew-q-card" aria-labelledby="ew-q-title">
        <div class="ew-q-head">
          <span class="ew-chip">第 ${index+1} 题 / ${paper.questions.length}</span>
          <span class="ew-chip ew-chip--plain">单选题</span>
          ${question.subject?`<span class="ew-chip ew-chip--plain">${e(question.subject)}${question.topic?' · '+e(question.topic):''}</span>`:''}
          ${saveStatusMarkup(saveState,saveText)}
        </div>
        <h2 class="ew-q-title" id="ew-q-title" tabindex="-1" data-ew-q-title>${e(question.title||('第 '+(index+1)+' 题'))}</h2>
        <p class="ew-q-prompt">${e(question.prompt||'')}</p>
        <fieldset class="ew-options">
          <legend class="sr-only">选择答案</legend>
          ${options.map((option,optionIndex)=>`<label class="ew-option ${selected===optionIndex?'is-selected':''}">
            <input type="radio" name="ew-answer" value="${optionIndex}" data-ew-answer data-question-id="${e(question.id)}" ${selected===optionIndex?'checked':''}>
            <span class="ew-option-key">${LETTERS[optionIndex]||String(optionIndex+1)}</span>
            <span class="ew-option-text">${e(option)}</span>
          </label>`).join('')}
        </fieldset>
        <div class="ew-q-actions">
          <button type="button" class="ew-btn ew-btn-outline" data-ew-prev ${index===0?'disabled':''}><span class="material-symbols-outlined" aria-hidden="true">arrow_back</span>上一题</button>
          <button type="button" class="ew-btn ew-btn-tonal" data-ew-next ${index===paper.questions.length-1?'disabled':''}>下一题<span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span></button>
        </div>
      </article>`;
    }
    function bottomMarkup(){
      const answered=answeredCount(),total=paper.questions.length;
      return `<div class="ew-bottom"><div class="ew-bottom-inner">
        <div class="ew-bottom-summary" role="status" aria-live="polite">
          <span>已答 <strong data-ew-answered>${answered}</strong> / ${total}</span>
          <span class="ew-bottom-muted">未答 <strong data-ew-unanswered>${total-answered}</strong></span>
          <div class="ew-bottom-track" aria-hidden="true"><i data-ew-progress style="width:${total?answered/total*100:0}%"></i></div>
          <small>未交卷退出不会删除已保存答案</small>
          <small class="ew-action-status" data-ew-action-status></small>
        </div>
        <button type="button" class="ew-btn ew-btn-primary ew-btn-lg" data-ew-submit>交卷并评分</button>
      </div></div>`;
    }
    function runningMarkup(){
      return `<div class="ew-sitting">${headMarkup()}
        <div class="ew-sit-body">${navMarkup()}<main class="ew-question" data-ew-question-area>${questionMarkup(paper.questions[viewIndex],viewIndex)}</main></div>
        ${bottomMarkup()}
      </div>`;
    }
    function readyMarkup(){
      const assembly=paper.assembly||{};
      const method=String(assembly.method||'program-selection');
      const ai=method.indexOf('ai')===0;
      const assemblyNote=method==='ai-candidates-program-quota'
        ?`AI 推荐了 ${e(assembly.recommendedCount??'—')} 道合法候选，程序按科目轮选 ${e(assembly.selectedCount??paper.questions.length)} 道组成试卷。`
        :ai?'AI 在固定题候选中选题，题目为固定题快照。':'程序从固定题库选编，未调用 AI、不产生模型费用。';
      return `<div class="ew-sitting">${headMarkup()}
        <div class="ew-sit-body ew-sit-body--center">
          <section class="ew-start" aria-labelledby="ew-start-title">
            <span class="ew-start-icon material-symbols-outlined" aria-hidden="true">timer</span>
            <span class="ew-eyebrow">Ready</span>
            <h2 id="ew-start-title">${e(paper.label||'模拟考试')}</h2>
            <p class="ew-start-text">本卷共 ${paper.questions.length} 题，限时 ${e(paper.minutes)} 分钟。点击开始后由服务端记录开始时间与截止时间；中途退出不会删除已保存答案。</p>
            <dl class="ew-facts">
              <div><dt>题量</dt><dd>${paper.questions.length} 题</dd></div>
              <div><dt>时长</dt><dd>${e(paper.minutes)} 分钟</dd></div>
              <div><dt>科目</dt><dd>${e(paperSubjects(paper))}</dd></div>
              <div><dt>组卷</dt><dd>${ai?'AI 选题（固定题快照）':'程序选编'}</dd></div>
            </dl>
            <p class="ew-start-note">${e(assemblyNote)} 站内题目为改编/原创模拟题，不是历年真题。</p>
            <div class="ew-start-actions">
              <button type="button" class="ew-btn ew-btn-primary ew-btn-lg" data-ew-start><span class="material-symbols-outlined" aria-hidden="true">play_arrow</span>开始计时考试</button>
              <a class="ew-btn ew-btn-outline" href="#space/exams">返回试卷列表</a>
            </div>
            <p class="ew-action-status" data-ew-action-status role="status" aria-live="polite"></p>
            <ul class="ew-rules">
              <li>倒计时以服务端截止时间为准，关闭或刷新页面不会暂停。</li>
              <li>选择答案后自动保存；网络异常会明确提示，不会假装保存成功。</li>
              <li>时间到后服务端自动收卷，客观题得分由服务端判定。</li>
            </ul>
          </section>
        </div>
      </div>`;
    }
    function resultItem(question,index){
      const detail=(paper.result&&Array.isArray(paper.result.questions)?paper.result.questions:[]).find(item=>item.questionId===question.id)||{};
      const correctIndex=typeof question.answer==='number'?question.answer:null;
      const mine=paper.answers?paper.answers[question.id]:undefined;
      const unanswered=mine===undefined;
      const correct=detail.correct===true;
      const options=Array.isArray(question.options)?question.options:[];
      return `<article class="ew-result-item ${unanswered?'is-unanswered':correct?'is-correct':'is-wrong'}">
        <header class="ew-result-item-head">
          <span class="ew-result-num">${index+1}</span>
          <div class="ew-result-question"><h3>${e(question.title||('第 '+(index+1)+' 题'))}</h3><p class="ew-q-prompt">${e(question.prompt||'')}</p></div>
          <span class="ew-result-badge">${unanswered?'未作答':correct?'正确':'错误'}</span>
        </header>
        <ul class="ew-result-options">
          ${options.map((option,optionIndex)=>`<li class="${optionIndex===correctIndex?'is-correct':''} ${mine===optionIndex&&optionIndex!==correctIndex?'is-wrong':''}"><span class="ew-option-key">${LETTERS[optionIndex]||String(optionIndex+1)}</span><span>${e(option)}</span>${optionIndex===correctIndex?'<em>正确答案</em>':''}${mine===optionIndex?'<em>你的选择</em>':''}</li>`).join('')}
        </ul>
        <p class="ew-answer-line">我的答案：${unanswered?'未作答':e(LETTERS[mine]||String(mine))} · 正确答案：${correctIndex===null?'—':e(LETTERS[correctIndex]||String(correctIndex))}</p>
        <div class="ew-explanation"><span class="material-symbols-outlined" aria-hidden="true">lightbulb</span><div><strong>解析</strong><p>${e(question.explanation||'该题暂未提供解析。')}</p></div></div>
      </article>`;
    }
    function resultMarkup(){
      const result=paper.result||{score:0,maxScore:paper.questions.length,unanswered:paper.questions.length,questions:[]};
      const answered=paper.questions.length-(result.unanswered||0);
      return `<div class="ew-sitting">${headMarkup()}
        <div class="ew-sit-body ew-sit-body--result">
          <section class="ew-result-hero" aria-labelledby="ew-result-title">
            <div class="ew-score"><span class="ew-score-value">${e(result.score)}</span><span class="ew-score-max">/ ${e(result.maxScore)}</span></div>
            <div class="ew-result-copy">
              <span class="ew-eyebrow">Result</span>
              <h2 id="ew-result-title">交卷完成 · 客观题已由服务端判定</h2>
              <p>得分 ${e(result.score)} / ${e(result.maxScore)} · 已答 ${answered} 题 · 未答 ${e(result.unanswered||0)} 题。</p>
              <div class="ew-result-actions"><a class="ew-btn ew-btn-primary" href="#space/exams"><span class="material-symbols-outlined" aria-hidden="true">assignment_turned_in</span>返回试卷列表</a></div>
            </div>
          </section>
          <section class="ew-result-list" aria-label="逐题正确答案与解析">
            <h2>逐题正确答案与解析</h2>
            ${paper.questions.map((question,index)=>resultItem(question,index)).join('')}
          </section>
        </div>
        <div class="ew-bottom"><div class="ew-bottom-inner">
          <div class="ew-bottom-summary"><span>已交卷 · 得分 <strong>${e(result.score)}</strong> / ${e(result.maxScore)}</span><small>作答记录已保存到服务端</small></div>
          <a class="ew-btn ew-btn-primary ew-btn-lg" href="#space/exams"><span class="material-symbols-outlined" aria-hidden="true">arrow_back</span>返回试卷列表</a>
        </div></div>
      </div>`;
    }
    function drawSitting(){
      clearTimer('clock');
      if(paper.status==='ready')container.innerHTML=readyMarkup();
      else if(paper.status==='submitted')container.innerHTML=resultMarkup();
      else{container.innerHTML=runningMarkup();startClock();}
    }
    function refreshAnswerIndicators(){
      const answered=answeredCount(),total=paper.questions.length;
      container.querySelectorAll('[data-ew-nav]').forEach(button=>{
        const index=Number(button.dataset.ewNav);
        const question=paper.questions[index];
        const done=Boolean(question&&paper.answers&&paper.answers[question.id]!==undefined);
        button.classList.toggle('is-answered',done);
        button.setAttribute('aria-label',`第 ${index+1} 题，${done?'已作答':'未作答'}`);
      });
      container.querySelectorAll('[data-ew-answered]').forEach(node=>{node.textContent=String(answered);});
      container.querySelectorAll('[data-ew-unanswered]').forEach(node=>{node.textContent=String(total-answered);});
      container.querySelectorAll('[data-ew-progress]').forEach(node=>{node.style.width=(total?answered/total*100:0)+'%';});
      const navCount=container.querySelector('[data-ew-answered-text]');
      if(navCount)navCount.textContent=`已答 ${answered}/${total}`;
    }
    function paintAnswer(){
      const current=paper.questions[viewIndex];
      const selected=current&&paper.answers?paper.answers[current.id]:undefined;
      container.querySelectorAll('.ew-option').forEach(label=>{
        const input=label.querySelector('input[data-ew-answer]');
        if(!input)return;
        const isSelected=selected!==undefined&&Number(input.value)===selected;
        label.classList.toggle('is-selected',isSelected);
        input.checked=isSelected;
      });
      refreshAnswerIndicators();
    }
    function showQuestion(index,{focus=false}={}){
      if(paper.status!=='running')return;
      viewIndex=Math.max(0,Math.min(paper.questions.length-1,index));
      const area=container.querySelector('[data-ew-question-area]');
      if(!area){drawSitting();return;}
      area.innerHTML=questionMarkup(paper.questions[viewIndex],viewIndex);
      container.querySelectorAll('[data-ew-nav]').forEach(button=>{
        const current=Number(button.dataset.ewNav)===viewIndex;
        button.classList.toggle('is-current',current);
        if(current)button.setAttribute('aria-current','true');else button.removeAttribute('aria-current');
      });
      if(focus){
        const title=area.querySelector('[data-ew-q-title]');
        if(title)try{title.focus();}catch{}
      }
    }
    function updateClock(){
      const value=container.querySelector('[data-ew-clock-value]');
      if(!value)return;
      const left=remaining();
      if(left===null){value.textContent='--:--';return;}
      value.textContent=formatClock(left);
      const clock=container.querySelector('[data-ew-clock]');
      if(clock){
        clock.classList.toggle('is-warning',left<=300);
        clock.classList.toggle('is-critical',left<=60);
      }
      if(left===0&&!deadlineArmed){deadlineArmed=true;triggerDeadline();}
    }
    function startClock(){
      clearTimer('clock');
      updateClock();
      if(paper.status!=='running')return;
      timers.clock=setInterval(updateClock,500);
    }
    async function reloadPaper(notice){
      try{
        const data=await getJSON('exams/'+encodeURIComponent(id));
        if(stamp!==generation||!container.isConnected)return false;
        if(!data.session)throw new Error('EXAM_NOT_FOUND');
        paper=data.session;
        clockOffsetMs=typeof paper.serverNow==='number'?paper.serverNow*1000-Date.now():clockOffsetMs;
        if(notice){saveState='error';saveText=notice;}
        const left=remaining();
        if(left!==null&&left>0){deadlineArmed=false;deadlineRetries=0;}
        viewIndex=Math.min(viewIndex,Math.max(0,paper.questions.length-1));
        drawSitting();
        return true;
      }catch(error){
        if(stamp===generation&&container.isConnected)setActionStatus('重新读取服务端状态失败：'+errorText(error)+'。请刷新页面核对服务端记录。','error');
        return false;
      }
    }
    function triggerDeadline(){
      if(timers.retry)return;
      setActionStatus('倒计时结束，正在向服务端确认交卷状态…','pending');
      const attempt=async()=>{
        timers.retry=null;
        if(stamp!==generation||!container.isConnected)return;
        const ok=await reloadPaper('考试时间已到；页面已按服务端结果刷新。');
        if(!ok){
          if(remaining()===0&&deadlineRetries<20){deadlineRetries++;timers.retry=setTimeout(attempt,3000);}
          return;
        }
        if(paper.status==='submitted')return;
        if(remaining()===0&&deadlineRetries<20){
          deadlineRetries++;
          timers.retry=setTimeout(attempt,2000);
        }else if(remaining()===0){
          setActionStatus('服务器已到截止时间，但尚未返回交卷结果。请刷新页面确认，不要继续作答。','error');
        }else{
          deadlineArmed=false;deadlineRetries=0;
        }
      };
      attempt();
    }
    function setActionError(text){setActionStatus(text,'error');}
    async function queueAnswer(qid,index){
      if(paper.status!=='running')return;
      if(remaining()===0){setSaveState('error','考试时间已到，答案未提交；正在刷新服务端状态。');triggerDeadline();return;}
      if(!paper.answers)paper.answers={};
      const previous=paper.answers[qid];
      paper.answers[qid]=index;
      setSaveState('saving');
      paintAnswer();
      saveChain=saveChain.then(async()=>{
        try{
          setSaveState('saving');
          const data=await postJSON('exams/'+encodeURIComponent(id)+'/answers',{expectedRevision:paper.revision,answers:{[qid]:index}});
          if(stamp!==generation)return;
          paper=data.session;
          clockOffsetMs=typeof paper.serverNow==='number'?paper.serverNow*1000-Date.now():clockOffsetMs;
          setSaveState('saved',`已保存到服务端 · ${timestamp()}`);
          paintAnswer();
          if(paper.status==='submitted')drawSitting();
        }catch(error){
          if(stamp!==generation)return;
          setSaveState('error',`保存失败：${errorText(error)}；请刷新核对服务端记录。`);
          let resynced=false;
          try{
            const data=await getJSON('exams/'+encodeURIComponent(id));
            if(stamp!==generation||!container.isConnected)return;
            paper=data.session;
            clockOffsetMs=typeof paper.serverNow==='number'?paper.serverNow*1000-Date.now():clockOffsetMs;
            resynced=true;
            if(paper.status==='submitted'){drawSitting();return;}
            paintAnswer();
          }catch{}
          if(!resynced&&stamp===generation){
            try{
              if(!paper.answers)paper.answers={};
              if(previous===undefined)delete paper.answers[qid];
              else paper.answers[qid]=previous;
              paintAnswer();
            }catch{}
          }
        }
      }).catch(()=>{});
    }
    async function startExam(){
      if(actionBusy||paper.status!=='ready')return;
      actionBusy=true;
      const button=container.querySelector('[data-ew-start]');
      if(button){button.disabled=true;button.innerHTML='<span class="ew-spinner" aria-hidden="true"></span>正在开始…';}
      setActionStatus('正在向服务端请求开始计时…','pending');
      try{
        const data=await postJSON('exams/'+encodeURIComponent(id)+'/start',{expectedRevision:paper.revision});
        if(stamp!==generation||!container.isConnected)return;
        paper=data.session;
        clockOffsetMs=typeof paper.serverNow==='number'?paper.serverNow*1000-Date.now():clockOffsetMs;
        viewIndex=0;
        saveState='idle';saveText='';
        deadlineArmed=false;deadlineRetries=0;
        drawSitting();
      }catch(error){
        if(!container.isConnected)return;
        setActionError('开始失败：'+errorText(error)+'。试卷仍为未开始状态，请重试或刷新核对。');
        if(button){button.disabled=false;button.innerHTML='<span class="material-symbols-outlined" aria-hidden="true">play_arrow</span>开始计时考试';}
      }finally{actionBusy=false;}
    }
    async function submitExam(){
      if(actionBusy||paper.status!=='running')return;
      const unanswered=paper.questions.length-answeredCount();
      const confirmed=await confirmAction({
        title:'确认交卷？',
        message:`交卷后将无法继续作答；当前还有 ${unanswered} 题未答，未答题按未作答计入结果。交卷后由服务端自动判定客观题得分。`,
        confirmLabel:'确认交卷',
        cancelLabel:'继续检查'
      });
      if(!confirmed)return;
      actionBusy=true;
      const button=container.querySelector('[data-ew-submit]');
      if(button){button.disabled=true;button.innerHTML='<span class="ew-spinner" aria-hidden="true"></span>正在交卷…';}
      setActionStatus('正在提交交卷请求…','pending');
      await saveChain.catch(()=>{});
      try{
        const data=await postJSON('exams/'+encodeURIComponent(id)+'/submit',{expectedRevision:paper.revision});
        if(stamp!==generation||!container.isConnected)return;
        paper=data.session;
        clockOffsetMs=typeof paper.serverNow==='number'?paper.serverNow*1000-Date.now():clockOffsetMs;
        saveState='idle';saveText='';
        drawSitting();
      }catch(error){
        if(!container.isConnected)return;
        const code=String((error&&(error.code||error.message))||'');
        if(code==='EXAM_REVISION_CONFLICT'){
          await reloadPaper('试卷已在其他窗口更新，页面已重新读取服务端记录，请核对后再交卷。');
        }else{
          setActionError('交卷失败：'+errorText(error)+'。试卷尚未交卷，请核对网络或刷新页面确认服务端状态。');
        }
        if(button&&button.isConnected){button.disabled=false;button.textContent='交卷并评分';}
      }finally{actionBusy=false;}
    }
    async function exitExam(){
      if(actionBusy)return;
      if(paper.status==='submitted'){location.hash='space/exams';return;}
      const confirmed=await confirmAction({
        title:'退出本次考试？',
        message:saveState==='error'
          ?'当前有答案未能确认保存。退出只会离开视图，已保存的记录仍保留在服务端；请刷新或稍后重新进入核对，必要时重新作答。'
          :'退出只会离开当前视图，已保存的答案仍会保留在服务端。你可以随时从「我的试卷」重新进入继续作答。',
        confirmLabel:'退出考试',
        cancelLabel:'继续作答'
      });
      if(!confirmed)return;
      actionBusy=true;
      await saveChain.catch(()=>{});
      location.hash='space/exams';
    }
    function handleClick(event){
      if(!(event.target instanceof Element))return;
      const target=event.target.closest('button,a');
      if(!target)return;
      if(target.matches('[data-ew-exit]')){event.preventDefault();exitExam();}
      else if(target.matches('[data-ew-start]')){event.preventDefault();startExam();}
      else if(target.matches('[data-ew-submit]')){event.preventDefault();submitExam();}
      else if(target.matches('[data-ew-prev]')){event.preventDefault();showQuestion(viewIndex-1,{focus:true});}
      else if(target.matches('[data-ew-next]')){event.preventDefault();showQuestion(viewIndex+1,{focus:true});}
      else if(target.matches('[data-ew-nav]')){event.preventDefault();showQuestion(Number(target.dataset.ewNav),{focus:true});}
      else if(target.matches('[data-ew-retry]')){event.preventDefault();mount(container,id);}
    }
    function handleChange(event){
      const input=event.target instanceof Element?event.target.closest('[data-ew-answer]'):null;
      if(!input)return;
      queueAnswer(input.dataset.questionId,Number(input.value));
    }
    container.onclick=handleClick;
    container.onchange=handleChange;
    if(visibilityHandler)document.removeEventListener('visibilitychange',visibilityHandler);
    visibilityHandler=()=>{if(document.visibilityState==='visible'&&paper.status==='running'&&stamp===generation)reloadPaper('');};
    document.addEventListener('visibilitychange',visibilityHandler);
    drawSitting();
  }

  function mount(container,id){
    const stamp=++generation;
    clearTimers();
    document.body.classList.remove('ew-sitting-active');
    if(activeDialog)destroyDialog(activeDialog);
    if(visibilityHandler){document.removeEventListener('visibilitychange',visibilityHandler);visibilityHandler=null;}
    if(!container)return;
    let routeId='';
    if(id){try{routeId=decodeURIComponent(String(id));}catch{routeId=String(id);}}
    if(routeId){
      document.body.classList.add('ew-sitting-active');
      mountSitting(container,routeId,stamp);
    }else{
      mountLanding(container,stamp);
    }
  }
  window.addEventListener('hashchange',()=>{
    clearTimers();
    document.body.classList.remove('ew-sitting-active');
    if(visibilityHandler){document.removeEventListener('visibilitychange',visibilityHandler);visibilityHandler=null;}
    if(activeDialog)destroyDialog(activeDialog);
  });
  window.XueyaExamWorkspace={mount};
})();
