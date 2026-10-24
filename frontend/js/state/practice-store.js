/* Practice state slice and offline op queue. Status rules are the parity twin of backend/xueya/practice_rules.py */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaPracticeStore=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const KEY='xueya-practice-v1',OPS='xueya-practice-ops';
const CATEGORIES=['hot100','basic','interview'],STATUSES=['pending','mastered','wrong'],ACTIONS=['answer','correct','master','conquer','fuzzy','mark-wrong','reset','note-save'];
const OBJECTIVE=['single','fill'];
const blank=()=>({status:'pending',confidence:'unknown',wrongCount:0,correctCount:0,wrongEnteredAt:null,lastWrongAt:null,lastResult:null,masteredAt:null,lastOperationAt:null,revision:0});
function entry(progress,questionId){let row=progress[questionId];if(!row){row=blank();progress[questionId]=row;}return row;}
function apply(progress,question,action,payload={}){
  const type=question&&question.type,row=entry(progress,question&&question.id),at=payload.at||'';
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
    if(row.lastResult!=='wrong'||row.wrongCount<=0)throw new Error('NOTHING_TO_CORRECT');
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
  const stamp=item=>item[1].lastWrongAt||item[1].wrongEnteredAt||'';
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
  if(question.type==='fill'){
    const norm=s=>String(s==null?'':s).trim().toLowerCase();
    const accepted=(question.acceptedAnswers&&question.acceptedAnswers.length?question.acceptedAnswers:[question.answer]).map(norm);
    return accepted.includes(norm(value));
  }
  return false;
}
function createStore({storage=globalThis.localStorage,accountId='local',now=()=>new Date().toISOString(),id=()=>globalThis.crypto.randomUUID()}={}){
  const key=KEY+':'+accountId,opsKey=OPS+':'+accountId;
  const read=k=>{try{const v=JSON.parse(storage.getItem(k)||'null');return v&&typeof v==='object'?v:null;}catch{return null;}};
  const defaults=()=>({version:1,accountId,bankVersion:'',serverSeq:0,statuses:{},notes:{},drafts:{},filters:{},ui:{category:'hot100',selectedQuestionId:null,detailFullscreen:false,listScroll:0,mode:'order',language:'python',wrongSort:'recent'}});
  let state=Object.assign(defaults(),read(key)||{});
  state.filters=Object.assign({hot100:{},basic:{},interview:{}},state.filters||{});
  for(const category of CATEGORIES)state.filters[category]=Object.assign({keyword:'',subject:'',tag:'',difficulty:'',type:'',status:''},state.filters[category]||{});
  state.ui=Object.assign(defaults().ui,state.ui||{});
  let queue=Array.isArray(read(opsKey))?read(opsKey):[];
  let flushing=null,offline=queue.some(op=>op.state==='pending');
  function persist(){try{storage.setItem(key,JSON.stringify(state));}catch{/* drafts are best effort; authoritative state stays on the server */}}
  function persistQueue(){try{storage.setItem(opsKey,JSON.stringify(queue));}catch{throw new Error('STORAGE_UNAVAILABLE');}}
  function push(kind,questionId,payload={}){
    const op={opId:'op-'+id(),kind,questionId,payload,clientTs:now(),deviceTag:state.accountId,state:'pending',retries:0};
    queue.push(op);persistQueue();
    if(kind!=='note-save'){try{apply(state.statuses,{id:questionId,type:payload.questionType},kind,payload);}catch{/* server will reject; keep the op for the error surface */}}
    persist();return op;
  }
  function pushNote(questionId,text,baseRevision){
    const note=mergeNote(state.notes[questionId],text,baseRevision,now(),state.accountId);
    state.notes[questionId]=note;delete note.merged;persist();
    return push('note-save',questionId,{text,baseRevision});
  }
  function applyServer(payload){
    if(payload&&typeof payload.serverSeq==='number')state.serverSeq=payload.serverSeq;
    if(payload&&payload.statuses)state.statuses=payload.statuses;
    if(payload&&payload.notes)state.notes=payload.notes;
    persist();
  }
  async function flush(client){
    if(!client)return {ok:false,error:'NO_CLIENT'};
    const pending=queue.filter(op=>op.state==='pending');
    if(!pending.length){offline=false;return {ok:true,accepted:[]};}
    flushing=(flushing||Promise.resolve()).catch(()=>{}).then(async()=>{
      try{
        const result=await client.submitOps(pending.map(({opId,kind,questionId,payload,clientTs,deviceTag})=>({opId,kind,questionId,payload,clientTs,deviceTag})));
        const done=new Set([...(result.accepted||[]),...(result.duplicates||[])]);
        for(const op of queue)if(done.has(op.opId))op.state='synced';
        queue=queue.filter(op=>op.state!=='synced');
        persistQueue();applyServer(result);offline=queue.some(op=>op.state==='pending');
        return result;
      }catch(error){
        for(const op of pending)op.retries=(op.retries||0)+1;
        persistQueue();offline=true;throw error;
      }
    });
    return flushing;
  }
  return {
    state,get offline(){return offline;},get pendingOps(){return queue.filter(op=>op.state==='pending').length;},
    get error(){return '';},
    filters(){return state.filters[state.ui.category]||{};},
    persist,push,pushNote,flush,applyServer,judgeAnswer,
    setDraft(questionId,text){if(text)state.drafts[questionId]={text,savedAt:now()};else delete state.drafts[questionId];persist();},
    draft(questionId){return (state.drafts[questionId]||{}).text||'';},
    chooseConflict(questionId,text){
      const note=state.notes[questionId];if(!note)return false;
      const conflicts=(note.conflicts||[]).filter(c=>c.text!==text);
      state.notes[questionId]={text,revision:note.revision,updatedAt:now(),conflicts};persist();return true;
    },
  };
}
return{createStore,KEY,OPS,CATEGORIES,STATUSES,ACTIONS,blank,apply,weight,randomPick,sortWrong,mergeNote,judgeAnswer};
});
