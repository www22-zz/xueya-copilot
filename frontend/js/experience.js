/* Conversation-first navigation; existing controls retain their listeners and IDs. */
(() => {
'use strict';
window.XueyaExperience={create({state}){
 let observed=false,scheduled=false;
 function mount(){
  const top=document.querySelector('.space-top-right');if(!top)return;
  let services=document.querySelector('#workspaceServices');
  if(!services){services=document.createElement('details');services.id='workspaceServices';services.className='workspace-more workspace-services';services.innerHTML='<summary>服务与数据 <span aria-hidden="true">⚙</span></summary><div class="workspace-more-panel"><strong>课程与服务</strong><div data-more-settings></div></div>';document.querySelector('#workspaceServicesSlot').append(services);services.addEventListener('click',event=>{if(event.target.closest('button,a')&&!services.classList.contains('settings-services-content'))services.open=false;},true);}
  const settings=services.querySelector('[data-more-settings]');
  for(const selector of ['[data-manage-courses]','[data-export-workspace]','#platformData','#workbenchSettings','#workbenchTasks','#engineStatus']){const element=document.querySelector(selector);if(element&&element.parentElement!==settings)settings.append(element);}
  const nav=document.querySelector('.space-nav'),header=document.querySelector('.site-header');
  if(nav&&header&&nav.parentElement!==header)header.insertBefore(nav,header.firstChild);
  window.XueyaPreferences?.mount();
  if(!observed){observed=true;new MutationObserver(()=>{if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;mount();});}).observe(top,{childList:true,subtree:true});}
 }
 document.addEventListener('click',event=>{const details=document.querySelector('#workspaceServices');if(details&&!details.classList.contains('settings-services-content')&&details.open&&!details.contains(event.target))details.open=false;});
 document.addEventListener('keydown',event=>{const details=document.querySelector('#workspaceServices');if(event.key==='Escape'&&details&&!details.classList.contains('settings-services-content')&&details.open){details.open=false;details.querySelector('summary').focus();}});
 return {mount};
}};
const fine=matchMedia('(hover:hover) and (pointer:fine)'),reduced=matchMedia('(prefers-reduced-motion:reduce)');
function resetTitle(title){title.classList.remove('is-playing');title.querySelectorAll('.title-letter').forEach(letter=>{letter.style.removeProperty('transform');letter.style.removeProperty('color');});}
document.addEventListener('pointermove',event=>{
 const title=event.target.closest('[data-title-play]');
 document.querySelectorAll('[data-title-play].is-playing').forEach(el=>{if(el!==title)resetTitle(el);});
 if(!title||!fine.matches||reduced.matches)return;
 title.classList.add('is-playing');
 title.querySelectorAll('.title-letter').forEach(letter=>{const r=letter.getBoundingClientRect(),distance=Math.abs(event.clientX-r.left-r.width/2),weight=Math.max(0,1-distance/70);letter.style.transform=`translateY(${-3*weight}px)`;letter.style.color=weight>.3?'var(--blue)':'';});
});
document.addEventListener('pointerout',event=>{const title=event.target.closest('[data-title-play]');if(title&&!title.contains(event.relatedTarget))resetTitle(title);});

})();
