'use strict';
const path=require('node:path'),{randomUUID,createHash}=require('node:crypto');
const {openDatabase}=require('./database.js');
const {createRepository}=require('./repository.js');
const {createFileStore}=require('./files.js');
const {createResources}=require('./resources.js');
const {createJobQueue}=require('./jobs.js');
const {createBrowserMigration}=require('./migration.js');
const {createActionAuthority}=require('../mcp/actions.js');
const {createBusinessPorts}=require('../mcp/business-ports.js');
const L=require('../../shared/learning.js');

function createPlatform({dataDir,rag,userId='local-user',apiSlots=2,startJobs=true,parseArtifact=require('./file-worker.js').parseArtifact}={}){
  dataDir=path.resolve(dataDir);const db=openDatabase(path.join(dataDir,'workspace.sqlite'));
  const repository=createRepository(db),files=createFileStore(path.join(dataDir,'files')),resources=createResources({apiSlots});
  if(!repository.courses(userId).length)repository.ensureCourse(userId,{id:'course-default',name:'数据结构'});
  if(startJobs)for(const course of repository.courses(userId))for(const run of repository.all({userId,courseId:course.id},'run').filter(r=>r.status==='running')){
    if(!course.archived)repository.put({scope:{userId,courseId:course.id},kind:'run',entityId:run.id,value:{...run,status:'interrupted',recoveredAt:new Date().toISOString()}});
  }
  if(startJobs)db.prepare("UPDATE invocations SET status='unknown' WHERE status='pending'").run();
  const jobs=createJobQueue({repository,resources}),authority=createActionAuthority({repository}),migration=createBrowserMigration(repository);
  function scope(courseId){const s={userId,courseId};repository.requireCourse(s);return s;}
  function document(s,id){const row=repository.read({scope:s,kind:'document',entityId:id});if(!row)throw new Error('DOCUMENT_NOT_FOUND');return{...row.value,id,version:row.version};}
  jobs.register('parse-document',async({scope:s,input},{signal,progress,checkpoint,commit})=>{
    const doc=document(s,input.documentId);if(doc.status==='已解析，可检索')return{documentId:doc.id,version:doc.version};
    signal.throwIfAborted();progress({percent:10,label:'正在读取原件'});const buffer=files.read(doc.fileHash);checkpoint({documentId:doc.id,fileHash:doc.fileHash});
    const ingested=await parseArtifact({buffer,kind:doc.kind,document:{id:doc.id,name:doc.name}},{signal});signal.throwIfAborted();progress({percent:80,label:'正在保存原文与检索记录'});
    const save=()=>{const current=document(s,doc.id);if(current.status==='已解析，可检索')return{documentId:doc.id,version:current.version};if(current.version!==doc.version)throw new Error('VERSION_CONFLICT');
      for(const source of ingested.sources)repository.put({scope:s,kind:'source',entityId:source.id,value:{...source,documentId:doc.id}});
      const saved=repository.put({scope:s,kind:'document',entityId:doc.id,expectedVersion:doc.version,value:{...doc,status:'已解析，可检索',chunks:ingested.sources,meta:ingested.sources.length+'个原文片段',originalAvailable:true}});return{documentId:doc.id,version:saved.version};};
    const result=commit(save);progress({percent:100,label:'原文与检索记录已保存'});return result;
  });
  function upload(s,{name,buffer,previousDocumentId,idempotencyKey}){
    repository.requireCourse(s);const kind=name.split('.').at(-1).toLowerCase();if(!['txt','md','pdf','docx'].includes(kind))throw new Error('UNSUPPORTED_FILE_TYPE');if(name.length>200)throw new Error('INVALID_FILE_NAME');
    if(['txt','md'].includes(kind)&&buffer.length>1048576)throw new Error('FILE_TOO_LARGE');
    const requestHash=createHash('sha256').update(buffer).update(JSON.stringify({name,previousDocumentId:previousDocumentId||null})).digest('hex');
    const prior=db.prepare("SELECT * FROM jobs WHERE user_id=? AND course_id=? AND type='parse-document' AND idempotency_key=?").get(s.userId,s.courseId,idempotencyKey);if(prior){if(JSON.parse(prior.input).requestHash!==requestHash)throw new Error('IDEMPOTENCY_CONFLICT');return jobs.get(prior.id,s.userId);}
    const file=files.put(buffer),id='doc-'+randomUUID();
    return repository.transaction(()=>{
      if(previousDocumentId){const previous=document(s,previousDocumentId);repository.put({scope:s,kind:'document',entityId:previous.id,value:{...previous,superseded:true},expectedVersion:previous.version});for(const source of repository.all(s,'source').filter(source=>source.documentId===previous.id))repository.put({scope:s,kind:'source',entityId:source.id,value:source,deleted:true});}
      repository.put({scope:s,kind:'document',entityId:id,expectedVersion:0,value:{id,name,kind,fileHash:file.hash,size:file.size,status:'等待解析',chunks:[],tags:[],meta:'后台处理中',originalAvailable:true,remote:true}});
      return jobs.submit(s.userId,{type:'parse-document',courseId:s.courseId,input:{documentId:id,requestHash},idempotencyKey,resource:'cpu'});
    });
  }
  const learning={
    async analyzeProgress({scope:s}){const records=repository.all(s,'attempt'),questions=repository.all(s,'question'),weak=L.wrongQuestions(records,questions);return{total:records.length,correct:records.filter(r=>r.correct).length,weakTopics:[...new Set(weak.map(q=>q.topic))],dueTopics:L.memoryCards(records,L.today(),questions).filter(c=>c.due).map(c=>c.topic)};},
    async buildReviewPlan({scope:s}){const course=repository.getWorkspace(s.userId)?.data.courses.find(c=>c.id===s.courseId),data=course?.data||{},examDate=data.examDate||L.addDays(L.today(),21),minutes=data.minutes||30;return{examDate,minutes,days:L.buildPlan(examDate,minutes,repository.all(s,'attempt'),L.today(),repository.all(s,'question'))};}
  };
  function services(s){repository.requireCourse(s);return createBusinessPorts({repository,rag,learning});}
  if(startJobs)jobs.start();
  return{dataDir,userId,db,repository,files,resources,jobs,authority,migration,scope,services,document,upload,
    async close(){await jobs.stop();db.close();}
  };
}
module.exports={createPlatform};
