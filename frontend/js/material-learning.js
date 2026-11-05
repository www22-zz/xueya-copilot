/* Material catalog, selectable concept graph, and shared persisted quiz cards. */
(() => {
  'use strict';
  const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let generation=0,timer,subject='',selected='',selectedDocument='',nodeId='',autoPrepared=0;
  let cached=null,cacheCourse='',signature='',tab='graph',planUI=null;
  const attempted=new Set();
  async function api(path,body){
    const reply=await window.XueyaPlatform.spaceFetch('/api/learning/space/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
    return reply.json();
  }
  async function mount(container,courseId='course-default',local=false){
    if(!container)return;const stamp=++generation;clearTimeout(timer);
    try{
      if(!container.dataset.materialMounted){tab='graph';signature='';container.dataset.materialMounted='1';const parts=location.hash.split('/');if(parts[1]==='materials'&&parts[2]){selected=parts[2];nodeId=parts[3]||'';subject='';}}
      const selectionKey=(window.XueyaDataKey||((key)=>key))('xueya-material-selection:'+courseId);
      if(!selected){try{const saved=JSON.parse(localStorage.getItem(selectionKey)||'{}');selected=saved.selected||'';selectedDocument=saved.selectedDocument||'';subject=saved.subject||'';nodeId=saved.nodeId||'';}catch{}}
      if(!local||!cached||cacheCourse!==courseId){
        const [data,attendance]=await Promise.all([api('materials?courseId='+encodeURIComponent(courseId)),api('attendance')]);
        if(stamp!==generation||!container.isConnected)return;
        cached={data,attendance};cacheCourse=courseId;
      }
      const {data,attendance}=cached,nextSignature=JSON.stringify(cached);
      // Keep focused inputs, open answers and unchanged DOM intact during polling.
      if(!local&&container.querySelector('.material-learning')&&(signature===nextSignature||container.querySelector('[data-quiz-card]')||(container.contains(document.activeElement)&&document.activeElement.matches('input,textarea,select,[contenteditable=true]'))||tab!=='graph')){schedule();return;}
      signature=nextSignature;planUI?.unmount();
      const redraw=()=>mount(container,courseId,true);

      const materials=data.materials,subjects=[...new Set(materials.map(m=>m.subject))];
      const filtered=materials.filter(m=>!subject||m.subject===subject);
      const material=filtered.find(m=>m.id===selected)||filtered.find(m=>m.documentId===selectedDocument)||filtered[0];
      if(material){selected=material.id;selectedDocument=material.documentId;}
      const concept=material?.concepts.find(n=>n.id===nodeId)||material?.concepts[0];
      if(concept)nodeId=concept.id;
      try{localStorage.setItem(selectionKey,JSON.stringify({selected,selectedDocument,subject,nodeId}));}catch{}
      const status={parsing:'正在解析资料',queued:'等待出题',running:'正在生成',succeeded:'已生成',failed:'生成失败',unknown:'调用状态待核对',cancelled:'已取消','not-generated':'待准备'};
      const nodes=material?.concepts||[];
      container.innerHTML=`<section class="panel material-learning"><h1>课程资料学习</h1><p>选择资料，查看知识关系，并练习对应知识点。AI题目未经独立审校。</p>
        <nav class="heading-actions material-workflow" aria-label="资料学习流程"><button class="button button-outline" data-material-tab="graph" aria-pressed="${tab==='graph'}">知识点与练习</button><button class="button button-outline" data-material-tab="plan" aria-pressed="${tab==='plan'}">学习计划</button><button class="button button-outline" data-material-tab="video" aria-pressed="${tab==='video'}">配套课程</button><a class="button button-outline" href="#space/knowledge" data-material-manage>上传与管理</a><button class="button button-blue" type="button" data-attendance ${attendance.signed?'disabled':''}>${attendance.signed?'今日已签到':'每日签到'}</button></nav>
        <details><summary>签到记录（${attendance.timezone}）</summary>${attendance.history.map(row=>`<p>${e(row.date)}</p>`).join('')||'<p>还没有签到</p>'}<p>签到仅记录到访，不代表完成任务或掌握知识。</p></details>
        <div data-material-subview ${tab==='graph'?'hidden':''}></div><div data-material-graph-view ${tab!=='graph'?'hidden':''}>
        <label class="form-field">学科<select data-material-subject><option value="">全部学科</option>${subjects.map(s=>`<option ${s===subject?'selected':''}>${e(s)}</option>`).join('')}</select></label>
        <div class="materials-list">${filtered.map(m=>`<button type="button" class="button ${m.id===selected?'button-blue':'button-outline'}" data-material="${e(m.id)}">${e(m.name)} · ${e(status[m.status]||m.status)}</button>`).join('')||'<p>还没有可用资料，请先上传。</p>'}</div>
        ${material?`<h2>${e(material.name)}</h2><p>解析：${e(material.parseStatus)} · 出题：${e(status[material.status]||material.status)} ${e(material.error||'')}</p>
        ${material.ready&&!material.jobId&&data.available?'<button type="button" class="button button-outline" data-material-prepare>准备此资料题目</button>':''}
        ${material.coverage?`<p>${material.coverage.questions}题 · ${material.coverage.selectedChunks}/${material.coverage.totalChunks}个输入片段（不代表知识点全部覆盖）${material.coverage.partial?'，当前仅覆盖部分资料，不能视为整本教材已覆盖':''}</p>`:''}
        ${!material.ready?'<p>资料尚未达到可信解析状态，请先完成解析或校正确认。</p>':!data.available?'<p>模型尚未配置，暂不能生成题目。</p>':''}
        ${nodes.length?`<div class="heading-actions"><button class="button button-outline" data-graph-zoom="0.8">放大</button><button class="button button-outline" data-graph-zoom="1.25">缩小</button><button class="button button-outline" data-graph-reset>重置视图</button><label>查找知识点<input type="search" data-graph-search></label></div><div class="material-graph" role="group" aria-label="资料知识图谱"><svg viewBox="0 0 640 420" aria-label="知识点关系图" style="width:100%;max-height:440px;touch-action:none">
          ${nodes.map((n,i)=>{const angle=2*Math.PI*i/nodes.length;return `<line x1="320" y1="210" x2="${320+200*Math.cos(angle)}" y2="${210+145*Math.sin(angle)}" stroke="var(--stitch-outline-variant)"/>`;}).join('')}
          <circle cx="320" cy="210" r="48" fill="var(--stitch-primary-fixed)"/><text x="320" y="215" text-anchor="middle" fill="var(--stitch-on-surface)">资料主题</text>
          ${nodes.map((n,i)=>{const a=2*Math.PI*i/nodes.length,x=320+200*Math.cos(a),y=210+145*Math.sin(a);return `<g data-node="${e(n.id)}" role="button" tabindex="0" aria-label="${e(n.label)}"><title>${e(n.label)}</title><circle cx="${x}" cy="${y}" r="48" fill="var(--stitch-surface-container-high)" stroke="${n.id===nodeId?'var(--stitch-primary)':'var(--stitch-outline-variant)'}"/><text x="${x}" y="${y}" text-anchor="middle" fill="var(--stitch-on-surface)" font-size="12">${Array.from(n.label).slice(0,21).reduce((rows,c,i)=>{if(i%7===0)rows.push('');rows[rows.length-1]+=c;return rows;},[]).map((line,j)=>`<tspan x="${x}" dy="${j?15:-10}">${e(line)}</tspan>`).join('')}</text></g>`;}).join('')}</svg><p>连线表示本资料包含的知识点；当前不推断先修关系。</p></div>
          ${concept?`<section><h3>${e(concept.label)}</h3><p>${e(concept.description)}</p><p>${concept.questionIds.length}道关联题 · ${concept.locations.map(l=>l.page?'第'+e(l.page)+'页':'位置未提供').join('、')}</p><button type="button" class="button button-blue" data-material-practice>练习此知识点</button><div data-material-questions></div></section>`:''}`:'<p>题目生成成功后将在此展示可点击的知识点图谱。</p>'}`:''}
        </div><p role="status" data-material-status></p></section>`;
      container.querySelectorAll('[data-material-tab]').forEach(button=>button.onclick=()=>{tab=button.dataset.materialTab;redraw();});
      container.querySelector('[data-material-manage]').onclick=()=>{try{sessionStorage.setItem((window.XueyaDataKey||((key)=>key))('xueya-material-return'),JSON.stringify({hash:'#space/materials/'+selected+'/'+nodeId,name:material?.name||'课程资料学习'}));}catch{}};
      if(tab==='plan'){
        const target=container.querySelector('[data-material-subview]');target.innerHTML='<h2>学习计划</h2><p>计划使用当前账号的资料与题目；完成后切回知识点与练习继续。</p><div data-material-plan></div>';
        planUI||=window.XueyaPlan.create({toast:window.toast,navigate:hash=>{location.hash=hash;}});planUI.mount(target.querySelector('[data-material-plan]'));
      }
      if(tab==='video'){
        const target=container.querySelector('[data-material-subview]');target.innerHTML='<h2>配套课程</h2><p>官方课程总览，尚未精确匹配知识点分集。在新标签打开，保留当前学习位置。</p>';
        api('courses').then(({courses:rows})=>{if(stamp!==generation||!container.isConnected)return;target.insertAdjacentHTML('beforeend',rows.filter(c=>c.sourceUrl).map(c=>`<a class="material-video" href="${e(c.sourceUrl)}" target="_blank" rel="noopener noreferrer"><strong>${e(c.title)}</strong><span>官方原站 ↗</span></a>`).join('')||'<p>暂无课程入口。</p>');}).catch(()=>{if(target.isConnected)target.insertAdjacentHTML('beforeend','<p>课程目录读取失败，请切回后重试。</p>');});
      }
      container.querySelector('[data-material-subject]').onchange=event=>{subject=event.target.value;redraw();};
      container.querySelector('[data-attendance]').onclick=async()=>{try{cached.attendance=await api('attendance',{});redraw();}catch(error){container.querySelector('[data-material-status]').textContent=error.message;}};
      container.querySelector('[data-material-prepare]')?.addEventListener('click',async()=>{try{await api('materials/prepare',{documentId:material.documentId,sourceCourseId:material.sourceCourseId,public:material.public,courseId});mount(container,courseId);}catch(error){container.querySelector('[data-material-status]').textContent=error.message;}});
      container.querySelectorAll('[data-material]').forEach(button=>button.onclick=()=>{selected=button.dataset.material;nodeId='';redraw();});
      container.querySelectorAll('[data-node]').forEach(button=>{
        const select=()=>{nodeId=button.dataset.node;redraw();};button.onclick=select;button.onkeydown=event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();select();}};
      });
      const svg=container.querySelector('.material-graph svg');
      if(svg){
        const poseKey=selectionKey+':graph:'+selected;let box=[0,0,640,420];
        try{const saved=JSON.parse(localStorage.getItem(poseKey));if(Array.isArray(saved)&&saved.length===4&&saved.every(Number.isFinite)&&saved[2]>=200&&saved[2]<=2000)box=saved;}catch{}
        const apply=(save=true)=>{svg.setAttribute('viewBox',box.join(' '));if(save)try{localStorage.setItem(poseKey,JSON.stringify(box));}catch{}};apply();
        container.querySelectorAll('[data-graph-zoom]').forEach(button=>button.onclick=()=>{const f=Number(button.dataset.graphZoom),width=Math.max(200,Math.min(2000,box[2]*f)),height=width*420/640;box=[box[0]+(box[2]-width)/2,box[1]+(box[3]-height)/2,width,height];apply();});
        container.querySelector('[data-graph-reset]').onclick=()=>{box=[0,0,640,420];apply();};
        container.querySelector('[data-graph-search]').onchange=event=>{const match=nodes.find(n=>n.label.includes(event.target.value.trim()));if(match){nodeId=match.id;redraw();}else container.querySelector('[data-material-status]').textContent='没有匹配的知识点';};
        let drag;
        svg.onpointerdown=event=>{if(event.target.closest('[data-node]'))return;drag={x:event.clientX,y:event.clientY,box:[...box]};svg.setPointerCapture(event.pointerId);};
        svg.onpointermove=event=>{if(!drag)return;const rect=svg.getBoundingClientRect();box=[drag.box[0]-(event.clientX-drag.x)*drag.box[2]/rect.width,drag.box[1]-(event.clientY-drag.y)*drag.box[3]/rect.height,drag.box[2],drag.box[3]];apply(false);};
        svg.onpointerup=svg.onpointercancel=()=>{if(drag)apply();drag=null;};
      }
      container.querySelector('[data-material-practice]')?.addEventListener('click',()=>{
        const target=container.querySelector('[data-material-questions]');
        target.innerHTML=concept.questionIds.map(id=>`<section class="study-quiz-card panel" data-quiz-card="${e(id)}" aria-label="知识点练习"></section>`).join('');
        window.XueyaStudyQuiz.mount(target);target.scrollIntoView({block:'start',behavior:'smooth'});
      });
      // Existing accessible materials are prepared once; each document batch is
      // bounded server-side. Refreshing never retries a failed or unknown job.
      container.onclick=event=>{const link=event.target.closest('a[href^="#space/"]');if(link)try{sessionStorage.setItem((window.XueyaDataKey||((key)=>key))('xueya-material-return'),JSON.stringify({hash:'#space/materials/'+selected+'/'+nodeId,name:material?.name||'课程资料学习'}));}catch{}};
      if(data.available){
        for(const m of materials.filter(m=>m.ready&&!m.jobId&&!attempted.has(m.id)).slice(0,Math.max(0,20-autoPrepared))){
          attempted.add(m.id);autoPrepared++;
          try{await api('materials/prepare',{documentId:m.documentId,sourceCourseId:m.sourceCourseId,public:m.public,courseId});m.status='queued';if(stamp!==generation||!container.isConnected)return;}
          catch(error){container.querySelector('[data-material-status]').textContent=error.message;}
        }
      }
      schedule();
      function schedule(){
        clearTimeout(timer);
        if(data.materials.some(m=>m.status==='parsing'||(['queued','running'].includes(m.status)&&m.ready&&data.available)))timer=setTimeout(()=>{if(container.isConnected&&!document.hidden)mount(container,courseId);else if(container.isConnected)schedule();},8000);
      }

    }catch(error){if(stamp===generation&&container.isConnected)container.innerHTML=`<p role="alert">资料学习暂不可用：${e(error.message)}</p>`;}
  }
  window.XueyaMaterialLearning={mount,unmount(){generation++;clearTimeout(timer);planUI?.unmount();cached=null;signature='';}};
})();
