/* A owns UI orchestration; domain algorithms remain in B/C and repositories in E. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaWorkspace=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const clone=value=>JSON.parse(JSON.stringify(value));
function createWorkspace(ctx){
  const {state,L,store,e,icon,persist,toast,render,sourceById,allSources,libraryService}=ctx;
  const rich=globalThis.XueyaRich,service=globalThis.XueyaWorkspaceService.createService({adapter:globalThis.XueyaWorkspaceBackend||{}}),cache=globalThis.XueyaFileCache.createCache();
  const $=s=>document.querySelector(s),id=()=>crypto.randomUUID();
  let attachments=[],queue=[],uploading=false,nextUpload=null,editorSubmit,readerURL,mediaController;
  const mediaFiles={},mediaURLs=new Set(),audioLoads=new Set();let remoteGraph=null,graphLoadedFor=null,graphRevision=0;
  const messageImages=globalThis.XueyaMessageImages?.create({state,cache,toast});
  const voice=globalThis.XueyaComposerInput?.create({state,persist,render,toast});
  function mediaURL(blob){const url=URL.createObjectURL(blob);mediaURLs.add(url);return url;}
  const newButton=(label,attrs='')=>`<button class="button button-outline button-small" type="button" ${attrs}>${e(label)}</button>`;
  function notifyError(error){toast(error?.message||'操作未完成，请重试。');}
  function busy(){if(state.pending||state.working||uploading||voice?.busy||state.mediaJob?.running){toast('当前任务还在处理，请先完成或停止，再切换课程。');return true;}return false;}
  function openEditor(title,body,onSubmit,{submit='保存',readonly=false}={}){
    const dialog=$('#workspaceDialog');if(dialog.open)dialog.close();editorSubmit=onSubmit;
    $('#workspaceDialogTitle').textContent=title;
    $('#workspaceDialogBody').innerHTML=`<form id="workspaceForm">${body}<p id="editorError" class="form-error" role="alert"></p>${readonly?'':`<div class="dialog-actions"><button type="button" class="button button-outline button-small" data-close-dialog>取消</button><button type="submit" class="button button-blue button-small">${e(submit)}</button></div>`}</form>`;
    globalThis.XueyaIcons?.();dialog.showModal();
    dialog.querySelector('input:not([type="hidden"]),textarea,select,button')?.focus();
  }
  function field(label,name,value='',{textarea=false,type='text',required=false}={}){return `<label class="form-field">${e(label)}${textarea?`<textarea name="${name}" rows="6" ${required?'required':''}>${e(value)}</textarea>`:`<input name="${name}" type="${type}" value="${e(value)}" ${required?'required':''} maxlength="${name==='title'?160:1000}">`}</label>`;}
  function download(name,blob){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function editDocument(documentId){const doc=state.documents.find(d=>d.id===documentId);if(!doc)return;
    openEditor('整理资料',field('文件显示名称','title',doc.name,{required:true})+field('章节','chapter',doc.chapter||'')+field('标签（逗号分隔）','tags',(doc.tags||[]).join('，')),async data=>{const metadata={name:String(data.get('title')).trim(),chapter:String(data.get('chapter')).trim(),tags:String(data.get('tags')).split(/[,，]/).map(s=>s.trim()).filter(Boolean)};if(!metadata.name)throw new Error('资料名称不能为空。');if(doc.remote&&service.capabilities.updateDocument)await service.call('updateDocument',{courseId:state.courseId,documentId:doc.id,version:doc.version||1,metadata});else if(doc.remote)doc.uiMetadata=metadata;Object.assign(doc,metadata);persist();render();if(doc.remote&&!service.capabilities.updateDocument)toast('整理已保存在当前浏览器，尚未同步服务端。');});
  }
  async function upload(files,{existing=null}={}){
    if(uploading){toast('正在处理上一批资料，请稍候。');return;}uploading=true;const courseId=state.courseId;
    queue=Array.from(files).map(file=>({id:id(),file,name:file.name,status:'等待处理',progress:0}));
    const refresh=()=>{if(state.view==='library'){$('#uploadProgress').innerHTML=views.queue?views.queue():'';render();}};
    refresh();
    try{for(const item of queue){
      if(state.courseId!==courseId)break;
      if(!existing&&state.documents.some(d=>!d.superseded&&d.name===item.file.name&&d.bytes===item.file.size)){item.status='已存在，未重复添加';item.progress=100;refresh();continue;}
      item.status='正在读取与解析';item.progress=20;refresh();
      try{
        const doc=service.capabilities.uploadDocument?globalThis.XueyaWorkspaceService.normalizeDocument(await service.call('uploadDocument',{courseId,file:item.file,previousDocumentId:existing?.id,generatePractice:true},{onProgress:progress=>{if(typeof progress==='string')item.status=progress;else if(progress&&typeof progress.label==='string'){item.status=progress.label;if(Number.isFinite(progress.percent))item.progress=Math.max(0,Math.min(100,progress.percent));}refresh();}})):await libraryService.prepareDocument(item.file);if(state.courseId!==courseId)break;
        if(service.capabilities.uploadDocument)doc.remote=true;
        if(state.documents.some(existingDoc=>existingDoc.id===doc.id))throw new Error('资料服务必须为新版本提供独立记录ID，本次未覆盖已有原件。');
        doc.tags=doc.tags||existing?.tags||[];doc.chapter=doc.chapter||existing?.chapter||'';doc.version=Number.isInteger(doc.version)&&doc.version>0?doc.version:existing?(Number(existing.version)||1)+1:1;doc.familyId=doc.familyId||existing?.familyId||existing?.id||doc.id;doc.createdAt=doc.createdAt||new Date().toISOString();
        item.progress=85;item.status='正在缓存原件';refresh();
        try{await cache.put(doc.id,item.file);doc.originalAvailable=true;}catch{doc.originalAvailable=false;toast('正文可用，但原件缓存失败，请保留本地文件。');}
        state.documents.unshift(doc);
        if(existing)existing.superseded=true;
        if(!persist()){state.documents.shift();if(existing)existing.superseded=false;await cache.remove(doc.id).catch(()=>{});throw new Error('正文未能保存，请导出备份并释放浏览器空间。');}
        state.bankTopics=[];state.bankSelected=[];
        item.status=doc.chunks?.length?'已解析，可检索':doc.status+' · 原件'+(doc.originalAvailable?'已缓存':'未缓存');item.progress=100;
      }catch(error){item.status=error.message||'文件读取失败';item.failed=true;item.progress=0;}
      refresh();
    }}finally{uploading=false;persist();refresh();toast(queue.some(item=>item.failed)?'部分资料未完成，可在处理列表重试。':'这批资料已处理，请查看每份资料的状态。');}
  }
  async function openSource(source){
    if(!source)return;
    const url=source.url||(typeof source.location==='string'&&source.location.startsWith('http')?source.location:'');
    if(source.isWeb||url){
      if(url){window.open(url,'_blank','noopener,noreferrer');return;}
    }
    state.activeSource=source;const doc=state.documents.find(d=>d.id===source.documentId||d.id===source.id);
    if(readerURL){URL.revokeObjectURL(readerURL);readerURL=null;}
    const chunks=!source.isPlatform&&doc?.chunks?.length?doc.chunks:[source];
    const passageText=source.isPlatform?'平台预置资料仅供 AI 回答参考，这里保留来源名称和位置。你可以继续提问，了解相关知识。':source.quote||'尚未解析出正文。可下载原件核对，或重选文件重试。';
    $('#sourceContent').innerHTML=`<div class="source-content-body"><h2>${e(doc?.name||source.title)}</h2><p class="source-location">${e(source.location||doc?.status||'原文片段')}${source.isPlatform&&source.originCourseName?' · '+e(source.originCourseName):''} · ${doc?.superseded?'历史版本':doc?'v'+(Number(doc.version)||1):'保存的引用快照'}</p><div class="reader-tools">${doc&&!source.isPlatform?newButton('下载原件',`data-original="${e(doc.id)}" ${doc.originalAvailable||service.capabilities.original?'':'disabled'}`):''}${doc?.chunks?.length&&!source.isPlatform?newButton('导出正文',`data-export-document="${e(doc.id)}"`):''}${doc&&!source.sample&&!source.isPlatform?newButton('纠错草稿',`data-correct-source="${e(doc.id)}"`):''}</div>${source.isPlatform?'':'<label class="form-field">搜索原文<input type="search" id="readerSearch" placeholder="查找片段中的文字"></label>'}${chunks.length>1?`<label class="form-field">切换片段<select id="readerSection">${chunks.map((s,i)=>`<option value="${i}" ${s.id===source.id?'selected':''}>${e(s.location||'文本片段 '+(i+1))}</option>`).join('')}</select></label>`:''}<div id="readerPassage"><blockquote class="source-quote">${e(passageText)}</blockquote></div><div id="readerMedia"></div><p class="source-footnote">${source.sample?'内置课程示例。':source.isPlatform?'平台受保护知识库来源；可查阅定位和讲解，不提供整书导出。':doc?'正文位置由当前解析器提供；没有真实页码时只显示片段，不推断页码。':'原资料可能已移除；这里保留当时引用的文本快照。'}</p>${doc?.corrections?.length?`<p class="capability-note">已有${doc.corrections.length}份纠错草稿${doc.corrections.some(c=>!c.applied)?'，未接通重建的修改不会替换检索原文':''}。</p>`:''}</div>`;
    $('#sourceSave').hidden=source.isPlatform||!source.quote;$('#sourceDialog').setAttribute('aria-label',source.isPlatform?'资料来源':'资料原文');$('#sourceDialog .eyebrow').textContent=source.isPlatform?'公共资料来源':'回到原文';$('#sourceDialog').showModal();
    $('#readerSection')?.addEventListener('change',event=>{state.activeSource=chunks[Number(event.target.value)];$('#readerSearch').value='';$('#readerPassage').innerHTML=`<blockquote class="source-quote">${e(state.activeSource.quote)}</blockquote>`;});
    $('#readerSearch')?.addEventListener('input',event=>{const quote=state.activeSource.quote||'',query=event.target.value.trim();$('#readerPassage').innerHTML=`<blockquote class="source-quote">${query?quote.split(query).map(e).join('<mark>'+e(query)+'</mark>'):e(quote)}</blockquote>`;});
  }
  async function original(documentId){
    const doc=state.documents.find(d=>d.id===documentId);if(!doc)return;
    let blob=await cache.get(doc.id).catch(()=>null);
    if(!blob&&service.capabilities.original){const response=await service.call('original',{courseId:state.courseId,documentId:doc.id,version:doc.version||1});blob=response.blob;}
    if(!(blob instanceof Blob))throw new Error('当前浏览器没有此原件，请重新选择原件或接通资料库服务。');
    download(doc.name,blob);
    if(/\.pdf$/i.test(doc.name)){readerURL=URL.createObjectURL(new Blob([blob],{type:'application/pdf'}));$('#readerMedia').innerHTML=`<iframe class="original-preview" title="PDF原件预览" sandbox src="${e(readerURL)}"></iframe>`;}
  }
  function correctSource(documentId){const doc=state.documents.find(d=>d.id===documentId),source=state.activeSource;if(!doc||!source)return;
    openEditor('核对并纠正原文',`<p class="panel-description">对照原件修改。服务未接通时保存为草稿，检索仍使用原文。</p>`+field('纠正后的片段','text',source.quote||'',{textarea:true,required:true}),async data=>{
      const correction={id:id(),sourceId:source.id,text:String(data.get('text')).trim(),createdAt:new Date().toISOString(),applied:false};
      if(service.capabilities.correctOCR){await service.call('correctOCR',{courseId:state.courseId,documentId:doc.id,version:doc.version||1,correction});correction.applied=true;}
      doc.corrections=doc.corrections||[];doc.corrections.push(correction);persist();render();toast(correction.applied?'纠错已保存并重建原文，请重新打开资料核对。':'纠错草稿已保存，尚未替换检索原文。');
    });
  }
  function courses(){openEditor('管理课程',`<p class="panel-description">每门课程的资料与会话分别保存；练习进度、错题和随手记在同一账号下跨课程共享。归档课程仍可恢复。</p><div class="course-list">${store.courses.map(c=>`<div><strong>${e(c.name)}</strong>${c.archived?newButton('恢复',`data-restore-course="${e(c.id)}"`):newButton(c.id===state.courseId?'当前课程':'切换',`data-select-course="${e(c.id)}"`)}${!c.archived?newButton('归档',`data-archive-course="${e(c.id)}"`):''}</div>`).join('')}</div>`+field('新课程名称','name','',{required:true}),data=>{if(busy())return false;const course=store.addCourse(data.get('name'));if(course){resetTransient();render();}},{submit:'创建课程'});}
  function resetTransient(){for(const a of attachments)URL.revokeObjectURL(a.url);for(const url of mediaURLs)URL.revokeObjectURL(url);mediaURLs.clear();attachments=[];queue=[];remoteGraph=null;graphLoadedFor=null;graphRevision++;for(const key of Object.keys(mediaFiles))delete mediaFiles[key];state.mediaFiles={};state.mediaPreviews={};state.mediaTokens={};state.mediaJob=null;state.speechText='';}
  function selectCourse(courseId){if(busy())return;if(store.switchCourse(courseId)){resetTransient();$('#workspaceDialog').close();$('#sourceDialog').close();render();}}
  async function attachImages(files){
    if(state.pending||voice?.busy)return;
    for(const file of files){const audio=file.type.startsWith('audio/')||/\.(wav|mp3)$/i.test(file.name),image=['image/png','image/jpeg','image/webp'].includes(file.type),document=!audio&&!image&&/\.(pdf|docx|txt|md|markdown)$/i.test(file.name);if(!audio&&!image&&!document){toast('请选择 PNG/JPG/WebP 图片，或 PDF、Word、TXT、Markdown 文件。');continue;}if(audio&&!/\.(wav|mp3)$/i.test(file.name)){toast('语音附件暂支持 WAV 和 MP3。');continue;}if(!file.size||file.size>(audio?7:image?6:10)*1024*1024||attachments.length>=4){toast('最多4个附件；图片6MB、文档10MB以内。');continue;}attachments.push({file,url:URL.createObjectURL(file),documentFile:document});}
    render();
  }
  function pasteImages(event){
    const input=event.target;if(input.id!=='chatInput'||!event.clipboardData)return;
    const items=Array.from(event.clipboardData.items||[]).filter(item=>item.kind==='file'&&item.type.startsWith('image/'));
    const files=items.length?items.map(item=>item.getAsFile()).filter(Boolean):Array.from(event.clipboardData.files||[]).filter(file=>file.type.startsWith('image/'));
    if(!files.length)return;
    if(state.pending||voice?.busy){toast('请等待当前处理完成后再粘贴图片。');return;}
    event.preventDefault();
    const text=event.clipboardData.getData('text/plain'),room=Math.max(0,input.maxLength-(input.value.length-(input.selectionEnd-input.selectionStart)));
    if(text&&room)input.setRangeText(text.slice(0,room),input.selectionStart,input.selectionEnd,'end');
    const start=input.selectionStart,end=input.selectionEnd;state.draft=input.value;persist();
    attachImages(files).then(()=>{const current=$('#chatInput');if(current){current.focus({preventScroll:true});current.setSelectionRange(start,end);}}).catch(notifyError);
  }
  function historyFor(question){const index=Number.isInteger(state.followupIndex)?state.followupIndex:state.messages.length-1;const messages=state.messages.slice(0,index+1).filter(m=>!m.failed&&!m.cancelled);const latest=[...messages].reverse().find(m=>m.role==='ai');const prior=Number.isInteger(state.followupIndex)?state.messages[state.followupIndex]:[...messages].reverse().find(m=>m.role==='ai'&&m.sources?.length);return{history:messages.slice(-12).map(m=>({role:m.role==='ai'?'assistant':'user',content:m.text})),previousSources:['MiMo 通用问答','MiMo 自主回答','应用信息'].includes(latest?.engine)?[]:prior?.sources||[],...(['MiMo 通用问答','MiMo 自主回答','应用信息'].includes(latest?.engine)?{previousAnswerKind:'general'}:{}),question};}
  async function imageChat(request,options,batch){
    const sent=batch||attachments;
    if(globalThis.XueyaChatAttachments){
      const documents=sent.filter(a=>a.documentFile),courseId=state.courseId;
      for(const item of documents){
        options.signal?.throwIfAborted();
        if(!item.document){options.onUpdate?.({progress:'正在解析附件：'+item.file.name});item.document=globalThis.XueyaWorkspaceService.normalizeDocument(await service.call('uploadDocument',{courseId,file:item.file},options));}
        options.signal?.throwIfAborted();if(state.courseId!==courseId)throw new DOMException('课程已切换','AbortError');
        const doc=item.document;
        if(!state.documents.some(d=>d.id===doc.id)){state.documents.unshift({...doc,remote:true});persist();}
        if(!doc.chunks.length)throw Error(item.file.name+' 没有可用正文，请到资料页核对解析结果后再提问。');
      }
      if(documents.length){const docs=documents.map(a=>a.document);request={...request,documentIds:[...new Set([...(request.documentIds||[]),...docs.map(d=>d.id)])],sources:[...new Map([...request.sources,...docs.flatMap(d=>d.chunks)].map(s=>[s.id,s])).values()]};}
      const result=await globalThis.XueyaChatAttachments.respond(sent.filter(a=>!a.documentFile).map(a=>a.file),request,options);
      return result;
    }
    const inputFiles=sent.map(a=>a.file),names=inputFiles.map(f=>f.name),response=await service.call('imageChat',{...request,courseId:state.courseId,images:inputFiles},options);
    if(typeof response.answer!=='string'||!response.answer.trim())throw new Error('图片服务没有返回有效回答。');
    const known=request.sources,sources=(Array.isArray(response.sources)?response.sources:[]).map(s=>known.find(k=>k.id===(typeof s==='string'?s:s?.id))).filter(Boolean);
    return{answer:response.answer,sources,engine:response.engine||'图文学习服务',online:true,imageNames:names,workflow:response.workflow};
  }
  async function mediaRun(name){
    if(mediaController){toast('请先停止或等待当前处理完成。');return;}const file=mediaFiles[name],text=state.speechText||'';
    if(name!=='speak'&&!file)throw new Error('请先选择文件。');if(name==='speak'&&!text.trim())throw new Error('请填写讲解内容。');
    mediaController=new AbortController();const controller=mediaController,courseId=state.courseId;
    state.mediaJob={running:true,label:'正在处理，可随时停止'};render();
    try{const result=await service.call(name,{courseId,file,text},{signal:controller.signal,onProgress:progress=>{if(state.courseId!==courseId||controller.signal.aborted)return;state.mediaJob.label=typeof progress==='string'?progress:'正在处理';if(state.view==='media'){$('#mediaJob strong').textContent=state.mediaJob.label;}}});
      const body=typeof result.text==='string'?result.text:typeof result.summary==='string'?result.summary:'',segments=Array.isArray(result.segments)?result.segments.filter(segment=>segment&&typeof segment.text==='string'):[];if(!body.trim()&&!segments.length&&!(result.audio instanceof Blob))throw new Error('服务结果格式不完整。');
      if(state.courseId!==courseId)return;
      const entry={id:id(),kind:name,inputToken:state.mediaTokens?.[name],title:file?.name||'语音讲解',text:body,segments,createdAt:new Date().toISOString()};
      if(result.audio instanceof Blob){entry.audioURL=mediaURL(result.audio);try{await cache.put('audio:'+entry.id,result.audio);entry.audioCached=true;}catch{toast('语音可在当前页播放，但缓存失败，请保留文本结果。');}}
      state.mediaResults=state.mediaResults||[];state.mediaResults.unshift(entry);state.mediaJob={running:false,label:'处理完成'};persist();
    }catch(error){state.mediaJob={running:false,label:controller.signal.aborted?'已停止处理':'处理失败',error:controller.signal.aborted?'没有保存未完成结果。':error.message};}
    finally{mediaController=null;if(state.view==='media')render();}
  }
  let views;
  function enhance(base){views=globalThis.XueyaWorkspaceViews.createViews({...ctx,rich,service,isSpeaking:text=>globalThis.XueyaTTS?.isPlaying(text),getAttachments:()=>attachments,getMessageImage:ref=>messageImages?.source(ref)||'',getVoiceState:()=>voice?.status,getQueue:()=>queue},base);return views;}
  function beforeRender(){
    voice?.mount();
    const course=store.courses.find(c=>c.id===state.courseId),select=$('#courseSelect');if(select){select.innerHTML=store.courses.filter(c=>!c.archived).map(c=>`<option value="${e(c.id)}" ${c.id===state.courseId?'selected':''}>${e(c.name)}</option>`).join('');select.disabled=state.pending||state.working||uploading||!!voice?.busy||!!state.mediaJob?.running;}if($('#courseLabel'))$('#courseLabel').textContent=course?.name||'我的课程';
  }
  function afterRender(){
    messageImages?.mount();
    if(state.view==='media')for(const result of state.mediaResults||[])if(result.audioCached&&!result.audioURL&&!audioLoads.has(result.id)){const courseId=state.courseId;audioLoads.add(result.id);cache.get('audio:'+result.id).then(blob=>{if(!(blob instanceof Blob)||state.courseId!==courseId)return;result.audioURL=mediaURL(blob);if(state.view==='media')render();}).catch(()=>toast('语音缓存未能读取，可重新生成。'));}
    if(state.view==='graph'&&service.capabilities.graph&&graphLoadedFor!==state.courseId){const courseId=state.courseId,revision=++graphRevision;graphLoadedFor=courseId;service.call('graph',{courseId}).then(result=>{if(state.courseId!==courseId||revision!==graphRevision)return;if(!Array.isArray(result.nodes)||!Array.isArray(result.edges))throw new Error('概念服务格式不完整。');const nodes=result.nodes.slice(0,40).filter(n=>n&&typeof n.id==='string'&&typeof n.label==='string').map(n=>({...n}));position(nodes);const ids=new Set(nodes.map(n=>n.id));remoteGraph={nodes,edges:result.edges.filter(edge=>edge&&ids.has(edge.from)&&ids.has(edge.to)),paths:(Array.isArray(result.paths)?result.paths:[]).filter(p=>p&&Array.isArray(p.nodeIds)&&p.nodeIds.every(id=>ids.has(id))),remote:true};if(state.view==='graph')render();}).catch(error=>{if(state.courseId===courseId&&revision===graphRevision)notifyError(error);});}
  }
  function handleInput(event){
    const t=event.target;if(t.id==='sessionSearch'){state.sessionQuery=t.value;const caret=t.selectionStart;render();const search=$('#sessionSearch');search.focus();try{search.setSelectionRange(caret,caret);}catch{}return true;}
    if(t.id==='shortAnswer'){saveAnswerDraft(t.value);return true;}if(t.id==='speechText'){state.speechText=t.value;return true;}return false;
  }
  function handleChange(event){const t=event.target;
    if(t.id==='imageInput'||t.id==='audioInput'){attachImages([...t.files]).catch(notifyError);return true;}
    if(t.dataset.scope!==undefined){state.selectedDocuments=[...document.querySelectorAll('[data-scope]:checked')].map(el=>el.dataset.scope);try{localStorage.setItem((window.XueyaDataKey||((key)=>key))('xueya-c-learning:'+state.courseId+':scope:'+state.sessionId),JSON.stringify(state.selectedDocuments));}catch{}persist();const summary=document.querySelector('.scope-picker summary');if(summary)summary.textContent='资料范围：'+state.selectedDocuments.length+' 份资料';window.dispatchEvent(new Event('xueya:scope-change'));return true;}
    if(t.dataset.multipleAnswer!==undefined){const values=[...document.querySelectorAll('[data-multiple-answer]:checked')].map(el=>Number(el.dataset.multipleAnswer));saveAnswerDraft(values);return true;}
    if(t.dataset.mediaFile){const file=t.files[0];if(file){const name=t.dataset.mediaFile;if(file.size>100*1024*1024){toast('音视频文件暂限100MB，请先剪成片段。');t.value='';return true;}if(name==='transcribe'&&!file.type.startsWith('audio/')||name==='video'&&!file.type.startsWith('video/')){toast('请选择对应类型的音频或视频。');return true;}if(state.mediaJob?.running){toast('请先停止当前处理，再更换原件。');return true;}mediaFiles[name]=file;state.mediaFiles=state.mediaFiles||{};state.mediaFiles[name]=file.name;state.mediaPreviews=state.mediaPreviews||{};state.mediaTokens=state.mediaTokens||{};if(state.mediaPreviews[name]){URL.revokeObjectURL(state.mediaPreviews[name]);mediaURLs.delete(state.mediaPreviews[name]);}state.mediaPreviews[name]=mediaURL(file);state.mediaTokens[name]=id();render();}return true;}
    return false;
  }
  function handleSubmit(event){if(event.target.id!=='planForm')return false;
    const date=$('#examDate').value,minutes=Number($('#dailyMinutes').value);if(!L.validDate(date)||L.daysUntil(date)<0){toast('请选择今天或之后的有效考试日期。');return true;}
    const pool=[...L.questions,...state.bank];if(!pool.length){toast('先添加自测题或接通学习计划服务，再生成有依据的安排。');return true;}
    planPreview(L.buildPlan(date,minutes,state.records,L.today(),pool),date,minutes);return true;
  }
  const actions={
    toggleWebSearch:()=>{state.webSearch=!state.webSearch;persist();render();toast(state.webSearch?'全网搜索已开启：提问将同时检索互联网最新信息':'全网搜索已关闭：仅依据课程资料回答');},
    newSession:()=>{store.newSession();render();},clearChat:()=>{store.newSession();render();},session:d=>{store.selectSession(d.session);render();},
    toggleSidebar:()=>{if(typeof window.XueyaToggleSidebar==='function')window.XueyaToggleSidebar();else document.body.classList.toggle('sidebar-collapsed');},
    toggleArchived:()=>{state.archivedOpen=!state.archivedOpen;render();},
    archiveSession:d=>{const isArchived=store.toggleArchiveSession(d.archiveSession);state.activeSessionMenuId=null;render();toast(isArchived?'已归档对话':'已取消归档');},
    toggleSessionSearch:()=>{state.sessionSearchOpen=!state.sessionSearchOpen;render();if(state.sessionSearchOpen){setTimeout(()=>$('#sessionSearch')?.focus(),50);}},
    clearSessionSearch:()=>{state.sessionQuery='';render();setTimeout(()=>$('#sessionSearch')?.focus(),50);},
    sessionMenu:d=>{state.activeSessionMenuId=state.activeSessionMenuId===d.sessionMenu?null:d.sessionMenu;render();},
    pinSession:d=>{const isPinned=store.togglePinSession(d.pinSession);state.activeSessionMenuId=null;render();toast(isPinned?'已置顶对话':'已取消置顶');},
    renameSession:d=>{
      const session=state.sessions.find(s=>s.id===d.renameSession);if(!session)return;
      state.activeSessionMenuId=null;render();
      openEditor('重命名对话',field('对话标题','title',session.title,{required:true}),data=>{
        const title=String(data.get('title')||'').trim();if(!title)return false;
        store.renameSession(session.id,title);render();toast('对话已重命名');return true;
      },{submit:'保存'});
    },
    branchSession:d=>{
      const session=state.sessions.find(s=>s.id===d.branchSession);if(!session)return;
      state.activeSessionMenuId=null;
      const lastMsgIdx=Math.max(0,(session.messages?.length||1)-1);
      store.selectSession(session.id);
      store.branchSession(lastMsgIdx);
      render();toast('已在新对话中继续');
    },
    deleteSession:d=>{
      const session=state.sessions.find(s=>s.id===d.deleteSession);if(!session)return;
      state.activeSessionMenuId=null;render();
      openEditor('删除对话',`<p>确定要删除对话“<strong>${e(session.title)}</strong>”吗？删除后将无法恢复。</p>`,()=>{
        store.deleteSession(session.id);render();toast('对话已删除');return true;
      },{submit:'确认删除'});
    },
    dailyCheckin: e => {
      const res = globalThis.XueyaDailyCheckin?.checkin?.();
      if (!res) return;
      if (res.already) {
        toast(`今天已经打过卡啦，已坚持学习 ${res.streak} 天，明天继续加油！`);
      } else {
        toast(`🎉 打卡成功！已连续坚持学习 ${res.streak} 天，继续保持！`);
        render();
        const btn = document.querySelector('[data-daily-checkin]');
        globalThis.XueyaDailyCheckin?.celebrate?.(btn);
      }
    },
    openSettings:()=>{
      const btn=$('#appSettingsButton');if(btn)btn.click();
      else{$('#appSettingsDialog')?.showModal?.();}
    },
    followup:d=>{const index=Number(d.followup);if(state.messages[index]?.role!=='ai')return;state.followupIndex=index;state.draft='请进一步解释这个问题，并给出资料中的依据。';render();$('#chatInput').focus();},cancelFollowup:()=>{state.followupIndex=null;render();},
    ttsRead:d=>{const index=Number(d.ttsRead);const m=state.messages[index];if(!m||!m.text)return;if(globalThis.XueyaTTS?.isPlaying(m.text))globalThis.XueyaTTS.stop();else globalThis.XueyaTTS?.speak(m.text);},
    copyMessage:d=>{const m=state.messages[Number(d.copyMessage)];if(!m||!m.text)return;const text=m.text;if(navigator.clipboard?.writeText){navigator.clipboard.writeText(text).then(()=>toast('已复制回答')).catch(()=>{const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();try{document.execCommand('copy');toast('已复制回答');}catch{toast('复制失败，请手动选取文字');}document.body.removeChild(ta);});}else{const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();try{document.execCommand('copy');toast('已复制回答');}catch{toast('复制失败，请手动选取文字');}document.body.removeChild(ta);}},
    branch:d=>{const index=Number(d.branch);if(state.pending){toast('正在生成中，请稍候再创建分支');return;}const session=store.branchSession?store.branchSession(index):null;if(session){render();toast('已新建分支对话：'+session.title);const input=$('#chatInput');if(input){input.focus();try{input.scrollIntoView({behavior:'smooth',block:'center'});}catch{}}}else{toast('创建分支失败，请重试');}},
    regenerate:d=>{const index=Number(d.regenerate);if(state.pending){toast('正在生成中，请稍候');return;}const m=state.messages[index];if(!m)return;let question='',userIndex=-1;for(let i=index-1;i>=0;i--){if(state.messages[i].role==='user'){question=state.messages[i].text;userIndex=i;break;}}if(!question&&m.title)question=m.title;if(!question){toast('未找到对应问题，无法重新生成');return;}if(userIndex>=0){state.messages.splice(userIndex,index-userIndex+1);}else{state.messages.splice(index,1);}persist();render();if(typeof window.XueyaAsk==='function'){window.XueyaAsk(question);}else{const input=$('#chatInput');if(input){input.value=question;input.form?.requestSubmit();}}},
    messageImage:d=>messageImages?.open(d.messageImage),addAudio:()=>voice?.toggle(),cancelVoice:()=>voice?.cancel(),retryVoice:()=>voice?.retry(),addImages:()=>$('#imageInput').click(),removeImage:d=>{const [item]=attachments.splice(Number(d.removeImage),1);if(item)URL.revokeObjectURL(item.url);render();},
    editDocument:d=>editDocument(d.editDocument),refreshDocuments:async()=>{const courseId=state.courseId;const result=await service.call('listDocuments',{courseId});const list=Array.isArray(result)?result:result.documents;if(!Array.isArray(list))throw new Error('资料服务没有返回有效列表。');const remote=list.map(globalThis.XueyaWorkspaceService.normalizeDocument).map(doc=>{const old=state.documents.find(item=>item.id===doc.id);return{...doc,...old?.uiMetadata,uiMetadata:old?.uiMetadata,originalAvailable:doc.originalAvailable||old?.originalAvailable,remote:true};});if(state.courseId!==courseId)return;const ids=new Set(remote.map(doc=>doc.id));if(ids.size!==remote.length)throw new Error('资料服务返回了重复版本ID，本次未替换原件记录。');state.documents=[...remote,...state.documents.filter(doc=>!doc.remote&&!ids.has(doc.id))];persist();render();toast('资料状态已同步。');},versionDocument:d=>{nextUpload=state.documents.find(doc=>doc.id===d.versionDocument);$('#fileInput').click();},retryDocument:d=>{nextUpload=state.documents.find(doc=>doc.id===d.retryDocument);$('#fileInput').click();},retryUpload:d=>{const item=queue.find(item=>item.id===d.retryUpload);if(item)upload([item.file]).catch(notifyError);},
    original:d=>original(d.original),exportDocument:d=>{const doc=state.documents.find(doc=>doc.id===d.exportDocument);if(doc)download(doc.name+'.txt',new Blob([doc.chunks.map(c=>c.quote).join('\n\n')],{type:'text/plain;charset=utf-8'}));},correctSource:d=>correctSource(d.correctSource),
    manageCourses:()=>courses(),selectCourse:d=>selectCourse(d.selectCourse),restoreCourse:d=>{store.restoreCourse(d.restoreCourse);courses();render();},archiveCourse:d=>{if(busy())return;if(store.archive(d.archiveCourse)){resetTransient();courses();render();}else toast('至少保留一门使用中的课程。');},
    exportWorkspace:()=>download('学涯学习记录-'+L.today()+'.json',new Blob([store.exportData()],{type:'application/json'})),
    feedback:d=>{const m=state.messages[Number(d.feedback)];if(!m)return;const rating=d.rating;if(rating==='incorrect'){openEditor('说明需要核对的地方',field('问题说明','text','',{textarea:true,required:true}),data=>{state.feedback.push({id:id(),messageId:m.id||String(d.feedback),rating:'incorrect',text:String(data.get('text')),sourceIds:(m.sources||[]).map(s=>s.id),createdAt:new Date().toISOString()});persist();render();toast('已提交报错反馈。');});return;}const existingIndex=state.feedback.findIndex(f=>f.messageId===(m.id||String(d.feedback)));if(existingIndex>=0&&state.feedback[existingIndex].rating===rating){state.feedback.splice(existingIndex,1);persist();render();toast('已取消评价');return;}if(existingIndex>=0){state.feedback[existingIndex].rating=rating;state.feedback[existingIndex].createdAt=new Date().toISOString();}else{state.feedback.push({id:id(),messageId:m.id||String(d.feedback),rating,text:'',sourceIds:(m.sources||[]).map(s=>s.id),createdAt:new Date().toISOString()});}persist();render();toast(rating==='helpful'?'已点赞（回答有帮助）':'已点踩（回答待改进）');},
    mediaRun:d=>mediaRun(d.mediaRun),stopMedia:()=>mediaController?.abort(),seekMedia:d=>{const result=state.mediaResults[Number(d.seekMedia)],element=result&&$('#mediaPreview-'+result.kind);if(!element||state.mediaTokens?.[result.kind]!==result.inputToken)return;const seconds=Math.max(0,Number(d.seconds)||0);element.currentTime=Number.isFinite(element.duration)?Math.min(seconds,element.duration):seconds;element.focus();},mediaNote:d=>{const result=state.mediaResults[Number(d.mediaNote)];if(result)editCard(null,{title:result.title,text:result.text+'\n'+(result.segments||[]).map(s=>`[${Number.isFinite(Number(s.start))?Number(s.start).toFixed(1)+'s':'时间未提供'}] ${s.text}`).join('\n'),category:'多模态笔记'});}
  };
  function handleClick(button){const data=button.dataset;
    if(data.removeDocument){const doc=state.documents.find(doc=>doc.id===data.removeDocument);if(!doc)return true;if(uploading||state.pending||state.working){toast('请等待当前处理完成后再移除资料。');return true;}if(doc.remote&&!service.capabilities.removeDocument){toast('服务端资料删除尚未接通，本次未移除。');return true;}openEditor('移除课程资料',`<p>移除“${e(doc.name)}”？这会移除${doc.remote?'服务端资料与':'本地'}原件与检索正文，已保存笔记仍保留引用快照。</p>`,async()=>{if(doc.remote){const result=await service.call('removeDocument',{courseId:state.courseId,documentId:doc.id,version:doc.version||1});if(result.removed!==true)throw new Error('服务端未确认删除，当前记录仍保留。');}await cache.remove(doc.id).catch(()=>{});state.documents=state.documents.filter(d=>d.id!==doc.id);state.selectedDocuments=state.selectedDocuments.filter(v=>v!==doc.id);state.bankTopics=[];state.bankSelected=[];persist();render();toast('资料已移除。');},{submit:'确认移除'});return true;}
    if(data.removeCard){const card=state.cards.find(c=>c.id===data.removeCard);openEditor('移除知识卡片',`<p>确认移除“${e(card?.title)}”及其编辑版本？</p>`,()=>{state.cards=state.cards.filter(c=>c.id!==data.removeCard);persist();render();},{submit:'确认移除'});return true;}
    if('submitAnswer'in data){const q=questionPool()[state.quizIndex];if(q&&state.selected!==null&&!state.submitted){state.submitted=true;recordAnswer(q,state.selected===q.answer,state.selected);render();}return true;}
    if('nextQuestion'in data){const q=questionPool()[state.quizIndex];if(q)delete state.quizDraft[q.id];persist();return false;}
    if(data.practiceTopic){for(const q of [...L.questions,...state.bank].filter(q=>q.topic===data.practiceTopic))delete state.quizDraft[q.id];persist();return false;}
    if('quizFilter'in data){if(data.quizFilter==='wrong')for(const q of L.wrongQuestions(state.records,[...L.questions,...state.bank]))delete state.quizDraft[q.id];state.submitted=false;state.selected=null;return false;}
    for(const [key,fn] of Object.entries(actions))if(Object.prototype.hasOwnProperty.call(data,key)){try{const result=fn(data);if(result&&typeof result.then==='function')result.catch(notifyError);}catch(error){notifyError(error);}return true;}
    return false;
  }
  function mount(){
    $('#spaceContent').addEventListener('paste',pasteImages);
    document.addEventListener('click',event=>{
      if(!event.target.closest('[data-session-menu]')&&!event.target.closest('.session-dropdown-menu')){
        if(state.activeSessionMenuId){state.activeSessionMenuId=null;render();}
      }
    });
    const dialog=document.createElement('dialog');dialog.id='workspaceDialog';dialog.className='source-dialog workspace-dialog';dialog.setAttribute('aria-labelledby','workspaceDialogTitle');dialog.innerHTML=`<div class="dialog-head"><h2 id="workspaceDialogTitle"></h2><button type="button" class="icon-button" data-close-dialog aria-label="关闭编辑面板">×</button></div><div id="workspaceDialogBody"></div>`;document.body.append(dialog);
    dialog.addEventListener('submit',async event=>{if(event.target.id!=='workspaceForm')return;event.preventDefault();if(!editorSubmit)return;const submit=event.submitter;if(submit)submit.disabled=true;try{const result=await editorSubmit(new FormData(event.target));if(result!==false)dialog.close();}catch(error){$('#editorError').textContent=error.message||'保存失败，请重试。';}finally{if(submit)submit.disabled=false;}});
    $('#courseSelect').addEventListener('change',event=>selectCourse(event.target.value));

    globalThis.addEventListener('xueya:sidebar-ask', event => {
      const { text, messageIndex } = event.detail || {};
      if (!text) return;
      state.sidebarAskOpen = true;
      state.sidebarAskText = text;
      state.sidebarAskIndex = messageIndex;
      if (state.view !== 'ask') {
        location.hash = 'space/ask';
      } else {
        render();
      }
      setTimeout(() => {
        const inp = $('#sidebarAskInput');
        if (inp) {
          inp.focus();
          inp.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 50);
      toast('已开启侧边提问助手');
    });

    document.addEventListener('click', event => {
      if (event.target.closest('[data-toggle-sidebar-ask]')) {
        state.sidebarAskOpen = !state.sidebarAskOpen;
        render();
        return;
      }
      if (event.target.closest('[data-close-sidebar-ask]')) {
        state.sidebarAskOpen = false;
        render();
        return;
      }
      if (event.target.closest('[data-sidebar-fill-composer]')) {
        const custom = $('#sidebarAskInput')?.value?.trim();
        const snippet = state.sidebarAskText ? (state.sidebarAskText.length > 60 ? state.sidebarAskText.slice(0, 60) + '…' : state.sidebarAskText) : '';
        state.draft = '关于「' + snippet + '」：' + (custom || '');
        render();
        const inp = $('#chatInput');
        if (inp) {
          inp.focus();
          try { inp.setSelectionRange(inp.value.length, inp.value.length); } catch {}
          inp.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        toast('已带入主输入框');
        return;
      }
    });

    document.addEventListener('submit', event => {
      if (event.target.id === 'sidebarAskForm') {
        event.preventDefault();
        const custom = $('#sidebarAskInput')?.value?.trim();
        const snippet = state.sidebarAskText ? (state.sidebarAskText.length > 80 ? state.sidebarAskText.slice(0, 80) + '…' : state.sidebarAskText) : '';
        const question = custom ? ('关于「' + snippet + '」：' + custom) : ('请详细讲解选中的知识点「' + snippet + '」的核心原理、应用场景与注意事项。');
        state.sidebarAskDraft = '';
        if (globalThis.XueyaAsk) {
          globalThis.XueyaAsk(question);
        }
      }
    });

    document.addEventListener('input', event => {
      if (event.target.id === 'sidebarAskInput') {
        state.sidebarAskDraft = event.target.value;
      }
    });

    globalThis.addEventListener('xueya:followup-selection',event=>{
      const {text,messageIndex}=event.detail||{};
      if(!text)return;
      if(Number.isInteger(messageIndex)&&state.messages[messageIndex]?.role==='ai')state.followupIndex=messageIndex;
      const snippet=text.length>80?text.slice(0,80)+'…':text;
      state.draft='关于「'+snippet+'」：';
      render();
      const input=$('#chatInput');
      if(input){
        input.focus();
        try{input.setSelectionRange(input.value.length,input.value.length);}catch{}
        input.scrollIntoView({behavior:'smooth',block:'center'});
      }
      toast('已带入追问内容');
    });
    globalThis.XueyaTTS?.subscribe(()=>{if(state.view==='ask')render();});
    globalThis.addEventListener('beforeunload',()=>{if(!globalThis.XueyaPlatform?.isRestoring)persist();});
  }
  function takeAttachments(message){const batch=attachments;attachments=[];message.images=messageImages?.remember(batch,message.id)||[];message.attachmentNames=batch.filter(a=>!a.file.type.startsWith('image/')).map(a=>a.file.name);for(const a of batch)if(!a.file.type.startsWith('image/'))URL.revokeObjectURL(a.url);return batch;}
  return{takeAttachments,get versionUploadPending(){return !!nextUpload;},enhance,beforeRender,afterRender,mount,handleClick,handleInput,handleChange,handleSubmit,upload:files=>{const existing=nextUpload;nextUpload=null;return upload(files,{existing});},openSource,historyFor,get service(){return service;},get attachments(){return attachments;},imageChat,canAsk(){if(voice?.busy){toast('请先停止录音并等待文字识别，核对后再发送。');return false;}if(attachments.length&&!(globalThis.XueyaChatAttachments&&globalThis.XueyaPlatform?.available)&&!service.capabilities.imageChat){toast('图像服务尚未接通，请移除图片发送文字，或配置图像服务后重试。');return false;}return true;}};
}
return{createWorkspace};
});
