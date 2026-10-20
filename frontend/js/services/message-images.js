/* Store image blobs separately from serializable message history. */
(() => {
  'use strict';
  window.XueyaMessageImages={create({state,cache,toast}){
    const urls=new Map(),loading=new Set();let dialog,course=state.courseId;
    const prefix=()=>`chat-image:${state.courseId}:`;
    const allowed=ref=>ref?.courseId===state.courseId&&typeof ref.key==='string'&&ref.key.startsWith(prefix());
    function remember(batch,messageId){return batch.filter(a=>a.file.type.startsWith('image/')).map((a,i)=>{
      const ref={courseId:state.courseId,key:prefix()+messageId+':'+i,name:a.file.name,mime:a.file.type};
      urls.set(ref.key,a.url);void cache.put(ref.key,a.file).catch(()=>toast('图片当前可查看，但未能保存原件；请保留本地图片。'));return ref;
    });}
    const source=ref=>allowed(ref)?urls.get(ref.key)||'':'';
    async function restore(ref){
      if(!allowed(ref))return '';
      if(urls.has(ref.key))return urls.get(ref.key);
      const file=await cache.get(ref.key);
      if(!(file instanceof Blob)||!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>6*1024*1024)return '';
      if(!urls.has(ref.key))urls.set(ref.key,URL.createObjectURL(file));return urls.get(ref.key);
    }
    function mount(){
      if(course!==state.courseId){dialog?.close();course=state.courseId;}
      for(const node of document.querySelectorAll('[data-sent-image]')){
        const ref=state.messages.flatMap(m=>m.images||[]).find(r=>r.key===node.dataset.sentImage);
        if(!ref||!allowed(ref)||loading.has(ref.key))continue;
        const set=value=>{if(!allowed(ref))return;for(const current of document.querySelectorAll('[data-sent-image]')){if(current.dataset.sentImage!==ref.key)continue;const missing=current.parentElement.querySelector('[data-image-missing]');if(value){current.src=value;current.hidden=false;missing?.setAttribute('hidden','');}else{current.hidden=true;if(missing){missing.textContent=ref.name+' · 当前浏览器无原件';missing.hidden=false;}}}};
        if(source(ref)){set(source(ref));continue;}
        loading.add(ref.key);void restore(ref).then(set).catch(()=>set('')).finally(()=>loading.delete(ref.key));
      }
    }
    async function open(key){
      const ref=state.messages.flatMap(m=>m.images||[]).find(r=>r.key===key);if(!ref||!allowed(ref))return;
      const value=await restore(ref).catch(()=>null);
      if(!allowed(ref))return;
      if(!value){toast('当前浏览器没有这张图片的原件，请在原浏览器查看或重新选择图片。');return;}
      if(!dialog){dialog=document.createElement('dialog');dialog.id='messageImageDialog';dialog.className='source-dialog message-image-dialog';dialog.setAttribute('aria-label','查看发送的图片');dialog.innerHTML='<div class="dialog-head"><strong></strong><button type="button" class="button button-outline button-small" data-close-message-image>关闭</button></div><div class="message-image-preview"><img alt=""></div>';document.body.append(dialog);dialog.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();dialog.close();}});dialog.querySelector('button').onclick=()=>dialog.close();dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});}
      dialog.querySelector('strong').textContent=ref.name;const image=dialog.querySelector('img');image.src=value;image.alt=ref.name;if(!dialog.open)dialog.showModal();
    }
    window.addEventListener('pagehide',()=>{for(const url of urls.values())URL.revokeObjectURL(url);urls.clear();});
    return {remember,source,mount,open};
  }};
})();
