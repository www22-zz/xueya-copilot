/* Route -> phase -> substage -> persisted concept exercises. */
(() => {
  const e=window.XueyaRich.escape;
  function mount(host,plan,{onFocusChange=()=>{},onPlanUpdate=()=>{}}={}){
    const practiceRequests=new Map();
    const key=(window.XueyaDataKey||((k)=>k))('learning-route:'+plan.id);
    let returnPoint=null;
    try{returnPoint=JSON.parse(sessionStorage.getItem(key+':position')||'null');}catch{}
    let selected=sessionStorage.getItem(key)||'',nodeId=sessionStorage.getItem(key+':node')||'',route=plan.learningRoute;
    const api=async(path,body)=>{const r=await window.XueyaPlatform.spaceFetch('/api/learning/space/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!d.ok)throw Error(d.error);return d;};
    async function refresh(){try{const d=await api('plan/list');const fresh=[d.active,...d.drafts,...d.history].find(p=>p?.id===plan.id);if(host.isConnected&&fresh){plan=fresh;route=fresh.learningRoute;draw();}}catch(error){if(host.isConnected)host.querySelector('[data-route-status]').textContent=error.message;}}
    function draw(){
      if(!route){host.innerHTML='<p>此历史计划尚未保存节点练习组。</p><button class="button button-outline" data-route-prepare>整理已有计划路线（不调用模型）</button><p data-route-status></p>';host.querySelector('button').onclick=async()=>{try{await api('plan/'+plan.id+'/route',{});await refresh();}catch(error){host.querySelector('[data-route-status]').textContent=error.message;}};return;}
      const all=route.phases.flatMap(p=>p.stages),stage=all.find(s=>s.id===selected);
      if(stage){renderDay(stage);onFocusChange(true);return;}
      onFocusChange(false);
      host.innerHTML=window.XueyaLearningOrbit.render(plan);
      window.XueyaLearningOrbit.bind(host);
      host.querySelectorAll('[data-route-stage]').forEach(button=>button.onclick=()=>{
        returnPoint={stageId:button.dataset.routeStage,date:button.dataset.routeDate,top:button.getBoundingClientRect().top};
        sessionStorage.setItem(key+':position',JSON.stringify(returnPoint));
        selected=button.dataset.routeStage;nodeId='';sessionStorage.setItem(key,selected);
        sessionStorage.removeItem(key+':node');
        if(button.dataset.routeDate)sessionStorage.setItem(key+':date',button.dataset.routeDate);else sessionStorage.removeItem(key+':date');
        draw();host.querySelector('.route-day-heading')?.focus({preventScroll:true});
        host.querySelector('.route-day-view')?.scrollIntoView({block:'start',behavior:'instant'});
      });
    }

    function renderDay(stage){
      const today=new Date().toLocaleDateString('en-CA');
      const rememberedDate=sessionStorage.getItem(key+':date');
      const node=stage.nodes.find(n=>n.id===nodeId);
      const date=node?.date||(stage.nodes.some(n=>n.date===rememberedDate)?rememberedDate:null)
        ||(stage.nodes.some(n=>n.date===today)?today:null)
        ||stage.nodes.find(n=>!n.completed)?.date||stage.nodes[0]?.date||stage.startDate;
      sessionStorage.setItem(key+':date',date);
      const tasks=stage.nodes.filter(n=>n.date===date);
      const video=tasks.map(n=>n.video).find(v=>v&&/^(#space\/|https?:\/\/)/.test(v.url||''));
      const questionCount=tasks.reduce((count,n)=>count+(n.questions||[]).length,0);
      const minutes=tasks.reduce((count,n)=>count+(n.minutes||0),0);
      const canAnswer=plan.status==='active';
      const missing=tasks.filter(n=>!(n.questions||[]).length&&!n.fixedPracticePrepared);
      const practiceKey=stage.id+':'+date,practiceState=practiceRequests.get(practiceKey);
      const preparing=missing.length>0&&practiceState!=='failed';
      const brief=tasks.find(n=>n.taskSummary);
      const points=[...new Set(tasks.flatMap(n=>n.knowledgePoints||[]))].slice(0,6);
      host.innerHTML=`<section class="route-day-view orbit-detail" aria-label="当日学习">
        <header class="route-day-header">
          <button type="button" class="route-day-back" data-node-back aria-label="返回我的计划">← 返回</button>
          <span>${e(date)} · ${date===today?'今日学习':'当日学习'}${!canAnswer?' · 预览':''}</span>
        </header>
        <div class="route-day-intro"><h2 class="route-day-heading" tabindex="-1">${e(stage.title)}</h2>
          <p>看视频，完成对应练习${minutes?' · 预计 '+e(minutes)+' 分钟':''}</p>
          <p class="route-task-summary">${e(brief?.taskSummary||'先通过视频梳理本次任务，再完成相关练习并核对解析。')}</p>
          ${points.length?`<ul class="route-knowledge-points" aria-label="本次知识点">${points.map(point=>`<li>${e(point)}</li>`).join('')}</ul>`:''}</div>
        <section class="route-day-video" aria-labelledby="route-video-${e(plan.id)}">
          <div class="route-day-section-title"><span aria-hidden="true">01</span><h3 id="route-video-${e(plan.id)}">视频学习</h3></div>
          ${video?`<a class="route-video-link" href="${e(video.url)}" data-route-video ${/^https?:/.test(video.url)?'target="_blank" rel="noopener noreferrer"':''}><span aria-hidden="true">▶</span><span>观看学习视频<small>${e(video.title||stage.title)}</small></span><span aria-hidden="true">↗</span></a>`:'<p class="route-day-empty">暂未匹配到这项学习任务的视频。</p>'}
        </section>
        <section class="route-day-exercises" aria-labelledby="route-questions-${e(plan.id)}">
          <div class="route-day-section-title"><span aria-hidden="true">02</span><h3 id="route-questions-${e(plan.id)}">对应练习</h3><small>${questionCount} 题</small></div>
          ${!canAnswer&&questionCount?'<p class="route-day-note">草稿中的题目可预览，采用计划后可提交作答。</p>':''}
          ${questionCount?tasks.map(n=>(n.questions||[]).map(q=>`<section class="study-quiz-card panel" data-quiz-card="${e(q.id)}" data-plan-id="${e(plan.id)}" data-plan-revision="${q.revision}" data-plan-node="${e(n.id)}"><p role="status">正在读取题目…</p></section>`).join('')).join(''):preparing?'<p class="route-day-empty" role="status">正在载入已有题库中的相关练习…</p>':practiceState==='failed'?'<p class="route-day-empty">现有练习暂未读取成功。</p><button type="button" class="button button-outline button-small" data-practice-retry>重新载入练习</button>':'<p class="route-day-empty">暂未匹配到这项任务的相关练习。</p>'}
        </section><p data-route-status role="status"></p>
      </section>`;
      host.querySelector('[data-node-back]').onclick=async()=>{
        host.dataset.orbitReturned='true';
        selected='';nodeId='';sessionStorage.removeItem(key);sessionStorage.removeItem(key+':node');sessionStorage.removeItem(key+':date');
        draw();await refresh();
        requestAnimationFrame(()=>{
          if(!host.isConnected||selected||!returnPoint)return;
          const button=[...host.querySelectorAll('[data-route-stage]')].find(b=>b.dataset.routeStage===returnPoint.stageId&&b.dataset.routeDate===returnPoint.date);
          if(button){button.focus({preventScroll:true});if(Number.isFinite(returnPoint.top))window.scrollBy({top:button.getBoundingClientRect().top-returnPoint.top,behavior:'instant'});}
        });
      };
      host.querySelector('[data-route-video]')?.addEventListener('click',()=>sessionStorage.setItem((window.XueyaDataKey||((k)=>k))('xueya-video-context'),JSON.stringify({courseId:video.courseId,label:stage.title,returnHash:location.hash,returnTab:'plan'})));
      window.XueyaStudyQuiz.mount(host,{readOnly:!canAnswer});
      const loadPractice=()=>{
        if(practiceRequests.get(practiceKey)==='pending')return;
        practiceRequests.set(practiceKey,'pending');
        api('plan/'+encodeURIComponent(plan.id)+'/practice',{nodeIds:missing.map(n=>n.id)}).then(value=>{
          if(!value.plan?.learningRoute)throw Error('PLAN_NOT_FOUND');
          practiceRequests.set(practiceKey,'done');
          if(!host.isConnected)return;
          plan=value.plan;route=plan.learningRoute;onPlanUpdate(plan);
          if(selected===stage.id&&sessionStorage.getItem(key+':date')===date){
            const focusHeading=document.activeElement===host.querySelector('.route-day-heading');
            draw();if(focusHeading)host.querySelector('.route-day-heading')?.focus({preventScroll:true});
          }
        }).catch(()=>{
          practiceRequests.set(practiceKey,'failed');
          if(host.isConnected&&selected===stage.id&&sessionStorage.getItem(key+':date')===date)draw();
        });
      };
      host.querySelector('[data-practice-retry]')?.addEventListener('click',()=>{practiceRequests.delete(practiceKey);draw();});
      if(missing.length&&!practiceState)loadPractice();
    }
    draw();
    return {reset(){
      selected='';nodeId='';sessionStorage.removeItem(key);sessionStorage.removeItem(key+':node');sessionStorage.removeItem(key+':date');draw();
    }};
  }
  window.XueyaLearningRoute={mount};
})();
