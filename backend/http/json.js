'use strict';

function json(res,status,data){
  if(res.writableEnded)return;
  const body=JSON.stringify(data);
  res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Content-Length':Buffer.byteLength(body),'Cache-Control':'no-store'});
  res.end(body);
}

module.exports={json};
