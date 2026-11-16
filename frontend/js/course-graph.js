/* Source-backed course books and interactive mind maps. No model calls on read. */
(() => {
  'use strict';
  const e = window.XueyaRich.escape;
  const messageFor = code => ({AI_CONNECTION_FAILED:'当前服务无法连接模型站点，未提交新批次。请检查服务启动环境或网络。',JOB_FAILED:'请求异常，尚无可核验结果；请先核对连接和调用账本。'}[code] || code);
  const titleOf = name => name.replace(/\.[a-z0-9]+$/i, '').replace(/^week\d+[\s_-]*/i, '').replace(/[_-]+/g, ' ').trim();
  let epoch = 0, timer, detach = () => {};
  // Memory only: account/course data must never leak through a shared cache.
  const snapshots = new Map(), requests = new Map();
  const scopedKey = course => (window.XueyaDataKey || (key => key))('course-graph:' + course);
  function rememberSnapshot(key, value) {
    snapshots.delete(key); snapshots.set(key, value);
    if (snapshots.size > 6) snapshots.delete(snapshots.keys().next().value);
  }
  function read(course, key) {
    if (!requests.has(key)) {
      const request = api(course).then(value => { rememberSnapshot(key, value); return value; })
        .finally(() => { if (requests.get(key) === request) requests.delete(key); });
      requests.set(key, request);
    }
    return requests.get(key);
  }

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
    detach();
    const cacheKey = scopedKey(course);
    let data, signature = '', subject = '', filter = '', focusedDocument = '', selected = 'course', search = '', page = 0;
    let viewport, viewportKey = '', courses = [], videoError = false, submitting = false;
    let concepts = new Map(), children = new Map(), subjects = [];
    const stateKey=(window.XueyaDataKey||((k)=>k))('course-graph-view:'+course);
    try{const old=JSON.parse(sessionStorage.getItem(stateKey)||'{}');subject=old.subject||'';focusedDocument=old.focusedDocument||'';selected=old.selected||'course';page=old.page||0;viewport=old.viewport;viewportKey=old.viewportKey||'';}catch{}
    const remember=()=>sessionStorage.setItem(stateKey,JSON.stringify({subject,focusedDocument,selected,page,viewport,viewportKey}));
    const alive = () => stamp === epoch && target.isConnected && scopedKey(course) === cacheKey;
    if (!snapshots.has(cacheKey)) target.innerHTML = '<p role="status">正在读取课程书架…</p>';
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
    const questionCount = nodes => new Set(nodes.flatMap(n => [...n.questionIds, ...(n.fixedQuestions || []).map(q => q.id)])).size;
    const openDocument = id => { focusedDocument = id; selected = id; page = 0; search = ''; draw(); };
    const chooseConcept = id => { selected = id; remember(); updateSelection(); drawDetail(); target.querySelector('[data-cg-detail]')?.scrollIntoView({block:'nearest',behavior:'smooth'}); };

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
      if (alive()) timer = setTimeout(() => document.hidden ? schedule() : load(), data?.coverage.pendingJobs ? 8000 : 15000);
    }
    function apply(next) {
      const nextSignature = JSON.stringify(next);
      // Keep the currently rendered data and selection consistent while editing.
      const busy = target.querySelector('[data-quiz-card]') ||
        (target.contains(document.activeElement) && document.activeElement.matches('input,textarea,select'));
      if (data && nextSignature !== signature && busy) return;
      data = next; index();
      if (reference) {
        const node = data.nodes.find(n => n.references?.some(r => r.materialId === reference));
        const doc = data.documents.find(d => d.id === node?.references.find(r => r.materialId === reference)?.documentId);
        if (doc?.ready) { subject = doc.subject; focusedDocument = doc.id; selected = node.id; }
        reference = null;
      }
      if (nextSignature !== signature) { signature = nextSignature; draw(); }
      const status = target.querySelector('[data-cg-load-status]');
      if (status) status.textContent = '';
    }
    let loading = false, refreshAgain = false;
    async function load() {
      if (!alive() || loading) return;
      loading = true;
      try {
        const next = await read(course, cacheKey);
        if (!alive()) return;
        apply(next);
      } catch (error) {
        if (!alive()) return;
        if (['AUTH_REQUIRED','AUTH_SCOPE_MISMATCH','FORBIDDEN','COURSE_NOT_FOUND'].includes(error.code || error.message)) {
          snapshots.delete(cacheKey); data = null;
          target.innerHTML = `<p role="alert">${e(messageFor(error.message))}</p>`;
          return;
        }
        const status = target.querySelector('[data-cg-load-status]');
        if (status) status.textContent = '更新暂不可用，当前内容已保留。' + messageFor(error.message);
        else target.innerHTML = `<p role="alert">${e(messageFor(error.message))}</p>`;
      } finally {
        loading = false;
        if (alive() && refreshAgain) { refreshAgain = false; void load(); }
        else schedule();
      }
    }

    function coverage() {
      const c = data.coverage;
      return `<details class="cg-coverage"><summary>资料生成进度 · 已处理 ${c.completedRanges}/${c.totalRanges} 批${c.pendingJobs ? ' · 正在处理 ' + c.pendingJobs + ' 批' : ''}</summary>
        <p>${c.questions}道已保存题 · ${data.blocked.length}批需核对 · ${c.unreadyDocuments}份未就绪。${c.inputComplete ? '当前可信输入均已处理，知识完整性仍待审校。' : '导图展示已保存的知识点，尚未完成全文提取。'}${c.outlineNodes ? `另有${c.outlineNodes}个节点来自MD章节标题，点击可读正文；目录展开不生成题目。` : ''}AI题目未经独立审校。</p>
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
      target.innerHTML = `<section class="cg-reader"><div class="cg-reader-heading"><button type="button" class="button button-outline" data-cg-back>← 返回书架</button><div><span class="cg-eyebrow">${e(subject)} / 知识图谱</span><h2>${e(doc ? titleOf(doc.title || doc.name) : subject)}</h2></div><span class="cg-reader-count">${docs.length}份资料 · ${nodes.length}个知识点 · ${questionCount(nodes)}道题</span></div>
        <div class="cg-reader-layout"><div class="cg-map-area"><div class="cg-map-toolbar"><button class="button button-outline" data-cg-overview ${!doc ? 'disabled' : ''}>课程总览</button><button class="button button-outline" data-cg-zoom="0.8" aria-label="放大导图">＋</button><button class="button button-outline" data-cg-zoom="1.25" aria-label="缩小导图">−</button><button class="button button-outline" data-cg-fit>适应画布</button><label class="cg-search">查找知识点<input type="search" data-cg-search placeholder="输入名称" value="${e(search)}"></label></div>
        <div class="cg-search-results" data-cg-results></div><div class="cg-map" data-cg-map></div>
        <p class="cg-map-legend"><span>● 课程 / 资料</span><span>○ 知识点与固定练习</span><span>点击节点查看详情 · 拖动画布 · 连线表示包含关系</span></p></div>
        <aside class="cg-detail" data-cg-detail aria-label="节点详情"></aside></div><div data-cg-questions></div></section>`;
      target.querySelector('[data-cg-back]').onclick = () => { const previous = subject; subject = ''; draw(); target.querySelectorAll('[data-cg-book]').forEach(b => { if (b.dataset.cgBook === previous) b.focus({preventScroll:true}); }); };
      target.querySelector('[data-cg-overview]').onclick = () => { focusedDocument = ''; selected = 'course'; page = 0; draw(); };
      target.querySelector('[data-cg-search]').oninput = event => { search = event.target.value; drawSearch(); };
      drawCanvas(); drawSearch(); drawDetail();
      if(directory){const map=target.querySelector('.cg-map-area');map.innerHTML='<h3>章节与知识点目录</h3>'+docs.map(d=>`<details open><summary>${e(titleOf(d.title || d.name))}</summary>${(children.get(d.id)||[]).map(n=>`<button type="button" class="button button-outline" data-directory-node="${e(n.id)}">${e(n.label)} · ${n.questionIds.length}题</button>`).join('')||'<p>待补充资料或尚未生成题目</p>'}</details>`).join('');map.querySelectorAll('[data-directory-node]').forEach(b=>b.onclick=()=>chooseConcept(b.dataset.directoryNode));}
    }
    function drawSearch() {
      const box = target.querySelector('[data-cg-results]');
      if (!box) return;
      const term = search.trim().toLocaleLowerCase(), matches = pointsFor(documents()).filter(n => n.label.toLocaleLowerCase().includes(term));
      box.innerHTML = term ? (matches.slice(0, 30).map(n => `<button type="button" data-cg-result="${e(n.id)}">${e(n.label)}</button>`).join('') || '<p>没有匹配的已保存知识点。</p>') : '';
      box.querySelectorAll('[data-cg-result]').forEach(b => b.onclick = () => {
        const n = concepts.get(b.dataset.cgResult), ref = n.references.find(r => documents().some(d => d.id === r.documentId));
        focusedDocument = ref.documentId; selected = n.id; page = Math.floor((children.get(ref.documentId) || []).findIndex(c => c.id === n.id) / 12); search = ''; draw();
      });
    }

    function drawCanvas() {
      const docs = documents();
      if (!focusedDocument && docs.length) focusedDocument = docs[0].id;
      const doc = docs.find(d => d.id === focusedDocument), all = children.get(doc?.id) || [];
      const matches = all.filter(n => !search || n.label.includes(search));
      page = Math.min(page, Math.max(0, Math.ceil(matches.length / 12) - 1));
      const items = matches.slice(page * 12, (page + 1) * 12);
      const width = 1250;
      const height = Math.max(560, docs.length * 78 + 70, items.length * 62 + 70);
      const topic = subject === '数据结构' ? '数据结构与算法' : subject;
      const topicChars = Array.from(topic);
      const topicLabel = topicChars.length > 9 ? topicChars.slice(0, 8).join('') + '…' : topic;
      const rootX = 20, rootY = height / 2, rootWidth = 210, rootHeight = 82;
      const chapterX = 300, chapterWidth = 290, leafX = 820;
      const yDoc = i => (height - docs.length * 78) / 2 + i * 78 + 39;
      const yLeaf = i => (height - items.length * 62) / 2 + i * 62 + 31;
      const connect = (fromX, fromY, toX, toY) => {
        const bend = (fromX + toX) / 2;
        return `M${fromX} ${fromY} C${bend} ${fromY},${bend} ${toY},${toX} ${toY}`;
      };
      const activeChapterY = yDoc(docs.findIndex(d => d.id === doc?.id));
      const paths = items.map((_, i) => connect(chapterX + chapterWidth, activeChapterY, leafX, yLeaf(i)));
      target.querySelector('[data-cg-map]').innerHTML = `<div class="cg-nebula"><div class="cg-nebula-heading"><span>✦ 知识星轨</span><span>${e(topic)} · ${docs.length}份资料</span></div>${matches.length > 12 ? `<div class="heading-actions"><button class="button button-outline" data-cg-page="-1" ${page ? '' : 'disabled'}>上一组</button><span>${page * 12 + 1}–${Math.min((page + 1) * 12, matches.length)} / ${matches.length} 个节点</span><button class="button button-outline" data-cg-page="1" ${(page + 1) * 12 < matches.length ? '' : 'disabled'}>下一组</button></div>` : ''}<svg class="cg-star-map" viewBox="0 0 ${width} ${height}" role="group" aria-label="${e(topic)}章节知识图谱">
        <defs><linearGradient id="cg-rail"><stop stop-color="#ffd166"/><stop offset="1" stop-color="#38bdf8"/></linearGradient></defs>
        <g class="cg-stars" aria-hidden="true">${Array.from({length:65},(_,i)=>`<circle cx="${(i*173+31)%width}" cy="${(i*97+17)%height}" r="${i%3===0?1.4:.7}"/>`).join('')}</g>
        ${docs.map((d, i) => `<path class="cg-root-rail ${doc?.id===d.id ? 'is-active' : ''}" d="${connect(rootX + rootWidth, rootY, chapterX, yDoc(i))}"/>`).join('')}
        ${paths.map(d=>`<path class="cg-star-rail" d="${d}"/><path class="cg-star-flow" d="${d}"/>`).join('')}
        <g class="cg-star-root" transform="translate(${rootX} ${rootY - rootHeight / 2})" role="img" aria-label="${e(topic)}">
          <title>${e(topic)}</title><rect width="${rootWidth}" height="${rootHeight}" rx="18"/>
          <text x="${rootWidth / 2}" y="31" class="cg-star-sub" text-anchor="middle">课程主题</text>
          <text x="${rootWidth / 2}" y="58" class="cg-star-root-title" text-anchor="middle">${e(topicLabel)}</text>
        </g>
        ${docs.map((d,i)=>`<g class="cg-chapter ${doc?.id===d.id?'is-active':''}" transform="translate(${chapterX} ${yDoc(i)-27})" tabindex="0" role="button" aria-label="${e(titleOf(d.title || d.name))}" aria-pressed="${doc?.id===d.id}" data-star-doc="${e(d.id)}"><rect width="${chapterWidth}" height="54" rx="15"/><text x="16" y="23">${e(titleOf(d.title || d.name).slice(0,24))}</text><text class="cg-star-sub" x="16" y="42">${children.get(d.id)?.length||0}个知识点</text><title>${e(d.name)}</title></g>`).join('')}
        ${items.map((n,i)=>`<g class="cg-leaf" transform="translate(${leafX} ${yLeaf(i)-23})" tabindex="0" role="button" data-cg-node="${e(n.id)}" aria-label="${e(n.label)}，查看对应练习"><rect width="410" height="46" rx="13"/><circle cx="18" cy="23" r="4"/><text x="32" y="20">${e(n.label)}</text><text class="cg-star-sub" x="32" y="37">${(n.fixedQuestions||[]).length}道课程固定练习 · ${n.questionIds.length}道资料题 →</text></g>`).join('')}
        </svg>${!items.length?'<p class="cg-star-empty">本章暂无已保存知识点或可匹配的固定练习。</p>':''}<p class="cg-star-footer">点击章节切换知识点 · 点击知识点打开对应题目 · 连线表示包含关系</p></div>`;
      const bind = (selector, action) => target.querySelectorAll(selector).forEach(el => {
        el.onclick = () => action(el);
        el.onkeydown = ev => {if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();action(el);}};
      });
      bind('[data-star-doc]', el => openDocument(el.dataset.starDoc));
      bind('[data-cg-node]', el => chooseConcept(el.dataset.cgNode));
      target.querySelectorAll('[data-cg-page]').forEach(button => button.onclick = () => {
        page += Number(button.dataset.cgPage); viewportKey = ''; draw();
      });
      const svg = target.querySelector('.cg-star-map');
      const base=[0,0,width,height], key=`${width}/${height}/${subject}/${focusedDocument}`;
      if(viewportKey!==key){viewport=base.slice();viewportKey=key;}
      const apply=()=>{svg.setAttribute('viewBox',viewport.join(' '));remember();};apply();
      target.querySelectorAll('[data-cg-zoom]').forEach(b=>b.onclick=()=>{const f=Number(b.dataset.cgZoom);if(viewport[2]*f<300||viewport[2]*f>width*2)return;viewport=[viewport[0]+viewport[2]*(1-f)/2,viewport[1]+viewport[3]*(1-f)/2,viewport[2]*f,viewport[3]*f];apply();});
      target.querySelector('[data-cg-fit]').onclick=()=>{viewport=base.slice();apply();};
      let drag;
      svg.onpointerdown=ev=>{if(ev.button!==0||ev.target.closest('[role="button"]'))return;drag={x:ev.clientX,y:ev.clientY};svg.setPointerCapture(ev.pointerId);};
      svg.onpointermove=ev=>{if(!drag)return;const scale=viewport[2]/svg.getBoundingClientRect().width;viewport[0]-=(ev.clientX-drag.x)*scale;viewport[1]-=(ev.clientY-drag.y)*scale;drag={x:ev.clientX,y:ev.clientY};apply();};
      svg.onpointerup=svg.onpointercancel=()=>{drag=null;};
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
        const savedDescription = node.descriptions[0] || '';
        const description = savedDescription.includes('[平台资料正文受保护]')
          ? '本节点对应资料中的“' + node.label + '”章节。可查看关联练习，或向伴学助手提问学习本节内容。'
          : savedDescription || '暂无知识点说明。';
        box.innerHTML = `<span class="cg-eyebrow">${node.sourceType === 'markdown-outline' ? '资料章节 · 来自MD标题' : '知识点'}</span><h3>${e(node.label)}</h3><p>${e(description)}</p><div class="cg-detail-stat">${questionCount([node])}<span>道关联练习</span></div>
          <button type="button" class="button button-blue" data-cg-practice ${node.questionIds.length ? '' : 'hidden disabled'}>打开资料生成题 →</button>${node.questionIds.length ? '<p class="cg-muted">资料生成题未经独立审校</p>' : ''}<h4>课程固定练习</h4><div class="cg-fixed-links">${(node.fixedQuestions||[]).map(q=>`<a class="cg-fixed-question" href="${e(q.url)}">${e(q.title)} ↗</a>`).join('')||'<p>暂无精确匹配的固定练习。</p>'}</div><h4>资料出处</h4><ul class="cg-source-list">${refs.map(r => `<li>${e(data.documents.find(d => d.id === r.documentId)?.name || '资料')}${r.page ? ' · 第' + e(r.page) + '页' : ''}</li>`).join('')}</ul><div data-cg-video></div>`;
        box.querySelector('[data-cg-practice]').onclick = () => {
          const questions = target.querySelector('[data-cg-questions]');
          questions.innerHTML = '<button type="button" class="button button-outline" data-cg-close-quiz>返回知识图谱</button><div data-shared-practice></div>';
          window.XueyaConceptPractice.mount(questions.querySelector('[data-shared-practice]'),node.id,course);
          questions.querySelector('[data-cg-close-quiz]').onclick = () => { questions.innerHTML = ''; box.querySelector('[data-cg-practice]').focus(); };
          questions.scrollIntoView({block:'start', behavior:'smooth'});
        };
      } else {
        const list = doc ? children.get(doc.id) || [] : pointsFor(docs);
        box.innerHTML = `<span class="cg-eyebrow">${doc ? '资料章节' : '课程总览'}</span><h3>${e(doc ? titleOf(doc.title || doc.name) : subject)}</h3><p>${doc ? e(doc.name) : '这本课程书汇集当前可访问的同科资料。点击图中的资料展开章节，点击知识点查看说明和练习。'}</p>
          <div class="cg-detail-stat">${list.length}<span>个知识点 · ${questionCount(list)}题</span></div>
          ${doc ? `<div class="cg-detail-links">${list.map(n => `<button type="button" data-cg-detail-node="${e(n.id)}">${e(n.label)} <span>${n.questionIds.length}题 ↗</span></button>`).join('') || '<p>此资料尚无已保存知识点，题目生成后会显示在这里。</p>'}</div>` : `<h4>资料目录</h4><div class="cg-detail-links">${docs.map(d => `<button type="button" data-cg-document="${e(d.id)}">${e(titleOf(d.title || d.name))}<span>${children.get(d.id)?.length || 0}个知识点 ↗</span></button>`).join('')}</div>`}
          <div data-cg-video></div>`;
        box.querySelectorAll('[data-cg-document]').forEach(b => b.onclick = () => openDocument(b.dataset.cgDocument));
        box.querySelectorAll('[data-cg-detail-node]').forEach(b => b.onclick = () => {
          const index = list.findIndex(n => n.id === b.dataset.cgDetailNode);
          if (Math.floor(index / 12) !== page) { page = Math.floor(index / 12); selected = b.dataset.cgDetailNode; draw(); }
          else chooseConcept(b.dataset.cgDetailNode);
        });
      }
      drawVideos();
    }
    function drawVideos() {
      const box = target.querySelector('[data-cg-video]');
      if (!box) return;
      const matching = courses.filter(c => c.subject === subject && /^https?:\/\//i.test(c.sourceUrl || ''));
      box.innerHTML = `<h4>相关视频课程</h4>${matching.map(c => `<a class="cg-video-link" href="#space/courses/${e(c.id)}/${e(c.episodes?.[0]?.id||'')}" data-concept-video="${e(c.id)}">${e(c.title)} ↗</a>`).join('') || `<p>${videoError ? '课程目录暂时无法读取。' : '暂无匹配的课程入口。'}</p>`}<p class="cg-muted">${matching.length ? '已核验的本科目课程入口；尚未定位到该知识点的具体分集。' : '没有匹配视频时，不添加占位链接。'}</p>`;
    }
    const onVideo = event => {const link=event.target.closest('[data-concept-video]');if(link)sessionStorage.setItem((window.XueyaDataKey||((k)=>k))('xueya-video-context'),JSON.stringify({courseId:link.dataset.conceptVideo,label:concepts.get(selected)?.label||subject,returnHash:location.hash,returnTab:directory?'graph':'corpus'}));};
    const refresh = () => { if (!document.hidden) { if (loading) refreshAgain = true; else void load(); } };
    target.addEventListener('click', onVideo);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    window.addEventListener('xueya:materials-changed', refresh);
    detach = () => {
      target.removeEventListener('click', onVideo);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
      window.removeEventListener('xueya:materials-changed', refresh);
    };
    if (snapshots.has(cacheKey)) apply(snapshots.get(cacheKey));
    const videoPromise = window.XueyaPlatform.spaceFetch('/api/learning/space/courses').then(async response => {
      const value = await response.json(); if (!response.ok || !value.ok) throw Error('课程目录读取失败');
      if (alive()) { courses = value.courses || []; drawVideos(); }
    }).catch(() => { if (alive()) { videoError = true; drawVideos(); } });
    await load(); await videoPromise;
  }
  window.XueyaCourseGraph = {mount, unmount() { epoch++; clearTimeout(timer); detach(); }};
})();
