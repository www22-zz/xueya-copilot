/* Standalone deterministic demonstration; no evaluation of user code. */
(() => {
  const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const root=document.querySelector('#lab'),id=new URLSearchParams(location.search).get('question');
  let data,index=0,timer=null,speed=700,angle=-30,tilt=55,zoom=1,request=0;
  const stop=()=>{clearInterval(timer);timer=null;const b=document.querySelector('[data-play]');if(b)b.textContent='播放';};
  async function load(sample=0){stop();const stamp=++request;try{const boot=await fetch('/api/platform/bootstrap').then(r=>r.json());const r=await fetch('/api/learning/space/algorithm-demo/'+encodeURIComponent(id)+'?sample='+sample,{headers:{'X-Xueya-Token':boot.token}});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'题目读取失败');if(stamp!==request)return;data=d.demo;index=0;render();}catch(error){root.innerHTML='<p role="alert">无法打开本题演示：'+e(error.message)+'</p><a href="/#space/practice/hot100">返回 Hot100</a>';}}
  function render(){
    const dfs=!!data.inputs.grid;
    root.innerHTML=`<header><div><span class="eyebrow">学涯 / 算法交互实验室</span><h1>#${data.number} ${e(data.title)}</h1><p>原题示例 · 确定性教学步骤 · ${dfs?'DFS 深入与回溯':'二分下界查找'}</p></div><a href="/#space/practice/hot100/${e(id)}">返回原题 ↗</a></header><div class="example"><label>原题示例 <select data-sample>${Array.from({length:data.sampleCount},(_,i)=>`<option value="${i}" ${i===data.sampleIndex?'selected':''}>示例 ${i+1}</option>`).join('')}</select></label><code>${e(data.sample.input)}</code><strong>预期输出 ${e(data.sample.output)}</strong></div><div class="lab-layout"><section class="stage-area"><div class="stage-title"><span>${dfs?'3D 网格 · 四方向相邻':'搜索区间 · [left, right)'}</span><span>${dfs?'拖动旋转 · 滚轮缩放':''}</span></div><div class="stage" data-stage><div data-scene class="${dfs?'grid-scene':'array-scene'}"></div></div><div class="legend"><span>🟨 当前 / 中点</span><span>🟩 已访问 / 左边界</span><span>🟦 未访问 / 右边界</span><span>灰色：水域 / 排除</span></div><div class="controls"><button data-prev>上一步</button><button data-play>播放</button><button data-next>下一步</button><button data-reset>重置</button><label>速度 <select data-speed><option value="1400">慢</option><option value="700" selected>标准</option><option value="250">快</option></select></label></div></section><aside><p class="eyebrow">执行轨迹</p><h2 data-note></h2><p data-step></p><pre data-variables></pre><ol class="code">${data.code.map((line,i)=>`<li data-line="${i+1}"><code>${e(line)}</code></li>`).join('')}</ol><p class="footnote">演示解释选定解法，不运行用户提交的代码。</p></aside></div>`;
    root.querySelector('[data-sample]').onchange=ev=>load(Number(ev.target.value));
    root.querySelector('[data-prev]').onclick=()=>{stop();index=Math.max(0,index-1);draw();};
    root.querySelector('[data-next]').onclick=()=>{stop();index=Math.min(data.steps.length-1,index+1);draw();};
    root.querySelector('[data-play]').onclick=()=>{if(timer){stop();return;}if(index===data.steps.length-1)index=0;timer=setInterval(()=>{index++;draw();if(index===data.steps.length-1)stop();},speed);root.querySelector('[data-play]').textContent='暂停';};
    root.querySelector('[data-reset]').onclick=()=>{stop();index=0;angle=-30;tilt=55;zoom=1;draw();};
    root.querySelector('[data-speed]').value=String(speed);root.querySelector('[data-speed]').onchange=ev=>{stop();speed=Number(ev.target.value);};
    const stage=root.querySelector('[data-stage]');let drag;
    if(dfs){stage.onpointerdown=ev=>{drag=[ev.clientX,ev.clientY,angle,tilt];stage.setPointerCapture(ev.pointerId);};stage.onpointermove=ev=>{if(drag){angle=drag[2]+(ev.clientX-drag[0])*.4;tilt=Math.max(15,Math.min(75,drag[3]-(ev.clientY-drag[1])*.3));pose();}};stage.onpointerup=stage.onpointercancel=()=>drag=null;stage.onwheel=ev=>{ev.preventDefault();zoom=Math.max(.5,Math.min(1.6,zoom-ev.deltaY*.001));pose();};}
    draw();
  }
  function pose(){const scene=root.querySelector('.grid-scene');if(scene)scene.style.transform=`translate(-50%,-50%) rotateX(${tilt}deg) rotateZ(${angle}deg) scale(${zoom})`;}
  function draw(){
    const s=data.steps[index],scene=root.querySelector('[data-scene]');
    root.querySelector('[data-note]').textContent=s.note;root.querySelector('[data-step]').textContent=`第 ${index+1} / ${data.steps.length} 步`;
    root.querySelector('[data-prev]').disabled=index===0;root.querySelector('[data-next]').disabled=index===data.steps.length-1;
    root.querySelectorAll('[data-line]').forEach(n=>n.classList.toggle('active',Number(n.dataset.line)===s.line));
    if(data.inputs.grid){const grid=data.inputs.grid;scene.style.width=grid[0].length*64+'px';scene.style.height=grid.length*64+'px';scene.innerHTML=grid.flatMap((row,r)=>row.map((v,c)=>{const current=s.current?.[0]===r&&s.current?.[1]===c,visited=s.visited.some(p=>p[0]===r&&p[1]===c);return `<div class="cube ${v==='0'?'water':current?'current':visited?'visited':'land'}" style="left:${c*64}px;top:${r*64}px"><div class="top">${r},${c}</div><div class="front"></div><div class="side"></div></div>`;})).join('');pose();root.querySelector('[data-variables]').textContent='岛屿计数：'+s.count+'\n递归栈（栈顶在下）：\n'+(s.stack.map(p=>'dfs('+p.join(', ')+')').join('\n')||'空栈');if(!CSS.supports('transform-style','preserve-3d'))scene.innerHTML='<p>浏览器不支持三维变换；请用支持 CSS 3D 的浏览器。右侧仍可查看步骤。</p>';}
    else{scene.innerHTML=data.inputs.nums.map((n,i)=>`<div class="array-cell ${i<s.left||i>=s.right?'excluded':''} ${i===s.mid?'current':''}"><small>${i===s.left?'L ':''}${i===s.right?'R ':''}${i===s.mid?'M':''}</small><strong>${n}</strong><span>${i}</span></div>`).join('')+`<div class="array-cell endpoint"><small>${s.right===data.inputs.nums.length?'R':''}${s.left===data.inputs.nums.length?' L':''}</small><strong>∅</strong><span>${data.inputs.nums.length}</span></div>`;root.querySelector('[data-variables]').textContent=`target = ${data.inputs.target}\nleft = ${s.left}\nright = ${s.right}\nmid = ${s.mid??'—'}`;}
  }
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});window.addEventListener('pagehide',()=>{stop();request++;});load();
})();
