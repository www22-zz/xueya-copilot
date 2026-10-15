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

/** Integration owner: assemble modules here; individual modules never start servers. */
function createApp({config,rag=createRagService(),tools=createToolGateway(),model=createMimoProvider(config.ai)}){
  const agent=createAgent({rag,model,tools});
  const handleAI=createAIHandler(agent);
  const postRoutes=new Map([
    ['/api/ai',handleAI],
    ['/api/ai/stream',createStreamHandler(agent)],
    ['/api/topics',createPracticeHandler(agent,'topics')],
    ['/api/questions',createPracticeHandler(agent,'questions')],
    ['/api/parse',createParseHandler(rag)]
  ]);
  const staticFile=createStaticHandler(config.root);
  return function app(req,res){
    const url=(req.url||'').split('?')[0];
    if(req.method==='GET'&&url==='/api/health')return json(res,200,{ok:true,engine:config.ai.apiKey?'xiaomi-mimo':'local-fallback',model:config.ai.model});
    if(req.method==='POST'&&postRoutes.has(url))return postRoutes.get(url)(req,res);
    if(!['GET','HEAD'].includes(req.method))return json(res,405,{error:'Method not allowed'});
    staticFile(req,res);
  };
}

module.exports={createApp};
