'use strict';
function crc32(buffer) {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < buffer.length; i++) {
    let c = (crc ^ buffer[i]) & 0xFF;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

function zipStore(files) {
  const local = [], central = [];
  let offset = 0;
  for (const [name, data] of files) {
    const nameBuffer = Buffer.from(name, 'utf8');
    const crc = crc32(data);
    const header = Buffer.alloc(30);
    header.writeUInt32LE(0x04034b50, 0); header.writeUInt16LE(20, 4); header.writeUInt32LE(crc, 14);
    header.writeUInt32LE(data.length, 18); header.writeUInt32LE(data.length, 22); header.writeUInt16LE(nameBuffer.length, 26);
    local.push(header, nameBuffer, data);
    const entry = Buffer.alloc(46);
    entry.writeUInt32LE(0x02014b50, 0); entry.writeUInt16LE(20, 4); entry.writeUInt16LE(20, 6); entry.writeUInt32LE(crc, 16);
    entry.writeUInt32LE(data.length, 20); entry.writeUInt32LE(data.length, 24); entry.writeUInt16LE(nameBuffer.length, 28);
    entry.writeUInt32LE(offset, 42);
    central.push(entry, nameBuffer);
    offset += header.length + nameBuffer.length + data.length;
  }
  const centralBuffer = Buffer.concat(central);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(files.length, 8); eocd.writeUInt16LE(files.length, 10);
  eocd.writeUInt32LE(centralBuffer.length, 12); eocd.writeUInt32LE(offset, 16);
  return Buffer.concat([...local, centralBuffer, eocd]);
}

function sampleDocx() {
  const xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    + '<w:p><w:r><w:t>第一段：光合作用发生在叶绿体。</w:t></w:r></w:p>'
    + '<w:p><w:r><w:t>第二段：光反应产生 ATP 和 NADPH。</w:t></w:r></w:p>'
    + '</w:body></w:document>';
  return zipStore([['word/document.xml', Buffer.from(xml, 'utf8')]]);
}

function samplePdf() {
  const content = 'BT /F1 24 Tf 40 700 Td (photosynthesis happens) Tj ET';
  const objects = [
    '1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n',
    '2 0 obj\n<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n',
    '3 0 obj\n<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>\nendobj\n',
    '4 0 obj\n<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>\nendobj\n',
    '5 0 obj\n<</Length ' + content.length + '>>\nstream\n' + content + '\nendstream\nendobj\n'
  ];
  let pdf = '%PDF-1.4\n';
  const offsets = [];
  for (const object of objects) { offsets.push(pdf.length); pdf += object; }
  const startxref = pdf.length;
  pdf += 'xref\n0 ' + (objects.length + 1) + '\n0000000000 65535 f \n';
  for (const off of offsets) pdf += String(off).padStart(10, '0') + ' 00000 n \n';
  pdf += 'trailer\n<</Size ' + (objects.length + 1) + '/Root 1 0 R>>\nstartxref\n' + startxref + '\n%%EOF';
  return Buffer.from(pdf, 'latin1');
}


module.exports={sampleDocx,samplePdf,zipStore};
