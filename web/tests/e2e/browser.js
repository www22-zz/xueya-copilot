// Optional standalone regression runner for developers with Playwright installed.
// Current redesign was checked through the desktop app's browser tools.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const outputDirectory=path.resolve(__dirname,'../../test-results/browser');
(async()=>{
  const options={headless:true};
  if(process.env.CHROME_PATH)options.executablePath=process.env.CHROME_PATH;
  const browser=await chromium.launch(options);
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  fs.mkdirSync(outputDirectory,{recursive:true});
  try{
    await page.goto('http://127.0.0.1:4173/');
    assert.equal(await page.locator('.hero h1').innerText(),'让知识，\n真正连起来。');
    await page.getByRole('tab',{name:'记得牢固'}).click();
    assert.match(await page.locator('#demoContent').innerText(),/知识卡片/);
    await page.getByRole('link',{name:'进入学习空间',exact:true}).click();
    await page.getByRole('link',{name:'练习与错题',exact:true}).click();
    await page.locator('[data-option="0"]').click();
    await page.getByRole('button',{name:'提交答案',exact:true}).click();
    assert.match(await page.locator('.quiz-feedback').innerText(),/再学一次/);
    await page.getByRole('link',{name:'复习计划',exact:true}).click();
    await page.locator('[data-task]').first().check();
    await page.reload();assert.equal(await page.locator('[data-task]').first().isChecked(),true);
    for(const width of [1440,768,375]){
      await page.setViewportSize({width,height:900});
      for(const view of ['overview','chat','library','cards','practice','plan']){
        await page.goto(`http://127.0.0.1:4173/#space/${view}`);
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${view} overflows at ${width}`);
      }
    }
    await page.goto('http://127.0.0.1:4173/#home');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(outputDirectory,'regression-mobile.png')});
    assert.deepEqual(errors,[]);
    console.log('Home interactions, practice, plan persistence and responsive pages passed.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
