const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
loadEnv();
const PORT = Number(process.env.PORT || 4173);
const MIMO_BASE_URL = process.env.MIMO_BASE_URL || "https://api.xiaomimimo.com/v1";
const MIMO_MODEL = process.env.MIMO_MODEL || "mimo-v2.6-flash";
const MIMO_API_KEY = process.env.MIMO_API_KEY || "";

const sourceLibrary = {
  "source-1": {
    title: "数据结构讲义 · 第 3 章",
    location: "树与二叉树 · p.42",
    quote: "在一棵二叉搜索树中，查找操作从根节点开始，根据比较结果进入左子树或右子树，最多沿着一条根到叶的路径进行。"
  },
  "source-2": {
    title: "期中复习题 2024",
    location: "查找与排序 · p.8",
    quote: "平衡二叉搜索树的高度与节点数量呈对数关系，查找、插入和删除的平均时间复杂度为 O(log n)。"
  },
  "source-3": {
    title: "实验指导书",
    location: "二叉树遍历实验 · p.3",
    quote: "遍历序列可以作为验证二叉树结构和实现递归算法的实验输入。"
  }
};

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon"
};

function sendJson(res, status, data) {
  const body = JSON.stringify(data);
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(body) });
  res.end(body);
}

function loadEnv() {
  const envPath = path.join(ROOT, ".env");
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/i);
    if (!match || process.env[match[1]]) continue;
    process.env[match[1]] = match[2].replace(/^["']|["']$/g, "");
  }
}

function buildPrompt(question, mode, sourceIds) {
  const sources = sourceIds.map((id) => sourceLibrary[id]).filter(Boolean);
  const sourceText = sources.length
    ? sources.map((source, index) => `[${index + 1}] ${source.title} / ${source.location}\n${source.quote}`).join("\n\n")
    : "当前没有命中资料片段。";
  const modeText = {
    ask: "根据资料回答问题，解释清楚，保持简洁。",
    summarize: "将内容整理成适合复习的知识卡片，包含定义、关键点和一个记忆提示。",
    quiz: "生成一道有明确答案和解析的练习题。"
  }[mode] || "根据资料回答问题。";
  return `你是“学涯 Copilot”的课程学习助手。只能使用下方课程资料回答；资料不足时明确说未找到，不要编造。
输出必须是严格 JSON，格式：{"answer":"用中文撰写的回答","sources":["source-1"],"knowledgePoints":["知识点"],"confidence":0.0到1.0}
${modeText}
课程资料：
${sourceText}

用户问题：${question}`;
}

function extractJson(content) {
  const match = content.match(/\{[\s\S]*\}/);
  if (!match) return null;
  try { return JSON.parse(match[0]); } catch { return null; }
}

async function callMimo(question, mode, sourceIds) {
  if (!MIMO_API_KEY) throw new Error("MIMO_API_KEY is not configured");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45000);
  try {
    const response = await fetch(`${MIMO_BASE_URL}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${MIMO_API_KEY}`
      },
      body: JSON.stringify({
        model: MIMO_MODEL,
        temperature: 0.25,
        messages: [
          { role: "system", content: "你是一个严谨的中文课程资料助手，只输出 JSON，不使用 emoji，不编造资料外事实。" },
          { role: "user", content: buildPrompt(question, mode, sourceIds) }
        ]
      }),
      signal: controller.signal
    });
    const raw = await response.text();
    if (!response.ok) throw new Error(`MiMo API ${response.status}: ${raw.slice(0, 300)}`);
    const payload = JSON.parse(raw);
    const content = payload?.choices?.[0]?.message?.content || "";
    const parsed = extractJson(content);
    if (!parsed || typeof parsed.answer !== "string") throw new Error("MiMo returned an invalid response");
    return {
      answer: parsed.answer,
      sources: Array.isArray(parsed.sources) ? parsed.sources.filter((id) => sourceLibrary[id]) : [],
      knowledgePoints: Array.isArray(parsed.knowledgePoints) ? parsed.knowledgePoints : [],
      confidence: Number.isFinite(parsed.confidence) ? parsed.confidence : 0.8,
      model: payload.model || MIMO_MODEL,
      usage: payload.usage || null
    };
  } finally {
    clearTimeout(timer);
  }
}

function serveStatic(req, res) {
  const requestPath = decodeURIComponent((req.url || "/").split("?")[0]);
  const safePath = path.normalize(requestPath === "/" ? "/index.html" : requestPath).replace(/^([/\\])+/, "");
  const filePath = path.join(ROOT, safePath);
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }
  fs.stat(filePath, (error, stat) => {
    if (error || !stat.isFile()) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(filePath).toLowerCase()] || "application/octet-stream" });
    fs.createReadStream(filePath).pipe(res);
  });
}

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/api/health") {
    sendJson(res, 200, { ok: true, engine: MIMO_API_KEY ? "xiaomi-mimo" : "local-fallback", model: MIMO_MODEL });
    return;
  }
  if (req.method === "POST" && req.url === "/api/ai") {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1000000) req.destroy();
    });
    req.on("end", async () => {
      try {
        const input = JSON.parse(body || "{}");
        const question = String(input.question || "").slice(0, 4000);
        const mode = ["ask", "summarize", "quiz"].includes(input.mode) ? input.mode : "ask";
        const sourceIds = Array.isArray(input.sources) ? input.sources.slice(0, 6) : [];
        if (!question.trim()) {
          sendJson(res, 400, { ok: false, error: "question is required" });
          return;
        }
        const result = await callMimo(question, mode, sourceIds);
        sendJson(res, 200, { ok: true, ...result });
      } catch (error) {
        sendJson(res, 200, { ok: false, error: error.message || "AI request failed", engine: "local-fallback" });
      }
    });
    return;
  }
  serveStatic(req, res);
});

loadEnv();
server.listen(PORT, "127.0.0.1", () => {
  console.log(`Xueya Copilot running at http://127.0.0.1:${PORT}`);
});