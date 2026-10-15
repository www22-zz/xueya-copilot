'use strict';

const {readBody}=require('./body.js');
const {json}=require('./json.js');
const {LIMITS}=require('../../shared/contracts/index.js');

function createParseHandler(rag){
  return(req,res)=>{
    const kind=new URL(req.url,'http://localhost').searchParams.get('type')||'pdf';
    if(!['pdf','docx'].includes(kind))return json(res,400,{ok:false,error:'UNSUPPORTED_DOCUMENT_TYPE'});
    readBody(req,res,LIMITS.fileBytes,async buffer=>{
      try{json(res,200,await rag.parseDocument({buffer,kind}));}
      catch{json(res,200,{ok:false,error:'PARSE_FAILED'});}
    });
  };
}

module.exports={createParseHandler};
