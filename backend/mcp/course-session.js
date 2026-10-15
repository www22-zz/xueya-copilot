'use strict';

const path=require('node:path');
const z=require('zod');
const {connectStdio}=require('./stdio-client.js');
const {createToolGateway}=require('./index.js');
const {normalizeContext}=require('../../shared/agent/context.js');

const argumentsByTool={
  search_materials:z.object({query:z.string().min(1).max(4000),limit:z.number().int().min(1).max(6).optional()}).strict(),
  read_source:z.object({sourceId:z.string().min(1).max(150)}).strict(),
  analyze_progress:z.object({}).strict(),
  build_review_plan:z.object({}).strict()
};

async function createCourseSession(input,{signal,timeoutMs=5000,connect=connectStdio}={}){
  const context=normalizeContext(input);
  const adapter=await connect({command:process.execPath,args:[path.join(__dirname,'course-server.js')],cwd:path.resolve(__dirname,'../..'),timeoutMs,signal});
  try{
    const available=await adapter.listTools();
    const gateway=createToolGateway({timeoutMs});
    for(const [name,schema] of Object.entries(argumentsByTool)){
      const remote=available.find(tool=>tool.name===name);
      if(!remote)throw new Error('MCP_TOOL_MISSING');
      gateway.registerTool({name:'course__'+name,description:remote.description,inputSchema:z.toJSONSchema(schema)},async(args,options)=>{
        const parsed=schema.parse(args);
        const bound=name==='search_materials'||name==='read_source'
          ?{...parsed,sources:context.library}
          :{questions:context.questions,records:context.records,baseDate:context.baseDate,...(name==='build_review_plan'?{examDate:context.examDate,minutes:context.minutes}:{})};
        return adapter.callTool(name,bound,options);
      });
    }
    return{
      get pid(){return adapter.pid;},
      listTools:gateway.listTools,
      async call(name,args={}){
        const response=await gateway.callTool('course__'+name,args,{signal});
        if(response.isError)throw new Error('MCP_TOOL_FAILED');
        const data=response.structuredContent||JSON.parse(response.content.find(block=>block.type==='text')?.text||'null');
        if(!data||typeof data!=='object')throw new Error('MCP_INVALID_RESULT');
        return data;
      },
      close:()=>adapter.close()
    };
  }catch(error){await adapter.close().catch(()=>{});throw error;}
}

module.exports={createCourseSession};
