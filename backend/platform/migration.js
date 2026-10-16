'use strict';
const {randomUUID}=require('node:crypto');
const C=require('../../shared/contracts/platform.js');
const {hash}=require('./repository.js');
function createBrowserMigration(repository,{now=Date.now}={}){
  const previews=new Map();
  function counts(value){return value.courses.reduce((n,c)=>({courses:n.courses+1,documents:n.documents+(c.data.documents||[]).length,messages:n.messages+Math.max((c.data.messages||[]).length,(c.data.sessions||[]).reduce((sum,s)=>sum+(s.messages||[]).length,0)),records:n.records+(c.data.records||[]).length,cards:n.cards+(c.data.cards||[]).length}),{courses:0,documents:0,messages:0,records:0,cards:0});}
  return{
    preview(userId,input){
      const workspace=C.workspace.parse(input.workspace),raw=input.raw||{};if(Buffer.byteLength(JSON.stringify({workspace,raw}))>24000000)throw new Error('IMPORT_TOO_LARGE');
      const valueHash=hash({workspace,raw}),existing=repository.db.prepare('SELECT * FROM imports WHERE user_id=? AND hash=?').get(userId,valueHash);
      for(const [id,p] of previews)if(p.expiresAt<=now())previews.delete(id);if(previews.size>=20)throw new Error('IMPORT_CAPACITY');
      const preview={id:randomUUID(),hash:valueHash,counts:counts(workspace),expectedVersion:repository.getWorkspace(userId)?.version||0,expiresAt:now()+300000,alreadyImported:!!existing};previews.set(preview.id,{userId,workspace,raw,...preview});return preview;
    },
    apply(userId,{id,hash:expectedHash}){
      const p=previews.get(id);if(!p||p.userId!==userId)throw new Error('IMPORT_NOT_FOUND');if(p.expiresAt<=now())throw new Error('IMPORT_EXPIRED');if(p.hash!==expectedHash)throw new Error('IMPORT_CHANGED');
      const old=repository.db.prepare('SELECT * FROM imports WHERE user_id=? AND hash=?').get(userId,p.hash);if(old)return{alreadyImported:true,version:old.workspace_version,counts:p.counts};
      return repository.transaction(()=>{const previous=repository.getWorkspace(userId),saved=repository.saveWorkspace(userId,p.workspace,p.expectedVersion);
      repository.db.prepare('INSERT INTO imports VALUES(?,?,?,?,?)').run(userId,p.hash,JSON.stringify({raw:p.raw,workspace:p.workspace,previous}),saved.version,C.now());return{version:saved.version,counts:p.counts,backupId:p.hash};});
    },
    backup(userId,backupId){const row=repository.db.prepare('SELECT backup FROM imports WHERE user_id=? AND hash=?').get(userId,backupId);if(!row)throw new Error('IMPORT_NOT_FOUND');return JSON.parse(row.backup);}
  };
}
module.exports={createBrowserMigration};
