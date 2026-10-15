const test = require('node:test');
const assert = require('node:assert/strict');
const { extractDocxText, docxTextFromXml } = require('../../backend/rag/parsers/docx.js');
const { extractText } = require('../../backend/rag/parsers/pdf.js');

const {sampleDocx,samplePdf}=require('../fixtures/documents.js');

test('docx extraction keeps paragraph text from word/document.xml', () => {
  const text = extractDocxText(sampleDocx());
  assert.match(text, /光合作用发生在叶绿体/);
  assert.match(text, /光反应产生 ATP/);
  assert.match(text, /\n/);
});

test('pdf extraction reads text operators from a simple page', () => {
  const result = extractText(samplePdf());
  assert.equal(result.pages, 1);
  assert.match(result.text, /photosynthesis happens/);
});

test('pdf extraction reads Chinese CMap ranges with padded source codes and inline resources',()=>{
  const pdf='%PDF-1.4\n'
    +'1 0 obj <</Type/Page/Resources<</Font<</F1 2 0 R>>>>/Contents 3 0 R>> endobj\n'
    +'2 0 obj <</Type/Font/Subtype/Type0/ToUnicode 4 0 R>> endobj\n'
    +'3 0 obj <<>> stream\nBT /F1 12 Tf <00010002> Tj ET\nendstream endobj\n'
    +'4 0 obj <<>> stream\n1 beginbfrange\n<0001> <0002> <4E00>\nendbfrange\nendstream endobj';
  assert.equal(extractText(Buffer.from(pdf,'latin1')).text,'一丁');
});

test('pdf extraction decodes UTF-16 big-endian text without reversing Chinese characters',()=>{
  const pdf='%PDF-1.4\n1 0 obj <</Type/Page/Contents 2 0 R>> endobj\n'
    +'2 0 obj <<>> stream\nBT <FEFF4E2D6587> Tj ET\nendstream endobj';
  assert.equal(extractText(Buffer.from(pdf,'latin1')).text,'中文');
});

test('docx XML decodes numeric entities once while preserving literal escaped entities',()=>{
  assert.equal(docxTextFromXml('<w:p><w:t>&#x4E2D;&#25991; &amp;#65;</w:t></w:p>'),'中文 &#65;');
});

test('parse endpoint returns document text for docx and pdf uploads', async () => {
  delete require.cache[require.resolve('../../backend/server.js')];
  const { server } = require('../../backend/server.js');
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    const docx = await (await fetch(base + '/api/parse?type=docx', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: sampleDocx() })).json();
    assert.equal(docx.ok, true);
    assert.equal(docx.kind, 'docx');
    assert.match(docx.text, /叶绿体/);
    const pdf = await (await fetch(base + '/api/parse?type=pdf', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: samplePdf() })).json();
    assert.equal(pdf.ok, true);
    assert.equal(pdf.kind, 'pdf');
    assert.match(pdf.text, /photosynthesis/);
  } finally {
    server.closeAllConnections?.();
    await new Promise(resolve => server.close(resolve));
  }
});
