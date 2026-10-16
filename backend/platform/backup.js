'use strict';
const fs=require('node:fs'),path=require('node:path'),{createHash,randomUUID}=require('node:crypto');
const {backup,DatabaseSync}=require('node:sqlite');
const sum=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
async function createBackup(platform,destination){
  destination=path.resolve(destination);if(fs.existsSync(destination))throw new Error('BACKUP_DESTINATION_EXISTS');fs.mkdirSync(destination,{recursive:true});
  await backup(platform.db,path.join(destination,'workspace.sqlite'));
  const entries=[];
  for(const file of platform.files.inventory()){const target=path.join(destination,'files',file.hash.slice(0,2),file.hash);fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,platform.files.read(file.hash),{flag:'wx'});entries.push({path:'files/'+file.hash.slice(0,2)+'/'+file.hash,sha256:sum(target)});}
  entries.unshift({path:'workspace.sqlite',sha256:sum(path.join(destination,'workspace.sqlite'))});
  const manifest={version:1,createdAt:new Date().toISOString(),entries};fs.writeFileSync(path.join(destination,'manifest.json'),JSON.stringify(manifest,null,2),{flag:'wx'});return{destination,files:entries.length};
}
async function restoreBackup(source,destination){
  source=path.resolve(source);destination=path.resolve(destination);if(fs.existsSync(destination))throw new Error('RESTORE_REQUIRES_NEW_DIRECTORY');
  const manifest=JSON.parse(fs.readFileSync(path.join(source,'manifest.json'),'utf8'));if(manifest.version!==1||!Array.isArray(manifest.entries)||!manifest.entries.some(e=>e.path==='workspace.sqlite'))throw new Error('INVALID_BACKUP');
  for(const entry of manifest.entries){if(!/^(workspace\.sqlite|files\/[a-f0-9]{2}\/[a-f0-9]{64})$/.test(entry.path))throw new Error('UNSAFE_BACKUP_PATH');const file=path.join(source,entry.path);if(fs.lstatSync(file).isSymbolicLink()||sum(file)!==entry.sha256)throw new Error('BACKUP_CHECKSUM_MISMATCH');}
  const probe=new DatabaseSync(path.join(source,'workspace.sqlite'),{readOnly:true});try{if(probe.prepare('PRAGMA integrity_check').get().integrity_check!=='ok')throw new Error('DATABASE_INTEGRITY_FAILED');}finally{probe.close();}
  const staging=destination+'.restore-'+randomUUID();fs.mkdirSync(staging,{recursive:true});
  for(const entry of manifest.entries){const target=path.join(staging,entry.path);fs.mkdirSync(path.dirname(target),{recursive:true});fs.copyFileSync(path.join(source,entry.path),target,fs.constants.COPYFILE_EXCL);}
  for(let attempt=0;;attempt++){
    try{await fs.promises.rename(staging,destination);break;}
    catch(error){if(attempt>=5||!['EPERM','EBUSY','EACCES'].includes(error.code)||fs.existsSync(destination))throw error;await new Promise(resolve=>setTimeout(resolve,20*2**attempt));}
  }
  return{destination,files:manifest.entries.length};
}
module.exports={createBackup,restoreBackup};
