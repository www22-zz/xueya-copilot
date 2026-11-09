/* Deterministic teaching traces; no execution of user-supplied code. */
(() => {
  'use strict';
  const clone=value=>JSON.parse(JSON.stringify(value));
  function trace(kind){
    const steps=[],save=(state,note)=>steps.push({...clone(state),note});
    if(kind==='binary'){
      const a=[1,3,5,7,9,11,13],target=11;let left=0,right=a.length-1;
      save({a,left,right},'在有序数组中查找目标11');
      while(left<=right){const mid=Math.floor((left+right)/2);save({a,left,right,mid},`比较中点 a[${mid}]=${a[mid]} 与11`);
        if(a[mid]===target){save({a,left,right,mid,result:mid},`找到11，下标为${mid}`);break;}
        if(a[mid]<target)left=mid+1;else right=mid-1;
        save({a,left,right},'缩小仍可能包含目标的区间');}
    }else if(kind==='two-pointers'){
      const a=[1,2,3,4,6,8],target=10;let left=0,right=a.length-1;
      while(left<right){const sum=a[left]+a[right];save({a,left,right},`比较两端之和 ${a[left]}+${a[right]}=${sum}`);
        if(sum===target){save({a,left,right,result:[left,right]},'找到目标和10');break;}
        if(sum<target)left++;else right--;}
    }else if(kind==='bubble'){
      const a=[5,1,4,2,3];save({a},'通过相邻交换把较大元素移向右侧');
      for(let end=a.length-1;end>0;end--)for(let i=0;i<end;i++){
        save({a,left:i,right:i+1},`比较下标${i}和${i+1}`);
        if(a[i]>a[i+1]){[a[i],a[i+1]]=[a[i+1],a[i]];save({a,left:i,right:i+1},'逆序，交换两个元素');}}
      save({a,result:a},'排序完成');
    }else if(kind==='stack'){
      const a=[];for(const x of [1,2,3]){a.push(x);save({a},`入栈${x}，栈顶在右侧`);}
      while(a.length){const x=a.pop();save({a},`出栈${x}：后进先出`);}
      save({a,result:[]},'栈已清空');
    }else{
      const graph=[[1,2],[3],[3],[]],visited=new Set([0]),a=[0],order=[];
      save({a,visited:[...visited],order},'从节点0开始，邻接表：0→1,2；1→3；2→3；3无后继');
      while(a.length){const node=a.shift();order.push(node);save({a,visited:[...visited],order},`队头取出${node}`);
        for(const next of graph[node])if(!visited.has(next)){visited.add(next);a.push(next);save({a,visited:[...visited],order},`首次发现${next}，标记并入队`);}}
      save({a,visited:[...visited],order,result:order},'遍历完成，每个节点只访问一次');
    }
    return steps;
  }
  const names={binary:'二分查找','two-pointers':'双指针求和',bubble:'冒泡排序',stack:'栈的入栈与出栈',bfs:'广度优先搜索 BFS'};
  let timer=null;
  function mount(container,kind='binary'){
    clearInterval(timer);if(!names[kind])kind='binary';let index=0,speed=800,steps=trace(kind),playing=false;
    function stop(){clearInterval(timer);playing=false;}
    function render(){
      if(!container.isConnected){stop();return;}
      const step=steps[index];
      container.innerHTML=`<section class="panel"><h1>算法学习</h1><p>预设输入的可复现算法演示，观察每一步数据与指针变化。</p><a class="button button-outline" href="#space/practice/hot100">进入 Hot100 刷题</a>
        <label class="form-field">演示<select data-demo-kind>${Object.entries(names).map(([id,label])=>`<option value="${id}" ${id===kind?'selected':''}>${label}</option>`).join('')}</select></label>
        <h2>${names[kind]}</h2><p role="status">第${index+1}/${steps.length}步：${step.note}</p>
        <div style="display:flex;flex-wrap:wrap;gap:12px;padding:24px 0">${step.a.map((value,i)=>`<div style="padding:16px;border:2px solid ${i===step.left||i===step.right||i===step.mid?'var(--stitch-primary)':'var(--stitch-outline-variant)'};border-radius:10px;background:var(--stitch-surface-container)"><strong>${value}</strong><small style="display:block">下标${i}${i===step.left?' · L':''}${i===step.right?' · R':''}${i===step.mid?' · M':''}</small></div>`).join('')||'<p>当前为空</p>'}</div>
        ${step.order?`<p>访问顺序：${step.order.join(' → ')}</p>`:''}${step.visited?`<p>已发现节点：${step.visited.join(', ')}</p>`:''}
        ${step.result!==undefined?`<p>结果：${JSON.stringify(step.result)}</p>`:''}
        <div class="heading-actions"><button class="button button-blue" data-demo-play>${playing?'暂停':'播放'}</button><button class="button button-outline" data-demo-prev ${index===0?'disabled':''}>上一步</button><button class="button button-outline" data-demo-next ${index===steps.length-1?'disabled':''}>下一步</button><button class="button button-outline" data-demo-reset>重置</button></div>
        <label class="form-field">步进间隔<select data-demo-speed>${[300,800,1500].map(n=>`<option value="${n}" ${speed===n?'selected':''}>${n}毫秒</option>`).join('')}</select></label></section>`;
      container.querySelector('[data-demo-kind]').onchange=event=>{stop();mount(container,event.target.value);};
      container.querySelector('[data-demo-play]').onclick=()=>{if(playing){stop();render();}else{if(index===steps.length-1)index=0;playing=true;timer=setInterval(()=>{if(index<steps.length-1)index++;else stop();render();},speed);render();}};
      container.querySelector('[data-demo-prev]').onclick=()=>{stop();index=Math.max(0,index-1);render();};
      container.querySelector('[data-demo-next]').onclick=()=>{stop();index=Math.min(steps.length-1,index+1);render();};
      container.querySelector('[data-demo-reset]').onclick=()=>{stop();index=0;render();};
      container.querySelector('[data-demo-speed]').onchange=event=>{speed=Number(event.target.value);stop();render();};
    }
    render();
  }
  window.XueyaAlgorithmDemo={mount,trace};
})();
