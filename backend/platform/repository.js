'use strict';
const {randomUUID,createHash}=require('node:crypto');
const {transaction}=require('./database.js');
const C=require('../../shared/contracts/platform.js');
const L=require('../../shared/learning.js');
const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const parse=value=>value?JSON.parse(value):null;
function createRepository(db){
  const scope=C.scope.parse;
  function requireCourse(s,{allowArchived=false}={}){s=scope(s);const row=db.prepare('SELECT * FROM courses WHERE user_id=? AND id=?').get(s.userId,s.courseId);if(!row)throw new Error('COURSE_NOT_FOUND');if(row.archived&&!allowArchived)throw new Error('COURSE_ARCHIVED');return row;}
  function read({scope:s,kind,entityId,includeDeleted=false}){requireCourse(s,{allowArchived:true});const row=db.prepare('SELECT * FROM entities WHERE user_id=? AND course_id=? AND kind=? AND id=?').get(s.userId,s.courseId,kind,entityId);return row&&(!row.deleted||includeDeleted)?{id:row.id,version:row.version,value:parse(row.data),createdAt:row.created_at,updatedAt:row.updated_at,deleted:!!row.deleted}:null;}
  function put({scope:s,kind,entityId,value,expectedVersion,deleted=false}){
    return transaction(db,()=>{
    requireCourse(s);C.kind.parse(kind);C.id.parse(entityId);const old=read({scope:s,kind,entityId,includeDeleted:true});
    if(expectedVersion!==undefined&&(old?.version||0)!==expectedVersion)throw new Error('VERSION_CONFLICT');
    const at=C.now(),version=(old?.version||0)+1,data=JSON.stringify(value);if(Buffer.byteLength(data)>16000000)throw new Error('ENTITY_TOO_LARGE');
    db.prepare('INSERT INTO entities VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,course_id,kind,id) DO UPDATE SET version=excluded.version,data=excluded.data,updated_at=excluded.updated_at,deleted=excluded.deleted').run(s.userId,s.courseId,kind,entityId,version,data,old?.createdAt||at,at,+deleted);
    db.prepare('INSERT INTO revisions VALUES(?,?,?,?,?,?,?)').run(s.userId,s.courseId,kind,entityId,version,data,at);return{version,value};});
  }
  function list({scope:s,kind,cursor,limit=20}){
    requireCourse(s,{allowArchived:true});C.kind.parse(kind);limit=Math.min(50,Math.max(1,limit));let after='';
    if(cursor){let c;try{c=JSON.parse(Buffer.from(cursor,'base64url').toString());}catch{throw new Error('INVALID_CURSOR');}if(c.userId!==s.userId||c.courseId!==s.courseId||c.kind!==kind||typeof c.after!=='string')throw new Error('INVALID_CURSOR');after=c.after;}
    const rows=db.prepare('SELECT * FROM entities WHERE user_id=? AND course_id=? AND kind=? AND deleted=0 AND id>? ORDER BY id LIMIT ?').all(s.userId,s.courseId,kind,after,limit+1);
    const items=rows.slice(0,limit).map(row=>({id:row.id,...parse(row.data),version:row.version}));return{items,nextCursor:rows.length>limit?Buffer.from(JSON.stringify({...s,kind,after:items.at(-1).id})).toString('base64url'):null};
  }
  function all(s,kind){requireCourse(s,{allowArchived:true});return db.prepare('SELECT * FROM entities WHERE user_id=? AND course_id=? AND kind=? AND deleted=0 ORDER BY id').all(s.userId,s.courseId,kind).map(row=>({id:row.id,...parse(row.data),version:row.version}));}
  function pageItems({scope:s,cursor,limit=20},items,label){
    const binding=hash({scope:s,label});let after='';limit=Math.min(50,Math.max(1,limit));
    if(cursor){let parsed;try{parsed=parse(Buffer.from(cursor,'base64url').toString());}catch{throw new Error('INVALID_CURSOR');}if(parsed?.binding!==binding||typeof parsed.after!=='string')throw new Error('INVALID_CURSOR');after=parsed.after;}
    const remaining=items.filter(item=>String(item.id)>after).sort((a,b)=>String(a.id)<String(b.id)?-1:String(a.id)>String(b.id)?1:0);
    const page=remaining.slice(0,limit);return{items:page,nextCursor:remaining.length>limit?Buffer.from(JSON.stringify({binding,after:page.at(-1).id})).toString('base64url'):null};
  }
  function ensureCourse(userId,course){C.id.parse(userId);C.id.parse(course.id);db.prepare('INSERT INTO courses(user_id,id,name,archived) VALUES(?,?,?,?) ON CONFLICT(user_id,id) DO UPDATE SET name=excluded.name,archived=excluded.archived,version=courses.version+1').run(userId,course.id,String(course.name).slice(0,100),+!!course.archived);}
  function project(userId,workspace){
    for(const course of workspace.courses){ensureCourse(userId,{...course,archived:false});const s={userId,courseId:course.id},data=course.data;
      const sources=[...(course.id==='course-default'?L.sources:[]),...(data.documents||[]).filter(d=>!d.superseded&&!d.deleted).flatMap(d=>d.chunks||[])];
      const groups={source:sources,note:(data.cards||[]).map(n=>({...n,content:n.content??n.text})),question:[...(course.id==='course-default'?L.questions:[]),...(data.bank||[])],attempt:data.records||[],plan:(data.plan||[]).map((d,i)=>({...d,id:d.id||'day-'+i})),session:data.sessions||[],event:data.reviewLog||[]};
      for(const [kind,items] of Object.entries(groups)){
        const seen=new Set();
        for(let i=0;i<items.length;i++){const item=items[i];if(!item||typeof item!=='object')continue;const entityId=String(item.id||kind+'-'+hash(item).slice(0,30)+'-'+i);seen.add(entityId);const old=read({scope:s,kind,entityId});if(!old||hash(old.value)!==hash(item))put({scope:s,kind,entityId,value:item});}
        for(const previous of all(s,kind))if(!seen.has(previous.id))put({scope:s,kind,entityId:previous.id,value:previous,deleted:true});
      }
      for(const document of data.documents||[]){if(document?.remote)continue;if(document?.id){const old=read({scope:s,kind:'document',entityId:document.id}),value={...old?.value,...document,...(old?.value.fileHash?{fileHash:old.value.fileHash,originalAvailable:true}:{})};if(!old||hash(old.value)!==hash(value))put({scope:s,kind:'document',entityId:document.id,value});}}
      ensureCourse(userId,course);
    }
  }
  function getWorkspace(userId){const row=db.prepare('SELECT * FROM workspaces WHERE user_id=?').get(userId);return row?{version:row.version,data:parse(row.data),updatedAt:row.updated_at}:null;}
  function saveWorkspace(userId,input,expectedVersion=0){const value=C.workspace.parse(input);return transaction(db,()=>{const old=getWorkspace(userId);if((old?.version||0)!==expectedVersion)throw new Error('VERSION_CONFLICT');const version=expectedVersion+1;project(userId,value);db.prepare('INSERT INTO workspaces VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET version=excluded.version,data=excluded.data,updated_at=excluded.updated_at').run(userId,version,JSON.stringify(value),C.now());return{version,data:value};});}
  function patchWorkspaceEntity(s,kind,entityId,value){
    const ws=getWorkspace(s.userId);if(!ws)return;const course=ws.data.courses.find(c=>c.id===s.courseId);if(!course)return;
    if(kind==='plan'){course.data.plan=value.days.map((day,i)=>({...day,id:entityId+'-day-'+i,tasks:day.tasks.map((task,j)=>({...task,id:entityId+'-task-'+i+'-'+j}))}));course.data.planVersion=(course.data.planVersion||0)+1;}
    else{const field=kind==='note'?'cards':'bank';course.data[field]=course.data[field]||[];const item=kind==='note'?{...value,id:entityId,text:value.content,sources:(value.sourceIds||[]).map(sourceId=>readSource({scope:s,sourceId})).filter(Boolean),createdAt:C.now()}:{...value,id:entityId,type:'short',answerText:value.answer,sourceId:value.sourceIds[0],topic:'课程练习',version:1};const i=course.data[field].findIndex(n=>n.id===entityId);if(i<0)course.data[field].unshift(item);else course.data[field][i]=item;}
    db.prepare('UPDATE workspaces SET version=version+1,data=?,updated_at=? WHERE user_id=?').run(JSON.stringify(ws.data),C.now(),s.userId);
  }
  function readSource({scope:s,sourceId}){const row=read({scope:s,kind:'source',entityId:sourceId});return row?{id:sourceId,...row.value,version:row.version}:null;}
  return{
    db,requireCourse,ensureCourse,read,put,list,all,getWorkspace,saveWorkspace,
    courses:userId=>db.prepare('SELECT id,name,archived,version FROM courses WHERE user_id=? ORDER BY id').all(userId).map(c=>({...c,archived:!!c.archived})),
    listSources:({scope:s})=>all(s,'source'),readSource,
    listNotes:args=>list({...args,kind:'note'}),listQuestionDrafts:args=>list({...args,kind:'question'}),listAttempts:args=>list({...args,kind:'attempt'}),listReviews:args=>list({...args,kind:'review'}),listPlans:args=>list({...args,kind:'plan'}),listConcepts:args=>list({...args,kind:'concept'}),
    listWrongQuestions:args=>pageItems(args,L.wrongQuestions(all(args.scope,'attempt'),all(args.scope,'question')),'wrong-questions'),
    listSections:args=>pageItems(args,all(args.scope,'document').filter(d=>!d.superseded),'sections'),
    readSection:args=>pageItems(args,all(args.scope,'source').filter(source=>source.documentId===args.sectionId),'section:'+args.sectionId),
    applyConfirmed(request,{signal}={}){signal?.throwIfAborted();return transaction(db,()=>{
      const {scope:s,actionId,kind,entityId,expectedVersion,after,references,audit}=request;requireCourse(s);
      const prior=db.prepare('SELECT receipt FROM receipts WHERE user_id=? AND course_id=? AND action_id=?').get(s.userId,s.courseId,actionId);if(prior)return parse(prior.receipt);
      for(const ref of references||[]){const source=readSource({scope:s,sourceId:ref.sourceId});if(!source||source.version!==ref.version||hash(source.quote)!==ref.quoteHash)throw new Error('SOURCE_VERSION_CONFLICT');}
      const saved=put({scope:s,kind,entityId,value:after,expectedVersion}),auditId=randomUUID();
      db.prepare('INSERT INTO audits VALUES(?,?,?,?,?,?)').run(auditId,s.userId,s.courseId,actionId,JSON.stringify(audit),C.now());const receipt={actionId,version:saved.version,auditId};db.prepare('INSERT INTO receipts VALUES(?,?,?,?)').run(s.userId,s.courseId,actionId,JSON.stringify(receipt));
      patchWorkspaceEntity(s,kind,entityId,after);return receipt;
    });},
    transaction:fn=>transaction(db,fn),hash
  };
}
module.exports={createRepository,hash};
