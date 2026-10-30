/* Microphone -> PCM WAV -> existing ASR -> editable draft. Never auto-send. */
(() => {
  'use strict';
  window.XueyaComposerInput = {create({state, persist, render, toast}) {
    let phase='idle', error='', recorder, stream, controller, timer, deadline, audioFile, media, owner='', epoch=0;
    const busy=()=>['requesting','recording','transcribing'].includes(phase);
    const key=()=>state.courseId+':'+state.sessionId;
    function release(){clearInterval(timer);clearTimeout(deadline);stream?.getTracks().forEach(track=>track.stop());stream=null;}
    function cancel(redraw=true){epoch++;controller?.abort();controller=null;const active=recorder;recorder=null;if(active?.state==='recording'){active.onstop=null;active.stop();}release();phase='idle';error='';audioFile=null;media=null;if(redraw)render();}
    function fail(err){phase='error';error=({NotAllowedError:'无法使用麦克风，请在浏览器地址栏允许麦克风后重试。',NotFoundError:'没有找到麦克风，请检查设备连接。',NotReadableError:'麦克风正被占用，请关闭其他录音程序后重试。',ASR_NOT_CONFIGURED:'尚未配置语音识别服务，请检查服务设置。',AI_TIMEOUT:'语音识别响应超时，录音已保留。请先到任务与用量核对本次调用。',AI_UNAVAILABLE:'语音识别服务暂不可用，录音已保留，可手动重试。',LOGIN_REQUIRED:'请先登录，再重试语音识别。'}[err.code||err.name]||err.message||'录音未完成，请重试。');render();toast(error);}
    async function pcm(blob){
      const context=new AudioContext();
      try{
        const decoded=await context.decodeAudioData(await blob.arrayBuffer());
        if(!decoded.length||decoded.duration>62)throw Error('录音无效或超过一分钟，请重新录制。');
        const offline=new OfflineAudioContext(1,Math.ceil(decoded.duration*16000),16000);
        const source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start();
        const rendered=await offline.startRendering(),samples=rendered.getChannelData(0),bytes=new ArrayBuffer(44+samples.length*2),view=new DataView(bytes);
        const text=(at,value)=>{for(let i=0;i<value.length;i++)view.setUint8(at+i,value.charCodeAt(i));};
        text(0,'RIFF');view.setUint32(4,36+samples.length*2,true);text(8,'WAVE');text(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,samples.length*2,true);
        for(let i=0;i<samples.length;i++){const n=Math.max(-1,Math.min(1,samples[i]));view.setInt16(44+i*2,n<0?n*32768:n*32767,true);}
        return {file:new File([bytes],'语音提问.wav',{type:'audio/wav'}),durationMs:Math.ceil(samples.length/16)};
      }finally{await context.close();}
    }
    async function transcribe(version){
      const courseId=state.courseId;
      controller=new AbortController();const signal=controller.signal;
      const api=(path,body,headers)=>window.XueyaPlatform.learningRequest(path,{courseId,method:'POST',body,headers,signal});
      phase='transcribing';error='';render();
      try{
        if(!media)media=await api('media/upload?'+new URLSearchParams({name:audioFile.file.name,durationMs:audioFile.durationMs}),audioFile.file,{'Content-Type':'audio/wav'});
        signal.throwIfAborted();if(version!==epoch||owner!==key())return;
        const result=await api('media/transcribe',{segments:[{id:media.id,version:media.version,startMs:0,endMs:media.endMs}]});
        signal.throwIfAborted();if(version!==epoch||owner!==key())return;
        const text=String(result.text||'').trim();if(!text)throw Error('没有识别出文字，请靠近麦克风重新录音。');
        const draft=state.draft+(state.draft.trim()?'\n':'')+text;
        if(draft.length>4000)throw Error('语音文字加上草稿超过4000字，请缩短草稿后手动重试。');
        state.draft=draft;persist();phase='idle';audioFile=null;media=null;render();
        document.querySelector('#chatInput')?.focus();toast('语音已转成文字，请核对后点击发送。');
      }catch(err){if(version===epoch&&!signal.aborted)fail(err);}
      finally{if(version===epoch)controller=null;}
    }
    async function toggle(){
      if(phase==='recording'){if(recorder?.state==='recording'){phase='transcribing';render();recorder.stop();}return;}
      if(busy()||state.pending)return;
      if(!window.XueyaPlatform?.available){toast('请先启动本地服务并登录，再使用录音。');return;}
      if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){toast('当前浏览器无法录音，请使用本地服务地址及新版 Chrome 或 Edge。');return;}
      cancel(false);owner=key();const version=epoch;phase='requesting';render();
      try{
        const granted=await navigator.mediaDevices.getUserMedia({audio:true});
        if(version!==epoch||owner!==key()){granted.getTracks().forEach(track=>track.stop());return;}
        stream=granted;const parts=[];let bytes=0;
        const mime=['audio/webm;codecs=opus','audio/mp4','audio/webm'].find(type=>MediaRecorder.isTypeSupported(type));
        const active=new MediaRecorder(stream,mime?{mimeType:mime}:{});recorder=active;
        active.ondataavailable=event=>{if(event.data.size){parts.push(event.data);bytes+=event.data.size;if(bytes>6*1024*1024&&active.state==='recording')active.stop();}};
        active.onerror=()=>{if(version===epoch){cancel(false);fail(Error('浏览器录音失败，请重新录制。'));}};
        active.onstop=async()=>{
          release();if(version!==epoch||owner!==key())return;
          phase='transcribing';render();
          try{const value=await pcm(new Blob(parts,{type:active.mimeType}));if(version!==epoch||owner!==key())return;audioFile=value;await transcribe(version);}
          catch(err){if(version===epoch)fail(err);}
        };
        active.start(250);phase='recording';const started=Date.now();render();
        timer=setInterval(()=>{const target=document.querySelector('[data-voice-status]');if(target)target.textContent='正在录音 '+Math.floor((Date.now()-started)/1000)+' 秒 · 停止后识别，核对后发送';},250);
        deadline=setTimeout(()=>{if(active.state==='recording')active.stop();},60000);
      }catch(err){if(version===epoch){release();fail(err);}}
    }
    window.addEventListener('pagehide',()=>cancel(false));
    return {toggle,cancel,retry(){if(!busy()&&audioFile&&owner===key())return transcribe(epoch);},get busy(){return busy();},get status(){return {phase,error,canRetry:!!audioFile};},mount(){if((owner&&owner!==key())||!['overview','ask','chat'].includes(state.view)){if(phase!=='idle'||audioFile)cancel(false);}}};
  }};
})();
