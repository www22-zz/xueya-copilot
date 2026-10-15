'use strict';

const core=require('../../shared/rag/index.js');
const {sources:sampleSources}=require('../../shared/fixtures/course.js');
const {sanitizeSources}=require('../../shared/contracts/index.js');
const {LIMITS}=require('../../shared/contracts/index.js');
const {extractText}=require('./parsers/pdf.js');
const {extractDocxText}=require('./parsers/docx.js');

/** RAG owner's service boundary. Async methods allow a later vector-store adapter. */
function createRagService({catalog=sampleSources}={}){
  return{
    async parseDocument({buffer,kind}){
      if(!Buffer.isBuffer(buffer)||!['pdf','docx'].includes(kind))throw new Error('INVALID_DOCUMENT');
      if(buffer.length>LIMITS.fileBytes)throw new Error('FILE_TOO_LARGE');
      const text=(kind==='docx'?extractDocxText(buffer):extractText(buffer).text).slice(0,LIMITS.parsedCharacters);
      return{ok:true,text,kind,...(!text.trim()?{empty:true}:{})};
    },
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
