'use strict';

function parseModelJSON(content){
  if(typeof content!=='string')throw new Error('AI_INVALID_RESPONSE');
  try{return JSON.parse(content.replace(/^\s*```(?:json)?\s*/i,'').replace(/\s*```\s*$/,''));}
  catch{throw new Error('AI_INVALID_RESPONSE');}
}

module.exports={parseModelJSON};
