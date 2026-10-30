/* Knowledge bases are existing courses. Never keep a second copy of their sources. */
(() => {
'use strict';
window.XueyaKnowledgeBase={create({state,store,toast,render}){
 const e=window.XueyaRich.escape,$=s=>document.querySelector(s),uid=()=>crypto.randomUUID();
 const labels={queued:'等待处理',running:'正在处理',cancelling:'正在取消',succeeded:'处理完成',failed:'处理失败',cancelled:'已取消',unknown:'结果待核对'};
 const errors={AUTH_REQUIRED:'会话已变化，请刷新页面',EXTERNAL_CONFIRMATION_REQUIRED:'请先确认外部 API 调用',VERSION_CONFLICT:'资料已更新，请刷新后再操作',EMBEDDING_UNAVAILABLE:'向量服务未配置，仍可使用关键词检索',OCR_UNAVAILABLE:'文字识别服务未配置',KNOWLEDGE_REVIEW_REQUIRED:'请先校正并确认当前资料修订',OCR_SUBMISSION_UNKNOWN:'提交结果未知，请先核对平台任务，不能自动重新提交',OCR_REMOTE_FAILED:'远端解析失败，请核对平台任务',OCR_TASK_RECEIPT_MISSING:'缺少远端任务回执，请核对用量',PAID_RETRY_FORBIDDEN:'请先到任务与用量核对外部请求',TEMPORARY_FILE_FORBIDDEN:'已跳过 Office 临时文件',FILE_TOO_LARGE:'PDF 最大64MB，其他资料最大10MB，文本最大1MB',REPLACEMENT_NOT_READY:'新 PDF 仍有未识别页面，请先完成文字识别；旧 PPT 尚未移除',OCR_PAGE_LIMIT:'每次最多识别64页，请分批处理',OCR_BATCH_TOO_LARGE:'本批图片过大，请减少识别页数',INVALID_OCR_PAGES:'所选页面已处理或发生变化，请刷新',OCR_PDF_REQUIRED:'文字识别仅适用于PDF',JOB_NOT_RETRYABLE:'该任务当前不能重试',IDEMPOTENCY_CONFLICT:'同一次操作的内容已变化，请重新操作'};
 let listOpen=false,uploadOpen=false;
 let course='',epoch=0,data=null,bases=[],timer=null,loading=false,busy=false,reader=null,chapter='',filter='',query='',results=null,notice='',token='',uploadChapter='',searchMode='lexical',externalConfirmed=false,paidConfirmed=false;
 const button=(text,action,id='',extra='')=>`<button type="button" class="button button-outline button-small" data-kb="${action}" data-id="${e(id)}" ${extra}>${e(text)}</button>`;
 const valid=g=>g===epoch&&state.view==='knowledge'&&course===state.courseId;
 const statusText=d=>!d.sourceCount&&d.kind==='pdf'&&d.review?.pendingPages.length?'待文字识别 · '+d.review.pendingPages.length+' 页':d.sourceCount&&d.review?.pendingPages.length?'已解析 · '+d.review.pendingPages.length+' 页待识图或空白核对':!d.sourceCount&&d.review?.blankPages.length?'已核对空白页 · 无可检索正文':d.status||'待解析';
 function pageSelectionText(d){const p=d.pageSelection;if(!p)return '';const ranges=[];for(const n of p.pages){const last=ranges[ranges.length-1];if(last&&last[1]+1===n)last[1]=n;else ranges.push([n,n]);}return '仅收录原PDF第 '+ranges.map(([a,b])=>a===b?a:a+'—'+b).join('、')+' 页 · 原件共 '+p.originalPageCount+' 页';}
 let visualPreview=null,visualPack=null,replacementPreview=null,reviewDoc=null,reviewArtifact=null;
 async function api(path,value,options={}){
  if(!token){const r=await fetch('/api/platform/bootstrap');if(!r.ok)throw Error('请启动本地服务并登录后使用知识库');token=(await r.json()).token;}
  const response=await fetch('/api/platform/'+path,{method:value!==undefined?'POST':'GET',headers:{'X-Xueya-Token':token,...(value!==undefined&&!(value instanceof File)?{'Content-Type':'application/json'}:{}),...options.headers},body:value===undefined?undefined:value instanceof File?value:JSON.stringify(value)});
  const result=await response.json();if(!response.ok||!result.ok)throw Error(errors[result.error]||result.error||'操作未完成');return result;
 }
 let countCourse='',countAt=0,countLoading=false;
 async function refreshCount(){
  if(!window.XueyaPlatform?.available||state.view==='knowledge'||countLoading||countCourse===state.courseId&&Date.now()-countAt<15000)return;
  const id=state.courseId;countLoading=true;
  try{const result=await api('knowledge/catalog?'+new URLSearchParams({courseId:id}));if(state.courseId!==id)return;state.documentCount=result.summary.documents;countCourse=id;countAt=Date.now();if(!window.XueyaWorkspaceAppearance.isOriginal()&&$('#documentCount'))$('#documentCount').textContent=state.documentCount;document.querySelectorAll('[data-document-total]').forEach(el=>el.textContent=state.documentCount+' 份资料');store.persist();}catch{}finally{countLoading=false;if(state.courseId!==id)void refreshCount();}
 }
 function demoNotice(){const d=data?.demoImport;if(!d)return '';const active=['preparing','running'].includes(d.status),total=Number(d.total)||17,done=Number(d.completed)||0;
  if(active)return `<div class="kb-demo-import" data-demo-status="${e(d.status)}"><strong>${d.status==='preparing'?'首次启动，正在校验演示课件':'正在准备演示知识库'}</strong><p>已准备 ${done} / ${total} 份课件${d.currentFile?' · '+e(d.currentFile):''}。完成后可直接检索，无需模型密钥。可离开本页，后台会继续处理。</p><progress max="${total}" value="${done}" aria-label="演示课件导入进度"></progress></div>`;
  if(d.status==='completed')return `<div class="kb-demo-import" data-demo-status="completed">已完成首次课件准备。当前知识库有 ${Number(data?.summary.documents)||0} 份资料，可供问答参考，也可以查看资料原文。</div>`;
  if(['failed','interrupted'].includes(d.status)){const reason=d.error?.includes('HASH')?'文件校验未通过，请重新下载完整仓库。':d.error?.includes('UNAVAILABLE')?'课件文件缺失或无法读取，请重新下载完整仓库。':'请检查当前资料后重试；你已修改的内容不会被覆盖。';return `<div class="kb-demo-import" data-demo-status="${e(d.status)}"><strong>演示课件尚未准备完成</strong><p>已完成的资料会保留。${reason}</p>${button('重试准备演示课件','demo-retry')}</div>`;}
  return '';}
 function schedule(){clearTimeout(timer);if((data?.summary.processing||data?.practiceGenerations?.some(g=>['waiting_parse','generating'].includes(g.status))||['preparing','running'].includes(data?.demoImport?.status))&&state.view==='knowledge')timer=setTimeout(()=>void load(false),1500);}
 function generationRows(){const target=$('#kbPracticeGeneration');if(!target)return;const labels={waiting_parse:'等待解析后自动出题',generating:'正在生成题库',succeeded:'Hot 100 和基础 100 已就绪',model_unavailable:'请先配置模型，再到练习页继续生成',insufficient_material:'资料内容不足，无法可靠生成200道不同题',unknown:'调用结果待核对，可到练习页查看并继续',failed:'出题未完成，可到练习页继续',cancelled:'出题已停止',stale:'原文已更新，旧题库已停用'};target.innerHTML=(data?.practiceGenerations||[]).map(g=>`<p><strong>${e(g.name)}</strong> · ${e(labels[g.status]||g.status)} · ${Number(g.completed)||0}/200 <a class="text-link" href="#space/practice">查看练习 →</a></p>`).join('');}
 async function load(full=true){
  if(loading)return;loading=true;const g=epoch,id=course;
  try{
   if(full){bases=(await api('knowledge/bases')).bases;if(!valid(g))return;const local=store.courses.find(c=>c.id===id);if(!bases.some(c=>c.id===id)&&local){await api('courses',{id,name:local.name});bases=(await api('knowledge/bases')).bases;}}
   const next=await api('knowledge/catalog?'+new URLSearchParams({courseId:id}));if(!valid(g))return;
   if(data&&JSON.stringify(data.documents.map(d=>[d.id,d.version,d.archived]))!==JSON.stringify(next.documents.map(d=>[d.id,d.version,d.archived])))results=null;
   data=next;state.documentCount=data.summary.documents;countCourse=id;countAt=Date.now();store.persist();
   if($('#documentCount'))$('#documentCount').textContent=data.summary.documents;
   if(!full&&$('#kbDocuments')){
    rows();showResults();generationRows();$('.kb-stats')?.querySelectorAll('strong').forEach((el,i)=>el.textContent=[data.summary.documents,data.summary.sources,data.summary.processing,data.summary.needsReview][i]);
    if($('#kbNotice'))$('#kbNotice').innerHTML=e(notice)+demoNotice();
    const select=$('#kbChapter');select.innerHTML='<option value="">全部章节</option>'+[...new Set(data.documents.filter(d=>!d.archived).map(d=>d.chapter).filter(Boolean))].map(c=>`<option value="${e(c)}">${e(c)}</option>`).join('');select.value=chapter;
   }else draw();schedule();
  }catch(error){if(valid(g)){notice=error.message;draw();}}
  finally{if(g===epoch)loading=false;}
 }
 function draw(){
  const root=$('#knowledgeWorkspace');if(!root)return;
  const s=data?.summary||{documents:0,sources:0,processing:0,needsReview:0},caps=data?.capabilities||{};
  root.innerHTML=`<div class="view-heading"><div><h1>课程资料</h1><p>上传课程资料，让每一次回答都有参考。</p></div><div class="heading-actions">${button('刷新','refresh')}<button type="button" class="button button-blue button-small" data-kb="create">新建资料库</button></div></div>
   <section class="panel kb-overview"><div class="kb-scope"><label class="form-field">当前课程资料<select id="kbBase">${[...bases,...store.courses.filter(c=>!c.archived&&!bases.some(b=>b.id===c.id))].map(c=>`<option value="${e(c.id)}" ${c.id===course?'selected':''}>${e(c.name)}</option>`).join('')}</select></label><p>与当前课程共用资料，问答与学习成果可直接使用。</p></div><div class="kb-stats">${[['当前资料',s.documents]].map(([label,n])=>`<div><strong>${n}</strong><span>${label}</span></div>`).join('')}</div></section>
   <div id="kbNotice" role="status" aria-live="polite">${e(notice||(!data?'正在加载知识库…':''))}${demoNotice()}</div>
   <div id="kbPracticeGeneration" class="practice-generation" role="status"></div><div class="kb-entry-actions">${button(uploadOpen?'收起上传':'上传资料','toggle-upload')}${button(listOpen?'收起资料列表':'查看资料','toggle-list')}</div><section class="panel kb-import" ${uploadOpen?'':'hidden'}><div><h2>添加学习资料</h2><p>PDF 最大64MB · PPTX、DOCX 最大10MB · TXT、Markdown 最大1MB</p></div><label class="form-field">所属章节<input id="kbUploadChapter" maxlength="200" placeholder="可选；留空时识别文件名中的章节或周次"></label><input id="kbFiles" type="file" multiple accept=".pdf,.pptx,.docx,.txt,.md" ${busy?'disabled':''}><small>上传后先解析并进入人工复核。确认当前文字后可建立向量索引；OCR 和向量调用需要单独确认。资料练习接入准备中，当前不自动出题。</small></section>
   <div class="kb-columns" ${listOpen?'':'hidden'}><section class="panel kb-documents"><div class="kb-section-heading"><h2>资料列表</h2><a class="text-link" href="#space/library/manage">阅读与版本管理 →</a></div><div class="kb-filters"><label class="form-field">章节<select id="kbChapter"><option value="">全部章节</option>${[...new Set((data?.documents||[]).filter(d=>!d.archived).map(d=>d.chapter).filter(Boolean))].map(c=>`<option value="${e(c)}" ${c===chapter?'selected':''}>${e(c)}</option>`).join('')}</select></label><label class="form-field">筛选文件<input id="kbFilter" type="search" value="${e(filter)}" placeholder="文件名"></label></div><div id="kbDocuments"></div><details class="kb-advanced"><summary>高级处理设置</summary><label><input id="kbPaidConfirm" type="checkbox">确认下一次向量索引或文字识别调用外部 API，可能产生费用</label></details></section>
   </div><section class="panel kb-search"><h2 id="kbSearchHeading">测试知识库检索</h2><p>OCR：${e(caps.ocrModel||'未配置')} · 向量：${e(caps.embeddingModel||'未配置')}。本阶段索引输入为校正文字。</p><form id="kbSearch"><label class="form-field">测试问题<input id="kbQuery" name="query" required maxlength="4000" value="${e(query)}" placeholder="例如：为什么栈是后进先出？"></label><label class="form-field">检索方式<select id="kbMode" name="mode"><option value="lexical">关键词</option><option value="hybrid">关键词＋向量</option><option value="vector">向量</option></select></label><label class="kb-api-confirm" ${searchMode==='lexical'?'hidden':''}><input type="checkbox" name="confirmedExternal" ${searchMode!=='lexical'?'required':''}>确认将问题发送给外部向量服务，可能产生费用</label><button class="button button-blue">测试检索</button></form><div id="kbResults"></div></section>`;
  $('#kbMode').value=searchMode;$('#kbUploadChapter').value=uploadChapter;$('#kbPaidConfirm').checked=paidConfirmed;
  rows();showResults();generationRows();
 }
 function rows(){const target=$('#kbDocuments');if(!target)return;const docs=(data?.documents||[]).filter(d=>!d.archived&&(!chapter||d.chapter===chapter)&&(!filter||d.name.toLowerCase().includes(filter.toLowerCase())));
  target.innerHTML=docs.map(d=>{const j=d.task,active=j&&!['succeeded','failed','cancelled','unknown'].includes(j.status);return `<article class="kb-document"><div><h3>${e(d.name)}</h3><p>${e(d.chapter||'未分章')} · ${(Number(d.size||0)/1048576).toFixed(2)} MB · ${d.sourceCount} 个片段</p><span class="kb-status ${j?.status==='failed'?'kb-status-error':''}">${e(active?labels[j.status]:j&&['failed','cancelled','unknown'].includes(j.status)?labels[j.status]:statusText(d))}</span>${active?`<progress max="100" value="${Number(j.progress?.percent)||0}" aria-label="${e(d.name)}处理进度"></progress>`:''}${j?.error?`<small>处理代码：${e(j.error)}</small>`:''}${d.quality?.warnings?.length?`<small>${d.kind==='pdf'?'扫描PDF仍有待识别页，请配置OCR；识别前不能作为完整知识库':'有页面尚无可读文字：可能为图片或空白，需逐页核对'}</small>`:''}${d.review?.transcribedPages.length?`<small>图片转写：${d.review.transcribedPages.length} 页（辅助识图，未独立人审）</small>`:''}${d.review?.reviewedImages?`<small>图片核查：${d.review.reviewedImages} 个引用 · 补充 ${d.review.supplementedPages.length} 页正文${d.review.partialImages?` · ${d.review.partialImages} 个部分转写`:""}${d.review.unreadableImages?` · ${d.review.unreadableImages} 个无法辨认`:""}（辅助识图，未独立人审）</small>`:''}${d.review?.blankPages.length?`<small>已核对 ${d.review.blankPages.length} 个空白页</small>`:''}${d.ocrPreparation?`<small class="kb-warning">${e(d.ocrPreparation.notice)} · 可随时查看原PDF</small>`:''}${d.pageSelection?`<small class="kb-page-selection">${e(pageSelectionText(d))}</small>`:''}<small>${d.reviewReady===false?'待校正与确认：当前修订尚未用于检索':'当前修订可用于检索'} · 向量索引：${d.vectorReady?'当前模型已就绪':'未建立当前模型索引'}</small></div><div class="kb-row-actions">${button('查看原文','read',d.id)}${button('校正与确认','review',d.id,d.sourceCount?'':'disabled')}${button('用于问答','chat',d.id,d.sourceCount&&d.reviewReady!==false?'':'disabled')}${active?button('取消任务','cancel',j.id):`<details><summary>处理</summary>${j&&['failed','cancelled'].includes(j.status)&&['rag-parse','rag-visual-apply'].includes(j.type)?button('重试本地处理','retry',j.id):''}${d.kind==='pptx'?button('图片文字补录','visual-review',d.id):''}${button('重新解析','parse',d.id)}${button('建立向量索引','index',d.id,data?.capabilities.embedding&&d.reviewReady!==false?'':'disabled')}${button('选择识别页（最多20页）','ocr-select',d.id,data?.capabilities.ocr&&d.kind==="pdf"&&d.review?.pendingPages.length?'':'disabled')}${d.kind==='pdf'&&data.documents.some(old=>old.kind==='pptx'&&!old.archived)?button('用此PDF替换旧PPT','replace-ppt',d.id,d.sourceCount&&!d.review?.pendingPages.length?'':'disabled'):''}</details>`}</div></article>`;}).join('')||'<div class="empty-state"><h3>从一份课件开始</h3><p>添加课程资料后，这里会显示解析状态与原文片段。</p></div>';
 }
 function showResults(){const target=$('#kbResults');if(!target)return;if(!results){target.innerHTML='';return;}const warnings={EMBEDDING_UNAVAILABLE:'向量未配置，本次使用关键词检索',VECTOR_INDEX_UNAVAILABLE:'未建立当前模型索引，本次使用关键词检索',RERANK_UNAVAILABLE:'重排服务不可用',VECTOR_API_UNAVAILABLE:'向量调用未完成，请到任务与用量核对',RERANK_API_UNAVAILABLE:'重排调用未完成，请到任务与用量核对'};
  target.innerHTML=`${results.warnings.map(w=>`<p class="kb-warning">${e(warnings[w]||w)}</p>`).join('')}<p>${results.sources.length?'找到 '+results.sources.length+' 条原文依据':'没有找到相关原文。请调整关键词或章节范围。'}</p>${results.sources.map(s=>`<article class="kb-result"><strong>${e(s.title)}</strong><small>${e(s.location)} · 内容修订 ${s.documentRevision}</small><blockquote>${e(s.quote)}</blockquote>${button('核对原文','source',s.id)}</article>`).join('')}`;
 }
 function dialog(title,content){if(!reader){reader=document.createElement('dialog');reader.className='source-dialog kb-dialog';reader.id='kbDialog';document.body.append(reader);}reader.setAttribute('aria-label',title);reader.innerHTML=`<div class="dialog-head"><strong>${e(title)}</strong>${button('关闭','close')}</div><div class="c-dialog-body">${content}</div>`;if(!reader.open)reader.showModal();}
 async function select(id){if(busy||state.pending||state.working){toast('请先等待当前操作完成');return;}const c=bases.find(b=>b.id===id)||store.courses.find(c=>c.id===id);if(!c||!store.adoptCourse(c)||!store.switchCourse(id))return;render();}
 async function action(action,id){const g=epoch,idCourse=course;let ownsBusy=false;
  try{
   if(action==='close'){reader.close();return;}if(action==='jump-search'){$('#kbSearchHeading')?.scrollIntoView({behavior:'instant',block:'start'});$('#kbSearchHeading')?.focus({preventScroll:true});return;}
   if(action==='toggle-list'){listOpen=!listOpen;draw();return;}if(action==='toggle-upload'){uploadOpen=!uploadOpen;draw();return;}
   if(action==='refresh'){await load();return;}
   if(action==='create'){dialog('新建知识库','<form id="kbCreate"><label class="form-field">知识库名称<input name="name" maxlength="60" required placeholder="例如：数据结构与算法"></label><label class="form-field">说明<textarea name="description" maxlength="4000" rows="3"></textarea></label><p>创建独立课程范围，已有资料与私人记录会保留。</p><button class="button button-blue button-small">确认创建</button></form>');return;}
   if(busy)throw Error('请等待当前操作完成');
   if(action==='demo-retry'){busy=true;ownsBusy=true;await api('knowledge/demo-retry',{courseId:idCourse,confirmed:true});if(valid(g)){notice='正在重新准备演示资料。';await load(false);}return;}
   if(action==='visual-review'){
    const response=await api('knowledge/visual-pack?'+new URLSearchParams({courseId:idCourse,documentId:id}));if(!valid(g))return;visualPack=response.pack;visualPreview=null;
    dialog('图片文字补录与空白核对',`<p>普通正文和历史补录保留。可追加已有正文页的图片内容；背景、装饰、无法辨认的图片只记核查状态，不作为知识证据。本工具导入已完成的视觉核查，不调用 OCR 或聊天模型 API。</p><p>待核对页：${visualPack.pages.filter(p=>p.needsOcr).map(p=>p.page).join('、')||'无'}。含图页面不等于已被完整理解。</p><form id="kbVisualForm"><label class="form-field">选择识图结果 JSON<input id="kbVisualFile" type="file" accept=".json,application/json"></label><label class="form-field">或粘贴转写内容<textarea name="reviewJson" rows="9" required placeholder="通过导出工具生成草稿，完成图片核对后导入"></textarea></label><small>保留 documentId/version/fileHash/page/imageHashes；reviewer 为 assistant-in-session 或 human。blank 仅用于无图片的空白页；supplement 用 imageReviews 逐图追加，已核查图片不可重复补入。</small><button class="button button-blue button-small">预览补录</button></form>`);return;
   }
   if(action==='visual-apply'){
    if(!visualPreview)throw Error('请重新预览');busy=true;ownsBusy=true;
    await api('knowledge/visual-apply',{courseId:idCourse,previewId:visualPreview.previewId,confirmed:true});if(!valid(g))return;visualPreview=null;reader.close();notice='图片转写已提交；原资料和历史版本保留，任务完成后自动更新片段。';await load(false);return;
   }
   if(action==='replace-ppt'){
    const oldDocumentIds=data.documents.filter(d=>d.kind==='pptx'&&!d.archived).map(d=>d.id);
    const response=await api('knowledge/replacement-preview',{courseId:idCourse,targetDocumentId:id,oldDocumentIds});if(!valid(g))return;replacementPreview=response.preview;
    dialog('确认更换课程资料',`<p>新资料：${e(replacementPreview.target.name)}。将从当前检索移除以下 ${replacementPreview.previous.length} 份 PPT，原件与历史保留供恢复，其他学习记录保留。</p><ul>${replacementPreview.previous.map(d=>`<li>${e(d.name)}</li>`).join('')}</ul>${button('确认使用PDF并移除旧PPT','replace-apply')}`);return;
   }
   if(action==='replace-apply'){
    if(!replacementPreview)throw Error('请重新预览');busy=true;ownsBusy=true;
    await api('knowledge/replacement-apply',{courseId:idCourse,previewId:replacementPreview.previewId,confirmed:true});if(!valid(g))return;replacementPreview=null;reader.close();notice='已更换为PDF资料，旧PPT已退出当前检索，历史保留。';results=null;await load(false);return;
   }
   if(action==='review'){
    const r=await api('rag/export?'+new URLSearchParams({courseId:idCourse,documentId:id}));if(!valid(g))return;
    reviewDoc=r.document;reviewArtifact=r.artifact;
    dialog('校正与确认 · '+reviewDoc.name,`<p>请对照原件检查定义、条件、公式和代码。每次保存产生新修订，向量索引失效；确认只覆盖当前已提取文字，未识别页仍需继续处理。</p>${button('下载原件对照','original',id)}<form id="kbCorrection"><label class="form-field">选择正文块<select name="blockId" id="kbReviewBlock">${reviewArtifact.blocks.map(b=>`<option value="${e(b.id)}">${b.page?'第 '+b.page+' 页':'正文'} · ${e(b.type)} · ${e(b.text.slice(0,45))}</option>`).join('')}</select></label><label class="form-field">校正内容<textarea name="replacement" id="kbReviewText" rows="12" maxlength="100000" required></textarea></label><label class="form-field">修订原因<input name="reason" maxlength="1000" required value="对照原件校正"></label><button class="button button-blue">保存校正</button></form><form id="kbReviewConfirm"><label><input type="checkbox" required>我已核对当前提取文字及关键条件，确认此修订可用于检索</label><button class="button button-blue">确认当前修订</button></form>`);
    if($('#kbReviewText'))$('#kbReviewText').value=reviewArtifact.blocks[0]?.text||'';return;
   }
   if(action==='ocr-select'){
    const d=data.documents.find(d=>d.id===id);reviewDoc=d;
    dialog('选择本批 OCR 页面',`<p>仅处理所选原书页码，每批最多20页。MinerU按原页建立任务，已完成结果可复用。未知任务需先核对用量，再主动继续。</p><form id="kbOcrBatch"><label class="form-field">页码（例如 2,4-8）<input name="pages" required value="${e(d.review.pendingPages.slice(0,15).join(','))}"></label><label><input name="confirmedExternal" type="checkbox" required>确认这些页面将发送给 ${e(data.capabilities.ocrModel||'外部OCR服务')}，可能产生费用</label><button class="button button-blue">提交本批</button></form>`);return;
   }
   if(action==='chat'){const doc=data.documents.find(d=>d.id===id);if(!doc?.sourceCount||doc.reviewReady===false)throw Error('请等待解析完成后再使用');const current=await api('documents?'+new URLSearchParams({courseId:idCourse}));if(!valid(g))return;state.documents=[...state.documents.filter(d=>!d.remote),...current.documents];state.selectedDocuments=[id];store.persist();try{localStorage.setItem('xueya-c-learning:'+course+':scope:'+state.sessionId,JSON.stringify([id]));}catch{}location.hash='space/ask';window.dispatchEvent(new Event('xueya:scope-change'));return;}
   if(action==='read'||action==='source'){
    const r=await api((action==='read'?'library/read?'+new URLSearchParams({documentId:id,courseId:idCourse}):'rag/read?'+new URLSearchParams({sourceId:id,courseId:idCourse})));if(!valid(g))return;
    const doc=r.document,blocks=action==='read'?r.artifact?.blocks||[]:[r.parent];dialog(doc?.name||r.source?.title||'原文依据',`<p>正文来自原课件；图示请下载原件核对。</p>${button('下载原件','original',doc?.id||r.source.documentId)}${blocks.map(b=>`<article class="kb-original"><small>${b.page?'实际第 '+b.page+' 页':'字符 '+b.start+'–'+b.end}</small><p>${e(b.text)}</p></article>`).join('')||'<p>暂无可阅读正文，解析可能尚未完成。</p>'}`);return;
   }
   if(action==='original'){const response=await fetch('/api/platform/rag/original?'+new URLSearchParams({courseId:idCourse,documentId:id}),{headers:{'X-Xueya-Token':token}});if(!response.ok)throw Error('原件暂不可用');const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download=data.documents.find(d=>d.id===id)?.name||'原件';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;}
   let value={courseId:idCourse};busy=true;ownsBusy=true;
   if(action==='cancel'||action==='retry')await api('knowledge/task',{...value,id,action});
   else if(['parse','index','ocr'].includes(action)){const d=data.documents.find(d=>d.id===id),confirmed=!!$('#kbPaidConfirm')?.checked;paidConfirmed=false;if($('#kbPaidConfirm'))$('#kbPaidConfirm').checked=false;await api('knowledge/process',{...value,documentId:id,version:d.version,action,idempotencyKey:uid(),confirmedExternal:confirmed,...(action==='ocr'?{pages:d.review.pendingPages.slice(0,16)}:{})});}
   if(valid(g)){notice='操作已提交，任务状态将自动刷新。';results=null;await load(false);}
  }catch(error){if(g===epoch)toast(error.message);}finally{if(ownsBusy)busy=false;}
 }
 async function upload(files){if(busy)return;const g=epoch,id=course,ch=$('#kbUploadChapter').value;busy=true;notice='正在上传课件…';draw();
  try{for(const file of files){if(!valid(g))break;if(file.name.startsWith('~$'))continue;const key='kb-file-'+Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer()))).map(b=>b.toString(16).padStart(2,'0')).join('')+'-'+Array.from(new TextEncoder().encode(file.name+'|'+ch)).reduce((h,b)=>(h*31+b)>>>0,0);if(file.size>(/\.pdf$/i.test(file.name)?67108864:10485760)||/\.(txt|md)$/i.test(file.name)&&file.size>1048576)throw Error(file.name+' 超过文件大小限制');notice='正在上传：'+file.name;if($('#kbNotice'))$('#kbNotice').textContent=notice;await api('knowledge/upload?'+new URLSearchParams({courseId:id,name:file.name,chapter:ch,review:'1'}),file,{headers:{'Idempotency-Key':key}});}if(valid(g))notice='上传完成。解析后请打开校正与确认，再建立向量索引或用于问答。当前不自动出题。';}
  catch(error){if(valid(g))notice='本批上传已停止：'+error.message+'。已接收的资料保留；重新选择同一批文件不会重复导入。';}
  finally{busy=false;if(valid(g)){draw();await load(false);}}
 }
 document.addEventListener('click',event=>{const b=event.target.closest('[data-kb]');if(b){event.preventDefault();void action(b.dataset.kb,b.dataset.id);}});
 document.addEventListener('change',event=>{const t=event.target;if(t.id==='kbFiles')void upload([...t.files]);if(t.id==='kbBase')void select(t.value);if(t.id==='kbChapter'){chapter=t.value;results=null;rows();showResults();}if(t.id==='kbPaidConfirm')paidConfirmed=t.checked;if(t.name==='confirmedExternal'&&t.closest('#kbSearch'))externalConfirmed=t.checked;if(t.id==='kbMode'){searchMode=t.value;const label=$('.kb-api-confirm');label.hidden=t.value==='lexical';label.querySelector('input').required=t.value!=='lexical';}});
 document.addEventListener('change',event=>{if(event.target.id==='kbReviewBlock'){const b=reviewArtifact?.blocks.find(b=>b.id===event.target.value);if(b)$('#kbReviewText').value=b.text;}});
 document.addEventListener('input',event=>{if(event.target.id==='kbFilter'){filter=event.target.value;rows();}if(event.target.id==='kbUploadChapter')uploadChapter=event.target.value;if(event.target.id==='kbQuery')query=event.target.value;});
 document.addEventListener('submit',async event=>{
  const f=event.target;if(!['kbSearch','kbCreate','kbVisualForm','kbCorrection','kbReviewConfirm','kbOcrBatch'].includes(f.id))return;event.preventDefault();if(busy)return;const g=epoch,id=course,v=Object.fromEntries(new FormData(f));busy=true;const submit=f.querySelector('button');submit.disabled=true;
  try{if(f.id==='kbCorrection'){
    const r=await api('rag/correct',{courseId:id,documentId:reviewDoc.id,version:reviewDoc.version,blockId:v.blockId,replacement:v.replacement,reason:v.reason});if(!valid(g))return;await load(false);busy=false;await action('review',reviewDoc.id);
   }else if(f.id==='kbReviewConfirm'){
    await api('knowledge/review-confirm',{courseId:id,documentId:reviewDoc.id,version:reviewDoc.version,confirmed:true});if(!valid(g))return;reader.close();notice='当前修订已确认。可建立向量索引，或先使用关键词检索。';await load(false);
   }else if(f.id==='kbOcrBatch'){
    const pages=[];for(const part of v.pages.split(/[,，、\s]+/).filter(Boolean)){const m=part.match(/^(\d+)(?:-(\d+))?$/);if(!m)throw Error('页码格式不正确');const a=Number(m[1]),b=Number(m[2]||m[1]);if(a<1||b<a||b-a>20)throw Error('页码范围不正确');for(let n=a;n<=b;n++)pages.push(n);}
    if(!pages.length||pages.length>20||new Set(pages).size!==pages.length||pages.some(n=>!reviewDoc.review.pendingPages.includes(n)))throw Error('请选择1至20个尚待识别且不重复的页码');
    await api('knowledge/process',{courseId:id,documentId:reviewDoc.id,version:reviewDoc.version,action:'ocr',pages,idempotencyKey:uid(),confirmedExternal:true});if(!valid(g))return;reader.close();notice='已提交所选页面，任务状态将自动刷新。';await load(false);
   }else if(f.id==='kbVisualForm'){
    const input=JSON.parse(v.reviewJson);if(!visualPack||input.documentId!==visualPack.documentId||input.fileHash!==visualPack.fileHash||input.version!==visualPack.version)throw Error('转写文件与当前资料不匹配，请重新导出');const r=await api('knowledge/visual-preview',{...input,courseId:id});if(!valid(g))return;visualPreview=r.preview;
    dialog('确认图片补录预览',`<p>${e(r.preview.warning)}</p><p>资料内容修订：${visualPack.contentRevision} → ${visualPack.contentRevision+1}；来源：${e(r.preview.reviewer)}</p>${r.preview.pages.map(p=>`<article class="kb-original"><strong>第 ${p.page} 页 · ${p.kind==='blank'?'核对为空白页':p.kind==='supplement'?'追加图片补充':'图片文字转写'}</strong><p>${e(p.text||(p.kind==='supplement'?'本页仅记录图片核查状态，不新增正文':'无正文，不补造内容'))}</p>${p.imageReviews?.map(r=>`<small>${e(r.imageHash.slice(0,12))} · ${e(r.kind)}${r.partial?' · 部分内容':''}：${e(r.text)}</small>`).join('')||''}</article>`).join('')}${button('确认采纳并重建片段','visual-apply', '', r.preview.expired?'disabled':'')}`);
   }else if(f.id==='kbCreate'){f.dataset.key||=uid();const r=await api('knowledge/create',{...v,idempotencyKey:f.dataset.key});if(!valid(g))return;bases=(await api('knowledge/bases')).bases;if(!valid(g))return;reader.close();busy=false;await select(r.base.id);}
   else{results=null;showResults();externalConfirmed=false;$('.kb-api-confirm input').checked=false;const r=await api('knowledge/search',{courseId:id,query:v.query,chapter,mode:v.mode,confirmedExternal:v.confirmedExternal==='on'});if(valid(g)){results=r.evidence;showResults();}}}
  catch(error){if(g===epoch)toast(error.message);}finally{busy=false;submit.disabled=false;}
 });
 document.addEventListener('change',async event=>{if(event.target.id!=='kbVisualFile')return;const f=event.target.files[0];if(!f)return;try{if(f.size>200000)throw Error('转写文件过大');const text=await f.text();JSON.parse(text);const field=$('#kbVisualForm [name=reviewJson]');if(field)field.value=text;}catch(error){toast('无法读取转写文件：'+error.message);}});
 return {refreshCount,mount(){clearTimeout(timer);epoch++;loading=false;if(course!==state.courseId){course=state.courseId;data=null;results=null;chapter='';filter='';query='';notice='';reader?.close();}if(state.view!=='knowledge')return;if(location.protocol==='file:'){$('#spaceContent').innerHTML='<div class="panel"><h1>知识库</h1><p>请通过本机服务打开，离线预览不能读取知识库。</p></div>';return;}const root=document.createElement('div');root.id='knowledgeWorkspace';$('#spaceContent').append(root);draw();void load();}};
}};
})();
