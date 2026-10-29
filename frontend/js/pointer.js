/* Frame-synced pointer above modal dialogs; native cursors for editing. */
(() => {
  document.addEventListener('DOMContentLoaded',()=>{
    const fine=matchMedia('(hover: hover) and (pointer: fine)');
    const reduced=matchMedia('(prefers-reduced-motion: reduce)');
    const layer=document.createElement('div');
    layer.className='cursor-layer';layer.setAttribute('aria-hidden','true');
    const topLayer=typeof layer.showPopover==='function';
    if(topLayer)layer.setAttribute('popover','manual');
    const ring=document.createElement('div');
    const dot=document.createElement('div');
    ring.className='cursor-ring';dot.className='cursor-dot';
    ring.setAttribute('aria-hidden','true');dot.setAttribute('aria-hidden','true');
    layer.append(ring,dot);document.body.append(layer);
    let x=0,y=0,frame=0,shown=false,dragging=false,pressStart=null;
    let lastTarget=null,editing=false,interactive=false,onDark=false,scrollArea=null;
    let displayedInteractive=false,displayedDark=false;
    const original=window.XueyaWorkspaceAppearance.isOriginal;
    const legacy=window.XueyaOriginalPointer.create({ring,dot,active:original});
    function routePointer(){
      hide();legacy.hide();
      if(topLayer&&layer.matches(':popover-open'))layer.hidePopover();
      if(original())document.body.append(ring,dot);else layer.append(ring,dot);
      lastTarget=null;
    }
    window.addEventListener('hashchange',routePointer);
    routePointer();

    function hide(){
      cancelAnimationFrame(frame);frame=0;
      if(shown){shown=false;document.body.classList.remove('custom-cursor','cursor-interactive','cursor-on-dark');displayedInteractive=false;displayedDark=false;}
    }

    function raise(){
      if(!topLayer)return true;
      try{if(!layer.matches(':popover-open'))layer.showPopover();return true;}
      catch{return false;}
    }
    function paint(){
      frame=0;if(!shown)return;
      // Both marks use the latest coordinates, without a trailing spring.
      const transform=`translate3d(${x}px,${y}px,0)`;
      ring.style.transform=transform;dot.style.transform=transform;
    }
    function classify(target){
      if(target===lastTarget)return;
      lastTarget=target;
      editing=Boolean(target?.closest('iframe,object,embed,input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit]),textarea,[contenteditable="true"],.source-quote,.message-body p,.knowledge-card p,.document-copy,.quiz-feedback'));
      interactive=Boolean(target?.closest('a,button,select,summary,[role="button"],[role="option"],label[for],.plan-task,input[type=checkbox],input[type=radio]'));
      onDark=Boolean(target?.closest('.evidence-section,.button-dark,.button-blue,.send-button'));
      scrollArea=null;
      if(target){
        const style=getComputedStyle(target);
        const vertical=/(auto|scroll)/.test(style.overflowY)&&target.scrollHeight>target.clientHeight;
        const horizontal=/(auto|scroll)/.test(style.overflowX)&&target.scrollWidth>target.clientWidth;
        if(vertical||horizontal)scrollArea={rect:target.getBoundingClientRect(),vertical,horizontal};
      }
    }

    function move(event){
      if(original())return;
      if(pressStart&&Math.hypot(event.clientX-pressStart.x,event.clientY-pressStart.y)>5)dragging=true;
      if(dragging||event.pointerType!=='mouse'||!fine.matches||reduced.matches)return hide();
      const target=event.target instanceof Element?event.target:null;
      classify(target);
      const nativeScroll=scrollArea&&((scrollArea.vertical&&event.clientX>=scrollArea.rect.right-12)||(scrollArea.horizontal&&event.clientY>=scrollArea.rect.bottom-12));
      if(editing||nativeScroll||(!topLayer&&target?.closest('dialog')))return hide();
      x=event.clientX;y=event.clientY;
      if(!shown){
        if(!raise())return hide();
        shown=true;paint();document.body.classList.add('custom-cursor');
      }
      if(displayedInteractive!==interactive){displayedInteractive=interactive;document.body.classList.toggle('cursor-interactive',interactive);}
      if(displayedDark!==onDark){displayedDark=onDark;document.body.classList.toggle('cursor-on-dark',onDark);}
      if(!frame)frame=requestAnimationFrame(paint);
    }

    // A new modal covers earlier popovers; raise the pointer after transitions.
    function refreshLayer(){
      if(original())return;
      lastTarget=null;
      if(topLayer){
        if(layer.matches(':popover-open'))layer.hidePopover();
        if(shown&&!raise())hide();
      }else hide();
    }
    new MutationObserver(records=>{
      if(records.some(record=>record.target instanceof HTMLDialogElement))refreshLayer();
    }).observe(document.body,{attributes:true,attributeFilter:['open'],subtree:true});
    document.addEventListener('xueya:overlay-open',refreshLayer);
    document.addEventListener('pointermove',move,{passive:true});
    document.addEventListener('pointerover',move,{passive:true});
    document.addEventListener('pointerdown',event=>{
      if(original()||event.pointerType!=='mouse')return;
      pressStart={x:event.clientX,y:event.clientY};
      move(event);
    });
    document.addEventListener('pointerup',event=>{if(original())return;pressStart=null;dragging=false;move(event);});
    document.addEventListener('pointercancel',()=>{pressStart=null;dragging=false;hide();});
    document.addEventListener('pointerout',event=>{if(!event.relatedTarget)hide();});
    document.addEventListener('keydown',event=>{if(['Tab','Escape'].includes(event.key))hide();});
    document.addEventListener('focusin',event=>{if(!original()&&event.target instanceof Element&&event.target.matches('input:not([type=checkbox]):not([type=radio]),textarea,[contenteditable="true"]'))hide();});
    document.addEventListener('scroll',()=>{lastTarget=null;},{capture:true,passive:true});
    window.addEventListener('resize',()=>{lastTarget=null;});
    document.addEventListener('visibilitychange',()=>{if(document.hidden)hide();});
    window.addEventListener('blur',()=>{pressStart=null;dragging=false;hide();});
    fine.addEventListener('change',hide);reduced.addEventListener('change',hide);
  });
})();
