/* Small, deterministic motion primitives; no animation dependency. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.XueyaMotion=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  function spring(position,velocity,target,seconds,response=.3){
    const dt=Math.max(0,Math.min(seconds,.05));
    const omega=2*Math.PI/response;
    const offset=position-target;
    const coefficient=velocity+omega*offset;
    const decay=Math.exp(-omega*dt);
    return {
      position:target+(offset+coefficient*dt)*decay,
      velocity:(velocity-omega*coefficient*dt)*decay
    };
  }

  function repel(x,y,pointerX,pointerY,radius,strength=12){
    const dx=x-pointerX,dy=y-pointerY,distance=Math.hypot(dx,dy);
    if(distance>=radius)return{x,y,influence:0};
    const influence=(1-distance/radius)**2;
    const direction=distance>0?1/distance:0;
    return {
      x:x+(distance>0?dx*direction:1)*strength*influence,
      y:y+dy*direction*strength*influence,
      influence
    };
  }

  return{spring,repel};
});
