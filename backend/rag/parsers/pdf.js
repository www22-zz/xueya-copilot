'use strict';
/* Minimal PDF text extraction for text-based files. Uses only Node built-ins.
   Handles FlateDecode streams, ToUnicode CMaps, and Tj / TJ / ' / " operators.
   Scanned (image-only) PDFs return empty text. */
const zlib = require('zlib');

function hexToStr(hex) {
  let out = '';
  for (let i = 0; i + 4 <= hex.length; i += 4) {
    out += String.fromCharCode(parseInt(hex.slice(i, i + 4), 16));
  }
  return out;
}

function parseToUnicode(text) {
  const map = {};
  const bfchar = /beginbfchar([\s\S]*?)endbfchar/g;
  let m;
  while ((m = bfchar.exec(text))) {
    const pairs = m[1].match(/<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>/g) || [];
    for (const p of pairs) {
      const pm = /<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>/.exec(p);
      if (pm) map[pm[1].toUpperCase()] = hexToStr(pm[2]);
    }
  }
  const bfrange = /beginbfrange([\s\S]*?)endbfrange/g;
  while ((m = bfrange.exec(text))) {
    for (const line of m[1].split(/\r?\n/)) {
      const rm = /<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>/.exec(line);
      if (rm) {
        const s = parseInt(rm[1], 16), e = parseInt(rm[2], 16), d = parseInt(rm[3], 16);
        for (let c = s; c <= e; c++) map[c.toString(16).toUpperCase().padStart(rm[1].length, '0')] = String.fromCharCode(d + (c - s));
        continue;
      }
      const ra = /<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[([^\]]*)\]/.exec(line);
      if (ra) {
        const s = parseInt(ra[1], 16), e = parseInt(ra[2], 16);
        const ds = (ra[3].match(/<([0-9A-Fa-f]+)>/g) || []).map(h => hexToStr(h.slice(1, -1)));
        let k = 0;
        for (let c = s; c <= e && k < ds.length; c++) map[c.toString(16).toUpperCase().padStart(ra[1].length, '0')] = ds[k++];
      }
    }
  }
  return map;
}

function tokenize(s) {
  const tokens = [];
  const n = s.length;
  let i = 0;
  function skipWs() { while (i < n && /\s/.test(s[i])) i++; }
  function readString() {
    let j = i + 1, depth = 1, out = '';
    while (j < n && depth > 0) {
      const ch = s[j];
      if (ch === '\\') {
        const nx = s[j + 1];
        if (nx === 'n') { out += '\n'; j += 2; }
        else if (nx === 'r') { out += '\r'; j += 2; }
        else if (nx === 't') { out += '\t'; j += 2; }
        else if (nx === 'b') { out += '\b'; j += 2; }
        else if (nx === 'f') { out += '\f'; j += 2; }
        else if (nx === '(' || nx === ')' || nx === '\\') { out += nx; j += 2; }
        else if (nx === '\r' || nx === '\n') { j += 2; }
        else if (/[0-7]/.test(nx)) { let k = j + 1, oct = ''; while (k < n && k < j + 4 && /[0-7]/.test(s[k])) { oct += s[k]; k++; } out += String.fromCharCode(parseInt(oct, 8) & 255); j = k; }
        else { out += nx; j += 2; }
        continue;
      }
      if (ch === '(') depth++;
      else if (ch === ')') { depth--; if (depth === 0) { j++; break; } }
      out += ch;
      j++;
    }
    i = j;
    return { t: 'str', v: out };
  }
  function readHex() {
    let j = i + 1;
    while (j < n && s[j] !== '>') j++;
    const v = s.slice(i + 1, j);
    i = j + 1;
    return { t: 'hex', v };
  }
  function readNumber() {
    let j = i;
    while (j < n && /[+\-.\d]/.test(s[j])) j++;
    const v = s.slice(i, j);
    i = j;
    return { t: 'num', v };
  }
  function readArray() {
    const arr = [];
    i++;
    while (i < n) {
      skipWs();
      if (i >= n) break;
      const ch = s[i];
      if (ch === ']') { i++; break; }
      if (ch === '(') arr.push(readString());
      else if (ch === '<') arr.push(readHex());
      else if (/[+\-.\d]/.test(ch)) arr.push(readNumber());
      else i++;
    }
    return { t: 'array', v: arr };
  }
  while (i < n) {
    const c = s[i];
    if (/\s/.test(c)) { i++; continue; }
    if (c === '%') { while (i < n && s[i] !== '\n' && s[i] !== '\r') i++; continue; }
    if (c === '(') { tokens.push(readString()); continue; }
    if (c === '<') {
      if (s[i + 1] === '<') { tokens.push({ t: '<<' }); i += 2; }
      else tokens.push(readHex());
      continue;
    }
    if (c === '>') {
      if (s[i + 1] === '>') { tokens.push({ t: '>>' }); i += 2; }
      else i++;
      continue;
    }
    if (c === '/') {
      let j = i + 1;
      while (j < n && !/[\s/[\]()<>{}%]/.test(s[j])) j++;
      tokens.push({ t: 'name', v: s.slice(i + 1, j) });
      i = j;
      continue;
    }
    if (c === '[') { tokens.push(readArray()); continue; }
    if (/[+\-.\d]/.test(c)) { tokens.push(readNumber()); continue; }
    if (/[A-Za-z*'"]/.test(c)) {
      let j = i;
      while (j < n && /[A-Za-z*'"]/.test(s[j])) j++;
      tokens.push({ t: 'op', v: s.slice(i, j) });
      i = j;
      continue;
    }
    i++;
  }
  return tokens;
}

function extractText(buffer) {
  const raw = buffer.toString('latin1');
  const objs = new Map();
  const objRe = /(\d+)\s+(\d+)\s+obj([\s\S]*?)endobj/g;
  let m;
  while ((m = objRe.exec(raw))) objs.set(m[1], m[3]);

  function streamBytes(id) {
    const body = objs.get(id);
    if (!body) return null;
    const i = body.indexOf('stream');
    if (i < 0) return null;
    let j = i + 6;
    if (body[j] === '\r' && body[j + 1] === '\n') j += 2;
    else if (body[j] === '\n' || body[j] === '\r') j += 1;
    const e = body.lastIndexOf('endstream');
    if (e < 0 || e <= j) return null;
    const dict = body.slice(0, i);
    const data = Buffer.from(body.slice(j, e), 'latin1');
    if (/\/FlateDecode/.test(dict)) {
      try { return zlib.inflateSync(data, {maxOutputLength: 16777216}); } catch (_) { try { return zlib.inflateRawSync(data, {maxOutputLength: 16777216}); } catch (_) { return null; } }
    }
    if (/\/DCTDecode/.test(dict) || /\/JPXDecode/.test(dict)) return null;
    return data;
  }

  function resolveFonts(resId) {
    const body = objs.get(resId) || resId;
    if (!body) return {};
    let part = null;
    const inline = /\/Font\s*<<([\s\S]*?)>>/.exec(body);
    if (inline) part = inline[1];
    else {
      const fr = /\/Font\s+(\d+)\s+\d+\s+R/.exec(body);
      if (fr) part = objs.get(fr[1]) || null;
    }
    if (!part) return {};
    const fonts = {};
    const re = /\/?([A-Za-z0-9+_.-]+)\s+(\d+)\s+\d+\s+R/g;
    let mm;
    while ((mm = re.exec(part))) fonts[mm[1]] = mm[2];
    return fonts;
  }

  function fontInfo(fontObjId) {
    const body = objs.get(fontObjId);
    if (!body) return { cid: false, cmap: {} };
    const cid = /\/Subtype\s*\/Type0/.test(body) || /\/Encoding\s*\/Identity-H/.test(body);
    const tu = /\/ToUnicode\s+(\d+)\s+\d+\s+R/.exec(body);
    let cmap = {};
    if (tu) {
      const t = streamBytes(tu[1]);
      if (t) cmap = parseToUnicode(t.toString('latin1'));
    }
    return { cid, cmap };
  }

  const pages = [];
  for (const [id, body] of objs) {
    if (/\/Type\s*\/Page\b/.test(body) && !/\/Type\s*\/Pages\b/.test(body)) pages.push(id);
  }
  const chunks = [];
  for (const pageId of pages) {
    const body = objs.get(pageId);
    if (!body) continue;
    const contentIds = [];
    const single = /\/Contents\s+(\d+)\s+\d+\s+R/.exec(body);
    if (single) contentIds.push(single[1]);
    else {
      const arr = /\/Contents\s*\[([^\]]*)\]/.exec(body);
      if (arr) for (const mm of arr[1].matchAll(/(\d+)\s+\d+\s+R/g)) contentIds.push(mm[1]);
    }
    const resMatch = /\/Resources\s+(\d+)\s+\d+\s+R/.exec(body);
    const fonts = resolveFonts(resMatch ? resMatch[1] : body);
    const ctx = { fontName: null, fonts: {} };
    for (const name of Object.keys(fonts)) ctx.fonts[name] = fontInfo(fonts[name]);
    let text = '';
    for (const cid of contentIds) {
      const cs = streamBytes(cid);
      if (!cs) continue;
      const toks = tokenize(cs.toString('latin1'));
      const show = tok => {
        let bytes = null;
        if (tok.t === 'str') bytes = Buffer.from(tok.v, 'latin1');
        else if (tok.t === 'hex') bytes = Buffer.from(tok.v, 'hex');
        if (!bytes || !bytes.length) return;
        if (bytes.length >= 2 && bytes[0] === 0xFE && bytes[1] === 0xFF) {
          const unicode=Buffer.from(bytes.subarray(2, bytes.length-(bytes.length%2)));
          text += unicode.swap16().toString('utf16le'); return;
        }
        if (bytes.length >= 2 && bytes[0] === 0xFF && bytes[1] === 0xFE) { text += bytes.subarray(2).toString('utf16le'); return; }
        const font = ctx.fontName ? ctx.fonts[ctx.fontName] : null;
        if (font && Object.keys(font.cmap).length) {
          const width = font.cid ? 2 : 1;
          for (let i = 0; i + width <= bytes.length; i += width) {
            const code = bytes.slice(i, i + width).toString('hex').toUpperCase();
            text += font.cmap[code] || (font.cid ? '' : String.fromCharCode(bytes[i]));
          }
        } else {
          text += bytes.toString('latin1');
        }
      };
      for (let k = 0; k < toks.length; k++) {
        const t = toks[k];
        if (t.t === 'op') {
          if (t.v === 'Tf' && k >= 2 && toks[k - 2].t === 'name') ctx.fontName = toks[k - 2].v;
          else if (t.v === 'Tj' && k >= 1) show(toks[k - 1]);
          else if (t.v === 'TJ' && k >= 1 && toks[k - 1].t === 'array') toks[k - 1].v.forEach(show);
          else if (t.v === "'" && k >= 1) { show(toks[k - 1]); text += '\n'; }
          else if (t.v === '"' && k >= 2) { show(toks[k - 2]); show(toks[k - 1]); text += '\n'; }
        }
      }
    }
    if (text.trim()) chunks.push(text);
  }
  return { text: chunks.join('\n'), pages: chunks.length };
}

module.exports = { extractText };
