/* E's same-origin adapter. Paid/model capabilities remain absent until real implementations exist. */
(() => {
'use strict';
if(location.protocol==='file:')return;
let bootstrap,token='',etag=0,enabled=false,conflict=false,restoring=false,timer,context,chain=Promise.resolve();
const KEY='xueya-copilot-workspace-v3',MARK='xueya-platform-sync-v1',PENDING='xueya-platform-pending-v1';
async function request(path,{method='GET',body,signal,headers={}}={}){
  const response=await fetch('/api/platform'+path,{method,headers:{...(token?{'X-Xueya-Token':token}:{}),...(body!==undefined&&!((body instanceof Blob))?{'Content-Type':'application/json'}:{}),...headers},body:body===undefined?undefined:body instanceof Blob?body:JSON.stringify(body),signal});
  if(path.startsWith('/documents/original')){if(!response.ok)throw new Error('原件下载失败');return{blob:await response.blob()};}
  const data=await response.json();if(!response.ok||!data.ok){const error=new Error(data.error||'本地服务暂不可用');error.code=data.error;throw error;}return data;
}
function workspace(){const value=JSON.parse(context.store.exportData());delete value.exportedAt;return value;}
function mark(){localStorage.setItem(MARK,JSON.stringify({enabled,version:etag}));}
function status(text){const el=document.getElementById('platformStatus');if(el)el.textContent=text;}
function changed(){if(restoring||!enabled||conflict||!context)return;try{localStorage.setItem(PENDING,JSON.stringify(workspace()));}catch{context.toast('本地服务同步队列未保存，请导出备份。');return;}clearTimeout(timer);timer=setTimeout(()=>void flush().catch(()=>{}),400);}
function flush(){clearTimeout(timer);chain=chain.catch(()=>{}).then(async()=>{if(!enabled||conflict)return;const pending=localStorage.getItem(PENDING);if(!pending)return;try{const saved=await request('/workspace',{method:'PUT',body:{workspace:JSON.parse(pending),expectedVersion:etag}});etag=saved.workspace.version;mark();if(localStorage.getItem(PENDING)===pending)localStorage.removeItem(PENDING);status('已保存到本地服务');}catch(error){conflict=error.code==='VERSION_CONFLICT';status(conflict?'发现数据版本冲突，请先备份并选择恢复版本':'尚未同步，浏览器副本仍保留');throw error;}});return chain;}
async function ensureCourse(courseId){const course=context?.store.courses.find(c=>c.id===courseId);if(course)await request('/courses',{method:'POST',body:{id:course.id,name:course.name,archived:!!course.archived}});}
const adapter={
  async uploadDocument({courseId,file,previousDocumentId},{signal,onProgress=()=>{}}={}){
    await ensureCourse(courseId);const query=new URLSearchParams({courseId,name:file.name,...(previousDocumentId?{previousDocumentId}:{})});
    const result=await request('/documents/upload?'+query,{method:'POST',body:file,signal,headers:{'Idempotency-Key':crypto.randomUUID()}});
    let job=result.job;
    while(!['succeeded','failed','cancelled','unknown'].includes(job.status)){signal?.throwIfAborted();onProgress(job.progress?.label?job.progress:{label:'等待后台解析',percent:5});await new Promise((resolve,reject)=>{const timeout=setTimeout(done,200);function done(){signal?.removeEventListener('abort',abort);resolve();}function abort(){clearTimeout(timeout);reject(signal.reason);}signal?.addEventListener('abort',abort,{once:true});});job=(await request('/jobs/status?id='+job.id,{signal})).job;}
    if(job.status!=='succeeded')throw new Error(job.error||'资料处理未完成，可在本地数据面板重试');const documents=(await request('/documents?'+new URLSearchParams({courseId}),{signal})).documents;const document=documents.find(d=>d.id===job.result.documentId);if(!document)throw new Error('解析完成但资料记录缺失');return document;
  },
  async listDocuments({courseId},options){await ensureCourse(courseId);return request('/documents?'+new URLSearchParams({courseId}),options);},
  async updateDocument(input,options){const result=await request('/documents/update',{...options,method:'POST',body:{...input,changes:input.metadata}});const doc=context?.state.documents.find(d=>d.id===input.documentId);if(doc)doc.version=result.document.version;return result;},
  async correctOCR({courseId,documentId,version,correction},{signal}={}){
    const source=await request('/rag/read?'+new URLSearchParams({courseId,sourceId:correction.sourceId}),{signal});
    const start=source.source.start-source.parent.start,end=source.source.end-source.parent.start;
    // B offsets count Unicode code points; JS string indices count UTF-16 units.
    const characters=Array.from(source.parent.text);
    const replacement=characters.slice(0,start).join('')+correction.text+characters.slice(end).join('');
    await request('/rag/correct',{method:'POST',signal,body:{courseId,documentId,version,blockId:source.parent.id,replacement,reason:'学习者对照原件核对纠错'}});
    const documents=(await request('/documents?'+new URLSearchParams({courseId}),{signal})).documents;
    const doc=context?.state.documents.find(d=>d.id===documentId),updated=documents.find(d=>d.id===documentId);
    if(doc&&updated)Object.assign(doc,updated);return{corrected:true};
  },
  removeDocument:(input,options)=>request('/documents/remove',{...options,method:'POST',body:input}),
  original:(input,options)=>request('/documents/original?'+new URLSearchParams(input),options)
};
function download(name,value){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function adopt(){
  const response=await request('/workspace');if(!response.workspace)throw new Error('本地服务暂无学习数据');
  restoring=true;clearTimeout(timer);
  try{const old=localStorage.getItem(KEY);if(old)localStorage.setItem('xueya-platform-before-restore-'+Date.now(),old);localStorage.setItem(KEY,JSON.stringify(response.workspace.data));localStorage.removeItem(PENDING);enabled=true;etag=response.workspace.version;mark();location.reload();}
  catch(error){restoring=false;throw error;}
}
function attach(ctx){
  context=ctx;if(!bootstrap)return;
  const button=document.createElement('button');button.type='button';button.className='subtle-button';button.id='platformData';button.textContent='本地数据';document.querySelector('.space-top-right')?.append(button);
  const dialog=document.createElement('dialog');dialog.id='platformDialog';dialog.className='source-dialog';dialog.setAttribute('aria-label','本地数据与任务');dialog.innerHTML='<div class="dialog-head"><strong>本地数据与任务</strong><button type="button" class="subtle-button" id="platformClose">关闭</button></div><div class="bank-dialog-body"><p id="platformStatus"></p><div class="dialog-actions"><button type="button" class="button button-outline button-small" id="platformBackup">导出浏览器备份</button><button type="button" class="button button-blue button-small" id="platformPreview">预览迁移到本地服务</button><button type="button" class="button button-outline button-small" id="platformRestore">使用服务端版本</button></div><pre id="platformPreviewText" style="white-space:pre-wrap;max-height:230px;overflow:auto"></pre><button type="button" class="button button-blue button-small" id="platformApply" hidden>确认迁移并启用同步</button><hr><h3>笔记写入确认</h3><p>预览内容后确认，才会保存到本地服务。</p><label class="form-field">标题<input id="platformNoteTitle" maxlength="200"></label><label class="form-field">内容<textarea id="platformNoteContent" rows="3"></textarea></label><button type="button" class="button button-outline button-small" id="platformNotePreview">生成写入预览</button><pre id="platformActionPreview" style="white-space:pre-wrap;max-height:200px;overflow:auto"></pre><button type="button" class="button button-blue button-small" id="platformNoteConfirm" hidden>确认保存笔记</button><hr><h3>后台任务</h3><div id="platformJobs"></div><p id="platformError" role="alert"></p></div>';
  document.body.append(dialog);const $=id=>document.getElementById(id);let preview,action;
  const safe=fn=>async()=>{try{$('platformError').textContent='';await fn();}catch(error){$('platformError').textContent=error.message;}};
  button.onclick=safe(async()=>{dialog.showModal();status(enabled?conflict?'同步冲突；请先导出浏览器备份':'自动同步已启用，修改会保留浏览器和本地服务副本':'目前保存在浏览器。迁移会保留原数据和备份，不会清空浏览器。');const jobs=(await request('/jobs')).jobs;$('platformJobs').replaceChildren();for(const job of jobs){const row=document.createElement('div');row.textContent=job.type+' · '+job.status+' · '+(job.error||'');for(const [label,endpoint] of ['queued','running','cancelling'].includes(job.status)?[['取消','cancel']]:['failed','cancelled'].includes(job.status)?[['重试','retry']]:[]){const b=document.createElement('button');b.textContent=label;b.type='button';b.className='subtle-button';b.onclick=safe(async()=>{await request('/jobs/'+endpoint,{method:'POST',body:{id:job.id}});row.textContent+=' · 已提交'+label;});row.append(b);}$('platformJobs').append(row);}});
  $('platformClose').onclick=()=>dialog.close();
  $('platformBackup').onclick=()=>download('xueya-browser-backup.json',{workspace:workspace(),raw:raw()});
  function raw(){return Object.fromEntries(['xueya-copilot-state-v1','xueya-copilot-state-v2',KEY,PENDING].map(key=>[key,localStorage.getItem(key)]));}
  $('platformPreview').onclick=safe(async()=>{preview=(await request('/migration/preview',{method:'POST',body:{workspace:workspace(),raw:raw()}})).preview;$('platformPreviewText').textContent=JSON.stringify(preview.counts,null,2)+(preview.expectedVersion?'\n本地服务已有数据；确认将以当前浏览器完整版本替换，原服务版本会保留备份。':'\n将建立本地服务副本。');$('platformApply').hidden=false;});
  $('platformApply').onclick=safe(async()=>{const result=await request('/migration/apply',{method:'POST',body:{id:preview.id,hash:preview.hash}});etag=result.version;enabled=true;conflict=false;mark();localStorage.removeItem(PENDING);$('platformApply').hidden=true;
    let originals=0,missing=0;const cache=globalThis.XueyaFileCache.createCache();
    for(const course of ctx.store.courses)for(const document of course.data.documents||[]){if(document.remote)continue;try{const file=await cache.get(document.id);if(!file){missing++;continue;}await request('/documents/import-original?'+new URLSearchParams({courseId:course.id,documentId:document.id}),{method:'POST',body:file});originals++;}catch{missing++;}}
    status('迁移完成，自动同步已启用。原件迁移'+originals+'份'+(missing?'，'+missing+'份原件不在当前缓存中，请保留文件或重新上传。':''));});
  $('platformRestore').onclick=safe(async()=>{download('xueya-before-restore.json',{workspace:workspace(),raw:raw()});await adopt();});
  $('platformNotePreview').onclick=safe(async()=>{if(!enabled)throw new Error('请先完成数据迁移并启用同步');await flush();action=(await request('/tools/call',{method:'POST',body:{courseId:ctx.state.courseId,name:'prepare_action',arguments:{kind:'note',entityId:'note-'+crypto.randomUUID(),expectedVersion:0,after:{title:$('platformNoteTitle').value,content:$('platformNoteContent').value,sourceIds:[]}}}})).data;$('platformActionPreview').textContent=JSON.stringify({before:action.before,after:action.after,expiresAt:new Date(action.expiresAt).toLocaleString()},null,2);$('platformNoteConfirm').hidden=false;});
  for(const id of ['platformNoteTitle','platformNoteContent'])$(id).oninput=()=>{$('platformNoteConfirm').hidden=true;action=null;};
  $('platformNoteConfirm').onclick=safe(async()=>{if(!action)throw new Error('请重新预览');await flush();const courseId=ctx.state.courseId;await request('/actions/confirm',{method:'POST',body:{courseId,actionId:action.actionId,digest:action.digest}});await request('/tools/call',{method:'POST',body:{courseId,name:'apply_action',arguments:{actionId:action.actionId}}});await adopt();});
  window.addEventListener('xueya:workspace-save',changed);if(enabled&&localStorage.getItem(PENDING))void flush().catch(()=>{});
}
window.XueyaPlatform={
  async ragRequest(path,body,{signal}={}){await ensureCourse(body.courseId);return request('/rag/'+path,{method:'POST',body,signal});},
  async learningRequest(path,{courseId='course-default',method='GET',body,signal,headers={}}={}){
    if(!bootstrap)throw Object.assign(new Error('请先启动本地服务，再刷新页面使用学习功能。'),{code:'SERVICE_UNAVAILABLE'});
    await ensureCourse(courseId);
    const separator=path.includes('?')?'&':'?';
    const response=await fetch('/api/learning/'+path+separator+new URLSearchParams({courseId}),{method,signal,headers:{'X-Xueya-Token':token,...(body!==undefined&&!(body instanceof Blob)?{'Content-Type':'application/json'}:{}),...headers},body:body===undefined?undefined:body instanceof Blob?body:JSON.stringify(body)});
    let result;try{result=await response.json();}catch{throw Object.assign(new Error('当前服务尚未启用课程学习接口，请使用最新版后端启动后刷新。'),{code:'SERVICE_UNAVAILABLE'});}if(!response.ok||!result.ok)throw Object.assign(new Error(result.error||'学习操作未完成'),{code:result.error});return result.result;
  },
  get isRestoring(){return restoring;},
  async initialize(){try{bootstrap=await request('/bootstrap',{signal:AbortSignal.timeout(3000)});token=bootstrap.token;let marker;try{marker=JSON.parse(localStorage.getItem(MARK));}catch{}enabled=!!marker?.enabled;etag=marker?.version||0;if(enabled&&bootstrap.workspace&&!localStorage.getItem(PENDING)){localStorage.setItem(KEY,JSON.stringify(bootstrap.workspace.data));etag=bootstrap.workspace.version;mark();}if(!window.XueyaWorkspaceBackend)window.XueyaWorkspaceBackend=adapter;}catch{bootstrap=null;}},attach,flush
};
})();
