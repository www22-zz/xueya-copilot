'use strict';
const fs=require('node:fs'),path=require('node:path'),{createHash,randomUUID}=require('node:crypto');
function createFileStore(root,{maxBytes=10485760}={}){
  root=path.resolve(root);fs.mkdirSync(root,{recursive:true});
  function location(hash){if(!/^[a-f0-9]{64}$/.test(hash))throw new Error('INVALID_FILE_HASH');const dir=path.join(root,hash.slice(0,2));if(fs.existsSync(dir)&&fs.lstatSync(dir).isSymbolicLink())throw new Error('UNSAFE_FILE_PATH');return path.join(dir,hash);}
  function read(hash){const file=location(hash);if(fs.lstatSync(file).isSymbolicLink())throw new Error('UNSAFE_FILE_PATH');const data=fs.readFileSync(file);if(createHash('sha256').update(data).digest('hex')!==hash)throw new Error('FILE_HASH_MISMATCH');return data;}
  return{root,read,
    put(buffer){if(!Buffer.isBuffer(buffer)||!buffer.length)throw new Error('EMPTY_FILE');if(buffer.length>maxBytes)throw new Error('FILE_TOO_LARGE');const hash=createHash('sha256').update(buffer).digest('hex'),file=location(hash);fs.mkdirSync(path.dirname(file),{recursive:true});if(!fs.existsSync(file)){const temp=file+'.'+randomUUID()+'.tmp';try{fs.writeFileSync(temp,buffer,{flag:'wx',mode:0o600});const fd=fs.openSync(temp,'r+');try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}fs.renameSync(temp,file);}finally{if(fs.existsSync(temp))fs.unlinkSync(temp);}}else read(hash);return{hash,size:buffer.length};},
    inventory(){return fs.readdirSync(root,{withFileTypes:true}).filter(d=>d.isDirectory()&&/^[a-f0-9]{2}$/.test(d.name)).flatMap(d=>fs.readdirSync(path.join(root,d.name)).filter(h=>/^[a-f0-9]{64}$/.test(h)).map(hash=>({hash,size:fs.statSync(location(hash)).size})));},
    removeUnreferenced(hash,referenced){if(referenced.has(hash))throw new Error('FILE_STILL_REFERENCED');const file=location(hash);if(fs.existsSync(file)){if(fs.lstatSync(file).isSymbolicLink())throw new Error('UNSAFE_FILE_PATH');fs.unlinkSync(file);}}
  };
}
module.exports={createFileStore};
