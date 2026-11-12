/* Material catalog, selectable concept graph, and shared persisted quiz cards. */
(() => {
  'use strict';
  const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let generation=0,timer,subject='',selected='',selectedDocument='',nodeId='',autoPrepared=0;
  let cached=null,cacheCourse='',signature='',tab='corpus',planUI=null,videoUI=null,mountedLocation='',mountedCourse='';
  const attempted=new Set();
  async function api(path,body){
    const reply=await window.XueyaPlatform.spaceFetch('/api/learning/space/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
    return reply.json();
  }
  async function mount(container,courseId='course-default',local=false){
    if(!container)return;const entering=!container.dataset.materialMounted,stamp=++generation;clearTimeout(timer);
    try{
      if(!container.dataset.materialMounted){const parts=location.hash.split('/'),deep=parts[1]==='materials'?(parts[2]||''):'',namedTabs=['corpus','video','plan'];if(mountedLocation!==location.hash||mountedCourse!==courseId)tab=namedTabs.includes(deep)?deep:'corpus';mountedLocation=location.hash;mountedCourse=courseId;signature='';container.dataset.materialMounted='1';if(deep&&!namedTabs.includes(deep)&&deep!=='graph'){selected=deep;nodeId=parts[3]||'';subject='';}}
      const returnTabKey=(window.XueyaDataKey||((key)=>key))('xueya-material-return-tab');
      if(entering){const returnTab=sessionStorage.getItem(returnTabKey);if(['corpus','plan'].includes(returnTab)&&!['corpus','video','plan'].includes(location.hash.split('/')[2])){tab=returnTab;sessionStorage.removeItem(returnTabKey);}}
      const selectionKey=(window.XueyaDataKey||((key)=>key))('xueya-material-selection:'+courseId);
      if(!selected){try{const saved=JSON.parse(localStorage.getItem(selectionKey)||'{}');selected=saved.selected||'';selectedDocument=saved.selectedDocument||'';subject=saved.subject||'';nodeId=saved.nodeId||'';}catch{}}
      if(!local||!cached||cacheCourse!==courseId){
        const [data,attendance]=await Promise.all([api('materials?courseId='+encodeURIComponent(courseId)),api('attendance')]);
        if(stamp!==generation||!container.isConnected)return;
        cached={data,attendance};cacheCourse=courseId;
      }
      const {data,attendance}=cached,nextSignature=JSON.stringify(cached);
      // Keep focused inputs, open answers and unchanged DOM intact during polling.
      if(!local&&container.dataset.renderedTab===tab&&container.querySelector('.material-learning')&&(signature===nextSignature||container.querySelector('[data-quiz-card]')||(container.contains(document.activeElement)&&document.activeElement.matches('input,textarea,select,[contenteditable=true]'))||tab!=='graph')){schedule();return;}
      signature=nextSignature;planUI?.unmount();videoUI?.unmount();window.XueyaCourseGraph?.unmount();
      const redraw=()=>mount(container,courseId,true);

      const materials=data.materials,subjects=[...new Set(materials.map(m=>m.subject))];
      const filtered=materials.filter(m=>!subject||m.subject===subject);
      const requested=filtered.find(m=>m.id===selected)||filtered.find(m=>m.documentId===selectedDocument);
      const hasExplicitTarget=Boolean(location.hash.split('/')[2]);
      const material=(entering&&!hasExplicitTarget&&!requested?.concepts?.length?filtered.find(m=>m.concepts?.length):requested)||requested||filtered.find(m=>m.concepts?.length)||filtered.find(m=>m.ready)||filtered[0];
      const materialStatus=m=>String(m.parseStatus||'').startsWith('示例')&&!m.revision?'示例记录 · 无原件':status[m.status]||m.status;

      if(material){selected=material.id;selectedDocument=material.documentId;}
      try{localStorage.setItem(selectionKey,JSON.stringify({selected,selectedDocument,subject,nodeId}));}catch{}
      const status={parsing:'正在解析资料',queued:'等待出题',running:'正在生成',succeeded:'已生成',failed:'生成失败',unknown:'调用状态待核对',cancelled:'已取消','not-generated':'待准备'};
      container.innerHTML=`<section class="panel material-learning"><h1 class="visually-hidden">课程资料学习</h1>
        <nav class="heading-actions material-workflow" aria-label="资料学习流程"><button class="button button-outline" data-material-tab="corpus" aria-pressed="${tab==='corpus'}">课程书架与知识图谱</button><button class="button button-outline" data-material-tab="video" aria-pressed="${tab==='video'}">视频目录</button><button class="button button-outline" data-material-tab="plan" aria-pressed="${tab==='plan'}">个性化学习</button><a class="button button-outline" href="#space/knowledge" data-material-manage>个人资料库</a><a class="button button-outline" href="#space/practice/legacy">课程固定练习</a><button class="button button-blue" type="button" data-attendance ${attendance.signed?'disabled':''}>${attendance.signed?'今日已签到':'每日签到'}</button></nav>
        <div data-material-subview></div>
        <p role="status" data-material-status></p></section>`;
      container.dataset.renderedTab=tab;
      container.querySelectorAll('[data-material-tab]').forEach(button=>button.onclick=()=>{tab=button.dataset.materialTab;redraw();});
      container.querySelector('[data-material-manage]').onclick=()=>{try{sessionStorage.setItem((window.XueyaDataKey||((key)=>key))('xueya-material-return'),JSON.stringify({hash:'#space/materials/'+selected+'/'+nodeId,name:material?.name||'课程资料学习'}));}catch{}};
      if(tab==='corpus'){window.XueyaCourseGraph.mount(container.querySelector('[data-material-subview]'),courseId,location.hash.split('/')[2]);}
      if(tab==='plan'){
        const target=container.querySelector('[data-material-subview]');target.innerHTML='<div data-material-plan></div>';
        planUI=window.XueyaPlanWorkbench?.create?window.XueyaPlanWorkbench.create({toast:window.toast,navigate:hash=>{location.hash=hash;}}):window.XueyaPlan.create({toast:window.toast,navigate:hash=>{location.hash=hash;}});planUI.mount(target.querySelector('[data-material-plan]'));
      }
      if(tab==='video'){
        const target=container.querySelector('[data-material-subview]');
        const drawVideo=()=>{if(stamp!==generation||!target.isConnected)return;target.innerHTML='<h2>课程资料 · 视频目录</h2><p>全部课程均可站内播放；讲师与分集信息已核验。返回知识图谱可继续原知识点。</p>'+videoUI.render();videoUI.mount();};
        videoUI=window.XueyaCourses.create({host:target,embedded:true,toast:window.toast,render:drawVideo,navigate:hash=>location.hash=hash});drawVideo();
      }
      container.querySelector('[data-material-subject]')?.addEventListener('change',event=>{subject=event.target.value;redraw();});
      container.querySelector('[data-attendance]').onclick=async()=>{try{cached.attendance=await api('attendance',{});redraw();}catch(error){container.querySelector('[data-material-status]').textContent=error.message;}};
      container.querySelector('[data-material-prepare]')?.addEventListener('click',async()=>{try{await api('materials/prepare',{documentId:material.documentId,sourceCourseId:material.sourceCourseId,public:material.public,courseId});mount(container,courseId);}catch(error){container.querySelector('[data-material-status]').textContent=error.message;}});
      container.querySelectorAll('[data-material]').forEach(button=>button.onclick=()=>{selected=button.dataset.material;nodeId='';redraw();});
      // Existing accessible materials are prepared once; each document batch is
      // bounded server-side. Refreshing never retries a failed or unknown job.
      container.onclick=event=>{const link=event.target.closest('a[href^="#space/"]');if(link)try{sessionStorage.setItem((window.XueyaDataKey||((key)=>key))('xueya-material-return'),JSON.stringify({hash:'#space/materials/'+selected+'/'+nodeId,name:material?.name||'课程资料学习'}));}catch{}};
      schedule();
      function schedule(){
        clearTimeout(timer);
        if(tab==='corpus'&&data.materials.some(m=>m.status==='parsing'||(['queued','running'].includes(m.status)&&m.ready&&data.available)))timer=setTimeout(()=>{if(container.isConnected&&!document.hidden)mount(container,courseId);else if(container.isConnected)schedule();},8000);
      }

    }catch(error){if(stamp===generation&&container.isConnected)container.innerHTML=`<p role="alert">资料学习暂不可用：${e(error.message)}</p>`;}
  }
  window.XueyaMaterialLearning={mount,unmount(){if(!location.hash.startsWith('#space/materials'))mountedLocation='';generation++;clearTimeout(timer);planUI?.unmount();videoUI?.unmount();window.XueyaCourseGraph?.unmount();cached=null;signature='';}};
})();
