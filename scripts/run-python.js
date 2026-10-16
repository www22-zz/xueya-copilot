/* Optional npm convenience only. The production backend runs entirely in Python. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),venv=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const python=process.env.XUEYA_PYTHON||(fs.existsSync(venv)?venv:'python');
const result=spawnSync(python,['-X','utf8',...process.argv.slice(2)],{cwd:root,stdio:'inherit',windowsHide:true});
if(result.error)console.error('Python unavailable. Run scripts/start.ps1 or install Python 3.11+ and requirements.lock.');
process.exitCode=result.status??1;
