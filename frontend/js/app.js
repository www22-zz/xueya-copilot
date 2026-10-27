(async() => {
  'use strict';
  if(location.protocol!=='file:'&&navigator.serviceWorker)navigator.serviceWorker.register('/sw.js').catch(()=>{});
  await window.XueyaAccountReady;
  await window.XueyaPlatform?.initialize();
  const L=window.XueyaLearning,$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
  const icons=()=>window.XueyaIcons?.();
  const e=window.XueyaRich.escape;
  const icon=name=>`<span data-icon="${name}"></span>`;
  let storage;try{storage=window.localStorage;}catch{storage={getItem(){return null;},setItem(){throw new Error('STORAGE_UNAVAILABLE');}};}
  const store=window.XueyaWorkspaceStore.createStore({storage,learning:L}),state=store.state;
  let agentRuns;
  window.XueyaPlatform?.attach({store,state,toast,render});
  const viewLearning=Object.create(L);
  for(const key of ['documents','sources','questions'])Object.defineProperty(viewLearning,key,{get:()=>state.courseId==='course-default'?L[key]:[]});
  const courseQuestions=()=>viewLearning.questions;
  const allSources=()=>[...viewLearning.sources,...state.documents.filter(d=>!d.superseded&&!d.archived).flatMap(d=>Array.isArray(d.chunks)?d.chunks:[])];
  function persist(){const saved=store.persist();$('#storageNotice')?.toggleAttribute('hidden',saved);if(!saved)toast(store.error);return saved;}
  let toastTimer;function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),3500);}
  const workspace=window.XueyaWorkspace.createWorkspace({state,L:viewLearning,store,e,icon,persist,toast,render,sourceById,allSources,libraryService:window.XueyaLibrary});
  const {titles,renders,documentRows,currentQuestions}=workspace.enhance(window.XueyaViews.createViews({state,L:viewLearning,e,icon,sourceById}));
  titles.knowledge='课程资料';renders.knowledge=()=>'';
  const chatService=window.XueyaChat.createChatService();
  const experience=window.XueyaExperience?.create({state});
  let activeChat;
  const historyLayout=window.XueyaHistoryLayout?.create();
  const searchUI=window.XueyaPlatform?.available?window.XueyaSearchWorkspace?.create({state,store,toast}):null;
  const practiceClient=window.XueyaPracticeClient?.createPracticeClient({accountId:window.XueyaAccountId||'local'});
  const practiceStore=window.XueyaPracticeStore?.createStore({storage,accountId:window.XueyaAccountId||'local'});
  const practiceUI=window.XueyaPracticeView?.createPracticeView({store:practiceStore,client:practiceClient,toast,navigate:hash=>{location.hash=hash;}});
  const analysisUI=window.XueyaAnalysis?.create({client:practiceClient,store:practiceStore,navigate:hash=>{location.hash=hash;},accountId:window.XueyaAccountId||'local'});
  titles.analysis='AI 学习分析';
  renders.analysis=()=>'<div class="view-heading"><div><h1>从练习，看见下一步。</h1><p>AI 学习分析 · 基于你的真实记录</p></div></div><div id="analysisModule"></div>';
  const analysisLink=document.createElement('a');analysisLink.href='#space/analysis';analysisLink.dataset.view='analysis';analysisLink.textContent='学习分析';analysisLink.setAttribute('aria-label','AI 学习分析');document.querySelector('.space-nav').append(analysisLink);
  const workbench=window.XueyaPlatform?.available?window.XueyaWorkbench?.create({state,store,toast}):null;
  const libraryUI=window.XueyaPlatform?.available?window.XueyaLibraryWorkspace?.create({state,store,toast}):null;
  const knowledgeUI=window.XueyaKnowledgeBase?.create({state,store,toast,render});
  const materialLink=document.querySelector('[data-view="library"]');if(materialLink){materialLink.href='#space/knowledge';materialLink.dataset.view='knowledge';}
  const mediaUI=window.XueyaPlatform?.available?window.XueyaMediaWorkspace?.create({state,store,toast}):null;
  function render(){
    analysisUI?.unmount();
    practiceUI?.beforeRender();
    const prior=$('#chatThread'),sameSession=prior?.dataset.sessionId===state.sessionId,scrollTop=prior?.scrollTop||0,nearBottom=!prior||prior.scrollHeight-prior.scrollTop-prior.clientHeight<90;
    const pool=currentQuestions();if(state.quizIndex>=pool.length)state.quizIndex=0;
    workspace.beforeRender();$('#spaceContent').innerHTML=renders[state.view]();$('#documentCount').textContent=state.documents.filter(d=>!d.superseded).length;icons();workspace.afterRender();workbench?.prepare();libraryUI?.mount();workbench?.mount();experience?.mount();mediaUI?.mount();historyLayout?.mount();knowledgeUI?.mount();const practiceModule=$('#practiceModule');if(practiceModule){if(state.view==='review')practiceUI?.mountReview(practiceModule);else practiceUI?.mountPractice(practiceModule,{category:({foundation:'basic',interview:'interview',hot100:'hot100'})[location.hash.split('/')[2]]});}
    const thread=$('#chatThread');if(thread)thread.scrollTop=!sameSession||nearBottom?thread.scrollHeight:scrollTop;
    agentRuns?.refresh();
    if(state.view==='analysis')analysisUI?.mount($('#analysisModule'));
  }
  let initialRoute=true;function route(){const parts=location.hash.replace(/^#/,'').split('/');if(parts[0]==='space'&&parts[1]==='library'&&parts[2]!=='manage'&&window.XueyaPlatform?.available)parts[1]='knowledge';const space=parts[0]==='space';$('#homePage').hidden=space;$('#spacePage').hidden=!space;document.body.classList.toggle('in-space',space);if(space){state.view=titles[parts[1]]?parts[1]:'overview';$$('[data-view]').forEach(a=>{a.classList.toggle('active',a.dataset.view===state.view);a.dataset.view===state.view?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current');});render();document.title=`${titles[state.view]} · 学涯 Copilot`;if(!initialRoute){scrollTo({top:0,behavior:'instant'});$('#spaceContent').focus({preventScroll:true});}}else{document.title='学涯 Copilot — 让知识，真正连起来';if(['possibilities','evidence','rhythm'].includes(parts[0]))requestAnimationFrame(()=>document.getElementById(parts[0]).scrollIntoView());else if(!initialRoute)scrollTo({top:0,behavior:'instant'});}initialRoute=false;}
  function sourceById(id){return [...viewLearning.sources,...state.documents.flatMap(d=>d.chunks||[])].find(s=>s.id===id)||state.messages.flatMap(m=>m.sources||[]).find(s=>s.id===id)||(id?.startsWith('web-')?{id,title:'全网搜索网页',location:'互联网搜索',isWeb:true}:null);}
  function openSource(source){
    if(!source)return;
    const url=source.url||(typeof source.location==='string'&&source.location.startsWith('http')?source.location:'');
    if(source.isWeb||url){
      if(url){window.open(url,'_blank','noopener,noreferrer');return;}
    }
    return workspace.openSource(source);
  }
  async function ask(question){
    const clean=question.trim()||(workspace.attachments.length?'请根据附件内容帮我解答。':'');if(!clean||state.pending||!workspace.canAsk())return;
    const {history,previousSources,previousAnswerKind}=workspace.historyFor(clean);
    const sources=state.selectedDocuments.length?allSources().filter(s=>state.selectedDocuments.includes(s.documentId)):allSources();
    const request={courseId:state.courseId,question:clean,mode:state.mode,sources,history,previousSources,previousAnswerKind,learning:{questions:[],records:[]},webSearch:Boolean(state.webSearch)};
    try{const scope=JSON.parse(localStorage.getItem('xueya-c-learning:'+state.courseId+':scope:'+state.sessionId));if(Array.isArray(scope))request.documentIds=scope;else if(state.selectedDocuments.length)request.documentIds=[...state.selectedDocuments];}catch{}
    const ai={id:crypto.randomUUID(),role:'ai',text:'',reasoning:'',sources:[],engine:'正在回答',title:clean,createdAt:new Date().toISOString()};
    const controller=new AbortController();activeChat=controller;
    state.draft='';state.followupIndex=null;state.pending=true;const userMessage={id:crypto.randomUUID(),role:'user',text:clean};const batch=workspace.takeAttachments(userMessage);state.messages.push(userMessage,ai);persist();
    if(state.view!=='ask')location.hash='space/ask';else render();
    const thinkStart=Date.now();
    let thinkingDuration=null,userScrolledUp=false,isProgrammaticScroll=false,scrollRafId=null;
    const thread=$('#chatThread');
    function updateScrollState(){
      if(isProgrammaticScroll){isProgrammaticScroll=false;return;}
      const t=$('#chatThread');if(!t)return;
      const dist=t.scrollHeight-t.scrollTop-t.clientHeight;
      if(dist>80){userScrolledUp=true;showScrollBottomButton();}
      else if(dist<=30){userScrolledUp=false;hideScrollBottomButton();}
    }
    function onWheel(e){
      if(e.deltaY<0){userScrolledUp=true;showScrollBottomButton();}
      else if(e.deltaY>0){const t=$('#chatThread');if(t&&(t.scrollHeight-t.scrollTop-t.clientHeight<=40)){userScrolledUp=false;hideScrollBottomButton();}}
    }
    function onTouch(){
      const t=$('#chatThread');if(!t)return;
      if(t.scrollHeight-t.scrollTop-t.clientHeight>80){userScrolledUp=true;showScrollBottomButton();}
    }
    function showScrollBottomButton(){
      const t=$('#chatThread');if(!t||$('#chatScrollBottom')||!state.pending)return;
      const btn=document.createElement('button');btn.type='button';btn.id='chatScrollBottom';btn.className='chat-scroll-bottom';btn.setAttribute('aria-label','回到底部');btn.innerHTML='↓ 回到最新';
      btn.onclick=()=>{userScrolledUp=false;isProgrammaticScroll=true;t.scrollTop=t.scrollHeight;btn.remove();};
      t.append(btn);
    }
    function hideScrollBottomButton(){$('#chatScrollBottom')?.remove();}
    if(thread){
      thread.addEventListener('scroll',updateScrollState,{passive:true});
      thread.addEventListener('wheel',onWheel,{passive:true});
      thread.addEventListener('touchmove',onTouch,{passive:true});
    }
    try{
      const stream=batch.length?((input,options)=>workspace.imageChat(input,options,batch)):chatService.stream.bind(chatService);
      const result=await stream(request,{workflow:true,signal:controller.signal,onUpdate(update){
        if(typeof update.answer==='string')ai.text=update.answer;
        if(update.progress)ai.progress=update.progress;
        if(typeof update.reasoning==='string')ai.reasoning=update.reasoning;
        if(update.agent){ai.agent=update.agent;ai.toolCalls=window.XueyaMCPTrace.collect(ai.toolCalls,update.agent);}
        if(update.toolCalls)ai.toolCalls=update.toolCalls;
        if(update.runId)ai.runId=update.runId;
        if(update.agent||update.toolCalls)persist();
        if(ai.text&&!thinkingDuration){
          thinkingDuration=Math.max(1,Math.round((Date.now()-thinkStart)/1000));
          ai.thinkingSeconds=thinkingDuration;
        }
        if(state.view==='ask'){
          const body=$$('#chatThread .ai-message .message-body').at(-1);
          if(body){
            const hasReasoning=Boolean(ai.reasoning||ai.progress||!ai.text);
            let thinkingBox=body.querySelector('.thinking-box');
            if(hasReasoning){
              const label=ai.text?('已深度思考'+(thinkingDuration?' (用时 '+thinkingDuration+' 秒)':'')):(ai.reasoning?'思考中…':(ai.progress||'思考中…'));
              const content=ai.reasoning||ai.progress||'正在思考并核查课程依据…';
              if(!thinkingBox){
                const meta=body.querySelector('.message-meta');
                const boxEl=document.createElement('details');boxEl.className='thinking-box';boxEl.open=!ai.text;
                boxEl.innerHTML=`<summary class="thinking-summary"><span class="thinking-spark">✳</span><span class="thinking-label">${e(label)}</span><span class="thinking-arrow">▾</span></summary><div class="thinking-content">${e(content)}</div>`;
                if(meta&&meta.nextSibling)meta.parentNode.insertBefore(boxEl,meta.nextSibling);else body.prepend(boxEl);
              }else{
                const lbl=thinkingBox.querySelector('.thinking-label');if(lbl)lbl.textContent=label;
                const cnt=thinkingBox.querySelector('.thinking-content');if(cnt)cnt.textContent=content;
                if(ai.text&&thinkingBox.open&&!ai.reasoning){thinkingBox.open=false;}
              }
            }else if(thinkingBox&&ai.text&&!ai.reasoning){
              thinkingBox.remove();
            }
            let richEl=body.querySelector('.rich-content');
            if(richEl){
              richEl.hidden=false;
              if(ai.text){
                richEl.innerHTML=window.XueyaRich.render(ai.text)+'<span class="stream-cursor" aria-hidden="true"></span>';
              }else if(!hasReasoning){
                richEl.innerHTML='<p class="streaming-placeholder">正在组织回答…</p>';
              }else{
                richEl.innerHTML='';
              }
            }
            const streamP=body.querySelector('.stream-text');if(streamP)streamP.hidden=true;
          }
          const t=$('#chatThread');
          if(t&&!userScrolledUp){
            if(!scrollRafId){
              scrollRafId=requestAnimationFrame(()=>{
                scrollRafId=null;
                if(!userScrolledUp&&t){
                  isProgrammaticScroll=true;
                  t.scrollTop=t.scrollHeight;
                  const activeMsg=body?.closest('.ai-message');
                  if(activeMsg){
                    const rect=activeMsg.getBoundingClientRect();
                    if(rect.bottom>window.innerHeight-24){
                      window.scrollBy({top:rect.bottom-(window.innerHeight-24),behavior:'instant'});
                    }
                  }
                }
              });
            }
          }
        }
      }});
      controller.signal.throwIfAborted();
      if(result.transcript)userMessage.transcript=result.transcript;
      Object.assign(ai,{text:result.answer,reasoning:result.reasoning||'',sources:result.sources,engine:result.engine,...(result.timings?{timings:result.timings}:{}),...(result.agent?{agent:result.agent}:{}),...(result.workflow?{workflow:result.workflow}:{}),...(result.artifacts?{artifacts:result.artifacts}:{})});
      if(result.agent)ai.toolCalls=window.XueyaMCPTrace.collect(ai.toolCalls,result.agent);
      if(result.toolCalls)ai.toolCalls=result.toolCalls;
      if(result.runId)ai.runId=result.runId;
      $('#engineStatus').textContent=result.online?'MiMo 在线':result.workflow?'本地学习模式':'本地检索模式';
      $('#engineStatus').classList.toggle('online',result.online);
    }catch(error){
      const cancelled=controller.signal.aborted||error.name==='AbortError';
      Object.assign(ai,{text:cancelled?'已停止生成。你可以修改问题或重新发送。':({IMAGE_MODEL_NOT_CONFIGURED:'图片服务未配置，请在更多中的服务设置查看。',ASR_NOT_CONFIGURED:'语音识别服务未配置，请在更多中的服务设置查看。',AI_UNAVAILABLE:'服务暂不可用，请在更多中的服务设置查看。'}[error.code]||'这次回答未能完成，请检查服务设置后重试。'),reasoning:'',sources:[],engine:cancelled?'已停止':'回答未完成',cancelled,failed:!cancelled});
      if(!state.draft)state.draft=clean;
    }finally{
      if(scrollRafId){cancelAnimationFrame(scrollRafId);scrollRafId=null;}
      hideScrollBottomButton();
      const t=$('#chatThread');
      if(t){
        t.removeEventListener('scroll',updateScrollState);
        t.removeEventListener('wheel',onWheel);
        t.removeEventListener('touchmove',onTouch);
      }
      if(activeChat===controller)activeChat=undefined;
      delete ai.progress;
      if(thinkingDuration&&!ai.thinkingSeconds)ai.thinkingSeconds=thinkingDuration;
      state.pending=false;persist();
      if(state.view==='ask'&&!$('#spacePage').hidden){
        render();
        if(!userScrolledUp){
          const currThread=$('#chatThread');
          if(currThread)currThread.scrollTop=currThread.scrollHeight;
        }
      }else toast(ai.cancelled?'已停止生成。':ai.failed?'回答未完成，请在资料问答中重试。':'回答已准备好，可在资料问答中查看。');
    }
  }

  function upload(files){return libraryUI&&state.view==='knowledge'&&!workspace.versionUploadPending?libraryUI.uploadFiles(files):workspace.upload(files);}
  function searchResults(query){const q=query.trim().toLowerCase();const items=Object.entries(titles).map(([view,title])=>({title,type:'页面',view}));state.documents.forEach(d=>items.push({title:d.name,type:'资料',document:d.id}));state.messages.forEach(m=>{if(m.role==='ai'&&m.text)items.push({title:(m.title||m.text).slice(0,40),type:'回答',view:'ask',query:m.title||''});});const found=items.filter(item=>!q||item.title.toLowerCase().includes(q)).slice(0,12);$('#searchResults').innerHTML=found.length?found.map(item=>`<button type="button" class="search-result" ${item.document?`data-search-document="${e(item.document)}"`:`data-search-view="${item.view}"`} data-query="${e(item.query||'')}">${icon(item.type==='资料'?'file':item.type==='卡片'?'spark':'arrow')} ${e(item.title)}<span>${item.type}</span></button>`).join(''):'<div class="empty-state"><p>没有找到结果。试试文件名、知识点或页面名称。</p></div>';icons();}
  function showDocument(id){const doc=state.documents.find(d=>d.id===id);if(!doc)return;const source=doc.chunks?.[0]||viewLearning.sources.find(s=>s.documentId===id);openSource(source||{id:doc.id,documentId:doc.id,title:doc.name,location:doc.status,quote:'',sample:false});}
  agentRuns=window.XueyaAgentRuns?.create({state,persist,render,toast});
  function mount(){
    agentRuns?.mount();
    workspace.mount();practiceUI?.initialize?.();route();window.addEventListener('hashchange',route);
    if(location.protocol==='file:')$('#engineStatus').textContent='本地检索模式';
    else fetch('/api/health',{signal:AbortSignal.timeout(5000)}).then(r=>r.json()).then(p=>{$('#engineStatus').textContent=p.engine==='xiaomi-mimo'?'MiMo 已配置':'本地检索模式';}).catch(()=>{$('#engineStatus').textContent='本地检索模式';});
    $('#spaceContent').addEventListener('submit',event=>{event.preventDefault();if(workspace.handleSubmit(event))return;if(event.target.id==='chatForm')ask($('#chatInput').value);});
    $('#spaceContent').addEventListener('input',event=>{if(workspace.handleInput(event))return;if(event.target.id==='chatInput')state.draft=event.target.value;if(event.target.id==='librarySearch'){state.libraryQuery=event.target.value;$('#documentList').innerHTML=documentRows(state.libraryQuery);icons();}if(event.target.id==='cardSearch'){state.cardQuery=event.target.value;$('#cardList').innerHTML=cardRows(state.cardQuery);icons();}});
    $('#spaceContent').addEventListener('keydown',event=>{if(event.target.id==='chatInput'&&event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();event.target.form.requestSubmit();}});
    $('#spaceContent').addEventListener('change',event=>{if(workspace.handleChange(event))return;if(event.target.id==='fileInput')upload([...event.target.files]);});
    $('#spaceContent').addEventListener('dragover',event=>{if(event.target.closest('#uploadZone')){event.preventDefault();$('#uploadZone').classList.add('drag-over');}});
    $('#spaceContent').addEventListener('dragleave',event=>{if(event.target.closest('#uploadZone'))$('#uploadZone').classList.remove('drag-over');});
    $('#spaceContent').addEventListener('drop',event=>{if(event.target.closest('#uploadZone')){event.preventDefault();$('#uploadZone').classList.remove('drag-over');upload([...event.dataTransfer.files]);}});
    document.addEventListener('click',event=>{const b=event.target.closest('button');if(!b)return;if(workspace.handleClick(b))return;const d=b.dataset;
      if('closeDialog'in d)b.closest('dialog').close();if(d.citation)openSource(sourceById(d.citation));if(d.document)showDocument(d.document);if('upload'in d)$('#fileInput').click();if(d.prompt)ask(d.prompt);
      if('stopChat'in d)activeChat?.abort();
      if(d.mode){state.mode=d.mode;render();$('#chatInput').focus();}


      if(d.searchView){state.cardQuery=d.query||'';$('#searchDialog').close();if(location.hash===`#space/${d.searchView}`)render();else location.hash=`space/${d.searchView}`;}if(d.searchDocument){$('#searchDialog').close();showDocument(d.searchDocument);}
    });
    $$('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}}));
    function openSearch(){if($('#searchDialog').open)return;searchResults('');$('#searchInput').value='';$('#searchDialog').showModal();$('#searchInput').focus();}$('#searchTrigger').addEventListener('click',openSearch);$('#searchInput').addEventListener('input',event=>searchResults(event.target.value));
    document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();openSearch();}});
    const originalDemo=$('#demoContent').innerHTML;const demoViews={ask:originalDemo,practice:`<div class="demo-big-card"><small>用一道题，检验理解</small><h3>什么时候会退化为 O(n)？</h3><p>节点按顺序插入，且不进行平衡调整时，二叉搜索树可能退化成链。<br>理解树高，就理解了查找复杂度。</p><div class="demo-card-footer"><span>期中复习题 · p.8</span><span>${icon('check')} 把重点，练扎实</span></div></div><a class="demo-compose" href="#space/practice">去完成一组示例练习 ${icon('arrow')}</a>`};
    function changeDemo(b){$$('[data-demo]').forEach(tab=>{tab.classList.toggle('active',tab===b);tab.setAttribute('aria-selected',String(tab===b));tab.tabIndex=tab===b?0:-1;});$('#demoPanel').setAttribute('aria-labelledby',b.id);$('#demoContent').innerHTML=demoViews[b.dataset.demo];icons();if(!matchMedia('(prefers-reduced-motion: reduce)').matches)$('#demoContent').animate([{opacity:.35,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:220,easing:'cubic-bezier(.23,1,.32,1)'});}
    $$('[data-demo]').forEach(b=>{b.addEventListener('click',()=>changeDemo(b));b.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const tabs=$$('[data-demo]'),index=tabs.indexOf(b),next=event.key==='Home'?0:event.key==='End'?2:(index+(event.key==='ArrowRight'?1:2))%3;changeDemo(tabs[next]);tabs[next].focus();});});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
