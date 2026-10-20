/* MiMo-inspired dot and ring, with native cursors for editing and touch. */
(() => {
  document.addEventListener('DOMContentLoaded',()=>{
    const fine=matchMedia('(hover: hover) and (pointer: fine)');
    const reduced=matchMedia('(prefers-reduced-motion: reduce)');
    const ring=document.createElement('div');
    const dot=document.createElement('div');
    ring.className='cursor-ring';dot.className='cursor-dot';
    ring.setAttribute('aria-hidden','true');dot.setAttribute('aria-hidden','true');
    document.body.append(ring,dot);
    let x=0,y=0,targetX=0,targetY=0,vx=0,vy=0,frame=0,last=0,shown=false;

    function hide(){
      shown=false;cancelAnimationFrame(frame);frame=0;
      document.body.classList.remove('custom-cursor','cursor-interactive','cursor-editing','cursor-pressed','cursor-on-dark');
    }

    function tick(time){
      frame=0;if(!shown||!fine.matches||reduced.matches||document.hidden)return;
      const dt=last?Math.min((time-last)/1000,.05):1/60;last=time;
      const sx=window.XueyaMotion.spring(x,vx,targetX,dt,.09);
      const sy=window.XueyaMotion.spring(y,vy,targetY,dt,.09);
      x=sx.position;vx=sx.velocity;y=sy.position;vy=sy.velocity;
      ring.style.transform=`translate3d(${x}px,${y}px,0)`;
      if(Math.hypot(targetX-x,targetY-y)>.05||Math.hypot(vx,vy)>.05)frame=requestAnimationFrame(tick);
    }

    function move(event){
      if(event.pointerType!=='mouse'||!fine.matches||reduced.matches)return hide();
      const target=event.target instanceof Element?event.target:null;
      const editing=Boolean(target?.closest('dialog,input,textarea,select,[contenteditable="true"],.source-quote,.message-body p,.knowledge-card p,.document-copy,.quiz-feedback'));
      if(editing){hide();document.body.classList.add('cursor-editing');return;}
      document.body.classList.remove('cursor-editing');
      targetX=event.clientX;targetY=event.clientY;
      // Keep the ring within 10px even during a fast sweep.
      const gap=Math.hypot(targetX-x,targetY-y);if(shown&&gap>10){x=targetX+(x-targetX)*10/gap;y=targetY+(y-targetY)*10/gap;vx=0;vy=0;ring.style.transform=`translate3d(${x}px,${y}px,0)`;}
      if(!shown){x=targetX;y=targetY;vx=0;vy=0;last=0;shown=true;ring.style.transform=`translate3d(${x}px,${y}px,0)`;}
      dot.style.transform=`translate3d(${targetX}px,${targetY}px,0)`;
      document.body.classList.add('custom-cursor');
      document.body.classList.toggle('cursor-interactive',Boolean(target?.closest('a,button,[role="button"],label[for],.plan-task')));
      document.body.classList.toggle('cursor-on-dark',Boolean(target?.closest('.evidence-section,.button-dark,.button-blue,.send-button')));
      if(!frame)frame=requestAnimationFrame(tick);
    }

    document.addEventListener('pointermove',move,{passive:true});
    document.addEventListener('pointerover',move,{passive:true});
    document.addEventListener('pointerdown',event=>{if(shown&&event.pointerType==='mouse')document.body.classList.add('cursor-pressed');});
    document.addEventListener('pointerup',()=>document.body.classList.remove('cursor-pressed'));
    document.addEventListener('pointerout',event=>{if(!event.relatedTarget)hide();});
    document.addEventListener('keydown',event=>{if(['Tab','Escape'].includes(event.key))hide();});
    document.addEventListener('focusin',event=>{if(event.target instanceof Element&&event.target.closest('dialog,input,textarea,select,[contenteditable="true"]'))hide();});
    document.addEventListener('visibilitychange',()=>{if(document.hidden)hide();});
    window.addEventListener('blur',hide);
    fine.addEventListener('change',hide);reduced.addEventListener('change',hide);
  });
})();
