/* Knowledge bases are existing courses. Never keep a second copy of their sources. */
(() => {
'use strict';
window.XueyaKnowledgeBase={create({state,store,toast,render}){
 const e=window.XueyaRich.escape,$=s=>document.querySelector(s),uid=()=>crypto.randomUUID();
 const labels={queued:'等待处理',running:'正在处理',cancelling:'正在取消',succeeded:'处理完成',failed:'处理失败',cancelled:'已取消',unknown:'结果待核对'};
 const errors={AUTH_REQUIRED:'会话已变化，请刷新页面',EXTERNAL_CONFIRMATION_REQUIRED:'请先确认外部 API 调用',VERSION_CONFLICT:'资料已更新，请刷新后再操作',EMBEDDING_UNAVAILABLE:'向量服务未配置，仍可使用关键词检索',OCR_UNAVAILABLE:'文字识别服务未配置',KNOWLEDGE_REVIEW_REQUIRED:'请先校正并确认当前资料修订',OCR_SUBMISSION_UNKNOWN:'提交结果未知，请先核对平台任务，不能自动重新提交',OCR_REMOTE_FAILED:'远端解析失败，请核对平台任务',OCR_TASK_RECEIPT_MISSING:'缺少远端任务回执，请核对用量',PAID_RETRY_FORBIDDEN:'请先到任务与用量核对外部请求',TEMPORARY_FILE_FORBIDDEN:'已跳过 Office 临时文件',FILE_TOO_LARGE:'PDF 最大64MB，其他资料最大10MB，文本最大1MB',REPLACEMENT_NOT_READY:'新 PDF 仍有未识别页面，请先完成文字识别；旧 PPT 尚未移除',OCR_PAGE_LIMIT:'每次最多识别64页，请分批处理',OCR_BATCH_TOO_LARGE:'本批图片过大，请减少识别页数',INVALID_OCR_PAGES:'所选页面已处理或发生变化，请刷新',OCR_PDF_REQUIRED:'文字识别仅适用于PDF',JOB_NOT_RETRYABLE:'该任务当前不能重试',IDEMPOTENCY_CONFLICT:'同一次操作的内容已变化，请重新操作'};
 const KINDS={pdf:'PDF',md:'MD',txt:'TXT',docx:'DOCX',pptx:'PPTX'};
 const BLOCKS={paragraph:'正文',heading:'标题',table:'表格',code:'代码',formula:'公式',list:'列表',image:'图片'};
 const MODES=[['lexical','关键词（本地规则）'],['hybrid','关键词＋向量'],['vector','向量'],['rerank','向量＋重排']];
 const SEARCH_WARNINGS={EMBEDDING_UNAVAILABLE:'向量服务未配置，本次使用关键词检索',VECTOR_INDEX_UNAVAILABLE:'尚未为当前模型建立向量索引，本次使用关键词检索',RERANK_UNAVAILABLE:'重排服务未配置或不可用，已保留融合排序',VECTOR_API_UNAVAILABLE:'向量调用未完成，请到任务与用量核对',RERANK_API_UNAVAILABLE:'重排调用未完成，请到任务与用量核对',RERANK_BUDGET_EXCEEDED:'候选文字超过重排预算，已保留融合排序'};
 let listOpen=true,uploadOpen=false;
 let course='',epoch=0,data=null,bases=[],timer=null,loading=false,busy=false,reader=null,chapter='',filter='',query='',results=null,notice='',token='',uploadChapter='',searchMode='lexical',externalConfirmed=false,paidConfirmed=false;
 let uploadState=null,searching=false,searchError=null,searchErrorCode='',lastSearchMode='lexical',syncedAt='',focusTarget='',loadError='';
 let visualPreview=null,visualPack=null,replacementPreview=null,reviewDoc=null,reviewArtifact=null;
 const n=value=>{const number=Number(value);return Number.isFinite(number)?number:0;};
 const button=(text,action,id='',extra='')=>`<button type="button" class="button button-outline button-small" data-kb="${action}" data-id="${e(id)}" ${extra}>${e(text)}</button>`;
 const valid=g=>g===epoch&&state.view==='knowledge'&&course===state.courseId;
 function fmtSize(bytes){const size=n(bytes);if(!size)return '—';if(size<1024)return size+' B';if(size<1048576)return (size/1024).toFixed(1)+' KB';return (size/1048576).toFixed(2)+' MB';}
 function fmtTime(date){try{return date.toLocaleTimeString('zh-CN',{hour12:false});}catch{return '';}}
 function fmtScore(value){const score=Number(value);if(!Number.isFinite(score))return '';return score>=1?score.toFixed(2):score.toFixed(4);}
 function modeLabel(value){return (MODES.find(mode=>mode[0]===value)||[value,value])[1];}
 function kindLabel(kind){return KINDS[String(kind||'').toLowerCase()]||'—';}
 function statusText(d){return !d.sourceCount&&d.kind==='pdf'&&d.review?.pendingPages.length?'待文字识别 · '+d.review.pendingPages.length+' 页':d.sourceCount&&d.review?.pendingPages.length?'已解析 · '+d.review.pendingPages.length+' 页待识图或空白核对':!d.sourceCount&&d.review?.blankPages.length?'已核对空白页 · 无可检索正文':d.status||'待解析';}
 function pageSelectionText(d){const p=d.pageSelection;if(!p)return '';const ranges=[];for(const page of p.pages){const last=ranges[ranges.length-1];if(last&&last[1]+1===page)last[1]=page;else ranges.push([page,page]);}return '仅收录原PDF第 '+ranges.map(([a,b])=>a===b?a:a+'—'+b).join('、')+' 页 · 原件共 '+p.originalPageCount+' 页';}
 function errorHint(){
  if(searchErrorCode==='EMBEDDING_UNAVAILABLE')return '<p class="lw-hint">向量服务未配置：请在本机 .env 配置 RAG_EMBEDDING_API_KEY 与 RAG_EMBEDDING_MODEL 后重启服务，再使用向量或混合检索。</p>';
  if(searchErrorCode==='EXTERNAL_CONFIRMATION_REQUIRED')return '<p class="lw-hint">向量、混合或重排检索会调用外部服务，请先勾选“确认将问题发送给外部向量或重排服务”。</p>';
  if(searchErrorCode==='AUTH_REQUIRED')return '<p class="lw-hint">登录会话已变化，请刷新页面后重新检索。</p>';
  if(searchErrorCode==='NETWORK')return '<p class="lw-hint">请确认本机服务正在运行，然后刷新页面重试。</p>';
  return '';
 }
 function syncState(){
  if(!data)return {tone:'idle',text:'正在读取资料目录…'};
  const s=data.summary||{},caps=data.capabilities||{};
  const docs=(data.documents||[]).filter(d=>!d.archived);
  const pendingPages=docs.reduce((total,d)=>total+n(d.review?.pendingPages?.length),0);
  const embeddable=docs.filter(d=>n(d.sourceCount)>0),embedded=embeddable.filter(d=>d.vectorReady);
  const unparsed=docs.filter(d=>!n(d.sourceCount)&&d.originalAvailable!==false&&!d.contentRevision&&!d.review?.pendingPages?.length).length;
  const parts=[];
  if(['preparing','running'].includes(data.demoImport?.status))parts.push('演示课件准备中');
  if(n(s.processing))parts.push(n(s.processing)+' 个任务处理中');
  if(unparsed)parts.push(unparsed+' 份待解析');
  if(n(s.missingOriginals))parts.push(n(s.missingOriginals)+' 份记录缺少原件');
  if(!docs.length)parts.push('暂无资料');
  if(pendingPages)parts.push(pendingPages+' 页待文字识别');
  if(n(s.needsReview))parts.push(n(s.needsReview)+' 份待复核');
  if(caps.embedding&&embeddable.length&&embedded.length===embeddable.length)parts.push('全量嵌入完成');
  else if(!caps.embedding)parts.push('向量未配置');
  if(!parts.length)parts.push('资料目录已同步');
  const busyState=['preparing','running'].includes(data.demoImport?.status)||n(s.processing)>0;
  const warn=parts.some(part=>/待解析|待文字识别|待复核|未配置|缺少原件/.test(part));
  return {tone:busyState?'busy':warn?'warn':'ok',text:parts.join(' · ')};
 }
 function overviewStats(){
  const s=data?.summary||{};
  const docs=(data?.documents||[]).filter(d=>!d.archived);
  const searchable=docs.filter(d=>n(d.sourceCount)>0&&d.originalAvailable!==false&&d.reviewReady!==false).length;
  return `<li><strong>${n(s.documents)}</strong><span>资料份数</span></li><li><strong>${n(s.sources)}</strong><span>原文切片</span></li><li><strong>${searchable}</strong><span>可检索</span></li><li><strong>${n(s.needsReview)}</strong><span>待复核</span></li>`;
 }
 function scaleBody(){
  const s=data?.summary||{},caps=data?.capabilities||{};
  const docs=(data?.documents||[]).filter(d=>!d.archived);
  const totalSize=docs.reduce((total,d)=>total+n(d.size),0);
  const embeddable=docs.filter(d=>n(d.sourceCount)>0),embedded=embeddable.filter(d=>d.vectorReady);
  const formats=Object.entries(docs.reduce((counts,d)=>{const kind=String(d.kind||'').toLowerCase();if(KINDS[kind])counts[kind]=(counts[kind]||0)+1;return counts;},{}));
  return `<dl class="lw-metrics">
   <div><dt>资料份数</dt><dd>${n(s.documents)}</dd></div>
   <div><dt>原文切片</dt><dd>${n(s.sources)}</dd></div>
   <div><dt>资料体积</dt><dd>${totalSize?fmtSize(totalSize):'—'}</dd></div>
   <div><dt>待复核</dt><dd>${n(s.needsReview)}</dd></div>
   <div><dt>处理中</dt><dd>${n(s.processing)}</dd></div>
   <div><dt>向量索引</dt><dd>${caps.embedding?embedded.length+' / '+embeddable.length:'未配置'}</dd></div>
  </dl>${formats.length?`<p class="lw-formats" aria-label="资料格式构成">${formats.map(([kind,count])=>`<span class="lw-chip">${KINDS[kind]} ${count}</span>`).join('')}</p>`:''}<p class="lw-hint">切片数是当前可用于检索的原文片段数。接口未返回字符数或 token 数，因此这里不展示这两项。</p>`;
 }
 function paintPanels(){
  const sync=syncState();
  const wrap=$('#lwSync');if(wrap)wrap.dataset.tone=sync.tone;
  const text=$('#lwSyncText');if(text)text.textContent=sync.text;
  const at=$('#lwSyncAt');if(at)at.textContent=syncedAt?'更新于 '+syncedAt:'';
  const overview=$('#lwOverviewStats');if(overview)overview.innerHTML=overviewStats();
  const scale=$('#lwScaleBody');if(scale)scale.innerHTML=scaleBody();
 }
 async function api(path,value,options={}){
  if(!token){const r=await fetch('/api/platform/bootstrap');if(!r.ok)throw Error('请启动本地服务并登录后使用知识库');token=(await r.json()).token;}
  let response;
  try{response=await fetch('/api/platform/'+path,{method:value!==undefined?'POST':'GET',headers:{'X-Xueya-Token':token,...(value!==undefined&&!(value instanceof File)?{'Content-Type':'application/json'}:{}),...options.headers},body:value===undefined?undefined:value instanceof File?value:JSON.stringify(value)});}
  catch(networkFailure){const failure=Error('无法连接本机服务，请确认服务已启动并刷新页面。');failure.code='NETWORK';throw failure;}
  const result=await response.json().catch(()=>null);
  if(!response.ok||!result?.ok){const failure=Error(errors[result?.error]||result?.error||'操作未完成');failure.code=result?.error||'';throw failure;}
  return result;
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
 function generationRows(){
  const target=$('#kbPracticeGeneration');if(!target)return;
  const list=data?.practiceGenerations||[];
  const labelsFor={waiting_parse:'等待解析后自动出题',generating:'正在生成题库',succeeded:'Hot 100 和基础 100 已就绪',model_unavailable:'请先配置模型，再到练习页继续生成',insufficient_material:'资料内容不足，无法可靠生成200道不同题',unknown:'调用结果待核对，可到练习页查看并继续',failed:'出题未完成，可到练习页继续',cancelled:'出题已停止',stale:'原文已更新，旧题库已停用'};
  target.innerHTML=list.length?`<h3 class="lw-subtitle">自动出题状态</h3>`+list.map(g=>`<p><strong>${e(g.name)}</strong> · ${e(labelsFor[g.status]||g.status)} · ${Number(g.completed)||0}/200 <a class="text-link" href="#space/practice">查看练习 →</a></p>`).join(''):'';
 }
 function chapterOptions(){
  const chapters=[...new Set((data?.documents||[]).filter(d=>!d.archived).map(d=>d.chapter).filter(Boolean))];
  return '<option value="">全部章节</option>'+chapters.map(name=>`<option value="${e(name)}" ${name===chapter?'selected':''}>${e(name)}</option>`).join('');
 }
 async function load(full=true){
  if(loading)return;loading=true;const g=epoch,id=course;
  try{
   if(full){bases=(await api('knowledge/bases')).bases;if(!valid(g))return;const local=store.courses.find(c=>c.id===id);if(!bases.some(c=>c.id===id)&&local){await api('courses',{id,name:local.name});bases=(await api('knowledge/bases')).bases;}for(const base of bases)store.adoptCourse(base);}
   const next=await api('knowledge/catalog?'+new URLSearchParams({courseId:id}));if(!valid(g))return;
   if(data&&JSON.stringify(data.documents.map(d=>[d.id,d.version,d.archived]))!==JSON.stringify(next.documents.map(d=>[d.id,d.version,d.archived])))results=null;
   data=next;state.documentCount=n(data.summary?.documents);countCourse=id;countAt=Date.now();syncedAt=fmtTime(new Date());loadError='';store.persist();
   if($('#documentCount'))$('#documentCount').textContent=state.documentCount;
   if(!full&&$('#kbDocuments')){
    rows();showResults();generationRows();paintPanels();
    if($('#kbNotice'))$('#kbNotice').innerHTML=e(notice)+demoNotice();
    const select=$('#kbChapter');if(select){select.innerHTML=chapterOptions();select.value=chapter;}
   }else draw();schedule();
  }catch(error){loadError=error.message;if(valid(g)){notice=error.message;draw();}}
  finally{if(g===epoch)loading=false;}
 }
 function statsFacts(d){
  const pages=d.kind==='pdf'||d.kind==='pptx'?n(d.review?.totalPages):null;
  const vectorLabel=d.vectorReady?'就绪':d.indexStatus==='ready'?(data?.capabilities?.embedding?'已有缓存，当前模型不匹配':'已有缓存，服务未配置'):data?.capabilities?.embedding?'未建立':'未配置';
  return [['格式',kindLabel(d.kind)],['大小',fmtSize(d.size)],['章节',d.chapter||'—'],['切片',n(d.sourceCount)],['页数',pages?pages+(d.kind==='pptx'?' 页幻灯片':' 页'):'—'],['解析',d.task&&!['succeeded','failed','cancelled','unknown'].includes(d.task.status)?labels[d.task.status]:d.task&&['failed','cancelled','unknown'].includes(d.task.status)?labels[d.task.status]:statusText(d)],['向量索引',vectorLabel]];
 }
 function docRow(d){
  const task=d.task,active=task&&!['succeeded','failed','cancelled','unknown'].includes(task.status);
  const status=active?labels[task.status]:task&&['failed','cancelled','unknown'].includes(task.status)?labels[task.status]:statusText(d);
  const facts=statsFacts(d).map(([key,value])=>`<div><dt>${e(key)}</dt><dd>${e(String(value))}</dd></div>`).join('');
  return `<article class="kb-document lw-doc" data-document-id="${e(d.id)}">
   <div class="lw-doc-main">
    <div class="lw-doc-title"><span class="lw-kind" data-kind="${e(String(d.kind||'').toLowerCase())}">${e(kindLabel(d.kind))}</span><h3>${e(d.name)}</h3></div>
    <dl class="lw-facts">${facts}</dl>
    <div class="lw-doc-status"><span class="kb-status ${task?.status==='failed'?'kb-status-error':''}">${e(status)}</span>${active?`<progress max="100" value="${n(task.progress?.percent)}" aria-label="${e(d.name)}处理进度"></progress>`:''}</div>
    ${task?.error?`<small>处理代码：${e(task.error)}</small>`:''}
    ${d.quality?.warnings?.length?`<small>${d.kind==='pdf'?'扫描PDF仍有待识别页，请配置OCR；识别前不能作为完整知识库':'有页面尚无可读文字：可能为图片或空白，需逐页核对'}</small>`:''}
    ${d.review?.transcribedPages.length?`<small>图片转写：${d.review.transcribedPages.length} 页（辅助识图，未独立人审）</small>`:''}
    ${d.review?.reviewedImages?`<small>图片核查：${d.review.reviewedImages} 个引用 · 补充 ${d.review.supplementedPages.length} 页正文${d.review.partialImages?' · '+d.review.partialImages+' 个部分转写':''}${d.review.unreadableImages?' · '+d.review.unreadableImages+' 个无法辨认':''}（辅助识图，未独立人审）</small>`:''}
    ${d.review?.blankPages.length?`<small>已核对 ${d.review.blankPages.length} 个空白页</small>`:''}
    ${d.ocrPreparation?`<small class="kb-warning">${e(d.ocrPreparation.notice)} · 可随时查看原PDF</small>`:''}
    ${d.pageSelection?`<small class="kb-page-selection">${e(pageSelectionText(d))}</small>`:''}
    <small>${d.originalAvailable===false?'原件缺失：请重新上传，当前记录不计为可检索资料':!d.sourceCount?'暂无可检索正文':d.reviewReady===false?'待校正与确认：当前修订尚未用于检索':'当前修订可用于检索'}</small>
   </div>
   <div class="kb-row-actions lw-doc-actions">
    ${d.protected?'<small>平台预置资料：可用于问答，正文与原件受保护</small>':button('查看原文','read',d.id)}
    ${button('用于问答','chat',d.id,d.sourceCount&&d.reviewReady!==false?'':'disabled')}
    ${button('校正与确认','review',d.id,d.sourceCount?'':'disabled')}
    ${active?button('取消任务','cancel',task.id):`<details><summary>处理</summary>${task&&['failed','cancelled'].includes(task.status)&&['rag-parse','rag-visual-apply'].includes(task.type)?button('重试本地处理','retry',task.id):''}${d.kind==='pptx'?button('图片文字补录','visual-review',d.id):''}${button('重新解析','parse',d.id)}${button('建立向量索引','index',d.id,data?.capabilities?.embedding&&d.reviewReady!==false?'':'disabled')}${button('选择识别页（最多20页）','ocr-select',d.id,data?.capabilities?.ocr&&d.kind==='pdf'&&d.review?.pendingPages.length?'':'disabled')}${d.kind==='pdf'&&data.documents.some(old=>old.kind==='pptx'&&!old.archived)?button('用此PDF替换旧PPT','replace-ppt',d.id,d.sourceCount&&!d.review?.pendingPages.length?'':'disabled'):''}</details>`}
   </div>
  </article>`;
 }
 function rows(){
  const target=$('#kbDocuments');if(!target)return;
  if(!data){target.innerHTML='';return;}
  const docs=(data.documents||[]).filter(d=>!d.archived&&(!chapter||d.chapter===chapter)&&(!filter||d.name.toLowerCase().includes(filter.toLowerCase())));
  target.innerHTML=docs.map(docRow).join('')||'<div class="empty-state lw-empty"><h3>没有匹配的资料</h3><p>调整章节或文件名筛选，或在上方上传新的课程资料。</p></div>';
  const badge=$('#lwDocsCount');if(badge)badge.textContent=docs.length+' 份';
 }
 function resultWarnings(){
  return (results?.warnings||[]).map(warning=>`<p class="kb-warning lw-warning">${e(SEARCH_WARNINGS[warning]||('检索提示：'+warning))}</p>`).join('');
 }
 function searchHint(){
  if(!results||results.sources?.length)return '';
  if(!data?.capabilities?.embedding)return '<p class="lw-hint">当前知识库未配置向量检索。可在本机 .env 配置 RAG_EMBEDDING_API_KEY 与 RAG_EMBEDDING_MODEL 后重启服务；未配置时请使用关键词检索。</p>';
  return '';
 }
 function resultRow(source,index){
  const score=source.score;
  const location=source.location||'—';
  const block=BLOCKS[source.blockType]||'';
  const revision=Number.isFinite(Number(source.documentRevision))?' · 内容修订 '+n(source.documentRevision):'';
  return `<li class="kb-result lw-result">
   <div class="lw-result-head"><span class="lw-rank" aria-label="排名 ${index+1}">${index+1}</span><strong>${e(source.title||'资料片段')}</strong>${Number.isFinite(Number(score))?`<span class="lw-score" title="得分由当前检索方式计算，不同检索方式之间不可直接比较">得分 ${e(fmtScore(score))}</span>`:''}</div>
   <p class="lw-result-meta">${e(location)}${block?' · '+e(block):''}${e(revision)}</p>
   <blockquote class="lw-quote" tabindex="0">${e(source.quote||'')}</blockquote>
   <div class="lw-result-actions">${button('核对原文','source',source.id)}</div>
  </li>`;
 }
 function showResults(){
  const target=$('#kbResults');if(!target)return;
  if(searching){target.setAttribute('aria-busy','true');target.innerHTML='<div class="lw-empty"><strong>正在检索…</strong><p>正在核对原文范围与召回结果。</p></div>';return;}
  target.removeAttribute('aria-busy');
  if(searchError){target.innerHTML=`<div class="lw-empty lw-empty-error" role="alert"><strong>检索未完成</strong><p>${e(searchError.message)}</p>${searchErrorCode?`<p class="lw-hint">错误代码：${e(searchErrorCode)}</p>`:''}${errorHint()}</div>`;return;}
  if(!results){target.innerHTML='<div class="lw-empty"><strong>尚未执行检索</strong><p>输入问题并执行后，这里会按排名显示得分、来源资料、页码或章节与命中片段。</p></div>';return;}
  const sources=Array.isArray(results.sources)?results.sources:[];
  const status=results.status==='evidence_found'?'已召回原文依据':results.status==='conflict'?'原文之间存在冲突表述':results.status==='insufficient'?'没有足够的原文依据':'检索完成';
  const budget=results.budget||{};
  const meta=[sources.length+' 条命中'];
  if(Number.isFinite(Number(results.elapsedMs)))meta.push('用时 '+Number(results.elapsedMs)+' ms');
  if(Number.isFinite(Number(budget.limit)))meta.push('预算 '+n(budget.used)+' / '+n(budget.limit)+' 字节');
  if(results.rewrittenQuery&&results.rewrittenQuery!==results.query)meta.push('检索词：'+results.rewrittenQuery);
  target.innerHTML=`<div class="lw-result-summary"><div><strong>${e(status)}</strong><p class="lw-hint">${e(meta.join(' · '))}</p></div><span class="lw-chip">检索方式：${e(modeLabel(lastSearchMode))}</span></div>${resultWarnings()}${sources.length?`<ol class="lw-ranklist">${sources.map(resultRow).join('')}</ol>`:`<div class="lw-empty"><strong>没有召回到原文</strong><p>当前资料库中没有匹配“${e(String(results.query||query||''))}”的片段。可以换用关键词、缩小章节范围，或先上传资料并完成解析与确认。</p></div>`}${searchHint()}`;
 }
 function dialog(title,content){if(!reader){reader=document.createElement('dialog');reader.className='source-dialog kb-dialog';reader.id='kbDialog';document.body.append(reader);}reader.setAttribute('aria-label',title);reader.innerHTML=`<div class="dialog-head"><strong>${e(title)}</strong>${button('关闭','close')}</div><div class="c-dialog-body">${content}</div>`;if(!reader.open)reader.showModal();}
 async function select(id){if(busy||state.pending||state.working){toast('请先等待当前操作完成');return;}const c=bases.find(b=>b.id===id)||store.courses.find(c=>c.id===id);if(!c||!store.adoptCourse(c)||!store.switchCourse(id))return;render();}
 function rememberFocus(el){const key=el?.dataset?.kb||'';focusTarget=key?`[data-kb="${key}"]`+(el.dataset.id?`[data-id="${el.dataset.id}"]`:''):'';}
 function refocus(){if(!focusTarget)return;const target=document.querySelector(focusTarget);focusTarget='';if(target&&target.offsetParent!==null)target.focus({preventScroll:true});}
 async function action(action,id,el){const g=epoch,idCourse=course;let ownsBusy=false;
  try{
   if(action==='close'){reader.close();return;}
   if(action==='toggle-list'){listOpen=!listOpen;draw();return;}if(action==='toggle-upload'){uploadOpen=!uploadOpen;draw();return;}
   if(action==='refresh'){if(loading){toast('正在刷新，请稍候');return;}if(el){el.disabled=true;el.textContent='刷新中…';}loadError='';await load();if(valid(g)){if(loadError){notice=loadError;}else{syncedAt=fmtTime(new Date());notice='资料目录已刷新 · '+syncedAt;}draw();}return;}
   if(action==='create'){dialog('新建知识库','<form id="kbCreate"><label class="form-field">知识库名称<input name="name" maxlength="60" required placeholder="例如：数据结构与算法"></label><label class="form-field">说明<textarea name="description" maxlength="4000" rows="3"></textarea></label><p>创建独立课程范围，已有资料与私人记录会保留。</p><button class="button button-blue button-small">确认创建</button></form>');return;}
   if(busy)throw Error('请等待当前操作完成');
   if(action==='index'){
    const r=await api('knowledge/index-plan?'+new URLSearchParams({courseId:idCourse,documentId:id}));if(!valid(g))return;
    const p=r.plan;
    dialog('建立向量索引',`<p>将使用已配置的向量化服务：<strong>${e(p.model)}</strong>。</p><p>当前 ${n(p.sourceCount)} 个片段，可复用 ${n(p.cachedVectors)} 条已有向量，${n(p.missingVectors)} 条需要计算。</p><p>${p.requiresExternal?'缺失片段会发送给上述服务，可能产生费用。':'已有向量全部匹配，预计直接复用缓存，无需重新计算文档向量。'}</p><form id="kbIndexConfirm"><input type="hidden" name="documentId" value="${e(id)}"><input type="hidden" name="version" value="${n(p.version)}"><label><input type="checkbox" name="confirmedExternal" required>确认建立索引；如有缺失片段，允许使用上述已配置 API</label><button class="button button-blue" type="submit">确认建立索引</button></form>`);return;
   }
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
   if(action==='chat'){const doc=data.documents.find(d=>d.id===id);if(!doc?.sourceCount||doc.reviewReady===false)throw Error('请等待解析完成后再使用');const current=await api('documents?'+new URLSearchParams({courseId:idCourse}));if(!valid(g))return;state.documents=[...state.documents.filter(d=>!d.remote),...current.documents];state.selectedDocuments=[id];store.persist();try{localStorage.setItem((window.XueyaDataKey||((key)=>key))('xueya-c-learning:'+course+':scope:'+state.sessionId),JSON.stringify([id]));}catch{}location.hash='space/ask';window.dispatchEvent(new Event('xueya:scope-change'));return;}
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
 function renderUploadProgress(){
  const target=$('#kbUploadProgress');if(!target)return;
  if(!uploadState){target.innerHTML='';return;}
  target.innerHTML=`<div class="lw-upload-status" role="status" aria-live="polite"><strong>正在上传 ${Math.min(uploadState.done+1,uploadState.total)} / ${uploadState.total}</strong><span>${e(uploadState.current||'准备中…')}</span><progress max="${uploadState.total}" value="${uploadState.done}" aria-label="上传进度"></progress></div>`;
 }
 async function upload(files){
  if(busy||!files?.length)return;const g=epoch,id=course,ch=$('#kbUploadChapter')?.value??uploadChapter;uploadChapter=ch;busy=true;
  uploadState={done:0,total:files.length,current:''};notice='正在上传课件…';draw();renderUploadProgress();
  try{
   for(const file of files){
    if(!valid(g))break;
    if(file.name.startsWith('~$')){uploadState.done++;renderUploadProgress();continue;}
    const key='kb-file-'+Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer()))).map(b=>b.toString(16).padStart(2,'0')).join('')+'-'+Array.from(new TextEncoder().encode(file.name+'|'+ch)).reduce((h,b)=>(h*31+b)>>>0,0);
    if(file.size>(/\.pdf$/i.test(file.name)?67108864:10485760)||/\.(txt|md)$/i.test(file.name)&&file.size>1048576)throw Error(file.name+' 超过文件大小限制');
    uploadState.current=file.name;notice='正在上传 '+(uploadState.done+1)+' / '+uploadState.total+'：'+file.name;renderUploadProgress();
    await api('knowledge/upload?'+new URLSearchParams({courseId:id,name:file.name,chapter:ch,review:'1'}),file,{headers:{'Idempotency-Key':key}});
    uploadState.done++;
   }
   notice='上传完成。解析后请完成必要的校正与确认，随后将自动准备资料题目；可在课程资料学习查看图谱和练习。向量索引用于问答，不是出题的必要条件。';
  }catch(error){notice='本批上传已停止：'+error.message+'。已接收的资料保留；重新选择同一批文件不会重复导入。';}
  finally{uploadState=null;busy=false;if(valid(g)){draw();await load(false);}}
 }
 document.addEventListener('click',event=>{const b=event.target.closest('[data-kb]');if(b){event.preventDefault();rememberFocus(b);void action(b.dataset.kb,b.dataset.id,b);}});
 document.addEventListener('change',event=>{const t=event.target;if(t.id==='kbFiles')void upload([...t.files]);if(t.id==='kbBase')void select(t.value);if(t.id==='kbChapter'){chapter=t.value;results=null;rows();showResults();}if(t.id==='kbPaidConfirm')paidConfirmed=t.checked;if(t.name==='confirmedExternal'&&t.closest('#kbSearch'))externalConfirmed=t.checked;if(t.id==='kbMode'){searchMode=t.value;const label=$('.kb-api-confirm');if(label){label.hidden=t.value==='lexical';const input=label.querySelector('input');if(input)input.required=t.value!=='lexical';}}});
 document.addEventListener('change',event=>{if(event.target.id==='kbReviewBlock'){const b=reviewArtifact?.blocks.find(block=>block.id===event.target.value);if(b)$('#kbReviewText').value=b.text;}});
 document.addEventListener('input',event=>{if(event.target.id==='kbFilter'){filter=event.target.value;rows();}if(event.target.id==='kbUploadChapter')uploadChapter=event.target.value;if(event.target.id==='kbQuery')query=event.target.value;});
 document.addEventListener('submit',async event=>{
  const f=event.target;if(!['kbSearch','kbCreate','kbVisualForm','kbCorrection','kbReviewConfirm','kbOcrBatch','kbIndexConfirm'].includes(f.id))return;event.preventDefault();if(busy)return;const g=epoch,id=course,v=Object.fromEntries(new FormData(f));busy=true;const submit=f.querySelector('button');submit.disabled=true;
  try{if(f.id==='kbIndexConfirm'){
    await api('knowledge/process',{courseId:id,documentId:v.documentId,version:Number(v.version),action:'index',idempotencyKey:uid(),confirmedExternal:v.confirmedExternal==='on'});if(!valid(g))return;reader.close();notice='已使用当前配置提交索引任务，优先复用已有向量缓存。';await load(false);
   }else if(f.id==='kbCorrection'){
    const r=await api('rag/correct',{courseId:id,documentId:reviewDoc.id,version:reviewDoc.version,blockId:v.blockId,replacement:v.replacement,reason:v.reason});if(!valid(g))return;await load(false);busy=false;await action('review',reviewDoc.id);
   }else if(f.id==='kbReviewConfirm'){
    await api('knowledge/review-confirm',{courseId:id,documentId:reviewDoc.id,version:reviewDoc.version,confirmed:true});if(!valid(g))return;reader.close();notice='当前修订已确认。可建立向量索引，或先使用关键词检索。';await load(false);
   }else if(f.id==='kbOcrBatch'){
    const pages=[];for(const part of v.pages.split(/[,，、\s]+/).filter(Boolean)){const m=part.match(/^(\d+)(?:-(\d+))?$/);if(!m)throw Error('页码格式不正确');const a=Number(m[1]),b=Number(m[2]||m[1]);if(a<1||b<a||b-a>20)throw Error('页码范围不正确');for(let page=a;page<=b;page++)pages.push(page);}
    if(!pages.length||pages.length>20||new Set(pages).size!==pages.length||pages.some(page=>!reviewDoc.review.pendingPages.includes(page)))throw Error('请选择1至20个尚待识别且不重复的页码');
    await api('knowledge/process',{courseId:id,documentId:reviewDoc.id,version:reviewDoc.version,action:'ocr',pages,idempotencyKey:uid(),confirmedExternal:true});if(!valid(g))return;reader.close();notice='已提交所选页面，任务状态将自动刷新。';await load(false);
   }else if(f.id==='kbVisualForm'){
    const input=JSON.parse(v.reviewJson);if(!visualPack||input.documentId!==visualPack.documentId||input.fileHash!==visualPack.fileHash||input.version!==visualPack.version)throw Error('转写文件与当前资料不匹配，请重新导出');const r=await api('knowledge/visual-preview',{...input,courseId:id});if(!valid(g))return;visualPreview=r.preview;
    dialog('确认图片补录预览',`<p>${e(r.preview.warning)}</p><p>资料内容修订：${visualPack.contentRevision} → ${visualPack.contentRevision+1}；来源：${e(r.preview.reviewer)}</p>${r.preview.pages.map(p=>`<article class="kb-original"><strong>第 ${p.page} 页 · ${p.kind==='blank'?'核对为空白页':p.kind==='supplement'?'追加图片补充':'图片文字转写'}</strong><p>${e(p.text||(p.kind==='supplement'?'本页仅记录图片核查状态，不新增正文':'无正文，不补造内容'))}</p>${p.imageReviews?.map(review=>`<small>${e(review.imageHash.slice(0,12))} · ${e(review.kind)}${review.partial?' · 部分内容':''}：${e(review.text)}</small>`).join('')||''}</article>`).join('')}${button('确认采纳并重建片段','visual-apply','',r.preview.expired?'disabled':'')}`);
   }else if(f.id==='kbCreate'){f.dataset.key||=uid();const r=await api('knowledge/create',{...v,idempotencyKey:f.dataset.key});if(!valid(g))return;bases=(await api('knowledge/bases')).bases;if(!valid(g))return;reader.close();busy=false;await select(r.base.id);}
   else{results=null;searchError=null;searchErrorCode='';searching=true;lastSearchMode=v.mode||'lexical';searchMode=lastSearchMode;query=v.query;showResults();if(submit)submit.textContent='检索中…';externalConfirmed=false;const confirmBox=$('.kb-api-confirm input');if(confirmBox)confirmBox.checked=false;const r=await api('knowledge/search',{courseId:id,query:v.query,chapter,mode:v.mode,confirmedExternal:v.confirmedExternal==='on'});if(valid(g)){results=r.evidence;searching=false;searchError=null;searchErrorCode='';showResults();}}}
  catch(error){if(g===epoch){if(f.id==='kbSearch'){searching=false;searchError=error;searchErrorCode=error.code||'';showResults();}toast(error.message);}}
  finally{busy=false;submit.disabled=false;if(f.id==='kbSearch')submit.textContent='执行检索';}
 });
 document.addEventListener('change',async event=>{if(event.target.id!=='kbVisualFile')return;const f=event.target.files[0];if(!f)return;try{if(f.size>200000)throw Error('转写文件过大');const text=await f.text();JSON.parse(text);const field=$('#kbVisualForm [name=reviewJson]');if(field)field.value=text;}catch(error){toast('无法读取转写文件：'+error.message);}});
 function draw(){
  const root=$('#knowledgeWorkspace');if(!root)return;
  const s=data?.summary||{documents:0,sources:0,processing:0,needsReview:0},caps=data?.capabilities||{};
  const sync=syncState();
  const modeReady=value=>value==='lexical'||(value==='rerank'?!!caps.embedding&&!!caps.rerank:!!caps.embedding);
  if(!MODES.some(mode=>mode[0]===searchMode&&modeReady(mode[0])))searchMode='lexical';
  const allBases=[...bases,...store.courses.filter(c=>!c.archived&&!bases.some(b=>b.id===c.id))];
  root.innerHTML=`<div class="lw-page">
   <header class="view-heading lw-heading">
    <div class="lw-heading-copy">
     <nav class="lw-breadcrumb" aria-label="位置"><a href="#space/materials">课程资料</a><span aria-hidden="true">/</span><span aria-current="page">课程资料库</span></nav>
     <h1>课程资料库</h1>
     <p>上传并管理课程资料，为 AI 伴学与问答提供可追溯上下文。</p>
    </div>
    <div class="heading-actions lw-heading-actions">${button('刷新状态','refresh')}<button type="button" class="button button-blue button-small" data-kb="create">新建资料库</button></div>
   </header>
   <div id="kbNotice" class="lw-notice" role="status" aria-live="polite">${e(notice||(!data?'正在加载知识库…':''))}${demoNotice()}</div>
   <div id="kbPracticeGeneration" class="practice-generation lw-generation" role="status" aria-live="polite"></div>
   <section class="panel lw-overview" aria-label="资料库概览">
    <div class="lw-overview-scope">
     <label class="form-field lw-field">当前挂载资料库<select id="kbBase">${allBases.map(c=>`<option value="${e(c.id)}" ${c.id===course?'selected':''}>${e(c.name)}</option>`).join('')}</select></label>
     <p class="lw-hint">资料库与课程范围一致，问答、练习与学习记录共用同一范围。</p>
     <div class="lw-sync" id="lwSync" data-tone="${sync.tone}" role="status" aria-live="polite"><span class="lw-sync-dot" aria-hidden="true"></span><span id="lwSyncText">${e(sync.text)}</span><small id="lwSyncAt">${syncedAt?'更新于 '+e(syncedAt):''}</small></div>
    </div>
    <ul class="lw-overview-stats" id="lwOverviewStats">${overviewStats()}</ul>
    <div class="lw-overview-actions">${button(uploadOpen?'收起上传':'上传资料','toggle-upload')}${button(listOpen?'收起资料列表':'查看资料','toggle-list')}</div>
   </section>
   <div class="lw-layout">
    <div class="lw-main">
     <section class="panel kb-import lw-import" ${uploadOpen?'':'hidden'} aria-labelledby="lwImportTitle">
      <div class="lw-import-copy"><h2 id="lwImportTitle">添加学习资料</h2><p>PDF 最大 64MB · PPTX、DOCX 最大 10MB · TXT、Markdown 最大 1MB。上传后先解析并进入人工复核，确认文字后可建立向量索引。</p></div>
      <label class="form-field lw-field">所属章节<input id="kbUploadChapter" maxlength="200" value="${e(uploadChapter)}" placeholder="可选；留空时识别文件名中的章节或周次"></label>
      <input id="kbFiles" type="file" multiple accept=".pdf,.pptx,.docx,.txt,.md" aria-label="选择要上传的课程资料" ${busy?'disabled':''}>
      <small>上传不触发出题；OCR、向量索引与重排需要单独确认，未配置时不会调用外部服务。</small>
      <div id="kbUploadProgress" aria-live="polite"></div>
     </section>
     <section class="panel lw-docs" ${listOpen?'':'hidden'} aria-labelledby="lwDocsTitle">
      <div class="lw-section-head"><div><h2 id="lwDocsTitle">资料列表 <span class="lw-badge" id="lwDocsCount"></span></h2><p class="lw-hint">文件名、格式、大小、解析与索引状态均来自接口真实字段；接口未返回的项以“—”标出。</p></div></div>
      <div class="kb-filters lw-filters"><label class="form-field">章节<select id="kbChapter">${chapterOptions()}</select></label><label class="form-field">筛选文件<input id="kbFilter" type="search" value="${e(filter)}" placeholder="按文件名筛选"></label></div>
      <div id="kbDocuments" class="lw-doc-list"></div>
       <details class="kb-advanced lw-advanced"><summary>高级处理设置</summary><label><input id="kbPaidConfirm" type="checkbox">确认下一次文字识别调用外部 API，可能产生费用</label></details>
     </section>
    </div>
    <aside class="lw-side" aria-label="知识库统计与配置">
     <section class="panel lw-card" aria-labelledby="lwScaleTitle"><div class="lw-card-head"><h2 id="lwScaleTitle">知识库规模</h2><span class="lw-chip">实时</span></div><div id="lwScaleBody">${scaleBody()}</div></section>
    </aside>
   </div>
  </div>`;
  const setValue=(selector,value)=>{const field=$(selector);if(field)field.value=value;};
  setValue('#kbMode',searchMode);setValue('#kbUploadChapter',uploadChapter);setValue('#kbFilter',filter);setValue('#kbChapter',chapter);
  const chapterField=$('#kbChapter');if(chapterField&&chapter&&chapterField.value!==chapter){chapter='';chapterField.value='';}
  if($('#kbPaidConfirm'))$('#kbPaidConfirm').checked=paidConfirmed;
  rows();showResults();generationRows();renderUploadProgress();refocus();
 }
 return {refreshCount,mount(){clearTimeout(timer);epoch++;loading=false;if(course!==state.courseId){course=state.courseId;data=null;results=null;chapter='';filter='';query='';notice='';syncedAt='';uploadState=null;searchError=null;searching=false;reader?.close();}if(state.view!=='knowledge')return;if(location.protocol==='file:'){$('#spaceContent').innerHTML='<div class="panel"><h1>知识库</h1><p>请通过本机服务打开，离线预览不能读取知识库。</p></div>';return;}const root=document.createElement('div');root.id='knowledgeWorkspace';$('#spaceContent').append(root);draw();void load();}};
}};
})();
