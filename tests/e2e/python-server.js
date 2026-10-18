/* Test harness only: run the actual Python host against an optional local fake API. */
'use strict';
const {spawn}=require('node:child_process'),http=require('node:http'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const root=path.resolve(__dirname,'../..');
const python=process.env.XUEYA_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));

async function startPython({model,platform=false,dataDir}={}){
  let upstream;
  if(model){
    upstream=http.createServer(async(req,res)=>{
      const controller=new AbortController();res.on('close',()=>{if(!res.writableEnded)controller.abort();});
      try{
        const parts=[];for await(const chunk of req)parts.push(chunk);const value=JSON.parse(Buffer.concat(parts));
        if(value.stream){
          res.writeHead(200,{'Content-Type':'text/event-stream'});
          for await(const event of model.stream({messages:value.messages,signal:controller.signal})){
            const delta=event.type==='reasoning'?{reasoning_content:event.text}:{content:event.text};
            if(!res.destroyed)res.write('data: '+JSON.stringify({choices:[{delta}]})+'\n\n');
          }
          if(!res.destroyed)res.end('data: [DONE]\n\n');
        }else{
          const result=await model.generate({messages:value.messages,signal:controller.signal});res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({choices:[{message:{content:result.content}}],usage:result.usage}));
        }
      }catch{if(!res.headersSent)res.writeHead(500);res.end();}
    });
    await new Promise(resolve=>upstream.listen(0,'127.0.0.1',resolve));
  }
  const directory=dataDir||fs.mkdtempSync(path.join(os.tmpdir(),'xueya-python-e2e-'));
  let logs='',exit;
  const child=spawn(python,['-X','utf8','-m','backend.xueya.server'],{cwd:root,windowsHide:true,env:{...process.env,PYTHONUTF8:'1',PORT:'0',XUEYA_DATA_DIR:directory,XUEYA_PLATFORM_ENABLED:platform?'1':'0',MIMO_API_KEY:model?'controlled-test-only':'',MIMO_MODEL:model?'controlled':'no-paid-api',MIMO_BASE_URL:upstream?'http://127.0.0.1:'+upstream.address().port:'http://127.0.0.1:1'}});
  child.stdout.on('data',chunk=>{logs+=chunk;});child.stderr.on('data',chunk=>{logs+=chunk;});child.on('exit',code=>{exit=code;});
  const exited=new Promise(resolve=>child.on('exit',resolve));
  try{
    let info,base;
    for(let i=0;i<300;i++){
      if(exit!==undefined)throw new Error('Python host exited: '+logs);
      try{
        info=JSON.parse(fs.readFileSync(path.join(directory,'server.json'),'utf8'));base='http://127.0.0.1:'+info.port;
        const r=await fetch(base+'/api/health',{signal:AbortSignal.timeout(300)});if(r.ok)break;
      }catch{}
      await delay(50);
      if(i===299)throw new Error('Python host startup timed out: '+logs);
    }
    const bootstrap=platform?await fetch(base+'/api/platform/bootstrap').then(r=>r.json()):null;
    const headers=bootstrap?{'X-Xueya-Token':bootstrap.token}:{};
    return{base,directory,address:()=>({port:info.port}),async api(route){return fetch(base+'/api/platform'+route,{headers}).then(r=>r.json());},closeAllConnections(){},async close(callback){
      try{
        const r=await fetch(base+'/api/platform/shutdown',{method:'POST',headers:{'X-Xueya-Stop':info.stopToken},signal:AbortSignal.timeout(1000)});if(!r.ok)throw new Error('Python stop rejected');
        await Promise.race([exited,delay(7000).then(()=>{throw new Error('Python shutdown timed out: '+logs);})]);
        if(exit!==0)throw new Error('Python host failed: '+logs);
      }finally{
        if(exit===undefined)child.kill();
        if(upstream){upstream.closeAllConnections();await new Promise(resolve=>upstream.close(resolve));}
        if(!dataDir){const target=path.resolve(directory);if(!target.startsWith(path.join(os.tmpdir(),'xueya-python-e2e-')))throw new Error('Unsafe temp cleanup');fs.rmSync(target,{recursive:true,force:true});}
      }
      callback?.();
    }};
  }catch(error){child.kill();upstream?.closeAllConnections();upstream?.close();throw error;}
}
// Historical A/E acceptance intentionally exercises the expanded legacy surface.
// G1's separate browser acceptance verifies the default collapsed primary view.
async function expandLegacyRecords(page){
  await page.addInitScript(()=>{
    const expand=()=>document.querySelectorAll('.wb-legacy:not([open])').forEach(panel=>{
      panel.querySelector(':scope > summary')?.click();
    });
    new MutationObserver(expand).observe(document,{childList:true,subtree:true});
    document.addEventListener('DOMContentLoaded',expand,{once:true});
  });
}
module.exports={startPython,expandLegacyRecords};
