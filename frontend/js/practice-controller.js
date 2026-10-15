/* Existing topic/question API orchestration, extracted from the page controller. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaPracticeUI=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
function create({state,allSources,persist,toast,render,e}){
  const service=globalThis.XueyaPractice.createPracticeService(),$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];let active;
  function selectedSources(documentId){const doc=documentId?state.documents.find(d=>d.id===documentId&&!d.superseded):state.documents.find(d=>d.chunks?.length&&!d.superseded);return{doc,sources:doc?.chunks?.length?doc.chunks.slice(0,24):allSources().slice(0,6)};}
  async function run(label,kind,operation){
    if(active){toast('还有一项资料整理正在进行，请等待或停止等待。');return;}
    const controller=new AbortController(),courseId=state.courseId;active={controller,kind};state.working=true;
    $('#activityBanner').hidden=false;$('#activityLabel').textContent=label;render();
    try{return await operation({signal:controller.signal,check(){controller.signal.throwIfAborted();if(state.courseId!==courseId)throw new Error('课程已切换，本次结果没有写入当前课程。');}});}
    catch(error){if(controller.signal.aborted)toast('已停止等待，没有保存未完成结果。');else toast(error.message||'处理失败，请确认服务可用后重试。');}
    finally{active=null;state.working=false;$('#activityBanner').hidden=true;render();}
  }
  async function addQuestions(documentId,focus){
    const {doc,sources}=selectedSources(documentId);if(!sources.length){toast('请先添加一份已解析的资料。');return;}
    return run('正在根据课程资料生成候选题…','questions',async({signal,check})=>{
      const result=await service.questions({courseId:state.courseId,topic:doc?.name||'',focus:Array.isArray(focus)&&focus.length?focus.join('、'):undefined,sources:sources.map(({id,title,location,quote})=>({id,title,location,quote})),count:5},{signal});check();
      const known=new Set(sources.map(s=>s.id));const valid=result.filter(q=>Array.isArray(q.options)&&q.options.length>=2&&Number.isInteger(q.answer)&&q.answer>=0&&q.answer<q.options.length&&known.has(q.sourceId));
      if(!valid.length)throw new Error('没有生成具备有效答案与来源的题目，请重新生成。');
      const items=valid.map(q=>({...q,id:'bank-'+crypto.randomUUID(),origin:'ai',type:'single',reviewed:false,version:1}));state.bank.unshift(...items);state.quizFilter='bank';state.quizIndex=0;state.selected=null;state.submitted=false;persist();toast(`已生成${items.length}道候选题，请核对题干、答案与原文。`);if(location.hash!=='#space/practice')location.hash='space/practice';
    });
  }
  function renderBankTopics(){const picked=new Set(state.bankSelected||[]);$('#bankTopics').innerHTML=state.bankTopics.length?state.bankTopics.map(t=>`<label class="bank-topic"><input type="checkbox" data-topic="${e(t.name)}" ${picked.has(t.name)?'checked':''}><span>${e(t.name)}</span></label>`).join(''):'<p class="panel-description">没有找到可出题的知识点。</p>';updateBankCount();}
  function updateBankCount(){const n=$$('#bankTopics input[data-topic]:checked').length,button=$('#bankGenerate');button.disabled=!n;button.textContent=n?`生成 ${n} 个知识点的题目`:'请选择知识点';}
  async function openBankDialog(){
    const dialog=$('#bankDialog');if(!dialog.open)dialog.showModal();if(state.bankTopics.length){renderBankTopics();return;}
    const {sources}=selectedSources();if(!sources.length){$('#bankTopics').innerHTML='<p class="panel-description">请先添加一份已解析资料。</p>';updateBankCount();return;}
    $('#bankTopics').innerHTML='<p class="panel-description" role="status">正在整理知识点，可关闭面板停止等待。</p>';updateBankCount();
    return run('正在从课程资料整理知识点…','topics',async({signal,check})=>{const topics=await service.topics(sources.map(({id,title,location,quote})=>({id,title,location,quote})),{signal,courseId:state.courseId});check();state.bankTopics=topics;state.bankSelected=[];persist();if(dialog.open)renderBankTopics();});
  }
  function generateFromTopics(){const selected=$$('#bankTopics input[data-topic]:checked').map(input=>input.dataset.topic);state.bankSelected=selected;$('#bankDialog').close();return addQuestions(null,selected);}
  function mount(){$('#bankDialog').addEventListener('close',()=>{if(active?.kind==='topics')active.controller.abort();});}
  return{addQuestions,openBankDialog,renderBankTopics,updateBankCount,generateFromTopics,generateBank:()=>addQuestions(null),mount,cancel(){active?.controller.abort();}};
}
return{create};
});
