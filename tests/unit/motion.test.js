const test=require('node:test');
const assert=require('node:assert/strict');
const {spring,repel}=require('../../frontend/js/motion.js');

test('critically damped pointer motion settles and can retarget without teleporting',()=>{
  let position=0,velocity=0;
  for(let i=0;i<30;i++){
    const next=spring(position,velocity,100,1/60);
    assert.ok(next.position>=position&&next.position<=100);
    position=next.position;velocity=next.velocity;
  }
  assert.ok(Math.abs(position-100)<.1);
  const reversed=spring(position,velocity,0,1/60);
  assert.ok(reversed.position>80&&reversed.position<position);
  assert.ok(Number.isFinite(reversed.velocity));
  assert.deepEqual(spring(50,0,50,1/60),{position:50,velocity:0});
});

test('particle response is local, bounded and safe at the exact pointer position',()=>{
  const near=repel(20,0,0,0,100,12),far=repel(80,0,0,0,100,12);
  assert.ok(near.x-20>far.x-80);
  assert.ok(near.x-20<=12);
  assert.deepEqual(repel(150,0,0,0,100,12),{x:150,y:0,influence:0});
  const center=repel(0,0,0,0,100,12);
  assert.ok(Number.isFinite(center.x)&&Number.isFinite(center.y));
  assert.ok(Math.hypot(center.x,center.y)<=12);
});
