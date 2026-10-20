(async() => {
  'use strict';
  await window.XueyaAccountReady;
  await window.XueyaPlatform?.initialize();
  const L=window.XueyaLearning,$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
  const icons=()=>window.XueyaIcons?.();
  const e=window.XueyaRich.escape;
  const icon=name=>`<span data-icon="${name}"></span>`;
  let storage;try{storage=window.localStorage;}catch{storage={getItem(){return null;},setItem(){throw new Error('STORAGE_UNAVAILABLE');}};}
  const store=window.XueyaWorkspaceStore.createStore({storage,learning:L}),state=store.state;
  window.XueyaPlatform?.attach({store,state,toast,render});
  const viewLearning=Object.create(L);
  for(const key of ['documents','sources','questions'])Object.defineProperty(viewLearning,key,{get:()=>state.courseId==='course-default'?L[key]:[]});
  const courseQuestions=()=>viewLearning.questions;
  if(state.quizFilter==='wrong')state.quizPool=L.wrongQuestions(state.records,[...courseQuestions(),...state.bank]);
  if(!state.plan.length&&courseQuestions().length)state.plan=L.buildPlan(state.examDate,state.minutes,state.records,L.today(),[...courseQuestions(),...state.bank]);
  const allSources=()=>[...viewLearning.sources,...state.documents.filter(d=>!d.superseded&&!d.archived).flatMap(d=>Array.isArray(d.chunks)?d.chunks:[])];
  function persist(){const saved=store.persist();$('#storageNotice')?.toggleAttribute('hidden',saved);if(!saved)toast(store.error);return saved;}
  let toastTimer;function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),3500);}
  const workspace=window.XueyaWorkspace.createWorkspace({state,L:viewLearning,store,e,icon,persist,toast,render,sourceById,allSources,libraryService:window.XueyaLibrary});
  const {titles,renders,documentRows,cardRows,currentQuestions}=workspace.enhance(window.XueyaViews.createViews({state,L:viewLearning,e,icon,sourceById}));
  const chatService=window.XueyaChat.createChatService();
  const experience=window.XueyaExperience?.create({state});
  let activeChat;
  const searchUI=window.XueyaPlatform?.available?window.XueyaSearchWorkspace?.create({state,store,toast}):null;
  const practiceUI=window.XueyaPracticeUI.create({state,allSources,persist,toast,render,e});
  const learningUI=window.XueyaLearningUI?.create({state,store,toast});
  const workbench=window.XueyaPlatform?.available?window.XueyaWorkbench?.create({state,store,toast}):null;
  const notesUI=window.XueyaPlatform?.available?window.XueyaNotes?.create({state,toast}):null;
  const libraryUI=window.XueyaPlatform?.available?window.XueyaLibraryWorkspace?.create({state,store,toast}):null;
  const {addQuestions,openBankDialog,generateBank,renderBankTopics,updateBankCount,generateFromTopics}=practiceUI;
  function render(){
    const prior=$('#chatThread'),sameSession=prior?.dataset.sessionId===state.sessionId,scrollTop=prior?.scrollTop||0,nearBottom=!prior||prior.scrollHeight-prior.scrollTop-prior.clientHeight<90;
    const pool=currentQuestions();if(state.quizIndex>=pool.length)state.quizIndex=0;
    workspace.beforeRender();$('#spaceContent').innerHTML=renders[state.view]();$('#documentCount').textContent=state.documents.filter(d=>!d.superseded).length;icons();workspace.afterRender();workbench?.prepare();libraryUI?.mount();learningUI?.mount();notesUI?.mount();workbench?.mount();experience?.mount();
    const thread=$('#chatThread');if(thread)thread.scrollTop=!sameSession||nearBottom?thread.scrollHeight:scrollTop;
  }
  let initialRoute=true;function route(){const parts=location.hash.replace(/^#/,'').split('/');const space=parts[0]==='space';$('#homePage').hidden=space;$('#spacePage').hidden=!space;document.body.classList.toggle('in-space',space);if(space){state.view=titles[parts[1]]?parts[1]:'overview';$$('[data-view]').forEach(a=>{a.classList.toggle('active',a.dataset.view===state.view);a.dataset.view===state.view?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current');});render();document.title=`${titles[state.view]} · 学涯 Copilot`;if(!initialRoute){scrollTo({top:0,behavior:'instant'});$('#spaceContent').focus({preventScroll:true});}}else{document.title='学涯 Copilot — 让知识，真正连起来';if(['possibilities','evidence','rhythm'].includes(parts[0]))requestAnimationFrame(()=>document.getElementById(parts[0]).scrollIntoView());else if(!initialRoute)scrollTo({top:0,behavior:'instant'});}initialRoute=false;}
  function sourceById(id){return [...viewLearning.sources,...state.documents.flatMap(d=>d.chunks||[])].find(s=>s.id===id)||state.messages.flatMap(m=>m.sources||[]).find(s=>s.id===id)||state.cards.flatMap(c=>c.sources||[]).find(s=>s.id===id);}
  function openSource(source){return workspace.openSource(source);}
  function saveCard(title,text,sources){if(state.cards.some(c=>c.text===text)){toast('这段重点已经在知识卡片里了。');return;}state.cards.unshift({id:crypto.randomUUID(),title:title.slice(0,80),text,sources,createdAt:new Date().toISOString()});if(persist())toast('理解，留下来了。已保存知识卡片。');}
  async function ask(question){
    const clean=question.trim()||(workspace.attachments.length?'请根据附件内容帮我解答。':'');if(!clean||state.pending||!workspace.canAsk())return;
    const {history,previousSources}=workspace.historyFor(clean);
    const sources=state.selectedDocuments.length?allSources().filter(s=>state.selectedDocuments.includes(s.documentId)):allSources();
    const request={courseId:state.courseId,question:clean,mode:state.mode,sources,history,previousSources,learning:{questions:[...courseQuestions(),...state.bank],records:state.records,examDate:state.examDate,minutes:state.minutes}};
    try{const scope=JSON.parse(localStorage.getItem('xueya-c-learning:'+state.courseId+':scope:'+state.sessionId));if(Array.isArray(scope))request.documentIds=scope;else if(state.selectedDocuments.length)request.documentIds=[...state.selectedDocuments];}catch{}
    const ai={id:crypto.randomUUID(),role:'ai',text:'',reasoning:'',sources:[],engine:'正在回答',title:clean,createdAt:new Date().toISOString()};
    const controller=new AbortController();activeChat=controller;
    state.draft='';state.followupIndex=null;state.pending=true;const userMessage={id:crypto.randomUUID(),role:'user',text:clean,attachmentNames:workspace.attachments.map(a=>a.file.name)};state.messages.push(userMessage,ai);persist();
    if(state.view!=='chat')location.hash='space/chat';else render();
    try{
      const stream=workspace.attachments.length?workspace.imageChat:chatService.stream.bind(chatService);
      const result=await stream(request,{workflow:true,signal:controller.signal,onUpdate(update){
        if(typeof update.answer==='string')ai.text=update.answer;
        if(typeof update.reasoning==='string')ai.reasoning=update.reasoning;
        if(update.progress)ai.progress=update.progress;
        if(state.view==='chat'){
          const body=$$('#chatThread .ai-message .message-body').at(-1);
          const paragraph=body?.querySelector('p');
          if(paragraph)paragraph.textContent=ai.text;
          const status=body?.querySelector('.message-meta span');
          if(status&&ai.progress)status.textContent=ai.progress;

        }
      }});
      controller.signal.throwIfAborted();
      if(result.transcript)userMessage.transcript=result.transcript;
      Object.assign(ai,{text:result.answer,reasoning:result.reasoning||'',sources:result.sources,engine:result.engine,...(result.workflow?{workflow:result.workflow}:{}),...(result.artifacts?{artifacts:result.artifacts}:{})});
      $('#engineStatus').textContent=result.online?'MiMo 在线':result.workflow?'本地学习模式':'本地检索模式';
      $('#engineStatus').classList.toggle('online',result.online);
    }catch(error){
      const cancelled=controller.signal.aborted||error.name==='AbortError';
      Object.assign(ai,{text:cancelled?'已停止生成。你可以修改问题或重新发送。':({IMAGE_MODEL_NOT_CONFIGURED:'图片服务未配置，请在更多中的服务设置查看。',ASR_NOT_CONFIGURED:'语音识别服务未配置，请在更多中的服务设置查看。',AI_UNAVAILABLE:'服务暂不可用，请在更多中的服务设置查看。'}[error.code]||'这次回答未能完成，请检查服务设置后重试。'),reasoning:'',sources:[],engine:cancelled?'已停止':'回答未完成',cancelled,failed:!cancelled});
      if(!state.draft)state.draft=clean;
    }finally{
      if(activeChat===controller)activeChat=undefined;
      delete ai.progress;
      state.pending=false;persist();
      if(state.view==='chat'&&!$('#spacePage').hidden){render();$$('#chatThread .message').at(-1)?.scrollIntoView({block:'nearest',behavior:'instant'});}
      else toast(ai.cancelled?'已停止生成。':ai.failed?'回答未完成，请在资料问答中重试。':'回答已准备好，可在资料问答中查看。');
    }
  }
  function upload(files){return libraryUI&&state.view==='library'&&!workspace.versionUploadPending?libraryUI.uploadFiles(files):workspace.upload(files);}
  const contentUI=window.XueyaPlatform?.available?window.XueyaContentWorkspace?.create({state,store,toast}):null;
  const mountLearning=learningUI?.mount;
  if(mountLearning)learningUI.mount=()=>{mountLearning();contentUI?.mount();};
  function searchResults(query){const q=query.trim().toLowerCase();const items=Object.entries(titles).map(([view,title])=>({title,type:'页面',view}));state.documents.forEach(d=>items.push({title:d.name,type:'资料',document:d.id}));state.cards.forEach(c=>items.push({title:c.title,type:'卡片',view:'cards',query:c.title}));const found=items.filter(item=>!q||item.title.toLowerCase().includes(q)).slice(0,12);$('#searchResults').innerHTML=found.length?found.map(item=>`<button type="button" class="search-result" ${item.document?`data-search-document="${e(item.document)}"`:`data-search-view="${item.view}"`} data-query="${e(item.query||'')}">${icon(item.type==='资料'?'file':item.type==='卡片'?'bookmark':'arrow')} ${e(item.title)}<span>${item.type}</span></button>`).join(''):'<div class="empty-state"><p>没有找到结果。试试文件名、知识点或页面名称。</p></div>';icons();}
  function showDocument(id){const doc=state.documents.find(d=>d.id===id);if(!doc)return;const source=doc.chunks?.[0]||viewLearning.sources.find(s=>s.documentId===id);openSource(source||{id:doc.id,documentId:doc.id,title:doc.name,location:doc.status,quote:'',sample:false});}
  function mount(){
    workspace.mount();practiceUI.mount();route();window.addEventListener('hashchange',route);
    if(location.protocol==='file:')$('#engineStatus').textContent='本地检索模式';
    else fetch('/api/health',{signal:AbortSignal.timeout(5000)}).then(r=>r.json()).then(p=>{$('#engineStatus').textContent=p.engine==='xiaomi-mimo'?'MiMo 已配置':'本地检索模式';}).catch(()=>{$('#engineStatus').textContent='本地检索模式';});
    $('#spaceContent').addEventListener('submit',event=>{event.preventDefault();if(workspace.handleSubmit(event))return;if(event.target.id==='chatForm')ask($('#chatInput').value);});
    $('#spaceContent').addEventListener('input',event=>{if(workspace.handleInput(event))return;if(event.target.id==='chatInput')state.draft=event.target.value;if(event.target.id==='librarySearch'){state.libraryQuery=event.target.value;$('#documentList').innerHTML=documentRows(state.libraryQuery);icons();}if(event.target.id==='cardSearch'){state.cardQuery=event.target.value;$('#cardList').innerHTML=cardRows(state.cardQuery);icons();}});
    $('#spaceContent').addEventListener('keydown',event=>{if(event.target.id==='chatInput'&&event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();event.target.form.requestSubmit();}});
    $('#spaceContent').addEventListener('change',event=>{if(workspace.handleChange(event))return;if(event.target.id==='fileInput')upload([...event.target.files]);if(event.target.matches('[data-task]')){const id=event.target.dataset.task;state.completed[id]=event.target.checked;if(persist()){render();$$('[data-task]').find(input=>input.dataset.task===id)?.focus({preventScroll:true});}}});
    $('#spaceContent').addEventListener('dragover',event=>{if(event.target.closest('#uploadZone')){event.preventDefault();$('#uploadZone').classList.add('drag-over');}});
    $('#spaceContent').addEventListener('dragleave',event=>{if(event.target.closest('#uploadZone'))$('#uploadZone').classList.remove('drag-over');});
    $('#spaceContent').addEventListener('drop',event=>{if(event.target.closest('#uploadZone')){event.preventDefault();$('#uploadZone').classList.remove('drag-over');upload([...event.dataTransfer.files]);}});
    document.addEventListener('click',event=>{const b=event.target.closest('button');if(!b)return;if(workspace.handleClick(b))return;const d=b.dataset;
      if('closeDialog'in d)b.closest('dialog').close();if(d.citation)openSource(sourceById(d.citation));if(d.document)showDocument(d.document);if('upload'in d)$('#fileInput').click();if(d.prompt)ask(d.prompt);
      if('stopChat'in d)activeChat?.abort();if('stopPractice'in d)practiceUI.cancel();
      if(d.mode){state.mode=d.mode;render();$('#chatInput').focus();}
      if(d.saveMessage!==undefined){const m=state.messages[Number(d.saveMessage)];saveCard(m.title||'课程重点',m.text,m.sources||[]);}

      if(d.quizFilter){state.quizFilter=d.quizFilter;state.quizPool=L.wrongQuestions(state.records,[...courseQuestions(),...state.bank]);state.quizIndex=0;state.selected=null;state.submitted=false;render();}if(d.practiceTopic){const idx=courseQuestions().findIndex(q=>q.topic===d.practiceTopic);const bankIndex=state.bank.findIndex(q=>q.topic===d.practiceTopic);state.quizFilter=idx<0&&bankIndex>=0?'bank':'all';state.quizIndex=idx<0?Math.max(0,bankIndex):idx;state.selected=null;state.submitted=false;if(state.view==='practice')render();else location.hash='space/practice';}if(d.generateQuestions){addQuestions(d.generateQuestions);}if('generateBank'in d){generateBank();}if('openBankDialog'in d){openBankDialog();}

      if('nextQuestion'in d){if(state.quizFilter==='wrong'){state.quizPool=L.wrongQuestions(state.records,[...courseQuestions(),...state.bank]);state.quizIndex=0;}else if(state.quizFilter==='bank'){if(state.quizIndex>=currentQuestions().length-1){state.quizFilter='all';state.quizIndex=0;}else state.quizIndex++;}else state.quizIndex=(state.quizIndex+1)%Math.max(currentQuestions().length,1);state.selected=null;state.submitted=false;render();}
      if(d.searchView){state.cardQuery=d.query||'';$('#searchDialog').close();if(location.hash===`#space/${d.searchView}`)render();else location.hash=`space/${d.searchView}`;}if(d.searchDocument){$('#searchDialog').close();showDocument(d.searchDocument);}
    });
    $('#sourceSave').addEventListener('click',()=>{const s=state.activeSource;if(s?.quote)saveCard(s.title,s.quote,[s]);});
    const bankGenerateEl=$('#bankGenerate'),bankTopicsEl=$('#bankTopics');
    if(bankGenerateEl)bankGenerateEl.addEventListener('click',generateFromTopics);
    if(bankTopicsEl)bankTopicsEl.addEventListener('change',event=>{if(event.target.matches('input[data-topic]')){state.bankSelected=$$('#bankTopics input[data-topic]:checked').map(input=>input.dataset.topic);updateBankCount();}});
    const bankRefreshEl=$('#bankRefresh');
    if(bankRefreshEl)bankRefreshEl.addEventListener('click',()=>{state.bankTopics=[];state.bankSelected=[];persist();openBankDialog();});
    $$('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}}));
    function openSearch(){if($('#searchDialog').open)return;searchResults('');$('#searchInput').value='';$('#searchDialog').showModal();$('#searchInput').focus();}$('#searchTrigger').addEventListener('click',openSearch);$('#searchInput').addEventListener('input',event=>searchResults(event.target.value));
    document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();openSearch();}});
    const originalDemo=$('#demoContent').innerHTML;const demoViews={ask:originalDemo,card:`<div class="demo-big-card"><small>属于你的知识卡片</small><h3>二叉搜索树的查找</h3><p>复杂度取决于树高 h。平衡时为 O(log n)，退化成链时为 O(n)。<br>记忆提示：每一次比较，只走向一棵子树。</p><div class="demo-card-footer"><span>讲义 · p.42</span><span>${icon('bookmark')} 已保存重点</span></div></div><a class="demo-compose" href="#space/cards">建立自己的知识卡片 ${icon('arrow')}</a>`,practice:`<div class="demo-big-card"><small>用一道题，检验理解</small><h3>什么时候会退化为 O(n)？</h3><p>节点按顺序插入，且不进行平衡调整时，二叉搜索树可能退化成链。<br>理解树高，就理解了查找复杂度。</p><div class="demo-card-footer"><span>期中复习题 · p.8</span><span>${icon('check')} 把重点，练扎实</span></div></div><a class="demo-compose" href="#space/practice">去完成一组示例练习 ${icon('arrow')}</a>`};
    function changeDemo(b){$$('[data-demo]').forEach(tab=>{tab.classList.toggle('active',tab===b);tab.setAttribute('aria-selected',String(tab===b));tab.tabIndex=tab===b?0:-1;});$('#demoPanel').setAttribute('aria-labelledby',b.id);$('#demoContent').innerHTML=demoViews[b.dataset.demo];icons();if(!matchMedia('(prefers-reduced-motion: reduce)').matches)$('#demoContent').animate([{opacity:.35,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:220,easing:'cubic-bezier(.23,1,.32,1)'});}
    $$('[data-demo]').forEach(b=>{b.addEventListener('click',()=>changeDemo(b));b.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const tabs=$$('[data-demo]'),index=tabs.indexOf(b),next=event.key==='Home'?0:event.key==='End'?2:(index+(event.key==='ArrowRight'?1:2))%3;changeDemo(tabs[next]);tabs[next].focus();});});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
