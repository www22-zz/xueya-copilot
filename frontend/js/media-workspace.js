/* G5 media learning: existing platform, explicit paid work and real recall only. */
(() => {
  'use strict';
  window.XueyaMediaWorkspace = {create({state, toast}) {
    const e = window.XueyaRich.escape, uid = () => crypto.randomUUID();
    let course = '', data, dialog, referenceDialog, busy = false, epoch = 0, activeRun, editing, player, timer, recordingTimer, recorder, recordingStream, discard = false;
    const urls = new Set();
    const labels = {prepare:'录音分段',transcribe:'片段转写',video:'采样画面分析',synthesize:'复习音频',queued:'等待处理',running:'处理中',completed:'已完成',unknown:'结果不明，需核对',cancelled:'已取消',failed:'未发送或处理失败'};
    const errors = {PCM_WAV_REQUIRED:'请使用可解码的音频，浏览器会转换为 PCM WAV。',INVALID_PCM_WAV:'无法读取完整 PCM WAV；请检查文件或重新导出。',API_CONFIRMATION_REQUIRED:'请先确认外部 API 调用。',MEDIA_PROVIDER_NOT_CONFIGURED:'尚未配置对应语音/图像服务；原件和脚本仍可保存。',SCRIPT_REVIEW_REQUIRED:'请逐段核对脚本并勾选确认。',SCRIPT_EVIDENCE_REQUIRED:'讲解和答案必须保留原文出处。',STALE_SCRIPT_EVIDENCE:'原文已更新，请重新核对脚本出处。',STALE_SCRIPT_PARENT:'所用笔记或卡片已更新，请重新生成脚本。',ARTIFACT_CONFLICT:'记录已更新，请刷新后重新核对。',API_CALL_BUDGET_REQUIRED:'调用次数上限不足或无效。',UNKNOWN_OUTCOME_REQUIRES_REVIEW:'请先核对服务商记录，再明确恢复未完成片段。',CONFIGURATION_CHANGED_START_NEW:'服务配置已变化，请新建任务并核对。',NO_SOURCES:'请先选择有有效原文的资料。',NO_VERIFIED_NOTE_EVIDENCE:'这些笔记没有可核对的原文依据，请选择资料或有出处的笔记。',NO_DUE_REVIEW_CARDS:'今天没有可用的到期复习卡。'};
    const api = (path, body) => window.XueyaPlatform.learningRequest('media-workspace/'+path, {courseId:course, method:body===undefined?'GET':'POST', body});
    const button = (label, action, id='', extra='') => `<button type="button" class="button button-outline button-small" data-g5="${action}" data-id="${e(id)}" ${extra}>${e(label)}</button>`;
    const field = (label, name, value='', type='text') => `<label class="form-field">${e(label)}<input name="${name}" type="${type}" value="${e(value)}" ${type==='number'?'step="any"':''}></label>`;
    const area = (label, name, value='') => `<label class="form-field">${e(label)}<textarea name="${name}" rows="4" maxlength="20000">${e(value)}</textarea></label>`;
    const check = (name, label) => `<label class="c-choice"><input type="checkbox" name="${name}" required>${e(label)}</label>`;
    const form = (name, text, label) => `<form class="c-form" data-g5-form="${name}">${text}<button class="button button-primary">${e(label)}</button></form>`;
    function url(blob) {const value=URL.createObjectURL(blob);urls.add(value);return value;}
    function stop() {clearTimeout(timer);timer=null;player?.pause();if(player)player.onended=null;}
    function cleanup() {stop();for(const value of urls)URL.revokeObjectURL(value);urls.clear();}
    function availability() {for(const b of document.querySelectorAll('#g5Workspace button,#g5Dialog button')){const action=b.dataset.g5;if(action==='close'||action==='stop')b.disabled=false;else if(action==='record-stop')b.disabled=recorder?.state!=='recording';else b.disabled=busy;}dialog?.setAttribute('aria-busy',String(busy));}
    function modal(title, content) {
      if(!dialog){dialog=document.createElement('dialog');dialog.id='g5Dialog';dialog.className='source-dialog c-dialog';dialog.setAttribute('aria-label','录音与复习音频');document.body.append(dialog);dialog.addEventListener('close',cleanup);}
      stop();dialog.innerHTML=`<div class="dialog-head"><strong>${e(title)}</strong>${button('关闭','close')}</div><div class="c-dialog-body">${content}</div>`;
      availability();if(!dialog.open)dialog.showModal();
    }
    async function blob(path, {platform=false}={}) {
      const bootstrap=await fetch('/api/platform/bootstrap').then(r=>r.json());
      const route=platform?'/api/platform/':'/api/learning/media-workspace/';
      const response=await fetch(route+path+(path.includes('?')?'&':'?')+'courseId='+encodeURIComponent(course),{headers:{'X-Xueya-Token':bootstrap.token}});
      if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.error||'无法读取媒体，请刷新核对版本。');}
      return response.blob();
    }
    async function load() {const version=epoch,current=course;const value=await api('workspace');if(version!==epoch||current!==course)return;data=value;draw();}
    function draw() {
      const root=document.querySelector('#g5Workspace');if(!root)return;
      if(!data){root.innerHTML='<p role="status">正在读取录音与复习音频…</p>';return;}
      const options=data.documents.map(d=>`<option value="${e(d.id)}">${e(d.name)}</option>`).join('');
      root.innerHTML=`<span class="eyebrow">从课程资料到主动回忆</span><h2>录音与复习音频</h2><p>保存和分段不调用模型；识别和合成需要再次确认。听完不自动记为掌握。</p><p>转写：${data.capabilities.asr?'已配置':'未配置'} · 语音合成：${data.capabilities.tts?'已配置':'未配置'} · 画面分析：${data.capabilities.image?'已配置':'未配置'}。配置状态不代表真实效果已验收。</p>
        <details><summary>导入录音或录制一段</summary><p>可解码音频最多一小时、120MB；转换为单声道16k PCM WAV。较大文件可能受浏览器内存限制。</p>
        ${form('upload','<label class="form-field">音频文件<input name="file" type="file" accept="audio/*" required></label>'+field('每段秒数（30～180）','seconds','120','number'),'保存原件并免费分段')}
        ${button('开始录音（需要麦克风许可）','record')}${button('停止录音并保存分段','record-stop','','disabled')}<p id="g5Recording" role="status"></p></details>
        <details><summary>课程视频：选择范围与抽帧数量</summary><p>最多50MB、30分钟；只分析所选的1～24个实际画面，不代表理解整段视频。</p>
        ${form('video','<label class="form-field">视频文件<input name="file" type="file" accept="video/mp4,video/webm" required></label>'+field('范围开始（秒）','start','0','number')+field('范围结束（秒，留空到结尾）','end','','number')+field('抽帧数量（1～24）','count','6','number'),'保存原件与采样画面（不调用模型）')}</details>
        <details><summary>制作有出处的单人 / 双人复习脚本</summary>${form('script',field('标题','title','课程复习')+'<label class="form-field">格式<select name="style"><option value="solo">单人讲解</option><option value="dialogue">双人问答</option></select></label><label class="form-field">重点<select name="focus"><option value="selected">所选资料 / 笔记</option><option value="due">今日到期复习卡</option></select></label><label class="form-field">课程资料（多选；最多取六段，省略会提示）<select name="documents" multiple size="4">'+options+'</select></label><label class="form-field">有出处的笔记 / 产物（可选，多选）<select name="parents" multiple size="3">'+data.parents.map(p=>`<option value="${e(p.id)}">${e(p.kind+' · '+p.id)}</option>`).join('')+'</select></label><label class="form-field">关联实际复习卡（可选）<select name="cards" multiple size="3">'+(data.cards||[]).map(c=>`<option value="${e(c.id)}">${e(c.content.prompt||c.id)}</option>`).join('')+'</select></label>','免费生成可核对脚本')}</details>
        <h3>已保存的脚本</h3>${data.scripts.map(s=>`<article class="c-item"><strong>${e(s.content.title)}</strong><p>${s.content.style==='dialogue'?'双人问答':'单人讲解'} · v${s.revision}</p>${button('编辑并重新核对','script-edit',s.id)}${button('确认合成音频','synthesize',s.id)}</article>`).join('')||'<p>还没有脚本。</p>'}
        <h3>录音和视频原件</h3>${data.media.filter(m=>m.content.kind!=='image'&&!m.content.originalMediaId).map(m=>`<article class="c-item"><strong>${e(m.content.name)}</strong><p>${e(m.content.kind)} · ${m.content.durationMs?(m.content.durationMs/1000).toFixed(2)+'秒':'时长待解码'} · v${m.revision}</p>${button('打开原件','original',m.content.id)}${m.content.kind==='audio'?button('重新免费分段','prepare',m.content.processingMediaId?'media:'+m.content.processingMediaId:m.id,m.content.pendingConversion?'disabled':''):''}${m.content.frames?.length?button('确认分析采样画面','analyze',m.id):''}</article>`).join('')||'<p>还没有媒体原件。</p>'}
        <h3>处理进度和结果</h3>${data.runs.slice().reverse().map(r=>`<article class="c-item"><strong>${e(labels[r.content.mode])}</strong><p>${e(labels[r.content.status]||r.content.status)} · ${r.content.mode==='prepare'&&r.content.status==='completed'?r.content.items.length:r.content.items.filter(p=>p.done).length}/${r.content.items.length} 段 ${r.content.error?'· '+e(errors[r.content.error]||r.content.error):''}</p>${button('查看 / 核对 / 播放','run',r.id)}${['queued','running'].includes(r.content.status)?button('取消后台执行','cancel',r.id):''}${['unknown','cancelled','failed'].includes(r.content.status)&&r.content.mode!=='prepare'?button('核对后恢复未完成段','resume',r.id):''}${r.content.mode==='prepare'&&r.content.status==='completed'?button('确认分段转写','transcribe',r.id):''}</article>`).join('')||'<p>还没有后台处理。</p>'}`;
    }
    async function work(fn) {if(busy)return;busy=true;availability();const version=epoch;try{await fn();if(version===epoch)await load();}catch(error){if(version===epoch)toast(error.name==='NotAllowedError'?'浏览器限制了自动播放，请点击音频控件播放。':errors[error.code||error.message]||error.message||'操作未完成');}finally{busy=false;availability();if(recorder?.state==='recording'){const stop=document.querySelector('[data-g5=record-stop]');if(stop)stop.disabled=false;const status=document.querySelector('#g5Recording');if(status)status.textContent='正在录音，停止后保存分段。';}}}
    async function upload(file, seconds=120) {
      if(!file?.size)throw Error('没有可处理的音频数据，请重新录制或选择有效音频文件。');if(file.size>120*1024*1024)throw Error('音频文件须在120MB内。');
      const version=epoch;
      let wav=file,converted=false;
      if(file.type!=='audio/wav'&&!/\.wav$/i.test(file.name||'')) {
        const Audio=window.AudioContext||window.webkitAudioContext,context=new Audio();
        let decoded;try{decoded=await context.decodeAudioData(await file.arrayBuffer());}finally{await context.close();}
        if(decoded.duration>3600)throw Error('当前每个录音最多一小时，请分成课次。');
        const output=new OfflineAudioContext(1,Math.ceil(decoded.duration*16000),16000),source=output.createBufferSource();source.buffer=decoded;source.connect(output.destination);source.start();
        const samples=(await output.startRendering()).getChannelData(0),buffer=new ArrayBuffer(44+samples.length*2),view=new DataView(buffer);
        function word(at,text){for(let i=0;i<text.length;i++)view.setUint8(at+i,text.charCodeAt(i));}
        word(0,'RIFF');view.setUint32(4,buffer.byteLength-8,true);word(8,'WAVEfmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);word(36,'data');view.setUint32(40,samples.length*2,true);
        for(let i=0;i<samples.length;i++){const n=Math.max(-1,Math.min(1,samples[i]));view.setInt16(44+i*2,n<0?n*32768:n*32767,true);}wav=new Blob([buffer],{type:'audio/wav'});converted=true;
      }
      if(version!==epoch)throw Error('课程已切换，本次没有上传到其他课程。');
      let name=file.name||'课堂录音.wav',originalQuery='';if(converted){const original=await api('upload-original?name='+encodeURIComponent(name),new Blob([file],{type:file.type||'application/octet-stream'}));if(version!==epoch)throw Error('课程已切换，原件保留在原课程，未继续转换。');originalQuery='&originalId='+encodeURIComponent(original.content.id)+'&originalVersion='+original.revision;name=name.replace(/\.[^/.]+$/,'')+'.wav';}const media=await api('upload?name='+encodeURIComponent(name)+originalQuery,new Blob([wav],{type:'audio/wav'}));
      return api('prepare',{mediaId:media.content.id,mediaVersion:media.revision,seconds,confirmed:true,operationId:uid()});
    }
    async function waitJob(job) {for(let i=0;i<600;i++){const value=await fetchJob(job.id);if(['failed','cancelled','unknown'].includes(value.status))throw Error('资料处理未完成：'+value.status);if(value.status==='succeeded')return value;await new Promise(r=>setTimeout(r,150));}throw Error('已停止等待，后台结果请到任务中心核对。');}
    async function fetchJob(id) {const bootstrap=await fetch('/api/platform/bootstrap').then(r=>r.json());return fetch('/api/platform/jobs/status?id='+encodeURIComponent(id),{headers:{'X-Xueya-Token':bootstrap.token}}).then(r=>r.json()).then(v=>v.job);}
    async function videoUpload(file, start, end, count) {
      if(!file?.size||file.size>50*1024*1024||!Number.isInteger(count)||count<1||count>24)throw Error('视频最多50MB，抽帧数为1～24。');
      const version=epoch,video=document.createElement('video'),source=url(file);video.muted=true;video.preload='auto';
      const event=(name)=>new Promise((resolve,reject)=>{let timeout;const done=()=>{clearTimeout(timeout);video.removeEventListener(name,ok);video.removeEventListener('error',bad);};const ok=()=>{done();resolve();};const bad=()=>{done();reject(Error('浏览器无法读取这个视频。'));};video.addEventListener(name,ok,{once:true});video.addEventListener('error',bad,{once:true});timeout=setTimeout(bad,15000);});
      try {
        const ready=event('loadedmetadata');video.src=source;await ready;
        if(!Number.isFinite(video.duration)){const durationReady=event('seeked');video.currentTime=1e10;await durationReady;}if(!Number.isFinite(video.duration)||video.duration>1800)throw Error('视频最多30分钟，请按课次拆分。');
        end=end===''?video.duration:Number(end);if(!(0<=start&&start<end&&end<=video.duration))throw Error('请核对视频开始/结束时间。');
        const media=await window.XueyaPlatform.learningRequest('media/upload?'+new URLSearchParams({name:file.name,durationMs:Math.ceil(video.duration*1000)}),{courseId:course,method:'POST',body:file});
        const canvas=document.createElement('canvas');const scale=Math.min(1,1280/Math.max(video.videoWidth,video.videoHeight));canvas.width=Math.max(1,Math.round(video.videoWidth*scale));canvas.height=Math.max(1,Math.round(video.videoHeight*scale));const frames=[];
        for(let i=0;i<count;i++){if(version!==epoch)throw Error('课程已切换，抽帧已停止。');const time=start+(end-start)*(i+.5)/count;const seek=event('seeked');video.currentTime=time;await seek;canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);const image=await new Promise(r=>canvas.toBlob(r,'image/jpeg',.85));const item=await window.XueyaPlatform.learningRequest('media/upload?name='+encodeURIComponent(file.name+' frame '+i+'.jpg'),{courseId:course,method:'POST',body:image});frames.push({id:item.id,version:item.version,timeMs:video.currentTime*1000});}
        await api('video/register',{mediaId:media.id,mediaVersion:Number(media.version),frames,startMs:start*1000,endMs:end*1000,confirmed:true,operationId:uid()});toast('已保存实际采样画面；尚未调用模型。');
      } finally {video.removeAttribute('src');video.load();URL.revokeObjectURL(source);urls.delete(source);}
    }
    function editor(content, row) {
      editing={content:structuredClone(content),row};activeRun=null;
      modal('逐段核对复习脚本',`<p>这是原文模板，不是已验证的模型讲解。可改写，但须逐段核对事实与出处。省略 ${content.omittedSourceCount||0} 段原文；最多六段。</p>${form('script-save',field('标题','title',content.title)+content.segments.map((p,i)=>`<fieldset data-g5-part="${i}"><legend>${i+1}. ${e(p.kind)}</legend><label class="form-field">角色<select name="speaker"><option value="A" ${p.speaker==='A'?'selected':''}>讲解者 A</option><option value="B" ${p.speaker==='B'?'selected':''}>提问者 B</option></select></label>${p.kind==='pause'?field('回忆留白（秒）','pauseSeconds',p.pauseSeconds,'number'):area('讲解 / 提问 / 参考答案','text',p.text)}${p.evidence.map(r=>`<blockquote>${e(r.quote)}<small>${e(r.title||'课程资料')} · ${e(r.location||'原文片段')}</small>${button('读取当前原文核对','source',r.sourceId)}</blockquote>`).join('')}${check('reviewed','我已核对本段及其出处')}</fieldset>`).join('')+check('confirmed','确认保存这版脚本；本次不合成音频'),'保存已核对脚本')}`);
    }
    function confirmation(mode, target, resume=false) {
      const c=target.content;
      const items=resume?c.items:mode==='transcribe'?c.items:mode==='video'?c.frames:c.segments;
      const count=items.filter(p=>!p.done&&p.kind!=='pause').length;
      activeRun=resume?target:null;
      modal('核对外部服务调用',`<p>最多处理 ${count} 段/画面，每段一次请求。金额由供应商实际计费；没有可靠账单时不估价。${resume?'已有成功段会保留；未知段可能已收费，请先核对。':''}</p>${form('start',`<input type="hidden" name="mode" value="${mode}"><input type="hidden" name="id" value="${e(target.id)}"><input type="hidden" name="resume" value="${resume?'1':''}">${field('本次调用次数上限','maxCalls',count,'number')}${mode==='synthesize'?['A','B'].map(s=>`<label class="form-field">角色 ${s} 音色<select name="voice${s}">${data.voices.map(v=>`<option ${v===(s==='A'?'冰糖':'苏打')?'selected':''}>${e(v)}</option>`).join('')}</select></label>`).join(''):''}${resume?check('reviewedUnknown','我已核对服务商和已完成片段，明确恢复未完成部分'):''}${check('allowApi','同意将对应资料发送至已配置的外部 API，并接受本次费用')}`,'明确提交本次任务')}`);
    }
    async function showRun(row) {
      activeRun=row;editing=null;const c=row.content,completed=c.status==='completed';
      const partial=c.items.map((p,i)=>`<article class="c-item"><strong>${i+1}. ${e(p.kind||('timeMs'in p?'采样画面':'录音片段'))}</strong><p>${p.startMs!==undefined?(p.startMs/1000).toFixed(3)+'–'+(p.endMs/1000).toFixed(3)+'秒（片段精度）':p.timeMs!==undefined?(p.timeMs/1000).toFixed(3)+'秒的采样画面':'角色 '+e(p.speaker||'')}</p>${p.audioHash?button(c.mode==='synthesize'?'播放本段':'回放本段','play',String(i)):''}${c.mediaId?button('回到原件位置','seek',String(i)):''}${p.analysis?`<h4>画面观察（待核对）</h4><ul>${p.analysis.observations.map(t=>'<li>'+e(t)+'</li>').join('')}</ul><h4>不确定内容</h4><p>${e(p.analysis.uncertainties.join('；')||'服务未标出不确定项，仍需人工核对。')}</p><h4>推断（不能当作画面事实）</h4><p>${e(p.analysis.inferences.join('；')||'没有额外推断。')}</p>`:''}${['transcribe','video'].includes(c.mode)&&completed?`<fieldset data-g5-transcript="${e(p.id)}" data-time="${p.timeMs??''}">${area('核对并修正转写或画面说明','text',p.text)}${check('reviewed',c.mode==='video'?'我已查看原画面并核对说明':'我已听原片段并核对这段文字')}</fieldset>`:`<p>${e(p.kind==='pause'?'回忆留白 '+p.pauseSeconds+' 秒':p.text||'等待处理')}</p>`}</article>`).join('');
      const recalls=c.mode==='synthesize'?(data.cards||[]).filter(card=>data.scripts.find(s=>s.id===c.scriptId)?.content.cardIds?.includes(card.id)):[];
      modal(labels[c.mode]+' · '+(labels[c.status]||c.status),`${button('刷新进度与结果','run',row.id)}<p>仅片段对齐，不提供逐字时间。${c.coverage?'只覆盖 '+c.items.length+' 个采样画面，不代表整段视频。':''}</p><audio id="g5Player" controls preload="none"></audio><video id="g5VideoPlayer" controls preload="none" hidden style="max-width:100%"></video><p id="g5PlayStatus" role="status"></p>${c.mode==='synthesize'&&completed?button('按顺序播放（含回忆留白）','play-all')+button('停止播放 / 留白','stop')+button('下载音频、脚本与字幕','export',row.id):''}${['transcribe','video'].includes(c.mode)&&completed?form('transcript-save',partial+check('confirmed','确认保存逐段修订，原识别结果仍保留'),'保存已核对转写')+button('确认导入资料并关联原件片段','import',row.id):partial}${recalls.map(card=>`<article class="c-item"><h3>实际回忆：${e(card.content.prompt)}</h3><details><summary>回忆后核对答案</summary><p>${e(card.content.answer)}</p></details><p>以下是你明确提交的自评，会写入原 FSRS 复习记录：</p>${[1,2,3,4].map((rating,i)=>button(['没想起来','困难','想起来了','很轻松'][i],'rate',card.id,`data-rating="${rating}"`)).join('')}</article>`).join('')}<p>播放、结束或下载不会更新掌握度。<a href="#space/practice" data-g5="practice">进入题库实际作答</a></p>`);
      player=document.querySelector('#g5Player');
    }
    async function play(index, sequence=false) {
      stop();const row=activeRun,part=row?.content.items[index];if(!part)return;
      const marker=()=>{try{localStorage.setItem((window.XueyaDataKey||((key)=>key))('xueya-g5-position:'+course+':'+row.id),JSON.stringify({index,at:Date.now(),masteryUpdated:false}));}catch{}};marker();
      const status=document.querySelector('#g5PlayStatus');
      if(part.kind==='pause'){status.textContent='请闭卷回忆，留白 '+part.pauseSeconds+' 秒。';timer=setTimeout(()=>{if(sequence)void play(index+1,true).catch(err=>toast(err.message));},part.pauseSeconds*1000);return;}
      player.hidden=false;document.querySelector('#g5VideoPlayer').hidden=true;player.src=url(await blob('audio?'+new URLSearchParams({id:row.id,part:part.id})));status.textContent='第 '+(index+1)+' 段：'+(part.text||'原始录音片段');
      player.onended=()=>{if(sequence)void play(index+1,true).catch(err=>toast(err.message));else status.textContent='播放结束；尚未提交学习评分。';};await player.play();
    }
    async function seek(index) {
      stop();const c=activeRun.content,part=c.items[index];const processed=data.media.find(m=>m.content.id===c.mediaId),original=processed?.content.originalMediaId?data.media.find(m=>m.content.id===processed.content.originalMediaId):processed;const expected=processed?.content.originalMediaVersion??c.mediaVersion;if(!original||original.revision!==expected)throw Error('原件已变化，请刷新核对。');
      const audio=original.content.kind==='video'?document.querySelector('#g5VideoPlayer'):player;
      audio.hidden=false;audio.src=url(await blob('library/media-original?'+new URLSearchParams({id:original.content.id,version:expected}),{platform:true}));
      audio.onloadedmetadata=()=>{audio.currentTime=(part.startMs??part.timeMs??0)/1000;};audio.preload='metadata';audio.load();
      if(audio!==player)player.hidden=true;
    }
    document.addEventListener('click', event=>{
      const el=event.target.closest('[data-g5]');if(!el)return;event.preventDefault();const action=el.dataset.g5,id=el.dataset.id;
      if(action==='source-close'){referenceDialog.close();return;}if(action==='close'){dialog.close();return;}if(action==='record-stop'){if(recorder?.state==='recording')recorder.stop();return;}if(action==='stop'){stop();return;}if(action==='practice'){dialog.close();location.hash='space/practice';return;}
      void work(async()=>{
        if(action==='source'){const value=await window.XueyaPlatform.learningRequest('search/read?'+new URLSearchParams({kind:'source',id}),{courseId:course});const source=value.source;if(!referenceDialog){referenceDialog=document.createElement('dialog');referenceDialog.id='g5SourceDialog';referenceDialog.className='source-dialog c-dialog';document.body.append(referenceDialog);}referenceDialog.innerHTML=`<div class="dialog-head"><strong>${e(source.title||'课程原文')}</strong>${button('关闭原文','source-close')}</div><div class="c-dialog-body"><p>${e(source.location||'原文片段')}</p><blockquote>${e(source.quote)}</blockquote><p>这是当前课程服务端重新读取的原文；若内容已变化，请重新核对脚本。</p></div>`;referenceDialog.showModal();}if(action==='run')await showRun(await api('result?id='+encodeURIComponent(id)));
        if(action==='script-edit'){const row=data.scripts.find(s=>s.id===id);editor(row.content,row);}
        if(action==='synthesize')confirmation('synthesize',data.scripts.find(s=>s.id===id));
        if(action==='prepare'){const media=data.media.find(m=>m.id===id);await api('prepare',{mediaId:media.content.id,mediaVersion:media.revision,seconds:120,confirmed:true,operationId:uid()});}if(action==='transcribe')confirmation('transcribe',data.runs.find(s=>s.id===id));
        if(action==='analyze')confirmation('video',data.media.find(s=>s.id===id));
        if(action==='resume'){const row=data.runs.find(s=>s.id===id);confirmation(row.content.mode,row,true);}
        if(action==='cancel')await api('cancel',{id});
        if(action==='play')await play(Number(id));
        if(action==='play-all'){const previous=JSON.parse(localStorage.getItem((window.XueyaDataKey||((key)=>key))('xueya-g5-position:'+course+':'+activeRun.id))||'{}');await play(Number.isInteger(previous.index)?previous.index:0,true);}
        if(action==='seek')await seek(Number(id));
        if(action==='export'){const file=await blob('export?id='+encodeURIComponent(id)),a=document.createElement('a');a.href=url(file);a.download='学涯复习音频.zip';a.click();}
        if(action==='import'){const row=await api('result?id='+encodeURIComponent(id));if(!row.content.items.every(p=>p.reviewed))throw Error('请先逐段核对并保存转写。');const result=await api('transcript/import',{id,revision:row.revision,confirmed:true,operationId:uid()});await waitJob(result.job);await api('transcript/link',{id,revision:row.revision,documentId:result.documentId,confirmed:true});toast('转写已导入资料，并关联到真实原件片段。');}
        if(action==='original'){const m=data.media.find(m=>m.content.id===id);modal(m.content.name,`<${m.content.kind==='video'?'video':'audio'} id="g5Original" controls style="max-width:100%"></${m.content.kind==='video'?'video':'audio'}>`);document.querySelector('#g5Original').src=url(await blob('library/media-original?'+new URLSearchParams({id,version:m.revision}),{platform:true}));}
        if(action==='rate'){const card=data.cards.find(c=>c.id===id);await window.XueyaPlatform.learningRequest('reviews/rate',{courseId:course,method:'POST',body:{id,expectedRevision:card.revision,operationId:uid(),rating:Number(el.dataset.rating)}});toast('已记录你明确提交的自评与复习调度。');}
        if(action==='record'){if(recorder?.state==='recording')throw Error('正在录音，请先停止。');if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw Error('此浏览器无法录音，请上传音频文件。');const requestedEpoch=epoch;recordingStream=await navigator.mediaDevices.getUserMedia({audio:true});if(requestedEpoch!==epoch){recordingStream.getTracks().forEach(t=>t.stop());throw Error('课程已切换，本次没有开始录音。');}const parts=[],recordingEpoch=epoch,ownStream=recordingStream;let size=0;discard=false;recorder=new MediaRecorder(recordingStream);recorder.ondataavailable=event=>{parts.push(event.data);size+=event.data.size;if(size>80*1024*1024)recorder.stop();};recorder.onstop=async event=>{clearTimeout(recordingTimer);ownStream.getTracks().forEach(t=>t.stop());document.querySelector('[data-g5=record-stop]')?.setAttribute('disabled','');while(busy)await new Promise(r=>setTimeout(r,30));if(!discard&&recordingEpoch===epoch)void work(async()=>{const file=new File(parts,'课堂录音.webm',{type:event.target.mimeType});await upload(file);toast('录音已保存，正在免费分段。');});};recorder.start(1000);recordingTimer=setTimeout(()=>recorder.state==='recording'&&recorder.stop(),3600000);document.querySelector('[data-g5=record-stop]').disabled=false;document.querySelector('#g5Recording').textContent='正在录音；停止后仅保存和分段，不进行付费识别。';}
        if(action==='record-stop'&&recorder?.state==='recording')recorder.stop();
      });
    });
    document.addEventListener('submit',event=>{
      const f=event.target;if(!f.matches('[data-g5-form]'))return;event.preventDefault();const values=new FormData(f);
      void work(async()=>{
        if(f.dataset.g5Form==='upload'){await upload(values.get('file'),Number(values.get('seconds')));toast('原件已保存，分段进度见下方。');}
        if(f.dataset.g5Form==='video')await videoUpload(values.get('file'),Number(values.get('start')),values.get('end'),Number(values.get('count')));
        if(f.dataset.g5Form==='script'){const documentIds=values.getAll('documents'),parentIds=values.getAll('parents');const result=await api('script/draft',{title:values.get('title'),style:values.get('style'),focus:values.get('focus'),...(documentIds.length?{selection:{documentIds}}:{}),parentIds,cardIds:values.getAll('cards')});editor(result.content);}
        if(f.dataset.g5Form==='script-save'){const c=structuredClone(editing.content);c.title=values.get('title');for(const fieldset of f.querySelectorAll('[data-g5-part]')){const p=c.segments[Number(fieldset.dataset.g5Part)];p.speaker=fieldset.querySelector('[name=speaker]').value;p.reviewed=fieldset.querySelector('[name=reviewed]').checked;if(p.kind==='pause')p.pauseSeconds=Number(fieldset.querySelector('[name=pauseSeconds]').value);else p.text=fieldset.querySelector('[name=text]').value;}await api('script/save',{id:editing.row?.id||'review-script-'+uid(),expectedRevision:editing.row?.revision||0,content:c,confirmed:values.has('confirmed'),operationId:uid()});dialog.close();toast('脚本已保存；合成需要另行确认。');}
        if(f.dataset.g5Form==='transcript-save'){const row=activeRun;const items=[...f.querySelectorAll('[data-g5-transcript]')].map(el=>({id:el.dataset.g5Transcript,...(el.dataset.time!==''?{timeMs:Number(el.dataset.time)}:{}),text:el.querySelector('[name=text]').value,reviewed:el.querySelector('[name=reviewed]').checked}));await api(row.content.mode==='video'?'video/save':'transcript/save',{id:row.id,revision:row.revision,items,confirmed:values.has('confirmed'),operationId:uid()});await showRun(await api('result?id='+encodeURIComponent(row.id)));toast('逐段修订已保存，原识别文本保留。');}
        if(f.dataset.g5Form==='start'){const mode=values.get('mode'),id=values.get('id'),resume=values.get('resume');let request={confirmed:true,allowApi:values.has('allowApi'),maxCalls:Number(values.get('maxCalls')),operationId:uid()};if(resume)request={...request,resumeId:id,reviewedUnknown:values.has('reviewedUnknown')};else if(mode==='synthesize'){const script=data.scripts.find(s=>s.id===id);request={...request,scriptId:id,scriptRevision:script.revision,voices:{A:values.get('voiceA'),B:values.get('voiceB')}};}else if(mode==='transcribe'){const run=data.runs.find(r=>r.id===id);request={...request,preparedId:id,mediaId:run.content.mediaId,mediaVersion:run.content.mediaVersion};}else{const media=data.media.find(m=>m.id===id);request={...request,mediaId:media.content.id,mediaVersion:media.revision};}const result=await api(mode,request);dialog.close();await showRun(result);}
      });
    });
    setInterval(()=>{if(!busy&&data?.runs.some(r=>['queued','running'].includes(r.content.status)))void load().catch(()=>{});},1200);
    return {mount(){if(course!==state.courseId){epoch++;discard=true;if(recorder?.state==='recording')recorder.stop();recordingStream?.getTracks().forEach(t=>t.stop());cleanup();dialog?.close();referenceDialog?.close();data=null;course=state.courseId;}
      const advanced=document.querySelector('#g3Workspace')?.closest('.notes-advanced');
      if(state.view==='chapters'&&advanced&&!advanced.querySelector('#g5Open')){const link=document.createElement('a');link.id='g5Open';link.className='button button-outline button-small';link.textContent='录音与复习音频';link.href='#space/media';advanced.append(link);}
      if(state.view!=='media'){stop();if(recorder?.state==='recording')recorder.stop();return;}const root=document.createElement('section');root.id='g5Workspace';root.className='c-learning panel section-width';document.querySelector('#spaceContent').prepend(root);draw();void load().catch(err=>toast(err.message));}};
  }};
})();
