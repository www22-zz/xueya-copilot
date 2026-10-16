'use strict';
const z=require('zod');
const {result,createLimiter}=require('./policy.js');
const outbound=createLimiter(4);

/** Optional public metadata lookup. Only a DOI is sent; no course text, auth key or arbitrary URL. */
function registerReferenceTool(server,{enabled=false,fetchImpl=fetch}={}){
  if(!enabled)return;
  server.registerTool('lookup_reference',{
    description:'通过Crossref查询用户指定DOI的公开参考文献信息；不是课程原文证据。',
    inputSchema:z.object({doi:z.string().min(6).max(200).regex(/^10\.\d{4,9}\/[\x21-\x7e]+$/)}).strict(),
    annotations:{readOnlyHint:true,destructiveHint:false,idempotentHint:true,openWorldHint:true}
  },async({doi},context)=>{
    let release;
    try{
      context.mcpReq.signal.throwIfAborted();release=outbound.acquire();
      const response=await fetchImpl('https://api.crossref.org/works/'+encodeURIComponent(doi),{headers:{Accept:'application/json','User-Agent':'Xueya-Copilot/2.0 (learning-reference-lookup)'},redirect:'error',signal:AbortSignal.any([context.mcpReq.signal,AbortSignal.timeout(5000)])});
      if(!response.ok)throw new Error(response.status===404?'REFERENCE_NOT_FOUND':'REFERENCE_UNAVAILABLE');
      const reader=response.body.getReader();let text='',size=0;const decoder=new TextDecoder();
      try{while(true){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>262144)throw new Error('REFERENCE_TOO_LARGE');text+=decoder.decode(value,{stream:true});}text+=decoder.decode();}finally{await reader.cancel().catch(()=>{});}
      const data=JSON.parse(text).message;
      if(typeof data?.DOI!=='string'||data.DOI.toLowerCase()!==doi.toLowerCase())throw new Error('INVALID_REFERENCE');
      return result({doi:data.DOI,title:Array.isArray(data.title)?String(data.title[0]||'').slice(0,500):'',publisher:String(data.publisher||'').slice(0,300),year:data.published?.['date-parts']?.[0]?.[0]||null,url:'https://doi.org/'+encodeURIComponent(data.DOI),source:'Crossref public metadata',courseEvidence:false});
    }catch(error){return{content:[{type:'text',text:/^REFERENCE_|^INVALID_REFERENCE$|^MCP_BUSY$/.test(error.message)?error.message:'REFERENCE_UNAVAILABLE'}],isError:true};}
    finally{release?.();}
  });
}
module.exports={registerReferenceTool};
