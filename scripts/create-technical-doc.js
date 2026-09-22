const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, PageBreak, Header, Footer, PageNumber
} = require("docx");

const FONT = "Microsoft YaHei";
const BLUE = "315CE5";
const INK = "14202B";
const MUTED = "52606D";
const PALE = "EAF0FF";

const p = (text, options = {}) => new Paragraph({
  spacing: { after: options.after ?? 140, line: 330 },
  children: [new TextRun({ text, font: FONT, size: options.size ?? 21, color: options.color ?? INK, bold: options.bold ?? false })]
});

const numbered = (text, n) => new Paragraph({
  spacing: { after: 90, line: 310 },
  children: [new TextRun({ text: `${n}. ${text}`, font: FONT, size: 21, color: INK })]
});

const heading = (text, level) => new Paragraph({
  heading: level,
  spacing: { before: level === HeadingLevel.HEADING_1 ? 320 : 220, after: 120 },
  children: [new TextRun({ text, font: FONT, color: level === HeadingLevel.HEADING_1 ? BLUE : INK, bold: true })]
});

const caption = (text) => new Paragraph({
  spacing: { before: 50, after: 180 },
  children: [new TextRun({ text, font: FONT, size: 17, color: MUTED, italics: true })]
});

const table = (headers, rows, widths) => new Table({
  width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
  columnWidths: widths,
  borders: {
    top: { style: BorderStyle.SINGLE, size: 4, color: "D9E0E5" },
    bottom: { style: BorderStyle.SINGLE, size: 4, color: "D9E0E5" },
    left: { style: BorderStyle.SINGLE, size: 4, color: "D9E0E5" },
    right: { style: BorderStyle.SINGLE, size: 4, color: "D9E0E5" },
    insideHorizontal: { style: BorderStyle.SINGLE, size: 3, color: "E4E9EC" },
    insideVertical: { style: BorderStyle.SINGLE, size: 3, color: "E4E9EC" }
  },
  rows: [
    new TableRow({
      tableHeader: true,
      children: headers.map((text) => new TableCell({
        width: { size: widths[headers.indexOf(text)], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: PALE },
        margins: { top: 100, bottom: 100, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text, font: FONT, size: 19, bold: true, color: INK })] })]
      }))
    }),
    ...rows.map((row) => new TableRow({
      children: row.map((text, index) => new TableCell({
        width: { size: widths[index], type: WidthType.DXA },
        margins: { top: 95, bottom: 95, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text, font: FONT, size: 18, color: INK })] })]
      }))
    }))
  ]
});

const code = (text) => new Paragraph({
  spacing: { before: 80, after: 160 },
  shading: { type: ShadingType.CLEAR, fill: "F3F5F6" },
  children: [new TextRun({ text, font: "Consolas", size: 17, color: INK })]
});

const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

const doc = new Document({
  creator: "学涯 Copilot",
  title: "学涯 Copilot 技术文档",
  description: "AI WEB 网页开发挑战赛参赛作品技术文档",
  styles: {
    default: { document: { run: { font: FONT, size: 21, color: INK } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 38, bold: true, color: BLUE },
        paragraph: { alignment: AlignmentType.CENTER, spacing: { after: 180 } } }
    ]
  },
  sections: [{
    properties: { page: { margin: { top: 1100, right: 1100, bottom: 1100, left: 1100 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "学涯 Copilot · 技术文档", font: FONT, size: 16, color: MUTED })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "第 ", font: FONT, size: 16, color: MUTED }), new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: MUTED }), new TextRun({ text: " 页", font: FONT, size: 16, color: MUTED })] })] }) },
    children: [
      new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun({ text: "学涯 Copilot 技术文档", font: FONT, size: 38, bold: true, color: BLUE })] }),
      p("基于课程知识库的 AI 学习副驾", { size: 25, color: MUTED, after: 280 }),
      p("项目类型：AI WEB 网页开发挑战赛参赛作品", { size: 21, color: MUTED }),
      p("文档版本：v1.0　　更新日期：2026-09-22", { size: 21, color: MUTED }),
      p("项目定位：将课程资料转化为可检索、可引用、可练习、可规划的学习资产，帮助学生完成从资料输入到能力提升的闭环。", { size: 22, after: 300 }),
      table(["文档目录", "内容"], [
        ["1", "项目概述"],
        ["2", "需求分析"],
        ["3", "系统架构设计"],
        ["4", "AI 技术方案"],
        ["5", "核心功能实现"],
        ["6", "测试与部署"],
        ["7", "创新点说明"],
        ["8", "总结与展望"]
      ], [1000, 7600]),
      pageBreak(),

      heading("1. 项目概述", HeadingLevel.HEADING_1),
      heading("1.1 项目背景", HeadingLevel.HEADING_2),
      p("大学生在课程学习中通常需要处理大量讲义、PPT、教材、实验指导书和历年试题。传统资料管理方式存在资料分散、AI 回答缺乏可靠出处、学习行为停留在问答三个问题。"),
      heading("1.2 项目定位", HeadingLevel.HEADING_2),
      p("学涯 Copilot 是一个基于课程知识库的 AI 学习副驾。它将课程资料转化为可检索、可引用、可练习、可规划的学习资产，帮助学生完成从“资料输入”到“能力提升”的闭环。"),
      code("上传课程资料 → 建立知识库 → AI 问答 → 查看原文引用 → 保存知识卡片 → 生成练习题 → 生成复习计划"),
      heading("1.3 目标用户", HeadingLevel.HEADING_2),
      numbered("需要备考和整理课程重点的大学生", 1),
      numbered("需要快速检索课程资料的学生", 2),
      numbered("希望根据薄弱知识点安排复习计划的学习者", 3),
      heading("1.4 项目目标", HeadingLevel.HEADING_2),
      numbered("让 AI 回答具备可追溯的课程资料依据。", 1),
      numbered("将 RAG 问答与学习练习、复习规划连接起来。", 2),
      numbered("提供清晰、稳定、适合演示的 Web 产品体验。", 3),
      numbered("为后续接入真实大模型、向量数据库和用户系统预留扩展接口。", 4),

      heading("2. 需求分析", HeadingLevel.HEADING_1),
      heading("2.1 功能需求", HeadingLevel.HEADING_2),
      table(["模块", "功能", "优先级"], [
        ["课程空间", "展示当前课程和学习概览", "P0"],
        ["知识库", "上传 PDF、DOCX、TXT、MD 资料，展示索引状态", "P0"],
        ["AI 问答", "根据课程资料回答问题，支持多轮追问", "P0"],
        ["引用溯源", "展示命中来源、页码和原文片段", "P0"],
        ["知识卡片", "将回答或原文保存为重点知识", "P1"],
        ["练习系统", "根据知识点生成练习题并提供答题反馈", "P1"],
        ["复习计划", "根据考试日期和薄弱点安排学习任务", "P1"],
        ["状态持久化", "保存资料记录、知识卡片和学习状态", "P1"]
      ], [1700, 5450, 1450]),
      heading("2.2 非功能需求", HeadingLevel.HEADING_2),
      numbered("准确性：回答必须优先使用已上传资料，不将推测内容伪装成事实。", 1),
      numbered("可解释性：回答中的关键结论应关联原文引用。", 2),
      numbered("响应性：核心页面在桌面和移动端均可正常使用。", 3),
      numbered("可恢复性：上传失败、检索为空、AI 服务失败时有明确状态和恢复路径。", 4),
      numbered("可扩展性：前端、检索、生成、业务服务相互解耦。", 5),
      numbered("可演示性：无外部 API Key 时仍可完成完整演示流程。", 6),
      heading("2.3 用户场景", HeadingLevel.HEADING_2),
      p("场景 A：学生上传数据结构讲义和历年试题，询问“二叉搜索树的查找复杂度”，系统返回 O(h)、平衡树 O(log n) 和退化为 O(n) 的解释，并显示讲义和复习题出处。"),
      p("场景 B：学生将回答保存为知识卡片，然后针对“平衡树与旋转”生成练习题，系统根据答题结果把该知识点标记为薄弱点。"),
      p("场景 C：学生设置考试日期，系统根据剩余天数、已掌握知识点和错题情况生成未来七天的学习安排。"),

      heading("3. 系统架构设计", HeadingLevel.HEADING_1),
      heading("3.1 总体架构", HeadingLevel.HEADING_2),
      p("当前交付版本采用“静态 Web 原型 + 本地演示服务层”的架构，生产环境建议升级为前后端分离架构。"),
      code("Web 前端：课程空间 / 知识库 / AI 问答 / 引用查看 / 练习 / 复习计划\nAPI 服务层：IngestionService / RetrievalService / GenerationService / PracticeService / PlanService\n数据层：关系型数据库 + 向量数据库"),
      heading("3.2 前端设计", HeadingLevel.HEADING_2),
      p("当前原型使用原生 HTML、CSS 和 JavaScript。index.html 负责页面结构，styles.css 负责视觉系统和响应式布局，app.js 负责课程状态、检索模拟、引用交互、练习和计划逻辑。"),
      table(["组件", "职责"], [
        ["CourseSpace", "课程入口和学习概览"],
        ["DocumentUploader", "资料上传、格式校验和解析状态"],
        ["KnowledgeLibrary", "文档、章节和知识点管理"],
        ["ChatWorkspace", "多轮问答和生成状态"],
        ["CitationViewer", "引用来源和原文抽屉"],
        ["KnowledgeCard", "保存重点知识"],
        ["PracticeGenerator", "生成练习题和答题反馈"],
        ["StudyPlanner", "考试日期和复习任务"]
      ], [2300, 6300]),
      heading("3.3 后端服务设计", HeadingLevel.HEADING_2),
      numbered("IngestionService：解析文件、清洗文本、分块、生成向量。", 1),
      numbered("RetrievalService：向量检索、关键词检索、结果重排、引用片段关联。", 2),
      numbered("GenerationService：构造上下文、调用大模型、解析结构化回答。", 3),
      numbered("PracticeService：根据知识点生成题目、批改答案、记录错题。", 4),
      numbered("PlanService：根据考试日期、错题和掌握度生成复习计划。", 5),
      heading("3.4 数据模型", HeadingLevel.HEADING_2),
      table(["实体", "关键字段"], [
        ["Course", "id、name、examDate、progress"],
        ["Document", "id、courseId、fileName、fileType、status"],
        ["Chunk", "id、documentId、content、pageNumber、embedding"],
        ["Conversation", "id、courseId、createdAt"],
        ["Message", "id、role、content、citationIds"],
        ["KnowledgeCard", "id、title、content、sourceChunkId"],
        ["PracticeRecord", "id、knowledgePoint、correct、answeredAt"],
        ["StudyPlan", "id、courseId、date、task、status"]
      ], [2300, 6300]),

      heading("4. AI 技术方案", HeadingLevel.HEADING_1),
      heading("4.1 技术选型及理由", HeadingLevel.HEADING_2),
      p("生成模型：推荐使用支持 OpenAI-compatible 接口的中文友好大模型，例如 Qwen-Plus、GLM-4-Flash 或 GPT-4o-mini。选型理由是中文理解能力强、支持结构化输出、可通过统一接口替换模型，并能根据成本选择不同档位。"),
      p("Embedding 模型：推荐 BGE-M3 或同等中文语义向量模型。选型理由是中文课程文本语义表达能力强、支持较长文本、可覆盖讲义术语和代码注释，并可本地部署。"),
      p("向量数据库：开发和比赛演示使用 Chroma；生产环境使用 PostgreSQL + pgvector，便于与业务数据统一管理。"),
      p("检索策略：采用向量检索 + 关键词检索 + 重排的混合 RAG。向量检索抓语义，关键词检索抓精确术语，重排筛选 top-k 片段。"),
      heading("4.2 当前原型中的 AI 集成方式", HeadingLevel.HEADING_2),
      p("当前版本为了保证无 API Key 时也能演示，使用本地检索器和规则化生成器作为降级方案。系统从问题中提取关键词，对课程资料片段进行相关性评分，返回 top 片段及引用，再根据命中主题生成基于片段的回答。没有命中时明确返回“资料中未找到”，不编造答案。"),
      p("核心逻辑位于 app.js 的 retrieve() 和 answerFor()。生产版只需将 answerFor() 替换为大模型 API 调用，并保留相同的数据结构。"),
      code('{ "answer": "回答文本", "sources": ["source-1", "source-2"], "confidence": 0.91, "knowledgePoints": ["二叉搜索树"] }'),
      heading("4.3 提示词设计", HeadingLevel.HEADING_2),
      numbered("只能使用提供的课程资料回答。", 1),
      numbered("关键结论必须关联来源。", 2),
      numbered("资料不足时明确说明，不推测。", 3),
      numbered("使用学生能理解的中文解释。", 4),
      numbered("输出答案、引用编号和知识点。", 5),
      heading("4.4 优化策略", HeadingLevel.HEADING_2),
      numbered("分块优化：按章节、段落和标题切分，避免把公式和上下文切断。", 1),
      numbered("混合检索：向量检索抓语义，关键词检索抓术语。", 2),
      numbered("重排优化：对候选片段二次评分，提高 top-k 准确率。", 3),
      numbered("引用约束：要求生成模型使用编号，并由后端绑定真实来源。", 4),
      numbered("上下文压缩：只传入相关片段，减少 Token 成本和干扰。", 5),
      numbered("缓存优化：缓存高频问题的回答和 Embedding 结果。", 6),
      numbered("降级策略：外部模型超时或不可用时，切换到本地演示生成器。", 7),
      numbered("评估优化：建立问答准确率、引用命中率和无答案识别率评估集。", 8),

      heading("5. 核心功能实现", HeadingLevel.HEADING_1),
      heading("5.1 课程学习总览", HeadingLevel.HEADING_2),
      p("页面展示课程进度、资料数量、引用数量、知识卡片数量和今日练习。用户可以从总览快速进入问答、知识库和练习模块。"),
      heading("5.2 课程知识库与上传", HeadingLevel.HEADING_2),
      p("支持 PDF、DOCX、TXT、MD 文件。上传前进行扩展名校验，一次可选择多个文件，每个文件独立显示解析状态，解析成功后加入资料列表，并保存在浏览器 localStorage。"),
      heading("5.3 AI 问答与多轮追问", HeadingLevel.HEADING_2),
      p("用户输入问题后，系统插入用户消息，显示检索状态，执行本地检索或调用生产 RAG API，最后显示回答、引用编号和置信状态，并支持保存知识卡片和继续追问。"),
      heading("5.4 引用溯源", HeadingLevel.HEADING_2),
      p("回答中的引用编号可点击，右侧抽屉显示文档名称、章节和页码、原文片段以及该来源与当前回答的关系。生产版可扩展为原文字符偏移量。"),
      heading("5.5 知识卡片", HeadingLevel.HEADING_2),
      p("点击保存为知识卡片后，知识卡片数量更新，保存记录写入 localStorage，后续可扩展为与来源绑定的结构化知识卡片。"),
      heading("5.6 练习与错题", HeadingLevel.HEADING_2),
      p("系统提供选择题、答案反馈和错题列表。当前原型内置树与二叉树主题练习题，生产版可由 PracticeService 根据知识卡片和错题记录动态生成题目。"),
      heading("5.7 复习计划", HeadingLevel.HEADING_2),
      p("用户可以设置考试日期，系统显示剩余天数和学习任务。生产版可根据考试时间、知识点掌握度、错题数量、每日预计学习时间和已完成任务动态排程。"),

      heading("6. 测试与部署", HeadingLevel.HEADING_1),
      heading("6.1 测试策略", HeadingLevel.HEADING_2),
      table(["测试类型", "测试内容"], [
        ["单元测试", "文档解析、分块、检索评分、引用绑定"],
        ["接口测试", "上传、检索、问答、练习、计划接口"],
        ["集成测试", "上传资料后完成问答和引用查看"],
        ["UI 测试", "导航、对话、来源抽屉、练习、上传流程"],
        ["兼容性测试", "桌面端、平板端和移动端"],
        ["AI 评估", "回答准确率、引用命中率、无答案识别率"],
        ["安全测试", "文件类型限制、输入转义、越权访问检查"]
      ], [2300, 6300]),
      heading("6.2 已完成验证", HeadingLevel.HEADING_2),
      numbered("JavaScript 语法检查：node --check app.js。", 1),
      numbered("本地静态资源加载：index.html、styles.css、app.js 均返回 HTTP 200。", 2),
      numbered("Git 差异检查：git diff --check。", 3),
      numbered("核心页面具备响应式布局和键盘焦点样式。", 4),
      heading("6.3 本地运行", HeadingLevel.HEADING_2),
      code("cd C:\\Users\\12638\\Desktop\\web\npython -m http.server 4173\n浏览器访问 http://127.0.0.1:4173/"),
      heading("6.4 生产部署建议", HeadingLevel.HEADING_2),
      p("前端使用 Vercel、Netlify 或 Nginx 静态托管；API 使用 FastAPI + Uvicorn + Docker；数据库使用 PostgreSQL + pgvector；文件存储使用 S3 兼容对象存储；模型调用使用 OpenAI-compatible Gateway；日志与监控关注请求日志、检索命中率、模型延迟和错误率。"),

      heading("7. 创新点说明", HeadingLevel.HEADING_1),
      heading("7.1 技术创新点", HeadingLevel.HEADING_2),
      numbered("证据优先的 RAG 设计：回答、引用、原文定位形成可验证链路，降低大模型幻觉风险。", 1),
      numbered("混合检索策略：向量语义检索与关键词精确检索结合，兼顾概念理解和术语命中。", 2),
      numbered("可降级 AI 架构：外部模型不可用时仍可使用本地演示服务完成核心流程。", 3),
      numbered("回答结构化输出：统一返回答案、来源、知识点和置信状态，便于前后端解耦。", 4),
      numbered("学习数据闭环：问答结果可以转化为知识卡片、练习题和复习任务。", 5),
      heading("7.2 应用创新点", HeadingLevel.HEADING_2),
      numbered("从问答工具升级为学习副驾，覆盖理解、巩固、练习和复习四个阶段。", 1),
      numbered("引用驱动学习，学生不仅得到答案，还能回到课程原文验证答案。", 2),
      numbered("薄弱点导向复习，错题和知识点掌握度直接影响学习计划。", 3),
      numbered("课程知识资产化，讲义、试题和实验资料变成可持续检索的个人知识库。", 4),
      numbered("面向真实学习场景，不做泛化聊天机器人。", 5),

      heading("8. 总结与展望", HeadingLevel.HEADING_1),
      heading("8.1 项目总结", HeadingLevel.HEADING_2),
      p("学涯 Copilot 将课程资料、RAG 问答、原文引用、知识卡片、练习题和复习计划整合为一个完整的学习产品。当前版本已经完成可运行的 Web 原型，具备清晰的信息架构、响应式布局、来源抽屉、资料上传、练习反馈和本地状态持久化。"),
      p("在 AI 方面，项目采用生产级 RAG 目标架构加本地可演示降级方案的策略，既保证比赛现场演示的稳定性，也为接入真实大模型和向量数据库预留了接口。"),
      heading("8.2 后续展望", HeadingLevel.HEADING_2),
      numbered("接入真实 Embedding、向量数据库和大模型 API。", 1),
      numbered("支持 PDF OCR、PPT 图片和多模态课程资料解析。", 2),
      numbered("增加基于错题的自适应学习路径。", 3),
      numbered("支持教师端课程管理、班级知识库和学习报告。", 4),
      numbered("增加引用高亮、原文字符级定位和答案可信度评估。", 5),
      numbered("引入用户账号、云端同步和多设备学习记录。", 6),
      numbered("建立 RAG 评估集，对回答准确率和引用质量持续跟踪。", 7),

      pageBreak(),
      heading("附录：项目文件", HeadingLevel.HEADING_1),
      table(["文件", "说明"], [
        ["index.html", "Web 应用入口和页面结构"],
        ["styles.css", "视觉系统、布局、响应式和动效"],
        ["app.js", "状态管理、检索、问答、练习和计划逻辑"],
        ["docs/superpowers/specs/2026-09-22-xueya-copilot-design.md", "产品设计规格"],
        ["docs/superpowers/plans/2026-09-22-xueya-copilot-plan.md", "实施计划"],
        ["docs/technical-document.md", "技术文档 Markdown 源文件"]
      ], [3900, 4700])
    ]
  }]
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync("docs/xueya-copilot-technical-document.docx", buffer);
  console.log("created docs/xueya-copilot-technical-document.docx");
});