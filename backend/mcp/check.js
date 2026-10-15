'use strict';

const L=require('../../shared/learning.js');
const {createCourseSession}=require('./course-session.js');

(async()=>{
  let session;
  try{
    session=await createCourseSession({library:L.sources});
    const tools=await session.listTools();
    const found=await session.call('search_materials',{query:'二叉搜索树的查找复杂度'});
    console.log(JSON.stringify({ok:true,transport:'stdio',server:'xueya-course-tools',tools:tools.map(tool=>tool.name),sourceIds:found.sources.map(source=>source.id)},null,2));
  }finally{await session?.close();}
})().catch(()=>{console.error('课程 MCP 工具检查失败，请确认已安装依赖。');process.exitCode=1;});
