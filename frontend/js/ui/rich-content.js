/* Deliberately small safe renderer: raw HTML is always text; no remote assets/scripts. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.XueyaRich=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function safeURL(value){try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?escape(url.href):'';}catch{return '';}}
function math(value){
  const text=String(value).slice(0,2000);let i=0,count=0;
  const symbols={alpha:'α',beta:'β',gamma:'γ',theta:'θ',lambda:'λ',pi:'π',sigma:'σ',Delta:'Δ',sum:'∑',int:'∫',infty:'∞',times:'×',cdot:'·',leq:'≤',geq:'≥',neq:'≠',in:'∈',to:'→',log:'log',sin:'sin',cos:'cos'};
  function group(depth=0){if(depth>12)throw new Error('deep');let output='';while(i<text.length&&text[i]!=='}'){if(++count>2000)throw new Error('long');output+=atom(depth);}if(text[i]==='}')i++;return `<mrow>${output}</mrow>`;}
  function operand(depth){while(text[i]===' ')i++;if(text[i]==='{'){i++;return group(depth+1);}return atom(depth+1);}
  function atom(depth){
    let node='',c=text[i++];if(c==='{')node=group(depth+1);
    else if(c==='\\'){
      const cmd=(text.slice(i).match(/^[a-zA-Z]+/)||[''])[0];i+=cmd.length;
      if(cmd==='frac')node=`<mfrac>${operand(depth)}${operand(depth)}</mfrac>`;
      else if(cmd==='sqrt')node=`<msqrt>${operand(depth)}</msqrt>`;
      else if(['mathrm','text','operatorname'].includes(cmd))node=operand(depth);
      else node=`<mi>${escape(symbols[cmd]||'\\'+cmd)}</mi>`;
    }else if(/\s/.test(c))node='<mspace width="0.2em"/>';
    else node=`<${/[\d.]/.test(c)?'mn':/[a-zA-Z\u4e00-\u9fff]/.test(c)?'mi':'mo'}>${escape(c)}</${/[\d.]/.test(c)?'mn':/[a-zA-Z\u4e00-\u9fff]/.test(c)?'mi':'mo'}>`;
    while(text[i]==='^'||text[i]==='_'){const type=text[i++]==='^'?'msup':'msub';node=`<${type}>${node}${operand(depth)}</${type}>`;}
    return node;
  }
  try{return `<math xmlns="http://www.w3.org/1998/Math/MathML" aria-label="${escape(text)}">${group()}</math>`;}catch{return `<code class="formula-source">${escape(text)}</code>`;}
}
function inline(text){
  const pattern=/(`[^`\n]+`|\$[^$\n]+\$|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\([^\s)]+\))/g;let output='',last=0;
  for(const match of String(text).matchAll(pattern)){
    output+=escape(text.slice(last,match.index));const token=match[0];
    if(token[0]==='`')output+=`<code>${escape(token.slice(1,-1))}</code>`;
    else if(token[0]==='$')output+=math(token.slice(1,-1));
    else if(token.startsWith('**'))output+=`<strong>${escape(token.slice(2,-2))}</strong>`;
    else{const parts=token.match(/^\[([^\]]+)\]\((.+)\)$/),url=safeURL(parts[2]);output+=url?`<a href="${url}" target="_blank" rel="noopener noreferrer">${escape(parts[1])}</a>`:escape(token);}
    last=match.index+token.length;
  }
  return output+escape(String(text).slice(last));
}
function render(value){
  const lines=String(value??'').slice(0,300000).replace(/\r\n?/g,'\n').split('\n');let out='';
  for(let i=0;i<lines.length;i++){
    const line=lines[i];if(!line.trim())continue;
    if(/^```/.test(line)){const language=line.slice(3).trim();let code='';while(++i<lines.length&&!/^```/.test(lines[i]))code+=lines[i]+'\n';out+=`<figure class="code-block"><figcaption>${escape(language||'代码')}</figcaption><pre><code>${escape(code.trimEnd())}</code></pre></figure>`;continue;}
    if(line.trim().startsWith('$$')){let formula=line.trim().slice(2);if(formula.endsWith('$$'))formula=formula.slice(0,-2);else while(++i<lines.length){if(lines[i].includes('$$')){formula+=' '+lines[i].split('$$')[0];break;}formula+=' '+lines[i];}out+=`<div class="formula-block">${math(formula)}</div>`;continue;}
    if(line.includes('|')&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1]||'')){
      const cells=row=>row.trim().replace(/^\||\|$/g,'').split('|').map(cell=>cell.trim());const headers=cells(line);i++;let body='';
      while(i+1<lines.length&&lines[i+1].includes('|'))body+=`<tr>${cells(lines[++i]).slice(0,headers.length).map(cell=>`<td>${inline(cell)}</td>`).join('')}</tr>`;
      out+=`<div class="table-scroll" tabindex="0" role="region" aria-label="内容表格"><table><thead><tr>${headers.map(cell=>`<th scope="col">${inline(cell)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div>`;continue;
    }
    const heading=line.match(/^(#{1,4})\s+(.+)/);if(heading){const level=Math.min(heading[1].length+1,5);out+=`<h${level}>${inline(heading[2])}</h${level}>`;continue;}
    if(/^\s*([-*]|\d+\.)\s+/.test(line)){const ordered=/^\s*\d/.test(line),tag=ordered?'ol':'ul';let items='';do{items+=`<li>${inline(lines[i].replace(/^\s*([-*]|\d+\.)\s+/,''))}</li>`;}while(i+1<lines.length&&/^\s*([-*]|\d+\.)\s+/.test(lines[i+1])&&++i);out+=`<${tag}>${items}</${tag}>`;continue;}
    if(/^>\s?/.test(line)){out+=`<blockquote>${inline(line.replace(/^>\s?/,''))}</blockquote>`;continue;}
    out+=`<p>${inline(line)}</p>`;
  }
  return out;
}
return{escape,render,inline,math,safeURL};
});
