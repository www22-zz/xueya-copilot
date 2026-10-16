'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {loadConfig}=require('../config.js');
const {createRagService}=require('../rag/index.js');
const {createPlatform}=require('./index.js');
const {createBackup,restoreBackup}=require('./backup.js');
async function main(){
  const [command='doctor',argument,target]=process.argv.slice(2),config=loadConfig();
  if(command==='restore'){if(!argument||!target)throw new Error('Usage: npm run restore -- BACKUP NEW_DATA_DIRECTORY');console.log(JSON.stringify(await restoreBackup(argument,target)));return;}
  if(command==='doctor'){
    const details={node:process.version,nodeSupported:Number(process.versions.node.split('.')[0])>=24,dataDir:config.platform.dataDir,model:config.ai.model,apiConfigured:!!config.ai.apiKey,inference:'external-api-only',pythonRequired:false,gpuRequired:false};
    try{const {DatabaseSync}=require('node:sqlite'),db=new DatabaseSync(':memory:');details.sqlite=db.prepare('select sqlite_version() as version').get().version;db.close();}catch{details.sqlite='unavailable';}
    console.log(JSON.stringify(details,null,2));if(!details.nodeSupported||details.sqlite==='unavailable')process.exitCode=1;return;
  }
  if(command==='stop'){
    const pidFile=path.join(config.platform.dataDir,'server.json');if(!fs.existsSync(pidFile))throw new Error('SERVER_PID_NOT_FOUND');const info=JSON.parse(fs.readFileSync(pidFile));
    const response=await fetch('http://127.0.0.1:'+info.port+'/api/health',{signal:AbortSignal.timeout(1000)}).then(r=>r.json());if(response.instanceId!==info.instanceId)throw new Error('SERVER_IDENTITY_MISMATCH');
    const stopped=await fetch('http://127.0.0.1:'+info.port+'/api/platform/shutdown',{method:'POST',headers:{'X-Xueya-Stop':info.stopToken},signal:AbortSignal.timeout(3000)});if(!stopped.ok)throw new Error('STOP_REJECTED');console.log('已请求安全停止');return;
  }
  if(command==='backup'){
    if(!argument)throw new Error('Usage: npm run backup -- NEW_BACKUP_DIRECTORY');
    const {DatabaseSync}=require('node:sqlite'),db=new DatabaseSync(path.join(config.platform.dataDir,'workspace.sqlite'),{readOnly:true});
    try{console.log(JSON.stringify(await createBackup({db,files:require('./files.js').createFileStore(path.join(config.platform.dataDir,'files'))},argument)));}finally{db.close();}return;
  }
  const platform=createPlatform({...config.platform,rag:createRagService(),startJobs:false});
  try{
    if(command==='init'){console.log(JSON.stringify({ok:true,dataDir:platform.dataDir,courses:platform.repository.courses(platform.userId)}));return;}
    if(command==='export'){if(!argument||fs.existsSync(argument))throw new Error('EXPORT_REQUIRES_NEW_FILE');fs.writeFileSync(argument,JSON.stringify({schemaVersion:1,workspace:platform.repository.getWorkspace(platform.userId),courses:platform.repository.courses(platform.userId)},null,2),{flag:'wx'});console.log('导出完成');return;}
    if(command==='gc'){const refs=new Set();for(const row of platform.db.prepare("SELECT data FROM revisions WHERE kind='document'").all()){const hash=JSON.parse(row.data).fileHash;if(hash)refs.add(hash);}const candidates=platform.files.inventory().filter(file=>!refs.has(file.hash));if(target==='--apply')for(const file of candidates)platform.files.removeUnreferenced(file.hash,refs);console.log(JSON.stringify({dryRun:target!=='--apply',candidates}));return;}
    throw new Error('UNKNOWN_COMMAND');
  }finally{await platform.close();}
}
if(require.main===module)main().catch(error=>{console.error(error.message);process.exitCode=1;});
module.exports={main};
