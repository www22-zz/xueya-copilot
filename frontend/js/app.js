(() => {
  'use strict';
  const L=window.XueyaLearning,$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)],KEY='xueya-copilot-state-v2';
  const icons=()=>window.XueyaIcons?.();
  const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon=name=>`<span data-icon="${name}"></span>`;
  function read(key){try{return JSON.parse(localStorage.getItem(key)||'null');}catch{return null;}}
  const old=read('xueya-copilot-state-v1'),saved=read(KEY);
  const migrated=old?.documents?.filter(d=>!['doc-1','doc-2','doc-3'].includes(d.id)).map(d=>({...d,status:'内容待解析',meta:'旧版资料记录 · 请重新上传文本以检索'}))||[];
  const state={documents:saved?.documents||[...L.documents,...migrated],cards:saved?.cards||[],messages:saved?.messages||[],records:saved?.records||[],examDate:L.validDate(saved?.examDate)?saved.examDate:L.addDays(L.today(),21),minutes:saved?.minutes||30,completed:saved?.completed||{},plan:saved?.plan||[],mode:'ask',view:'overview',pending:false,quizIndex:0,quizFilter:'all',selected:null,submitted:false,draft:'',activeSource:null,libraryQuery:'',cardQuery:''};
  if(!state.plan.length||state.plan[0]?.date!==L.today())state.plan=L.buildPlan(state.examDate,state.minutes,state.records);
  const allSources=()=>[...L.sources,...state.documents.flatMap(d=>Array.isArray(d.chunks)?d.chunks:[])];
  function persist(){try{localStorage.setItem(KEY,JSON.stringify({documents:state.documents,cards:state.cards,messages:state.messages.slice(-24),records:state.records.slice(-300),examDate:state.examDate,minutes:state.minutes,completed:state.completed,plan:state.plan}));return true;}catch{toast('浏览器存储空间不足。本次记录未保存，请减少上传资料。');return false;}}
  let toastTimer;function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),3500);}
  const {titles,renders,documentRows,cardRows,currentQuestions}=window.XueyaViews.createViews({state,L,e,icon});
  const chatService=window.XueyaChat.createChatService();
  const libraryService=window.XueyaLibrary;
  function render(){const pool=currentQuestions();if(state.quizIndex>=pool.length)state.quizIndex=0;$('#spaceContent').innerHTML=renders[state.view]();$('#documentCount').textContent=state.documents.length;icons();}
  let initialRoute=true;function route(){const parts=location.hash.replace(/^#/,'').split('/');const space=parts[0]==='space';$('#homePage').hidden=space;$('#spacePage').hidden=!space;document.body.classList.toggle('in-space',space);if(space){state.view=titles[parts[1]]?parts[1]:'overview';$$('[data-view]').forEach(a=>{a.classList.toggle('active',a.dataset.view===state.view);a.dataset.view===state.view?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current');});render();document.title=`${titles[state.view]} · 学涯 Copilot`;if(!initialRoute){scrollTo({top:0,behavior:'instant'});$('#spaceContent').focus({preventScroll:true});}}else{document.title='学涯 Copilot — 让知识，真正连起来';if(['possibilities','evidence','rhythm'].includes(parts[0]))requestAnimationFrame(()=>document.getElementById(parts[0]).scrollIntoView());else if(!initialRoute)scrollTo({top:0,behavior:'instant'});}initialRoute=false;}
  function sourceById(id){return allSources().find(s=>s.id===id)||state.messages.flatMap(m=>m.sources||[]).find(s=>s.id===id)||state.cards.flatMap(c=>c.sources||[]).find(s=>s.id===id);}
  function openSource(source){if(!source)return;state.activeSource=source;$('#sourceContent').innerHTML=`<div class="source-content-body"><h2>${e(source.title)}</h2><p class="source-location">${e(source.location)}</p><blockquote class="source-quote">${e(source.quote)}</blockquote><p class="source-footnote">${source.sample?'这是一段内置课程示例，用于体验原文引用流程。':'这段文本读取自你在当前浏览器添加的资料。'}</p></div>`;$('#sourceSave').hidden=!source.quote;icons();$('#sourceDialog').showModal();}
  function saveCard(title,text,sources){if(state.cards.some(c=>c.text===text)){toast('这段重点已经在知识卡片里了。');return;}state.cards.unshift({id:crypto.randomUUID(),title:title.slice(0,80),text,sources,createdAt:new Date().toISOString()});if(persist())toast('理解，留下来了。已保存知识卡片。');}
  async function ask(question){
    const clean=question.trim();if(!clean||state.pending)return;
    const previous=state.messages.slice(-8).map(m=>({role:m.role==='ai'?'assistant':'user',content:m.text}));
    const prior=[...state.messages].reverse().find(m=>m.role==='ai'&&m.sources?.length);
    const request={question:clean,mode:state.mode,sources:allSources(),history:previous,previousSources:prior?.sources||[]};
    state.draft='';state.pending=true;state.messages.push({role:'user',text:clean});persist();
    if(state.view!=='chat')location.hash='space/chat';else render();
    const result=await chatService.ask(request);
    $('#engineStatus').textContent=result.online?'MiMo 在线':'本地检索模式';
    $('#engineStatus').classList.toggle('online',result.online);
    state.messages.push({role:'ai',text:result.answer,sources:result.sources,engine:result.engine,title:clean,createdAt:new Date().toISOString()});
    state.pending=false;persist();
    if(state.view==='chat'&&!$('#spacePage').hidden){render();const last=$$('#chatThread .message').at(-1);last?.scrollIntoView({block:'nearest',behavior:'instant'});}
    else toast('回答已准备好，可在资料问答中查看。');
  }
  let uploading=false;
  async function upload(files){
    if(uploading)return;uploading=true;let added=0;
    try{
      for(const file of files){
        if(state.documents.some(d=>d.name===file.name&&d.bytes===file.size)){toast(`${file.name} 已经添加过。`);continue;}
        let doc;
        try{doc=await libraryService.prepareDocument(file);}catch(error){if(error.code==='INVALID_DOCUMENT'){toast(error.message);continue;}throw error;}
        state.documents.unshift(doc);if(!persist()){state.documents.shift();break;}added++;
      }
      if(state.view==='library')render();
      if(added)toast(`已添加 ${added} 份资料${files.some(f=>/\.(pdf|docx)$/i.test(f.name))?'，PDF / DOCX 正文待解析':''}。`);
    }catch{toast('文件读取失败，请重新选择文件。');}finally{uploading=false;}
  }
  function searchResults(query){const q=query.trim().toLowerCase();const items=Object.entries(titles).map(([view,title])=>({title,type:'页面',view}));state.documents.forEach(d=>items.push({title:d.name,type:'资料',document:d.id}));state.cards.forEach(c=>items.push({title:c.title,type:'卡片',view:'cards',query:c.title}));const found=items.filter(item=>!q||item.title.toLowerCase().includes(q)).slice(0,12);$('#searchResults').innerHTML=found.length?found.map(item=>`<button type="button" class="search-result" ${item.document?`data-search-document="${e(item.document)}"`:`data-search-view="${item.view}"`} data-query="${e(item.query||'')}">${icon(item.type==='资料'?'file':item.type==='卡片'?'bookmark':'arrow')} ${e(item.title)}<span>${item.type}</span></button>`).join(''):'<div class="empty-state"><p>没有找到结果。试试文件名、知识点或页面名称。</p></div>';icons();}
  function showDocument(id){const doc=state.documents.find(d=>d.id===id);if(!doc)return;const source=allSources().find(s=>s.documentId===id);openSource(source||{id:doc.id,title:doc.name,location:doc.status,quote:'',sample:false});if(!source){$('#sourceContent').innerHTML=`<div class="source-content-body"><h2>${e(doc.name)}</h2><p class="source-location">${e(doc.status)}</p><p class="source-quote">当前只保存了文件记录，尚未读取正文。请将内容导出为 TXT / MD 后添加，即可用于检索问答。</p></div>`;}}
  document.addEventListener('DOMContentLoaded',()=>{
    route();window.addEventListener('hashchange',route);
    if(location.protocol==='file:')$('#engineStatus').textContent='本地检索模式';
    else fetch('/api/health',{signal:AbortSignal.timeout(5000)}).then(r=>r.json()).then(p=>{$('#engineStatus').textContent=p.engine==='xiaomi-mimo'?'MiMo 已配置':'本地检索模式';}).catch(()=>{$('#engineStatus').textContent='本地检索模式';});
    $('#spaceContent').addEventListener('submit',event=>{event.preventDefault();if(event.target.id==='chatForm')ask($('#chatInput').value);if(event.target.id==='planForm'){const date=$('#examDate').value;if(!L.validDate(date)||L.daysUntil(date)<0){toast('请选择今天或之后的有效考试日期。');return;}state.examDate=date;state.minutes=Number($('#dailyMinutes').value);state.plan=L.buildPlan(date,state.minutes,state.records);if(persist())toast('复习计划已按考试日期与薄弱点更新。');render();}});
    $('#spaceContent').addEventListener('input',event=>{if(event.target.id==='chatInput')state.draft=event.target.value;if(event.target.id==='librarySearch'){state.libraryQuery=event.target.value;$('#documentList').innerHTML=documentRows(state.libraryQuery);icons();}if(event.target.id==='cardSearch'){state.cardQuery=event.target.value;$('#cardList').innerHTML=cardRows(state.cardQuery);icons();}});
    $('#spaceContent').addEventListener('keydown',event=>{if(event.target.id==='chatInput'&&event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();event.target.form.requestSubmit();}});
    $('#spaceContent').addEventListener('change',event=>{if(event.target.id==='fileInput')upload([...event.target.files]);if(event.target.matches('[data-task]')){const id=event.target.dataset.task;state.completed[id]=event.target.checked;if(persist()){render();$$('[data-task]').find(input=>input.dataset.task===id)?.focus({preventScroll:true});}}});
    $('#spaceContent').addEventListener('dragover',event=>{if(event.target.closest('#uploadZone')){event.preventDefault();$('#uploadZone').classList.add('drag-over');}});
    $('#spaceContent').addEventListener('dragleave',event=>{if(event.target.closest('#uploadZone'))$('#uploadZone').classList.remove('drag-over');});
    $('#spaceContent').addEventListener('drop',event=>{if(event.target.closest('#uploadZone')){event.preventDefault();$('#uploadZone').classList.remove('drag-over');upload([...event.dataTransfer.files]);}});
    document.addEventListener('click',event=>{const b=event.target.closest('button');if(!b)return;const d=b.dataset;
      if('closeDialog'in d)b.closest('dialog').close();if(d.citation)openSource(sourceById(d.citation));if(d.document)showDocument(d.document);if('upload'in d)$('#fileInput').click();if(d.prompt)ask(d.prompt);
      if(d.mode){state.mode=d.mode;render();$('#chatInput').focus();}if('clearChat'in d&&!state.pending){state.messages=[];state.draft='';persist();render();}
      if(d.saveMessage!==undefined){const m=state.messages[Number(d.saveMessage)];saveCard(m.title||'课程重点',m.text,m.sources||[]);}if(d.followup!==undefined){state.draft='请进一步解释这个问题，并给出资料中的依据。';render();$('#chatInput').focus();}
      if(d.removeCard){state.cards=state.cards.filter(c=>c.id!==d.removeCard);persist();render();toast('知识卡片已移除。');}if(d.removeDocument){state.documents=state.documents.filter(doc=>doc.id!==d.removeDocument);persist();render();toast('资料已移除。已保存的卡片仍保留引用。');}
      if(d.quizFilter){state.quizFilter=d.quizFilter;state.quizPool=L.wrongQuestions(state.records);state.quizIndex=0;state.selected=null;state.submitted=false;render();}if(d.option!==undefined){state.selected=Number(d.option);render();$$('[data-option]').find(option=>option.dataset.option===d.option)?.focus({preventScroll:true});}
      if('submitAnswer'in d&&state.selected!==null&&!state.submitted){const q=currentQuestions()[state.quizIndex];state.submitted=true;state.records.push({questionId:q.id,correct:state.selected===q.answer,selected:state.selected,createdAt:new Date().toISOString()});persist();render();}
      if('nextQuestion'in d){if(state.quizFilter==='wrong'){state.quizPool=L.wrongQuestions(state.records);state.quizIndex=0;}else state.quizIndex=(state.quizIndex+1)%Math.max(currentQuestions().length,1);state.selected=null;state.submitted=false;render();}
      if(d.searchView){state.cardQuery=d.query||'';$('#searchDialog').close();if(location.hash===`#space/${d.searchView}`)render();else location.hash=`space/${d.searchView}`;}if(d.searchDocument){$('#searchDialog').close();showDocument(d.searchDocument);}
    });
    $('#sourceSave').addEventListener('click',()=>{const s=state.activeSource;if(s?.quote)saveCard(s.title,s.quote,[s]);});
    $$('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}}));
    function openSearch(){if($('#searchDialog').open)return;searchResults('');$('#searchInput').value='';$('#searchDialog').showModal();$('#searchInput').focus();}$('#searchTrigger').addEventListener('click',openSearch);$('#searchInput').addEventListener('input',event=>searchResults(event.target.value));
    document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();openSearch();}});
    const originalDemo=$('#demoContent').innerHTML;const demoViews={ask:originalDemo,card:`<div class="demo-big-card"><small>属于你的知识卡片</small><h3>二叉搜索树的查找</h3><p>复杂度取决于树高 h。平衡时为 O(log n)，退化成链时为 O(n)。<br>记忆提示：每一次比较，只走向一棵子树。</p><div class="demo-card-footer"><span>讲义 · p.42</span><span>${icon('bookmark')} 已保存重点</span></div></div><a class="demo-compose" href="#space/cards">建立自己的知识卡片 ${icon('arrow')}</a>`,practice:`<div class="demo-big-card"><small>用一道题，检验理解</small><h3>什么时候会退化为 O(n)？</h3><p>节点按顺序插入，且不进行平衡调整时，二叉搜索树可能退化成链。<br>理解树高，就理解了查找复杂度。</p><div class="demo-card-footer"><span>期中复习题 · p.8</span><span>${icon('check')} 把重点，练扎实</span></div></div><a class="demo-compose" href="#space/practice">去完成一组示例练习 ${icon('arrow')}</a>`};
    function changeDemo(b){$$('[data-demo]').forEach(tab=>{tab.classList.toggle('active',tab===b);tab.setAttribute('aria-selected',String(tab===b));tab.tabIndex=tab===b?0:-1;});$('#demoPanel').setAttribute('aria-labelledby',b.id);$('#demoContent').innerHTML=demoViews[b.dataset.demo];icons();if(!matchMedia('(prefers-reduced-motion: reduce)').matches)$('#demoContent').animate([{opacity:.35,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:220,easing:'cubic-bezier(.23,1,.32,1)'});}
    $$('[data-demo]').forEach(b=>{b.addEventListener('click',()=>changeDemo(b));b.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const tabs=$$('[data-demo]'),index=tabs.indexOf(b),next=event.key==='Home'?0:event.key==='End'?2:(index+(event.key==='ArrowRight'?1:2))%3;changeDemo(tabs[next]);tabs[next].focus();});});
  });
})();
