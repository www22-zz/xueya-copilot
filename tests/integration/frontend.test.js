const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL,fileURLToPath}=require('node:url');

test('frontend assets resolve both from a local HTML file and the server homepage',()=>{
  const root=path.resolve(__dirname,'../..');
  const entry=path.join(root,'frontend','index.html');
  const html=fs.readFileSync(entry,'utf8');
  const references=[...html.matchAll(/<(?:script|link|img)\b[^>]*\b(?:src|href)="([^"]+)"/g)].map(match=>match[1]);
  assert.ok(references.length>=6,'Page must include its scripts, stylesheet and brand assets');
  for(const reference of references){
    const localURL=new URL(reference,pathToFileURL(entry));
    assert.equal(localURL.protocol,'file:');
    assert.ok(fs.existsSync(fileURLToPath(localURL)),`Missing local asset: ${reference}`);
    const webURL=new URL(reference,'http://127.0.0.1:4173/');
    const expected=reference.startsWith('../shared/')?reference.slice(2):'/'+reference;
    assert.equal(webURL.pathname,expected,`Unexpected server asset: ${reference}`);
  }
});
