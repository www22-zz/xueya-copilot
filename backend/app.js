'use strict';

const {createRagService}=require('./rag/index.js');
const {createAgent}=require('./agent/index.js');
const {createToolGateway}=require('./mcp/index.js');
const {createMimoProvider}=require('./providers/mimo.js');
const {createAIHandler}=require('./http/ai.js');
const {createStaticHandler}=require('./http/static.js');
const {json}=require('./http/json.js');
const {createStreamHandler}=require('./http/stream.js');
const {createPracticeHandler}=require('./http/practice.js');
const {createParseHandler}=require('./http/parse.js');
const {createLearningWorkflow}=require('./agent/learning-workflow.js');

/** Integration owner: assemble modules here; individual modules never start servers. */
function createApp({config,rag=createRagService(),tools=createToolGateway(),model=createMimoProvider(config.ai),platform}){
  if(!platform&&config.platform?.enabled)platform=require('./platform/index.js').createPlatform({...config.platform,rag});
  const platformHandler=platform?require('./http/platform.js').createPlatformHandler(platform):null;
  const managedModel=platform?require('./platform/api-provider.js').createTrackedProvider({platform,model,scope:{userId:platform.userId,courseId:'course-default'}}):model;
  const agent=createAgent({rag,model:managedModel,tools});
  const fallback=createLearningWorkflow({model:managedModel,toolTimeoutMs:config.agent?.toolTimeoutMs||5000});
  const workflow=platform?require('./platform/workflow.js').createStoredWorkflow({platform,model,rag,fallback}):fallback;
  const handleAI=createAIHandler(agent);
  const postRoutes=new Map([
    ['/api/ai',handleAI],
    ['/api/agent',createAIHandler(workflow)],
    ['/api/agent/stream',createStreamHandler(workflow)],
    ['/api/ai/stream',createStreamHandler(agent)],
    ['/api/topics',createPracticeHandler(agent,'topics')],
    ['/api/questions',createPracticeHandler(agent,'questions')],
    ['/api/parse',createParseHandler(rag)]
  ]);
  const staticFile=createStaticHandler(config.root);
  function app(req,res){
    const url=(req.url||'').split('?')[0];
    if(res.writableEnded)return;
    if(url.startsWith('/api/')&&req.headers.origin&&req.headers.origin!=='http://'+req.headers.host)return json(res,403,{ok:false,error:'ORIGIN_FORBIDDEN'});
    if(platformHandler&&url.startsWith('/api/platform/'))return void platformHandler(req,res);
    if(req.method==='GET'&&url==='/api/health')return json(res,200,{ok:true,engine:config.ai.apiKey?'xiaomi-mimo':'local-fallback',model:config.ai.model,...(app.instanceId?{instanceId:app.instanceId}:{}),...(platform?{platform:{schemaVersion:'1.0',storage:'sqlite',inference:'external-api-only',resources:platform.resources.stats()}}:{})});
    if(req.method==='POST'&&postRoutes.has(url))return postRoutes.get(url)(req,res);
    if(!['GET','HEAD'].includes(req.method))return json(res,405,{error:'Method not allowed'});
    staticFile(req,res);
  }
  app.platform=platform;app.close=async()=>{await platform?.close();};return app;
}

module.exports={createApp};
