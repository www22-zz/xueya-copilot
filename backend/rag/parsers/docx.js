'use strict';
/* Minimal Office (DOCX) text extraction using only Node built-ins.
   DOCX is a ZIP archive; the visible text lives in word/document.xml.
   Reads stored and deflate entries. Images, tables and styles are ignored. */
const zlib = require('zlib');

function readZipEntries(buffer) {
  const entries = new Map();
  const eocdSignature = 0x06054b50;
  let eocd = -1;
  for (let i = buffer.length - 22; i >= 0; i--) {
    if (buffer.readUInt32LE(i) === eocdSignature) { eocd = i; break; }
  }
  if (eocd < 0) return entries;
  const total = buffer.readUInt16LE(eocd + 10);
  let pointer = buffer.readUInt32LE(eocd + 16);
  for (let index = 0; index < total; index++) {
    if (pointer + 46 > buffer.length || buffer.readUInt32LE(pointer) !== 0x02014b50) break;
    const method = buffer.readUInt16LE(pointer + 10);
    const compressedSize = buffer.readUInt32LE(pointer + 20);
    const nameLength = buffer.readUInt16LE(pointer + 28);
    const extraLength = buffer.readUInt16LE(pointer + 30);
    const commentLength = buffer.readUInt16LE(pointer + 32);
    const localOffset = buffer.readUInt32LE(pointer + 42);
    const name = buffer.toString('utf8', pointer + 46, pointer + 46 + nameLength);
    if (localOffset + 30 <= buffer.length && buffer.readUInt32LE(localOffset) === 0x04034b50) {
      const localNameLength = buffer.readUInt16LE(localOffset + 26);
      const localExtraLength = buffer.readUInt16LE(localOffset + 28);
      const start = localOffset + 30 + localNameLength + localExtraLength;
      const raw = buffer.subarray(start, start + compressedSize);
      if (method === 0) entries.set(name, Buffer.from(raw));
      else if (method === 8) {
        try { entries.set(name, zlib.inflateRawSync(raw, {maxOutputLength: 16777216})); } catch (_) { /* skip unreadable entry */ }
      }
    }
    pointer += 46 + nameLength + extraLength + commentLength;
  }
  return entries;
}

function decodeEntities(text) {
  const named={lt:'<',gt:'>',quot:'"',apos:"'",amp:'&'};
  return text.replace(/&(#x[0-9a-fA-F]+|#\d+|lt|gt|quot|apos|amp);/g,(entity,name)=>{
    if(name[0]!=='#')return named[name];
    const value=name[1]==='x'?parseInt(name.slice(2),16):Number(name.slice(1));
    return value>=0&&value<=0x10FFFF?String.fromCodePoint(value):entity;
  });
}

function docxTextFromXml(xml) {
  let text = String(xml);
  text = text.replace(/<w:tab\b[^>]*\/?>/g, '\t');
  text = text.replace(/<w:(?:br|cr)\b[^>]*\/?>/g, '\n');
  text = text.replace(/<\/w:p>/g, '\n');
  text = text.replace(/<\/w:tr>/g, '\n');
  text = text.replace(/<[^>]+>/g, '');
  text = decodeEntities(text);
  text = text.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n');
  return text.trim();
}

function extractDocxText(buffer) {
  const entries = readZipEntries(buffer);
  const document = entries.get('word/document.xml');
  if (!document) return '';
  return docxTextFromXml(document.toString('utf8'));
}

module.exports = { extractDocxText, docxTextFromXml, readZipEntries };
