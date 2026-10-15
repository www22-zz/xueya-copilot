'use strict';

const fs=require('node:fs');
const path=require('node:path');
const {json}=require('./json.js');
const MIME={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.json':'application/json; charset=utf-8'};
const PUBLIC_SHARED=new Set(['/shared/learning.js','/shared/contracts/index.js','/shared/fixtures/course.js','/shared/rag/index.js','/shared/agent/local-answer.js','/shared/agent/sse.js']);

function createStaticHandler(root){
  const frontendRoot=path.join(root,'frontend');
  return function staticFile(req,res){
    let requested;
    try{requested=decodeURIComponent(new URL(req.url,'http://localhost').pathname);}
    catch{return json(res,400,{error:'Invalid path'});}
    if(requested==='/')requested='/index.html';
    const isShared=PUBLIC_SHARED.has(requested);
    const isFrontend=requested==='/index.html'
      ||/^\/css\/(?:[a-zA-Z0-9_-]+\/)*[a-zA-Z0-9_-]+\.css$/.test(requested)
      ||/^\/js\/(?:[a-zA-Z0-9_-]+\/)*[a-zA-Z0-9_-]+\.js$/.test(requested)
      ||/^\/assets\/[a-zA-Z0-9_-]+\.(svg|png|jpg|woff2)$/.test(requested);
    if(!isShared&&!isFrontend){res.writeHead(404,{'Content-Type':'text/plain; charset=utf-8'});res.end('Not found');return;}
    const file=path.resolve(isShared?root:frontendRoot,'.'+requested);
    if(!file.startsWith((isShared?root:frontendRoot)+path.sep))return json(res,403,{error:'Forbidden'});
    fs.stat(file,(error,stat)=>{
      if(error||!stat.isFile()){res.writeHead(404);res.end('Not found');return;}
      res.writeHead(200,{'Content-Type':MIME[path.extname(file)]||'application/octet-stream','Cache-Control':'no-cache','X-Content-Type-Options':'nosniff'});
      if(req.method==='HEAD')res.end();else fs.createReadStream(file).pipe(res);
    });
  };
}

module.exports={createStaticHandler};
