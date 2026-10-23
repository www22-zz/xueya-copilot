/* Conversation-first navigation; existing controls retain their listeners and IDs. */
(() => {
'use strict';
window.XueyaExperience={create({state}){
 let observed=false,scheduled=false;
 function mount(){const top=document.querySelector('.space-top-right');if(!top)return;let more=document.querySelector('#workspaceMore');if(!more){more=document.createElement('details');more.id='workspaceMore';more.className='workspace-more';more.innerHTML='<summary>更多 <span aria-hidden="true">⋯</span></summary><div class="workspace-more-panel"><strong>学习工具</strong><div data-more-learning></div></div>';document.querySelector('.space-nav').append(more);more.addEventListener('click',event=>{const b=event.target.closest('button,a');if(!b)return;if(b.id==='g3Entry'&&state.view!=='cards'){event.preventDefault();event.stopPropagation();location.hash='space/cards';}more.open=false;},true);}
 let services=document.querySelector('#workspaceServices');if(!services){services=document.createElement('details');services.id='workspaceServices';services.className='workspace-more workspace-services';services.innerHTML='<summary>服务与数据 <span aria-hidden="true">⚙</span></summary><div class="workspace-more-panel"><strong>课程与服务</strong><div data-more-settings></div></div>';document.querySelector('#workspaceServicesSlot').append(services);services.addEventListener('click',event=>{if(event.target.closest('button,a')&&!services.classList.contains('settings-services-content'))services.open=false;},true);}
 const settings=services.querySelector('[data-more-settings]'),tools=more.querySelector('[data-more-learning]');
 for(const selector of ['[data-manage-courses]','[data-export-workspace]','#platformData','#workbenchSettings','#workbenchTasks','#engineStatus']){const element=document.querySelector(selector);if(element&&element.parentElement!==settings)settings.append(element);}
 const template=document.querySelector('#g3Entry');if(template)template.hidden=true;
 const entry=document.querySelector('#cLearningEntry');if(entry)entry.hidden=true;
 const nav=document.querySelector('.space-nav'),header=document.querySelector('.site-header');if(nav&&header&&nav.parentElement!==header)header.insertBefore(nav,header.firstChild);for(const [view,label] of [['chapters','章节学习'],['plan','复习计划'],['graph','知识图谱']]){const link=document.querySelector(`a[data-view="${view}"]`);if(link){if(link.textContent!==label)link.textContent=label;if(link.parentElement!==tools)tools.append(link);}}
 for(const [view,label] of [['chat','问答'],['cards','笔记'],['practice','练习'],['memory','复习']]){const link=nav?.querySelector(`[data-view="${view}"]`);if(link)link.textContent=label;}
 const library=nav?.querySelector('[data-view=library]');if(library?.firstChild?.nodeType===Node.TEXT_NODE)library.firstChild.textContent='资料 ';
 const g3=document.querySelector('#g3Workspace');if(g3){g3.hidden=state.view!=='chapters';if(!g3.closest('.notes-advanced')){const extra=document.createElement('details');extra.className='notes-advanced';extra.innerHTML='<summary>高级：模板加工与历史记录</summary>';g3.before(extra);extra.append(g3);}}
 window.XueyaPreferences?.mount();
 if(!observed){observed=true;new MutationObserver(()=>{if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;mount();});}).observe(top,{childList:true,subtree:true});}
 }
 document.addEventListener('click',event=>{for(const details of document.querySelectorAll('#workspaceMore,#workspaceServices'))if(!details.classList.contains('settings-services-content')&&details.open&&!details.contains(event.target))details.open=false;});
 document.addEventListener('keydown',event=>{if(event.key==='Escape')for(const details of document.querySelectorAll('#workspaceMore,#workspaceServices'))if(!details.classList.contains('settings-services-content')&&details.open){details.open=false;details.querySelector('summary').focus();}});
 return {mount};
}};
const fine=matchMedia('(hover:hover) and (pointer:fine)'),reduced=matchMedia('(prefers-reduced-motion:reduce)');
document.addEventListener('pointermove',event=>{const title=event.target.closest('[data-title-play]');document.querySelectorAll('[data-title-play].is-playing').forEach(el=>{if(el!==title)el.classList.remove('is-playing');});if(!title||!fine.matches||reduced.matches)return;const rect=title.getBoundingClientRect();title.style.setProperty('--title-x',event.clientX-rect.left+'px');title.style.setProperty('--title-y',event.clientY-rect.top+'px');title.classList.add('is-playing');});
document.addEventListener('pointerout',event=>{const title=event.target.closest('[data-title-play]');if(title&&!title.contains(event.relatedTarget))title.classList.remove('is-playing');});
})();
