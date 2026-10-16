'use strict';
const z=require('zod');
const scopeSchema=z.object({userId:z.string().min(1).max(150),courseId:z.string().min(1).max(150)}).strict();
const id=z.string().min(1).max(150);
const page=z.object({cursor:z.string().max(300).optional(),limit:z.number().int().min(1).max(50).default(20)}).strict();
const result=data=>({content:[{type:'text',text:JSON.stringify(data)}],structuredContent:data});
function bytes(value){try{return Buffer.byteLength(JSON.stringify(value));}catch{throw new Error('INVALID_JSON');}}
function checkResult(value,maxBytes=131072){
  if(!value||!Array.isArray(value.content)||value.content.some(b=>!b||b.type!=='text'||typeof b.text!=='string')||value.content.length>16)throw new Error('INVALID_TOOL_RESULT');
  if(bytes(value)>maxBytes)throw new Error('TOOL_RESULT_TOO_LARGE');
  return value;
}
function createLimiter(max=4){
  if(!Number.isInteger(max)||max<1)throw new Error('INVALID_CONCURRENCY');
  let active=0,peak=0,total=0;
  return{acquire(){if(active>=max)throw new Error('MCP_BUSY');active++;total++;peak=Math.max(peak,active);let done=false;return()=>{if(!done){done=true;active--;}};},stats:()=>({active,peak,total,max})};
}
module.exports={scopeSchema,id,page,result,bytes,checkResult,createLimiter};
