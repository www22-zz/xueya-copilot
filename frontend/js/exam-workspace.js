/* Timed 408 mock papers. Saved server snapshots decide answers and deadlines. */
(() => {
  'use strict';
  const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let generation=0,timer;
  async function api(path,body){const r=await window.XueyaPlatform.spaceFetch('/api/learning/space/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});return r.json();}
  async function mount(container,id){
    const stamp=++generation;clearTimeout(timer);if(!container)return;
    try{
      if(!id){
        const data=await api('exams');if(stamp!==generation||!container.isConnected)return;
        container.innerHTML=`<section class="panel"><h1>408考研学习</h1><nav class="heading-actions"><a class="button button-outline" href="#space/practice/exam408">分科练习</a><a class="button button-outline" href="#space/courses">课程视频</a></nav><h2>真题套卷</h2><p>${e(data.originalPaperStatus)}</p>
          <details><summary>按年份打开原卷与整理解析</summary>${data.originalPapers.map(p=>`<p>${e(p.year)}：<a href="${e(p.paper)}" target="_blank" rel="noopener noreferrer">真题原卷 PDF</a> · <a href="${e(p.answers)}" target="_blank" rel="noopener noreferrer">高校整理解析（非考试院官方评分）</a></p>`).join('')}</details>
          <h2>模拟考试</h2><p>程序组卷与AI选题均使用已保存固定题；不标为历年真题。本阶段计时卷使用客观单选题，主观题继续在分科练习中作答和参考评阅。</p>
          <form data-create-exam><label class="form-field">科目<select name="subject"><option value="">全部408科目</option>${data.subjects.map(s=>`<option>${e(s)}</option>`).join('')}</select></label><label class="form-field">题量<input name="count" type="number" min="1" max="40" value="10" required></label><label class="form-field">时长（分钟）<input name="minutes" type="number" min="1" max="180" value="30" required></label><label class="form-field">组卷方式<select name="mode"><option value="fixed">程序选编模拟卷（不调用AI）</option><option value="ai">AI选题模拟卷（调用模型）</option></select></label><button class="button button-blue" type="submit">生成模拟卷</button></form>
          <p role="status" data-exam-status>${data.jobs.filter(j=>j.status!=='succeeded').map(j=>'AI组卷：'+e(j.status)).join('；')}</p><h2>我的试卷</h2>${data.sessions.map(s=>`<p><a href="#space/exams/${e(s.id)}">${e(s.label)} · ${e(s.status)} · ${s.questions.length}题</a></p>`).join('')||'<p>还没有试卷</p>'}</section>`;
        container.querySelector('[data-create-exam]').onsubmit=async event=>{
          event.preventDefault();const button=event.target.querySelector('button[type=submit]');button.disabled=true;
          const values=Object.fromEntries(new FormData(event.target));
          try{const result=await api('exams',{...values,count:Number(values.count),minutes:Number(values.minutes),operationId:crypto.randomUUID()});
            if(result.session)location.hash='space/exams/'+result.session.id;
            else{container.querySelector('[data-exam-status]').textContent='AI选题已提交，正在生成；刷新不会重新付费。';timer=setTimeout(()=>mount(container),1500);}
          }catch(error){container.querySelector('[data-exam-status]').textContent=error.message;button.disabled=false;}
        };
        if(data.jobs.some(j=>['queued','running'].includes(j.status)))timer=setTimeout(()=>{if(container.isConnected)mount(container);},2000);
        return;
      }
      let paper=(await api('exams/'+encodeURIComponent(id))).session;
      if(stamp!==generation||!container.isConnected)return;
      let busy=false;
      function draw(){
        if(!container.isConnected)return;
        const active=paper.status==='running',done=paper.status==='submitted';
        container.innerHTML=`<section class="panel"><a href="#space/exams">← 试卷列表</a><h1>${e(paper.label)}</h1><p>试卷版本：${e(paper.bankVersion)} · ${e(paper.status)}</p>${paper.assembly?.method==='ai-candidates-program-quota'?`<p>AI推荐了${paper.assembly.recommendedCount}道合法候选，程序按科目轮选${paper.assembly.selectedCount}道组成试卷；未把超额推荐直接当作整卷。</p>`:''}<p role="status" data-exam-clock></p>
          ${paper.status==='ready'?'<button class="button button-blue" data-exam-start>开始计时考试</button>':''}
          ${done?`<h2>得分：${paper.result.score}/${paper.result.maxScore}</h2><p>未作答：${paper.result.unanswered}题</p>`:''}
          ${paper.status!=='ready'?paper.questions.map((q,i)=>`<article class="panel"><h3>${i+1}. ${e(q.title||'')}</h3><p>${e(q.prompt||'')}</p>${q.options.map((option,n)=>`<label style="display:block;padding:8px"><input type="radio" name="${e(q.id)}" value="${n}" data-exam-answer ${paper.answers[q.id]===n?'checked':''} ${!active?'disabled':''}>${e(option)}</label>`).join('')}${done?`<p>正确答案：${e(q.options[q.answer])}</p><p>${e(q.explanation)}</p>`:''}</article>`).join(''):''}
          ${active?'<button class="button button-blue" data-exam-submit>交卷并评分</button>':''}<p role="status" data-exam-save></p></section>`;
        async function action(name,extra={}){
          if(busy)return;busy=true;
          container.querySelectorAll('button,input').forEach(el=>el.disabled=true);
          try{paper=(await api('exams/'+id+'/'+name,{expectedRevision:paper.revision,...extra})).session;draw();}
          catch(error){container.querySelector('[data-exam-save]').textContent='未保存：'+error.message+'；请刷新核对服务端记录。';}
          finally{busy=false;}
        }
        container.querySelector('[data-exam-start]')?.addEventListener('click',()=>action('start'));
        container.querySelectorAll('[data-exam-answer]').forEach(input=>input.onchange=()=>action('answers',{answers:{[input.name]:Number(input.value)}}));
        container.querySelector('[data-exam-submit]')?.addEventListener('click',()=>action('submit'));
        const end=Date.now()+Math.max(0,(paper.deadline||0)-paper.serverNow)*1000;
        clearInterval(timer);
        if(active)timer=setInterval(async()=>{
          if(!container.isConnected||stamp!==generation){clearInterval(timer);return;}
          const left=Math.max(0,Math.ceil((end-Date.now())/1000));
          container.querySelector('[data-exam-clock]').textContent=`剩余 ${Math.floor(left/60)}分${left%60}秒，作答逐题保存。`;
          if(left===0&&!busy){clearInterval(timer);try{paper=(await api('exams/'+id)).session;draw();}catch(error){container.querySelector('[data-exam-save]').textContent=error.message;}}
        },500);
      }
      draw();
    }catch(error){if(container.isConnected&&stamp===generation)container.innerHTML=`<p role="alert">试卷暂不可用：${e(error.message)}</p>`;}
  }
  window.XueyaExamWorkspace={mount};
})();
