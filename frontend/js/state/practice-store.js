/* Practice state slice and offline op queue. Status rules are the parity twin of backend/xueya/practice_rules.py */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaPracticeStore=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const KEY='xueya-practice-v1',OPS='xueya-practice-ops';
const CATEGORIES=['hot100','exam408','legacy','basic','interview'],STATUSES=['pending','mastered','wrong'],ACTIONS=['answer','correct','master','conquer','fuzzy','mark-wrong','reset','note-save','written-save'];
const OBJECTIVE=['single','multiple','boolean','fill'];
const blank=()=>({status:'pending',confidence:'unknown',wrongCount:0,correctCount:0,wrongEnteredAt:null,lastWrongAt:null,lastResult:null,masteredAt:null,lastOperationAt:null,revision:0});
function entry(progress,questionId){let row=progress[questionId];if(!row){row=blank();progress[questionId]=row;}return row;}
function apply(progress,question,action,payload={}){
  const type=question&&question.type,row=entry(progress,question&&question.id),at=payload.at||'';
  if(action==='written-save'){
    if(type!=='short')throw new Error('WRITTEN_QUESTION_REQUIRED');
    row.writtenAnswers={...(payload.answers||{})};row.selfScores={...(payload.scores||{})};row.lastOperationAt=at;row.revision+=1;return row;
  }
  if(action==='answer'){
    if(!OBJECTIVE.includes(type))throw new Error('OBJECTIVE_ANSWER_ONLY');
    if(!['correct','wrong'].includes(payload.result))throw new Error('INVALID_ANSWER_RESULT');
    row.lastResult=payload.result;row.lastOperationAt=at;row.revision+=1;
    if(payload.result==='wrong'){row.wrongCount+=1;row.lastWrongAt=at;if(row.status!=='wrong')row.wrongEnteredAt=at;row.status='wrong';}
    else row.correctCount+=1;
    return row;
  }
  if(action==='correct'){
    if(type!=='fill')throw new Error('FILL_ONLY');
    if(payload.attemptId&&(row.correctedAttemptIds||[]).includes(payload.attemptId))return row;
    if((!payload.attemptId&&row.lastResult!=='wrong')||row.wrongCount<=0)throw new Error('NOTHING_TO_CORRECT');
    if(payload.attemptId)row.correctedAttemptIds=[...(row.correctedAttemptIds||[]),payload.attemptId];
    row.wrongCount-=1;row.correctCount+=1;row.lastResult='correct';row.status='pending';row.confidence='unknown';row.lastOperationAt=at;row.revision+=1;return row;
  }
  if(action==='fuzzy'){
    if(row.status!=='pending')throw new Error('PENDING_ONLY');
    row.confidence='fuzzy';row.lastOperationAt=at;row.revision+=1;return row;
  }
  if(action==='master'){
    if(row.status!=='pending')throw new Error('PENDING_ONLY');
    row.status='mastered';row.confidence='mastered';row.masteredAt=at;row.lastOperationAt=at;row.revision+=1;return row;
  }
  if(action==='conquer'){
    if(row.status!=='wrong')throw new Error('WRONG_ONLY');
    row.status='mastered';row.confidence='mastered';row.masteredAt=at;row.lastOperationAt=at;row.revision+=1;return row;
  }
  if(action==='mark-wrong'){
    row.status='wrong';row.wrongEnteredAt=at;row.lastOperationAt=at;row.revision+=1;return row;
  }
  if(action==='reset'){
    if(row.status==='pending')throw new Error('ALREADY_PENDING');
    row.status='pending';row.confidence='unknown';row.lastOperationAt=at;row.revision+=1;return row;
  }
  throw new Error('UNKNOWN_ACTION');
}
const weight=row=>(row&&row.confidence==='fuzzy')?3:1;
function randomPick(candidates,progress={},options={}){
  const items=(candidates||[]).filter(Boolean);if(!items.length)return null;
  const pool=items.length>1?items.filter(q=>q.id!==options.lastId):items;
  const weights=pool.map(q=>weight(progress[q.id])),total=weights.reduce((a,b)=>a+b,0);
  const roll=((options.roll==null?0.5:options.roll)%1+1)%1*total;let running=0;
  for(let i=0;i<pool.length;i++){running+=weights[i];if(roll<running)return pool[i];}
  return pool[pool.length-1];
}
function sortWrong(rows,mode='recent'){
  const stamp=item=>[item[1].lastWrongAt||'',item[1].wrongEnteredAt||''].sort().pop();
  const ordered=[...rows].sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:0);
  ordered.sort((a,b)=>stamp(a)<stamp(b)?1:stamp(a)>stamp(b)?-1:0);
  if(mode==='count')ordered.sort((a,b)=>(b[1].wrongCount||0)-(a[1].wrongCount||0));
  return ordered;
}
function mergeNote(existing,text,baseRevision,at='',device=''){
  const note=existing?{...existing,conflicts:[...(existing.conflicts||[])]}:{text:'',revision:0,updatedAt:null,conflicts:[]};
  if(baseRevision!==note.revision){note.conflicts.push({text,createdAt:at,deviceTag:device,baseRevision});note.revision+=1;note.updatedAt=at;return{...note,merged:true};}
  note.text=text;note.revision+=1;note.updatedAt=at;return{...note,merged:false};
}
function judgeAnswer(question,value){
  if(!question)return false;
  if(question.type==='single')return Number(value)===Number(question.answer);
  if(question.type==='boolean')return typeof value==='boolean'&&value===question.answer;
  if(question.type==='multiple')return Array.isArray(value)&&new Set(value).size===value.length&&value.length===question.answer.length&&value.every(v=>question.answer.includes(v));
  if(question.type==='fill'){
    const norm=s=>String(s==null?'':s).trim().toLowerCase();
    const accepted=(question.acceptedAnswers&&question.acceptedAnswers.length?question.acceptedAnswers:[question.answer]).map(norm);
    return accepted.includes(norm(value));
  }
  return false;
}
function createStore({storage=globalThis.localStorage,accountId='local',now=()=>new Date().toISOString(),id=()=>globalThis.crypto.randomUUID()}={}){
  const key=KEY+':'+accountId,opsKey=OPS+':'+accountId;
  // A separate session journal survives refresh when localStorage is full/disabled.
  // Keys remain account scoped; another account never reads this journal.
  const recovery=(()=>{try{return storage===globalThis.localStorage?globalThis.sessionStorage:null;}catch{return null;}})();
  const read=k=>{try{const saved=recovery?.getItem('xueya-recovery:'+k);return JSON.parse(saved||storage.getItem(k)||'null');}catch{return null;}};
  const defaults={version:2,accountId,serverSeq:0,statuses:{},notes:{},drafts:{},filters:{},ui:{category:'hot100',selectedQuestionId:null,listScroll:0,mode:'order',language:'python',wrongSort:'recent',positions:{},reviewFilters:{}}};
  const state=Object.assign({},defaults,read(key)||{});state.accountId=accountId;
  state.ui=Object.assign({},defaults.ui,state.ui||{});state.ui.positions=state.ui.positions||{};if(!CATEGORIES.includes(state.ui.category))state.ui.category='hot100';
  state.ui.reviewFilters=state.ui.reviewFilters||{};state.ui.detailFullscreen=false;delete state.ui.shortDraft;
  for(const category of CATEGORIES)state.filters[category]=Object.assign({keyword:'',subject:'',tag:'',difficulty:'',type:'',status:'pending'},state.filters[category]||{});
  for(const category of CATEGORIES)if(!state.filters[category].status)state.filters[category].status='pending';
  let queue=read(opsKey)||[],flushing=null,lastError='';
  const copy=v=>JSON.parse(JSON.stringify(v));
  let authoritative={statuses:copy(state.statuses),notes:copy(state.notes)};
  let journal=null,hydrated=false,journalPending=Promise.resolve();
  function journalWrite(k,text){
    if(!journal||!hydrated)return;
    const task=new Promise(resolve=>{try{const tx=journal.transaction('records','readwrite'),records=tx.objectStore('records');if(text===null)records.delete(k);else records.put(text,k);tx.oncomplete=resolve;tx.onerror=tx.onabort=()=>{lastError='持久恢复副本保存失败，请复制草稿并释放存储空间';resolve();};}catch{lastError='持久恢复副本保存失败，请复制草稿并释放存储空间';resolve();}});
    journalPending=Promise.all([journalPending,task]);
  }
  // IndexedDB has a separate capacity from the small localStorage quota. Session
  // storage supplies immediate refresh recovery while this durable journal commits.
  const ready=new Promise(resolve=>{
    if(!recovery||!globalThis.indexedDB){hydrated=true;resolve();return;}
    try{const request=indexedDB.open('xueya-practice-recovery',1);
      request.onupgradeneeded=()=>request.result.createObjectStore('records');
      request.onerror=request.onblocked=()=>{hydrated=true;resolve();};
      request.onsuccess=()=>{journal=request.result;journal.onversionchange=()=>journal.close();
        const tx=journal.transaction('records','readonly'),records=tx.objectStore('records'),saved=records.get(key),savedQueue=records.get(opsKey);
        tx.oncomplete=()=>{try{if(saved.result){const restored=JSON.parse(saved.result),ui=state.ui;Object.assign(ui,restored.ui||{});Object.assign(state,restored,{accountId,ui});if(!CATEGORIES.includes(ui.category))ui.category='hot100';ui.detailFullscreen=false;}if(savedQueue.result)queue=JSON.parse(savedQueue.result);}catch{lastError='恢复副本无法读取，请检查浏览器存储';}
          hydrated=true;persist();persistQueue();resolve();};
        tx.onerror=tx.onabort=()=>{hydrated=true;resolve();};};
    }catch{hydrated=true;resolve();}
  });
  function write(k,value){const text=JSON.stringify(value);try{storage.setItem(k,text);recovery?.removeItem('xueya-recovery:'+k);journalWrite(k,null);return true;}catch{lastError='浏览器存储空间不足，正在使用恢复副本';journalWrite(k,text);try{recovery?.setItem('xueya-recovery:'+k,text);return Boolean(recovery||journal);}catch{lastError='保存失败，请复制草稿后释放浏览器存储空间';return Boolean(journal);}}}
  function persist(){return write(key,state);}
  function persistQueue(){return write(opsKey,queue);}
  function replay(){
    state.statuses=copy(authoritative.statuses||{});state.notes=copy(authoritative.notes||{});
    for(const op of queue){
      if(op.kind==='note-save'){const before=state.notes[op.questionId]?.revision||0;state.notes[op.questionId]=mergeNote(state.notes[op.questionId],op.payload.text,op.payload.baseRevision,op.clientTs,op.deviceTag);if(op.payload.resolve&&op.payload.baseRevision===before)state.notes[op.questionId].conflicts=[];}
      else try{apply(state.statuses,{id:op.questionId,type:op.payload.questionType},op.kind,{...op.payload,at:op.clientTs});}catch{}
    }
  }
  function push(kind,questionId,payload={}){
    if(kind!=='note-save')apply(state.statuses,{id:questionId,type:payload.questionType},kind,{...payload,at:now()});
    const op={opId:'op-'+id(),kind,questionId,payload,clientTs:now(),deviceTag:accountId,state:'pending'};
    queue.push(op);persistQueue();persist();return op;
  }
  function pushNote(questionId,text,baseRevision,resolve=false){
    const op=push('note-save',questionId,{text,baseRevision,resolve});
    const note=mergeNote(state.notes[questionId],text,baseRevision,op.clientTs,accountId);
    if(resolve&&baseRevision===(state.notes[questionId]?.revision||0))note.conflicts=[];
    state.notes[questionId]=note;persist();return op;
  }
  function applyServer(payload){
    if(typeof payload?.serverSeq==='number'&&payload.serverSeq<state.serverSeq)return;
    lastError='';
    if(typeof payload?.serverSeq==='number')state.serverSeq=payload.serverSeq;
    authoritative={statuses:copy(payload?.statuses||{}),notes:copy(payload?.notes||{})};
    replay();persist();try{storage.setItem(key+':server',JSON.stringify(authoritative));}catch{}
  }
  async function flush(client){
    if(flushing)return flushing;
    flushing=(async()=>{
      while(queue.length){
        const pending=queue.slice(0,200);
        try{
          const result=await client.submitOps(pending);
          const accepted=new Set([...(result.accepted||[]),...(result.duplicates||[])]),done=new Set(accepted);
          const rejected=result.rejected||[];
          // Terminal validation failures must not block unrelated accepted saves.
          // Retain their receipts for inspection, rather than replaying them forever.
          for(const rejectedOp of rejected){done.add(rejectedOp.opId);(state.rejectedOps||(state.rejectedOps=[])).push({...pending.find(op=>op.opId===rejectedOp.opId),error:rejectedOp.error});}
          if(!done.size)throw Error('同步未完成');
          const remaining=queue.filter(op=>!done.has(op.opId));
          if(remaining.length===queue.length)throw Error('同步回执无效，记录仍保留在本地');
          queue=remaining;persistQueue();applyServer(result);
          for(const op of pending)if(op.kind==='note-save'&&accepted.has(op.opId)&&state.drafts[op.questionId]?.text===op.payload.text)delete state.drafts[op.questionId];
          persist();if(rejected.length)lastError='有操作未获接受，已保留详情；其他记录已同步';
        }catch(error){lastError=error.message||'待同步';persist();throw error;}
      }
      return {ok:true};
    })().finally(()=>{flushing=null;});return flushing;
  }
  // v2 stores optimistic state and its authoritative base separately, so refresh cannot double-count.
  const base=read(key+':server');if(base)authoritative=base;
  const originalApply=applyServer;
  function receive(payload){originalApply(payload);try{storage.setItem(key+':server',JSON.stringify(authoritative));}catch{}}
  return {state,persist,push,pushNote,flush,applyServer:receive,judgeAnswer,ready,async durable(){await ready;await journalPending;},
    get offline(){return queue.length>0;},get pendingOps(){return queue.length;},get error(){return lastError;},
    filters(){return state.filters[state.ui.category];},
    setDraft(questionId,text){state.drafts[questionId]={text,savedAt:now()};persist();},
    clearDraft(questionId){delete state.drafts[questionId];persist();},
    draft(questionId){return state.drafts[questionId]?.text??'';},
    hasDraft(questionId){return Object.prototype.hasOwnProperty.call(state.drafts,questionId);},
    queuedNote(questionId,text){return queue.some(op=>op.kind==='note-save'&&op.questionId===questionId&&op.payload.text===text);},
    rejectedNote(questionId,text){return (state.rejectedOps||[]).some(op=>op.kind==='note-save'&&op.questionId===questionId&&op.payload?.text===text);},
    chooseConflict(questionId,text){const note=state.notes[questionId];if(!note)return false;pushNote(questionId,text,note.revision,true);return true;}
  };
}
return{createStore,KEY,OPS,CATEGORIES,STATUSES,ACTIONS,blank,apply,weight,randomPick,sortWrong,mergeNote,judgeAnswer};
});
