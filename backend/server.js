'use strict';
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {randomUUID,randomBytes}=require('node:crypto');
const {loadConfig}=require('./config.js');
const {createApp}=require('./app.js');
const {sanitizeSources:normalizeSources}=require('../shared/contracts/index.js');
const {sources}=require('../shared/fixtures/course.js');
const config=loadConfig(),main=require.main===module;
let identity,pidFile;
if(main){
  fs.mkdirSync(config.platform.dataDir,{recursive:true});pidFile=path.join(config.platform.dataDir,'server.json');
  if(fs.existsSync(pidFile)){const old=JSON.parse(fs.readFileSync(pidFile));try{process.kill(old.pid,0);throw new Error('ANOTHER_PLATFORM_INSTANCE_RUNNING');}catch(error){if(error.code!=='ESRCH')throw error;}fs.unlinkSync(pidFile);}
  identity={pid:process.pid,port:config.port,instanceId:randomUUID(),stopToken:randomBytes(32).toString('hex')};fs.writeFileSync(pidFile,JSON.stringify(identity),{flag:'wx',mode:0o600});
}
// Importing compatibility exports never opens the user's database or starts workers.
const app=createApp({config:main?config:{...config,platform:undefined}}),server=http.createServer(app);
server.headersTimeout=10000;server.requestTimeout=30000;
const sanitizeSources=input=>normalizeSources(input,sources);
if(main){
  let stopping=false;app.instanceId=identity.instanceId;
  async function stop(){if(stopping)return;stopping=true;server.close();try{await app.close();}catch(error){console.error(error.message);}finally{if(fs.existsSync(pidFile)&&JSON.parse(fs.readFileSync(pidFile)).instanceId===identity.instanceId)fs.unlinkSync(pidFile);server.closeAllConnections();}}
  server.prependListener('request',(req,res)=>{if(req.url==='/api/platform/shutdown'&&req.method==='POST'&&req.headers['x-xueya-stop']===identity.stopToken){res.writeHead(200,{'Content-Type':'application/json'});res.end('{"ok":true}');void stop();}});
  server.on('error',error=>{console.error(error.code||'SERVER_ERROR');void stop();process.exitCode=1;});
  server.listen(config.port,'127.0.0.1',()=>{identity.port=server.address().port;fs.writeFileSync(pidFile,JSON.stringify(identity),{mode:0o600});console.log('Xueya Copilot running at http://127.0.0.1:'+identity.port);});
  process.on('SIGINT',()=>void stop());process.on('SIGTERM',()=>void stop());
}
module.exports={server,sanitizeSources};
