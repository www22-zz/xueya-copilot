/* UI-owned browser workspace. No server database or learning algorithm lives here. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaWorkspaceStore=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const KEY='xueya-copilot-workspace-v3',LEGACY='xueya-copilot-state-v2';
const fields=['documents','cards','messages','records','examDate','minutes','completed','plan','bank','bankTopics','sessions','sessionId','quizDraft','quizFilter','quizIndex','feedback','relations','reviewLog','planHistory','planVersion','planDraft','courseId','libraryTags','corrections','examRun','mediaResults'];
const clone=value=>JSON.parse(JSON.stringify(value));
function createStore({storage,learning:L,id=()=>globalThis.crypto.randomUUID(),now=()=>new Date().toISOString()}={}){
  let error='';
  function read(key){try{const value=JSON.parse(storage.getItem(key)||'null');return value&&typeof value==='object'&&!Array.isArray(value)?value:null;}catch{return null;}}
  const workspace=read(KEY),legacy=read(LEGACY),old=read('xueya-copilot-state-v1');
  const defaults=()=>({documents:[],cards:[],messages:[],records:[],bank:[],bankTopics:[],sessions:[],sessionId:'',examDate:L.addDays(L.today(),21),minutes:30,completed:{},plan:[],quizDraft:{},quizFilter:'all',quizIndex:0,feedback:[],relations:[],reviewLog:[],planHistory:[],planVersion:0,planDraft:null,libraryTags:[],corrections:[],examRun:null,mediaResults:[]});
  function normalize(value={}){
    const result={...defaults(),...value};
    for(const field of ['documents','cards','messages','records','bank','bankTopics','sessions','plan','feedback','relations','reviewLog','planHistory','libraryTags','corrections','mediaResults'])if(!Array.isArray(result[field]))result[field]=[];
    if(!L.validDate(result.examDate))result.examDate=L.addDays(L.today(),21);
    result.minutes=Math.max(15,Math.min(120,Number(result.minutes)||30));
    result.completed=result.completed&&typeof result.completed==='object'?result.completed:{};
    result.quizDraft=result.quizDraft&&typeof result.quizDraft==='object'?result.quizDraft:{};
    result.sessions=result.sessions.filter(s=>s&&typeof s.id==='string'&&Array.isArray(s.messages));
    if(!['all','bank','wrong','exam'].includes(result.quizFilter))result.quizFilter='all';
    result.quizIndex=Math.max(0,Number.isInteger(result.quizIndex)?result.quizIndex:0);
    if(!result.sessions.length)result.sessions=[{id:id(),title:String(result.messages.find(m=>m.role==='user')?.text||'新的对话').slice(0,40),messages:clone(result.messages),createdAt:now()}];
    result.sessionId=result.sessions.some(s=>s.id===result.sessionId)?result.sessionId:result.sessions[0].id;
    result.messages=clone(result.sessions.find(s=>s.id===result.sessionId).messages||[]);
    const scope=result.sessions.find(s=>s.id===result.sessionId).scopeDocumentIds;
    result.selectedDocuments=(Array.isArray(scope)?scope:[]).filter(value=>typeof value==='string');
    result.messages=result.messages.filter(message=>message&&typeof message==='object');
    for(const message of result.messages){message.id=message.id||id();if(message.role==='ai'&&message.engine==='正在回答')Object.assign(message,{text:'上次生成已中断，请重新发送。',failed:true,sources:[],engine:'回答未完成'});}
    result.sessions.find(s=>s.id===result.sessionId).messages=clone(result.messages);
    return result;
  }
  const initial=normalize(legacy||{documents:[...L.documents,...(old?.documents||[]).filter(d=>!L.documents.some(s=>s.id===d.id)).map(d=>({...d,status:'内容待解析',meta:'旧版资料记录 · 请重新选择原件'}))]});
  let courses=Array.isArray(workspace?.courses)&&workspace.courses.length?workspace.courses:[{id:'course-default',name:'数据结构',archived:false,data:initial}];
  courses=courses.filter(c=>c&&typeof c.id==='string'&&typeof c.name==='string').map(c=>({...c,data:normalize(c.data)}));
  if(!courses.length)courses=[{id:'course-default',name:'数据结构',archived:false,data:initial}];
  let activeId=courses.some(c=>c.id===workspace?.activeId&&!c.archived)?workspace.activeId:(courses.find(c=>!c.archived)||courses[0]).id;
  const state={...normalize(courses.find(c=>c.id===activeId).data),courseId:activeId,mode:'ask',view:'overview',pending:false,selected:null,submitted:false,draft:'',activeSource:null,libraryQuery:'',cardQuery:'',bankSelected:[],followupIndex:null};
  function snapshot(){const output={};for(const field of fields)output[field]=state[field];output.mediaResults=(state.mediaResults||[]).map(({audioURL,...result})=>result);return clone(output);}
  function sync(){
    const session=state.sessions.find(s=>s.id===state.sessionId);
    if(session){session.messages=clone(state.messages);session.scopeDocumentIds=[...state.selectedDocuments];session.title=String(state.messages.find(m=>m.role==='user')?.text||session.title||'新的对话').slice(0,40);session.updatedAt=now();}
    const course=courses.find(c=>c.id===activeId);if(course)course.data=snapshot();
  }
  function persist(){
    sync();error='';
    try{storage.setItem(KEY,JSON.stringify({version:3,activeId,courses}));}catch{error='浏览器空间不足或禁止保存。请先导出备份，本次修改暂未持久保存。';return false;}
    // Preserve the legacy key and full history for existing integrations; v3 is authoritative.
    try{storage.setItem(LEGACY,JSON.stringify(snapshot()));}catch{/* A compatibility mirror must not invalidate the durable v3 save. */}
    return true;
  }
  function switchCourse(courseId){
    if(state.pending)return false;
    const course=courses.find(c=>c.id===courseId&&!c.archived);if(!course)return false;
    sync();activeId=courseId;
    Object.assign(state,normalize(course.data),{courseId,pending:false,quizPool:undefined,selected:null,submitted:false,draft:'',activeSource:null,followupIndex:null,libraryQuery:'',cardQuery:'',bankSelected:[]});
    persist();return true;
  }
  function addCourse(name){
    if(state.pending||!String(name).trim())return null;
    const course={id:'course-'+id(),name:String(name).trim().slice(0,60),archived:false,data:normalize()};courses.push(course);switchCourse(course.id);return course;
  }
  function newSession(){if(state.pending)return false;sync();const session={id:id(),title:'新的对话',messages:[],scopeDocumentIds:[],createdAt:now()};state.sessions.unshift(session);state.sessionId=session.id;state.messages=[];state.selectedDocuments=[];state.draft='';state.followupIndex=null;persist();return session;}
  function selectSession(sessionId){if(state.pending)return false;const session=state.sessions.find(s=>s.id===sessionId);if(!session)return false;sync();state.sessionId=sessionId;state.messages=clone(session.messages);state.selectedDocuments=[...(session.scopeDocumentIds||[])];state.draft='';state.followupIndex=null;persist();return true;}
  function archive(courseId){const course=courses.find(c=>c.id===courseId);if(!course||state.pending||courses.filter(c=>!c.archived).length<2)return false;if(activeId===courseId)switchCourse(courses.find(c=>!c.archived&&c.id!==courseId).id);course.archived=true;persist();return true;}
  return{state,persist,newSession,selectSession,switchCourse,addCourse,archive,get courses(){return courses;},get error(){return error;},exportData(){sync();return JSON.stringify({version:3,exportedAt:now(),activeId,courses},null,2);},restoreCourse(courseId){const course=courses.find(c=>c.id===courseId);if(!course)return false;course.archived=false;return persist();}};
}
return{createStore,KEY,LEGACY};
});
