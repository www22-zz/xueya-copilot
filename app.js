const STORAGE_KEY = "xueya-copilot-state-v1";
const sourceLibrary = {
  "source-1": {
    title: "数据结构讲义 · 第 3 章",
    location: "树与二叉树 · p.42",
    quote: "在一棵二叉搜索树中，查找操作从根节点开始，根据比较结果进入左子树或右子树，最多沿着一条根到叶的路径进行。",
    keywords: ["二叉搜索树", "查找", "复杂度", "树", "路径", "节点", "高度"]
  },
  "source-2": {
    title: "期中复习题 2024",
    location: "查找与排序 · p.8",
    quote: "平衡二叉搜索树的高度与节点数量呈对数关系，查找、插入和删除的平均时间复杂度为 O(log n)。",
    keywords: ["平衡", "旋转", "AVL", "复杂度", "查找", "排序", "log"]
  },
  "source-3": {
    title: "实验指导书",
    location: "二叉树遍历实验 · p.3",
    quote: "遍历序列可以作为验证二叉树结构和实现递归算法的实验输入。",
    keywords: ["遍历", "中序", "递归", "实验", "序列", "二叉树"]
  }
};

const initialQuestions = [
  {
    prompt: "一棵有 15 个节点的平衡二叉搜索树，查找一个节点最多需要比较多少次？",
    options: ["3 次", "4 次", "7 次", "15 次"],
    answer: "B"
  },
  {
    prompt: "下面哪种情况会让二叉搜索树的查找复杂度退化到 O(n)？",
    options: ["节点按照从小到大的顺序插入", "每次插入后进行一次旋转", "树中所有节点都有两个孩子", "节点数量是 2 的幂"],
    answer: "A"
  },
  {
    prompt: "对一棵二叉搜索树进行中序遍历，通常会得到什么序列？",
    options: ["层次序列", "递减序列", "递增序列", "随机序列"],
    answer: "C"
  }
];

const initialDocuments = [
  { id: "doc-1", name: "数据结构讲义 · 第 3 章.pdf", meta: "树与二叉树 · 18 页 · 4.2 MB", status: "已索引" },
  { id: "doc-2", name: "期中复习题 2024.pdf", meta: "查找与排序 · 12 页 · 2.8 MB", status: "已索引" },
  { id: "doc-3", name: "实验指导书.pdf", meta: "二叉树遍历 · 8 页 · 1.6 MB", status: "已索引" },
  { id: "doc-4", name: "课堂笔记 · 第 4 周.md", meta: "递归与分治 · 3,821 字", status: "已索引" },
  { id: "doc-5", name: "往年试题整理.txt", meta: "综合复习 · 6,240 字", status: "已索引" }
];

const saved = (() => {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch { return {}; }
})();

const state = {
  currentView: "overview",
  chatMode: "ask",
  cardCount: Number(saved.cardCount || 6),
  questionIndex: 0,
  questions: initialQuestions,
  documents: Array.isArray(saved.documents) && saved.documents.length ? saved.documents : initialDocuments,
  savedCards: Array.isArray(saved.savedCards) ? saved.savedCards : [],
  source: sourceLibrary
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function persistState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    cardCount: state.cardCount,
    documents: state.documents,
    savedCards: state.savedCards
  }));
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

function renderRichText(value) {
  return escapeHtml(value)
    .replace(/\n\n/g, "<br><br>")
    .replace(/\n/g, "<br>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

async function requestMiMo(question, sources, mode) {
  const response = await fetch("/api/ai", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, sources, mode })
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || "MiMo request failed");
  return payload;
}

async function checkEngine() {
  try {
    const payload = await (await fetch("/api/health")).json();
    const status = $("#engineStatus");
    if (payload.engine === "xiaomi-mimo") {
      status.textContent = "MiMo 已连接";
      status.classList.add("online");
    } else {
      status.textContent = "本地降级";
      status.classList.add("offline");
    }
  } catch {
    $("#engineStatus").textContent = "本地降级";
    $("#engineStatus").classList.add("offline");
  }
}
function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2800);
}

function showView(view) {
  state.currentView = view;
  const titles = {
    overview: "学习总览",
    chat: "问一问资料",
    library: "课程知识库",
    practice: "练习与错题",
    plan: "复习计划"
  };
  $$(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === view);
    const label = item.querySelector("span:not(.nav-count)")?.textContent || "导航";
    item.title = label;
    item.setAttribute("aria-label", label);
  });
  $("#viewTitle").textContent = titles[view] || "学习总览";

  $("#overviewView").classList.toggle("hidden", view !== "overview");
  $(".quick-row").classList.toggle("hidden", view !== "overview");
  $("#chatView").classList.toggle("hidden", view !== "overview" && view !== "chat");
  $(".lower-grid").classList.toggle("hidden", view !== "overview");
  $("#libraryView").classList.toggle("hidden", view !== "library");
  $("#practiceView").classList.toggle("hidden", view !== "practice");
  $("#planView").classList.toggle("hidden", view !== "plan");

  if (view === "chat") $("#chatView").scrollIntoView({ behavior: "smooth", block: "start" });
  refreshIcons();
}

function renderDocuments() {
  $("#documentList").innerHTML = state.documents.map((doc, index) => `
    <div class="document-row" data-document-id="${doc.id}">
      <div class="document-icon"><i data-lucide="${index % 3 === 1 ? "file-check-2" : "file-text"}"></i></div>
      <div class="document-copy"><strong>${escapeHtml(doc.name)}</strong><span>${escapeHtml(doc.meta)}</span></div>
      <span class="document-status" style="${doc.status !== "已索引" ? "color: var(--yellow)" : ""}">${escapeHtml(doc.status)}</span>
      <button class="icon-button subtle" type="button" title="打开资料" aria-label="打开资料"><i data-lucide="arrow-up-right"></i></button>
    </div>
  `).join("");
  refreshIcons();
}

function openSource(sourceId) {
  const source = state.source[sourceId] || state.source["source-1"];
  $("#drawerTitle").textContent = source.title;
  $("#drawerLocation").textContent = source.location;
  $("#drawerQuote").textContent = source.quote;
  $("#sourceDrawer").classList.add("open");
  $("#sourceDrawer").setAttribute("aria-hidden", "false");
}

function closeSource() {
  $("#sourceDrawer").classList.remove("open");
  $("#sourceDrawer").setAttribute("aria-hidden", "true");
}

function retrieve(question) {
  const normalized = question.toLowerCase();
  return Object.entries(state.source)
    .map(([id, source]) => ({
      id,
      score: source.keywords.reduce((total, keyword) => total + (normalized.includes(keyword.toLowerCase()) ? 1 : 0), 0)
    }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map((item) => item.id);
}

function answerFor(question, mode = state.chatMode) {
  const sources = retrieve(question);
  const value = question.toLowerCase();
  if (mode === "summarize") {
    return {
      text: `围绕“${escapeHtml(question)}”，我整理出三个学习重点：先理解定义和适用条件，再掌握典型操作或算法，最后用一道例题验证是否真正掌握。当前资料中检索到 ${sources.length} 个相关片段，建议先保存为知识卡片再进入练习。`,
      sources,
      meta: `整理自 ${sources.length} 个片段`
    };
  }
  if (mode === "quiz") {
    return {
      text: `练习建议：请先判断“${escapeHtml(question)}”的定义、关键条件和典型边界情况。答完后我会把错题加入复习计划。当前资料中检索到 ${sources.length} 个相关片段。`,
      sources,
      meta: `练习依据 ${sources.length} 个片段`
    };
  }
  if (!sources.length) {
    return {
      text: `我在当前课程知识库中没有找到足够依据。可以补充“二叉搜索树”“平衡树”“遍历”等关键词，或先上传相关资料。`,
      sources: [],
      meta: "检索结果为空"
    };
  }
  if (value.includes("复杂度") || value.includes("查找") || value.includes("二叉搜索")) {
    return {
      text: `检索到树与查找相关片段。在一棵高度为 <mark>h</mark> 的二叉搜索树中，查找操作最多沿着一条根到叶的路径进行，因此时间复杂度为 <strong>O(h)</strong>。平衡时 <mark>h ≈ log₂n</mark>，平均为 O(log n)；树退化成链表时，最坏为 O(n)。`,
      sources,
      meta: `检索到 ${sources.length} 个相关片段`
    };
  }
  if (value.includes("平衡") || value.includes("旋转") || value.includes("avl")) {
    return {
      text: `相关资料指出，平衡树通过旋转限制树高。AVL 树会在插入或删除后检查平衡因子，并用单旋或双旋恢复结构，使查找、插入和删除保持在 <strong>O(log n)</strong> 的平均复杂度。`,
      sources,
      meta: `检索到 ${sources.length} 个相关片段`
    };
  }
  if (value.includes("遍历") || value.includes("中序") || value.includes("递归")) {
    return {
      text: `根据实验指导书，中序遍历会按照关键字从小到大访问二叉搜索树节点，通常得到一个<strong>递增序列</strong>，也可以用来验证树结构和递归实现。`,
      sources,
      meta: `检索到 ${sources.length} 个相关片段`
    };
  }
  return {
    text: `我检索到 ${sources.length} 个可能相关的资料片段，但它们还不足以形成可靠结论。建议把问题聚焦到具体章节、概念或公式，我会继续沿证据回答。`,
    sources,
    meta: "需要更具体的提问"
  };
}
function aiBodyMarkup(answer) {
  const citationMarkup = answer.sources.map((sourceId, index) => `
    <button class="citation-chip" type="button" data-source="${sourceId}">
      <span>${index + 1}</span>${sourceId === "source-1" ? "讲义 p.42" : sourceId === "source-2" ? "复习题 p.8" : "实验指导书 p.3"}
    </button>`).join("");
  const answerText = answer.html ? answer.text : renderRichText(answer.text);
  const knowledgePoints = Array.isArray(answer.knowledgePoints) ? answer.knowledgePoints.slice(0, 4) : [];
  const knowledgeMarkup = knowledgePoints.length
    ? `<div class="knowledge-pills"><span>知识点</span>${knowledgePoints.map((point) => `<b>${escapeHtml(point)}</b>`).join("")}</div>`
    : "";
  const confidence = Number.isFinite(answer.confidence)
    ? `<span><i class="confidence-dot"></i>置信度 ${Math.round(answer.confidence * 100)}%</span>`
    : "";
  return `<div class="message-meta"><strong>学涯 Copilot</strong><span>${answer.meta}</span>${confidence}</div><p>${answerText}${citationMarkup ? `<br />${citationMarkup}` : ""}</p>${knowledgeMarkup}${answer.sources.length ? `<div class="answer-actions"><button class="mini-action" type="button" data-save-message><i data-lucide="bookmark-plus"></i>保存为知识卡片</button><button class="mini-action" type="button" data-follow-up><i data-lucide="corner-down-right"></i>继续追问</button></div>` : ""}`;
}
function addChatMessage({ role, text, sources = [], meta = "", loading = false }) {
  const thread = $("#chatThread");
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : "ai-message"}${loading ? " loading-message" : ""}`;
  const avatar = role === "user"
    ? `<div class="message-avatar">林</div>`
    : `<div class="message-avatar ai-avatar"><i data-lucide="${loading ? "loader-circle" : "sparkles"}"></i></div>`;
  const body = role === "ai" && loading
    ? `<div class="message-meta"><strong>学涯 Copilot</strong><span>${meta}</span></div><p class="loading-copy">${text}</p>`
    : role === "ai"
      ? aiBodyMarkup({ text, sources, meta })
      : `<p>${text}</p>`;
  article.innerHTML = `${avatar}<div class="message-body">${body}</div>`;
  thread.appendChild(article);
  thread.scrollTop = thread.scrollHeight;
  refreshIcons();
  return article;
}

async function handleQuestion(question) {
  const cleanQuestion = question.trim();
  if (!cleanQuestion) {
    showToast("先输入一个课程问题");
    return;
  }
  addChatMessage({ role: "user", text: escapeHtml(cleanQuestion) });
  const loading = addChatMessage({ role: "ai", text: "正在检索课程知识库并整理证据…", meta: "MiMo 检索中", loading: true });
  const localSources = retrieve(cleanQuestion);
  try {
    const remote = await requestMiMo(cleanQuestion, localSources, state.chatMode);
    const sources = remote.sources.length ? remote.sources : localSources;
    const answer = {
      text: remote.answer,
      sources,
      meta: `MiMo ${remote.model || "V2.6"} · 检索到 ${sources.length} 个来源`,
      knowledgePoints: remote.knowledgePoints || [],
      confidence: remote.confidence,
      html: false
    };
    loading.classList.remove("loading-message");
    loading.querySelector(".message-body").innerHTML = aiBodyMarkup(answer);
    $("#engineStatus").textContent = "MiMo 已连接";
    $("#engineStatus").classList.add("online");
    $("#engineStatus").classList.remove("offline");
  } catch (error) {
    const answer = answerFor(cleanQuestion, state.chatMode);
    answer.html = true;
    answer.meta = `本地降级 · ${answer.meta}`;
    loading.classList.remove("loading-message");
    loading.querySelector(".message-body").innerHTML = aiBodyMarkup(answer);
    $("#engineStatus").textContent = "本地降级";
    $("#engineStatus").classList.add("offline");
    $("#engineStatus").classList.remove("online");
  }
  $("#chatThread").scrollTop = $("#chatThread").scrollHeight;
  refreshIcons();
}
function saveCard() {
  state.cardCount += 1;
  state.savedCards.push({ createdAt: new Date().toISOString() });
  $(".quick-stat:nth-child(3) strong").textContent = state.cardCount;
  persistState();
  showToast("已保存到知识卡片");
}

function openCommandPalette() {
  $("#commandPalette").classList.add("open");
  $("#commandPalette").setAttribute("aria-hidden", "false");
  $("#commandInput").value = "";
  filterCommands("");
  setTimeout(() => $("#commandInput").focus(), 20);
}

function closeCommandPalette() {
  $("#commandPalette").classList.remove("open");
  $("#commandPalette").setAttribute("aria-hidden", "true");
}

function filterCommands(value) {
  const keyword = value.trim().toLowerCase();
  $$("[data-command]").forEach((button) => {
    button.hidden = keyword && !button.textContent.toLowerCase().includes(keyword);
  });
}

function runCommand(command) {
  closeCommandPalette();
  if (command === "upload") {
    showView("library");
    setTimeout(() => $("#fileInput").click(), 80);
    return;
  }
  showView(command);
}
function bindEvents() {
  $$(".nav-item").forEach((item) => {
    const label = item.querySelector("span:not(.nav-count)")?.textContent || "导航";
    item.title = label;
    item.setAttribute("aria-label", label);
    item.addEventListener("click", () => showView(item.dataset.view));
  });
  $$("[data-view-jump]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.viewJump)));

  $("#chatForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("#chatInput");
    handleQuestion(input.value);
    input.value = "";
  });

  $("#chatInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("#chatForm").requestSubmit();
    }
  });

  $("#globalSearch").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      showView("chat");
      handleQuestion(event.currentTarget.value);
      event.currentTarget.value = "";
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
      event.preventDefault();
      $("#globalSearch").focus();
    }
    if (event.key === "Escape") { closeSource(); closeCommandPalette(); }
  });

  $("#chatThread").addEventListener("click", (event) => {
    const citation = event.target.closest("[data-source]");
    if (citation) openSource(citation.dataset.source);
    if (event.target.closest("[data-save-message]") || event.target.closest("#saveCard")) saveCard();
    if (event.target.closest("[data-follow-up]") || event.target.closest("#askFollowUp")) {
      $("#chatInput").focus();
      $("#chatInput").value = "那么它和 AVL 树有什么区别？";
    }
  });

  $$(".source-card").forEach((card) => card.addEventListener("click", () => {
    $$(".source-card").forEach((item) => item.classList.remove("selected"));
    card.classList.add("selected");
    openSource(card.id);
  }));

  $("#drawerClose").addEventListener("click", closeSource);
  $("#drawerBackdrop").addEventListener("click", closeSource);
  $("#drawerSave").addEventListener("click", () => {
    saveCard();
    closeSource();
  });

  $("#clearChat").addEventListener("click", () => {
    $("#chatThread").innerHTML = `<div class="date-divider"><span>新的对话</span></div>`;
    showToast("已清空当前对话");
  });

  $("#refreshInsight").addEventListener("click", () => {
    $$(".topic-bar span").forEach((bar, index) => {
      const value = [76, 68, 55][index] || 50;
      bar.style.width = `${value}%`;
      bar.parentElement.parentElement.querySelector(".topic-score").textContent = `${value}%`;
    });
    showToast("知识点脉搏已刷新");
  });

  $("#answerOptions").addEventListener("click", (event) => {
    const option = event.target.closest("button[data-answer]");
    if (!option) return;
    const question = state.questions[state.questionIndex];
    $$("#answerOptions button").forEach((item) => item.classList.remove("selected", "correct", "wrong"));
    option.classList.add("selected", option.dataset.answer === question.answer ? "correct" : "wrong");
    $("#practiceStatus").textContent = option.dataset.answer === question.answer ? "回答正确，继续保持" : "再看一眼来源，下一次会更稳";
  });

  $("#nextQuestion").addEventListener("click", () => {
    state.questionIndex = (state.questionIndex + 1) % state.questions.length;
    const question = state.questions[state.questionIndex];
    $("#practiceQuestion").textContent = question.prompt;
    $$("#answerOptions button").forEach((button, index) => {
      const key = ["A", "B", "C", "D"][index];
      button.className = "";
      button.dataset.answer = key;
      button.innerHTML = `<span>${key}</span>${question.options[index]}`;
    });
    $("#practiceStatus").textContent = "选择一个答案";
  });

  $$(".answer-options.vertical button").forEach((button) => button.addEventListener("click", () => {
    $$(".answer-options.vertical button").forEach((item) => item.classList.remove("selected", "correct", "wrong"));
    const correct = button.dataset.fullAnswer === "A";
    button.classList.add("selected", correct ? "correct" : "wrong");
    const result = $("#quizResult");
    result.classList.remove("hidden");
    result.textContent = correct ? "正确。按顺序插入会让二叉搜索树退化成链表，查找路径变成 O(n)。" : "不正确。最典型的退化情况是节点按顺序插入，树会变成一条链。";
    result.style.borderColor = correct ? "var(--teal)" : "var(--coral)";
    result.style.background = correct ? "var(--teal-soft)" : "var(--coral-soft)";
    result.style.color = correct ? "var(--teal)" : "var(--coral)";
    refreshIcons();
  }));

  $("#generatePractice").addEventListener("click", () => {
    state.questionIndex = 0;
    $("#quizResult").classList.add("hidden");
    $$(".answer-options.vertical button").forEach((item) => item.classList.remove("selected", "correct", "wrong"));
    showToast("已生成 5 道针对“树与二叉树”的练习");
  });

  $("#regeneratePlan").addEventListener("click", () => {
    const items = $$(".timeline-item");
    items.forEach((item, index) => item.classList.toggle("active", index === 1));
    showToast("复习计划已根据薄弱点重新排程");
  });

  $("#editExam").addEventListener("click", () => {
    const current = window.prompt("输入考试日期（YYYY-MM-DD）", "2026-11-08");
    if (!current) return;
    const date = new Date(`${current}T00:00:00`);
    if (Number.isNaN(date.getTime())) {
      showToast("日期格式应为 YYYY-MM-DD");
      return;
    }
    const days = Math.max(0, Math.ceil((date - new Date()) / 86400000));
    $("#examDateLabel").textContent = `还有 ${days} 天`;
    $(".date-chip").textContent = `${String(date.getMonth() + 1).padStart(2, "0")} 月 ${String(date.getDate()).padStart(2, "0")} 日`;
    showToast("考试日期已更新");
  });

  $$("[data-chat-mode]").forEach((button) => button.addEventListener("click", () => {
    state.chatMode = button.dataset.chatMode;
    $$("[data-chat-mode]").forEach((item) => item.classList.toggle("active", item === button));
    const placeholders = {
      ask: "输入一个关于课程资料的问题…",
      summarize: "输入一个知识点，整理为学习卡片…",
      quiz: "输入一个知识点，生成一道练习题…"
    };
    $("#chatInput").placeholder = placeholders[state.chatMode];
    showToast(state.chatMode === "ask" ? "已切换到资料问答" : state.chatMode === "summarize" ? "已切换到知识整理" : "已切换到练习生成");
  }));

  $$("[data-command]").forEach((button) => button.addEventListener("click", () => runCommand(button.dataset.command)));
  $("#commandBackdrop").addEventListener("click", closeCommandPalette);
  $("#commandInput").addEventListener("input", (event) => filterCommands(event.currentTarget.value));

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openCommandPalette();
    }
  });
  $("#fileInput").addEventListener("change", (event) => {
    const files = Array.from(event.target.files || []);
    const supported = ["pdf", "docx", "txt", "md"];
    files.forEach((file, index) => {
      const extension = file.name.split(".").pop().toLowerCase();
      const row = document.createElement("div");
      row.className = "document-row";
      const valid = supported.includes(extension);
      row.innerHTML = `<div class="document-icon"><i data-lucide="${valid ? "file-up" : "file-warning"}"></i></div><div class="document-copy"><strong>${escapeHtml(file.name)}</strong><span>${valid ? "正在解析内容并建立索引" : "格式不受支持，请上传 PDF、DOCX、TXT 或 MD"}</span></div><span class="document-status" style="color: ${valid ? "var(--yellow)" : "var(--coral)"}">${valid ? "解析中" : "失败"}</span>`;
      $("#documentList").prepend(row);
      refreshIcons();
      if (!valid) {
        showToast(`${file.name} 的格式不受支持`);
        return;
      }
      setTimeout(() => {
        row.querySelector(".document-copy span").textContent = "刚刚加入 · 可检索";
        const status = row.querySelector(".document-status");
        status.textContent = "已索引";
        status.style.color = "var(--teal)";
        state.documents.unshift({
          id: `doc-${Date.now()}-${index}`,
          name: file.name,
          meta: `${extension.toUpperCase()} · 本地资料 · 刚刚上传`,
          status: "已索引"
        });
        persistState();
        showToast(`${file.name} 已完成索引`);
      }, 1000 + index * 180);
    });
    event.target.value = "";
  });

  $("#courseButton").addEventListener("click", () => showToast("当前课程空间：数据结构"));
  $("#settingsButton").addEventListener("click", () => showToast(`AI 引擎：${$("#engineStatus").textContent}`));
}

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  renderDocuments();
  checkEngine();
  $(".quick-stat:nth-child(3) strong").textContent = state.cardCount;
  refreshIcons();
});
