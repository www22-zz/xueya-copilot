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
  function mediaURL(blob){const url=URL.createObjectURL(blob);mediaURLs.add(url);return url;}
  const newButton=(label,attrs='')=>`<button class="button button-outline button-small" type="button" ${attrs}>${e(label)}</button>`;
  function notifyError(error){toast(error?.message||'操作未完成，请重试。');}
  function busy(){if(state.pending||state.working||uploading||state.mediaJob?.running){toast('当前任务还在处理，请先完成或停止，再切换课程。');return true;}return false;}
  function openEditor(title,body,onSubmit,{submit='保存',readonly=false}={}){
    const dialog=$('#workspaceDialog');if(dialog.open)dialog.close();editorSubmit=onSubmit;
    $('#workspaceDialogTitle').textContent=title;
    $('#workspaceDialogBody').innerHTML=`<form id="workspaceForm">${body}<p id="editorError" class="form-error" role="alert"></p>${readonly?'':`<div class="dialog-actions"><button type="button" class="button button-outline button-small" data-close-dialog>取消</button><button type="submit" class="button button-blue button-small">${e(submit)}</button></div>`}</form>`;
    globalThis.XueyaIcons?.();dialog.showModal();
    dialog.querySelector('input:not([type="hidden"]),textarea,select,button')?.focus();
  }
  function field(label,name,value='',{textarea=false,type='text',required=false}={}){return `<label class="form-field">${e(label)}${textarea?`<textarea name="${name}" rows="6" ${required?'required':''}>${e(value)}</textarea>`:`<input name="${name}" type="${type}" value="${e(value)}" ${required?'required':''} maxlength="${name==='title'?160:1000}">`}</label>`;}
  function download(name,blob){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function saveCardVersion(card,changes){card.history=card.history||[];card.history.push({title:card.title,text:card.text,category:card.category,tags:card.tags,version:card.version||1,savedAt:new Date().toISOString()});Object.assign(card,changes,{version:(Number(card.version)||1)+1,updatedAt:new Date().toISOString()});}
  function editCard(cardId,initial){
    const existing=state.cards.find(c=>c.id===cardId),card=existing||initial||{};
    openEditor(existing?'编辑知识卡片':'新建课程笔记',field('标题','title',card.title||'',{required:true})+field('分类','category',card.category||'课程笔记')+field('标签（逗号分隔）','tags',(card.tags||[]).join('，'))+field('正文（Markdown / 常用公式）','text',card.text||'',{textarea:true,required:true}),data=>{
      const changes={title:String(data.get('title')).trim(),text:String(data.get('text')).trim(),category:String(data.get('category')).trim(),tags:String(data.get('tags')).split(/[,，]/).map(s=>s.trim()).filter(Boolean)};
      if(!changes.title||!changes.text)throw new Error('标题和正文不能为空。');
      if(existing)saveCardVersion(existing,changes);else state.cards.unshift({...changes,id:id(),version:1,sources:card.sources||[],createdAt:new Date().toISOString(),history:[]});
      persist();render();toast('笔记已保存。');
    });
  }
  function showCardHistory(cardId){const card=state.cards.find(c=>c.id===cardId);if(!card)return;
    openEditor('笔记版本',`<p>当前v${Number(card.version)||1}，恢复时仍保留当前内容。</p>${(card.history||[]).map((h,index)=>`<article class="history-entry"><strong>v${Number(h.version)||1} · ${e(h.title)}</strong><div class="rich-content">${rich.render(h.text)}</div>${newButton('恢复为新版本',`data-restore-card="${e(card.id)}" data-history-index="${index}"`)}</article>`).join('')||'<p>编辑后，旧版本会出现在这里。</p>'}`,null,{readonly:true});
  }
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
        const doc=service.capabilities.uploadDocument?globalThis.XueyaWorkspaceService.normalizeDocument(await service.call('uploadDocument',{courseId,file:item.file,previousDocumentId:existing?.id},{onProgress:progress=>{if(typeof progress==='string')item.status=progress;else if(progress&&typeof progress.label==='string'){item.status=progress.label;if(Number.isFinite(progress.percent))item.progress=Math.max(0,Math.min(100,progress.percent));}refresh();}})):await libraryService.prepareDocument(item.file);if(state.courseId!==courseId)break;
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
    if(!source)return;state.activeSource=source;const doc=state.documents.find(d=>d.id===source.documentId||d.id===source.id);
    if(readerURL){URL.revokeObjectURL(readerURL);readerURL=null;}
    const chunks=doc?.chunks?.length?doc.chunks:[source];
    $('#sourceContent').innerHTML=`<div class="source-content-body"><h2>${e(doc?.name||source.title)}</h2><p class="source-location">${e(source.location||doc?.status||'原文片段')} · ${doc?.superseded?'历史版本':doc?'v'+(Number(doc.version)||1):'保存的引用快照'}</p><div class="reader-tools">${doc?newButton('下载原件',`data-original="${e(doc.id)}" ${doc.originalAvailable||service.capabilities.original?'':'disabled'}`):''}${doc?.chunks?.length?newButton('导出正文',`data-export-document="${e(doc.id)}"`):''}${doc&&!source.sample?newButton('纠错草稿',`data-correct-source="${e(doc.id)}"`):''}</div><label class="form-field">搜索原文<input type="search" id="readerSearch" placeholder="查找片段中的文字"></label>${chunks.length>1?`<label class="form-field">切换片段<select id="readerSection">${chunks.map((s,i)=>`<option value="${i}" ${s.id===source.id?'selected':''}>${e(s.location||'文本片段 '+(i+1))}</option>`).join('')}</select></label>`:''}<div id="readerPassage"><blockquote class="source-quote">${e(source.quote||'尚未解析出正文。可下载原件核对，或重选文件重试。')}</blockquote></div><div id="readerMedia"></div><p class="source-footnote">${source.sample?'内置课程示例。':doc?'正文位置由当前解析器提供；没有真实页码时只显示片段，不推断页码。':'原资料可能已移除；这里保留当时引用的文本快照。'}</p>${doc?.corrections?.length?`<p class="capability-note">已有${doc.corrections.length}份纠错草稿${doc.corrections.some(c=>!c.applied)?'，未接通重建的修改不会替换检索原文':''}。</p>`:''}</div>`;
    $('#sourceSave').hidden=!source.quote;$('#sourceDialog').showModal();
    $('#readerSection')?.addEventListener('change',event=>{state.activeSource=chunks[Number(event.target.value)];$('#readerSearch').value='';$('#readerPassage').innerHTML=`<blockquote class="source-quote">${e(state.activeSource.quote)}</blockquote>`;});
    $('#readerSearch').addEventListener('input',event=>{const quote=state.activeSource.quote||'',query=event.target.value.trim();$('#readerPassage').innerHTML=`<blockquote class="source-quote">${query?quote.split(query).map(e).join('<mark>'+e(query)+'</mark>'):e(quote)}</blockquote>`;});
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
      doc.corrections=doc.corrections||[];doc.corrections.push(correction);persist();toast(correction.applied?'纠错已提交，请等待服务端重建完成。':'纠错草稿已保存，尚未替换检索原文。');
    });
  }
  function courses(){openEditor('管理课程',`<p class="panel-description">每门课程的资料、会话、笔记、练习和计划分别保存；归档后仍可恢复。</p><div class="course-list">${store.courses.map(c=>`<div><strong>${e(c.name)}</strong>${c.archived?newButton('恢复',`data-restore-course="${e(c.id)}"`):newButton(c.id===state.courseId?'当前课程':'切换',`data-select-course="${e(c.id)}"`)}${!c.archived?newButton('归档',`data-archive-course="${e(c.id)}"`):''}</div>`).join('')}</div>`+field('新课程名称','name','',{required:true}),data=>{if(busy())return false;const course=store.addCourse(data.get('name'));if(course){resetTransient();render();}},{submit:'创建课程'});}
  function resetTransient(){for(const a of attachments)URL.revokeObjectURL(a.url);for(const url of mediaURLs)URL.revokeObjectURL(url);mediaURLs.clear();attachments=[];queue=[];remoteGraph=null;graphLoadedFor=null;graphRevision++;for(const key of Object.keys(mediaFiles))delete mediaFiles[key];state.mediaFiles={};state.mediaPreviews={};state.mediaTokens={};state.mediaJob=null;state.speechText='';}
  function selectCourse(courseId){if(busy())return;if(store.switchCourse(courseId)){resetTransient();$('#workspaceDialog').close();$('#sourceDialog').close();render();}}
  async function attachImages(files){
    for(const file of files){if(!['image/png','image/jpeg','image/webp'].includes(file.type)){toast('请选择PNG、JPEG或WebP图片。');continue;}if(file.size>6*1024*1024||attachments.length>=4){toast('最多4张图片，每张不超过6MB。');break;}attachments.push({file,url:URL.createObjectURL(file)});}
    render();
  }
  function historyFor(question){const index=Number.isInteger(state.followupIndex)?state.followupIndex:state.messages.length-1;const messages=state.messages.slice(0,index+1).filter(m=>!m.failed&&!m.cancelled);const prior=Number.isInteger(state.followupIndex)?state.messages[state.followupIndex]:[...messages].reverse().find(m=>m.role==='ai'&&m.sources?.length);return{history:messages.slice(-12).map(m=>({role:m.role==='ai'?'assistant':'user',content:m.text})),previousSources:prior?.sources||[],question};}
  async function imageChat(request,options){
    const inputFiles=attachments.map(a=>a.file),names=inputFiles.map(f=>f.name),response=await service.call('imageChat',{...request,courseId:state.courseId,images:inputFiles},options);
    if(typeof response.answer!=='string'||!response.answer.trim())throw new Error('图片服务没有返回有效回答。');
    const known=request.sources,sources=(Array.isArray(response.sources)?response.sources:[]).map(s=>known.find(k=>k.id===(typeof s==='string'?s:s?.id))).filter(Boolean);
    for(const a of attachments)URL.revokeObjectURL(a.url);attachments=[];
    return{answer:response.answer,sources,engine:response.engine||'图文学习服务',online:true,imageNames:names,workflow:response.workflow};
  }
  function editQuestion(questionId){
    const old=state.bank.find(q=>q.id===questionId),q=old||{type:'single',options:[],topic:'',prompt:'',explanation:'',sourceId:''};
    openEditor(old?'审核编辑题目':'新建自测题',`<label class="form-field">题型<select name="type">${[['single','单选'],['multiple','多选'],['boolean','判断'],['short','简答']].map(([value,label])=>`<option value="${value}" ${q.type===value?'selected':''}>${label}</option>`).join('')}</select></label>`+field('知识点','topic',q.topic,{required:true})+field('题干','prompt',q.prompt,{textarea:true,required:true})+field('选项（每行一项；判断题自动使用正确/错误）','options',(q.options||[]).join('\n'),{textarea:true})+field('正确选项序号（从1开始，多选用逗号）','answer',Array.isArray(q.answer)?q.answer.map(n=>n+1).join(','):Number.isInteger(q.answer)?String(q.answer+1):'')+field('简答参考答案 / 评分量规','answerText',q.answerText||'',{textarea:true})+field('解析','explanation',q.explanation,{textarea:true,required:true})+`<label class="form-field">原文依据<select name="sourceId"><option value="">未绑定（手工题）</option>${allSources().map(s=>`<option value="${e(s.id)}" ${s.id===q.sourceId?'selected':''}>${e(s.title)} · ${e(s.location)}</option>`).join('')}</select></label>`,data=>{
      const type=String(data.get('type')),options=type==='boolean'?['正确','错误']:String(data.get('options')).split('\n').map(s=>s.trim()).filter(Boolean),values=String(data.get('answer')).split(/[,，]/).filter(s=>s.trim()).map(s=>Number(s.trim())-1);
      if(!String(data.get('topic')).trim()||!String(data.get('prompt')).trim()||!String(data.get('explanation')).trim())throw new Error('知识点、题干和解析不能为空。');
      if(type!=='short'&&(options.length<2||options.length>8||!values.length||values.some(n=>!Number.isInteger(n)||n<0||n>=options.length)||(type!=='multiple'&&values.length!==1)))throw new Error('请填写2～8个选项及有效答案序号。');
      if(type==='short'&&!String(data.get('answerText')).trim())throw new Error('简答题需要参考答案或评分量规。');
      const item={...q,id:old?.id||'bank-'+id(),origin:old?.origin||'manual',type,topic:String(data.get('topic')).trim(),prompt:String(data.get('prompt')).trim(),options:type==='short'?[]:options,answer:type==='multiple'?[...new Set(values)]:type==='short'?null:values[0],answerText:String(data.get('answerText')),explanation:String(data.get('explanation')),sourceId:String(data.get('sourceId')),reviewed:true,version:(q.version||0)+1};
      if(old){item.history=[...(old.history||[]),clone({...old,history:undefined})];state.bank[state.bank.indexOf(old)]=item;}else state.bank.unshift(item);
      delete state.quizDraft[item.id];state.quizFilter='bank';state.quizIndex=state.bank.findIndex(x=>x.id===item.id);state.selected=null;state.submitted=false;persist();render();
    });
  }
  function questionPool(){return views.currentQuestions();}
  function saveAnswerDraft(answer){const q=questionPool()[state.quizIndex];if(!q)return;state.quizDraft[q.id]={...(state.quizDraft[q.id]||{}),answer,submitted:state.submitted};persist();}
  function submitCustom(){const q=questionPool()[state.quizIndex];if(!q||state.submitted)return;const answer=state.quizDraft[q.id]?.answer;if(!answer?.length){toast('请先填写你的回答。');return;}state.submitted=true;saveAnswerDraft(answer);if(q.type==='multiple')recordAnswer(q,[...answer].sort().join(',')===[...(q.answer||[])].sort().join(','),answer);render();}
  function recordAnswer(q,correct,answer){const draft=state.quizDraft[q.id]||{};if(draft.recorded)return;state.records.push({questionId:q.id,questionVersion:q.version||1,correct,selected:answer,selfAssessed:q.type==='short',createdAt:new Date().toISOString()});state.quizDraft[q.id]={...draft,answer,submitted:true,recorded:true};persist();}
  function correction(questionId){const q=[...L.questions,...state.bank].find(q=>q.id===questionId);if(!q)return;openEditor('记录错因与订正',`<p>${e(q.prompt)}</p><label class="form-field">错因<select name="reason">${['概念不清','计算失误','审题遗漏','表达不完整','其他'].map(s=>`<option>${s}</option>`).join('')}</select></label>`+field('用自己的话订正','text','',{textarea:true,required:true}),data=>{state.corrections=state.corrections||[];state.corrections.unshift({id:id(),questionId,topic:q.topic,reason:String(data.get('reason')),text:String(data.get('text')),createdAt:new Date().toISOString()});persist();render();});}
  function rememberPlan(){state.planHistory.push({version:state.planVersion||1,days:clone(state.plan),examDate:state.examDate,minutes:state.minutes,createdAt:new Date().toISOString()});state.planVersion=(state.planVersion||1)+1;}
  function planPreview(days,examDate=state.examDate,minutes=state.minutes){if(!Array.isArray(days)||!days.length||days.some(d=>!L.validDate(d.date)||!Array.isArray(d.tasks)||d.tasks.some(t=>typeof t.id!=='string'||typeof t.title!=='string'||!Number.isFinite(Number(t.minutes))||Number(t.minutes)<=0)))throw new Error('计划格式不完整，请重新生成。');state.planDraft={days:clone(days),examDate,minutes};persist();render();}
  function adoptPlan(){const draft=state.planDraft;if(!draft)return;rememberPlan();state.plan=clone(draft.days);state.examDate=draft.examDate;state.minutes=draft.minutes;state.planDraft=null;persist();render();toast('新的复习安排已采纳。');}
  function deferTask(taskId){const day=state.plan.find(d=>d.tasks.some(t=>t.id===taskId));if(!day)return;const date=L.addDays(day.date,1);if(date>state.examDate){toast('延期后超过考试日期，请先调整考试日期。');return;}rememberPlan();const task=day.tasks.find(t=>t.id===taskId);day.tasks=day.tasks.filter(t=>t.id!==taskId);let next=state.plan.find(d=>d.date===date);if(!next){next={date,tasks:[]};state.plan.push(next);}next.tasks.push(task);state.plan=state.plan.filter(d=>d.tasks.length).sort((a,b)=>a.date.localeCompare(b.date));persist();render();}
  function getGraph(){
    if(remoteGraph){const ids=new Set(remoteGraph.nodes.map(n=>n.id));return{...remoteGraph,edges:[...remoteGraph.edges,...state.relations.filter(r=>ids.has(r.from)&&ids.has(r.to))]};}
    const sources=allSources(),nodes=[],edges=[],labels=new Map();
    for(const source of sources.slice(0,12)){
      const parent='source:'+source.id;nodes.push({id:parent,label:source.title,sourceId:source.id,primary:true});
      const keywords=[...(source.keywords||[]),...state.bank.filter(q=>q.sourceId===source.id).map(q=>q.topic)].filter(k=>typeof k==='string'&&k.trim());
      for(const word of [...new Set(keywords)].slice(0,3)){let concept=labels.get(word);if(!concept&&nodes.length<26){concept={id:'concept:'+word,label:word,sourceId:source.id,records:state.records.filter(r=>[...L.questions,...state.bank].some(q=>q.id===r.questionId&&q.topic===word)).length};labels.set(word,concept);nodes.push(concept);}if(concept)edges.push({from:parent,to:concept.id,type:'source'});}
    }
    for(const card of state.cards.slice(0,8)){if(nodes.length>=26)break;const node={id:'card:'+card.id,label:card.title,primary:true};nodes.push(node);for(const source of card.sources||[])if(nodes.some(n=>n.id==='source:'+source.id))edges.push({from:node.id,to:'source:'+source.id,type:'source'});}
    const validIds=new Set(nodes.map(n=>n.id));for(const relation of state.relations)if(validIds.has(relation.from)&&validIds.has(relation.to))edges.push(relation);
    position(nodes);return{nodes,edges};
  }
  function position(nodes){nodes.forEach((n,i)=>{const angle=i*Math.PI*2/Math.max(nodes.length,1)-Math.PI/2,r=nodes.length>12&&i%2?120:175;n.x=Math.round(380+Math.cos(angle)*r*1.7);n.y=Math.round(210+Math.sin(angle)*r);});}
  function addRelation(){const graph=getGraph();if(graph.nodes.length<2){toast('先添加资料或笔记，再建立关系。');return;}openEditor('手动标记先修关系',`<p class="panel-description">这是你的课程整理，不是模型已验证的先修结论。</p>${['from','to'].map((name,i)=>`<label class="form-field">${i?'后学习':'先学习'}<select name="${name}">${graph.nodes.map(n=>`<option value="${e(n.id)}">${e(n.label)}</option>`).join('')}</select></label>`).join('')}`,data=>{
      const from=String(data.get('from')),to=String(data.get('to'));if(from===to)throw new Error('请选择两个不同节点。');
      const links=graph.edges.filter(edge=>edge.type==='prerequisite');
      const reaches=(node,target,visited=new Set())=>node===target||!visited.has(node)&&(visited.add(node),links.filter(r=>r.from===node).some(r=>reaches(r.to,target,visited)));
      if(reaches(to,from))throw new Error('这会形成先修循环，请调整方向。');if(state.relations.some(r=>r.from===from&&r.to===to))throw new Error('这条关系已经存在。');
      state.relations.push({from,to,fromLabel:graph.nodes.find(n=>n.id===from).label,toLabel:graph.nodes.find(n=>n.id===to).label,type:'prerequisite',origin:'manual'});persist();render();
    });}
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
  function enhance(base){views=globalThis.XueyaWorkspaceViews.createViews({...ctx,rich,service,getAttachments:()=>attachments,getQueue:()=>queue,getGraph},base);return views;}
  function beforeRender(){
    if(state.quizFilter==='wrong'&&!Array.isArray(state.quizPool))state.quizPool=L.wrongQuestions(state.records,[...L.questions,...state.bank]);
    const q=views?.currentQuestions()[state.quizIndex],draft=q&&state.quizDraft[q.id];if(draft){state.selected=typeof draft.answer==='number'?draft.answer:null;state.submitted=!!draft.submitted;}
    const course=store.courses.find(c=>c.id===state.courseId),select=$('#courseSelect');if(select){select.innerHTML=store.courses.filter(c=>!c.archived).map(c=>`<option value="${e(c.id)}" ${c.id===state.courseId?'selected':''}>${e(c.name)}</option>`).join('');select.disabled=state.pending||state.working||uploading||!!state.mediaJob?.running;}if($('#courseLabel'))$('#courseLabel').textContent=course?.name||'我的课程';
  }
  function afterRender(){
    if(state.view==='media')for(const result of state.mediaResults||[])if(result.audioCached&&!result.audioURL&&!audioLoads.has(result.id)){const courseId=state.courseId;audioLoads.add(result.id);cache.get('audio:'+result.id).then(blob=>{if(!(blob instanceof Blob)||state.courseId!==courseId)return;result.audioURL=mediaURL(blob);if(state.view==='media')render();}).catch(()=>toast('语音缓存未能读取，可重新生成。'));}
    if(state.view==='graph'&&service.capabilities.graph&&graphLoadedFor!==state.courseId){const courseId=state.courseId,revision=++graphRevision;graphLoadedFor=courseId;service.call('graph',{courseId}).then(result=>{if(state.courseId!==courseId||revision!==graphRevision)return;if(!Array.isArray(result.nodes)||!Array.isArray(result.edges))throw new Error('概念服务格式不完整。');const nodes=result.nodes.slice(0,40).filter(n=>n&&typeof n.id==='string'&&typeof n.label==='string').map(n=>({...n}));position(nodes);const ids=new Set(nodes.map(n=>n.id));remoteGraph={nodes,edges:result.edges.filter(edge=>edge&&ids.has(edge.from)&&ids.has(edge.to)),paths:(Array.isArray(result.paths)?result.paths:[]).filter(p=>p&&Array.isArray(p.nodeIds)&&p.nodeIds.every(id=>ids.has(id))),remote:true};if(state.view==='graph')render();}).catch(error=>{if(state.courseId===courseId&&revision===graphRevision)notifyError(error);});}
  }
  function handleInput(event){
    const t=event.target;if(t.id==='sessionSearch'){state.sessionQuery=t.value;const caret=t.selectionStart;render();const search=$('#sessionSearch');search.focus();try{search.setSelectionRange(caret,caret);}catch{}return true;}
    if(t.id==='shortAnswer'){saveAnswerDraft(t.value);return true;}if(t.id==='speechText'){state.speechText=t.value;return true;}return false;
  }
  function handleChange(event){const t=event.target;
    if(t.id==='imageInput'){attachImages([...t.files]).catch(notifyError);return true;}
    if(t.dataset.scope!==undefined){state.selectedDocuments=[...document.querySelectorAll('[data-scope]:checked')].map(el=>el.dataset.scope);persist();return true;}
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
    newSession:()=>{store.newSession();render();},clearChat:()=>{store.newSession();render();},session:d=>{store.selectSession(d.session);render();},
    followup:d=>{const index=Number(d.followup);if(state.messages[index]?.role!=='ai')return;state.followupIndex=index;state.draft='请进一步解释这个问题，并给出资料中的依据。';render();$('#chatInput').focus();},cancelFollowup:()=>{state.followupIndex=null;render();},
    addImages:()=>$('#imageInput').click(),removeImage:d=>{const [item]=attachments.splice(Number(d.removeImage),1);if(item)URL.revokeObjectURL(item.url);render();},
    newCard:()=>editCard(),editCard:d=>editCard(d.editCard),cardHistory:d=>showCardHistory(d.cardHistory),restoreCard:d=>{const card=state.cards.find(c=>c.id===d.restoreCard),old=card?.history?.[Number(d.historyIndex)];if(old){saveCardVersion(card,{title:old.title,text:old.text,tags:old.tags,category:old.category});persist();$('#workspaceDialog').close();render();}},
    editDocument:d=>editDocument(d.editDocument),refreshDocuments:async()=>{const courseId=state.courseId;const result=await service.call('listDocuments',{courseId});const list=Array.isArray(result)?result:result.documents;if(!Array.isArray(list))throw new Error('资料服务没有返回有效列表。');const remote=list.map(globalThis.XueyaWorkspaceService.normalizeDocument).map(doc=>{const old=state.documents.find(item=>item.id===doc.id);return{...doc,...old?.uiMetadata,uiMetadata:old?.uiMetadata,originalAvailable:doc.originalAvailable||old?.originalAvailable,remote:true};});if(state.courseId!==courseId)return;const ids=new Set(remote.map(doc=>doc.id));if(ids.size!==remote.length)throw new Error('资料服务返回了重复版本ID，本次未替换原件记录。');state.documents=[...remote,...state.documents.filter(doc=>!doc.remote&&!ids.has(doc.id))];persist();render();toast('资料状态已同步。');},versionDocument:d=>{nextUpload=state.documents.find(doc=>doc.id===d.versionDocument);$('#fileInput').click();},retryDocument:d=>{nextUpload=state.documents.find(doc=>doc.id===d.retryDocument);$('#fileInput').click();},retryUpload:d=>{const item=queue.find(item=>item.id===d.retryUpload);if(item)upload([item.file]).catch(notifyError);},
    original:d=>original(d.original),exportDocument:d=>{const doc=state.documents.find(doc=>doc.id===d.exportDocument);if(doc)download(doc.name+'.txt',new Blob([doc.chunks.map(c=>c.quote).join('\n\n')],{type:'text/plain;charset=utf-8'}));},correctSource:d=>correctSource(d.correctSource),
    manageCourses:()=>courses(),selectCourse:d=>selectCourse(d.selectCourse),restoreCourse:d=>{store.restoreCourse(d.restoreCourse);courses();render();},archiveCourse:d=>{if(busy())return;if(store.archive(d.archiveCourse)){resetTransient();courses();render();}else toast('至少保留一门使用中的课程。');},
    exportWorkspace:()=>download('学涯学习记录-'+L.today()+'.json',new Blob([store.exportData()],{type:'application/json'})),
    feedback:d=>{const m=state.messages[Number(d.feedback)];if(!m)return;const save=text=>{state.feedback.push({id:id(),messageId:m.id||String(d.feedback),rating:d.rating,text,sourceIds:(m.sources||[]).map(s=>s.id),createdAt:new Date().toISOString()});persist();render();toast('反馈已保存在当前课程。');};if(d.rating==='incorrect')openEditor('说明需要核对的地方',field('问题说明','text','',{textarea:true,required:true}),data=>save(String(data.get('text'))));else save('');},
    newQuestion:()=>editQuestion(),editQuestion:d=>editQuestion(d.editQuestion),correction:d=>correction(d.correction),
    option:d=>{state.selected=Number(d.option);state.submitted=false;saveAnswerDraft(state.selected);render();$(`[data-option="${Number(d.option)}"]`)?.focus({preventScroll:true});},restartQuestion:()=>{const q=questionPool()[state.quizIndex];if(q){delete state.quizDraft[q.id];state.submitted=false;state.selected=null;persist();render();}},
    submitCustom:()=>submitCustom(),selfGrade:d=>{const q=questionPool().find(q=>q.id===d.selfGrade);if(q){recordAnswer(q,d.correct==='true',state.quizDraft[q.id]?.answer);render();toast('自评结果已记录。');}},
    buildExam:()=>{const questions=[...L.questions,...state.bank];if(!questions.length){toast('请先创建或生成题目。');return;}openEditor('组建一份测验',`<p class="panel-description">选择题目与顺序，答题草稿会自动保留。</p>${questions.map(q=>`<label class="exam-choice"><input type="checkbox" name="question" value="${e(q.id)}">${e(q.topic)} · ${e(q.prompt)}</label>`).join('')}`,data=>{const ids=data.getAll('question');if(!ids.length)throw new Error('至少选择一道题。');state.examRun={id:id(),ids,createdAt:new Date().toISOString()};state.quizFilter='exam';state.quizIndex=0;state.selected=null;state.submitted=false;for(const qid of ids)delete state.quizDraft[qid];persist();render();},{submit:'开始测验'});},
    variant:async d=>{const q=[...L.questions,...state.bank].find(q=>q.id===d.variant);if(!q)return;const result=await service.call('variant',{courseId:state.courseId,question:q});if(!Array.isArray(result.questions)||!result.questions.length)throw new Error('服务没有返回变式题。');const valid=result.questions.filter(q=>typeof q.prompt==='string'&&Array.isArray(q.options)&&q.options.length>=2&&Number.isInteger(q.answer)&&q.answer>=0&&q.answer<q.options.length&&allSources().some(s=>s.id===q.sourceId));if(!valid.length)throw new Error('变式题缺少有效答案或原文依据。');state.bank.unshift(...valid.map(q=>({...q,id:'bank-'+id(),reviewed:false})));persist();render();},
    adoptPlan:()=>adoptPlan(),discardPlan:()=>{state.planDraft=null;persist();render();},messagePlan:d=>{const m=state.messages[Number(d.messagePlan)],value=m?.artifacts?.plan,days=Array.isArray(value)?value:value?.days||value?.plan;if(!Array.isArray(days)){toast('这份旧结果只有文字预览，请在复习计划页生成可采纳安排。');return;}state.view='plan';location.hash='space/plan';planPreview(days);},
    deferTask:d=>deferTask(d.deferTask),moveTask:d=>{const day=state.plan.find(day=>day.tasks.some(t=>t.id===d.moveTask));if(!day)return;const i=day.tasks.findIndex(t=>t.id===d.moveTask);if(i<1)return;rememberPlan();[day.tasks[i-1],day.tasks[i]]=[day.tasks[i],day.tasks[i-1]];persist();render();},
    planHistory:()=>openEditor('计划历史',state.planHistory.map((p,i)=>`<article class="history-entry"><strong>v${p.version} · ${e(p.createdAt)}</strong><p>${p.days.length}天 · 每日${p.minutes}分钟</p>${newButton('作为预览恢复',`data-restore-plan="${i}"`)}</article>`).join('')||'<p>采纳或调整计划后，旧版本会保留在这里。</p>',null,{readonly:true}),restorePlan:d=>{const p=state.planHistory[Number(d.restorePlan)];if(p){$('#workspaceDialog').close();planPreview(p.days,p.examDate,p.minutes);}},
    reviewCard:d=>{state.reviewLog.push({cardId:d.reviewCard,rating:d.rating,createdAt:new Date().toISOString()});persist();render();},refreshGraph:()=>{graphLoadedFor=null;remoteGraph=null;render();},addRelation:()=>addRelation(),removeRelation:d=>{state.relations.splice(Number(d.removeRelation),1);persist();render();},
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
    const dialog=document.createElement('dialog');dialog.id='workspaceDialog';dialog.className='source-dialog workspace-dialog';dialog.setAttribute('aria-labelledby','workspaceDialogTitle');dialog.innerHTML=`<div class="dialog-head"><h2 id="workspaceDialogTitle"></h2><button type="button" class="icon-button" data-close-dialog aria-label="关闭编辑面板">×</button></div><div id="workspaceDialogBody"></div>`;document.body.append(dialog);
    dialog.addEventListener('submit',async event=>{if(event.target.id!=='workspaceForm')return;event.preventDefault();if(!editorSubmit)return;const submit=event.submitter;if(submit)submit.disabled=true;try{const result=await editorSubmit(new FormData(event.target));if(result!==false)dialog.close();}catch(error){$('#editorError').textContent=error.message||'保存失败，请重试。';}finally{if(submit)submit.disabled=false;}});
    $('#courseSelect').addEventListener('change',event=>selectCourse(event.target.value));
    globalThis.addEventListener('beforeunload',()=>{if(!globalThis.XueyaPlatform?.isRestoring)persist();});
  }
  return{enhance,beforeRender,afterRender,mount,handleClick,handleInput,handleChange,handleSubmit,upload:files=>{const existing=nextUpload;nextUpload=null;return upload(files,{existing});},openSource,historyFor,get service(){return service;},get attachments(){return attachments;},imageChat,canAsk(){if(attachments.length&&!service.capabilities.imageChat){toast('图像服务尚未接通，请移除图片发送文字，或配置图像服务后重试。');return false;}return true;}};
}
return{createWorkspace};
});
