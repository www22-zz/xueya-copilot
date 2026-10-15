/* Portable module: browser script and CommonJS. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaRag=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';

  function extractChunks(text,document){
    const cleaned=String(text).replace(/\r\n/g,'\n').trim();
    const chunks=[];
    for(let offset=0;offset<cleaned.length;offset+=520){
      const quote=cleaned.slice(offset,offset+600);
      chunks.push({
        id:`${document.id}-chunk-${chunks.length}`,documentId:document.id,
        title:document.name,location:`文本片段 ${chunks.length+1}`,
        quote,keywords:[],sample:false
      });
    }
    return chunks;
  }

  function retrieve(question,library){
    const q=String(question).toLowerCase();
    const latin=q.match(/[a-z0-9_]{2,}/g)||[];
    const han=q.replace(/[^\u4e00-\u9fff]/g,' ');
    const grams=new Set();
    for(const word of han.split(/\s+/)){
      for(let i=0;i<word.length-1;i++)grams.add(word.slice(i,i+2));
    }
    return library.map(source=>{
      const hay=(source.title+' '+source.quote).toLowerCase();
      const score=(source.keywords||[]).reduce((sum,keyword)=>sum+(q.includes(keyword.toLowerCase())?5:0),0)
        +latin.reduce((sum,word)=>sum+(hay.includes(word)?2:0),0)
        +[...grams].reduce((sum,word)=>sum+(hay.includes(word)?1:0),0);
      return{source,score};
    })
      .filter(hit=>hit.score>=2)
      .sort((a,b)=>b.score-a.score)
      .slice(0,4)
      .map(hit=>hit.source);
  }

return {extractChunks,retrieve};
});
