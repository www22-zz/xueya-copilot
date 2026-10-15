'use strict';

const {readJson}=require('./body.js');
const {json}=require('./json.js');

function createPracticeHandler(agent,task){
  return(req,res)=>readJson(req,res,async input=>{
    try{json(res,200,await agent[task](input));}
    catch(error){
      const code=error.name==='AbortError'?'AI_TIMEOUT':['NO_SOURCES','AI_EMPTY'].includes(error.message)?error.message:'AI_UNAVAILABLE';
      json(res,200,{ok:false,error:code});
    }
  });
}

module.exports={createPracticeHandler};
