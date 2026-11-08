/* Original knowledge globe: deterministic point geometry, no external assets. */
(() => {
  const paths={arrow:'M4 12h16m-6-6 6 6-6 6',down:'M12 4v16m-6-6 6 6 6-6',external:'M7 17 17 7M7 7h10v10',file:'M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5',check:'m5 12 4 4L19 6',spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z',tree:'M12 3v6M6 9h12M6 9v6M18 9v6M4 15h4v5H4zM16 15h4v5h-4zM10 3h4',layers:'m12 3 10 5-10 5L2 8zM2 12l10 5 10-5M2 16l10 5 10-5',link:'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2',bookmark:'M6 3h12v18l-6-4-6 4z',pause:'M9 5v14M15 5v14',play:'m8 5 11 7-11 7z',close:'m6 6 12 12M6 18 18 6',search:'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',upload:'M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5',trash:'M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7',refresh:'M20 8a8 8 0 1 0 0 8M20 3v5h-5',target:'M20 12a8 8 0 1 1-8-8M16 12a4 4 0 1 1-4-4M12 12l8-8M17 4h3v3',calendar:'M5 5h14v16H5zM8 3v4M16 3v4M5 10h14M9 14h1M14 14h1M9 17h1'};
  window.XueyaIcons=()=>document.querySelectorAll('[data-icon]').forEach(el=>{const name=el.dataset.icon;if(paths[name])el.innerHTML=`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name]}"/></svg>`;});
  document.addEventListener('DOMContentLoaded',()=>{
    window.XueyaIcons();const reduced=matchMedia('(prefers-reduced-motion: reduce)');
    if('IntersectionObserver'in window){
      document.body.classList.add('js-motion');
      const observer=new IntersectionObserver(entries=>{
        entries.forEach(entry=>{
          if(entry.isIntersecting){
            entry.target.classList.add('is-visible');
          }else if(entry.boundingClientRect.top>0){
            entry.target.classList.remove('is-visible');
          }
        });
      },{threshold:.12,rootMargin:'0px 0px -40px 0px'});
      document.querySelectorAll('.reveal').forEach(el=>observer.observe(el));
      window.addEventListener('scroll',()=>{
        if(window.scrollY<40){
          document.querySelectorAll('.reveal').forEach(el=>{
            if(el.getBoundingClientRect().top>window.innerHeight){
              el.classList.remove('is-visible');
            }
          });
        }
      },{passive:true});
    }
    const universe=document.querySelector('.knowledge-universe');
    const canvas=document.getElementById('knowledgeCanvas'),ctx=canvas.getContext('2d');if(!ctx)return;
    const motion=window.XueyaMotion,fine=matchMedia('(hover: hover) and (pointer: fine)');
    const center=universe.querySelector('[data-graph-center]');
    const nodes=[...universe.querySelectorAll('[data-node]')].map((el,index)=>({el,id:el.dataset.node,x:Number(el.dataset.x)/100,y:Number(el.dataset.y)/100,index}));
    const leaves=[...universe.querySelectorAll('[data-leaf]')].map((el,index)=>({el,id:el.dataset.leaf,parent:el.dataset.parent,x:Number(el.dataset.x)/100,y:Number(el.dataset.y)/100,index}));
    const connections=document.getElementById('knowledgeConnections');
    const points=[],count=820;
    for(let i=0;i<count;i++){const y=1-(i/(count-1))*2,r=Math.sqrt(1-y*y),a=i*Math.PI*(3-Math.sqrt(5));points.push({x:Math.cos(a)*r,y,z:Math.sin(a)*r});}
    let width=0,height=0,dpr=1,angle=.5,frame=0,visible=false,paused=false,last=0,hovered=null,focused=null;
    let tiltX=0,tiltY=0,velocityX=0,velocityY=0,targetX=0,targetY=0,influence=0,influenceVelocity=0;
    const globe={x:0,y:0,radius:0,outline:null};
    const globeSquash=.96,globeSkew=.1;
    const mouse={x:0,y:0,overGlobe:false};
    const toggle=document.getElementById('motionToggle');
    const activeNode=()=>focused||hovered;
    const canAnimate=()=>visible&&!paused&&!reduced.matches&&!document.hidden;

    function fadeSpotlight(){
      if(!mouse.overGlobe)return;
      mouse.overGlobe=false;
      influenceVelocity=0;
    }

    function clearSpotlight(){
      mouse.overGlobe=false;
      influence=0;
      influenceVelocity=0;
    }

    function resize(){
      const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;
      dpr=Math.min(devicePixelRatio||1,2);
      canvas.width=Math.max(1,Math.round(width*dpr));canvas.height=Math.max(1,Math.round(height*dpr));
      globe.x=width*.5;globe.y=height*.49;globe.radius=width*.31;
      const circle=new Path2D();
      circle.arc(0,0,globe.radius,0,Math.PI*2);
      globe.outline=new Path2D();
      globe.outline.addPath(circle,new DOMMatrix([1,globeSkew,0,globeSquash,globe.x,globe.y]));
      clearSpotlight();
      ctx.setTransform(dpr,0,0,dpr,0,0);draw();
    }

    function drawGraph(){
      if(width<1)return;
      const active=activeNode(),quiet=paused||reduced.matches;
      universe.dataset.activeNode=active||'';
      const centerX=width*.5+tiltX*9,centerY=height*.49+tiltY*7;
      center.style.transform=`translate(-50%,-50%) translate3d(${tiltX*9}px,${tiltY*7}px,0)`;
      const positions={};
      for(const node of nodes){
        const driftX=quiet?0:Math.sin(angle*6+node.index*2)*2.5;
        const driftY=quiet?0:Math.cos(angle*5+node.index*2)*2.5;
        const dx=tiltX*10+driftX,dy=tiltY*8+driftY;
        node.el.style.transform=`translate(-50%,-50%) translate3d(${dx}px,${dy}px,0)`;
        node.el.classList.toggle('is-active',node.id===active);
        const x=node.x*width+dx,y=node.y*height+dy;
        positions[node.id]={x,y};
        const line=connections.querySelector(`[data-branch="${node.id}"]`);
        line.setAttribute('d',`M ${centerX/width*600} ${centerY/height*600} L ${x/width*600} ${y/height*600}`);
        line.classList.toggle('is-active',node.id===active);
      }
      for(const leaf of leaves){
        const dx=tiltX*15+(quiet?0:Math.sin(angle*5+leaf.index)*2);
        const dy=tiltY*12+(quiet?0:Math.cos(angle*5+leaf.index)*2);
        leaf.el.style.transform=`translate(-50%,-50%) translate3d(${dx}px,${dy}px,0)`;
        leaf.el.classList.toggle('is-active',leaf.parent===active);
        const parent=positions[leaf.parent],x=leaf.x*width+dx,y=leaf.y*height+dy;
        const line=connections.querySelector(`[data-leaf-line="${leaf.id}"]`);
        line.setAttribute('d',`M ${parent.x/width*600} ${parent.y/height*600} L ${x/width*600} ${y/height*600}`);
        line.classList.toggle('is-active',leaf.parent===active);
      }
    }

    function draw(){
      if(width<1)return;ctx.clearRect(0,0,width,height);
      const dark=document.documentElement.dataset.theme==='dark';
      const {radius,x:cx,y:cy,outline}=globe;
      const glow=ctx.createRadialGradient(cx-radius*.3,cy-radius*.3,0,cx,cy,radius*1.25);
      glow.addColorStop(0,dark?'rgba(133,157,236,.12)':'rgba(75,108,225,.14)');
      glow.addColorStop(.6,dark?'rgba(131,155,226,.05)':'rgba(90,122,232,.06)');
      glow.addColorStop(1,'rgba(150,165,241,0)');
      ctx.fillStyle=glow;ctx.fillRect(0,0,width,height);
      const spotlight=paused||reduced.matches?0:influence;
      if(spotlight>.01){
        const spread=width*.21;
        const halo=ctx.createRadialGradient(mouse.x,mouse.y,0,mouse.x,mouse.y,spread);
        halo.addColorStop(0,dark?`rgba(213,240,255,${spotlight*.3})`:`rgba(142,190,255,${spotlight*.44})`);
        halo.addColorStop(.42,dark?`rgba(142,194,255,${spotlight*.18})`:`rgba(131,173,255,${spotlight*.24})`);
        halo.addColorStop(1,'rgba(151,172,255,0)');
        ctx.save();
        ctx.clip(outline);
        ctx.fillStyle=halo;
        ctx.fillRect(mouse.x-spread,mouse.y-spread,spread*2,spread*2);
        ctx.restore();
      }
      const rotation=angle+tiltX*.2,vertical=tiltY*.12;
      const projected=points.map(p=>{
        const x=p.x*Math.cos(rotation)+p.z*Math.sin(rotation);
        const z=-p.x*Math.sin(rotation)+p.z*Math.cos(rotation);
        const y=p.y*Math.cos(vertical)-z*Math.sin(vertical);
        const depth=p.y*Math.sin(vertical)+z*Math.cos(vertical);
        const perspective=1+depth*.1;
        const px=cx+x*radius*perspective,py=cy+(y*globeSquash+x*globeSkew)*radius*perspective;
        const displaced=motion.repel(px,py,mouse.x,mouse.y,width*.18,influence*width*.032*(depth+1)/2);
        return{x:displaced.x,y:displaced.y,z:depth,highlight:displaced.influence*spotlight};
      }).sort((a,b)=>a.z-b.z);
      projected.forEach((p,i)=>{
        const alpha=(dark?.35:.28)+(p.z+1)*(dark?.28:.30)+p.highlight*.38;
        const particleColor=dark?(p.z>0?'165,190,255':'125,150,225'):(p.z>0?'38,68,172':'65,92,182');
        const r=(dark?.65:.78)+(p.z+1)*(dark?.55:.65)+p.highlight*.9;
        if(p.highlight>.01){
          ctx.fillStyle=dark?`rgba(170,217,255,${p.highlight*.28})`:`rgba(88,138,234,${p.highlight*.22})`;
          ctx.beginPath();ctx.arc(p.x,p.y,r*(1+p.highlight*1.7),0,Math.PI*2);ctx.fill();
        }
        ctx.fillStyle=`rgba(${particleColor},${Math.min(1,alpha)})`;
        ctx.beginPath();ctx.arc(p.x,p.y,r,0,Math.PI*2);ctx.fill();
        if(p.highlight>.01){
          ctx.fillStyle=dark?`rgba(242,251,255,${p.highlight})`:`rgba(23,51,141,${p.highlight})`;
          ctx.fill();
        }
        if(p.z>.2&&i%6===0){
          for(let j=i+1;j<Math.min(i+12,projected.length);j++){
            const next=projected[j],dx=p.x-next.x,dy=p.y-next.y;
            if(dx*dx+dy*dy<width*width*.0022&&Math.abs(p.z-next.z)<.18){
              const lineAlpha=(dark?.16:.24)*p.z+p.highlight*.28;
              ctx.strokeStyle=dark?`rgba(165,192,255,${lineAlpha})`:`rgba(42,70,175,${lineAlpha})`;
              ctx.lineWidth=.75;
              ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(next.x,next.y);ctx.stroke();
            }
          }
        }
      });
      drawGraph();
    }

    function tick(time){
      frame=0;if(!canAnimate())return;
      const dt=last?Math.min((time-last)/1000,.05):1/60;last=time;angle+=dt*.032;
      const sx=motion.spring(tiltX,velocityX,targetX,dt),sy=motion.spring(tiltY,velocityY,targetY,dt);
      const si=motion.spring(influence,influenceVelocity,mouse.overGlobe?1:0,dt,mouse.overGlobe?.3:.42);
      tiltX=sx.position;velocityX=sx.velocity;tiltY=sy.position;velocityY=sy.velocity;
      influence=si.position;influenceVelocity=si.velocity;draw();frame=requestAnimationFrame(tick);
    }

    function sync(){
      cancelAnimationFrame(frame);frame=0;last=0;
      universe.classList.toggle('motion-paused',paused||reduced.matches);
      if(!canAnimate())clearSpotlight();
      if(reduced.matches){tiltX=0;tiltY=0;targetX=0;targetY=0;velocityX=0;velocityY=0;}
      draw();if(canAnimate())frame=requestAnimationFrame(tick);
    }

    universe.addEventListener('pointermove',event=>{
      if(event.pointerType!=='mouse'||!fine.matches||reduced.matches||paused)return;
      const rect=canvas.getBoundingClientRect();
      const x=event.clientX-rect.left,y=event.clientY-rect.top;
      if(ctx.isPointInPath(globe.outline,x*dpr,y*dpr)){
        mouse.x=x;mouse.y=y;
        mouse.overGlobe=true;
      }else{
        fadeSpotlight();
      }
      targetX=Math.max(-1,Math.min(1,(x/width-.5)*2));targetY=Math.max(-1,Math.min(1,(y/height-.5)*2));
    },{passive:true});
    universe.addEventListener('pointerleave',()=>{fadeSpotlight();targetX=0;targetY=0;hovered=null;drawGraph();});
    for(const node of nodes){
      node.el.addEventListener('pointerenter',event=>{if(event.pointerType==='mouse'&&fine.matches){hovered=node.id;drawGraph();}});
      node.el.addEventListener('pointerleave',()=>{hovered=null;drawGraph();});
      node.el.addEventListener('focus',()=>{focused=node.id;drawGraph();});
      node.el.addEventListener('blur',()=>{focused=null;drawGraph();});
      node.el.addEventListener('keydown',event=>{if(event.key==='Escape'){hovered=null;focused=null;drawGraph();node.el.blur();}});
    }
    toggle.addEventListener('click',()=>{
      paused=!paused;toggle.setAttribute('aria-pressed',String(paused));
      toggle.setAttribute('aria-label',paused?'播放背景动态效果':'暂停背景动态效果');
      toggle.innerHTML=`<span data-icon="${paused?'play':'pause'}"></span>`;window.XueyaIcons();sync();
    });
    new ResizeObserver(resize).observe(canvas);
    new IntersectionObserver(items=>{visible=items[0].isIntersecting;sync();},{threshold:.01}).observe(canvas);
    document.addEventListener('visibilitychange',sync);reduced.addEventListener('change',sync);
    fine.addEventListener('change',()=>{clearSpotlight();targetX=0;targetY=0;hovered=null;sync();});
    new MutationObserver(sync).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
    resize();sync();
  });
})();
