/* Source-backed course books and interactive mind maps. No model calls on read. */
(() => {
  'use strict';
  const e = window.XueyaRich.escape;
  const messageFor = code => ({AI_CONNECTION_FAILED:'当前服务无法连接模型站点，未提交新批次。请检查服务启动环境或网络。',JOB_FAILED:'请求异常，尚无可核验结果；请先核对连接和调用账本。'}[code] || code);
  const titleOf = name => name.replace(/\.[a-z0-9]+$/i, '').replace(/^week\d+[\s_-]*/i, '').replace(/[_-]+/g, ' ').trim();
  let epoch = 0, timer;

  async function api(course, body) {
    const response = await window.XueyaPlatform.spaceFetch('/api/learning/space/course-graph' + (body ? '/continue' : '?courseId=' + encodeURIComponent(course)), body ? {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...body, courseId:course})
    } : {});
    const value = await response.json();
    if (!response.ok || !value.ok) throw Error(value.error || '图谱读取失败');
    return value;
  }

  async function mount(target, course, reference, directory=false) {
    const stamp = ++epoch;
    clearTimeout(timer);
    let data, signature = '', subject = '', filter = '', focusedDocument = '', selected = 'course', search = '', page = 0;
    let viewport, viewportKey = '', courses = [], videoError = false, submitting = false;
    let concepts = new Map(), children = new Map(), subjects = [];
    const stateKey=(window.XueyaDataKey||((k)=>k))('course-graph-view:'+course);
    try{const old=JSON.parse(sessionStorage.getItem(stateKey)||'{}');subject=old.subject||'';focusedDocument=old.focusedDocument||'';selected=old.selected||'course';page=old.page||0;viewport=old.viewport;viewportKey=old.viewportKey||'';}catch{}
    const remember=()=>sessionStorage.setItem(stateKey,JSON.stringify({subject,focusedDocument,selected,page,viewport,viewportKey}));
    const alive = () => stamp === epoch && target.isConnected;
    target.innerHTML = '<p role="status">正在读取课程书架…</p>';
    const chapterNumber = text => {
      if (/^\d+$/.test(text)) return Number(text);
      const digits={'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'两':2};
      if (text.includes('十')) { const [a,b]=text.split('十'); return (digits[a]||1)*10+(digits[b]||0); }
      return digits[text] ?? Infinity;
    };
    const orderOf = d => {
      const chapter=d.name.match(/第\s*([0-9零一二三四五六七八九十两]+)\s*章/);
      const part=d.name.match(/[（(]\s*(\d+)\s*[）)]/);
      const week=d.name.match(/week\s*(\d+)/i);
      return [chapter?chapterNumber(chapter[1]):Infinity,part?Number(part[1]):0,week?Number(week[1]):Infinity];
    };
    const documents = () => data.documents.filter(d => d.ready && (!subject || d.subject === subject)).sort((a,b)=>{
      const aa=orderOf(a),bb=orderOf(b);
      for(let i=0;i<aa.length;i++)if(aa[i]!==bb[i])return aa[i]<bb[i]?-1:1;
      return a.name.localeCompare(b.name,'zh-CN',{numeric:true});
    });
    const pointsFor = docs => [...new Map(docs.flatMap(d => children.get(d.id) || []).map(n => [n.id, n])).values()];
    const questionCount = nodes => new Set(nodes.flatMap(n => n.questionIds)).size;
    const openDocument = id => { focusedDocument = id; selected = id; page = 0; search = ''; draw(); };
    const chooseConcept = id => { selected = id; remember(); updateSelection(); drawDetail(); };

    function index() {
      concepts = new Map(data.nodes.filter(n => n.kind === 'concept').map(n => [n.id, n]));
      children = new Map(data.documents.map(d => [d.id, []]));
      for (const edge of data.edges) if (concepts.has(edge.target) && children.has(edge.source)) children.get(edge.source).push(concepts.get(edge.target));
      subjects = [...new Set(data.documents.filter(d => d.ready).map(d => d.subject))];
      if (subject && !subjects.includes(subject)) { subject = ''; selected = 'course'; }
      if (focusedDocument && !documents().some(d => d.id === focusedDocument)) focusedDocument = '';
    }
    function schedule() {
      clearTimeout(timer);
      if (alive() && data?.coverage.pendingJobs) timer = setTimeout(() => document.hidden ? schedule() : load(), 8000);
    }
    async function load() {
      try {
        const next = await api(course);
        if (!alive()) return;
        const nextSignature = JSON.stringify(next);
        data = next; index();
        if (reference) {
          const node = data.nodes.find(n => n.references?.some(r => r.materialId === reference));
          const doc = data.documents.find(d => d.id === node?.references.find(r => r.materialId === reference)?.documentId);
          if (doc?.ready) { subject = doc.subject; focusedDocument = doc.id; selected = node.id; }
          reference = null;
        }
        const busy = target.querySelector('[data-quiz-card], details[open]') || (target.contains(document.activeElement) && document.activeElement.matches('input,textarea,select'));
        if (nextSignature !== signature && !busy) { signature = nextSignature; draw(); }
        schedule();
      } catch (error) {
        if (!alive()) return;
        const status = target.querySelector('[data-cg-load-status]');
        if (status) status.textContent = '更新暂不可用，当前内容已保留。' + messageFor(error.message);
        else target.innerHTML = `<p role="alert">${e(messageFor(error.message))}</p>`;
      }
    }

    function coverage() {
      const c = data.coverage;
      return `<details class="cg-coverage"><summary>资料生成进度 · 已处理 ${c.completedRanges}/${c.totalRanges} 批${c.pendingJobs ? ' · 正在处理 ' + c.pendingJobs + ' 批' : ''}</summary>
        <p>${c.questions}道已保存题 · ${data.blocked.length}批需核对 · ${c.unreadyDocuments}份未就绪。${c.inputComplete ? '当前可信输入均已处理，知识完整性仍待审校。' : '导图展示已保存的知识点，尚未覆盖全部资料。'}AI题目未经独立审校。</p>
        <details><summary>继续提取（调用外部模型）</summary><p>当前账号全部可访问资料还有${c.remainingCalls}批未提交。${subject || filter ? '本次仅提交“' + e(subject || filter) + '”范围内尚未开始的批次。' : ''}每批最多一次请求，成功批次复用，失败或状态未知不自动重试。</p>
        <label>本次最多调用次数 <input data-cg-limit type="number" min="1" max="50" value="10"></label>
        <label><input type="checkbox" data-cg-consent> 同意将所选范围发送给配置的外部模型并产生费用</label>
        <button type="button" class="button button-outline" data-cg-continue ${!c.remainingCalls || !data.available || submitting ? 'disabled' : ''}>继续提取</button><p data-cg-message role="status"></p>
        ${data.blocked.map(b => `<p>需核对：${e(messageFor(b.error || b.status))}。不会自动重放。</p>`).join('')}</details></details>`;
    }
    function draw() {
      if (!alive()) return;
      if (!subject) drawShelf(); else drawMap();
      remember();
      target.insertAdjacentHTML('beforeend', coverage() + '<p data-cg-load-status role="status"></p>');
      target.querySelector('[data-cg-continue]').onclick = async event => {
        const button = event.currentTarget, message = target.querySelector('[data-cg-message]');
        const limit = Number(target.querySelector('[data-cg-limit]').value);
        if (!target.querySelector('[data-cg-consent]').checked) { message.textContent = '请先确认外发和费用。'; return; }
        if (!Number.isInteger(limit) || limit < 1 || limit > 50) { message.textContent = '调用次数须为1至50之间的整数。'; return; }
        if (submitting) return;
        submitting = true; button.disabled = true;
        try {
          const result = await api(course, {confirmedExternal:true, callLimit:limit, subject:subject || filter});
          if (alive()) { message.textContent = `已提交${result.jobIds.length}批，可离开，后台继续处理。`; clearTimeout(timer); timer = setTimeout(load, 8000); }
        } catch (error) { if (alive()) message.textContent = messageFor(error.message); }
        finally { submitting = false; if (alive()) button.disabled = false; }
      };
    }

    function drawShelf() {
      const books = subjects.filter(s => !filter || s === filter);
      target.innerHTML = `<div class="cg-shelf-heading"><div><span class="cg-eyebrow">我的课程书架</span><h2>把一门课，读成一张知识地图</h2><p>每本课程书汇集同一科目的已有资料。点击封面，打开思维导图。</p></div>
        <label class="form-field">科目<select data-cg-subject><option value="">全部已有科目</option>${subjects.map(s => `<option ${s === filter ? 'selected' : ''}>${e(s)}</option>`).join('')}</select></label></div>
        <div class="cg-books">${books.map((s, i) => {
          const docs = data.documents.filter(d => d.ready && d.subject === s), nodes = pointsFor(docs);
          return `<button type="button" class="cg-book" data-cg-book="${e(s)}" aria-label="打开${e(s)}思维导图" style="--book-hue:${[250,200,155,320][i % 4]}">
            <span class="cg-book-cover"><span class="cg-book-edition">课程知识手册 <span>LEARNING ATLAS</span></span><strong>${e(s)}</strong><span class="cg-book-subtitle">从资料出发 · 串联知识与练习</span>
            <svg class="cg-cover-art" viewBox="0 0 240 160" aria-hidden="true"><path d="M120 84 48 36M120 84 194 40M120 84 58 134M120 84 194 128M48 36 18 76M194 40 224 78"/><circle cx="120" cy="84" r="26"/><circle cx="48" cy="36" r="14"/><circle cx="194" cy="40" r="18"/><circle cx="58" cy="134" r="18"/><circle cx="194" cy="128" r="13"/><circle cx="18" cy="76" r="6"/><circle cx="224" cy="78" r="7"/></svg>
            <span class="cg-book-footer">${docs.length}份资料汇编 <span>打开导图 ↗</span></span></span>
            <span class="cg-book-caption"><strong>${e(s)}</strong><small data-cg-count>${nodes.length}个知识点 · ${questionCount(nodes)}道题</small><small>${nodes.length ? '已有部分知识内容 · 可进入学习' : '资料已就绪 · 知识点尚待生成'}</small></span></button>`;
        }).join('') || '<p class="cg-empty">暂无可信解析资料。上传并完成解析后，这里会出现对应的课程书。</p>'}</div>`;
      target.querySelector('[data-cg-subject]').onchange = event => { filter = event.target.value; draw(); };
      target.querySelectorAll('[data-cg-book]').forEach(button => button.onclick = () => {
        subject = button.dataset.cgBook; focusedDocument = ''; selected = 'course'; page = 0; search = ''; draw();
        target.querySelector('[data-cg-back]').focus({preventScroll:true});
      });
    }
    function drawMap() {
      const docs = documents(), nodes = pointsFor(docs), doc = docs.find(d => d.id === focusedDocument);
      if (!concepts.has(selected) && selected !== 'course' && !docs.some(d => d.id === selected)) selected = doc?.id || 'course';
      target.innerHTML = `<section class="cg-reader"><div class="cg-reader-heading"><button type="button" class="button button-outline" data-cg-back>← 返回书架</button><div><span class="cg-eyebrow">${e(subject)} / 知识图谱</span><h2>${e(doc ? titleOf(doc.name) : subject)}</h2></div><span class="cg-reader-count">${docs.length}份资料 · ${nodes.length}个知识点 · ${questionCount(nodes)}道题</span></div>
        <div class="cg-reader-layout"><div class="cg-map-area"><div class="cg-map-toolbar"><button class="button button-outline" data-cg-overview ${!doc ? 'disabled' : ''}>课程总览</button><button class="button button-outline" data-cg-zoom="0.8" aria-label="放大导图">＋</button><button class="button button-outline" data-cg-zoom="1.25" aria-label="缩小导图">−</button><button class="button button-outline" data-cg-fit>适应画布</button><label class="cg-search">查找知识点<input type="search" data-cg-search placeholder="输入名称" value="${e(search)}"></label></div>
        <div class="cg-search-results" data-cg-results></div><div class="cg-map" data-cg-map></div>
        <p class="cg-map-legend"><span>● 课程 / 资料</span><span>○ 已提取知识点</span><span>点击节点查看详情 · 拖动画布 · 连线表示包含关系</span></p></div>
        <aside class="cg-detail" data-cg-detail aria-label="节点详情"></aside></div><div data-cg-questions></div></section>`;
      target.querySelector('[data-cg-back]').onclick = () => { const previous = subject; subject = ''; draw(); target.querySelectorAll('[data-cg-book]').forEach(b => { if (b.dataset.cgBook === previous) b.focus({preventScroll:true}); }); };
      target.querySelector('[data-cg-overview]').onclick = () => { focusedDocument = ''; selected = 'course'; page = 0; draw(); };
      target.querySelector('[data-cg-search]').oninput = event => { search = event.target.value; drawSearch(); };
      drawCanvas(); drawSearch(); drawDetail();
      if(directory){const map=target.querySelector('.cg-map-area');map.innerHTML='<h3>章节与知识点目录</h3>'+docs.map(d=>`<details open><summary>${e(titleOf(d.name))}</summary>${(children.get(d.id)||[]).map(n=>`<button type="button" class="button button-outline" data-directory-node="${e(n.id)}">${e(n.label)} · ${n.questionIds.length}题</button>`).join('')||'<p>待补充资料或尚未生成题目</p>'}</details>`).join('');map.querySelectorAll('[data-directory-node]').forEach(b=>b.onclick=()=>chooseConcept(b.dataset.directoryNode));}
    }
    function drawSearch() {
      const box = target.querySelector('[data-cg-results]');
      if (!box) return;
      const term = search.trim().toLocaleLowerCase(), matches = pointsFor(documents()).filter(n => n.label.toLocaleLowerCase().includes(term));
      box.innerHTML = term ? (matches.slice(0, 30).map(n => `<button type="button" data-cg-result="${e(n.id)}">${e(n.label)}</button>`).join('') || '<p>没有匹配的已保存知识点。</p>') : '';
      box.querySelectorAll('[data-cg-result]').forEach(b => b.onclick = () => {
        const n = concepts.get(b.dataset.cgResult), ref = n.references.find(r => documents().some(d => d.id === r.documentId));
        focusedDocument = ref.documentId; selected = n.id; page = Math.floor((children.get(ref.documentId) || []).findIndex(c => c.id === n.id) / 24); search = ''; draw();
      });
    }

    function drawCanvas() {
      const docs = documents(), doc = docs.find(d => d.id === focusedDocument);
      const all = doc ? children.get(doc.id) || [] : pointsFor(docs);
      // Large courses expand one source at a time, instead of overlapping labels.
      const overviewOnly = !doc && all.length > 40;
      const items = doc ? all.slice(page * 24, (page + 1) * 24) : overviewOnly ? [] : all;
      const positions = new Map(), edges = [], nodeRows = [];
      const add = (id, label, kind, x, y, radius, count) => { const n = {id, label, kind, x, y, radius, count}; positions.set(id, n); nodeRows.push(n); };
      const root = doc?.id || 'course';
      add(root, doc ? titleOf(doc.name) : subject, 'root', 0, 0, 70, doc ? all.length + '个知识点' : docs.length + '份资料');
      const radius = doc ? Math.max(210, items.length * 108 / (2 * Math.PI)) : overviewOnly ? Math.max(215, docs.length * 140 / (2 * Math.PI)) : Math.max(350, (items.length + docs.length) * 108 / (2 * Math.PI));
      if (doc) items.forEach((n, i) => {
        const angle = -Math.PI / 2 + i * 2 * Math.PI / items.length;
        add(n.id, n.label, 'concept', Math.cos(angle) * radius, Math.sin(angle) * radius, 47, n.questionIds.length + '题'); edges.push([root, n.id]);
      });
      else {
        const owned = new Set(), groups = docs.map(d => ({doc:d, nodes:items.filter(n => {
          if (owned.has(n.id) || !children.get(d.id)?.some(c => c.id === n.id)) return false;
          owned.add(n.id); return true;
        })}));
        const slots = groups.reduce((sum, g) => sum + Math.max(1, g.nodes.length) + 1, 0);
        let offset = 0;
        for (const group of groups) {
          const weight = Math.max(1, group.nodes.length), angle = -Math.PI / 2 + (offset + weight / 2) / slots * 2 * Math.PI;
          const innerRadius = overviewOnly ? radius : Math.max(195, radius * .51);
          add(group.doc.id, titleOf(group.doc.name), 'document', Math.cos(angle) * innerRadius, Math.sin(angle) * innerRadius, 56, (children.get(group.doc.id)?.length || 0) + '个知识点');
          edges.push(['course', group.doc.id]);
          group.nodes.forEach((n, i) => {
            const a = -Math.PI / 2 + (offset + i + .5) / slots * 2 * Math.PI;
            add(n.id, n.label, 'concept', Math.cos(a) * radius, Math.sin(a) * radius, 47, n.questionIds.length + '题');
          });
          offset += weight + 1;
        }
        for (const edge of data.edges) if (positions.has(edge.source) && positions.has(edge.target) && edge.source !== 'course') edges.push([edge.source, edge.target]);
      }
      const extent = Math.max(290, radius + 95), base = [-extent, -extent, extent * 2, extent * 2];
      const key = subject + '/' + focusedDocument + '/' + page + '/' + items.length;
      if (viewportKey !== key) { viewport = base.slice(); viewportKey = key; }
      const labels = n => {
        const perLine = n.kind === 'root' ? 8 : n.kind === 'document' ? 7 : 6;
        const chars = Array.from(n.label), rows = [];
        for (let i = 0; i < Math.min(chars.length, perLine * 3); i += perLine) rows.push(chars.slice(i, i + perLine).join(''));
        if (chars.length > perLine * 3) rows[2] = rows[2].slice(0, -1) + '…';
        return rows.map((line, i) => `<tspan x="0" y="${-(rows.length - 1) * 8 - 5 + i * 16}">${e(line)}</tspan>`).join('');
      };
      target.querySelector('[data-cg-map]').innerHTML = `<svg class="cg-mindmap" viewBox="${viewport.join(' ')}" role="group" aria-label="${e(subject)}思维导图">
        <g class="cg-edges">${edges.map(([a, b]) => { const from = positions.get(a), to = positions.get(b); return `<line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}"/>`; }).join('')}</g>
        ${nodeRows.map(n => `<g class="cg-node cg-node-${n.kind}" data-cg-node="${e(n.id)}" ${n.kind === 'concept' ? 'data-cg-concept="' + e(n.id) + '"' : ''} transform="translate(${n.x} ${n.y})" role="button" tabindex="0" aria-label="${e(n.label)}，${e(n.count)}" aria-pressed="${selected === n.id}"><title>${e(n.label)}</title><circle class="cg-node-ring" r="${n.radius + 5}"/><circle r="${n.radius}"/><text text-anchor="middle">${labels(n)}<tspan class="cg-node-count" x="0" y="${n.radius - 12}">${e(n.count)}</tspan></text></g>`).join('')}</svg>
        ${!all.length ? '<p class="cg-map-notice">资料已就绪，知识点尚待生成。此处没有添加占位知识点。</p>' : overviewOnly ? '<p class="cg-map-notice">知识点较多，点击资料节点展开对应章节。</p>' : ''}
        ${doc && all.length > 24 ? `<div class="cg-map-pages"><button class="button button-outline" data-cg-prev ${!page ? 'disabled' : ''}>上一组</button><span>${page * 24 + 1}–${Math.min((page + 1) * 24, all.length)} / ${all.length}个知识点</span><button class="button button-outline" data-cg-next ${(page + 1) * 24 >= all.length ? 'disabled' : ''}>下一组</button></div>` : ''}`;
      const svg = target.querySelector('.cg-mindmap');
      const apply = () => {svg.setAttribute('viewBox', viewport.join(' '));remember();};
      target.querySelectorAll('[data-cg-zoom]').forEach(b => b.onclick = () => {
        const factor = Number(b.dataset.cgZoom), size = viewport[2] * factor;
        if (size < base[2] / 5 || size > base[2] * 2) return;
        viewport = [viewport[0] + (viewport[2] - size) / 2, viewport[1] + (viewport[3] - size) / 2, size, size]; apply();
      });
      target.querySelector('[data-cg-fit]').onclick = () => { viewport = base.slice(); apply(); };
      target.querySelector('[data-cg-prev]')?.addEventListener('click', () => { page--; draw(); });
      target.querySelector('[data-cg-next]')?.addEventListener('click', () => { page++; draw(); });
      let drag;
      const point = event => new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
      svg.onpointerdown = event => { if (event.button !== 0 || event.target.closest('[data-cg-node]')) return; drag = point(event); svg.setPointerCapture(event.pointerId); };
      svg.onpointermove = event => {
        if (!drag) return;
        const p = point(event); viewport[0] -= p.x - drag.x; viewport[1] -= p.y - drag.y; apply();
      };
      svg.onpointerup = svg.onpointercancel = () => { drag = null; };
      svg.querySelectorAll('[data-cg-node]').forEach(node => {
        const activate = () => {
          const id = node.dataset.cgNode;
          if (concepts.has(id)) chooseConcept(id);
          else if (id === 'course' || id === focusedDocument) { selected = id; updateSelection(); drawDetail(); }
          else openDocument(id);
        };
        node.onclick = activate;
        node.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); } };
      });
    }
    function updateSelection() {
      target.querySelectorAll('[data-cg-node]').forEach(n => n.setAttribute('aria-pressed', String(n.dataset.cgNode === selected)));
      target.querySelector('[data-cg-questions]').innerHTML = '';
    }
    function drawDetail() {
      const box = target.querySelector('[data-cg-detail]');
      if (!box) return;
      const docs = documents(), node = concepts.get(selected), doc = docs.find(d => d.id === selected);
      if (node) {
        const refs = [...new Map(node.references.map(r => [r.documentId + '/' + r.page, r])).values()];
        box.innerHTML = `<span class="cg-eyebrow">知识点</span><h3>${e(node.label)}</h3><p>${e(node.descriptions[0] || '暂无知识点说明。')}</p><div class="cg-detail-stat">${node.questionIds.length}<span>道关联练习</span></div>
          <button type="button" class="button button-blue" data-cg-practice ${node.questionIds.length ? '' : 'disabled'}>练习此知识点 →</button><p class="cg-muted">AI题目未经独立审校</p><h4>资料出处</h4><ul class="cg-source-list">${refs.map(r => `<li>${e(data.documents.find(d => d.id === r.documentId)?.name || '资料')}${r.page ? ' · 第' + e(r.page) + '页' : ''}</li>`).join('')}</ul><div data-cg-video></div>`;
        box.querySelector('[data-cg-practice]').onclick = () => {
          const questions = target.querySelector('[data-cg-questions]');
          questions.innerHTML = '<button type="button" class="button button-outline" data-cg-close-quiz>返回知识图谱</button><div data-shared-practice></div>';
          window.XueyaConceptPractice.mount(questions.querySelector('[data-shared-practice]'),node.id,course);
          questions.querySelector('[data-cg-close-quiz]').onclick = () => { questions.innerHTML = ''; box.querySelector('[data-cg-practice]').focus(); };
          questions.scrollIntoView({block:'start', behavior:'smooth'});
        };
      } else {
        const list = doc ? children.get(doc.id) || [] : pointsFor(docs);
        box.innerHTML = `<span class="cg-eyebrow">${doc ? '资料章节' : '课程总览'}</span><h3>${e(doc ? titleOf(doc.name) : subject)}</h3><p>${doc ? e(doc.name) : '这本课程书汇集当前可访问的同科资料。点击图中的资料展开章节，点击知识点查看说明和练习。'}</p>
          <div class="cg-detail-stat">${list.length}<span>个已保存知识点 · ${questionCount(list)}题</span></div>
          ${doc ? `<div class="cg-detail-links">${list.map(n => `<button type="button" data-cg-detail-node="${e(n.id)}">${e(n.label)} <span>${n.questionIds.length}题 ↗</span></button>`).join('') || '<p>此资料尚无已保存知识点，题目生成后会显示在这里。</p>'}</div>` : `<h4>资料目录</h4><div class="cg-detail-links">${docs.map(d => `<button type="button" data-cg-document="${e(d.id)}">${e(titleOf(d.name))}<span>${children.get(d.id)?.length || 0}个知识点 ↗</span></button>`).join('')}</div>`}
          <div data-cg-video></div>`;
        box.querySelectorAll('[data-cg-document]').forEach(b => b.onclick = () => openDocument(b.dataset.cgDocument));
        box.querySelectorAll('[data-cg-detail-node]').forEach(b => b.onclick = () => {
          const index = list.findIndex(n => n.id === b.dataset.cgDetailNode);
          if (Math.floor(index / 24) !== page) { page = Math.floor(index / 24); selected = b.dataset.cgDetailNode; draw(); }
          else chooseConcept(b.dataset.cgDetailNode);
        });
      }
      drawVideos();
    }
    function drawVideos() {
      const box = target.querySelector('[data-cg-video]');
      if (!box) return;
      const matching = courses.filter(c => c.subject === subject && /^https?:\/\//i.test(c.sourceUrl || ''));
      box.innerHTML = `<h4>相关视频课程</h4>${matching.map(c => `<a class="cg-video-link" href="#space/courses/${e(c.id)}/${e(c.episodes?.[0]?.id||'')}" data-concept-video="${e(c.id)}">${e(c.title)} ↗</a>`).join('') || `<p>${videoError ? '课程目录暂时无法读取。' : '暂无匹配的课程入口。'}</p>`}<p class="cg-muted">${matching.length ? '本科目课程总览，尚未定位到此知识点的具体分集。' : '没有匹配视频时，不添加占位链接。'}</p>`;
    }
    target.addEventListener('click',event=>{const link=event.target.closest('[data-concept-video]');if(link)sessionStorage.setItem((window.XueyaDataKey||((k)=>k))('xueya-video-context'),JSON.stringify({courseId:link.dataset.conceptVideo,label:concepts.get(selected)?.label||subject,returnHash:location.hash,returnTab:directory?'graph':'corpus'}));});
    const videoPromise = window.XueyaPlatform.spaceFetch('/api/learning/space/courses').then(async response => {
      const value = await response.json(); if (!response.ok || !value.ok) throw Error('课程目录读取失败');
      if (alive()) { courses = value.courses || []; drawVideos(); }
    }).catch(() => { if (alive()) { videoError = true; drawVideos(); } });
    await load(); await videoPromise;
  }
  window.XueyaCourseGraph = {mount, unmount() { epoch++; clearTimeout(timer); }};
})();
