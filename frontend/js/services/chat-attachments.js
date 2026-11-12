/* Image + voice inputs belong to the conversation, not a separate mode. */
(() => {
'use strict';
const cache=new WeakMap();
const e=value=>window.XueyaRich.escape(value);
async function duration(file,signal){return new Promise((resolve,reject)=>{const audio=document.createElement('audio'),url=URL.createObjectURL(file);let timer;const clear=()=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);audio.removeAttribute('src');audio.load();URL.revokeObjectURL(url);};const abort=()=>{clear();reject(new DOMException('已取消','AbortError'));};timer=setTimeout(()=>{clear();reject(new Error('无法读取录音时长，请选择 WAV 或 MP3 文件。'));},10000);audio.onloadedmetadata=()=>{const ms=Math.ceil(audio.duration*1000);clear();Number.isFinite(ms)&&ms>0?resolve(ms):reject(new Error('录音时长无效。'));};audio.onerror=()=>{clear();reject(new Error('浏览器无法读取这份录音。'));};signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted){abort();return;}audio.src=url;});}
function reviewTranscript(text,signal){return new Promise((resolve,reject)=>{const dialog=document.createElement('dialog');dialog.className='source-dialog c-dialog';dialog.id='voiceTranscriptDialog';dialog.setAttribute('aria-label','核对语音文字');dialog.innerHTML=`<div class="dialog-head"><strong>先核对语音文字</strong><button type="button" data-voice-cancel>取消</button></div><form class="c-dialog-body"><p>语音识别可能出错。核对或修改后，作为这次提问发送；不会自动当作课程原文。</p><label class="form-field">识别文字<textarea name="transcript" rows="7" maxlength="12000" required>${e(text)}</textarea></label><button type="submit" class="button button-blue button-small">确认文字，继续提问</button></form>`;document.body.append(dialog);let settled=false;const finish=(value)=>{if(settled)return;settled=true;signal?.removeEventListener('abort',abort);dialog.close();dialog.remove();value===null?reject(new DOMException('已取消','AbortError')):resolve(value);};const abort=()=>finish(null);dialog.addEventListener('cancel',event=>{event.preventDefault();finish(null);});dialog.querySelector('[data-voice-cancel]').onclick=()=>finish(null);dialog.querySelector('form').onsubmit=event=>{event.preventDefault();const value=new FormData(event.target).get('transcript').trim();if(value)finish(value);};signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted){finish(null);return;}dialog.showModal();dialog.querySelector('textarea').focus();});}
window.XueyaChatAttachments={async respond(files,request,options={}){
 const {signal,onUpdate=()=>{}}=options,courseId=request.courseId;
 const api=(path,body,headers)=>window.XueyaPlatform.learningRequest(path,{courseId,method:body===undefined?'GET':'POST',body,headers,signal});
 const images=[],transcripts=[];
 for(const file of files){signal?.throwIfAborted();let cached=cache.get(file);if(cached?.courseId!==courseId)cached={courseId};
  const audio=file.type.startsWith('audio/')||/\.(wav|mp3)$/i.test(file.name);
  if(!cached.media){onUpdate({progress:audio?'正在读取语音附件…':'正在读取图片附件…'});const ms=audio?await duration(file,signal):null;const mime=audio?(/\.wav$/i.test(file.name)?'audio/wav':'audio/mpeg'):file.type;cached.media=await api('media/upload?'+new URLSearchParams({name:file.name,...(ms?{durationMs:ms}:{})}),file,{'Content-Type':mime});cache.set(file,cached);}
  if(audio){if(!cached.text){onUpdate({progress:'正在转写语音，可随时停止…'});const m=cached.media;const result=await api('media/transcribe',{segments:[{id:m.id,version:m.version,startMs:0,endMs:m.endMs}]});cached.text=result.text;cache.set(file,cached);}onUpdate({progress:'请核对语音文字后继续…'});cached.confirmed=await reviewTranscript(cached.confirmed||cached.text,signal);cache.set(file,cached);transcripts.push(cached.confirmed);}
  else images.push({id:cached.media.id,version:cached.media.version});
 }
 const question=request.question+(transcripts.length?'\n\n用户已核对的语音提问：\n'+transcripts.join('\n\n'):'');
 if(question.length>4000)throw new Error('语音文字和问题超过 4000 字，请缩短录音或文字后发送。');
 let result;
 if(images.length){onUpdate({progress:'正在结合图片和问题回答…'});const response=await api('chat/respond',{...request,question,media:images});const known=request.sources;result={...response,sources:(response.sources||[]).map(id=>known.find(s=>s.id===id)).filter(Boolean),engine:response.online?'图文回答':'图片回答暂不可用',online:response.online===true};}
 else{onUpdate({progress:'正在根据已核对的语音问题回答…'});result=await window.XueyaChat.createChatService().stream({...request,question},{...options,workflow:true});}
 return {...result,transcript:transcripts.join('\n\n')};
}};
})();
