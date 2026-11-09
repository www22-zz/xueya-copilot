/* Both catalog and graph open this same persisted question set. */
(() => {
  const e=window.XueyaRich.escape;
  async function mount(target,conceptId,courseId='course-default') {
    const stamp=crypto.randomUUID();target.dataset.practiceStamp=stamp;
    const alive=()=>target.isConnected&&target.dataset.practiceStamp===stamp;
    const api=async(path,body)=>{const r=await window.XueyaPlatform.spaceFetch('/api/learning/space/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!d.ok)throw Error(d.error);return d;};
    target.innerHTML='<p role="status">正在读取知识点练习…</p>';
    try {
      const [data,history]=await Promise.all([api('materials/concept/'+encodeURIComponent(conceptId)+'?courseId='+encodeURIComponent(courseId)),api('quiz/list')]);
      if(!alive())return;
      const key=(window.XueyaDataKey||((k)=>k))('concept-difficulty:'+conceptId);
      let difficulty=sessionStorage.getItem(key)||'简单';
      function draw(){
        const rows=data.groups[difficulty]||[];
        target.innerHTML=`<section class="concept-practice"><h3>${e(data.concept.label)} · 知识点练习</h3><p>${e(data.concept.description||'')}</p><p>来源版本 ${e(data.sourceRevision)} · ${(data.concept.locations||[]).map(l=>l.page?'第 '+e(l.page)+' 页':'页码未提供').join('、')}</p><nav class="heading-actions" aria-label="练习难度">${Object.entries(data.groups).map(([d,qs])=>`<button type="button" class="button button-outline" data-difficulty="${e(d)}" aria-pressed="${d===difficulty}">${e(d)} · ${qs.length}题</button>`).join('')}</nav><div data-concept-questions>${rows.map(q=>{const a=history.attempts.find(a=>a.questionId===q.id);return `<p>${e(q.difficultyReason||'难度依据尚未提供')} · ${a?'已有作答':'尚未作答'}</p><section class="study-quiz-card panel" data-quiz-card="${e(q.id)}" data-attempt-id="${e(a?.id||'')}"></section>`;}).join('')||'<p>该难度暂无题目。</p>'}</div>${difficulty!=='待分级'?'<details><summary>补充此难度练习</summary><p>仅使用此知识点的原资料，一次最多生成4题；失败与未知状态不会自动重试。</p><label><input type="checkbox" data-supplement-consent> 同意调用外部模型并产生费用</label><button type="button" class="button button-outline" data-supplement>准备补充题目</button></details>':'<p>旧题未记录难度，保留待分级，不按题型自动归类。</p>'}<p role="status" data-concept-status>${data.jobs.filter(j=>j.difficulty===difficulty).map(j=>'补题：'+e(({queued:'等待生成',running:'生成中',succeeded:'已保存',unknown:'结果待核对，不自动重试',failed:'生成失败',cancelled:'已取消'})[j.status]||j.status)+(j.error?' · '+e(j.error):'')).join('；')}</p></section>`;
        target.querySelectorAll('[data-difficulty]').forEach(b=>b.onclick=()=>{difficulty=b.dataset.difficulty;sessionStorage.setItem(key,difficulty);draw();});
        window.XueyaStudyQuiz.mount(target);
        target.querySelector('[data-supplement]')?.addEventListener('click',async event=>{
          const status=target.querySelector('[data-concept-status]');
          if(!target.querySelector('[data-supplement-consent]').checked){status.textContent='请先确认外部模型费用。';return;}
          event.currentTarget.disabled=true;
          try{const {job}=await api('materials/supplement',{conceptId,courseId,difficulty,confirmedExternal:true});if(alive())status.textContent='补题状态：'+job.status+'。重新打开本知识点查看已保存结果；相同请求复用原作业。';}
          catch(error){if(alive())status.textContent='补题未完成：'+error.message;}
        });
      }
      draw();
    } catch(error){if(alive())target.innerHTML=`<p role="alert">知识点练习暂不可用：${e(error.message)}</p>`;}
  }
  window.XueyaConceptPractice={mount};
})();
