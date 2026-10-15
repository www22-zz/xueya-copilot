'use strict';

const {createRagService}=require('./rag/index.js');
const {createAgent}=require('./agent/index.js');
const {createToolGateway}=require('./mcp/index.js');
const {createMimoProvider}=require('./providers/mimo.js');
const {createAIHandler}=require('./http/ai.js');
const {createStaticHandler}=require('./http/static.js');
const {json}=require('./http/json.js');

/** Integration owner: assemble modules here; individual modules never start servers. */
function createApp({config,rag=createRagService(),tools=createToolGateway(),model=createMimoProvider(config.ai)}){
  const agent=createAgent({rag,model,tools});
  const handleAI=createAIHandler(agent);
  const staticFile=createStaticHandler(config.root);
  return function app(req,res){
    const url=(req.url||'').split('?')[0];
    if(req.method==='GET'&&url==='/api/health')return json(res,200,{ok:true,engine:config.ai.apiKey?'xiaomi-mimo':'local-fallback',model:config.ai.model});
    if(req.method==='POST'&&url==='/api/ai')return handleAI(req,res);
    if(!['GET','HEAD'].includes(req.method))return json(res,405,{error:'Method not allowed'});
    staticFile(req,res);
  };
}

module.exports={createApp};
