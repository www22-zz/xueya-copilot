'use strict';
const {createRagService}=require('../rag/index.js');

/** Adapter only: retrieval and learning algorithms stay owned by B/C; storage stays E. */
function createBusinessPorts({repository,rag=createRagService(),learning={}}={}){
  const services={};
  if(typeof repository?.listSources==='function')services.searchMaterials=async({scope,query,limit},options)=>({sources:(await rag.retrieve({question:query,sources:await repository.listSources({scope},options),signal:options.signal})).slice(0,limit)});
  if(typeof repository?.readSource==='function')services.readSource=async({scope,sourceId},options)=>{
    const source=await repository.readSource({scope,sourceId},options);if(!source||source.id!==sourceId)throw new Error('SOURCE_NOT_FOUND');return{source};
  };
  for(const method of ['listSections','readSection','listConcepts','getPrerequisites','listQuestionDrafts','listAttempts','listWrongQuestions','listReviews','listPlans','listNotes'])if(typeof repository?.[method]==='function')services[method]=(args,options)=>repository[method](args,options);
  for(const method of ['analyzeProgress','buildReviewPlan'])if(typeof learning[method]==='function')services[method]=(args,options)=>learning[method](args,options);
  return services;
}
function createWorkflowSessionFactory({resolveScope,servicesForScope,authority}={}){
  if(typeof resolveScope!=='function'||typeof servicesForScope!=='function')throw new Error('TRUSTED_SCOPE_RESOLVER_REQUIRED');
  return async(context,options)=>{
    // resolveScope must be a trusted per-HTTP-request closure; never derive identity from model arguments.
    const scope=await resolveScope();
    const {createPlatformSession}=require('./platform-session.js');
    return createPlatformSession({scope,services:await servicesForScope(scope,context),authority},options);
  };
}
module.exports={createBusinessPorts,createWorkflowSessionFactory};
