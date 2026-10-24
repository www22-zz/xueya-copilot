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
  let root=null,view='practice',revealed=false,attempt=null,choice=null,shortDraft='',fillDraft='',noteTimer=null,noteTarget=null;
  let loading=true,loadError='',saving=new Set(),noteErrors=new Set(),syncing=false,initialized=false;
  const ui=store.state.ui;
  const button=(label,action,attrs='',style='button-outline')=>`<button type="button" class="button button-small ${style}" data-action="${action}" ${attrs}>${label}</button>`;
  const bank=()=>client.bank()||[];
  const filters=()=>view==='review'?ui.reviewFilters:store.filters();
  const progress=id=>store.state.statuses[id]||{};
  const statusOf=id=>progress(id).status||'pending';
  const positionKey=()=>view==='review'?'review':ui.category;
  const position=()=>ui.positions[positionKey()]||(ui.positions[positionKey()]={selected:null,scroll:0,completed:false});
  function matches(q,f){
    if(f.subject&&q.subject!==f.subject||f.difficulty&&q.difficulty!==f.difficulty||f.type&&q.type!==f.type||f.tag&&!(q.tags||[]).includes(f.tag))return false;
    const text=String(f.keyword||'').trim().toLowerCase();
    return !text||[q.id,q.leetcodeNumber||'',q.title,q.prompt,...(q.tags||[])].join(' ').toLowerCase().includes(text);
  }
  function listed(){
    const f=filters();let list=bank().filter(q=>matches(q,f)&&(view==='review'?statusOf(q.id)==='wrong':q.category===ui.category&&statusOf(q.id)===(f.status||'pending')));
    if(view==='review')list.sort((a,b)=>{
      const pa=progress(a.id),pb=progress(b.id),stamp=p=>[p.lastWrongAt||'',p.wrongEnteredAt||''].sort().pop();
      return (ui.wrongSort==='count'?(pb.wrongCount||0)-(pa.wrongCount||0):0)||stamp(pb).localeCompare(stamp(pa))||a.id.localeCompare(b.id);
    });
    return list;
  }
  function current(){return position().completed?null:bank().find(q=>q.id===position().selected)||null;}
  function clearTransient(){revealed=false;attempt=null;choice=null;shortDraft='';fillDraft='';}
  function ensureSelected(){if(!bank().length)return;const p=position();if(!p.completed&&!bank().some(q=>q.id===p.selected)){p.selected=listed()[0]?.id||null;}ui.selectedQuestionId=p.selected;}
  function savePosition(){const pane=root?.querySelector('.practice-list-pane');if(pane&&!loading)position().scroll=pane.scrollTop;store.persist();}
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
  function allTags(){return [...new Set(bank().filter(q=>view==='review'||q.category===ui.category).flatMap(q=>q.tags||[]))].sort();}
  function selectFilter(name,label,options){const f=filters();return `<select class="form-field" data-filter="${name}" aria-label="${label}"><option value="">全部${label}</option>${options.map(v=>{const [value,text]=Array.isArray(v)?v:[v,v];return `<option value="${e(value)}" ${f[name]===value?'selected':''}>${e(text)}</option>`;}).join('')}</select>`;}
  function toolbar(){
    const f=filters();const pending=store.pendingOps;const syncText=pending?'待同步'+(pending?` · ${pending}`:''):(client.online?'已同步':'本机服务未连接');
    return `<div class="practice-toolbar">${view==='review'?`<h2 class="practice-review-title">错题本</h2><div class="practice-statuses">${button('最近出错优先','wrong-sort','data-sort="recent"',ui.wrongSort==='recent'?'button-blue':'button-outline')}${button('错误次数最多','wrong-sort','data-sort="count"',ui.wrongSort==='count'?'button-blue':'button-outline')}</div>`:
      `<div class="practice-tabs" role="tablist">${CATEGORIES.map(([key,label])=>`<button type="button" class="practice-tab ${key===ui.category?'is-active':''}" data-action="category" data-category="${key}" role="tab" aria-selected="${key===ui.category}">${label}</button>`).join('')}</div><div class="practice-statuses">${['pending','mastered'].map(s=>button(STATUS_LABEL[s],'status',`data-status="${s}"`,f.status===s?'button-blue':'button-outline')).join('')}<a class="text-link" href="#space/review">错题本 →</a></div>`}
      <div class="practice-filters"><input type="search" class="form-field" data-filter="keyword" aria-label="搜索题目" placeholder="搜索题号、标题、题干、知识点" value="${e(f.keyword||'')}">
      ${selectFilter('subject','科目',SUBJECTS)}${view==='review'?'':selectFilter('difficulty','难度',DIFFICULTY[ui.category])}
      ${selectFilter('type','题型',Object.entries(TYPE_LABEL))}${selectFilter('tag','知识点',allTags())}${button('清除筛选','clear-filters')}</div>
      <div class="practice-modes">${view==='review'?'':button(f.status==='mastered'?'随机回顾':'随机一题','random')}${button('重试同步','retry-sync')}${store.error?button('重新登录','login'):''}<span class="practice-sync" role="status">${e(syncText)}${store.error?' · '+e(store.error):''}</span><span>${listed().length} 道题</span></div></div>`;
  }
  function statusChip(id){const status=statusOf(id);return `<span class="chip chip-${status}">${STATUS_LABEL[status]}</span>${progress(id).confidence==='fuzzy'&&status==='pending'?'<span class="chip chip-fuzzy">待巩固</span>':''}`;}
  function empty(){const complete=position().completed;return `<div class="practice-empty"><p>${view==='review'?'当前错题已清空。':complete?'当前筛选下的题目已刷完。':'当前筛选下没有题目。'}</p>${button('调整筛选','clear-filters')}${view==='review'?'':button('查看已掌握','show-mastered')}</div>`;}
  function listRows(){const list=listed();let topic='';return !list.length?empty():`<ul class="practice-list" role="listbox" aria-label="题目列表">${list.map(q=>{const heading=view!=='review'&&topic!==q.topic?`<li class="practice-topic" role="presentation">${e(q.category==='hot100'?(q.topic||q.subject):q.subject+' · '+(q.topic||q.tags[0]))}</li>`:'';topic=q.topic;return heading+`<li tabindex="0" class="practice-row ${q.id===position().selected?'is-active':''}" data-action="select" data-id="${e(q.id)}" role="option" aria-selected="${q.id===position().selected}"><span class="practice-row-id">${e(q.leetcodeNumber?'#'+q.leetcodeNumber:q.id)}</span><span class="practice-row-title">${e(q.title)}</span><span class="practice-row-meta">${e(q.difficulty)} · ${view==='review'?'错 '+(progress(q.id).wrongCount||0)+' 次':statusChip(q.id)}</span></li>`;}).join('')}</ul>`;}
  function noteBlock(q){
    const note=store.state.notes[q.id]||{text:'',revision:0,conflicts:[]},text=store.hasDraft(q.id)?store.draft(q.id):note.text;
    const state=saving.has(q.id)?'保存中':noteErrors.has(q.id)||store.rejectedNote(q.id,text)?'保存失败 · 草稿已保留':store.hasDraft(q.id)||store.pendingOps?'待同步':'已保存';
    return `<section class="practice-note"><header class="practice-note-head"><h3>随手记</h3><span class="practice-note-status" data-note-status role="status">${state}</span>${button(ui.notePreview?'编辑':'预览','note-mode')}</header>${ui.notePreview?`<div class="practice-note-preview rich-content">${globalThis.XueyaRich.render(text||'')}</div>`:`<textarea class="form-field practice-note-input" data-note="${e(q.id)}" rows="6" placeholder="记录你的思路与易错点">${e(text)}</textarea>`}
    ${(note.conflicts||[]).length?`<div class="practice-conflicts"><p>发现冲突副本，选择保留的内容：</p><pre>${e(note.text)}</pre>${button('保留当前','keep-server',`data-id="${e(q.id)}"`)}${note.conflicts.map((c,i)=>`<pre class="practice-conflict-preview">${e(c.text)}</pre>${button('使用副本 '+(i+1),'keep-conflict',`data-id="${e(q.id)}" data-index="${i}"`)}`).join('')}</div>`:''}</section>`;
  }
  function solutionBlock(q){if(q.type!=='code'||!revealed)return '';const language=ui.language||'python';return `<section class="practice-solution"><div class="practice-solution-tabs" role="tablist">${['python','cpp','java'].map(l=>button({python:'Python',cpp:'C++',java:'Java'}[l],'language',`data-language="${l}"`,l===language?'button-blue':'button-outline')).join('')}</div><pre class="practice-code"><code>${e(q.solutions[language])}</code></pre><p>时间复杂度 ${e(q.complexity.time)} · 空间复杂度 ${e(q.complexity.space)}</p><p><strong>易错点：</strong>${e(q.pitfalls)}</p></section>`;}
  function statusActions(q){const status=statusOf(q.id);if(status==='wrong')return button('已攻克','conquer',`data-id="${e(q.id)}"`,'button-blue')+button('移回待刷','reset',`data-id="${e(q.id)}"`);
    if(status==='mastered')return button('移回待刷','reset')+button('加入错题本','mark-wrong');
    return button('已掌握','master',q.type==='short'&&!revealed?'disabled':'','button-blue')+button('待巩固','fuzzy',q.type==='short'&&!revealed?'disabled':'')+button(q.type==='short'?'忘记':'加入错题本','mark-wrong',q.type==='short'&&!revealed?'disabled':'');}
  function detail(){
    const q=current();if(!q)return empty();
    let objective='';
    if(q.type==='single')objective=`<ul class="practice-options">${q.options.map((option,i)=>`<li><button type="button" class="practice-option ${choice===i?'is-chosen':''} ${revealed&&q.answer===i?'is-correct':''}" data-action="pick" data-index="${i}" ${revealed?'disabled':''}>${e(option)}</button></li>`).join('')}</ul>${!revealed?button('提交答案','submit-single',choice===null?'disabled':'','button-blue'):''}`;
    if(q.type==='fill')objective=`<div class="practice-fill"><input class="form-field" data-fill="${e(q.id)}" aria-label="填空答案" placeholder="填写答案" value="${e(attempt?.answer??fillDraft)}" ${revealed?'disabled':''}>${!revealed?button('提交答案','submit-fill','','button-blue'):''}</div>`;
    return `<article class="practice-detail"><header class="practice-detail-head">${button('返回列表','back','', 'button-outline practice-back')}<h2>${e(q.title)}</h2>${statusChip(q.id)}<p class="practice-detail-meta">${e(q.id)} · ${e(q.subject)} · ${e(q.difficulty)} · ${e((q.tags||[]).join(' / '))}</p></header><div class="practice-prompt">${e(q.prompt)}</div>
    ${(q.samples||[]).map(s=>`<pre class="practice-sample">输入：${e(s.input)}
输出：${e(s.output)}${s.explanation?'\n说明：'+e(s.explanation):''}</pre>`).join('')}${q.dataRange?`<p class="practice-range">数据范围：${e(q.dataRange)}</p>`:''}
    ${q.leetcodeUrl?`<a class="text-link" href="${e(q.leetcodeUrl)}" target="_blank" rel="noopener noreferrer">在力扣打开 ↗</a>`:''}
    ${(q.hints||[]).map((h,i)=>`<details class="practice-hints"><summary>提示 ${i+1}</summary><p>${e(h)}</p></details>`).join('')}${q.coreIdea?`<details class="practice-core"><summary>核心思路</summary><p>${e(q.coreIdea)}</p></details>`:''}
    ${objective}${q.type==='short'&&!revealed?`<textarea class="form-field" data-short rows="4" placeholder="先回忆一下（临时草稿）">${e(shortDraft)}</textarea>`:''}
    ${['short','code'].includes(q.type)&&!revealed?button(q.type==='short'?'查看参考答案与得分点':'查看完整题解','reveal'):''}
    ${revealed?`<section class="practice-answer">${attempt?`<p class="practice-result">${attempt.correct?'回答正确':'回答错误'} · 你的答案：${e(q.type==='single'?q.options[attempt.answer]:attempt.answer)}</p>`:''}${q.type==='short'?`<p><strong>一句话核心答案：</strong>${e(q.answer)}</p><h3>关键得分点</h3><ul>${q.keyPoints.map(x=>'<li>'+e(x)+'</li>').join('')}</ul><h3>常见追问</h3><ul>${q.followUps.map(x=>'<li>'+e(x)+'</li>').join('')}</ul>`:['single','fill'].includes(q.type)?`<p>正确答案：<strong>${e(q.type==='single'?q.options[q.answer]:q.answer)}</strong></p>`:''}<p class="practice-explanation">${e(q.explanation)}</p>${['single','fill'].includes(q.type)?button('重新作答','re-answer'):''}${q.type==='fill'&&attempt&&!attempt.correct?button('此答案也正确','also-correct'):''}</section>`:''}
    ${solutionBlock(q)}<div class="practice-actions">${statusActions(q)}${button('下一题','next')}</div>${noteBlock(q)}</article>`;
  }
  function render(){
    if(!root?.isConnected)return;ensureSelected();const focused=root.contains(document.activeElement)?document.activeElement:null;
    const filterName=focused?.dataset.filter,focusSelector=filterName?`[data-filter="${filterName}"]`:focused?.hasAttribute('data-note')?'[data-note]':focused?.hasAttribute('data-fill')?'[data-fill]':focused?.hasAttribute('data-short')?'[data-short]':null;
    const selection=focused?.selectionStart,selectionEnd=focused?.selectionEnd;
    const sameQuestion=root.dataset.renderedQuestion===(current()?.id||'');
    const openDetails=sameQuestion?[...root.querySelectorAll('details')].map(el=>el.open):[],detailScroll=sameQuestion?root.querySelector('.practice-detail-pane')?.scrollTop||0:0;
    root.dataset.renderedQuestion=current()?.id||'';
    root.innerHTML=`<div class="practice-module ${view==='review'?'practice-review':''} ${ui.detailFullscreen&&current()?'is-fullscreen':''}">${toolbar()}${loading?'<p role="status">正在加载题库…</p>':loadError?`<p role="alert">${e(loadError)}</p>`:''}<div class="practice-split"><section class="practice-list-pane">${listRows()}</section><section class="practice-detail-pane">${detail()}</section></div></div>`;
    root.querySelector('.practice-list-pane').scrollTop=position().scroll||0;
    root.querySelector('.practice-detail-pane').scrollTop=detailScroll;
    root.querySelectorAll('details').forEach((el,i)=>{el.open=Boolean(openDetails[i]);});
    if(focusSelector){const input=root.querySelector(focusSelector);input?.focus({preventScroll:true});if(selection!=null&&typeof input?.setSelectionRange==='function')try{input.setSelectionRange(selection,selectionEnd);}catch{}}
  }
  function updateNoteStatus(id){if(current()?.id!==id||!root?.isConnected)return;const label=root.querySelector('[data-note-status]');if(label)label.textContent=saving.has(id)?'保存中':noteErrors.has(id)||store.rejectedNote(id,store.draft(id))?'保存失败 · 草稿已保留':store.pendingOps||store.hasDraft(id)?'待同步':'已保存';}
  async function flushOps(){try{await store.flush(client);for(const id of [...noteErrors])if(!store.hasDraft(id))noteErrors.delete(id);}catch(error){if(error.code==='AUTH_REQUIRED')toast('请重新登录原账号后同步，本地记录已保留');}if(root?.isConnected){const label=root.querySelector('.practice-sync');if(label)label.textContent=store.pendingOps?'待同步 · '+store.pendingOps:'已同步';if(current())updateNoteStatus(current().id);}}
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
      if(action==='select'){select(id);return;}
      if(action==='category'){flushNote();savePosition();clearTransient();ui.detailFullscreen=false;const category=payload.category;ui.category=category;store.persist();navigate('#space/practice/'+({basic:'foundation',hot100:'hot100',interview:'interview'})[category]);render();return;}
      if(action==='status'||action==='show-mastered'){filters().status=action==='show-mastered'?'mastered':payload.status;resetSelection();render();return;}
      if(action==='clear-filters'){const f=filters(),status=f.status||'pending';for(const key of Object.keys(f))f[key]='';if(view!=='review')f.status=status;resetSelection();render();return;}
      if(action==='random'){ui.mode='random';const picked=randomPickLocal(listed());if(picked)select(picked.id,{manual:false});else {position().completed=true;render();}return;}
      if(action==='mode'){ui.mode=payload.mode;store.persist();return;}
      if(action==='next'){advance(listed());return;}
      if(action==='language'){ui.language=payload.language;store.persist();render();return;}
      if(action==='reveal'){revealed=true;render();return;}
      if(action==='pick'){choice=Number(payload.index);render();return;}
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
  function handleInput(event){const el=event.target;if(el.dataset.fill!==undefined){fillDraft=el.value;return true;}if(el.dataset.note!==undefined){onNoteInput(el.dataset.note,el.value);return true;}if(el.dataset.short!==undefined){shortDraft=el.value;return true;}if(el.dataset.filter!==undefined){flushNote();filters()[el.dataset.filter]=el.value;resetSelection();render();return true;}return false;}
  function bind(node){
    node.onclick=event=>{const el=event.target.closest('[data-action]');if(el&&node.contains(el)){event.preventDefault();event.stopPropagation();act(el.dataset.action,el.dataset);}};
    node.oninput=event=>{if(event.target.tagName!=='SELECT')handleInput(event);};
    node.onchange=event=>{if(event.target.tagName==='SELECT')handleInput(event);};
    node.onkeydown=event=>{if(event.target.classList.contains('practice-row')&&['Enter',' '].includes(event.key)){event.preventDefault();act('select',event.target.dataset);}};
    node.addEventListener('scroll',event=>{if(event.target.classList?.contains('practice-list-pane')){position().scroll=event.target.scrollTop;store.persist();}},true);
  }
  async function sync(){
    if(syncing)return;syncing=true;
    try{const before=JSON.stringify(store.state.statuses);await store.flush(client);const state=await client.refreshState();store.applyServer(state);
      if(before!==JSON.stringify(store.state.statuses)){const p=position(),list=listed();if(p.completed&&list.length||p.selected&&!list.some(q=>q.id===p.selected)&&!(attempt&&statusOf(p.selected)==='wrong')){flushNote();clearTransient();p.completed=false;p.selected=list[0]?.id||null;ui.selectedQuestionId=p.selected;store.persist();}}
      for(const id of Object.keys(store.state.drafts)){if(store.queuedNote(id,store.draft(id))||store.rejectedNote(id,store.draft(id)))continue;noteTarget=id;flushNote();}loadError='';}
    catch{if(store.pendingOps&&root?.isConnected){const label=root.querySelector('.practice-sync');if(label)label.textContent='待同步 · '+store.pendingOps;}}
    finally{syncing=false;}
  }
  async function initialize(){
    if(initialized)return;initialized=true;
    try{await store.ready;await client.initialize();if(client.loaded)store.applyServer(client.state());await sync();}
    catch{loadError='题库暂不可用，请启动本机服务后重试。';}
    finally{loading=false;render();}
    window.addEventListener('online',()=>sync().then(render));
    window.addEventListener('focus',()=>sync().then(render));
    window.addEventListener('pagehide',()=>{flushNote();savePosition();});
    setInterval(()=>{if(document.visibilityState==='visible'){const seq=store.state.serverSeq;sync().then(()=>{if(seq!==store.state.serverSeq)render();else if(current())updateNoteStatus(current().id);});}},5000);
  }
  function mount(node,nextView,params={}){
    const switched=root!==node||view!==nextView;
    if(switched){flushNote();clearTransient();}root=node;view=nextView;
    if(params.category&&params.category!==ui.category){ui.category=params.category;clearTransient();}
    if(switched)ui.detailFullscreen=false;
    ensureSelected();bind(node);render();store.persist();
  }
  return {initialize,beforeRender(){flushNote();savePosition();},afterRender(){},mountPractice(node,params={}){mount(node,'practice',params);},mountReview(node,params={}){mount(node,'review',params);},handleAction:act,handleInput,flushNote};
}
return{createPracticeView,CATEGORIES,SUBJECTS,STATUS_LABEL,TYPE_LABEL};
});
