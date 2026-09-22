const { chromium } = require("playwright");
const fs = require("fs");

(async () => {
  fs.mkdirSync("docs/qa", { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" });
  const results = { desktop: {}, mobile: {}, consoleErrors: [], failedRequests: [] };
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  page.on("console", (msg) => { if (msg.type() === "error") results.consoleErrors.push(msg.text()); });
  page.on("requestfailed", (req) => results.failedRequests.push(`${req.url()} ${req.failure()?.errorText || ""}`));

  await page.goto("http://127.0.0.1:4173/", { waitUntil: "networkidle" });
  results.desktop.title = await page.title();
  results.desktop.noHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  results.desktop.heroVisible = await page.locator(".course-masthead").isVisible();
  results.desktop.chatVisible = await page.locator("#chatView").isVisible();
  await page.screenshot({ path: "docs/qa/desktop-overview.png", fullPage: true });

  await page.click('[data-chat-mode="summarize"]');
  await page.fill("#chatInput", "平衡树与旋转");
  await page.click(".send-button");
  await page.waitForFunction(() => !document.querySelector(".ai-message.loading-message"), null, { timeout: 60000 });
  results.desktop.modeResponse = await page.locator(".ai-message").last().innerText();
  results.desktop.engineStatus = await page.locator("#engineStatus").innerText();

  await page.keyboard.press("Control+k");
  results.desktop.commandPalette = await page.locator("#commandPalette").getAttribute("aria-hidden");
  await page.click('[data-command="library"]');
  results.desktop.libraryVisible = await page.locator("#libraryView").isVisible();
  await page.setInputFiles("#fileInput", [
    { name: "算法笔记.md", mimeType: "text/markdown", buffer: Buffer.from("# 算法笔记") },
    { name: "unsupported.exe", mimeType: "application/octet-stream", buffer: Buffer.from("test") }
  ]);
  await page.waitForTimeout(1500);
  results.desktop.uploadValid = await page.locator(".document-row", { hasText: "算法笔记.md" }).innerText();
  results.desktop.uploadRejected = await page.locator(".document-row", { hasText: "unsupported.exe" }).innerText();
  await page.reload({ waitUntil: "networkidle" });
  await page.click('[data-view="library"]');
  results.desktop.uploadPersisted = await page.locator(".document-row", { hasText: "算法笔记.md" }).isVisible();
  await page.screenshot({ path: "docs/qa/desktop-library.png", fullPage: true });

  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("http://127.0.0.1:4173/", { waitUntil: "networkidle" });
  results.mobile.noHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  results.mobile.heroVisible = await page.locator(".course-masthead").isVisible();
  results.mobile.navScrollable = await page.locator(".main-nav").evaluate((el) => el.scrollWidth >= el.clientWidth);
  await page.screenshot({ path: "docs/qa/mobile-overview.png", fullPage: true });

  console.log(JSON.stringify(results, null, 2));
  await browser.close();
})();