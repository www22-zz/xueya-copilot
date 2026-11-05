/* Course bookshelf and document/concept hierarchy; no provider calls on GET. */
(() => {
  const e=window.XueyaRich.escape;
  const messageFor=code=>({AI_CONNECTION_FAILED:'当前服务无法连接模型站点，未提交新批次。请检查服务启动环境或网络。',JOB_FAILED:'请求异常，尚无可核验结果；请先核对连接和调用账本。'}[code]||code);
  let epoch=0,timer,host,data,documentId='',conceptId='',filter='';
  async function api(course,body){
    const r=await window.XueyaPlatform.spaceFetch('/api/learning/space/course-graph'+(body?'/continue':'?courseId='+encodeURIComponent(course)),body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,courseId:course})}:{});
    const value=await r.json();if(!r.ok||!value.ok)throw Error(value.error||'图谱读取失败');return value;
  }
  async function mount(target,course,reference){
    const stamp=++epoch;clearTimeout(timer);host=target;
    target.innerHTML='<p role="status">正在读取课程书架与知识图谱…</p>';
    async function load(){
      try{const next=await api(course);if(stamp!==epoch||!target.isConnected)return;data=next;
        if(reference){const node=data.nodes.find(n=>n.references?.some(r=>r.materialId===reference));if(node){conceptId=node.id;documentId=node.references[0].documentId;}reference=null;}
        if(!target.querySelector('[data-quiz-card]')&&!target.querySelector('details[open]'))draw();if(data.coverage.pendingJobs)timer=setTimeout(load,8000);
      }catch(error){if(stamp===epoch)target.innerHTML=`<p role="alert">${e(messageFor(error.message))}</p>`;}
    }
    function draw(){
      if(stamp!==epoch||!target.isConnected)return;
      const subjects=[...new Set(data.documents.filter(d=>d.ready).map(d=>d.subject))];
      const books=data.documents.filter(d=>d.ready&&(!filter||d.subject===filter));
      const book=books.find(d=>d.id===documentId)||books[0];documentId=book?.id||'';
      const concepts=data.nodes.filter(n=>n.kind==='concept'&&data.edges.some(edge=>edge.source===documentId&&edge.target===n.id));
      const concept=concepts.find(n=>n.id===conceptId)||concepts[0];conceptId=concept?.id||'';
      const c=data.coverage;
      target.innerHTML=`<h2>课程书架与知识图谱</h2><p>根据当前可访问的真实资料组织。先选科目与资料，再选知识点进入练习。</p>
        <label class="form-field">科目<select data-cg-subject><option value="">全部已有科目</option>${subjects.map(s=>`<option ${s===filter?'selected':''}>${e(s)}</option>`).join('')}</select></label>
        <div class="cg-books">${books.map(d=>`<button type="button" data-cg-book="${e(d.id)}" aria-pressed="${d.id===documentId}"><span>${e(d.subject)}</span><strong>${e(d.name)}</strong><small>${d.ranges}个待覆盖输入范围</small></button>`).join('')||'<p>暂无可信解析资料，请先上传并完成解析。示例记录不作为书架内容。</p>'}</div>
        <section class="cg-coverage"><strong>整门课程提取进度：${c.completedRanges}/${c.totalRanges}批</strong><p>${c.questions}道去重关联题 · ${c.pendingJobs}批处理中 · ${data.blocked.length}批需核对 · ${c.unreadyDocuments}份未就绪。${c.inputComplete?'当前可信输入均已处理，知识点完整性仍待审校。':'首批图谱仍可使用；其余原文尚待分批提取。'}连线仅表示包含关系。</p>
        <details><summary>补齐剩余原文（会调用外部模型）</summary><p>剩余${c.remainingCalls}批未提交，每批最多一次请求；每次最多50批，成功批次复用，失败或状态未知不自动重试。请求只使用当前权限内资料。</p><label>本次最多调用次数<input data-cg-limit type="number" min="1" max="50" value="10"></label><label><input type="checkbox" data-cg-consent>同意将所选范围发送给配置的外部模型并产生费用</label><button class="button button-outline" data-cg-continue ${!c.remainingCalls||!data.available?'disabled':''}>继续提取</button><p data-cg-message role="status"></p>${data.blocked.map(b=>`<p>需核对：${e(messageFor(b.error||b.status))}。不会自动重放。</p>`).join('')}</details></section>
        <div class="cg-map"><h3>${e(book?.name||'暂无资料')}</h3><div class="cg-concepts">${concepts.map(n=>`<button type="button" data-cg-concept="${e(n.id)}" aria-pressed="${n.id===conceptId}">${e(n.label)}<small>${n.questionIds.length}道题 · ${n.references.length}处来源</small></button>`).join('')||'<p>此资料尚无已保存知识点，可在上方补齐提取。不会展示虚构节点。</p>'}</div></div>
        ${concept?`<section class="cg-detail"><h3>${e(concept.label)}</h3><p>${e(concept.descriptions[0]||'')}</p><p>来源：${concept.references.map(r=>e(data.documents.find(d=>d.id===r.documentId)?.name||'资料')+(r.page?' · 第'+e(r.page)+'页':' · 页码未提供')).join('；')}</p><button class="button button-blue" data-cg-practice>练习此知识点（${concept.questionIds.length}题）</button><p>视频：尚未核验此知识点的精确分集，可切换到视频目录查看本科目课程入口。</p><div data-cg-questions></div></section>`:''}`;
      target.querySelector('[data-cg-subject]').onchange=event=>{filter=event.target.value;draw();};
      target.querySelectorAll('[data-cg-book]').forEach(b=>b.onclick=()=>{documentId=b.dataset.cgBook;conceptId='';draw();});
      target.querySelectorAll('[data-cg-concept]').forEach(b=>b.onclick=()=>{conceptId=b.dataset.cgConcept;draw();});
      target.querySelector('[data-cg-practice]')?.addEventListener('click',()=>{const box=target.querySelector('[data-cg-questions]');box.innerHTML=concept.questionIds.map(id=>`<section class="study-quiz-card panel" data-quiz-card="${e(id)}"></section>`).join('');window.XueyaStudyQuiz.mount(box);clearTimeout(timer);});
      target.querySelector('[data-cg-continue]').onclick=async()=>{const message=target.querySelector('[data-cg-message]');if(!target.querySelector('[data-cg-consent]').checked){message.textContent='请先确认外发和费用。';return;}try{const result=await api(course,{confirmedExternal:true,callLimit:Number(target.querySelector('[data-cg-limit]').value),subject:filter});message.textContent=`已提交${result.jobIds.length}批，可离开，后台继续处理。`;clearTimeout(timer);timer=setTimeout(load,8000);}catch(error){message.textContent=messageFor(error.message);}};
    }
    await load();
  }
  window.XueyaCourseGraph={mount,unmount(){epoch++;clearTimeout(timer);host=null;}};
})();
