/* Conversation-only sidebar: viewport height, remembered width and a mobile drawer. */
(() => {
  'use strict';
  window.XueyaHistoryLayout={create(){
    const key='xueya-history-width-v1',mobile=matchMedia('(max-width:760px)');
    let preferred=null,drag=null,open=false;
    try{const saved=localStorage.getItem(key);if(saved!==null&&Number.isFinite(Number(saved)))preferred=Number(saved);}catch{}
    const active=()=>location.hash.replace(/^#/,'').split('/').slice(0,2).join('/')==='space/chat';
    const limits=()=>({min:180,max:Math.max(180,Math.min(innerWidth*.45,innerWidth-480))});
    const width=()=>Math.max(limits().min,Math.min(limits().max,preferred??innerWidth*.2));
    function save(){try{preferred===null?localStorage.removeItem(key):localStorage.setItem(key,String(Math.round(width())));}catch{}}
    function apply(){
      document.documentElement.style.setProperty('--history-width',width()+'px');
      const handle=document.querySelector('[data-history-resize]');
      if(handle){handle.setAttribute('aria-valuemin',String(limits().min));handle.setAttribute('aria-valuemax',String(Math.round(limits().max)));handle.setAttribute('aria-valuenow',String(Math.round(width())));}
    }
    function drawer(value,focus=true){
      open=!!value&&mobile.matches&&active();document.body.classList.toggle('history-drawer-open',open);
      const panel=document.querySelector('#chatHistoryPanel'),trigger=document.querySelector('[data-history-open]');
      trigger?.setAttribute('aria-expanded',String(open));
      if(panel){if(open){panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');if(focus)panel.querySelector('[data-history-close]')?.focus();}else{panel.removeAttribute('role');panel.removeAttribute('aria-modal');}}
      if(!open&&focus)trigger?.focus({preventScroll:true});
    }
    function end(){if(!drag)return;drag=null;document.body.classList.remove('history-resizing');save();}
    function mount(){
      document.body.classList.toggle('history-layout',active());
      if(!active()){end();open=false;}
      apply();drawer(open,false);
    }
    document.addEventListener('pointerdown',event=>{
      const handle=event.target.closest('[data-history-resize]');if(!handle||mobile.matches||event.button!==0)return;
      event.preventDefault();drag={id:event.pointerId,x:event.clientX,width:width()};document.body.classList.add('history-resizing');handle.focus({preventScroll:true});
      handle.setPointerCapture?.(event.pointerId);
    });
    window.addEventListener('pointermove',event=>{if(!drag||event.pointerId!==drag.id)return;preferred=Math.max(limits().min,Math.min(limits().max,drag.width+event.clientX-drag.x));apply();});
    window.addEventListener('pointerup',end);window.addEventListener('pointercancel',end);window.addEventListener('blur',end);
    document.addEventListener('dblclick',event=>{if(event.target.closest('[data-history-resize]')){end();preferred=null;save();apply();}});
    document.addEventListener('click',event=>{
      if(event.target.closest('[data-history-open]'))drawer(true);
      if(event.target.closest('[data-history-close]'))drawer(false);
      if(event.target.closest('[data-session],[data-new-session],[data-clear-chat]')&&open)drawer(false,false);
    });
    document.addEventListener('keydown',event=>{
      if(event.target.closest('[data-history-resize]')&&!mobile.matches){
        const changes={ArrowLeft:width()-16,ArrowRight:width()+16,Home:limits().min,End:limits().max};
        if(event.key in changes){event.preventDefault();preferred=Math.max(limits().min,Math.min(limits().max,changes[event.key]));save();apply();}
      }
      if(!open||event.defaultPrevented)return;
      if(event.key==='Escape'){event.preventDefault();drawer(false);}
      if(event.key==='Tab'){
        const items=[...document.querySelectorAll('#chatHistoryPanel button:not([disabled]),#chatHistoryPanel input:not([disabled])')].filter(el=>el.checkVisibility());
        if(!items.length)return;const first=items[0],last=items.at(-1);
        if(event.shiftKey&&(document.activeElement===first||!document.querySelector('#chatHistoryPanel').contains(document.activeElement))){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&(document.activeElement===last||!document.querySelector('#chatHistoryPanel').contains(document.activeElement))){event.preventDefault();first.focus();}
      }
    });
    window.addEventListener('resize',()=>{end();if(!mobile.matches)drawer(false,false);apply();});
    window.addEventListener('hashchange',mount);
    return {mount};
  }};
})();
