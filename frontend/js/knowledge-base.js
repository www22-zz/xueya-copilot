/* Knowledge bases are existing courses. Never keep a second copy of their sources. */
(() => {
'use strict';
window.XueyaKnowledgeBase={create({state,store,toast,render}){
 const e=window.XueyaRich.escape,$=s=>document.querySelector(s),uid=()=>crypto.randomUUID();
 const labels={queued:'等待处理',running:'正在处理',cancelling:'正在取消',succeeded:'处理完成',failed:'处理失败',cancelled:'已取消',unknown:'结果待核对'};
 const errors={AUTH_REQUIRED:'会话已变化，请刷新页面',EXTERNAL_CONFIRMATION_REQUIRED:'请先确认外部 API 调用',VERSION_CONFLICT:'资料已更新，请刷新后再操作',EMBEDDING_UNAVAILABLE:'向量服务未配置，仍可使用关键词检索',OCR_UNAVAILABLE:'文字识别服务未配置',PAID_RETRY_FORBIDDEN:'请先到任务与用量核对外部请求',TEMPORARY_FILE_FORBIDDEN:'已跳过 Office 临时文件',FILE_TOO_LARGE:'文件超过大小限制',JOB_NOT_RETRYABLE:'该任务当前不能重试',IDEMPOTENCY_CONFLICT:'同一次操作的内容已变化，请重新操作'};
 let course='',epoch=0,data=null,bases=[],timer=null,loading=false,busy=false,reader=null,chapter='',filter='',query='',results=null,notice='',token='',uploadChapter='',searchMode='lexical',externalConfirmed=false,paidConfirmed=false;
 const button=(text,action,id='',extra='')=>`<button type="button" class="button button-outline button-small" data-kb="${action}" data-id="${e(id)}" ${extra}>${e(text)}</button>`;
 const valid=g=>g===epoch&&state.view==='knowledge'&&course===state.courseId;
 async function api(path,value,options={}){
  if(!token){const r=await fetch('/api/platform/bootstrap');if(!r.ok)throw Error('请启动本地服务并登录后使用知识库');token=(await r.json()).token;}
  const response=await fetch('/api/platform/'+path,{method:value!==undefined?'POST':'GET',headers:{'X-Xueya-Token':token,...(value!==undefined&&!(value instanceof File)?{'Content-Type':'application/json'}:{}),...options.headers},body:value===undefined?undefined:value instanceof File?value:JSON.stringify(value)});
  const result=await response.json();if(!response.ok||!result.ok)throw Error(errors[result.error]||result.error||'操作未完成');return result;
 }
 function schedule(){clearTimeout(timer);if(data?.summary.processing&&state.view==='knowledge')timer=setTimeout(()=>void load(false),1500);}
 async function load(full=true){
  if(loading)return;loading=true;const g=epoch,id=course;
  try{
   if(full){bases=(await api('knowledge/bases')).bases;if(!valid(g))return;const local=store.courses.find(c=>c.id===id);if(!bases.some(c=>c.id===id)&&local){await api('courses',{id,name:local.name});bases=(await api('knowledge/bases')).bases;}}
   const next=await api('knowledge/catalog?'+new URLSearchParams({courseId:id}));if(!valid(g))return;
   if(data&&JSON.stringify(data.documents.map(d=>[d.id,d.version,d.archived]))!==JSON.stringify(next.documents.map(d=>[d.id,d.version,d.archived])))results=null;
   data=next;
   if($('#documentCount'))$('#documentCount').textContent=data.summary.documents;
   if(!full&&$('#kbDocuments')){
    rows();showResults();$('.kb-stats')?.querySelectorAll('strong').forEach((el,i)=>el.textContent=[data.summary.documents,data.summary.sources,data.summary.processing,data.summary.needsReview][i]);
    if($('#kbNotice'))$('#kbNotice').textContent=notice;
    const select=$('#kbChapter');select.innerHTML='<option value="">全部章节</option>'+[...new Set(data.documents.filter(d=>!d.archived).map(d=>d.chapter).filter(Boolean))].map(c=>`<option value="${e(c)}">${e(c)}</option>`).join('');select.value=chapter;
   }else draw();schedule();
  }catch(error){if(valid(g)){notice=error.message;draw();}}
  finally{if(g===epoch)loading=false;}
 }
 function draw(){
  const root=$('#knowledgeWorkspace');if(!root)return;
  const s=data?.summary||{documents:0,sources:0,processing:0,needsReview:0},caps=data?.capabilities||{};
  root.innerHTML=`<div class="view-heading"><div><h1>知识库</h1><p>让课程资料成为可查找、可引用的学习依据。</p></div><div class="heading-actions"><a class="button button-outline button-small kb-search-jump" href="#" data-kb="jump-search">检索原文</a>${button('刷新','refresh')}<button type="button" class="button button-blue button-small" data-kb="create">新建知识库</button></div></div>
   <section class="panel kb-overview"><div class="kb-scope"><label class="form-field">当前知识库<select id="kbBase">${[...bases,...store.courses.filter(c=>!c.archived&&!bases.some(b=>b.id===c.id))].map(c=>`<option value="${e(c.id)}" ${c.id===course?'selected':''}>${e(c.name)}</option>`).join('')}</select></label><p>与当前课程共用资料，问答与学习成果可直接使用。</p></div><div class="kb-stats">${[['资料',s.documents],['原文片段',s.sources],['处理中',s.processing],['需核对',s.needsReview]].map(([label,n])=>`<div><strong>${n}</strong><span>${label}</span></div>`).join('')}</div></section>
   <div id="kbNotice" role="status" aria-live="polite">${e(notice||(!data?'正在加载知识库…':''))}</div>
   <section class="panel kb-import"><div><h2>添加学习资料</h2><p>PDF、PPTX、DOCX、TXT、Markdown · 每份最多 10MB，文字文件最多 1MB</p></div><label class="form-field">所属章节<input id="kbUploadChapter" maxlength="200" placeholder="可选；留空时识别文件名中的章节或周次"></label><input id="kbFiles" type="file" multiple accept=".pdf,.pptx,.docx,.txt,.md" ${busy?'disabled':''}><small>选中文件后自动上传并在后台解析，无需调用模型。图示与扫描内容请核对原件。</small></section>
   <div class="kb-columns"><section class="panel kb-documents"><div class="kb-section-heading"><h2>资料列表</h2><a class="text-link" href="#space/library">阅读与版本管理 →</a></div><div class="kb-filters"><label class="form-field">章节<select id="kbChapter"><option value="">全部章节</option>${[...new Set((data?.documents||[]).filter(d=>!d.archived).map(d=>d.chapter).filter(Boolean))].map(c=>`<option value="${e(c)}" ${c===chapter?'selected':''}>${e(c)}</option>`).join('')}</select></label><label class="form-field">筛选文件<input id="kbFilter" type="search" value="${e(filter)}" placeholder="文件名"></label></div><div id="kbDocuments"></div></section>
   <section class="panel kb-search"><h2 id="kbSearchHeading" tabindex="-1">检索原文</h2><p>先核对课件中的依据，再进入问答。</p><form id="kbSearch"><label class="form-field">你的问题<input name="query" id="kbQuery" type="search" value="${e(query)}" placeholder="例如：栈和队列有什么区别" maxlength="2000" required></label><label class="form-field">检索方式<select name="mode" id="kbMode"><option value="lexical">关键词检索 · 无模型调用</option><option value="hybrid">混合检索 · 外部 API</option><option value="rerank">混合检索并重排 · 外部 API</option></select></label><label class="kb-api-confirm" hidden><input type="checkbox" name="confirmedExternal">确认本次外部 API 调用，可能产生费用</label><button class="button button-blue button-small" ${busy?'disabled':''}>查找依据</button></form><p class="kb-capability">关键词检索可用 · 向量${caps.embedding?'已配置，连接未验证':'未配置'} · 重排${caps.rerank?'已配置，连接未验证':'未配置'}</p><div id="kbResults" aria-live="polite"></div><details class="kb-advanced"><summary>索引与文字识别</summary><p>普通解析已可关键词检索。向量索引与 OCR 使用外部服务，逐份明确确认后执行。失败或未知请求不会自动付费重试。</p><p>OCR ${caps.ocr?'已配置，连接未验证':'未配置'}。OCR 当前仅支持 PDF；PPT 图示请核对原件，或转为 PDF 后另行导入。</p><label><input id="kbPaidConfirm" type="checkbox">确认本次索引或识别的外部 API 调用</label></details></section></div>`;
  $('#kbUploadChapter').value=uploadChapter;$('#kbMode').value=searchMode;$('.kb-api-confirm').hidden=searchMode==='lexical';$('.kb-api-confirm input').required=searchMode!=='lexical';$('.kb-api-confirm input').checked=externalConfirmed;$('#kbPaidConfirm').checked=paidConfirmed;
  rows();showResults();
 }
 function rows(){const target=$('#kbDocuments');if(!target)return;const docs=(data?.documents||[]).filter(d=>!d.archived&&(!chapter||d.chapter===chapter)&&(!filter||d.name.toLowerCase().includes(filter.toLowerCase())));
  target.innerHTML=docs.map(d=>{const j=d.task,active=j&&!['succeeded','failed','cancelled','unknown'].includes(j.status);return `<article class="kb-document"><div><h3>${e(d.name)}</h3><p>${e(d.chapter||'未分章')} · ${(Number(d.size||0)/1048576).toFixed(2)} MB · ${d.sourceCount} 个片段</p><span class="kb-status ${j?.status==='failed'?'kb-status-error':''}">${e(active?labels[j.status]:j&&['failed','cancelled','unknown'].includes(j.status)?labels[j.status]:d.status||'待解析')}</span>${active?`<progress max="100" value="${Number(j.progress?.percent)||0}" aria-label="${e(d.name)}处理进度"></progress>`:''}${j?.error?`<small>处理代码：${e(j.error)}</small>`:''}${d.quality?.warnings?.length?'<small>部分内容需要核对原件或文字识别</small>':''}<small>向量索引：${d.vectorReady?'当前模型已就绪':'未建立当前模型索引'}</small></div><div class="kb-row-actions">${button('查看原文','read',d.id)}${button('用于问答','chat',d.id)}${active?button('取消任务','cancel',j.id):`<details><summary>处理</summary>${j&&['failed','cancelled'].includes(j.status)&&j.type==='rag-parse'?button('重试解析','retry',j.id):''}${button('重新解析','parse',d.id)}${button('建立向量索引','index',d.id,data?.capabilities.embedding?'':'disabled')}${button('文字识别 OCR','ocr',d.id,data?.capabilities.ocr&&d.kind==="pdf"?'':'disabled')}</details>`}</div></article>`;}).join('')||'<div class="empty-state"><h3>从一份课件开始</h3><p>添加课程资料后，这里会显示解析状态与原文片段。</p></div>';
 }
 function showResults(){const target=$('#kbResults');if(!target)return;if(!results){target.innerHTML='';return;}const warnings={EMBEDDING_UNAVAILABLE:'向量未配置，本次使用关键词检索',VECTOR_INDEX_UNAVAILABLE:'未建立当前模型索引，本次使用关键词检索',RERANK_UNAVAILABLE:'重排服务不可用',VECTOR_API_UNAVAILABLE:'向量调用未完成，请到任务与用量核对',RERANK_API_UNAVAILABLE:'重排调用未完成，请到任务与用量核对'};
  target.innerHTML=`${results.warnings.map(w=>`<p class="kb-warning">${e(warnings[w]||w)}</p>`).join('')}<p>${results.sources.length?'找到 '+results.sources.length+' 条原文依据':'没有找到相关原文。请调整关键词或章节范围。'}</p>${results.sources.map(s=>`<article class="kb-result"><strong>${e(s.title)}</strong><small>${e(s.location)} · 内容修订 ${s.documentRevision}</small><blockquote>${e(s.quote)}</blockquote>${button('核对原文','source',s.id)}</article>`).join('')}`;
 }
 function dialog(title,content){if(!reader){reader=document.createElement('dialog');reader.className='source-dialog kb-dialog';reader.id='kbDialog';document.body.append(reader);}reader.setAttribute('aria-label',title);reader.innerHTML=`<div class="dialog-head"><strong>${e(title)}</strong>${button('关闭','close')}</div><div class="c-dialog-body">${content}</div>`;if(!reader.open)reader.showModal();}
 async function select(id){if(busy||state.pending||state.working){toast('请先等待当前操作完成');return;}const c=bases.find(b=>b.id===id)||store.courses.find(c=>c.id===id);if(!c||!store.adoptCourse(c)||!store.switchCourse(id))return;render();}
 async function action(action,id){const g=epoch,idCourse=course;let ownsBusy=false;
  try{
   if(action==='close'){reader.close();return;}if(action==='jump-search'){$('#kbSearchHeading')?.scrollIntoView({behavior:'instant',block:'start'});$('#kbSearchHeading')?.focus({preventScroll:true});return;}
   if(action==='refresh'){await load();return;}
   if(action==='create'){dialog('新建知识库','<form id="kbCreate"><label class="form-field">知识库名称<input name="name" maxlength="60" required placeholder="例如：数据结构与算法"></label><label class="form-field">说明<textarea name="description" maxlength="4000" rows="3"></textarea></label><p>创建独立课程范围，已有资料与私人记录会保留。</p><button class="button button-blue button-small">确认创建</button></form>');return;}
   if(busy)throw Error('请等待当前操作完成');
   if(action==='chat'){const doc=data.documents.find(d=>d.id===id);if(!doc?.sourceCount)throw Error('请等待解析完成后再使用');const current=await api('documents?'+new URLSearchParams({courseId:idCourse}));if(!valid(g))return;state.documents=[...state.documents.filter(d=>!d.remote),...current.documents];state.selectedDocuments=[id];store.persist();try{localStorage.setItem('xueya-c-learning:'+course+':scope:'+state.sessionId,JSON.stringify([id]));}catch{}location.hash='space/chat';window.dispatchEvent(new Event('xueya:scope-change'));return;}
   if(action==='read'||action==='source'){
    const r=await api((action==='read'?'library/read?'+new URLSearchParams({documentId:id,courseId:idCourse}):'rag/read?'+new URLSearchParams({sourceId:id,courseId:idCourse})));if(!valid(g))return;
    const doc=r.document,blocks=action==='read'?r.artifact?.blocks||[]:[r.parent];dialog(doc?.name||r.source?.title||'原文依据',`<p>正文来自原课件；图示请下载原件核对。</p>${button('下载原件','original',doc?.id||r.source.documentId)}${blocks.map(b=>`<article class="kb-original"><small>${b.page?'实际第 '+b.page+' 页':'字符 '+b.start+'–'+b.end}</small><p>${e(b.text)}</p></article>`).join('')||'<p>暂无可阅读正文，解析可能尚未完成。</p>'}`);return;
   }
   if(action==='original'){const response=await fetch('/api/platform/rag/original?'+new URLSearchParams({courseId:idCourse,documentId:id}),{headers:{'X-Xueya-Token':token}});if(!response.ok)throw Error('原件暂不可用');const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download=data.documents.find(d=>d.id===id)?.name||'原件';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;}
   let value={courseId:idCourse};busy=true;ownsBusy=true;
   if(action==='cancel'||action==='retry')await api('knowledge/task',{...value,id,action});
   else if(['parse','index','ocr'].includes(action)){const d=data.documents.find(d=>d.id===id),confirmed=!!$('#kbPaidConfirm')?.checked;paidConfirmed=false;if($('#kbPaidConfirm'))$('#kbPaidConfirm').checked=false;await api('knowledge/process',{...value,documentId:id,version:d.version,action,idempotencyKey:uid(),confirmedExternal:confirmed});}
   if(valid(g)){notice='操作已提交，任务状态将自动刷新。';results=null;await load(false);}
  }catch(error){if(g===epoch)toast(error.message);}finally{if(ownsBusy)busy=false;}
 }
 async function upload(files){if(busy)return;const g=epoch,id=course,ch=$('#kbUploadChapter').value;busy=true;notice='正在上传课件…';draw();
  try{for(const file of files){if(!valid(g))break;if(file.name.startsWith('~$'))continue;const key='kb-file-'+Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer()))).map(b=>b.toString(16).padStart(2,'0')).join('')+'-'+Array.from(new TextEncoder().encode(file.name+'|'+ch)).reduce((h,b)=>(h*31+b)>>>0,0);if(file.size>10485760||/\.(txt|md)$/i.test(file.name)&&file.size>1048576)throw Error(file.name+' 超过文件大小限制');notice='正在上传：'+file.name;if($('#kbNotice'))$('#kbNotice').textContent=notice;await api('knowledge/upload?'+new URLSearchParams({courseId:id,name:file.name,chapter:ch}),file,{headers:{'Idempotency-Key':key}});}if(valid(g))notice='上传完成，正在后台解析。可离开本页，稍后回来查看。';}
  catch(error){if(valid(g))notice='本批上传已停止：'+error.message+'。已接收的资料保留；重新选择同一批文件不会重复导入。';}
  finally{busy=false;if(valid(g)){draw();await load(false);}}
 }
 document.addEventListener('click',event=>{const b=event.target.closest('[data-kb]');if(b){event.preventDefault();void action(b.dataset.kb,b.dataset.id);}});
 document.addEventListener('change',event=>{const t=event.target;if(t.id==='kbFiles')void upload([...t.files]);if(t.id==='kbBase')void select(t.value);if(t.id==='kbChapter'){chapter=t.value;results=null;rows();showResults();}if(t.id==='kbPaidConfirm')paidConfirmed=t.checked;if(t.name==='confirmedExternal'&&t.closest('#kbSearch'))externalConfirmed=t.checked;if(t.id==='kbMode'){searchMode=t.value;const label=$('.kb-api-confirm');label.hidden=t.value==='lexical';label.querySelector('input').required=t.value!=='lexical';}});
 document.addEventListener('input',event=>{if(event.target.id==='kbFilter'){filter=event.target.value;rows();}if(event.target.id==='kbUploadChapter')uploadChapter=event.target.value;if(event.target.id==='kbQuery')query=event.target.value;});
 document.addEventListener('submit',async event=>{
  const f=event.target;if(!['kbSearch','kbCreate'].includes(f.id))return;event.preventDefault();if(busy)return;const g=epoch,id=course,v=Object.fromEntries(new FormData(f));busy=true;const submit=f.querySelector('button');submit.disabled=true;
  try{if(f.id==='kbCreate'){f.dataset.key||=uid();const r=await api('knowledge/create',{...v,idempotencyKey:f.dataset.key});if(!valid(g))return;bases=(await api('knowledge/bases')).bases;if(!valid(g))return;reader.close();busy=false;await select(r.base.id);}
   else{results=null;showResults();externalConfirmed=false;$('.kb-api-confirm input').checked=false;const r=await api('knowledge/search',{courseId:id,query:v.query,chapter,mode:v.mode,confirmedExternal:v.confirmedExternal==='on'});if(valid(g)){results=r.evidence;showResults();}}}
  catch(error){if(g===epoch)toast(error.message);}finally{busy=false;submit.disabled=false;}
 });
 return {mount(){clearTimeout(timer);epoch++;loading=false;if(course!==state.courseId){course=state.courseId;data=null;results=null;chapter='';filter='';query='';notice='';reader?.close();}if(state.view!=='knowledge')return;if(location.protocol==='file:'){$('#spaceContent').innerHTML='<div class="panel"><h1>知识库</h1><p>请通过本机服务打开，离线预览不能读取知识库。</p></div>';return;}const root=document.createElement('div');root.id='knowledgeWorkspace';$('#spaceContent').append(root);draw();void load();}};
}};
})();
