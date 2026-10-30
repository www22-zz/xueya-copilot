const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let revision=1,confirmed=false;
 const doc=()=>({id:'doc-test',name:'教材.pdf',kind:'pdf',version:revision,contentRevision:revision,sourceCount:1,size:40,status:'待校正与确认',reviewReady:confirmed,pageSelection:{pages:[82,83,84,86],originalPageCount:324},review:{pendingPages:[],transcribedPages:[],blankPages:[],supplementedPages:[]}});
 await page.route('http://rag-test/**',async route=>{
  const url=new URL(route.request().url());let value={};
  if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:'<main id="spaceContent"></main>'});
  if(url.pathname.endsWith('bootstrap'))value={token:'test'};
  else if(url.pathname.endsWith('bases'))value={bases:[{id:'course-default',name:'测试课程'}]};
  else if(url.pathname.endsWith('catalog'))value={documents:[doc()],summary:{documents:1,sources:1,processing:0,needsReview:1},capabilities:{embedding:false,ocr:false}};
  else if(url.pathname.endsWith('export'))value={document:doc(),artifact:{blocks:[{id:'b1',type:'paragraph',text:'树是结点的有限集合。',page:1}]}};
  else if(url.pathname.endsWith('correct')){const body=route.request().postDataJSON();assert.equal(body.replacement,'树是有限结点的集合。');revision++;value={contentRevision:revision};}
  else if(url.pathname.endsWith('review-confirm')){assert.equal(route.request().postDataJSON().version,revision);confirmed=true;revision++;}
  else throw Error('Unexpected route '+url.pathname);
  return route.fulfill({json:{ok:true,...value}});
 });
 await page.goto('http://rag-test/');
 await page.evaluate(()=>{
  window.XueyaRich={escape:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
  window.XueyaPlatform={available:true};
  window.XueyaWorkspaceAppearance={isOriginal:()=>true};
 });
 await page.addScriptTag({path:path.resolve('frontend/js/knowledge-base.js')});
 await page.evaluate(()=>{window.kb=window.XueyaKnowledgeBase.create({state:{view:'knowledge',courseId:'course-default'},store:{courses:[{id:'course-default',name:'测试课程'}],persist(){}},toast:t=>{throw Error(t)},render(){}});window.kb.mount();});
 await page.getByRole('button',{name:'查看资料',exact:true}).click();
 await page.getByText('仅收录原PDF第 82—84、86 页 · 原件共 324 页',{exact:true}).waitFor();
 await page.getByRole('button',{name:'校正与确认'}).click();
 await page.locator('#kbReviewText').fill('树是有限结点的集合。');
 await page.getByRole('button',{name:'保存校正',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#kbReviewConfirm')&&!document.querySelector('#kbCorrection button').disabled);
 await page.locator('#kbReviewConfirm input').check();
 await page.getByRole('button',{name:'确认当前修订',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('#kbDialog').open);
 assert(confirmed);assert.deepEqual(errors,[]);
 await page.screenshot({path:'test-results/chapter-draft/knowledge-review.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:'test-results/chapter-draft/knowledge-mobile.png',fullPage:true});
 await browser.close();console.log('Knowledge review browser lifecycle passed; controlled HTTP responses.');
})().catch(e=>{console.error(e);process.exit(1)});
