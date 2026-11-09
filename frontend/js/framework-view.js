/* Knowledge Framework Mindmap Visualizer & Editor (Specs Section 9).
   Independent concept graph, editable nodes, collapse/expand, add/delete/patch. */
(function(root) {
  'use strict';
  const e = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function createFrameworkUI({ toast = () => {}, navigate = () => {} } = {}) {
    let container = null;
    let generation = 0;
    let currentFramework = null;
    let frameworksList = [];
    let loading = false;
    let selectedNodeId = null;
    const collapsed=new Set();let draggedNodeId=null;
    let activeJob=null,pollTimer=null,historySubject='',historyTopic='';
    const active=j=>j&&['queued','running','cancelling'].includes(j.status);
    async function poll(stamp){
      clearTimeout(pollTimer);if(stamp!==generation||!activeJob)return;
      try{
        const response=await window.XueyaPlatform.spaceFetch('/api/learning/space/jobs/'+activeJob.id);const data=await response.json();
        if(stamp!==generation)return;activeJob=data.job;loading=active(activeJob);
        if(loading){pollTimer=setTimeout(()=>poll(stamp),1000);return;}
        if(activeJob.status==='succeeded'){
          const id=activeJob.result.frameworkId;await loadList();if(stamp!==generation)return;
          currentFramework=frameworksList.find(f=>f.id===id)||currentFramework;toast('知识框架已保存');
        }else toast('框架操作未完成：'+(activeJob.error||activeJob.status)+'；不会自动重新调用');
        activeJob=null;render();
      }catch(error){if(stamp===generation){loading=false;toast('作业暂未读取，重新打开可恢复原作业');render();}}
    }
    async function submitJob(value){
      if(loading)return;const stamp=generation;loading=true;render();
      try{const response=await window.XueyaPlatform.spaceFetch('/api/learning/space/framework/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...value,operationId:'framework-'+crypto.randomUUID()})});
        const data=await response.json();if(stamp!==generation)return;activeJob=data.job;poll(stamp);
      }catch(error){if(stamp===generation){loading=false;toast(error.message);render();}}
    }

    async function loadList() {
      const stamp=generation;
      try {
        const res = await window.XueyaPlatform.spaceFetch('/api/learning/space/framework/list', {
          headers: {  }
        });
        const data = await res.json();
        if(stamp!==generation)return;
        if (data.ok) {
          frameworksList = data.frameworks || [];
          activeJob=(data.jobs||[]).find(active)||null;
          if (!currentFramework && frameworksList.length > 0) {
            currentFramework = frameworksList[0];
          }
        }
      } catch (error) { toast(error.message || '学习操作未完成'); }
    }

    async function generate(subject, topic) {
      return submitJob({mode:'generate',subject,topic});
    }

    async function patch(patchData) {
      if (!currentFramework||loading) return;
      const stamp=generation;
      try {
        loading=true;
        const res = await window.XueyaPlatform.spaceFetch(`/api/learning/space/framework/${currentFramework.id}/patch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({...patchData,expectedRevision:currentFramework.revision||currentFramework.version})
        });
        const data = await res.json();
        if(stamp!==generation)return;
        if (data.ok) {
          currentFramework = data.framework;
          frameworksList=frameworksList.map(f=>f.id===currentFramework.id?currentFramework:f);
          toast('导图已保存！');
          render();
        }
      } catch (error) { if(stamp===generation)toast(error.message || '学习操作未完成'); }
      finally{if(stamp===generation){loading=false;render();}}
    }

    function renderTree(nodes, parentId = null) {
      const children = nodes.filter(n => (parentId === null ? n.level === 0 : n.parentId === parentId));
      if (!children.length) return '';
      return `<ul class="kf-tree-level">
        ${children.map(node => `
          <li class="kf-tree-item ${node.id === selectedNodeId ? 'is-selected' : ''}" data-node-id="${e(node.id)}">
            <div class="kf-node-card kf-level-${node.level}" draggable="${node.level>0}" data-kf-drag="${e(node.id)}">
              <div class="kf-node-header">
                <strong>${e(node.label)}</strong>
                <span class="kf-node-badge">L${node.level}</span>
              </div>
              ${node.description ? `<p class="kf-node-desc">${e(node.description)}</p>` : ''}
              <div class="kf-node-actions">
                ${node.materialId&&node.conceptId?`<a class="button button-small button-outline" href="#space/materials/${e(node.materialId)}/${e(node.conceptId)}">打开资料知识点与练习</a>`:''}
                ${(node.questionIds||[]).slice(0,4).map(id=>`<a class="button button-small button-outline" href="#space/practice/ai/${e(id)}">练习题</a>`).join('')}
                ${node.video?.url?`<a class="button button-small button-outline" href="${e(node.video.url)}">${e(node.video.title||'相关课程')}</a>`:node.materialId?'<small>暂无已匹配视频分集</small>':''}
                ${(currentFramework.nodes||[]).some(n=>n.parentId===node.id)?`<button type="button" class="button button-small button-outline" data-kf-collapse="${e(node.id)}">${collapsed.has(node.id)?'展开':'收起'}</button>`:''}
                <button type="button" class="button button-small button-outline" data-kf-ask="${e(node.label)}" title="围绕该节点向 AI 提问">答疑</button>
                <button type="button" class="button button-small button-outline" data-kf-add-child="${e(node.id)}">＋添加子节点</button>
                <button type="button" class="button button-small button-outline" data-kf-edit="${e(node.id)}">编辑</button>
                <button type="button" class="button button-small button-outline" data-kf-ai="${e(node.id)}">AI 细化</button>
                ${node.level > 0 ? `<button type="button" class="button button-small button-outline" data-kf-del="${e(node.id)}">删除</button>` : ''}
              </div>
            </div>
            ${collapsed.has(node.id)?'':renderTree(nodes, node.id)}
          </li>
        `).join('')}
      </ul>`;
    }

    function render() {
      if (!container) return;
      container.innerHTML = `
        <div class="kf-workspace panel">
          <div class="kf-toolbar">
            <div class="kf-title-area">
              <h2>${currentFramework ? e(currentFramework.title) : '知识框架导图'}</h2>
              <p>概念与知识点结构关系图 · 独立于日程任务</p>${currentFramework?.planId?'<a href="#space/analysis/plans">查看关联计划</a>':''}
              ${currentFramework?.undo?.length?'<button type="button" class="button button-small button-outline" data-kf-undo>撤销上次修改</button>':''}
            </div>
            <div class="kf-actions">
              <select id="kfSubjectSelect" class="filter-select">
                <option value="数据结构">数据结构</option>
                <option value="计算机组成原理">计算机组成原理</option>
                <option value="操作系统">操作系统</option>
                <option value="计算机网络">计算机网络</option>
              </select>
              <input id="kfTopicInput" aria-label="知识框架专题" placeholder="专题（留空生成学科总览）" maxlength="200">
              <button type="button" class="button button-blue button-small" data-kf-generate ${loading?'disabled':''}>生成知识框架</button>
            </div>
          </div>

          <div class="kf-history-filters"><label>历史学科<select data-kf-filter-subject><option value="">全部</option>${[...new Set(frameworksList.map(f=>f.subject))].map(s=>`<option value="${e(s)}" ${s===historySubject?'selected':''}>${e(s)}</option>`).join('')}</select></label><label>专题筛选<input data-kf-filter-topic value="${e(historyTopic)}" maxlength="200"></label></div>
          ${frameworksList.length ? `
            <div class="kf-history-strip">
              <span class="kf-strip-label">框架历史：</span>
              ${frameworksList.filter(f=>(!historySubject||f.subject===historySubject)&&(!historyTopic||(f.topic+' '+f.title).includes(historyTopic))).map(fw => `
                <button type="button" class="button button-small ${fw.id === currentFramework?.id ? 'button-blue' : 'button-outline'}" data-kf-switch="${e(fw.id)}">
                  ${e(fw.title)}
                </button>
              `).join('')}
            </div>
          ` : ''}

          <div class="kf-canvas-stage">
            ${loading ? '<div class="kf-loading">正在梳理概念与关系结构…</div>' :
              currentFramework ? `
                <div class="kf-mindmap-tree">
                  ${renderTree(currentFramework.nodes || [])}
                </div>
              ` : `
                <div class="kf-empty">
                  <h3>还没有生成的知识框架</h3>
                  <p>选择学科并点击上方「生成知识框架」，或在 AI 对话中说“整理成知识框架”。</p>
                </div>
              `
            }
          </div>
        </div>
      `;

      bindEvents();
    }

    function bindEvents() {
      container.querySelector('[data-kf-undo]')?.addEventListener('click',()=>patch({undo:true}));
      container.querySelector('[data-kf-filter-subject]')?.addEventListener('change',event=>{historySubject=event.target.value;render();});
      container.querySelector('[data-kf-filter-topic]')?.addEventListener('change',event=>{historyTopic=event.target.value;render();});
      container.querySelectorAll('[data-kf-ai]').forEach(button=>button.onclick=()=>{
        const instruction=prompt('如何细化这个知识点？','补充子概念、联系与易混淆点');
        if(instruction?.trim())submitJob({mode:'expand',frameworkId:currentFramework.id,nodeId:button.dataset.kfAi,
          expectedRevision:currentFramework.revision||currentFramework.version,instruction:instruction.trim()});
      });
      container.ondragstart=event=>{const card=event.target.closest('[data-kf-drag]');if(card?.draggable){draggedNodeId=card.dataset.kfDrag;event.dataTransfer.setData('text/plain',draggedNodeId);}};
      container.ondragover=event=>{if(draggedNodeId&&event.target.closest('[data-kf-drag]'))event.preventDefault();};
      container.ondrop=event=>{const target=event.target.closest('[data-kf-drag]');if(!target||!draggedNodeId)return;event.preventDefault();const id=draggedNodeId;draggedNodeId=null;if(id!==target.dataset.kfDrag)patch({updateNode:{id,parentId:target.dataset.kfDrag}});};
      container.ondragend=()=>{draggedNodeId=null;};
      container.querySelectorAll('[data-kf-collapse]').forEach(btn=>btn.onclick=()=>{const id=btn.dataset.kfCollapse;collapsed.has(id)?collapsed.delete(id):collapsed.add(id);render();});
      container.querySelector('[data-kf-generate]')?.addEventListener('click', () => {
        const sel = container.querySelector('#kfSubjectSelect');
        const subj = sel ? sel.value : '数据结构';
        generate(subj, container.querySelector('#kfTopicInput').value.trim());
      });

      container.querySelectorAll('[data-kf-switch]').forEach(btn => {
        btn.addEventListener('click', () => {
          const fid = btn.dataset.kfSwitch;
          const target = frameworksList.find(f => f.id === fid);
          if (target) {
            currentFramework = target;
            render();
          }
        });
      });

      container.querySelectorAll('[data-kf-ask]').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const topic = btn.dataset.kfAsk;
          if (window.XueyaAsk) {
            location.hash = '#space/ask';
            setTimeout(() => window.XueyaAsk(`请帮我系统讲解一下「${topic}」的核心概念和易混淆考点。`), 200);
          }
        });
      });

      container.querySelectorAll('[data-kf-edit]').forEach(btn=>btn.addEventListener('click',()=>{
        const node=currentFramework.nodes.find(n=>n.id===btn.dataset.kfEdit);
        const label=prompt('编辑知识点名称：',node.label);
        if(label?.trim())patch({updateNode:{id:node.id,label:label.trim()}});
      }));

      container.querySelectorAll('[data-kf-add-child]').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const parentId = btn.dataset.kfAddChild;
          const label = prompt('请输入新节点名称：');
          if (label && label.trim()) {
            patch({
              addNode: {
                label: label.trim(),
                parentId: parentId,
                level: 2,
                description: '用户补充节点'
              }
            });
          }
        });
      });

      container.querySelectorAll('[data-kf-del]').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const nid = btn.dataset.kfDel;
          if (confirm('确定删除该概念节点及其子分支吗？')) {
            patch({ removeNodeId: nid });
          }
        });
      });
    }

    async function mount(targetNode,frameworkId) {
      const stamp=++generation;container = targetNode;loading=false;
      await loadList();if(stamp!==generation)return;
      if(frameworkId){const target=frameworksList.find(f=>f.id===frameworkId);if(target)currentFramework=target;else toast('关联框架不存在或已删除');}
      render();
      if(activeJob){loading=true;render();poll(stamp);}
    }

    return { mount, generate, render, unmount(){generation++;clearTimeout(pollTimer);container=null;} };
  }

  root.XueyaFramework = { create: createFrameworkUI };
})(typeof globalThis !== 'undefined' ? globalThis : window);
