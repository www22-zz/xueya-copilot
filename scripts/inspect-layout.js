const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const page = await browser.newPage({ viewport: { width: 375, height: 812 } });
  await page.goto("http://127.0.0.1:4173/", { waitUntil: "networkidle" });
  const result = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    overflows: Array.from(document.querySelectorAll("body *")).map((el) => {
      const r = el.getBoundingClientRect();
      return { tag: el.tagName, cls: el.className, id: el.id, left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width), scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
    }).filter((x) => x.right > window.innerWidth + 1 || x.left < -1 || x.scrollWidth > x.clientWidth + 2).slice(0, 40)
  }));
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
})();