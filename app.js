const state = {
  currentView: "overview",
  cardCount: 6,
  questionIndex: 0,
  source: {
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
  }
};

const documents = [
  ["数据结构讲义 · 第 3 章.pdf", "树与二叉树 · 18 页 · 4.2 MB"],
  ["期中复习题 2024.pdf", "查找与排序 · 12 页 · 2.8 MB"],
  ["实验指导书.pdf", "二叉树遍历 · 8 页 · 1.6 MB"],
  ["课堂笔记 · 第 4 周.md", "递归与分治 · 3,821 字"],
  ["往年试题整理.txt", "综合复习 · 6,240 字"]
];

const questions = [
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

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2600);
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
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  $("#viewTitle").textContent = titles[view] || "学习总览";

  $("#overviewView").classList.toggle("hidden", view !== "overview");
  $(".quick-row").classList.toggle("hidden", view !== "overview");
  $("#chatView").classList.toggle("hidden", view !== "overview" && view !== "chat");
  $(".lower-grid").classList.toggle("hidden", view !== "overview");
  $("#libraryView").classList.toggle("hidden", view !== "library");
  $("#practiceView").classList.toggle("hidden", view !== "practice");
  $("#planView").classList.toggle("hidden", view !== "plan");

  if (view === "chat") {
    $("#chatView").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  refreshIcons();
}

function renderDocuments() {
  $("#documentList").innerHTML = documents.map(([name, meta], index) => `
    <div class="document-row">
      <div class="document-icon"><i data-lucide="${index % 3 === 1 ? "file-check-2" : "file-text"}"></i></div>
      <div class="document-copy"><strong>${name}</strong><span>${meta}</span></div>
      <span class="document-status">已索引</span>
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

function addChatMessage({ role, text, sources = [], meta = "" }) {
  const thread = $("#chatThread");
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : "ai-message"}`;
  const avatar = role === "user"
    ? `<div class="message-avatar">林</div>`
    : `<div class="message-avatar ai-avatar"><i data-lucide="sparkles"></i></div>`;
  const citationMarkup = sources.map((sourceId, index) => `
    <button class="citation-chip" type="button" data-source="${sourceId}">
      <span>${index + 1}</span>${sourceId === "source-1" ? "讲义 p.42" : sourceId === "source-2" ? "复习题 p.8" : "实验指导书 p.3"}
    </button>`).join("");
  article.innerHTML = `${avatar}<div class="message-body">
    ${role === "ai" ? `<div class="message-meta"><strong>学涯 Copilot</strong><span>${meta || "基于课程资料回答"}</span></div>` : ""}
    <p>${text}${citationMarkup ? `<br />${citationMarkup}` : ""}</p>
    ${role === "ai" && sources.length ? `<div class="answer-actions"><button class="mini-action" type="button" data-save-message><i data-lucide="bookmark-plus"></i>保存为知识卡片</button><button class="mini-action" type="button" data-follow-up><i data-lucide="corner-down-right"></i>继续追问</button></div>` : ""}
  </div>`;
  thread.appendChild(article);
  thread.scrollTop = thread.scrollHeight;
  refreshIcons();
}

function answerFor(question) {
  const value = question.toLowerCase();
  if (value.includes("复杂度") || value.includes("查找") || value.includes("二叉搜索")) {
    return {
      text: `在一棵高度为 <mark>h</mark> 的二叉搜索树中，查找操作最多沿着一条根到叶的路径进行，因此时间复杂度为 <strong>O(h)</strong>。如果树比较平衡，<mark>h ≈ log₂n</mark>，平均为 O(log n)；如果插入顺序让树退化成链表，最坏会变成 O(n)。`,
      sources: ["source-1", "source-2"],
      meta: "基于 2 个来源回答"
    };
  }
  if (value.includes("平衡") || value.includes("旋转")) {
    return {
      text: `平衡树通过旋转限制树高，使路径长度保持在对数级别。AVL 树会在插入或删除后检查平衡因子，并用单旋或双旋恢复结构，查找、插入和删除的平均复杂度为 <strong>O(log n)</strong>。`,
      sources: ["source-1", "source-2"],
      meta: "基于 2 个来源回答"
    };
  }
  if (value.includes("遍历") || value.includes("中序")) {
    return {
      text: `二叉搜索树的中序遍历会按照关键字从小到大访问节点，因此通常得到一个<strong>递增序列</strong>。这也是验证二叉搜索树结构是否正确的常用方法。`,
      sources: ["source-1", "source-3"],
      meta: "基于 2 个来源回答"
    };
  }
  return {
    text: `当前课程资料中没有足够依据回答这个问题。可以换一种问法，例如补充知识点名称或指定章节，我会继续在“数据结构”知识库中检索。`,
    sources: [],
    meta: "资料中未找到"
  };
}

function handleQuestion(question) {
  const cleanQuestion = question.trim();
  if (!cleanQuestion) {
    showToast("先输入一个课程问题");
    return;
  }
  addChatMessage({ role: "user", text: escapeHtml(cleanQuestion) });
  const answer = answerFor(cleanQuestion);
  setTimeout(() => addChatMessage({ role: "ai", text: answer.text, sources: answer.sources, meta: answer.meta }), 420);
}

function bindEvents() {
  $$(".nav-item").forEach((item) => item.addEventListener("click", () => showView(item.dataset.view)));
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
    if (event.key === "Escape") closeSource();
  });

  $("#chatThread").addEventListener("click", (event) => {
    const citation = event.target.closest("[data-source]");
    if (citation) openSource(citation.dataset.source);
    if (event.target.closest("[data-save-message]") || event.target.closest("#saveCard")) {
      state.cardCount += 1;
      $(".quick-stat:nth-child(3) strong").textContent = state.cardCount;
      showToast("已保存到知识卡片");
    }
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
    state.cardCount += 1;
    $(".quick-stat:nth-child(3) strong").textContent = state.cardCount;
    closeSource();
    showToast("原文已保存到知识卡片");
  });

  $("#clearChat").addEventListener("click", () => {
    $("#chatThread").innerHTML = `<div class="date-divider"><span>新的对话</span></div>`;
    showToast("已清空当前对话");
  });

  $("#refreshInsight").addEventListener("click", () => showToast("知识点脉搏已刷新"));

  $("#answerOptions").addEventListener("click", (event) => {
    const option = event.target.closest("button[data-answer]");
    if (!option) return;
    $$("#answerOptions button").forEach((item) => item.classList.remove("selected", "correct", "wrong"));
    option.classList.add("selected", option.dataset.answer === questions[state.questionIndex].answer ? "correct" : "wrong");
    $("#practiceStatus").textContent = option.dataset.answer === questions[state.questionIndex].answer ? "回答正确，继续保持" : "再看一眼来源，下一次会更稳";
  });

  $("#nextQuestion").addEventListener("click", () => {
    state.questionIndex = (state.questionIndex + 1) % questions.length;
    const question = questions[state.questionIndex];
    $("#practiceQuestion").textContent = question.prompt;
    $$("#answerOptions button").forEach((button, index) => {
      button.className = "";
      button.dataset.answer = ["A", "B", "C", "D"][index];
      button.innerHTML = `<span>${["A", "B", "C", "D"][index]}</span>${question.options[index]}`;
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

  $("#generatePractice").addEventListener("click", () => showToast("已生成 5 道针对“树与二叉树”的练习"));
  $("#regeneratePlan").addEventListener("click", () => showToast("复习计划已根据薄弱点重新排程"));
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

  $("#fileInput").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const row = document.createElement("div");
    row.className = "document-row";
    row.innerHTML = `<div class="document-icon"><i data-lucide="file-up"></i></div><div class="document-copy"><strong>${escapeHtml(file.name)}</strong><span>正在解析内容并建立索引</span></div><span class="document-status" style="color: var(--yellow)">解析中</span>`;
    $("#documentList").prepend(row);
    refreshIcons();
    setTimeout(() => {
      row.querySelector(".document-copy span").textContent = "刚刚加入 · 可检索";
      const status = row.querySelector(".document-status");
      status.textContent = "已索引";
      status.style.color = "var(--teal)";
      showToast(`${file.name} 已完成索引`);
    }, 1200);
    event.target.value = "";
  });

  $("#courseButton").addEventListener("click", () => showToast("当前仅开放“数据结构”课程空间"));
  $("#settingsButton").addEventListener("click", () => showToast("偏好设置即将开放"));
}

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  renderDocuments();
  refreshIcons();
});
