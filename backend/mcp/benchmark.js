'use strict';
const {performance}=require('node:perf_hooks');
const L=require('../../shared/learning.js');
const {createCourseSession}=require('./course-session.js');
const {processStats}=require('./stdio-client.js');
const {createPlatformSession,connectionStats}=require('./platform-session.js');
const {createRagService}=require('../rag/index.js');
const percentile=(values,p)=>Number([...values].sort((a,b)=>a-b)[Math.min(values.length-1,Math.ceil(values.length*p)-1)].toFixed(2));
async function benchmark(){
  const runs=8,cold=[],warm=[],inProcess=[];
  for(let i=0;i<runs;i++){
    const start=performance.now(),session=await createCourseSession({library:L.sources});
    try{await session.call('search_materials',{query:'二叉搜索树'});}finally{await session.close();}cold.push(performance.now()-start);
  }
  // Comparison only: two request-immutable contexts, explicitly owned and always closed.
  const start=performance.now(),pool=await Promise.all([createCourseSession({library:L.sources}),createCourseSession({library:[]})]);
  const poolStartupMs=performance.now()-start;
  try{for(let i=0;i<runs;i++){const start=performance.now();await pool[i%2].call('search_materials',{query:'二叉搜索树'});warm.push(performance.now()-start);}}finally{await Promise.all(pool.map(s=>s.close()));}
  const rag=createRagService();
  for(let i=0;i<runs;i++){
    const start=performance.now(),session=await createPlatformSession({
      scope:{userId:'benchmark',courseId:'sample'},
      services:{searchMaterials:async({query,limit})=>({sources:(await rag.retrieve({question:query,sources:L.sources})).slice(0,limit)})}
    });
    try{await session.call('search_materials',{query:'二叉搜索树'});}finally{await session.close();}inProcess.push(performance.now()-start);
  }
  const summary=values=>({runs:values.length,p50Ms:percentile(values,.5),p95Ms:percentile(values,.95)});
  return{node:process.version,platform:process.platform,transport:'official SDK 2.3.1',coldPerRequest:summary(cold),comparisonOnlyBoundedReuse:{...summary(warm),startupMs:Number(poolStartupMs.toFixed(2)),size:2},inProcessScoped:summary(inProcess),processes:processStats(),connections:connectionStats(),choice:'Keep per-Agent-run stdio ownership; no cross-user/global context pool. Injected business ports may use isolated in-process SDK sessions.'};
}
if(require.main===module)benchmark().then(value=>console.log(JSON.stringify(value,null,2))).catch(error=>{console.error(error.message);process.exitCode=1;});
module.exports={benchmark};
