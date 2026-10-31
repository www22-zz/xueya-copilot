/* AI analysis UI: account-scoped server reports; model text is always escaped. */
(function(root){
  'use strict';
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const categoryNames={all:'全部题库',hot100:'力扣算法 Hot100',exam408:'408 考研题库',legacy:'历史练习',basic:'旧基础题',interview:'旧面试题'};
  const kindNames={weakness:'优先巩固',progress:'正在进步',pattern:'练习观察',coverage:'尚待探索'};
  const active=job=>job&&['queued','running','cancelling'].includes(job.status);
  const date=value=>new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
  const range=filters=>`${filters.days?'最近 '+filters.days+' 天':'全部历史'} · ${categoryNames[filters.category]}`;
  const errors={AI_UNAVAILABLE:'AI 暂不可用，请检查服务设置后再试。',AUTH_REQUIRED:'请重新登录原账号后查看分析。',LOGIN_REQUIRED:'登录已过期，请重新登录。',
    ANALYSIS_BUSY:'已有分析或追问正在进行，请等待完成。',ANALYSIS_NO_RECORDS:'这个范围还没有练习记录。先完成几道题，或扩大分析范围。',
    ANALYSIS_INVALID_RESPONSE:'AI 返回的报告不完整，本次没有保存报告。',ANALYSIS_INVALID_REFERENCE:'AI 引用了范围以外的题目，本次没有保存报告。',
    AI_TRUNCATED:'AI 回复未完整生成，本次没有保存报告。',JOB_TIMEOUT:'AI 服务未在规定时间内完成，请核对调用结果。',AI_RUN_TIMEOUT:'本次分析超过运行时限，请核对调用结果。',AI_COST_BUDGET_EXCEEDED:'本次分析超出已设置的调用预算。',AI_PRICING_REQUIRED:'服务尚未配置预算所需的模型价格。'};

  function create({client,store,navigate,accountId='local'}={}){
    let node=null,timer=null,reports=[],report=null,job=null,available=true,loading=false,submitting=false,message='',draft='',selection={days:7,category:'all',includeNotes:true},activeTab='report',planUI=null,frameworkUI=null;
    let generation=0,pending=null;
    let sourceSessions=[],scheduleSettings=null,candidates=[];
    async function spaceAPI(path,data){if(path==='/sources')return client.analysisSources();if(path==='/schedule')return client.updateAnalysisSchedule(data);const match=path.match(/^\/candidates\/([^/]+)\/submit$/);if(match)return client.submitAnalysisCandidate(match[1]);throw new Error('INVALID_ANALYSIS_ENDPOINT');}
    function sourceControls(){
      return `<details class="panel"><summary>对话和其他学习依据</summary><p>默认纳入可识别的学习对话。以下范围会发送至已配置的外部 AI；可排除任一会话。</p>${[['Conversations','学习对话'],['Courses','课程手动确认'],['Quizzes','聊天小测'],['Plans','计划与复习操作']].map(([key,label])=>`<label><input type="checkbox" data-analysis-filter="include${key}" ${selection['include'+key]!==false?'checked':''}>${label}</label>`).join('')}${sourceSessions.map(s=>`<label><input type="checkbox" data-analysis-session="${escape(s.id)}" ${(selection.excludedSessionIds||[]).includes(s.id)?'':s.learningRelated||(selection.includedSessionIds||[]).includes(s.id)?'checked':''}>${escape(s.title)}${s.learningRelated?'':'（未自动识别为学习，可手动纳入）'}</label>`).join('')}</details>`;
    }
    function scheduleControls(){
      if(!scheduleSettings)return '';
      return `<details class="panel"><summary>周期回顾设置</summary><p>本机服务运行时默认每周准备快照。启用自动 AI 分析会将所选学习记录发送给已配置的外部服务并产生费用；可随时关闭，未知结果不自动重试。</p><label><input data-schedule-enabled type="checkbox" ${scheduleSettings.enabled?'checked':''}>定期准备快照</label><label><input data-schedule-external type="checkbox" ${scheduleSettings.automaticExternalDispatch?'checked':''}>自动调用外部 AI 生成周报（付费）</label><label>周期（天）<input data-schedule-period type="number" min="1" max="90" value="${scheduleSettings.periodDays}"></label><label>每周星期<input data-schedule-weekday type="number" min="1" max="7" value="${scheduleSettings.weekday}"></label><label>时间<input data-schedule-time type="time" value="${scheduleSettings.time}"></label><p>时区 ${escape(scheduleSettings.timezone)} · 下次 ${escape(date(scheduleSettings.nextDueAt))}</p>${button('保存设置与当前分析范围','schedule-save')}<p>${escape(scheduleSettings.lastOutcome?.status||'尚未到期')}</p>${candidates.filter(c=>c.status==='awaiting-manual-analysis').map(c=>`<p>待分析快照：${escape(date(c.snapshot.cutoff))}${button('生成这份快照的 AI 分析（外部调用）','candidate-submit',`data-id="${escape(c.id)}" ${busy()?'disabled':''}`)}</p>`).join('')}</details>`;
    }
    function sourceHTML(snapshot){
      const sources=snapshot.activitySources;if(!sources)return '';
      const c=sources.counts;
      return `<section class="panel"><h3>多来源事实</h3><p>学习对话 ${c.conversations} 份 / 用户提问 ${c.userQuestions} 条；课程完成确认 ${c.courseConfirmations} 次 / 撤销 ${c.courseUndone} 次；计划操作 ${c.planOperations} 次。关联操作分列，不相加为学习次数。</p><p>小测原始作答 ${c.quizAttempts} 次：客观判分 ${c.objective} 次（正确 ${c.objectiveCorrect} 次），AI 参考评阅 ${c.aiReference} 次，人工修正 ${c.humanCorrection} 次，待评阅/未确定 ${c.ungraded} 次，争议 ${c.disputed} 次。复核不增加作答次数。</p>${snapshot.scheduleWindow?`<p>周期补报范围 ${escape(date(snapshot.scheduleWindow.from))} — ${escape(date(snapshot.scheduleWindow.through))}；快照包含此前累计背景。</p>`:''}<details><summary>核对本次依据${sources.truncated?'（有明确截取）':''}</summary>${sources.evidence.map(row=>`<article><strong>${escape(row.title)}</strong><small>${escape(row.type)} · ${escape(row.at?date(row.at):row.id)}</small>${row.url?`<a href="${escape(row.url)}">打开同一作答</a>`:''}${row.excerpts?row.excerpts.map(m=>`<p>${escape(m.text)}</p>`).join(''):''}${row.answerExcerpt?`<p>原答案：${escape(row.answerExcerpt)}</p>`:''}${row.evaluation?.result?.feedback?`<p>评阅：${escape(row.evaluation.result.feedback)}</p>`:''}<p>${escape(row.courseId||row.planId||row.sessionId||'')} ${escape(row.episodeId||row.action||'')}</p></article>`).join('')}</details></section>`;
    }
    const pendingKey='xueya-analysis-submission:'+accountId;
    try{pending=JSON.parse(sessionStorage.getItem(pendingKey)||'null');}catch{}
    function remember(value){pending=value;try{if(value)sessionStorage.setItem(pendingKey,JSON.stringify(value));else sessionStorage.removeItem(pendingKey);}catch{}}
    const errorText=error=>errors[error.code||error.message]||'连接暂时中断。恢复连接后可重新加载，已提交的任务会继续保留。';
    const button=(text,action,attributes='',primary=false)=>`<button type="button" class="button button-small ${primary?'button-blue':'button-outline'}" data-analysis-action="${action}" ${attributes}>${text}</button>`;
    const busy=()=>loading||submitting||active(job);
    function questionButtons(ids,snapshot){
      return `<div class="analysis-question-links">${ids.map(id=>{
        const q=snapshot.questions.find(item=>item.id===id);
        return q?button(escape(q.title),'practice',`data-id="${escape(id)}"`):'';
      }).join('')}</div>`;
    }
    function reportHTML(){
      if(!report)return `<section class="analysis-empty"><span class="analysis-kicker">从练习记录，看见下一步</span><h2>哪里需要再练一次？</h2><p>AI 会结合你的实际作答与自评，分析薄弱点、进步和接下来的练习重点。</p><p>选择时间和题库，开始第一份分析。完成几道练习后，建议会更具体。</p><a class="button button-outline button-small" href="#space/practice">先去练习</a></section>`;
      const {analysis:a,snapshot:s}=report,stats=s.stats;
      const accuracy=stats.attempts?Math.round(stats.correct/stats.attempts*100)+'%':'暂无作答';
      const statItems=[['客观题作答',stats.attempts+' 次'],['客观题正确率',accuracy],['练习覆盖',stats.practicedQuestions+' / '+stats.bankQuestions+' 题'],['自评操作',stats.selfAssessments+' 次']];
      return `<article class="analysis-report"><header><span class="analysis-kicker">${escape(range(report.filters))}</span><h2>${escape(a.title)}</h2><p class="analysis-meta">记录截至 ${escape(date(report.cutoff))} · ${escape(report.model)}</p>${store.state.serverSeq>report.serverSeq?'<p class="analysis-updated">已有新的练习记录；这份报告保留生成时的分析，你可以重新生成。</p>':''}</header>
        <dl class="analysis-stats">${statItems.map(([label,value])=>`<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')}</dl>
        <p class="analysis-summary">${escape(a.summary)}</p>
        <section class="analysis-findings" aria-label="分析发现">${a.findings.map(f=>`<section class="analysis-finding"><span class="analysis-tag">${kindNames[f.kind]}</span><h3>${escape(f.title)}</h3><p>${escape(f.detail)}</p>${questionButtons(f.questionIds,s)}</section>`).join('')}</section>
        <section class="analysis-next"><h3>接下来，练得更有方向</h3>${a.recommendations.map((item,i)=>`<section class="analysis-recommendation"><span class="analysis-step">${i+1}</span><div><h4>${escape(item.title)}</h4><p>${escape(item.reason)}</p>${questionButtons(item.questionIds,s)}</div></section>`).join('')}</section>
        <details class="analysis-limits"><summary>本次分析的依据与限制</summary><p>所选范围内答对 ${stats.correct} 次，共作答 ${stats.attempts} 次。当前错题 ${stats.currentWrong} 道，自评已掌握 ${stats.selfReportedMastered} 道。</p>${s.previousPeriod?`<p>前一等长时间段：作答 ${s.previousPeriod.attempts} 次，答对 ${s.previousPeriod.correct} 次。题目和难度可能不同。</p>`:''}<ul>${[...a.limitations,...s.limitations].map(line=>`<li>${escape(line)}</li>`).join('')}</ul></details>
        ${sourceHTML(s)}<section class="analysis-conversation"><h3>继续问问这份分析</h3><p class="analysis-meta">追问使用这份报告截止时的记录；每次发送调用一次 AI。</p><div class="analysis-messages">${report.conversation.map(row=>`<div class="analysis-message ${row.role==='user'?'from-user':''}"><strong>${row.role==='user'?'你':'AI'}</strong><p>${escape(row.content)}</p></div>`).join('')}</div><form data-analysis-chat><label for="analysisQuestion">你的问题</label><textarea id="analysisQuestion" name="question" rows="3" maxlength="1000" placeholder="例如：为什么建议我先巩固这个知识点？" ${busy()?'disabled':''}>${escape(draft)}</textarea><button class="button button-blue button-small" ${busy()||!available?'disabled':''}>发送追问</button></form></section></article>`;
    }
    function render(){
      if(!node?.isConnected)return;
      const working=busy();
      const tabsBar = `<div class="analysis-tabs-bar" role="tablist" style="display:flex;gap:12px;margin-bottom:16px;">
        <button type="button" class="button button-small ${activeTab==='report'?'button-blue':'button-outline'}" data-tab-switch="report">AI 学习分析报告</button>
        <button type="button" class="button button-small ${activeTab==='plan'?'button-blue':'button-outline'}" data-tab-switch="plan">我的学习计划</button>
      </div>`;
      if(activeTab==='plan'){
        if(node.querySelector('#planSubmodule'))return;
        node.innerHTML = tabsBar + '<div id="planSubmodule"></div>';
        if(!planUI && window.XueyaPlan) planUI = window.XueyaPlan.create({toast:window.toast, navigate});
        planUI?.mount(node.querySelector('#planSubmodule'));
        return;
      }
      if(activeTab==='framework'){
        node.innerHTML = tabsBar + '<div id="frameworkSubmodule"></div>';
        if(!frameworkUI && window.XueyaFramework) frameworkUI = window.XueyaFramework.create({toast:window.toast, navigate});
        frameworkUI?.mount(node.querySelector('#frameworkSubmodule'));
        return;
      }
      node.innerHTML = tabsBar + `<div class="analysis-layout"><aside class="analysis-sidebar"><section class="panel analysis-controls"><span class="analysis-kicker">按自己的节奏回顾</span><h2>分析范围</h2><label>时间<select data-analysis-filter="days" ${working?'disabled':''}>${[[7,'最近 7 天'],[30,'最近 30 天'],[0,'全部历史']].map(([v,t])=>`<option value="${v}" ${selection.days===v?'selected':''}>${t}</option>`).join('')}</select></label><label>题库<select data-analysis-filter="category" ${working?'disabled':''}>${Object.entries(categoryNames).map(([v,t])=>`<option value="${v}" ${selection.category===v?'selected':''}>${t}</option>`).join('')}</select></label><label class="analysis-note-choice"><input type="checkbox" data-analysis-filter="includeNotes" ${selection.includeNotes?'checked':''} ${working?'disabled':''}>结合题目随手记</label><p class="analysis-meta">选定范围的题目信息、练习记录${selection.includeNotes?'和已保存的随手记摘录':''}将发送给已配置的 AI 服务。</p>${button(submitting?'正在提交…':active(job)?'正在分析…':'开始分析','generate',working||!available?'disabled':'',true)}${!available?'<p class="analysis-warning">AI 服务尚未配置；配置完成后重新加载即可开始。</p>':''}</section>
        <section class="analysis-history"><h3>历史报告</h3>${reports.length?reports.map(item=>`<button type="button" class="analysis-history-item ${item.id===report?.id?'selected':''}" data-analysis-action="history" data-id="${escape(item.id)}"><strong>${escape(item.title)}</strong><span>${escape(range(item.filters))}</span><small>${escape(date(item.createdAt))}</small></button>`).join(''):'<p class="analysis-meta">生成后自动保存，随时回来查看。</p>'}${button('重新加载','reload',loading?'disabled':'')}</section></aside>
        <div class="analysis-main"><div class="analysis-status" role="status" aria-live="polite">${loading?'正在读取分析记录…':active(job)?escape(job.progress?.label||'任务已提交，AI 正在准备分析；离开页面后仍会继续。'):''}</div>${message?`<p class="analysis-warning" role="alert">${escape(message)}</p>`:''}${pending&&!active(job)?`<div class="analysis-warning"><p>上一次提交尚未收到明确回执。可以核对原任务，不会重复提交新的调用。</p>${button('核对原任务','recover',submitting?'disabled':'')}</div>`:''}${reportHTML()}</div></div>`;
      node.querySelector('.analysis-sidebar')?.insertAdjacentHTML('beforeend',sourceControls()+scheduleControls());
    }
    async function openReport(id){
      const version=generation;
      const result=await client.analysisReport(id);
      if(version!==generation)return;
      report=result.report;selection={...report.filters};draft='';render();
    }
    function schedule(){clearTimeout(timer);if(node?.isConnected&&active(job))timer=setTimeout(poll,1500);}
    async function poll(){
      if(!node?.isConnected||!active(job))return;
      const version=generation;
      try{
        const result=await client.analysisJob(job.id);
        if(version!==generation)return;
        job=result.job;
        if(job.status==='succeeded'){
          await openReport(job.result.reportId);
          const list=await client.analysisList();if(version!==generation)return;reports=list.reports;message='';
        }else if(!active(job))message=errorText({code:job.error})+(job.status==='unknown'?' 本次调用结果不明，系统不会自动重试；如需再次分析，请核对后手动开始。':'');
        render();
      }catch(error){if(version===generation){message=errorText(error);render();}}
      finally{if(version===generation)schedule();}
    }
    async function load(){
      const version=generation;loading=true;message='';render();
      try{
        const result=await client.analysisList();if(version!==generation)return;
        const extra=await spaceAPI('/sources');if(version!==generation)return;
        sourceSessions=extra.sessions;scheduleSettings=extra.settings;candidates=extra.candidates;
        reports=result.reports;available=result.available;
        job=result.jobs.find(active)||result.jobs[0]||null;
        if(reports.length)await openReport(reports.some(item=>item.id===report?.id)?report.id:reports[0].id);
        if(job?.status==='unknown')message=errorText({code:job.error})+' 本次调用结果不明，系统不会自动重试。';
      }catch(error){if(version===generation)message=errorText(error);}
      finally{if(version===generation){loading=false;render();schedule();}}
    }
    async function submit(recover=false,chat=false){
      if(busy()||!available)return;
      if(pending&&!recover){message='请先核对上一次提交的任务，再开始新的分析。';render();return;}
      if(chat&&!draft.trim())return;
      const proposed=chat?{chat:true,reportId:report.id,message:draft.trim(),idempotencyKey:crypto.randomUUID()}:{...selection,idempotencyKey:crypto.randomUUID()};
      const version=generation;submitting=true;message='';render();
      let request=pending;
      try{
        if(!recover){
          await store.ready;await store.flush(client);
          const state=await client.refreshState();store.applyServer(state);
          if(version!==generation)return;
          request=proposed;
          if(chat&&!request.message)return;
          remember(request);
        }
        if(!request)return;
        const result=request.chat?await client.askAnalysis(request.reportId,request):await client.createAnalysis(request);
        remember(null);
        if(version!==generation)return;
        job=result.job;
        if(request.chat)draft='';
        if(job.status==='succeeded')await openReport(job.result.reportId);
        else if(!active(job))message=errorText({code:job.error})+' 本次任务已结束，不会自动再次调用。';
      }catch(error){
        // A structured rejection means no uncertain submission remains. Transport failures retain its key.
        if(error.code&&error.code!=='PRACTICE_RESPONSE_INVALID')remember(null);
        if(version===generation)message=errorText(error);
      }finally{if(version===generation){submitting=false;render();schedule();}}
    }
    function goPractice(id){
      const q=report?.snapshot.questions.find(item=>item.id===id);if(!q)return;
      const category=q.category==='exam408'?'exam408':q.category==='hot100'&&!/^(g-|ds-)/.test(q.id)?'hot100':'legacy';
      const f=store.state.filters[category];for(const key of Object.keys(f))f[key]='';
      f.status=store.state.statuses[id]?.status||'pending';
      store.state.ui.category=category;
      store.state.ui.positions[category]={selected:id,scroll:0,completed:false};store.persist();
      navigate('#space/practice/'+category);
    }
    return {
      unmount(){planUI?.unmount?.();frameworkUI?.unmount?.();generation++;clearTimeout(timer);node=null;loading=false;submitting=false;},
      mount(target){
        if(location.hash.split('/')[2]==='plans')activeTab='plan';
        node=target;render();
        node.onchange=event=>{const sid=event.target.dataset.analysisSession;if(sid){selection.excludedSessionIds=[...new Set([...(selection.excludedSessionIds||[]).filter(id=>id!==sid),...(!event.target.checked?[sid]:[])])];selection.includedSessionIds=[...new Set([...(selection.includedSessionIds||[]).filter(id=>id!==sid),...(event.target.checked?[sid]:[])])];render();return;}const key=event.target.dataset.analysisFilter;if(!key)return;selection[key]=key==='days'?Number(event.target.value):key.startsWith('include')?event.target.checked:event.target.value;render();};
        node.oninput=event=>{if(event.target.id==='analysisQuestion')draft=event.target.value;};
        node.onsubmit=event=>{if(!event.target.matches('[data-analysis-chat]'))return;event.preventDefault();event.stopPropagation();submit(false,true);};
        node.onclick=event=>{const tab=event.target.closest('[data-tab-switch]');if(tab){event.preventDefault();activeTab=tab.dataset.tabSwitch;planUI?.unmount?.();frameworkUI?.unmount?.();render();return;}const el=event.target.closest('[data-analysis-action]');if(!el)return;event.preventDefault();event.stopPropagation();
          const action=el.dataset.analysisAction;
          if(action==='schedule-save'){
            const external=node.querySelector('[data-schedule-external]').checked;if(external&&!scheduleSettings.automaticExternalDispatch&&!confirm('授权本账号按周期发送所选对话、作答、课程和计划记录给外部 AI，并按现有模型预算计费？可随时关闭；本机停机后仅合并补一份。'))return;const value={automaticExternalDispatch:external,confirmedExternalDispatch:external,enabled:node.querySelector('[data-schedule-enabled]').checked,periodDays:Number(node.querySelector('[data-schedule-period]').value),weekday:Number(node.querySelector('[data-schedule-weekday]').value),time:node.querySelector('[data-schedule-time]').value,options:selection,expectedRevision:scheduleSettings.revision,operationId:'schedule-'+crypto.randomUUID()};
            spaceAPI('/schedule',value).then(data=>{scheduleSettings=data.settings;message=data.settings.automaticExternalDispatch?'已保存：按周期自动分析，使用已有调用预算与账本。':'已保存：仅准备本地候选，不会自动调用外部服务。';render();}).catch(error=>{message=error.message;render();});return;
          }
          if(action==='candidate-submit'){
            if(busy())return;submitting=true;render();
            spaceAPI('/candidates/'+el.dataset.id+'/submit',{confirmed:true}).then(data=>{job=data.job;if(job.status==='succeeded')return openReport(job.result.reportId);schedule();}).catch(error=>{message=errorText(error);}).finally(()=>{submitting=false;render();});return;
          }
          if(action==='generate')submit();else if(action==='recover')submit(true);else if(action==='reload')load();
          else if(action==='practice')goPractice(el.dataset.id);
          else if(action==='history')openReport(el.dataset.id).catch(error=>{message=errorText(error);render();});
        };
        load();
      }
    };
  }
  root.XueyaAnalysis={create};
})(typeof globalThis!=='undefined'?globalThis:this);
