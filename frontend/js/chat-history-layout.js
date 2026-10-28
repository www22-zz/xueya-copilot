/* Conversation-only sidebar: viewport height, remembered width, drag-to-collapse and a mobile drawer. */
(() => {
  'use strict';
  window.XueyaHistoryLayout={create(){
    const key='xueya-history-width-v1', collapsedKey='xueya-sidebar-collapsed-v1', mobile=matchMedia('(max-width:760px)');
    let preferred=null,drag=null,open=false,resizeFocused=false;
    try{const saved=localStorage.getItem(key);if(saved!==null&&Number.isFinite(Number(saved)))preferred=Number(saved);}catch{}
    const active=()=>location.hash.replace(/^#/,'').split('/').slice(0,2).join('/')==='space/ask';
    const limits=()=>({min:180,max:Math.max(180,Math.min(innerWidth*.45,innerWidth-480))});
    const width=()=>Math.max(limits().min,Math.min(limits().max,preferred??Math.round(innerWidth*.22)));
    function isCollapsed(){return document.body.classList.contains('sidebar-collapsed');}
    function save(){
      try{
        if(isCollapsed()){localStorage.setItem(collapsedKey,'true');}
        else{localStorage.removeItem(collapsedKey);localStorage.setItem(key,String(Math.round(width())));}
      }catch{}
    }
    function apply(){
      if(isCollapsed()){
        document.documentElement.style.setProperty('--history-width','0px');
      }else{
        document.documentElement.style.setProperty('--history-width',width()+'px');
      }
      const handle=document.querySelector('[data-history-resize]');
      if(handle){
        handle.setAttribute('aria-valuemin',String(limits().min));
        handle.setAttribute('aria-valuemax',String(Math.round(limits().max)));
        handle.setAttribute('aria-valuenow',String(Math.round(width())));
      }
    }
    function toggleSidebar(forceState){
      if(mobile.matches){drawer(!open);return;}
      const willCollapse = typeof forceState === 'boolean' ? !forceState : !isCollapsed();
      document.body.classList.toggle('sidebar-collapsed', willCollapse);
      if(!willCollapse && (!preferred || preferred < limits().min)){
        preferred = Math.round(innerWidth * 0.22);
      }
      apply();
      save();
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
      if(!active()){end();open=false;resizeFocused=false;}
      try{if(localStorage.getItem(collapsedKey)==='true'){document.body.classList.add('sidebar-collapsed');}}catch{}
      apply();drawer(open,false);
      if(active()&&!mobile.matches&&resizeFocused)document.querySelector('[data-history-resize]')?.focus({preventScroll:true});
    }
    document.addEventListener('pointerdown',event=>{
      const handle=event.target.closest('[data-history-resize]');if(!handle)resizeFocused=false;if(!handle||mobile.matches||event.button!==0)return;
      event.preventDefault();drag={id:event.pointerId,x:event.clientX,width:isCollapsed()?0:width()};document.body.classList.add('history-resizing');handle.focus({preventScroll:true});
      handle.setPointerCapture?.(event.pointerId);
    });
    window.addEventListener('pointermove',event=>{
      if(!drag||event.pointerId!==drag.id)return;
      const targetWidth = drag.width + event.clientX - drag.x;
      if(targetWidth < 140){
        if(!isCollapsed()){
          document.body.classList.add('sidebar-collapsed');
          document.documentElement.style.setProperty('--history-width','0px');
        }
        return;
      }
      if(isCollapsed()){
        document.body.classList.remove('sidebar-collapsed');
      }
      preferred = Math.max(limits().min, Math.min(limits().max, targetWidth));
      apply();
    });
    window.addEventListener('pointerup',end);window.addEventListener('pointercancel',end);window.addEventListener('blur',end);
    document.addEventListener('focusin',event=>{resizeFocused=!!event.target.closest('[data-history-resize]');});
    document.addEventListener('dblclick',event=>{if(event.target.closest('[data-history-resize]')){end();toggleSidebar();}});
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
    window.XueyaToggleSidebar=toggleSidebar;return {mount,toggleSidebar};
  }};
})();
