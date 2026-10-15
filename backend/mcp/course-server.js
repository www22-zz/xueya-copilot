'use strict';

const {McpServer}=require('@modelcontextprotocol/server');
const {serveStdio}=require('@modelcontextprotocol/server/stdio');
const z=require('zod');
const L=require('../../shared/learning.js');

const source=z.object({id:z.string().min(1).max(150),title:z.string().max(200),location:z.string().max(150),quote:z.string().min(1).max(1500),keywords:z.array(z.string().max(30)).max(12).optional(),sample:z.boolean().optional()}).strict();
const sources=z.array(source).max(48);
const question=z.object({id:z.string().max(150),topic:z.string().max(80),sourceId:z.string().max(150)}).strict();
const questions=z.array(question).max(100);
const record=z.object({questionId:z.string().max(150),correct:z.boolean(),createdAt:z.string().max(60).optional()}).strict();
const records=z.array(record).max(120);
const date=z.string().refine(L.validDate,'日期无效');
const annotations={readOnlyHint:true,destructiveHint:false,idempotentHint:true,openWorldHint:false};
const result=data=>({content:[{type:'text',text:JSON.stringify(data)}],structuredContent:data});

function createCourseServer(){
  const server=new McpServer({name:'xueya-course-tools',version:'1.0.0'});
  server.registerTool('search_materials',{
    description:'检索本次请求提供的课程原文，返回可引用的实际片段。',annotations,
    inputSchema:z.object({query:z.string().min(1).max(4000),sources,limit:z.number().int().min(1).max(6).default(4)}).strict()
  },async({query,sources,limit})=>result({sources:L.retrieve(query,sources).slice(0,limit)}));
  server.registerTool('read_source',{
    description:'按稳定的来源 ID 查看本次请求中的原文。',annotations,
    inputSchema:z.object({sourceId:z.string().min(1).max(150),sources}).strict()
  },async({sourceId,sources})=>{
    const found=sources.find(source=>source.id===sourceId);
    return found?result({source:found}):{content:[{type:'text',text:'SOURCE_NOT_FOUND'}],isError:true};
  });
  server.registerTool('analyze_progress',{
    description:'依据近期作答计算薄弱知识点和到期复习项，不修改学习记录。',annotations,
    inputSchema:z.object({questions,records,baseDate:date}).strict()
  },async({questions,records,baseDate})=>{
    const known=new Set(questions.map(question=>question.id));
    const actual=records.filter(record=>known.has(record.questionId));
    const weak=L.wrongQuestions(actual,questions);
    return result({total:actual.length,correct:actual.filter(record=>record.correct).length,weakTopics:[...new Set(weak.map(question=>question.topic))],dueTopics:L.memoryCards(actual,baseDate,questions).filter(card=>card.due).map(card=>card.topic)});
  });
  server.registerTool('build_review_plan',{
    description:'依据考试日期、每天时长和近期错题生成最多七天的计划预览，不保存计划。',annotations,
    inputSchema:z.object({questions,records,baseDate:date,examDate:date,minutes:z.number().int().min(15).max(120)}).strict()
  },async({questions,records,baseDate,examDate,minutes})=>{
    if(examDate<baseDate||!questions.length)return{content:[{type:'text',text:'INVALID_PLAN_SETTINGS'}],isError:true};
    return result({examDate,minutes,days:L.buildPlan(examDate,minutes,records,baseDate,questions)});
  });
  return server;
}

if(require.main===module)serveStdio(createCourseServer,{onerror:()=>console.error('Course MCP connection error')});
module.exports={createCourseServer};
