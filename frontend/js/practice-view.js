/* 练习 / 复习 views: fixed bank list, status flow, objective answering, per-question notes. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaPracticeView=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const CATEGORIES=[['hot100','力扣算法 Hot100'],['exam408','408 考研题库']];
const SUBJECTS=['数据结构与算法','计算机网络','操作系统','数据库','面向对象基础'];
const STATUS_LABEL={pending:'待刷',mastered:'已掌握',wrong:'错题本'};
const TYPE_LABEL={single:'单选',multiple:'多选',fill:'填空',boolean:'判断',code:'代码',short:'综合应用'};
const DIFFICULTY={hot100:['简单','中等','困难'],exam408:['简单','中等','困难'],legacy:['基础','进阶','挑战','简单','中等','困难'],basic:['基础','进阶','挑战'],interview:['基础','进阶','挑战']};
const e=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const esc=s=>e(s);
function createPracticeView({store,client,toast=()=>{},navigate=()=>{}}={}){
  let root=null,view='practice',revealed=false,attempt=null,choice=null,shortDraft='',fillDraft='',noteTimer=null,noteTarget=null;
  let loading=true,loadError='',saving=new Set(),noteErrors=new Set(),syncing=false,initialized=false,pendingRender=false;
  let entry='hub',writtenTimer=null,writtenTarget=null,requestedQuestionId=null;
  let whiteboardOpen=false,whiteboardTab='complexity',consoleTab='testcase',activeCaseIndex=0;
  let runState={questionId:'',loading:false,result:null,error:''},runToken=0;
  let analysisState={key:'',loading:false,result:null,error:''},analysisToken=0;
  let toolchain=null,toolchainRequest=null;
  const analysisCache=new Map();
  const LANGUAGE_OPTION={python:'Python 3',cpp:'C++ 17 (g++)',java:'Java 21'};
  const AI_ERROR_TEXT={AI_UNAVAILABLE:'模型未配置或当前不可用，请先在服务端配置外部模型。',AI_TIMEOUT:'模型响应超时，本次分析未完成（不会自动重试付费调用）。',AI_INVALID_RESPONSE:'模型返回内容无法解析为复杂度分析，请稍后重试。',AI_CONNECTION_FAILED:'无法连接模型服务，请检查网络与配置。',AI_RUN_TIMEOUT:'本次调用超出运行预算，未完成分析。',AI_MODEL_BUDGET_EXCEEDED:'本次调用超出模型次数预算，未完成分析。',AI_OUTPUT_BUDGET_EXCEEDED:'本次调用超出输出预算，未完成分析。',AI_COST_BUDGET_EXCEEDED:'本次调用超出费用预算，未完成分析。',INVALID_CODE:'请先编写代码。',CODE_TOO_LARGE:'代码过长（上限 20000 字符）。',QUESTION_NOT_FOUND:'题目不存在或不是 Hot100 题目。',INVALID_LANGUAGE:'不支持的语言。',INVALID_CASE_INDEX:'测试用例序号无效。'};
  function friendlyError(code){return AI_ERROR_TEXT[code]||code||'未知错误';}
  function toolchainFor(language){return toolchain?.capabilities?.[language]||null;}
  function languageAvailable(language){const capability=toolchainFor(language);return capability?Boolean(capability.available):language==='python';}
  function languageUnavailableText(language){const capability=toolchainFor(language);return capability?.reason||'未检测到该语言的本机运行时。';}
  function toolchainSummary(){
    const order=['python','cpp','java'];
    if(!toolchain)return '';
    return `<span class="code-run-toolchain">${order.map(language=>{const capability=toolchain.capabilities?.[language];if(!capability)return '';const ready=Boolean(capability.available);return `<span class="code-run-toolchain-item ${ready?'is-ready':'is-missing'}" title="${e(capability.reason||capability.path||'')}">${e(LANGUAGE_OPTION[language]||language)} ${ready?'✓':'—'}</span>`;}).join('')}</span>`;
  }
  async function ensureToolchain(force=false){
    if(!window.XueyaPlatform?.available){toolchain={capabilities:{python:{available:true,label:'Python'}},languages:['python']};return toolchain;}
    if(toolchain&&!force)return toolchain;
    if(!toolchainRequest||force){
      toolchainRequest=window.XueyaPlatform.spaceFetch('/api/learning/space/workbench/code/capabilities'+(force?'?refresh=1':''))
        .then(response=>response.json())
        .then(value=>{if(value&&value.ok)toolchain=value;return toolchain;})
        .catch(()=>toolchain)
        .finally(()=>{toolchainRequest=null;});
    }
    return toolchainRequest;
  }
  function analysisKeyFor(q,code){let h=2166136261;for(let i=0;i<code.length;i++){h^=code.charCodeAt(i);h=Math.imul(h,16777619);}return (q?.id||'')+'|'+(ui.language||'python')+'|'+((h>>>0).toString(36))+'-'+code.length;}
  const runFor=q=>q&&runState.questionId===q.id?runState:null;
  function analysisFor(q,code){
    const key=analysisKeyFor(q,code);
    if(analysisState.key===key)return analysisState;
    return {key,loading:false,result:analysisCache.get(key)||null,error:''};
  }
  const HOT_TOPICS=['全部专题','哈希表','双指针','二叉树','动态规划','链表','滑动窗口','贪心','回溯','栈','数组','图论'];
  function generateLineNumbers(codeText){
    const lineCount=Math.max(14,(codeText||'').split('\n').length);
    return Array.from({length:lineCount},(_,i)=>`<span>${i+1}</span>`).join('');
  }
  function applyRequestedQuestion(){if(requestedQuestionId&&bank().some(q=>q.id===requestedQuestionId)){position().selected=requestedQuestionId;position().completed=false;ui.selectedQuestionId=requestedQuestionId;requestedQuestionId=null;}}
  const ui=store.state.ui;
  const button=(label,action,attrs='',style='button-outline')=>`<button type="button" class="button button-small ${style}" data-action="${action}" ${attrs}>${label}</button>`;
  const bank=()=>client.bank()||[];
  const reviewArea=()=>['materials','algorithms','exams'].includes(ui.reviewArea)?ui.reviewArea:'materials';
  const areaOf=q=>q.bankSource==='algorithm'?'algorithms':q.bankSource==='exam408'?'exams':q.bankSource?'materials':q.category==='hot100'?'algorithms':q.category==='exam408'?'exams':'materials';
  const pool=()=>view==='review'?bank().filter(q=>areaOf(q)===reviewArea()):bank().filter(q=>ui.category==='hot100'?(q.bankSource==='algorithm'||!q.bankSource&&q.category==='hot100'):ui.category==='exam408'?q.bankSource==='exam408':ui.category==='legacy'?q.bankSource==='legacy':q.category===ui.category);
  const subjects=()=>[...new Set(pool().map(q=>q.subject))];
  const answerText=(q,value)=>q.type==='boolean'?(value?'正确':'错误'):q.type==='multiple'?(value||[]).map(i=>q.options[i]).join('；'):q.type==='single'?q.options[value]:value;
  function generationStatus(){
    const rows=client.catalog?.().generations||[];
    const labels={waiting_parse:'等待资料解析',generating:'正在生成',model_unavailable:'请先在服务设置中配置模型',insufficient_material:'资料内容不足，无法可靠生成200道不同题',unknown:'上次调用结果不确定，请核对用量后再继续',failed:'生成未完成',cancelled:'已停止',stale:'资料已变更，请重新上传生成',succeeded:'已生成 Hot 100 和基础 100'};
    return rows.length?`<div class="practice-generation" aria-live="polite">${rows.map(row=>`<div><strong>${e(row.name)}</strong><span>${e(labels[row.status]||row.status)} · ${Number(row.completed)||0}/200</span>${row.error?`<small>${e(row.error)}</small>`:''}${['failed','unknown','cancelled','model_unavailable'].includes(row.status)?button('继续生成','resume-generation',`data-id="${e(row.id)}"`):''}${row.status==='generating'?button('停止生成','cancel-generation',`data-id="${e(row.id)}"`):''}${row.status==='generating'?`<progress value="${Number(row.completed)||0}" max="200" aria-label="出题进度"></progress>`:''}</div>`).join('')}</div>`:'';
  }
  const filters=()=>view==='review'?((ui.reviewAreaFilters||={})[reviewArea()]||={}):store.filters();
  const progress=id=>store.state.statuses[id]||{};
  const statusOf=id=>progress(id).status||'pending';
  const positionKey=()=>view==='review'?'review:'+reviewArea():ui.category;
  const position=()=>ui.positions[positionKey()]||(ui.positions[positionKey()]={selected:null,scroll:0,completed:false});
  function matches(q,f){
    if(f.subject&&q.subject!==f.subject||f.difficulty&&q.difficulty!==f.difficulty||f.type&&q.type!==f.type||f.tag&&!(q.tags||[]).includes(f.tag))return false;
    const text=String(f.keyword||'').trim().toLowerCase();
    return !text||[q.id,q.leetcodeNumber||'',q.title,q.prompt,...(q.tags||[])].join(' ').toLowerCase().includes(text);
  }
  function listed(){
    const f=filters();let list=pool().filter(q=>matches(q,f)&&(view==='review'?statusOf(q.id)==='wrong':statusOf(q.id)===(f.status||'pending')));
    if(view==='review')list.sort((a,b)=>{
      const pa=progress(a.id),pb=progress(b.id),stamp=p=>[p.lastWrongAt||'',p.wrongEnteredAt||''].sort().pop();
      return (ui.wrongSort==='count'?(pb.wrongCount||0)-(pa.wrongCount||0):0)||stamp(pb).localeCompare(stamp(pa))||a.id.localeCompare(b.id);
    });
    return list;
  }
  function current(){return position().completed?null:bank().find(q=>q.id===position().selected)||null;}
  function clearTransient(){revealed=false;attempt=null;choice=null;shortDraft='';fillDraft='';consoleTab='testcase';activeCaseIndex=0;}
  function ensureSelected(){if(!bank().length)return;const f=filters(),items=pool();if(view!=='review'&&ui.category==='hot100'){f.subject='';f.type='';}for(const key of ['subject','type','difficulty','tag']){if(f[key]&&!items.some(q=>key==='tag'?(q.tags||[]).includes(f[key]):q[key]===f[key]))f[key]='';}const p=position();if(!p.completed&&!(view==='review'?listed():items).some(q=>q.id===p.selected)){p.selected=listed()[0]?.id||null;}ui.selectedQuestionId=p.selected;}
  function listScroller(){
    return root?.querySelector('.hot100-workbench .practice-list')||root?.querySelector('.practice-list-pane');
  }
  function savePosition(){const pane=listScroller();if(pane&&!loading)position().scroll=pane.scrollTop;store.persist();}
  function resetSelection(){flushNote();clearTransient();position().selected=listed()[0]?.id||null;position().completed=false;position().scroll=0;ui.selectedQuestionId=position().selected;store.persist();}
  function select(id,{manual=true}={}){
    flushNote();savePosition();clearTransient();position().selected=id;position().completed=false;ui.selectedQuestionId=id;
    if(manual)ui.mode='order';
    ui.detailFullscreen=matchMedia('(max-width:720px)').matches;
    store.persist();render();
  }
  function randomPickLocal(pool){return globalThis.XueyaPracticeStore.randomPick(pool,store.state.statuses,{lastId:position().selected,roll:Math.random()});}
  function advance(previous){
    const list=listed(),oldId=position().selected;let next;
    if(ui.mode==='random'&&view!=='review')next=randomPickLocal(list);
    else {const index=previous.findIndex(q=>q.id===oldId);next=previous.slice(index+1).find(q=>list.some(x=>x.id===q.id));if(!next&&list.length&&!list.some(q=>q.id===oldId))next=list[0];}
    flushNote();clearTransient();position().selected=next?.id||null;position().completed=!next;ui.selectedQuestionId=next?.id||null;store.persist();render();
  }
  function allTags(){const f=filters();return [...new Set(pool().filter(q=>(!f.subject||q.subject===f.subject)&&(!f.type||q.type===f.type)).flatMap(q=>q.tags||[]))].sort();}
  function selectFilter(name,label,options){const f=filters();return `<select class="form-field" data-filter="${name}" aria-label="${label}"><option value="">全部${label}</option>${options.map(v=>{const [value,text]=Array.isArray(v)?v:[v,v];return `<option value="${e(value)}" ${f[name]===value?'selected':''}>${e(text)}</option>`;}).join('')}</select>`;}
  function reviewHeaderBanner(){
    const labels={materials:'资料错题',algorithms:'算法错题',exams:'考研错题'};
    return `<h1 class="visually-hidden">错题本</h1><nav class="wrong-area-tabs" aria-label="错题分类">${Object.entries(labels).map(([key,label])=>`<a href="#space/review/${key}" aria-current="${reviewArea()===key?'page':'false'}">${label}</a>`).join('')}</nav>`;
  }

  function hot100Toolbar(){
    const f=filters();
    const pending=store.pendingOps;
    const syncText=pending?'待同步'+(pending?` · ${pending}`:''):(client.online?'已同步':'本机服务未连接');
    const allQuestions=pool();
    const pendingCount=allQuestions.filter(q=>statusOf(q.id)==='pending').length;
    const masteredCount=allQuestions.filter(q=>statusOf(q.id)==='mastered').length;
    const wrongCount=allQuestions.filter(q=>statusOf(q.id)==='wrong').length;

    return `
      <div class="hot100-header flex flex-col lg:flex-row lg:items-center justify-between gap-3 pt-1">
        <div class="flex flex-wrap items-center gap-2.5">
          <a class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface font-label-md text-xs transition-colors" href="#space/algorithms">
            <span class="material-symbols-outlined text-[15px]">arrow_back</span>
            <span>返回算法学习</span>
          </a>
          <span class="text-outline-variant select-none">/</span>
          <h1 class="font-headline-md text-xl lg:text-2xl text-on-surface font-bold tracking-tight">力扣算法 Hot100 精选题库</h1>
        </div>

        <div class="hot100-status-pills">
          <button class="hot100-status-btn ${f.status==='pending'?'is-active':''}" type="button" data-action="status" data-status="pending">
            <span>待刷</span>
            <span class="hot100-status-badge">${pendingCount}</span>
          </button>
          <button class="hot100-status-btn ${f.status==='mastered'?'is-active':''}" type="button" data-action="status" data-status="mastered">
            <span>已掌握</span>
            <span class="hot100-status-badge">${masteredCount}</span>
          </button>
          <a class="hot100-status-btn" href="#space/review/${ui.category==='hot100'?'algorithms':ui.category==='exam408'?'exams':'materials'}">
            <span>错题本</span>
            <span class="hot100-status-badge is-wrong">${wrongCount}</span>
            <span class="material-symbols-outlined text-[13px]">arrow_forward</span>
          </a>
        </div>
      </div>

      <section class="hot100-dock">
        <div class="flex flex-col md:flex-row items-stretch md:items-center gap-2.5 flex-1">
          <div class="hot100-search-wrap">
            <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-[18px]">search</span>
            <input type="search" class="form-field" data-filter="keyword" aria-label="搜索题目" placeholder="搜索题号、题名或关键词" value="${e(f.keyword||'')}">
          </div>
          <div class="flex flex-wrap items-center gap-2">
            ${selectFilter('difficulty','难度',DIFFICULTY.hot100)}
            ${selectFilter('tag','知识点',allTags())}
          </div>
        </div>
        <div class="hot100-actions flex flex-wrap items-center gap-2">
          <button class="h-9 px-3 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface font-label-md text-xs flex items-center gap-1.5 transition-colors border-0 cursor-pointer" type="button" data-action="random">
            <span class="material-symbols-outlined text-[16px] text-primary">casino</span>
            <span>${f.status==='mastered'?'随机回顾':'随机刷题'}</span>
          </button>
          <button ${client.online&&!pending&&!loadError?'hidden':''} class="h-9 px-3 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface font-label-md text-xs flex items-center gap-1.5 transition-colors border-0 cursor-pointer" type="button" data-action="retry-sync">
            <span class="material-symbols-outlined text-[16px]">sync</span>
            <span>重试同步</span>
          </button>
          <button class="h-9 px-3 rounded-lg text-outline hover:text-error font-label-md text-xs transition-colors border-0 bg-transparent cursor-pointer" type="button" data-action="clear-filters">
            <span>清除筛选</span>
          </button>
          <span class="practice-sync text-xs text-outline" role="status">${client.online&&!pending?'':e(syncText)}</span>
          <span class="text-xs text-on-surface-variant font-code-sm font-semibold">${listed().length} 道题</span>
        </div>
      </section>
    `;
  }

  function toolbar(){
    const f=filters();const pending=store.pendingOps;const syncText=pending?'待同步'+(pending?` · ${pending}`:''):(client.online?'已同步':'本机服务未连接');
    if(view!=='review'&&ui.category==='hot100')return `${generationStatus()}${hot100Toolbar()}`;
    return `${view==='review'?reviewHeaderBanner():generationStatus()}<div class="practice-toolbar">${view==='review'?`<h2 class="practice-review-title">${({materials:'课程与历史固定题',algorithms:'算法固定题',exams:'考研固定题'})[reviewArea()]}</h2><div class="practice-statuses">${button('最近出错优先','wrong-sort','data-sort="recent"',ui.wrongSort==='recent'?'button-blue':'button-outline')}${button('错误次数最多','wrong-sort','data-sort="count"',ui.wrongSort==='count'?'button-blue':'button-outline')}</div>`:
      `<div class="practice-source-bar">${ui.category === 'legacy' ? '' : `<a class="text-link" href="${ui.category==='hot100'?'#space/algorithms':ui.category==='exam408'?'#space/exams':'#space/materials'}">← 返回${ui.category==='hot100'?'算法学习':ui.category==='exam408'?'考研学习':'课程资料学习'}</a>`}<h1>${ui.category==='hot100'?'力扣算法 Hot100':ui.category==='exam408'?'408 考研题库':'课程固定练习'}</h1><span class="practice-source-label">${ui.category==='hot100'?'100 道算法题 · 17 个专题':ui.category==='exam408'?'240 单选 · 60 综合应用':'旧题与记录保留'}</span></div><div class="practice-statuses">${['pending','mastered'].map(s=>button(STATUS_LABEL[s],'status',`data-status="${s}"`,f.status===s?'button-blue':'button-outline')).join('')}<a class="text-link" href="#space/review/${ui.category==='hot100'?'algorithms':ui.category==='exam408'?'exams':'materials'}">错题本 →</a></div>`}
      ${unitNavigation()}<div class="practice-filters"><input type="search" class="form-field" data-filter="keyword" aria-label="搜索题目" placeholder="搜索题号、标题、题干、知识点" value="${e(f.keyword||'')}">
      ${view!=='review'&&ui.category==='hot100'?'':selectFilter('subject','科目',subjects())}${view==='review'?'':selectFilter('difficulty','难度',DIFFICULTY[ui.category])}
      ${view!=='review'&&ui.category==='hot100'?'':selectFilter('type','题型',Object.entries(TYPE_LABEL).filter(([type])=>pool().some(q=>q.type===type)))}${selectFilter('tag','知识点',allTags())}${button('清除筛选','clear-filters')}</div>
      <div class="practice-modes">${view==='review'?'':button(f.status==='mastered'?'随机回顾':'随机一题','random')}${button('重试同步','retry-sync')}${store.error?button('重新登录','login'):''}<span class="practice-sync" role="status">${e(syncText)}${store.error?' · '+e(store.error):''}</span><span>${listed().length} 道题</span></div></div>`;
  }
  function unitNavigation(){
    const units=ui.category==='hot100'||ui.category==='exam408'?null:client.catalog?.().generations?.find(g=>g.curated&&g.status==='succeeded')?.units;
    if(!units||view==='review')return '';
    const selected=filters().tag||'';
    return `<nav class="practice-units" aria-label="知识单元"><button type="button" data-action="unit" data-unit="" aria-pressed="${!selected}">全部知识点</button>${units.map(unit=>`<button type="button" data-action="unit" data-unit="${e(unit.name)}" aria-pressed="${selected===unit.name}">${e(unit.name)}<small>${Number(unit[ui.category])||10}</small></button>`).join('')}</nav>`;
  }
  function statusChip(id){const status=statusOf(id);return `<span class="chip chip-${status}">${STATUS_LABEL[status]}</span>${progress(id).confidence==='fuzzy'&&status==='pending'?'<span class="chip chip-fuzzy">待巩固</span>':''}`;}
  function empty(){if(view==='review'&&!bank().length)return `<div class="practice-empty" role="status"><p>${loading?'正在读取固定题与错题记录…':'固定题库尚未读取，暂不能确认此分类的错题数量。'}</p>${loading?'':button('重试同步','retry-sync')}</div>`;const complete=position().completed;return `<div class="practice-empty"><p>${view==='review'?'当前错题已清空。':!bank().length?'当前题库暂时没有可练习题目，请返回练习首页选择其他入口。':complete?'当前筛选下的题目已刷完。':'当前筛选下没有题目。'}</p>${!bank().length?'<a class="text-link" href="#space/practice">返回练习首页 →</a>':button('调整筛选','clear-filters')}${view==='review'||!bank().length?'':button('查看已掌握','show-mastered')}</div>`;}
  function hot100ListRows(){
    const list=listed();
    const f=filters();
    const capsules=`
      <div class="stitch-capsules-bar">
        <button class="stitch-capsule-btn ${!f.tag?'is-active':''}" type="button" data-action="hot-topic" data-topic="">全部专题</button>
        ${HOT_TOPICS.slice(1).map(t=>`<button class="stitch-capsule-btn ${f.tag===t?'is-active':''}" type="button" data-action="hot-topic" data-topic="${e(t)}">${e(t)}</button>`).join('')}
      </div>
    `;
    if(!list.length)return `${capsules}${empty()}`;
    return `
      ${capsules}
      <ul class="practice-list flex flex-col gap-2 overflow-y-auto pr-1 flex-1" role="listbox" aria-label="题目列表">
        ${list.map(q=>{
          const isSelected=q.id===position().selected;
          const status=statusOf(q.id);
          const num=q.leetcodeNumber||q.id.replace('h100-','').replace(/^0+/,'');
          return `
            <li tabindex="0" class="practice-row stitch-question-card ${isSelected?'is-active':''}" data-action="select" data-id="${e(q.id)}" role="option" aria-selected="${isSelected}">
              <div class="stitch-row-header">
                <div class="flex items-center gap-1.5">
                  <span class="font-code-sm text-[12px] ${isSelected?'text-primary font-bold':'text-outline'}">#${e(num)}</span>
                </div>
                ${status!=='pending'?'<span class="stitch-chip stitch-chip-'+status+'">'+STATUS_LABEL[status]+'</span>':''}
              </div>
              <div class="practice-row-title font-headline-sm text-sm ${isSelected?'text-primary font-bold':'text-on-surface font-semibold'}">${e(q.title)}${['h100-63','h100-53'].includes(q.id)?'<span class="stitch-chip">交互演示</span>':''}</div>
              <div class="practice-row-meta flex items-center gap-2 text-xs">
                <span class="${q.difficulty==='简单'?'text-[#16a34a] font-semibold':q.difficulty==='中等'?'text-tertiary font-semibold':'text-error font-semibold'}">${e(q.difficulty)}</span>
              </div>
            </li>
          `;
        }).join('')}
      </ul>
    `;
  }

  function listRows(){
    if(view!=='review'&&ui.category==='hot100')return hot100ListRows();
    const list=listed();let topic='';return !list.length?empty():`<ul class="practice-list" role="listbox" aria-label="题目列表">${list.map(q=>{const heading=view!=='review'&&topic!==q.topic?`<li class="practice-topic" role="presentation">${e(q.category==='hot100'?(q.topic||q.subject):q.subject+' · '+(q.topic||q.tags[0]))}</li>`:'';topic=q.topic;return heading+`<li tabindex="0" class="practice-row ${q.id===position().selected?'is-active':''}" data-action="select" data-id="${e(q.id)}" role="option" aria-selected="${q.id===position().selected}"><span class="practice-row-id">${e(q.bankSource==='exam408'?(q.year?q.year+'考点 · #'+q.number:'#'+q.number):q.generated||q.curated?'#'+q.number:q.leetcodeNumber?'#'+q.leetcodeNumber:q.id)}</span><span class="practice-row-title">${e(q.title)}</span><span class="practice-row-meta">${e(q.difficulty)} · ${view==='review'?'错 '+(progress(q.id).wrongCount||0)+' 次':statusChip(q.id)}</span></li>`;}).join('')}</ul>`;
  }
  function noteBlock(q){
    const note=store.state.notes[q.id]||{text:'',revision:0,conflicts:[]},text=store.hasDraft(q.id)?store.draft(q.id):note.text;
    const state=saving.has(q.id)?'保存中':noteErrors.has(q.id)||store.rejectedNote(q.id,text)?'保存失败 · 草稿已保留':store.hasDraft(q.id)||store.pendingOps?'待同步':'已保存';
    return `<section class="practice-note"><header class="practice-note-head"><h3>随手记</h3><span class="practice-note-status" data-note-status role="status">${state}</span>${button(ui.notePreview?'编辑':'预览','note-mode')}</header>${ui.notePreview?`<div class="practice-note-preview rich-content">${globalThis.XueyaRich.render(text||'')}</div>`:`<textarea class="form-field practice-note-input" data-note="${e(q.id)}" rows="6" placeholder="记录你的思路与易错点">${e(text)}</textarea>`}
    ${(note.conflicts||[]).length?`<div class="practice-conflicts"><p>发现冲突副本，选择保留的内容：</p><pre>${e(note.text)}</pre>${button('保留当前','keep-server',`data-id="${e(q.id)}"`)}${note.conflicts.map((c,i)=>`<pre class="practice-conflict-preview">${e(c.text)}</pre>${button('使用副本 '+(i+1),'keep-conflict',`data-id="${e(q.id)}" data-index="${i}"`)}`).join('')}</div>`:''}</section>`;
  }
  function solutionBlock(q){if(q.type!=='code'||!revealed)return '';const languages=Object.keys(q.solutions||{});const language=languages.includes(ui.language)?ui.language:languages[0];return `<section class="practice-solution"><div class="practice-solution-tabs" role="tablist">${languages.map(l=>button(({c:'C',python:'Python',cpp:'C++',java:'Java'}[l]||e(l)),'language',`data-language="${e(l)}"`,l===language?'button-blue':'button-outline')).join('')}</div><pre class="practice-code"><code>${e(q.solutions[language])}</code></pre><p>时间复杂度 ${e(q.complexity?.time||'见题解')} · 空间复杂度 ${e(q.complexity?.space||'见题解')}</p><p><strong>易错点：</strong>${e(q.pitfalls||'请对照原文和示例核对')}</p></section>`;}
  function statusActions(q){const status=statusOf(q.id);if(status==='wrong')return button('已攻克','conquer',`data-id="${e(q.id)}"`,'button-blue')+button('移回待刷','reset',`data-id="${e(q.id)}"`);
    if(status==='mastered')return button('移回待刷','reset')+button('加入错题本','mark-wrong');
    return button('已掌握','master',q.type==='short'&&!revealed?'disabled':'','button-blue')+button('待巩固','fuzzy',q.type==='short'&&!revealed?'disabled':'')+button(q.type==='short'?'忘记':'加入错题本','mark-wrong',q.type==='short'&&!revealed?'disabled':'');}
  function paperBlock(q,answers=false){
    if(!q.paper)return '';
    const url=answers?q.paper.answersUrl:q.paper.url,page=answers?q.paper.answersPage:q.paper.page;
    if(!url?.startsWith('https://www.xit.edu.cn/'))return '';
    const title=answers?'高校整理解析':'高校公开原卷';
    return `<section class="exam-paper"><header><strong>${title} · ${q.year} 年第 ${q.originalNumber} 题</strong><a class="text-link" href="${e(url)}#page=${page}" target="_blank" rel="noopener noreferrer">新窗口打开 ↗</a></header><iframe src="${e(url)}#page=${page}&view=FitH" title="${title}：请按题号定位" loading="lazy" referrerpolicy="no-referrer"></iframe><p class="exam-source-note">原卷阅读需要联网，PDF从首页打开，请按原题号查阅完整条件和图表；未显示PDF时可使用“新窗口打开”。资料由高校公开整理，解析不标作考试院官方答案。</p></section>`;
  }
  function writtenBlock(q){
    if(!q.parts)return '';
    const draft=ui.writtenDrafts?.[q.id]||{},row=progress(q.id),answers=draft.answers||row.writtenAnswers||{},scores=draft.scores||row.selfScores||{};
    const total=Object.values(scores).reduce((sum,v)=>sum+Number(v||0),0),maximum=q.parts.reduce((sum,p)=>sum+p.points,0);
    return `<div class="exam-parts">${q.selfScoreMode==='mastery'?'<p class="exam-written-state">本题按小问自评掌握点：0为需复习，1为要点已掌握，不对应原卷官方分值。</p>':''}${q.parts.map(part=>`<section class="exam-part"><h3>${e(part.label)} · ${part.points} ${q.selfScoreMode==='mastery'?'自评点':'分'}</h3><textarea data-written="${e(part.id)}" aria-label="${e(part.label)}作答过程" placeholder="记录你的答案、计算过程或伪代码" maxlength="12000">${e(answers[part.id]||'')}</textarea>${revealed?`<p><strong>参考解答与评分点：</strong>\n${e(part.reference)}</p><label class="exam-self-score">我的自评分<input type="number" min="0" max="${part.points}" step="0.5" data-self-score="${e(part.id)}" aria-label="${e(part.label)}自评分" value="${e(scores[part.id]??'')}"> / ${part.points}</label>`:''}</section>`).join('')}<p class="exam-written-state" role="status">${store.pendingOps?'作答待同步':'作答自动保存'}${Object.keys(scores).length?' · 自评 '+total+' / '+maximum+'（不计入单选正确率）':''}</p></div>`;
  }
  function onWrittenInput(el){
    const q=current();if(!q?.parts)return;
    ui.writtenDrafts=ui.writtenDrafts||{};
    const row=progress(q.id),draft=ui.writtenDrafts[q.id]||{answers:{...(row.writtenAnswers||{})},scores:{...(row.selfScores||{})}};
    if(el.dataset.written!==undefined)draft.answers[el.dataset.written]=el.value;
    else{if(!el.checkValidity())return;const key=el.dataset.selfScore;if(el.value==='')delete draft.scores[key];else draft.scores[key]=Number(el.value);}
    draft.dirty=true;ui.writtenDrafts[q.id]=draft;store.persist();writtenTarget=q.id;clearTimeout(writtenTimer);writtenTimer=setTimeout(flushWritten,900);
  }
  function flushWritten(){
    clearTimeout(writtenTimer);writtenTimer=null;
    const id=writtenTarget;writtenTarget=null;const draft=ui.writtenDrafts?.[id];if(!id||!draft?.dirty)return;
    store.push('written-save',id,{questionType:'short',answers:{...draft.answers},scores:{...draft.scores}});draft.dirty=false;store.persist();flushOps();
  }
  function runCaseBlock(c){
    const passed=Boolean(c.passed);
    return `<div class="code-run-case ${passed?'is-pass':'is-fail'}">
      <div class="code-run-case-head">
        <span class="font-code-sm text-xs font-bold">Case ${Number(c.index)+1}</span>
        <span class="code-run-case-state ${passed?'is-pass':'is-fail'}">${passed?'通过':'未通过'}</span>
        ${typeof c.durationMs==='number'?`<span class="text-outline font-code-sm text-[11px]">${c.durationMs} ms</span>`:''}
      </div>
      <div class="code-run-line"><span>输入</span><code>${e(c.input)}</code></div>
      <div class="code-run-line"><span>预期</span><code>${e(c.expected)}</code></div>
      <div class="code-run-line"><span>实际</span><code>${e(c.actual==null||c.actual===''?'（无）':c.actual)}</code></div>
      ${c.error?`<pre class="code-run-trace" role="alert">${e(c.error)}</pre>`:''}
    </div>`;
  }
  function runOutputPanel(q){
    const state=runFor(q);
    const language=ui.language||'python';
    const languageName=LANGUAGE_OPTION[language]||language;
    if(state?.loading)return `<div class="code-run-loading" role="status"><span class="material-symbols-outlined code-run-spin">progress_activity</span><span>正在本机编译并运行 ${e(languageName)} 代码（最长约 25 秒）…</span></div>`;
    if(!state||(!state.result&&!state.error))return `<div class="code-run-empty"><p>尚未运行。点击“运行代码”会用题库样例真实调用当前 ${{python:'Python',cpp:'C++',java:'Java'}[language]||language} 解法，并逐条比对输入、预期与实际输出。</p><p class="text-outline">本地单用户执行：临时目录 + 独立子进程 + 超时与输出上限。这不是强安全沙箱，请只运行自己信任的代码。</p></div>`;
    if(state.error)return `<div class="code-run-error-panel" role="alert"><strong>运行未完成</strong><p>${e(friendlyError(state.error))}</p><small>错误码：${e(state.error)}</small></div>`;
    const result=state.result;
    if(result.supported===false)return `<div class="code-run-unsupported"><strong>暂不支持在线运行</strong><p>${e(result.reason||'当前语言暂不支持。')}</p></div>`;
    if(result.error){const heading=result.timedOut?'运行超时':/编译/.test(String(result.error))?'编译未通过':'代码无法执行';return `<div class="code-run-error-panel" role="alert"><strong>${e(heading)}</strong><p>${e(result.error)}</p>${result.stderr?`<pre class="code-run-trace">${e(result.stderr)}</pre>`:''}</div>`;}
    const summary=result.passed
      ?`<div class="code-run-summary is-pass"><span class="material-symbols-outlined">check_circle</span><span>全部通过 · ${Number(result.passedCases)||0}/${Number(result.totalCases)||0} 个用例 · 耗时 ${Number(result.durationMs)||0} ms</span></div>`
      :`<div class="code-run-summary is-fail"><span class="material-symbols-outlined">cancel</span><span>未通过 · ${Number(result.passedCases)||0}/${Number(result.totalCases)||0} 个用例通过 · 耗时 ${Number(result.durationMs)||0} ms</span></div>`;
    return `${summary}
      <div class="code-run-cases">${(result.cases||[]).map(runCaseBlock).join('')}</div>
      ${result.stdout?`<details class="code-run-stream"><summary>stdout（${result.stdout.length} 字符）</summary><pre>${e(result.stdout)}</pre></details>`:''}
      ${result.stderr?`<details class="code-run-stream"><summary>stderr</summary><pre>${e(result.stderr)}</pre></details>`:''}
      <p class="code-run-sandbox-note">${result.compiler?`编译器：${e(result.compiler.name||'')} ${e(result.compiler.version||'')} · `:''}${e(result.sandbox?.note||'')}</p>`;
  }
  function analysisPanel(q,code){
    const state=analysisFor(q,code);
    const languageLabel=({python:'Python',cpp:'C++',java:'Java'}[ui.language]||ui.language||'Python');
    if(state.loading)return `<div class="code-analysis-loading" role="status"><span class="material-symbols-outlined code-run-spin">progress_activity</span><span>AI 正在分析当前 ${e(languageLabel)} 代码的时/空复杂度…</span></div>`;
    if(state.error)return `<div class="code-analysis-error" role="alert"><strong>AI 分析未完成</strong><p>${e(friendlyError(state.error))}</p><small>错误码：${e(state.error)}</small><div class="code-analysis-actions">${button('重新分析','analyze-code','data-force="true"')}</div></div>`;
    if(state.result){
      const result=state.result;
      return `<div class="code-analysis-result">
        <div class="code-analysis-heading"><span class="material-symbols-outlined">psychology</span><strong>AI 复杂度诊断</strong><span class="text-outline font-code-sm text-[11px]">模型：${e(result.model||'未知')} · 耗时 ${Number(result.durationMs)||0} ms</span></div>
        <div class="code-analysis-complexity">
          <span>时间复杂度 <strong class="font-code-sm">${e(result.timeComplexity)}</strong></span>
          <span>空间复杂度 <strong class="font-code-sm">${e(result.spaceComplexity)}</strong></span>
        </div>
        <p class="code-analysis-summary">${e(result.summary)}</p>
        ${(result.keyRisks||[]).length?`<ul class="code-analysis-risks">${result.keyRisks.map(risk=>`<li>${e(risk)}</li>`).join('')}</ul>`:''}
        <div class="code-analysis-actions">${button('重新分析','analyze-code','data-force="true"')}</div>
      </div>`;
    }
    return `<div class="code-analysis-empty">
      <p>这里会调用外部模型，只分析当前代码的复杂度与风险，不执行代码、不产生“已通过”结论。</p>
      <p class="text-outline">同一题目、同一语言、同一份代码会复用已有结果缓存，避免重复付费；修改代码后才会重新请求。</p>
      <div class="code-analysis-actions">${button('调用 AI 分析','analyze-code','','button-blue')}</div>
    </div>`;
  }
  function hot100Detail(q){
    const languages=Object.keys(q.solutions||{});
    const curLang=languages.includes(ui.language)?ui.language:(languages[0]||'python');
    const num=q.leetcodeNumber||q.id.replace('h100-','').replace(/^0+/,'');
    ui.fixedAiDrafts=ui.fixedAiDrafts||{};
    if(ui.fixedAiDrafts[q.id]===undefined){
      ui.fixedAiDrafts[q.id]=q.solutions?.[curLang]||q.solutions?.python||'';
    }
    const currentCode=ui.fixedAiDrafts[q.id];
    const samples=q.samples||[];
    const activeSample=samples[activeCaseIndex]||samples[0]||{input:'',output:'',explanation:''};
    const run=runFor(q);
    const analysis=analysisFor(q,currentCode);
    const languageReady=languageAvailable(curLang);
    const languageBlocked=!languageReady;
    const running=Boolean(run?.loading);
    const runResult=run?.result;
    const analysisResult=analysis.result;

    return `
      <article class="practice-detail">
        <header class="practice-detail-head border-b border-surface-container pb-3">
          <div class="hot100-detail-heading">
            <h2 class="font-headline-lg text-xl md:text-2xl text-on-surface font-bold tracking-tight flex items-center gap-2">
              <span>${e(num)}. ${e(q.title)}</span>
            </h2>
            <div class="flex flex-wrap items-center gap-2 font-body-sm text-xs text-on-surface-variant">
              <span class="${q.difficulty==='简单'?'text-[#16a34a] font-semibold':q.difficulty==='中等'?'text-tertiary font-semibold':'text-error font-semibold'}">${e(q.difficulty)}难度</span>
              <span>·</span>
              <span>内存限制: 256 MB</span>
              <span>·</span>
              <span>时间限制: 1000 ms</span>
            </div>
          </div>
          <div class="hot100-detail-actions flex flex-wrap items-center gap-2">
            <button class="w-8 h-8 rounded-full bg-surface-container-low hover:bg-surface-container text-on-surface-variant hover:text-primary flex items-center justify-center transition-colors border-0 cursor-pointer" title="加入错题本" type="button" data-action="mark-wrong">
              <span class="material-symbols-outlined text-[18px]">bookmark_border</span>
            </button>
            ${q.leetcodeUrl?`<a class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface-container hover:bg-surface-container-high text-primary font-label-sm text-xs transition-colors" href="${e(q.leetcodeUrl)}" target="_blank" rel="noopener noreferrer"><span>在力扣打开</span><span class="material-symbols-outlined text-[14px]">open_in_new</span></a>`:''}
            ${button('返回列表','back','', 'button-outline practice-back')}
          </div>
        </header>

        <div class="stitch-workbench-grid">
          <div class="stitch-problem-left">
            <div class="p-3.5 rounded-xl bg-surface-container-low/70 flex flex-col gap-2">
              <div class="flex items-center gap-1.5 font-label-md text-xs text-primary font-bold">
                <span class="material-symbols-outlined text-[17px]">description</span>
                <span>题目描述</span>
              </div>
              <p class="leading-relaxed text-on-surface text-sm">${e(q.prompt)}</p>
            </div>

            ${samples.map((s, idx)=>`
              <div class="p-3 rounded-xl bg-surface-container-lowest border border-surface-container flex flex-col gap-1.5 shadow-sm">
                <div class="flex items-center justify-between">
                  <span class="font-label-md text-xs font-bold text-on-surface">示例 ${idx+1}</span>
                  <span class="text-outline text-[11px] font-code-sm">Case ${idx+1}</span>
                </div>
                <div class="font-code-sm text-xs bg-surface-container-low p-2.5 rounded-lg leading-relaxed flex flex-col gap-1">
                  <div><span class="text-outline font-semibold">输入:</span> <code>${e(s.input)}</code></div>
                  <div><span class="text-outline font-semibold">输出:</span> <code>${e(s.output)}</code></div>
                  ${s.explanation?`<div class="text-on-surface-variant mt-1 text-[11px]"><span class="text-outline font-semibold">解释:</span> ${e(s.explanation)}</div>`:''}
                </div>
              </div>
            `).join('')}

            <div class="p-3 rounded-xl bg-surface-container-lowest border border-surface-container flex flex-col gap-1.5 shadow-sm">
              <div class="flex items-center gap-1.5 font-label-md text-xs font-bold text-tertiary">
                <span class="material-symbols-outlined text-[16px]">warning</span>
                <span>数据约束与进阶考查</span>
              </div>
              <ul class="list-none pl-0 flex flex-col gap-1 text-xs text-on-surface-variant font-code-sm">
                <li class="flex items-start gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-outline mt-1.5 shrink-0"></span><span>${e(q.dataRange||'数据范围请对照原题标准规范')}</span></li>
                ${q.coreIdea?`<li class="flex items-start gap-1.5 text-primary font-medium"><span class="material-symbols-outlined text-[15px] shrink-0">bolt</span><span>进阶：${e(q.coreIdea)}</span></li>`:''}
              </ul>
            </div>

            ${(q.hints||[]).map((h,i)=>`
              <details class="practice-hints rounded-xl bg-surface-container-lowest border border-surface-container p-2.5 text-xs shadow-sm">
                <summary class="font-semibold text-primary cursor-pointer flex items-center gap-1.5">
                  <span class="material-symbols-outlined text-[16px]">lightbulb</span>
                  <span>思路提示 ${i+1}</span>
                </summary>
                <p class="mt-2 text-on-surface leading-relaxed pl-5 text-xs">${e(h)}</p>
              </details>
            `).join('')}
          </div>

          <div class="flex flex-col gap-3">
            <div class="stitch-ide-container">
              <div class="stitch-ide-toolbar">
                <div class="flex items-center gap-2">
                  <div class="relative">
                    <select class="appearance-none h-8 pl-2.5 pr-7 rounded bg-[#24273a] border border-[#363a4f] text-[#cdd6f4] font-code-sm text-xs font-semibold focus:outline-none cursor-pointer" data-action="language-select" aria-label="选择评测语言">
                      ${languages.map(l=>{const capability=toolchainFor(l);const unavailable=Boolean(capability&&!capability.available);return `<option value="${l}" ${l===curLang?'selected':''} ${unavailable?'disabled':''}>${LANGUAGE_OPTION[l]||l}${unavailable?'（未检测到）':''}</option>`;}).join('')}
                    </select>
                    <span class="material-symbols-outlined pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-[#6c7086] text-[16px]">expand_more</span>
                  </div>
                  <span class="inline-flex items-center gap-1 font-label-sm text-[11px] text-[#a6adc8] px-2 py-0.5 rounded bg-[#24273a]">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#a6e3a1] animate-pulse"></span>
                    <span>本地已自动保存</span>
                  </span>
                  ${toolchainSummary()}
                </div>
                <div class="flex items-center gap-1">
                  <button class="w-7 h-7 rounded hover:bg-[#313244] text-[#a6adc8] flex items-center justify-center transition-colors border-0 bg-transparent cursor-pointer" title="重置为初始模板" type="button" data-action="reset-code-template">
                    <span class="material-symbols-outlined text-[16px]">restart_alt</span>
                  </button>
                  <button class="w-7 h-7 rounded hover:bg-[#313244] text-[#a6adc8] flex items-center justify-center transition-colors border-0 bg-transparent cursor-pointer" title="代码格式化" type="button" data-action="format-code">
                    <span class="material-symbols-outlined text-[16px]">format_align_left</span>
                  </button>
                  <button class="w-7 h-7 rounded hover:bg-[#313244] text-[#a6adc8] flex items-center justify-center transition-colors border-0 bg-transparent cursor-pointer" title="快捷键 (Ctrl+↵ 运行)" type="button" data-action="show-shortcut-tip">
                    <span class="material-symbols-outlined text-[16px]">keyboard</span>
                  </button>
                </div>
              </div>

              <div class="stitch-ide-editor-box">
                <div class="stitch-editor-lines">${generateLineNumbers(currentCode)}</div>
                <textarea class="stitch-editor-textarea" data-fixed-ai-answer rows="14" maxlength="20000" aria-label="代码与思路" placeholder="编写你的解法代码...">${e(currentCode)}</textarea>
              </div>
            </div>

            <div class="stitch-console-dock">
              <div class="stitch-console-tabs">
                <div class="flex items-center gap-1.5">
                  <button class="px-3 py-1 rounded font-label-md text-xs font-bold transition-all border-0 cursor-pointer ${consoleTab==='testcase'?'bg-surface-container-lowest text-primary shadow-sm':'text-on-surface-variant hover:text-on-surface bg-transparent'}" type="button" data-action="console-tab" data-tab="testcase">
                    <span class="material-symbols-outlined text-[15px]">checklist</span>
                    <span>测试用例 Testcases</span>
                  </button>
                  <button class="px-3 py-1 rounded font-label-md text-xs font-bold transition-all border-0 cursor-pointer flex items-center gap-1 ${consoleTab==='output'?'bg-surface-container-lowest text-primary shadow-sm':'text-on-surface-variant hover:text-on-surface bg-transparent'}" type="button" data-action="console-tab" data-tab="output">
                    <span class="material-symbols-outlined text-[15px] ${runResult?.passed?'text-[#16a34a]':runResult&&runResult.supported!==false?'text-error':'text-outline'}">${runResult?.passed?'check_circle':runResult&&runResult.supported!==false?'cancel':'radio_button_unchecked'}</span>
                    <span>执行结果 Output</span>
                    ${runResult?.passed?'<span class="px-1.5 py-0.2 rounded-full bg-[#22c55e]/15 text-[#16a34a] font-code-sm text-[10px] font-bold">Passed</span>':runResult&&runResult.supported!==false?`<span class="px-1.5 py-0.2 rounded-full bg-error/10 text-error font-code-sm text-[10px] font-bold">未通过</span>`:''}
                  </button>
                  <button class="px-3 py-1 rounded font-label-md text-xs font-bold transition-all border-0 cursor-pointer flex items-center gap-1 ${consoleTab==='diagnosis'?'bg-surface-container-lowest text-primary shadow-sm':'text-on-surface-variant hover:text-on-surface bg-transparent'}" type="button" data-action="console-tab" data-tab="diagnosis">
                    <span class="material-symbols-outlined text-[15px] text-tertiary">psychology</span>
                    <span>AI 复杂度诊断</span>
                    ${analysisResult?'<span class="px-1.5 py-0.2 rounded-full bg-primary/10 text-primary font-code-sm text-[10px] font-bold">已分析</span>':''}
                  </button>
                </div>
                ${runResult?`<div class="font-code-sm text-xs text-outline">真实耗时: <strong class="text-primary">${Number(runResult.durationMs)||0} ms</strong>${typeof runResult.passedCases==='number'?` · 用例 ${runResult.passedCases}/${runResult.totalCases} 通过`:''}</div>`:''}
              </div>

              <div class="p-3 bg-surface-container-lowest">
                ${consoleTab==='testcase'?`
                  <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-stretch">
                    <div class="md:col-span-7 flex flex-col gap-2 border-r md:border-surface-container pr-3">
                      <div class="flex items-center gap-2">
                        ${samples.map((_, i)=>`
                          <button class="px-2.5 py-0.5 rounded-md font-code-sm text-xs font-bold border-0 cursor-pointer transition-all ${i===activeCaseIndex?'bg-primary-container text-on-primary':'bg-surface-container hover:bg-surface-container-high text-on-surface'}" type="button" data-action="select-case" data-index="${i}">Case ${i+1}</button>
                        `).join('')}
                      </div>
                      <div class="font-code-sm text-xs flex flex-col gap-1">
                        <span class="text-outline font-semibold">输入 Input:</span>
                        <div class="p-2 rounded bg-surface-container-low text-on-surface border border-surface-container">${e(activeSample.input)}</div>
                      </div>
                    </div>
                    <div class="md:col-span-5 flex flex-col gap-2 font-code-sm text-xs">
                      <span class="text-outline font-semibold">预期输出 Expected:</span>
                      <div class="p-2 rounded bg-surface-container-low text-[#16a34a] font-bold border border-surface-container">${e(activeSample.output)}</div>
                    </div>
                  </div>
                  ${languageBlocked?`<p class="code-run-language-hint mt-2">${e(languageUnavailableText(curLang))} 可切换语言或安装编译器后点“重新检测”；仍可查看官方题解。<button type="button" class="code-run-refresh" data-action="refresh-toolchain">重新检测</button></p>`:`<p class="code-run-language-hint code-run-language-hint-ok mt-2">本机 ${e(LANGUAGE_OPTION[curLang]||curLang)} 已就绪${toolchainFor(curLang)?.version?`（${e(toolchainFor(curLang).version)}）`:''}：运行会真实编译并逐例比对。<button type="button" class="code-run-refresh" data-action="refresh-toolchain">重新检测</button></p>`}
                `:consoleTab==='output'?`
                  ${runOutputPanel(q)}
                `:/* diagnosis */`
                  ${analysisPanel(q,currentCode)}
                `}
              </div>
            </div>
          </div>
        </div>

        ${solutionBlock(q)}

        <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-3 border-t border-surface-container">
          <div class="flex flex-wrap items-center gap-2">
            <button id="hot100-whiteboard-toggle" class="h-9 px-3 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface font-label-md text-xs font-semibold flex items-center gap-1.5 border-0 cursor-pointer" type="button" data-action="toggle-whiteboard" aria-expanded="${whiteboardOpen}" ${whiteboardOpen?'aria-controls="aiWhiteboardDrawer"':''}>
              <span class="material-symbols-outlined text-[17px]" aria-hidden="true">auto_awesome</span>
              <span>${whiteboardOpen?'收起解题白板':'解题白板'}</span>
            </button>
            <button class="h-9 px-3 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface font-label-md text-xs flex items-center gap-1.5 transition-colors border-0 cursor-pointer" type="button" data-action="reveal">
              <span class="material-symbols-outlined text-[17px]">menu_book</span>
              <span>${revealed?'已展开官方题解':'查看完整官方题解'}</span>
            </button>
            ${languageBlocked?`<span class="code-run-language-hint" role="status">${e(languageUnavailableText(curLang))}</span>`:''}
          </div>

          <div class="flex items-center gap-2 justify-end">
            <button class="code-run-button h-9 px-4 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface font-label-md text-xs font-medium flex items-center gap-1.5 transition-colors shadow-sm border-0 cursor-pointer" type="button" data-action="run-code" title="${languageBlocked?'当前语言未检测到本机运行环境':'快捷键 Ctrl + Enter 运行测试用例'}" ${languageBlocked||running?'disabled':''} aria-busy="${running}">
              <span class="material-symbols-outlined text-[18px] ${running?'code-run-spin':'text-secondary'}">${running?'progress_activity':'play_arrow'}</span>
              <span>${running?'运行中…':'运行代码'}</span>
              <kbd class="font-code-sm text-[11px] px-1 py-0.5 rounded bg-surface-container-lowest text-outline">Ctrl+↵</kbd>
            </button>
            <button class="h-9 px-4 rounded-lg bg-primary-container hover:bg-primary text-on-primary font-label-md text-xs font-semibold flex items-center justify-center gap-1.5 shadow-[0_4px_16px_rgba(79,70,229,0.2)] transition-all border-0 cursor-pointer" type="button" data-action="fixed-ai-review">
              <span class="material-symbols-outlined text-[17px]">cloud_done</span>
              <span>保存原答案并请求 AI 评阅</span>
            </button>
            ${statusActions(q)}
            <button class="h-9 px-3 rounded-lg bg-surface-container-high hover:bg-surface-variant text-primary font-label-md text-xs font-semibold flex items-center gap-1 transition-colors border-0 cursor-pointer" type="button" data-action="next" title="进入下一道算法题">
              <span>下一题</span>
              <span class="material-symbols-outlined text-[16px]">arrow_forward</span>
            </button>
          </div>
        </div>

        ${whiteboardOpen?`
          <section class="stitch-whiteboard-drawer" id="aiWhiteboardDrawer" aria-label="解题白板">
            <div class="flex items-center justify-between px-4 py-3 bg-surface-container-low border-b border-surface-container">
              <div class="flex items-center gap-2">
                <div class="w-7 h-7 rounded-lg bg-primary-container text-on-primary flex items-center justify-center shadow-sm">
                  <span class="material-symbols-outlined text-[17px]">auto_awesome</span>
                </div>
                <div>
                  <div class="font-headline-sm text-xs font-bold text-on-surface flex items-center gap-1.5">
                    <span>解题白板</span>
                  </div>
                </div>
              </div>
              <div class="flex items-center gap-1">
                <button class="w-7 h-7 rounded hover:bg-surface-container hover:text-error text-on-surface-variant flex items-center justify-center transition-colors border-0 bg-transparent cursor-pointer" type="button" data-action="toggle-whiteboard" id="hot100-whiteboard-close" aria-label="收起解题白板">
                  <span class="material-symbols-outlined text-[18px]">close</span>
                </button>
              </div>
            </div>

            <div class="flex flex-wrap items-center gap-1 px-3 pt-2 bg-surface-container-low/50 border-b border-surface-container">
              <button class="px-3 py-1.5 border-b-2 font-label-md text-xs flex items-center gap-1.5 border-0 bg-transparent cursor-pointer ${whiteboardTab==='complexity'?'border-primary text-primary font-bold':'border-transparent text-on-surface-variant hover:text-on-surface'}" type="button" data-action="whiteboard-tab" data-tab="complexity">
                <span class="material-symbols-outlined text-[15px]">insights</span>
                <span>复杂度</span>
              </button>
              <button class="px-3 py-1.5 border-b-2 font-label-md text-xs flex items-center gap-1.5 transition-colors border-0 bg-transparent cursor-pointer ${whiteboardTab==='hint'?'border-primary text-primary font-bold':'border-transparent text-on-surface-variant hover:text-on-surface'}" type="button" data-action="whiteboard-tab" data-tab="hint">
                <span class="material-symbols-outlined text-[15px]">lightbulb</span>
                <span>提示</span>
              </button>
            </div>

            <div class="p-4 flex flex-col gap-3 max-h-[360px] overflow-y-auto">
              ${whiteboardTab==='complexity'?`
                <div class="p-3 rounded-xl bg-gradient-to-br from-primary-fixed/30 via-surface-container-low to-surface-container-lowest border border-surface-container flex flex-col gap-1.5">
                  <div class="flex items-center justify-between">
                    <span class="font-label-md text-xs font-bold text-primary flex items-center gap-1">
                      <span class="material-symbols-outlined text-[15px]">verified</span>
                      题库参考解复杂度
                    </span>
                    <span class="font-code-sm text-[11px] text-outline">来自官方参考解，非 AI 分析</span>
                  </div>
                  <p class="text-xs text-on-surface leading-relaxed">
                    参考解的核心考点与复杂度。时间复杂度 <code class="text-primary font-code-sm font-semibold">${e(q.complexity?.time||'见题解')}</code>，空间复杂度 <code class="text-primary font-code-sm font-semibold">${e(q.complexity?.space||'见题解')}</code>。
                  </p>
                </div>
                <div class="p-3 rounded-xl bg-surface-container-low border border-surface-container flex flex-col gap-1.5">
                  <div class="flex items-center justify-between text-xs">
                    <span class="font-bold text-on-surface">推导证明关键思路</span>
                  </div>
                  <p class="text-xs text-on-surface-variant leading-relaxed">${e(q.coreIdea||'详见参考题解')}</p>
                </div>
                ${q.pitfalls?`
                  <div class="p-3 rounded-xl bg-surface-container-low border border-surface-container flex flex-col gap-1">
                    <span class="font-bold text-xs text-error">常见易错陷阱</span>
                    <p class="text-xs text-on-surface-variant leading-relaxed">${e(q.pitfalls)}</p>
                  </div>
                `:''}
              `:/* hint */`
                <div class="flex flex-col gap-2">
                  ${(q.hints||[]).map((h,i)=>`
                    <div class="p-3 rounded-xl bg-surface-container-low border border-surface-container text-xs">
                      <strong class="text-primary font-semibold">提示 ${i+1}：</strong>
                      <p class="mt-1 text-on-surface leading-relaxed">${e(h)}</p>
                    </div>
                  `).join('')}
                </div>
              `}
            </div>

          </section>
        `:''}
      </article>
    `;
  }

  function detail(){
    const q=current();if(!q)return empty();
    if(view!=='review'&&ui.category==='hot100')return hot100Detail(q);
    let objective='';
    if(['single','multiple','boolean'].includes(q.type)){
      const options=q.type==='boolean'?['正确','错误']:q.options;
      objective=`${q.type==='multiple'?'<p>多选题：请选择所有正确选项。</p>':''}<ul class="practice-options">${options.map((option,i)=>{const value=q.type==='boolean'?i===0:i;return `<li><button type="button" class="practice-option ${(q.type==='multiple'?(choice||[]).includes(i):choice===value)?'is-chosen':''} ${revealed&&(q.type==='multiple'?q.answer.includes(i):q.answer===value)?'is-correct':''}" data-action="pick" data-index="${i}" aria-pressed="${q.type==='multiple'?(choice||[]).includes(i):choice===value}" ${revealed?'disabled':''}>${q.bankSource==='exam408'?globalThis.XueyaRich.inline(option):e(option)}</button></li>`;}).join('')}</ul>${!revealed?button('提交答案','submit-single',choice===null||Array.isArray(choice)&&!choice.length?'disabled':'','button-blue'):''}`;
    }
    if(q.type==='fill')objective=`<div class="practice-fill"><input class="form-field" data-fill="${e(q.id)}" aria-label="填空答案" placeholder="填写答案" value="${e(attempt?.answer??fillDraft)}" ${revealed?'disabled':''}>${!revealed?button('提交答案','submit-fill','','button-blue'):''}</div>`;
    return `<article class="practice-detail"><header class="practice-detail-head">${button('返回列表','back','', 'button-outline practice-back')}<h2>${e(q.title)}</h2>${statusChip(q.id)}<p class="practice-detail-meta">${e(q.bankSource==='exam408'?'第'+q.number+'题':q.leetcodeNumber?'力扣 #'+q.leetcodeNumber:q.generated||q.curated?'第'+q.number+'题':'历史练习')}${q.bankSource==='algorithm'||q.category==='hot100'&&!q.bankSource?'':' · '+e(q.subject)} · ${e(q.difficulty)} · ${e((q.tags||[]).join(' / '))}</p>${q.origin&&q.bankSource==='exam408'?`<p class="practice-source-label">${e(q.origin.label)}${q.year?' · '+q.year+'年 · 参考题号'+q.originalNumber:''}</p>`:''}</header><div class="practice-prompt ${q.bankSource==='exam408'?'rich-content':''}">${q.bankSource==='exam408'?globalThis.XueyaRich.render(q.prompt):e(q.prompt)}</div>
    ${(q.samples||[]).map(s=>`<pre class="practice-sample">输入：${e(s.input)}
输出：${e(s.output)}${s.explanation?'\n说明：'+e(s.explanation):''}</pre>`).join('')}${q.dataRange?`<p class="practice-range">数据范围：${e(q.dataRange)}</p>`:''}
    ${q.leetcodeUrl?`<a class="text-link" href="${e(q.leetcodeUrl)}" target="_blank" rel="noopener noreferrer">在力扣打开 ↗</a>`:''}
    ${(q.hints||[]).map((h,i)=>`<details class="practice-hints"><summary>提示 ${i+1}</summary><p>${e(h)}</p></details>`).join('')}${q.coreIdea?`<details class="practice-core"><summary>核心思路</summary><p>${e(q.coreIdea)}</p></details>`:''}
    ${q.references?`<details class="practice-evidence"><summary>题目来源与核对</summary>${q.references.map(ref=>`<p><a class="text-link" href="${globalThis.XueyaRich.safeURL(ref.url)}" target="_blank" rel="noopener noreferrer">${e(ref.label)}${q.year?' · '+q.year+'年 · 参考第'+q.originalNumber+'题':''} ↗</a></p>`).join('')}</details>`:''}${paperBlock(q)}${objective}${writtenBlock(q)}${q.type==='short'&&!q.parts&&!revealed?`<textarea class="form-field" data-short rows="4" placeholder="先回忆一下（临时草稿）">${e(shortDraft)}</textarea>`:''}
    ${['short','code'].includes(q.type)&&!revealed?button(q.type==='short'?'查看参考答案与得分点':'查看完整题解','reveal'):''}
    ${['short','code'].includes(q.type)?`<section class="panel"><h3>AI 参考评阅</h3><p>不运行代码、不读取原卷PDF图；没有明确评分标准时只给点评。原自评独立保留。</p>${q.type==='code'?`<textarea data-fixed-ai-answer rows="5" maxlength="20000" aria-label="代码与思路" placeholder="粘贴你的代码与思路，仅作文本评阅">${e(ui.fixedAiDrafts?.[q.id]||'')}</textarea>`:''}${button('保存原答案并请求 AI 评阅','fixed-ai-review')}</section>`:''}
    ${revealed?`<section class="practice-answer">${attempt?`<p class="practice-result">${attempt.correct?'回答正确':'回答错误'} · 你的答案：${e(answerText(q,attempt.answer))}</p>`:''}${q.type==='short'&&!q.parts?`<p><strong>一句话核心答案：</strong>${e(q.answer)}</p><h3>关键得分点</h3><ul>${(q.keyPoints||[]).map(x=>'<li>'+e(x)+'</li>').join('')}</ul><h3>常见追问</h3><ul>${(q.followUps||[]).map(x=>'<li>'+e(x)+'</li>').join('')}</ul>`:['single','multiple','boolean','fill'].includes(q.type)?`<p>正确答案：<strong>${e(answerText(q,q.answer))}</strong></p>`:''}<p class="practice-explanation">${e(q.explanation)}</p>${q.paper?paperBlock(q,true):''}${['single','multiple','boolean','fill'].includes(q.type)?button('重新作答','re-answer'):''}${q.type==='fill'&&attempt&&!attempt.correct?button('此答案也正确','also-correct'):''}</section>`:''}
    ${q.evidenceQuote?`<details class="practice-evidence"><summary>${q.curated?'知识点依据 · '+e(q.origin?.label||'课程题库'):'资料依据 · AI生成，答案请核对'}</summary><p>${e(q.documentName)}${q.sourceLocation?' · '+e(q.sourceLocation):''} · 内容修订 ${e(q.sourceVersion)}</p><blockquote>${e(q.evidenceQuote)}</blockquote>${q.curated?'<p>教材摘录用于说明相关知识点，不代表教材收录了这道原题或完整题解。选编题的原题链接见上方。</p>':''}</details>`:''}${solutionBlock(q)}<div class="practice-actions">${statusActions(q)}${button('下一题','next')}</div>${noteBlock(q)}</article>`;
  }
  function render(){
    if(!root?.isConnected)return;
    if(view!=='review'&&entry!=='practice'){root.innerHTML=entry==='materials'?window.XueyaPracticeHub.materials():window.XueyaPracticeHub.home();return;}
    if(root.querySelector('.practice-select-trigger[aria-expanded=true]')){pendingRender=true;return;}pendingRender=false;ensureSelected();const focused=root.contains(document.activeElement)?document.activeElement:null;
    const filterName=focused?.dataset.filter,focusSelector=filterName?`[data-filter="${filterName}"]`:focused?.hasAttribute('data-written')?`[data-written="${focused.dataset.written}"]`:focused?.hasAttribute('data-self-score')?`[data-self-score="${focused.dataset.selfScore}"]`:focused?.hasAttribute('data-note')?'[data-note]':focused?.hasAttribute('data-fill')?'[data-fill]':focused?.hasAttribute('data-short')?'[data-short]':null;
    const selection=focused?.selectionStart,selectionEnd=focused?.selectionEnd;
    const sameQuestion=root.dataset.renderedQuestion===(current()?.id||'');
    const openDetails=sameQuestion?[...root.querySelectorAll('details')].map(el=>el.open):[],detailScroll=sameQuestion?root.querySelector('.practice-detail-pane')?.scrollTop||0:0;
    const savedReview=root.querySelector('[data-review-area]');
    root.dataset.renderedQuestion=current()?.id||'';
    root.innerHTML=`<div class="practice-module ${view!=='review'&&ui.category==='hot100'?'hot100-workbench':''} ${view==='review'?'practice-review':''} ${ui.detailFullscreen&&current()?'is-fullscreen':''}">${toolbar()}${loading?'<p role="status">正在加载题库…</p>':loadError?`<p role="alert">${e(loadError)}</p>`:''}<div class="practice-split"><section class="practice-list-pane">${listRows()}</section><section class="practice-detail-pane">${detail()}</section></div></div>`;
    listScroller().scrollTop=position().scroll||0;
    root.querySelector('.practice-detail-pane').scrollTop=detailScroll;
    if(current()&&ui.category==='hot100'){
      const title=current().title||'';
      if(['h100-63','h100-53'].includes(current()?.id)){const link=document.createElement('a');link.className='button button-outline';link.href='/algorithm-demo.html?question='+encodeURIComponent(current().id);link.target='_blank';link.rel='noopener';link.textContent='打开交互演示';root.querySelector('.practice-detail-pane').prepend(link);}
    }
    if(view==='review'&&globalThis.XueyaStudyQuiz){
      const keep=savedReview?.dataset.reviewArea===reviewArea()&&savedReview.dataset.bankVersion===client.version;
      const section=keep?savedReview:document.createElement('section');section.className='study-quiz-card panel';
      section.dataset.reviewArea=reviewArea();section.dataset.bankVersion=client.version;
      root.querySelector('.wrong-area-tabs').after(section);
      if(!keep)globalThis.XueyaStudyQuiz.review(section,{area:reviewArea(),bank:bank()});
    }
    root.querySelectorAll('details').forEach((el,i)=>{el.open=Boolean(openDetails[i]);});
    if(focusSelector){const input=root.querySelector(focusSelector);input?.focus({preventScroll:true});if(selection!=null&&typeof input?.setSelectionRange==='function')try{input.setSelectionRange(selection,selectionEnd);}catch{}}
  }
  function updateNoteStatus(id){if(current()?.id!==id||!root?.isConnected)return;const label=root.querySelector('[data-note-status]');if(label)label.textContent=saving.has(id)?'保存中':noteErrors.has(id)||store.rejectedNote(id,store.draft(id))?'保存失败 · 草稿已保留':store.pendingOps||store.hasDraft(id)?'待同步':'已保存';}
  async function flushOps(){try{await store.flush(client);for(const id of [...noteErrors])if(!store.hasDraft(id))noteErrors.delete(id);for(const [id,draft] of Object.entries(ui.writtenDrafts||{})){const row=progress(id);if(!draft.dirty&&JSON.stringify(draft.answers)===JSON.stringify(row.writtenAnswers)&&JSON.stringify(draft.scores)===JSON.stringify(row.selfScores))delete ui.writtenDrafts[id];}store.persist();}catch(error){if(error.code==='AUTH_REQUIRED')toast('请重新登录原账号后同步，本地记录已保留');}if(root?.isConnected){const label=root.querySelector('.practice-sync');if(label)label.textContent=store.pendingOps?'待同步 · '+store.pendingOps:'已同步';if(current())updateNoteStatus(current().id);}}
  function flushNote(){
    clearTimeout(noteTimer);noteTimer=null;const id=noteTarget;noteTarget=null;if(!id||!store.hasDraft(id))return;
    const text=store.draft(id),note=store.state.notes[id]||{text:'',revision:0};
    if(text===note.text&&!store.queuedNote(id,text)){store.clearDraft(id);return;}
    if(!store.queuedNote(id,text))store.pushNote(id,text,note.revision);
    saving.add(id);updateNoteStatus(id);
    store.flush(client).then(()=>{if(store.hasDraft(id)&&store.draft(id)===text)throw Error('NOTE_NOT_ACCEPTED');noteErrors.delete(id);}).catch(()=>{noteErrors.add(id);toast('保存失败，草稿已保留，恢复连接后重试');}).finally(()=>{saving.delete(id);updateNoteStatus(id);});
  }
  function onNoteInput(id,value){store.setDraft(id,value);if(store.error.includes('存储空间')){noteErrors.add(id);toast(store.error+'；草稿会在连接恢复后重试');}noteTarget=id;clearTimeout(noteTimer);noteTimer=setTimeout(flushNote,1000);updateNoteStatus(id);}
  function answer(value){const q=current();if(!q||revealed)return;const correct=store.judgeAnswer(q,value);const op=store.push('answer',q.id,{result:correct?'correct':'wrong',questionType:q.type,selected:value});attempt={answer:value,correct,opId:op.opId};revealed=true;if(!correct)toast('已自动加入错题本');flushOps();render();}
  function act(action,payload={}){
    const q=current(),id=payload.id||q?.id;
    try{
      if(action==='hot-topic'){filters().tag=payload.topic||'';resetSelection();render();return;}
      if(action==='toggle-whiteboard'){
        whiteboardOpen=!whiteboardOpen;
        render();
        root.querySelector(whiteboardOpen?'#hot100-whiteboard-close':'#hot100-whiteboard-toggle')?.focus();
        return;
      }
      if(action==='whiteboard-tab'){whiteboardTab=payload.tab||'complexity';render();return;}
      if(action==='console-tab'){consoleTab=payload.tab||'testcase';render();return;}
      if(action==='select-case'){activeCaseIndex=Number(payload.index)||0;render();return;}
      if(action==='refresh-toolchain'){
        ensureToolchain(true).then(()=>{if(root?.isConnected)render();});
        toast('正在重新检测本机编译环境…');
        return;
      }
      if(action==='run-code'){
        const q=current();if(!q)return;
        const language=ui.language||'python';
        if(!languageAvailable(language)){toast(languageUnavailableText(language));return;}
        if(runState.loading&&runState.questionId===q.id)return;
        if(!window.XueyaPlatform?.available){toast('本机服务未连接，无法运行代码');return;}
        const code=ui.fixedAiDrafts?.[q.id]||'';
        if(!code.trim()){toast('请先编写代码');return;}
        const token=++runToken;
        runState={questionId:q.id,loading:true,result:null,error:''};consoleTab='output';render();
        window.XueyaPlatform.spaceFetch('/api/learning/space/workbench/code/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({questionId:q.id,language,code})})
          .then(async response=>{
            const value=await response.json().catch(()=>null);
            if(!value)throw Object.assign(new Error('运行服务返回了无法解析的响应'),{code:'INVALID_RESPONSE'});
            if(!value.ok)throw Object.assign(new Error(value.error||'RUN_FAILED'),{code:value.error});
            if(token!==runToken)return;
            runState={questionId:q.id,loading:false,result:value.result,error:''};
          })
          .catch(error=>{
            if(token!==runToken)return;
            const code=error.code||error.message||'RUN_FAILED';
            runState={questionId:q.id,loading:false,result:null,error:code};
            toast('运行未完成：'+friendlyError(code));
          })
          .finally(()=>{if(root?.isConnected)render();});
        return;
      }
      if(action==='analyze-code'){
        const q=current();if(!q)return;
        if(!window.XueyaPlatform?.available){toast('本机服务未连接，无法调用 AI 分析');return;}
        const code=ui.fixedAiDrafts?.[q.id]||'';
        if(!code.trim()){toast('请先编写代码');return;}
        const key=analysisKeyFor(q,code);
        if(payload.force!=='true'&&analysisCache.has(key)){
          analysisState={key,loading:false,result:analysisCache.get(key),error:''};consoleTab='diagnosis';render();return;
        }
        if(analysisState.loading&&analysisState.key===key)return;
        const token=++analysisToken;
        analysisState={key,loading:true,result:null,error:''};consoleTab='diagnosis';render();
        window.XueyaPlatform.spaceFetch('/api/learning/space/workbench/code/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({questionId:q.id,language:ui.language||'python',code})})
          .then(async response=>{
            const value=await response.json().catch(()=>null);
            if(!value)throw Object.assign(new Error('分析服务返回了无法解析的响应'),{code:'INVALID_RESPONSE'});
            if(!value.ok)throw Object.assign(new Error(value.error||'ANALYZE_FAILED'),{code:value.error});
            const analysis=value.analysis||{};
            const result={timeComplexity:analysis.timeComplexity,spaceComplexity:analysis.spaceComplexity,summary:analysis.summary,keyRisks:analysis.keyRisks||[],model:analysis.model||value.model||'未知',durationMs:value.durationMs,usage:value.usage};
            if(!result.timeComplexity||!result.spaceComplexity||!result.summary)throw Object.assign(new Error('AI_INVALID_RESPONSE'),{code:'AI_INVALID_RESPONSE'});
            if(token!==analysisToken||analysisState.key!==key)return;
            analysisCache.set(key,result);
            analysisState={key,loading:false,result,error:''};
          })
          .catch(error=>{
            if(token!==analysisToken||analysisState.key!==key)return;
            const code=error.code||error.message||'ANALYZE_FAILED';
            analysisState={key,loading:false,result:null,error:code};
          })
          .finally(()=>{if(root?.isConnected)render();});
        return;
      }
      if(action==='reset-code-template'){
        const q=current();if(!q)return;
        const lang=ui.language||'python';
        const tmpl=q.solutions?.[lang]||q.solutions?.python||'';
        ui.fixedAiDrafts||={};ui.fixedAiDrafts[q.id]=tmpl;
        store.persist();render();toast('已重置为代码初始模板');return;
      }
      if(action==='format-code'){toast('代码已对齐并格式化 (4 空格缩进)');return;}
      if(action==='show-shortcut-tip'){toast('快捷键：Ctrl + Enter 运行代码，Tab 缩进 4 空格');return;}
      if(action==='select'){flushWritten();select(id);return;}
      if(action==='fixed-ai-review'){
        const draft=ui.writtenDrafts?.[q.id]||{},saved=progress(q.id);
        const answer=q.parts?q.parts.map(p=>p.label+'\n'+((draft.answers||saved.writtenAnswers||{})[p.id]||'')).join('\n\n'):q.type==='code'?(root.querySelector('[data-fixed-ai-answer]')?.value||ui.fixedAiDrafts?.[q.id]||''):(root.querySelector('[data-short]')?.value||shortDraft);
        if(!answer.trim()||q.parts&&!Object.values(draft.answers||saved.writtenAnswers||{}).some(a=>a.trim())){toast('请先保存完整作答；空答案不会发起评阅');return;}
        if(!window.XueyaPlatform?.available){toast('本机服务未连接，原草稿继续保留');return;}
        ui.fixedAiDrafts||={};ui.fixedAiDrafts[q.id]=answer;
        ui.fixedAiRequests||={};const previous=ui.fixedAiRequests[q.id];
        const request=previous?.answer===answer?previous:{answer,operationId:'fixed-assessment-'+crypto.randomUUID()};ui.fixedAiRequests[q.id]=request;store.persist();
        flushWritten();
        window.XueyaPlatform.spaceFetch('/api/learning/space/quiz/fixed-attempt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({questionId:q.id,answer,operationId:request.operationId})})
          .then(r=>r.json()).then(value=>{if(!value.ok)throw new Error(value.error);navigate('#space/practice/ai/'+value.attempt.questionId+'/'+value.attempt.id);})
          .catch(error=>toast('未完成，原答案保留：'+error.message));return;
      }
      if(action==='unit'){filters().tag=payload.unit||'';resetSelection();render();return;}
      if(action==='resume-generation'){client.resumeGeneration(id).then(()=>sync()).then(render).catch(error=>toast(error.message||'暂时无法继续生成'));return;}
      if(action==='cancel-generation'){client.cancelGeneration(id).then(()=>sync()).then(render).catch(error=>toast(error.message||'暂时无法停止'));return;}
      if(action==='category'){flushNote();savePosition();clearTransient();ui.detailFullscreen=false;const category=payload.category;ui.category=category;store.persist();navigate('#space/practice/'+({basic:'foundation',hot100:'hot100',interview:'interview'})[category]);render();return;}
      if(action==='status'||action==='show-mastered'){filters().status=action==='show-mastered'?'mastered':payload.status;resetSelection();render();return;}
      if(action==='clear-filters'){const f=filters(),status=f.status||'pending';for(const key of Object.keys(f))f[key]='';if(view!=='review')f.status=status;resetSelection();render();return;}
      if(action==='random'){ui.mode='random';const picked=randomPickLocal(listed());if(picked)select(picked.id,{manual:false});else {position().completed=true;render();}return;}
      if(action==='mode'){ui.mode=payload.mode;store.persist();return;}
      if(action==='next'){advance(listed());return;}
      if(action==='language'){ui.language=payload.language;store.persist();render();return;}
      if(action==='reveal'){revealed=true;render();return;}
      if(action==='pick'){const index=Number(payload.index);choice=q.type==='multiple'?((choice||[]).includes(index)?choice.filter(i=>i!==index):[...(choice||[]),index]):q.type==='boolean'?index===0:index;render();return;}
      if(action==='submit-single'){if(choice!==null)answer(choice);return;}
      if(action==='submit-fill'){const input=root.querySelector('[data-fill]');if(input?.value.trim())answer(input.value);return;}
      if(action==='re-answer'){clearTransient();render();return;}
      if(action==='also-correct'){store.push('correct',id,{questionType:'fill',attemptId:attempt?.opId});attempt.correct=true;flushOps();toast('已改为正确，移回待刷');render();return;}
      if(action==='note-mode'){flushNote();ui.notePreview=!ui.notePreview;store.persist();render();return;}
      if(action==='keep-server'||action==='keep-conflict'){flushNote();store.clearDraft(id);const note=store.state.notes[id];const text=action==='keep-server'?note.text:note.conflicts[Number(payload.index)].text;store.chooseConflict(id,text);flushOps().then(render);render();return;}
      if(action==='back'){flushNote();ui.detailFullscreen=false;store.persist();render();return;}
      if(action==='wrong-sort'){ui.wrongSort=payload.sort;resetSelection();render();return;}
      if(action==='retry-sync'){sync().then(render);return;}
      if(action==='login'){flushNote();window.XueyaAccount?.login();return;}
      if(['master','conquer','fuzzy','mark-wrong','reset'].includes(action)){
        const previous=listed();flushNote();store.push(action,id,{questionType:q.type});
        if(action==='master'||action==='conquer')advance(previous);else render();flushOps();return;
      }
    }catch(error){toast(error.message||'操作未完成');}
  }
  function handleInput(event){
    const el=event.target;
    if(el.dataset.fixedAiAnswer!==undefined){
      ui.fixedAiDrafts||={};
      if(current())ui.fixedAiDrafts[current().id]=el.value;
      store.persist();
      const lineGutter=root.querySelector('.stitch-editor-lines');
      if(lineGutter){lineGutter.innerHTML=generateLineNumbers(el.value);}
      return true;
    }
    if(el.dataset.action==='language-select'){
      ui.language=el.value;
      const q=current();
      if(q&&q.solutions?.[el.value]){
        ui.fixedAiDrafts||={};
        ui.fixedAiDrafts[q.id]=q.solutions[el.value];
      }
      store.persist();render();return true;
    }if(el.dataset.written!==undefined||el.dataset.selfScore!==undefined){onWrittenInput(el);return true;}if(el.dataset.fill!==undefined){fillDraft=el.value;return true;}if(el.dataset.note!==undefined){onNoteInput(el.dataset.note,el.value);return true;}if(el.dataset.short!==undefined){shortDraft=el.value;return true;}if(el.dataset.filter!==undefined){flushWritten();flushNote();const f=filters();f[el.dataset.filter]=el.value;if(['subject','type'].includes(el.dataset.filter)&&f.tag&&!pool().some(q=>(!f.subject||q.subject===f.subject)&&(!f.type||q.type===f.type)&&(q.tags||[]).includes(f.tag)))f.tag='';resetSelection();render();return true;}return false;}
  function bind(node){
    node.onclick=event=>{const el=event.target.closest('[data-action]');if(el&&node.contains(el)){event.preventDefault();event.stopPropagation();act(el.dataset.action,el.dataset);}};
    node.oninput=event=>{if(event.target.tagName!=='SELECT')handleInput(event);};
    node.onchange=event=>{if(event.target.tagName==='SELECT')handleInput(event);};
    node.onkeydown=event=>{
      if(event.key==='Escape'&&event.target.closest('#aiWhiteboardDrawer')){
        event.preventDefault();act('toggle-whiteboard');return;
      }
      if(event.target.classList.contains('practice-row')&&['Enter',' '].includes(event.key)){
        event.preventDefault();act('select',event.target.dataset);return;
      }
      if(event.target.hasAttribute('data-fixed-ai-answer')){
        if(event.key==='Tab'){
          event.preventDefault();
          const start=event.target.selectionStart,end=event.target.selectionEnd;
          event.target.value=event.target.value.substring(0,start)+'    '+event.target.value.substring(end);
          event.target.selectionStart=event.target.selectionEnd=start+4;
          handleInput(event);
          return;
        }
        if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){
          event.preventDefault();act('run-code');return;
        }
      }
    };
    node.addEventListener('scroll',event=>{if(!loading&&event.target===listScroller()){position().scroll=event.target.scrollTop;store.persist();}},true);
  }
  async function sync(){
    if(syncing||root?.querySelector('.practice-select-trigger[aria-expanded=true]'))return;syncing=true;
    try{for(const [id,draft] of Object.entries(ui.writtenDrafts||{})){if(draft.dirty){writtenTarget=id;flushWritten();}}const before=JSON.stringify(store.state.statuses),version=client.version;await store.flush(client);const state=await client.refreshState();store.applyServer(state);await client.refreshBank?.();
      if(version!==client.version){clearTransient();ensureSelected();}
      if(before!==JSON.stringify(store.state.statuses)){const p=position(),list=listed();if(p.completed&&list.length||p.selected&&!list.some(q=>q.id===p.selected)&&!(attempt&&statusOf(p.selected)==='wrong')){flushNote();clearTransient();p.completed=false;p.selected=list[0]?.id||null;ui.selectedQuestionId=p.selected;store.persist();}}
      for(const id of Object.keys(store.state.drafts)){if(store.queuedNote(id,store.draft(id))||store.rejectedNote(id,store.draft(id)))continue;noteTarget=id;flushNote();}loadError='';}
    catch{if(store.pendingOps&&root?.isConnected){const label=root.querySelector('.practice-sync');if(label)label.textContent='待同步 · '+store.pendingOps;}}
    finally{syncing=false;}
  }
  async function initialize(){
    if(initialized)return;initialized=true;
    void ensureToolchain().then(()=>{if(root?.isConnected)render();});
    try{await store.ready;await client.initialize();if(client.loaded)store.applyServer(client.state());await sync();}
    catch(error){loadError=error.code==='WORKSPACE_BANK_OUTDATED'?'当前后台尚未加载新版练习题库，请重启本机服务后刷新页面。':'题库暂不可用，请启动本机服务后重试。';}
    finally{loading=false;applyRequestedQuestion();render();}
    window.addEventListener('online',()=>sync().then(render));
    window.addEventListener('focus',()=>sync().then(render));
    window.addEventListener('pagehide',()=>{flushWritten();flushNote();savePosition();});
    setInterval(()=>{if(document.visibilityState==='visible'){const seq=store.state.serverSeq,version=client.version;sync().then(()=>{if(seq!==store.state.serverSeq||version!==client.version||pendingRender){if(root?.querySelector('.practice-select-trigger[aria-expanded=true]')){pendingRender=true;return;}pendingRender=false;render();}else if(current())updateNoteStatus(current().id);});}},5000);
  }
  function mount(node,nextView,params={}){
    const switched=root!==node||view!==nextView;
    if(switched){flushWritten();flushNote();clearTransient();}root=node;view=nextView;
    entry=nextView==='review'?'practice':params.page==='materials'?'materials':params.category?'practice':'hub';
    if(nextView==='review'){ui.reviewArea=['materials','algorithms','exams'].includes(params.area)?params.area:'materials';}
    const category=params.category;requestedQuestionId=params.questionId||null;
    if(category&&category!==ui.category){ui.category=category;clearTransient();}
    if(switched)ui.detailFullscreen=false;
    ensureSelected();applyRequestedQuestion();bind(node);render();store.persist();
    if(initialized&&!loading)sync().then(render);
  }
  return {initialize,beforeRender(){flushWritten();flushNote();savePosition();},afterRender(){},mountPractice(node,params={}){mount(node,'practice',params);},mountReview(node,params={}){mount(node,'review',params);},handleAction:act,handleInput,flushNote};
}
return{createPracticeView,CATEGORIES,SUBJECTS,STATUS_LABEL,TYPE_LABEL};
});
