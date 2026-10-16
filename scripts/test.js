/* Test orchestration only; Python backend and browser JS are checked separately. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
function run(args){
  const result=spawnSync(process.execPath,args,{cwd:root,stdio:'inherit',windowsHide:true});
  if(result.error)throw result.error;
  if(result.status!==0)process.exit(result.status??1);
}
if(!process.argv.includes('--frontend'))run(['scripts/run-python.js','-m','pytest','-q']);
const files=['tests/unit','tests/integration'].flatMap(dir=>fs.readdirSync(path.join(root,dir)).filter(name=>name.endsWith('.test.js')).sort().map(name=>dir+'/'+name));
run(['--test',...files]);
