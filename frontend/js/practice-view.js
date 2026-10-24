/* 练习 / 复习 views: fixed bank list, status flow, objective answering, per-question notes. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaPracticeView=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const CATEGORIES=[['hot100','Hot 100'],['basic','基础题'],['interview','面试题']];
const SUBJECTS=['数据结构与算法','计算机网络','操作系统','数据库','面向对象基础'];
const STATUS_LABEL={pending:'待刷',mastered:'已掌握',wrong:'错题本'};
const TYPE_LABEL={code:'算法',single:'单选',fill:'填空',short:'面试'};
const DIFFICULTY={hot100:['简单','中等','困难'],basic:['基础','进阶','挑战'],interview:['基础','进阶','挑战']};
const e=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const esc=s=>e(s);
function createPracticeView({store,client,toast=()=>{},navigate=()=>{}}={}){
  let root=null,view='practice',revealed=new Set(),draftTimer=null,saving=false,lastSyncedNote='',pendingAutoNext=false;
  function bank(){return client.bank()||[];}
  function filters(){return store.filters();}
  function progress(id){return store.state.statuses[id]||null;}
  function statusOf(id){return (progress(id)||{status:'pending'}).status;}
  function matches(q,f){
    if(f.subject&&q.subject!==f.subject)return false;
    if(f.difficulty&&q.difficulty!==f.difficulty)return false;
    if(f.type&&q.type!==f.type)return false;
    if(f.tag&&!q.tags.includes(f.tag))return false;
    const keyword=String(f.keyword||'').trim().toLowerCase();
    if(keyword){
      const hay=[q.id,q.title,q.prompt,(q.tags||[]).join(' ')].join(' ').toLowerCase();
      if(!hay.includes(keyword))return false;
    }
    return true;
  }
  /* PRD 4.4: filters only hide rows. The bank array order is the fixed order. */
  function listed(){
    const category=store.state.ui.category,f=filters(),status=f.status||store.state.ui.status||'';
    return bank().filter(q=>q.category===category&&matches(q,f)&&(!status||statusOf(q.id)===status));
  }
  function allTags(){
    const set=new Set();
    for(const q of bank())if(q.category===store.state.ui.category)for(const t of q.tags||[])set.add(t);
    return [...set].sort();
  }
  function current(){
    const id=store.state.ui.selectedQuestionId;
    return bank().find(q=>q.id===id)||listed()[0]||null;
  }
  function select(id,{scroll=true}={}){
    store.state.ui.selectedQuestionId=id;
    if(scroll)store.state.ui.listScroll=0;
    flushNote();
    store.persist();draw();
  }
  function nextInList(){
    const list=listed(),id=store.state.ui.selectedQuestionId;
    const index=list.findIndex(q=>q.id===id);
    return index>=0&&index+1<list.length?list[index+1]:(list.length?list[0]:null);
  }
  function advance(){
    const target=nextInList();
    if(target)select(target.id,{scroll:false});
  }
  function showEmpty(message,actions=''){
    return `<div class="practice-empty"><p>${e(message)}</p>${actions}</div>`;
  }
  function statusChip(id){
    const row=progress(id);
    const label=STATUS_LABEL[(row||{status:'pending'}).status];
    const fuzzy=row&&row.confidence==='fuzzy'?'<span class="chip chip-fuzzy">待巩固</span>':'';
    return `<span class="chip chip-${e((row||{status:'pending'}).status)}">${e(label)}</span>${fuzzy}`;
  }
  function listRows(){
    const list=listed();
    if(!list.length)return showEmpty('当前筛选下没有题目。','<button type="button" class="button button-outline" data-action="clear-filters">调整筛选</button>');
    return `<ul class="practice-list" role="listbox">${list.map(q=>{
      const active=q.id===(current()||{}).id;
      return `<li class="practice-row${active?' is-active':''}" data-action="select" data-id="${e(q.id)}" role="option" aria-selected="${active}">
        <span class="practice-row-id">${e(q.id)}</span>
        <span class="practice-row-title">${e(q.title)}</span>
        <span class="practice-row-meta">${e(q.difficulty)}${statusChip(q.id)}</span>
      </li>`;}).join('')}</ul>`;
  }
  function toolbar(){
    const category=store.state.ui.category,f=filters();
    return `<div class="practice-toolbar">
      <div class="practice-tabs" role="tablist">${CATEGORIES.map(([key,label])=>
        `<button type="button" class="practice-tab${key===category?' is-active':''}" role="tab" aria-selected="${key===category}" data-action="category" data-category="${key}">${e(label)}</button>`).join('')}
      </div>
      <div class="practice-statuses">
        ${['pending','mastered','wrong'].map(s=>`<button type="button" class="button button-small ${(f.status||'')===s?'button-blue':'button-outline'}" data-action="status" data-status="${s}">${e(STATUS_LABEL[s])}</button>`).join('')}
        <button type="button" class="button button-small button-outline" data-action="status" data-status="">全部</button>
      </div>
      <div class="practice-filters">
        <input class="form-field" type="search" data-filter="keyword" value="${e(f.keyword)}" placeholder="搜索题号、标题、题干、知识点" aria-label="搜索题目">
        <select class="form-field" data-filter="subject" aria-label="科目"><option value="">全部科目</option>${SUBJECTS.map(s=>`<option${f.subject===s?' selected':''}>${e(s)}</option>`).join('')}</select>
        <select class="form-field" data-filter="difficulty" aria-label="难度"><option value="">全部难度</option>${(DIFFICULTY[category]||[]).map(d=>`<option${f.difficulty===d?' selected':''}>${e(d)}</option>`).join('')}</select>
        <select class="form-field" data-filter="type" aria-label="题型"><option value="">全部题型</option>${['single','fill','code','short'].map(t=>`<option value="${t}"${f.type===t?' selected':''}>${e(TYPE_LABEL[t]||t)}</option>`).join('')}</select>
        <select class="form-field" data-filter="tag" aria-label="知识点"><option value="">全部知识点</option>${allTags().map(t=>`<option${f.tag===t?' selected':''}>${e(t)}</option>`).join('')}</select>
        <button type="button" class="button button-small button-outline" data-action="clear-filters">清除筛选</button>
      </div>
      <div class="practice-modes">
        <button type="button" class="button button-small ${store.state.ui.mode==='order'?'button-blue':'button-outline'}" data-action="mode" data-mode="order">顺序练习</button>
        <button type="button" class="button button-small ${store.state.ui.mode==='random'?'button-blue':'button-outline'}" data-action="random">${store.state.ui.category==='hot100'?'随机一题':'随机一题'}</button>
      </div>
    </div>`;
  }
  function optionsBlock(q,submitted){
    const row=progress(q.id),revealedNow=revealed.has(q.id)||submitted;
    if(q.type==='single')return `<ul class="practice-options">${q.options.map((option,index)=>{
      const chosen=row&&row.lastSelected===index;
      const correct=revealedNow&&index===q.answer;
      return `<li><button type="button" class="practice-option${chosen?' is-chosen':''}${correct?' is-correct':''}" data-action="pick" data-id="${e(q.id)}" data-index="${index}">${e(option)}</button></li>`;}).join('')}</ul>`;
    if(q.type==='fill')return `<div class="practice-fill"><input class="form-field" data-fill="${e(q.id)}" placeholder="填写答案" aria-label="填空答案">
      <button type="button" class="button button-blue" data-action="submit-fill" data-id="${e(q.id)}">提交</button></div>`;
    return '';
  }
  function solutionBlock(q){
    if(q.type!=='code')return '';
    const language=store.state.ui.language||'python';
    const code=(q.solutions||{})[language]||'';
    return `<section class="practice-solution">
      <div class="practice-solution-tabs" role="tablist">${['python','cpp','java'].map(l=>
        `<button type="button" class="practice-tab${l===language?' is-active':''}" role="tab" data-action="language" data-language="${l}">${e({python:'Python',cpp:'C++',java:'Java'}[l])}</button>`).join('')}
      </div>
      <pre class="practice-code"><code>${e(code)}</code></pre>
      <p class="practice-complexity">时间复杂度 ${e(q.complexity&&q.complexity.time)} · 空间复杂度 ${e(q.complexity&&q.complexity.space)}</p>
      <p class="practice-pitfalls"><strong>易错点：</strong>${e(q.pitfalls)}</p>
      ${q.leetcodeUrl?`<p><a class="text-link" href="${e(q.leetcodeUrl)}" target="_blank" rel="noopener noreferrer">在力扣打开</a></p>`:''}
    </section>`;
  }
  function noteBlock(q){
    const note=store.state.notes[q.id]||{text:'',revision:0,conflicts:[]};
    const draft=store.draft(q.id);
    const text=draft||note.text||'';
    return `<section class="practice-note">
      <header class="practice-note-head"><h3>随手记</h3>
        <span class="practice-note-status" data-note-status>${saving?'保存中':(store.offline?'待同步':'已保存')}</span>
        <button type="button" class="button button-small button-outline" data-action="note-mode">${store.state.ui.notePreview?'编辑':'预览'}</button>
      </header>
      ${store.state.ui.notePreview
        ?`<div class="practice-note-preview rich-content">${e(text).replace(/\n/g,'<br>')}</div>`
        :`<textarea class="form-field practice-note-input" data-note="${e(q.id)}" rows="6" placeholder="记录你的思路、易错点、疑问……">${e(text)}</textarea>`}
      ${(note.conflicts||[]).length?`<div class="practice-conflicts"><p>发现冲突副本，请选择保留哪一份：</p>
        <button type="button" class="button button-small button-outline" data-action="keep-server" data-id="${e(q.id)}">保留当前</button>
        ${(note.conflicts||[]).map((c,i)=>`<button type="button" class="button button-small button-outline" data-action="keep-conflict" data-id="${e(q.id)}" data-index="${i}">使用副本 ${i+1}</button>`).join('')}
        <pre class="practice-conflict-preview">${e((note.conflicts||[]).map((c,i)=>`副本 ${i+1}：\n${c.text}`).join('\n\n'))}</pre></div>`:''}
    </section>`;
  }
  function detail(){
    const q=current();
    if(!q)return showEmpty('当前筛选下的题目已刷完。','<button type="button" class="button button-outline" data-action="clear-filters">调整筛选</button><button type="button" class="button button-outline" data-action="show-mastered">查看已掌握</button>');
    const row=progress(q.id),submitted=revealed.has(q.id),isWrong=row&&row.status==='wrong';
    return `<article class="practice-detail">
      <header class="practice-detail-head">
        <button type="button" class="button button-small button-outline practice-back" data-action="back">返回列表</button>
        <h2>${e(q.title)}</h2>
        ${statusChip(q.id)}
        <p class="practice-detail-meta">${e(q.id)} · ${e(q.subject)} · ${e(q.difficulty)} · ${e(TYPE_LABEL[q.type]||q.type)}${(q.tags||[]).length?' · '+e(q.tags.join(' / ')):''}</p>
      </header>
      <div class="practice-prompt">${e(q.prompt)}</div>
      ${(q.samples||[]).length?`<div class="practice-samples">${q.samples.map(s=>`<pre class="practice-sample"><code>输入：${e(s.input)}\n输出：${e(s.output)}${s.explanation?'\n说明：'+e(s.explanation):''}</code></pre>`).join('')}</div>`:''}
      ${q.dataRange?`<p class="practice-range"><strong>数据范围：</strong>${e(q.dataRange)}</p>`:''}
      ${(q.hints||[]).length?`<details class="practice-hints"><summary>渐进提示</summary><ol>${q.hints.map(h=>`<li>${e(h)}</li>`).join('')}</ol></details>`:''}
      ${q.coreIdea?`<details class="practice-core"><summary>核心思路</summary><p>${e(q.coreIdea)}</p></details>`:''}
      ${optionsBlock(q,submitted)}
      ${q.type==='short'?`<div class="practice-short"><textarea class="form-field" data-short="${e(q.id)}" rows="4" placeholder="先自己回忆一下（临时草稿，切换题目后清空）">${e(store.state.ui.shortDraft||'')}</textarea>
        <button type="button" class="button button-outline" data-action="reveal" data-id="${e(q.id)}">展开参考答案</button></div>`:''}
      ${q.type==='code'?`<button type="button" class="button button-outline" data-action="reveal" data-id="${e(q.id)}">查看提示与题解</button>`:''}
      ${submitted||q.type==='code'||q.type==='short'?`<section class="practice-answer">
        ${q.type==='fill'?`<p>正确答案：<strong>${e(q.answer)}</strong></p>`:''}
        ${q.type==='short'?`<p><strong>一句话核心答案：</strong>${e(q.answer)}</p>
          <ul>${(q.keyPoints||[]).map(p=>`<li>${e(p)}</li>`).join('')}</ul>
          <p><strong>常见追问：</strong></p><ul>${(q.followUps||[]).map(f=>`<li>${e(f)}</li>`).join('')}</ul>`:''}
        ${q.type==='single'&&submitted?`<p>正确答案：<strong>${e((q.options||[])[q.answer])}</strong></p>`:''}
        <p class="practice-explanation">${e(q.explanation)}</p>
        ${isWrong&&q.type==='fill'?`<button type="button" class="button button-outline" data-action="also-correct" data-id="${e(q.id)}">此答案也正确</button>`:''}
        ${(isWrong&&q.type!=='fill')?`<button type="button" class="button button-outline" data-action="re-answer" data-id="${e(q.id)}">重新作答</button>`:''}
      </section>`:''}
      ${solutionBlock(q)}
      ${statusActions(q)}
      ${noteBlock(q)}
    </article>`;
  }
  function statusActions(q){
    const status=statusOf(q.id);
    if(view==='review'){
      return `<div class="practice-actions">
        <button type="button" class="button button-blue" data-action="conquer" data-id="${e(q.id)}">已攻克</button>
        <button type="button" class="button button-outline" data-action="reset" data-id="${e(q.id)}">移回待刷</button>
      </div>`;
    }
    if(status==='pending')return `<div class="practice-actions">
      <button type="button" class="button button-blue" data-action="master" data-id="${e(q.id)}">已掌握</button>
      <button type="button" class="button button-outline" data-action="fuzzy" data-id="${e(q.id)}">待巩固</button>
      <button type="button" class="button button-outline" data-action="mark-wrong" data-id="${e(q.id)}">${q.type==='short'?'忘记':'加入错题本'}</button>
    </div>`;
    if(status==='wrong')return `<div class="practice-actions">
      <button type="button" class="button button-blue" data-action="conquer" data-id="${e(q.id)}">已攻克</button>
      <button type="button" class="button button-outline" data-action="reset" data-id="${e(q.id)}">移回待刷</button>
    </div>`;
    return `<div class="practice-actions">
      <button type="button" class="button button-outline" data-action="reset" data-id="${e(q.id)}">移回待刷</button>
    </div>`;
  }
  function reviewToolbar(){
    const f=filters();
    return `<div class="practice-toolbar">
      <h2 class="practice-review-title">错题本</h2>
      <div class="practice-statuses">
        <button type="button" class="button button-small ${store.state.ui.wrongSort==='recent'?'button-blue':'button-outline'}" data-action="wrong-sort" data-sort="recent">最近出错优先</button>
        <button type="button" class="button button-small ${store.state.ui.wrongSort==='count'?'button-blue':'button-outline'}" data-action="wrong-sort" data-sort="count">错误次数最多</button>
      </div>
      <div class="practice-filters">
        <select class="form-field" data-filter="type" aria-label="题型"><option value="">全部题型</option>${['single','fill','code','short'].map(t=>`<option value="${t}"${f.type===t?' selected':''}>${e(TYPE_LABEL[t]||t)}</option>`).join('')}</select>
        <select class="form-field" data-filter="subject" aria-label="科目"><option value="">全部科目</option>${SUBJECTS.map(s=>`<option${f.subject===s?' selected':''}>${e(s)}</option>`).join('')}</select>
        <select class="form-field" data-filter="tag" aria-label="算法标签"><option value="">全部标签</option>${allTags().map(t=>`<option${f.tag===t?' selected':''}>${e(t)}</option>`).join('')}</select>
        <button type="button" class="button button-small button-outline" data-action="clear-filters">清除筛选</button>
      </div>
    </div>`;
  }
  function reviewList(){
    const f=filters();
    const rows=bank().filter(q=>statusOf(q.id)==='wrong'&&matches(q,f))
      .map(q=>[q.id,{...progress(q.id),question:q}]);
    const ordered=sortRows(rows,store.state.ui.wrongSort);
    if(!ordered.length)return showEmpty('当前错题已清空。');
    return `<ul class="practice-list" role="listbox">${ordered.map(([id,row])=>{
      const q=row.question,active=q.id===(current()||{}).id;
      return `<li class="practice-row${active?' is-active':''}" data-action="select" data-id="${e(q.id)}" role="option" aria-selected="${active}">
        <span class="practice-row-id">${e(q.id)}</span>
        <span class="practice-row-title">${e(q.title)}</span>
        <span class="practice-row-meta">错 ${e(row.wrongCount||0)} 次 · ${e(q.difficulty)}</span>
      </li>`;}).join('')}</ul>`;
  }
  function sortRows(rows,mode){
    const stamp=item=>item[1].lastWrongAt||item[1].wrongEnteredAt||'';
    const ordered=[...rows].sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:0);
    ordered.sort((a,b)=>stamp(a)<stamp(b)?1:stamp(a)>stamp(b)?-1:0);
    if(mode==='count')ordered.sort((a,b)=>(b[1].wrongCount||0)-(a[1].wrongCount||0));
    return ordered;
  }
  function draw(){
    if(!root)return;
    const fullscreen=store.state.ui.detailFullscreen&&current();
    root.innerHTML=`<div class="practice-module${fullscreen?' is-fullscreen':''}">${toolbar()}
      <div class="practice-split">
        <section class="practice-list-pane">${listRows()}</section>
        <section class="practice-detail-pane">${detail()}</section>
      </div></div>`;
  }
  function drawReview(){
    if(!root)return;
    const fullscreen=store.state.ui.detailFullscreen&&current();
    root.innerHTML=`<div class="practice-module practice-review${fullscreen?' is-fullscreen':''}">${reviewToolbar()}
      <div class="practice-split">
        <section class="practice-list-pane">${reviewList()}</section>
        <section class="practice-detail-pane">${detail()}</section>
      </div></div>`;
  }
  function render(){view==='review'?drawReview():draw();}
  /* --- notes --- */
  function flushNote(){
    if(!draftTimer)return;
    clearTimeout(draftTimer);draftTimer=null;
    const id=store.state.ui.selectedQuestionId;
    if(!id)return;
    const text=store.draft(id),note=store.state.notes[id]||{revision:0};
    if(text===(lastSyncedNote||note.text||''))return;
    saving=true;render();
    store.pushNote(id,text,note.revision||0);
    store.flush(client).then(()=>{saving=false;lastSyncedNote=text;store.setDraft(id,'');render();})
      .catch(()=>{saving=false;render();toast('保存失败，草稿已保留，请稍后重试');});
  }
  function onNoteInput(value){
    const id=store.state.ui.selectedQuestionId;if(!id)return;
    store.setDraft(id,value);
    clearTimeout(draftTimer);
    draftTimer=setTimeout(()=>{draftTimer=null;flushNote();},1000);
  }
  /* --- answering --- */
  function answer(id,selected){
    const q=bank().find(x=>x.id===id);if(!q)return;
    const correct=store.judgeAnswer(q,selected);
    revealed.add(id);
    store.push('answer',id,{result:correct?'correct':'wrong',questionType:q.type,selected});
    if(!correct&&['single','fill'].includes(q.type))toast('已自动加入错题本');
    flushOps();
    render();
  }
  function flushOps(){
    store.flush(client).catch(()=>{});
  }
  function act(action,payload={}){
    const id=payload.id||store.state.ui.selectedQuestionId;
    const q=bank().find(x=>x.id===id);
    try{
      if(action==='select'){select(id);return true;}
      if(action==='category'){store.state.ui.category=payload.category;store.state.ui.status='';store.state.ui.selectedQuestionId=null;store.persist();render();return true;}
      if(action==='status'){store.state.ui.status=payload.status;store.filters().status=payload.status;store.persist();const list=listed();store.state.ui.selectedQuestionId=list.length?list[0].id:null;render();return true;}
      if(action==='clear-filters'){store.filters().keyword='';store.filters().subject='';store.filters().tag='';store.filters().difficulty='';store.filters().type='';store.filters().status='';store.state.ui.status='';store.persist();render();return true;}
      if(action==='show-mastered'){store.filters().status='mastered';store.state.ui.status='mastered';store.persist();render();return true;}
      if(action==='mode'){store.state.ui.mode=payload.mode;store.persist();render();return true;}
      if(action==='random'){
        const pool=listed().filter(x=>statusOf(x.id)==='pending');
        const picked=randomPickLocal(pool);
        if(!picked){toast('当前筛选下的题目已刷完');render();return true;}
        select(picked.id);return true;
      }
      if(action==='language'){store.state.ui.language=payload.language;store.persist();render();return true;}
      if(action==='reveal'){revealed.add(id);render();return true;}
      if(action==='pick'){answer(id,Number(payload.index));return true;}
      if(action==='submit-fill'){
        const input=root.querySelector(`[data-fill="${CSS.escape(id)}"]`);
        answer(id,input?input.value:'');return true;
      }
      if(action==='re-answer'){revealed.delete(id);render();return true;}
      if(action==='also-correct'){
        store.push('correct',id,{questionType:'fill'});flushOps();toast('已改为正确，移回待刷');render();return true;
      }
      if(action==='note-mode'){store.state.ui.notePreview=!store.state.ui.notePreview;store.persist();render();return true;}
      if(action==='keep-server'){flushNote();const note=store.state.notes[id];if(note)store.chooseConflict(id,note.text);render();return true;}
      if(action==='keep-conflict'){const note=store.state.notes[id];const copy=(note&&note.conflicts||[])[Number(payload.index)];if(copy)store.chooseConflict(id,copy.text);render();return true;}
      if(action==='back'){store.state.ui.detailFullscreen=false;store.persist();render();return true;}
      if(['master','conquer','fuzzy','mark-wrong','reset'].includes(action)){
        store.push(action,id,{questionType:q&&q.type});flushOps();
        /* PRD 5.4: only 已掌握 auto-advances; 待巩固 / 加入错题本 / 忘记 stay put. */
        if(action==='master'){advance();}else if(action==='conquer'&&view==='review'){
          const next=reviewNext();if(next)select(next.id);else render();
        }else render();
        return true;
      }
      if(action==='wrong-sort'){store.state.ui.wrongSort=payload.sort;store.persist();render();return true;}
    }catch(error){toast(error.message||'操作未完成');render();return true;}
    return false;
  }
  function randomPickLocal(pool){
    if(!pool.length)return null;
    const last=store.state.ui.selectedQuestionId;
    const items=pool.length>1?pool.filter(x=>x.id!==last):pool;
    const weights=items.map(x=>((progress(x.id)||{}).confidence==='fuzzy')?3:1);
    const total=weights.reduce((a,b)=>a+b,0);
    let roll=Math.random()*total;
    for(let i=0;i<items.length;i++){roll-=weights[i];if(roll<0)return items[i];}
    return items[items.length-1];
  }
  function reviewNext(){
    const f=filters();
    const rows=bank().filter(q=>statusOf(q.id)==='wrong'&&matches(q,f)).map(q=>[q.id,{...progress(q.id)}]);
    const ordered=sortRows(rows,store.state.ui.wrongSort);
    return ordered.length?ordered[0][1]&&bank().find(q=>q.id===ordered[0][0]):null;
  }
  return {
    beforeRender(){},
    afterRender(){},
    /* Load the fixed bank once; safe to call again and to call before any mount. */
    async initialize(){
      if(!client)return {count:0};
      try{
        await client.initialize();
        if(store&&client.state){
          const state=client.state();
          if(state&&state.statuses&&Object.keys(state.statuses).length)store.applyServer(state);
        }
        if(store&&store.flush)await store.flush(client).catch(()=>{});
      }catch(error){toast(error.message||'题库暂不可用');}
      return {count:(client.bank()||[]).length};
    },
    mountPractice(node,params={}){root=node;view='practice';if(params.category)store.state.ui.category=params.category;if(params.id)store.state.ui.selectedQuestionId=params.id;store.state.ui.detailFullscreen=!!params.fullscreen;render();},
    mountReview(node,params={}){root=node;view='review';if(params.id)store.state.ui.selectedQuestionId=params.id;render();},
    handleAction(action,payload){return act(action,payload);},
    handleInput(event){
      const target=event.target;
      if(target.dataset&&target.dataset.note!==undefined){onNoteInput(target.value);return true;}
      if(target.dataset&&target.dataset.filter!==undefined){
        filters()[target.dataset.filter]=target.value;
        if(target.dataset.filter!=='keyword'){const list=listed();store.state.ui.selectedQuestionId=list.length?list[0].id:null;}
        store.persist();if(target.dataset.filter==='keyword')render();
        return true;
      }
      return false;
    },
    flushNote,
  };
}
return{createPracticeView,CATEGORIES,SUBJECTS,STATUS_LABEL,TYPE_LABEL};
});
