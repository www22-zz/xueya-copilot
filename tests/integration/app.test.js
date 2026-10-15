const test=require('node:test');
const assert=require('node:assert/strict');
const http=require('node:http');
const path=require('node:path');
const fs=require('node:fs');
const {createApp}=require('../../backend/app.js');

test('assembled app serves every browser dependency and preserves API failures without a key',async()=>{
  const root=path.resolve(__dirname,'../..');
  const config={root,ai:{apiKey:'',baseURL:'http://unused.invalid',model:'test-model'}};
  const server=http.createServer(createApp({config}));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  const post=body=>fetch(base+'/api/ai',{method:'POST',body:JSON.stringify(body)});
  try{
    assert.deepEqual(await (await fetch(base+'/api/health')).json(),{ok:true,engine:'local-fallback',model:'test-model'});
    const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');
    for(const match of html.matchAll(/<(?:script|link|img)\b[^>]*\b(?:src|href)="([^"]+)"/g)){
      const asset=new URL(match[1],base+'/');
      const response=await fetch(asset);
      assert.equal(response.status,200,asset.pathname);
      assert.equal(response.headers.get('x-content-type-options'),'nosniff');
    }
    for(const file of ['/backend/app.js','/backend/mcp/index.js','/backend/config.js','/shared/contracts/private.js','/.env','/package.json','/docs/team-development.md']){
      assert.equal((await fetch(base+file)).status,404,file);
    }
    for(const body of [null,[],{question:'  '}])assert.equal((await post(body)).status,400);
    assert.deepEqual(await (await post({question:'问题',sources:[]})).json(),{ok:false,error:'NO_SOURCES',engine:'local-fallback'});
    assert.deepEqual(await (await post({question:'查找',sources:['source-1']})).json(),{ok:false,error:'AI_UNAVAILABLE',engine:'local-fallback'});
    assert.equal((await post({question:'查找',padding:'x'.repeat(530000)})).status,413);
    assert.equal((await fetch(base+'/api/ai',{method:'DELETE'})).status,405);
  }finally{await new Promise(resolve=>server.close(resolve));}
});
