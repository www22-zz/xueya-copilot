'use strict';

const core=require('../../shared/rag/index.js');
const {sources:sampleSources}=require('../../shared/fixtures/course.js');
const {sanitizeSources}=require('../../shared/contracts/index.js');

/** RAG owner's service boundary. Async methods allow a later vector-store adapter. */
function createRagService({catalog=sampleSources}={}){
  return{
    async ingest({text,document}){
      if(!document?.id||!document?.name||typeof text!=='string')throw new Error('INVALID_DOCUMENT');
      return{document,sources:core.extractChunks(text,document)};
    },
    async retrieve({question,sources=catalog}){
      return core.retrieve(question,sources);
    },
    // Existing /api/ai accepts already retrieved passages. Do not silently
    // substitute unrelated demo sources when the caller sends an empty list.
    async prepareSources(sources){return sanitizeSources(sources,catalog);}
  };
}

module.exports={createRagService};
