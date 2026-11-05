/* Shared question cards for conversation and the private practice directory. */
(function(root){
  'use strict';
  const e=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const restoring=new Set();
  async function api(path,body,signal){
    const response=await root.XueyaPlatform.spaceFetch('/api/learning/space/'+path,{
      ...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal});
    const value=await response.json();if(!value.ok)throw Error(value.error);return value;
  }
  async function generated(jobId,signal){
    while(true){
      signal?.throwIfAborted();const {job}=await api('jobs/'+encodeURIComponent(jobId),undefined,signal);
      if(job.status==='succeeded')return {answer:'小测题目已保存。可以在对话内作答，也可以从练习打开同一题目与作答。AI 生成题尚未经独立审校。',sources:[],engine:'AI 小测',online:true,
        artifacts:{quiz:{status:'succeeded',jobId,questionIds:job.result.questionIds}}};
      if(['unknown','failed','cancelled'].includes(job.status))return {answer:'小测生成未完成（'+job.status+'），没有创建占位题目，也不会自动重发请求。',sources:[],engine:'小测未完成',online:false,answerStatus:'unavailable',artifacts:{quiz:{status:job.status,jobId}}};
      await new Promise(resolve=>setTimeout(resolve,300));
    }
  }
  async function tryChat(input,{signal,onReference=()=>{}}={}){
    const value=await api('chat/quiz',input,signal);if(!value.handled)return null;
    if(value.questionIds)return {answer:'已找到固定题库中的相关题目，可直接作答。',sources:[],engine:'固定题小测',online:false,artifacts:{quiz:{status:'succeeded',questionIds:value.questionIds}}};
    onReference({status:'queued',jobId:value.jobId});
    const cancel=()=>api('jobs/'+encodeURIComponent(value.jobId)+'/cancel',{}).catch(()=>{});
    signal?.addEventListener('abort',cancel,{once:true});
    try{return await generated(value.jobId,signal);}finally{signal?.removeEventListener('abort',cancel);}
  }
  function shell(questionId,attemptId='',messageId=''){
    return `<section class="study-quiz-card panel" data-quiz-card="${e(questionId)}" data-attempt-id="${e(attemptId)}" data-chat-message="${e(messageId)}" aria-label="小测题卡"><p role="status">正在读取已保存题目…</p></section>`;
  }
  function markup(message){
    const ref=message.artifacts?.quiz;if(!ref)return '';
    return (ref.questionIds||[]).map(id=>shell(id,ref.attemptIds?.[id],message.id)).join('')+`<a href="#space/practice/ai">我的小测与作答</a>`;
  }
  const labels={'objective':'程序判定','objective-recheck':'程序复核','ai-reference':'AI 参考评阅','ai-review':'AI 复核','human':'人工修正','legacy-assessment':'历史评阅（旧来源）'};
  function evaluations(attempt){
    if(!attempt)return '';
    return `<p>作答已保存 · ${e(attempt.createdAt)}</p><p>${attempt.effectiveEvaluation?.status==='disputed'?'当前结论：争议待核对':''}</p>
      <details open><summary>评阅版本与来源 (${attempt.evaluations.length})</summary>${attempt.evaluations.map((entry,index)=>{
        const value=entry.result||{};
        return `<section class="quiz-evaluation"><strong>版本 ${index+1} · ${e(labels[entry.source]||entry.source)} · ${e(entry.status)}</strong><p>${e(entry.createdAt)}${value.model?' · '+e(value.model):''}</p>${entry.reason?`<p>理由：${e(entry.reason)}</p>`:''}
          ${entry.status==='graded'?`<p>${typeof value.correct==='boolean'?(value.correct?'判定正确':'判定错误')+' · ':''}${Number.isFinite(value.score)?e(value.score)+' / '+e(value.maxScore):'仅内容点评，不给总分'}</p><p>${e(value.feedback||value.explanation||'')}</p>`:'<p>评阅尚未形成有效分数，不计为零分或错误；不会自动付费重试。</p>'}</section>`;
      }).join('')}</details><p><a href="#space/practice/ai/${e(attempt.questionId)}/${e(attempt.id)}">在练习打开同一次作答</a></p>`;
  }
  function draftKey(id){return (root.XueyaDataKey||((k)=>k))('xueya-quiz-answer:'+id);}
  function mount(container){
    container?.querySelectorAll('[data-quiz-card]').forEach(async node=>{
      if(node.dataset.mounted)return;node.dataset.mounted='1';const id=node.dataset.quizCard;
      try{
        const {question:q}=await api('quiz/question/'+encodeURIComponent(id));
        const directory=await api('quiz/list');
        let attempt=node.dataset.attemptId?(await api('quiz/attempts/'+encodeURIComponent(node.dataset.attemptId))).attempt:directory.attempts.find(a=>a.questionId===id);
        let draft='';try{draft=sessionStorage.getItem(draftKey(id))||'';}catch{}
        function draw(){
          if(!node.isConnected)return;
          node.innerHTML=`<header><strong>${e(q.sourceType==='fixed-reference'?'固定题参考评阅':q.sourceType==='fixed'?'固定题库':'AI 生成题（未独立审校）')} · ${e(({single:'单选题',multiple:'多选题（全对得分）',boolean:'判断题',fill:'填空题（未匹配待复核）',short:'主观题'})[q.type])}</strong><h3>${e(q.subject)}</h3></header><p class="study-quiz-prompt">${e(q.prompt)}</p>${(q.limitations||[]).map(text=>`<p>${e(text)}</p>`).join('')}
            ${attempt?`<details><summary>本次原始答案（题目版本 ${e(attempt.questionRevision??'旧记录未保存')}）</summary><p>${e(attempt.questionSnapshotView?.prompt||'旧记录未保存完整题目快照')}</p><p>${e(q.type==='single'&&attempt.questionSnapshotView?.options?attempt.questionSnapshotView.options[attempt.answer]:attempt.answer)}</p></details>`:''}
            <form data-quiz-answer>${['single','multiple','boolean'].includes(q.type)?(q.type==='boolean'?['正确','错误']:q.options).map((option,index)=>`<label class="study-quiz-option"><input type="${q.type==='multiple'?'checkbox':'radio'}" name="answer" value="${index}" ${q.type!=='multiple'?'required':''}>${e(option)}</label>`).join(''):q.type==='fill'?Array.from({length:q.blankCount},(_,i)=>`<label>第${i+1}空<input name="answer" maxlength="500" required></label>`).join(''):`<label>完整答案<textarea name="answer" rows="5" maxlength="20000" required>${e(draft)}</textarea></label>`}

              <button type="submit" class="button button-blue button-small">${attempt?'再次作答（新增一次作答）':'保存并提交作答'}</button></form>
            ${evaluations(attempt)}${attempt?.canReview?'<button type="button" class="button button-outline button-small" data-quiz-review>说明理由并复核</button><button type="button" class="button button-outline button-small" data-quiz-correct>人工修正 / 标记争议</button>':attempt?'<p>旧记录缺少题目快照，保留阅读；重新作答后可使用版本化评阅。</p>':''}<p role="status" data-quiz-status></p>`;
          const answerForm=node.querySelector('[data-quiz-answer]');
          let values;try{values=JSON.parse(draft);}catch{values=draft;}
          if(q.type!=='short')answerForm.querySelectorAll('[name=answer]').forEach((input,index)=>{
            if(q.type==='fill')input.value=Array.isArray(values)?values[index]||'':'';
            else input.checked=q.type==='multiple'?Array.isArray(values)&&values.includes(input.value):String(values)===input.value;
          });
          answerForm.oninput=()=>{const values=new FormData(answerForm).getAll('answer');draft=q.type==='short'?String(values[0]||''):JSON.stringify(['multiple','fill'].includes(q.type)?values:values[0]);try{sessionStorage.setItem(draftKey(id),draft);}catch{}};
          const status=node.querySelector('[data-quiz-status]');
          const action=operation=>async event=>{
            event?.preventDefault();const buttons=node.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);
            try{await operation();}catch(error){if(node.isConnected)status.textContent=error.message||'操作未完成，请核对已保存记录后重试。';}
            finally{if(node.isConnected)buttons.forEach(b=>b.disabled=false);}
          };
          node.querySelector('form').onsubmit=action(async()=>{
            const form=new FormData(node.querySelector('form'));const answer=q.type==='single'?Number(form.get('answer')):q.type==='multiple'?form.getAll('answer').map(Number):q.type==='boolean'?form.get('answer')==='0':q.type==='fill'?form.getAll('answer'):draft;
            const request={questionId:q.id,questionRevision:q.revision,answer,operationId:crypto.randomUUID()};
            const key=draftKey(id)+':pending';let saved;try{saved=JSON.parse(sessionStorage.getItem(key));}catch{}
            if(saved&&JSON.stringify(saved.answer)===JSON.stringify(answer))request.operationId=saved.operationId;
            try{sessionStorage.setItem(key,JSON.stringify(request));}catch{}
            attempt=(await api('quiz/attempts',request)).attempt;
            node.dataset.attemptId=attempt.id;
            if(node.dataset.chatMessage)root.dispatchEvent(new CustomEvent('xueya:quiz-attempt',{detail:{messageId:node.dataset.chatMessage,questionId:q.id,attemptId:attempt.id}}));
            try{sessionStorage.removeItem(key);sessionStorage.removeItem(draftKey(id));}catch{}draft='';draw();poll();
          });
          node.querySelector('[data-quiz-review]')?.addEventListener('click',action(async()=>{
            const reason=prompt('请说明希望复核的理由（复核保留原答案，不新增一次作答）：');if(!reason?.trim())return;
            attempt=(await api('quiz/attempts/'+attempt.id+'/review',{reason,expectedRevision:attempt.revision,operationId:crypto.randomUUID()})).attempt;draw();poll();
          }));
          node.querySelector('[data-quiz-correct]')?.addEventListener('click',action(async()=>{
            const reason=prompt('人工修正的理由或争议说明：');if(!reason?.trim())return;
            const value={reason,expectedRevision:attempt.revision,operationId:crypto.randomUUID()};
            const decision=prompt(q.type!=='short'?'输入“正确”“错误”或“争议”：':q.maxPoints?'输入修正参考分（0至'+q.maxPoints+'）或“争议”：':'没有评分标准，只能内容修正。输入“确认”或“争议”：');if(decision===null)return;
            if(decision==='争议')value.disputed=true;
            else if(q.type!=='short'){if(!['正确','错误'].includes(decision))throw Error('请输入正确、错误或争议');value.correct=decision==='正确';}
            else if(q.maxPoints)value.score=Number(decision);
            attempt=(await api('quiz/attempts/'+attempt.id+'/correct',value)).attempt;draw();
          }));
        }
        async function poll(){
          while(node.isConnected&&attempt?.evaluations.some(entry=>entry.status==='queued')){
            await new Promise(resolve=>setTimeout(resolve,400));if(!node.isConnected)return;
            attempt=(await api('quiz/attempts/'+attempt.id)).attempt;draw();
          }
        }
        draw();poll().catch(()=>{});
      }catch(error){if(node.isConnected)node.innerHTML='<p role="alert">'+e(error.message)+'</p>';}
    });
  }
  async function directory(node,questionId,attemptId){
    try{
      const previous=node.querySelector('[data-new-quiz]');
      const formState=previous?Object.fromEntries(new FormData(previous)):{subject:'操作系统：进程管理',type:'single'};
      const value=await api('quiz/list');if(!node.isConnected)return;
      node.innerHTML=`<section class="panel study-quiz-directory"><a href="#space/materials">← 返回课程资料学习</a><h2>我的小测与作答</h2><p>与聊天共用题目、原答案和评阅版本。资料自动生成题可从课程资料学习的知识点进入。</p>
        <form data-new-quiz><label>学科 / 专题<input name="subject" required maxlength="100" value="${e(formState.subject)}"></label><label>题型<select name="type"><option value="single" ${formState.type==='single'?'selected':''}>单选</option><option value="multiple" ${formState.type==='multiple'?'selected':''}>多选</option><option value="boolean" ${formState.type==='boolean'?'selected':''}>判断</option><option value="fill" ${formState.type==='fill'?'selected':''}>填空</option><option value="short" ${formState.type==='short'?'selected':''}>主观</option></select></label><button type="submit" class="button button-small button-blue">主动生成一题</button></form><p role="status" data-quiz-generation>${value.jobs.filter(job=>['queued','running','unknown','failed'].includes(job.status)).map(job=>'生成 / 评阅作业：'+e(job.status)).join('；')}</p>
        <nav>${value.questions.map(q=>`<p><a href="#space/practice/ai/${e(q.id)}">${e(q.subject)} · ${e(q.prompt.slice(0,80))}</a></p>`).join('')||'<p>还没有小测，可以在聊天主动请求，或使用上方生成。</p>'}</nav>${questionId?shell(questionId,attemptId):''}</section>`;
      node.querySelector('[data-new-quiz]').onsubmit=async event=>{
        event.preventDefault();const form=event.target;form.querySelector('button').disabled=true;
        try{
          const {job}=await api('quiz/jobs',{...Object.fromEntries(new FormData(form)),operationId:crypto.randomUUID()});
          const output=await generated(job.id);if(!node.isConnected)return;
          if(output.artifacts.quiz.questionIds)location.hash='space/practice/ai/'+output.artifacts.quiz.questionIds[0];
          else node.querySelector('[data-quiz-generation]').textContent=output.answer;
        }catch(error){if(node.isConnected)node.querySelector('[data-quiz-generation]').textContent=error.message;}
        finally{if(node.isConnected)form.querySelector('button').disabled=false;}
      };mount(node);
      if(value.jobs.some(job=>job.type==='space-quiz-generate'&&['queued','running'].includes(job.status)))setTimeout(()=>{if(node.isConnected)directory(node,questionId,attemptId);},600);
    }catch(error){if(node.isConnected)node.innerHTML='<p role="alert">'+e(error.message)+'</p>';}
  }
  function recover(state,persist,render){
    if(state.pending||!root.XueyaPlatform?.available)return;
    for(const message of state.messages){
      const ref=message.artifacts?.quiz;
      if(!ref?.jobId||ref.status!=='queued'||restoring.has(ref.jobId))continue;restoring.add(ref.jobId);
      generated(ref.jobId).then(value=>{
        const apply=target=>Object.assign(target,{text:value.answer,engine:value.engine,failed:value.answerStatus==='unavailable',artifacts:value.artifacts});
        state.messages.filter(m=>m.id===message.id).forEach(apply);
        for(const session of state.sessions)session.messages.filter(m=>m.id===message.id).forEach(apply);
        persist();render();
      }).catch(()=>{}).finally(()=>restoring.delete(ref.jobId));
    }
  }
  function reviewRows(value,bank=[]){
    const fixed=new Map(bank.map(q=>[q.id,q])),seen=new Set(),rows=[];
    const areaOf=q=>{
      if(q.sourceType==='ai-material')return 'materials';
      const original=fixed.get(q.originalQuestionId||q.id);
      if(original)return original.bankSource==='exam408'?'exams':original.bankSource==='algorithm'?'algorithms':original.bankSource?'materials':original.category==='exam408'?'exams':original.category==='hot100'?'algorithms':'materials';
      return 'unclassified';
    };
    for(const attempt of [...value.attempts].sort((a,b)=>(b.createdAt||'').localeCompare(a.createdAt||''))){
      if(seen.has(attempt.questionId))continue;seen.add(attempt.questionId);
      const assessment=attempt.effectiveEvaluation,result=assessment?.result;
      if(assessment?.status!=='graded'||!result)continue;
      const objective=['objective','objective-recheck','human'].includes(assessment.source)&&result.correct===false;
      const reference=['ai-reference','ai-review','human'].includes(assessment.source)&&Number.isFinite(result.score)&&Number.isFinite(result.maxScore)&&result.maxScore>0&&result.score<result.maxScore;
      if(!objective&&!reference)continue;
      const question=value.questions.find(q=>q.id===attempt.questionId);if(!question)continue;
      rows.push({question,attempt,area:areaOf(question),objective});
    }
    return rows;
  }
  async function review(node,{area='materials',bank=[]}={}){
    node.innerHTML='<p role="status">正在读取此类作答与订正记录…</p>';
    try{
      const value=await api('quiz/list');if(!node.isConnected)return;
      const all=reviewRows(value,bank),rows=all.filter(r=>r.area===area),other=all.filter(r=>r.area==='unclassified');
      const items=list=>list.map(({question:q,attempt:a,objective})=>`<article class="wrong-quiz-row"><strong>${e(q.subject)}</strong><p>${e(q.prompt.slice(0,180))}</p><small>${objective?'客观判错 / 人工修正':'参考评阅建议巩固，不等同客观判错'} · ${e(a.createdAt)}</small><button type="button" class="button button-outline" data-wrong-quiz="${e(q.id)}" data-attempt="${e(a.id)}">查看原作答并重练</button></article>`).join('');
      node.innerHTML=`<div class="wrong-quiz-heading"><h2>${({materials:'资料题与课程小测',algorithms:'算法参考评阅',exams:'考试作答与参考评阅'})[area]}</h2><button type="button" class="button button-outline" data-wrong-refresh>刷新错题</button></div><p>按每题最近一次作答的最新有效评阅归集；失败、待复核和争议不算错。重新答对后刷新即可从本列表移出。</p><div class="wrong-quiz-list">${items(rows)||'<p class="wrong-empty">此分类暂时没有待复习的已评阅题目。</p>'}</div>
        ${area==='materials'&&other.length?`<details class="wrong-unclassified"><summary>未关联学习模块的历史小测（${other.length}题，保留原记录）</summary>${items(other)}</details>`:''}<div data-wrong-detail></div>`;
      node.querySelector('[data-wrong-refresh]').onclick=()=>review(node,{area,bank});
      node.querySelectorAll('[data-wrong-quiz]').forEach(button=>button.onclick=()=>{
        const box=node.querySelector('[data-wrong-detail]');box.innerHTML=`<button type="button" class="button button-outline" data-wrong-close>收起作答</button>${shell(button.dataset.wrongQuiz,button.dataset.attempt)}`;
        box.querySelector('[data-wrong-close]').onclick=()=>{box.innerHTML='';button.focus();};mount(box);box.scrollIntoView({block:'start',behavior:'smooth'});
      });
    }catch(error){if(node.isConnected)node.textContent='错题记录暂未读取：'+error.message;}
  }
  root.XueyaStudyQuiz={tryChat,markup,mount,directory,recover,review,reviewRows};
})(window);
