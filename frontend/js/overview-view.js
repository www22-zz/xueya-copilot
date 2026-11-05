/* Xueya Copilot - Welcome & Workspace Navigator Overview (Stitch Screen 4) */
(() => {
  'use strict';
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function render(ctx) {
    const { state, store } = ctx;
    const currentCourse = store.courses.find(c => c.id === state.courseId) || { name: '数据结构' };
    const docCount = state.documents?.filter(d => !d.superseded && !d.archived).length || 0;
    const sessionCount = state.sessions?.filter(s => !s.archived).length || 0;

    // Date and Greeting
    const now = new Date();
    const dateStr = now.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });
    const hour = now.getHours();
    const greetingTime = hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好';

    return `
    <div class="stitch-overview-view flex flex-col gap-6 w-full animate-fade-in pb-12">
      <!-- Section 1: Top Welcome & Daily Intent Bar -->
      <section class="w-full">
        <div class="bg-surface-container-lowest/85 backdrop-blur-xl rounded-2xl p-6 sm:p-8 shadow-sm border border-outline-variant/30 flex flex-col xl:flex-row xl:items-center xl:justify-between gap-6 relative overflow-hidden">
          <div class="absolute -right-24 -top-24 w-80 h-80 rounded-full bg-primary/10 blur-3xl pointer-events-none"></div>
          
          <!-- Left Greeting & Metrics -->
          <div class="flex flex-col gap-2 max-w-3xl relative z-10">
            <div class="flex flex-wrap items-center gap-2">
              <span class="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full bg-surface-container text-on-surface-variant text-xs font-medium">
                <span class="w-1.5 h-1.5 rounded-full bg-secondary"></span>
                ${dateStr}
              </span>
              <span class="inline-flex items-center gap-1 px-3 py-0.5 rounded-full bg-primary-fixed text-primary text-xs font-semibold">
                <span class="material-symbols-outlined text-[14px]">timer</span>
                制定我的学习计划
              </span>
              <span class="inline-flex items-center gap-1 px-3 py-0.5 rounded-full bg-surface-container-high text-on-surface text-xs font-medium">
                <span class="material-symbols-outlined text-[14px] text-primary">bolt</span>
                按实际学习记录回顾
              </span>
            </div>
            
            <h1 class="font-display-lg text-2xl sm:text-3xl text-on-surface tracking-tight font-bold mt-1">
              ${greetingTime}，<span class="bg-gradient-to-r from-primary to-tertiary bg-clip-text text-transparent">${escape(window.XueyaAccountId||'同学')}</span>。今天想从哪里开始深潜？
            </h1>
            <p class="font-body-md text-sm text-on-surface-variant">
              结合资料、知识点练习与计划安排学习。当前问答课程：<strong class="text-primary font-semibold">${escape(currentCourse.name)}</strong>（${docCount} 份资料在录）。
            </p>
          </div>

          <!-- Right Breakpoint Resumption Capsule -->
          <div class="flex-shrink-0 flex items-center relative z-10">
            <a class="group w-full xl:w-auto flex items-center justify-between xl:justify-start gap-4 p-4 rounded-xl bg-surface-container-low hover:bg-surface-container transition-all shadow-sm border border-outline-variant/30" href="#space/courses">
              <div class="w-10 h-10 rounded-lg bg-primary-fixed flex items-center justify-center text-primary flex-shrink-0 group-hover:scale-105 transition-transform">
                <span class="material-symbols-outlined text-[20px]">history_toggle_off</span>
              </div>
              <div class="flex flex-col min-w-0 pr-2 text-left">
                <div class="flex items-center gap-1.5">
                  <span class="text-xs text-on-surface-variant">课程与学习记录</span>
                  <span class="font-code-sm text-[11px] text-primary bg-primary-fixed/60 px-1 rounded font-bold">查看</span>
                </div>
                <span class="font-headline-sm text-sm text-on-surface font-semibold truncate max-w-[280px]">
                  打开课程目录与已保存进度
                </span>
              </div>
              <span class="material-symbols-outlined text-primary text-[20px] group-hover:translate-x-1 transition-transform">
                arrow_outward
              </span>
            </a>
          </div>
        </div>
      </section>

      <!-- Section 2: Dual Primary Mode Trackers -->
      <section class="w-full grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Card Left: AI 伴学助手 -->
        <div class="relative bg-surface-container-lowest/85 backdrop-blur-xl rounded-2xl p-6 sm:p-7 shadow-sm border border-outline-variant/30 hover:shadow-md transition-all flex flex-col justify-between group">
          <div class="absolute -top-3 -right-3 w-28 h-28 bg-primary-fixed/20 rounded-full blur-2xl pointer-events-none"></div>
          <div>
            <!-- Top Metadata -->
            <div class="flex items-center justify-between gap-2 mb-3">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-xl bg-primary flex items-center justify-center text-on-primary shadow-sm">
                  <span class="material-symbols-outlined text-[20px]">psychology</span>
                </div>
                <div>
                  <span class="text-[11px] font-bold text-primary tracking-wider uppercase">MODE ALPHA</span>
                  <h2 class="font-headline-lg text-lg text-on-surface font-bold">AI 伴学助手</h2>
                </div>
              </div>
              <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary-fixed text-primary text-xs font-semibold">
                <span class="material-symbols-outlined text-[13px]">neurology</span>
                MiMo 启发式引擎就绪
              </span>
            </div>
            
            <p class="text-sm text-on-surface-variant mb-4">
              碎片化探索 · 遇到不懂随时问 · 资料来源定位与学习记录关联
            </p>

            <!-- Quick Ask Input Box -->
            <div class="bg-surface-container-low rounded-xl p-3.5 mb-4 border border-outline-variant/30">
              <div class="relative flex items-center">
                <span class="material-symbols-outlined text-outline absolute left-3 text-[18px]">search</span>
                <input class="w-full pl-9 pr-20 py-2 bg-surface-container-lowest text-on-surface text-sm rounded-lg outline-none transition-all border border-outline-variant/30 focus:border-primary shadow-sm" id="overviewPromptInput" placeholder="输入讲义疑问、算法代码或考点公式..." type="text"/>
                <button class="absolute right-1.5 px-3 py-1 bg-primary text-on-primary rounded-md flex items-center gap-1 text-xs font-semibold hover:bg-primary-container transition-all active:scale-95 shadow-sm" id="overviewSubmitPromptBtn" type="button">
                  <span>提问</span>
                  <span class="material-symbols-outlined text-[14px]">arrow_forward</span>
                </button>
              </div>

              <!-- Clickable Suggestion Chips -->
              <div class="mt-3 flex flex-col gap-1.5">
                <span class="text-xs text-on-surface-variant flex items-center gap-1">
                  <span class="material-symbols-outlined text-[13px] text-primary">lightbulb</span>
                  快速点火探索节点：
                </span>
                <div class="flex flex-wrap gap-1.5 pt-0.5">
                  <button class="overview-prompt-chip px-2.5 py-1 rounded-full bg-surface-container-lowest hover:bg-primary-fixed hover:text-primary text-on-surface text-xs transition-all border border-outline-variant/20 shadow-sm text-left" type="button" data-prompt="二叉搜索树查找复杂度为什么是 O(log n)？">
                    二叉搜索树查找复杂度为什么是 O(log n)？
                  </button>
                  <button class="overview-prompt-chip px-2.5 py-1 rounded-full bg-surface-container-lowest hover:bg-primary-fixed hover:text-primary text-on-surface text-xs transition-all border border-outline-variant/20 shadow-sm text-left" type="button" data-prompt="解析 AVL 树 LL/RR 旋转平衡机制">
                    解析 AVL 树 LL/RR 旋转平衡机制
                  </button>
                  <button class="overview-prompt-chip px-2.5 py-1 rounded-full bg-surface-container-lowest hover:bg-primary-fixed hover:text-primary text-on-surface text-xs transition-all border border-outline-variant/20 shadow-sm text-left" type="button" data-prompt="操作系统虚拟内存段页式地址转换图解">
                    操作系统虚拟内存段页式地址转换图解
                  </button>
                </div>
              </div>
            </div>

            <!-- Features check list -->
            <div class="flex flex-col gap-1 text-xs text-on-surface-variant mb-4">
              <div class="flex items-center gap-2">
                <span class="material-symbols-outlined text-[15px] text-primary">check_circle</span>
                <span>查看资料来源与对应知识点，便于核对</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="material-symbols-outlined text-[15px] text-primary">check_circle</span>
                <span>支持随笔批注、代码高亮与白板公式推导</span>
              </div>
            </div>
          </div>

          <!-- Mode Entry Button -->
          <a class="w-full py-2.5 px-4 rounded-xl bg-surface-container-high hover:bg-primary-fixed text-primary font-semibold text-sm flex items-center justify-center gap-2 transition-all group-hover:shadow-sm" href="#space/ask">
            <span>进入 AI 助手问答空间</span>
            <span class="material-symbols-outlined text-[18px] transition-transform group-hover:translate-x-1">arrow_forward</span>
          </a>
        </div>

        <!-- Card Right: 学习中心四大核心板块 -->
        <div class="relative bg-surface-container-lowest/85 backdrop-blur-xl rounded-2xl p-6 sm:p-7 shadow-sm border border-outline-variant/30 hover:shadow-md transition-all flex flex-col justify-between group">
          <div class="absolute -top-3 -right-3 w-28 h-28 bg-secondary-fixed/20 rounded-full blur-2xl pointer-events-none"></div>
          <div>
            <!-- Top Metadata -->
            <div class="flex items-center justify-between gap-2 mb-3">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-xl bg-secondary flex items-center justify-center text-on-secondary shadow-sm">
                  <span class="material-symbols-outlined text-[20px]">school</span>
                </div>
                <div>
                  <span class="text-[11px] font-bold text-secondary tracking-wider uppercase">MODE BETA</span>
                  <h2 class="font-headline-lg text-lg text-on-surface font-bold">学习中心核心板块</h2>
                </div>
              </div>
              <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-secondary-fixed text-on-secondary-fixed text-xs font-semibold">
                <span class="material-symbols-outlined text-[13px]">verified</span>
                体系化研习与考点攻坚
              </span>
            </div>

            <p class="text-sm text-on-surface-variant mb-4">
              从视频精讲、专项题库刷题到错题定期归纳与 AI 全域诊断报告
            </p>

            <!-- 4 Module Mini Tiles Grid -->
            <div class="grid grid-cols-2 gap-3 mb-4">
              <!-- Tile 1: 课程学习 -->
              <a href="#space/courses" class="p-3.5 rounded-xl bg-surface-container-low hover:bg-surface-container transition-all border border-outline-variant/30 flex flex-col justify-between group/tile">
                <div class="flex items-center justify-between mb-2">
                  <div class="w-8 h-8 rounded-lg bg-primary-fixed text-primary flex items-center justify-center">
                    <span class="material-symbols-outlined text-[18px]">play_lesson</span>
                  </div>
                  <span class="material-symbols-outlined text-outline text-[16px] group-hover/tile:text-primary transition-colors">arrow_forward</span>
                </div>
                <div class="flex flex-col">
                  <span class="font-semibold text-sm text-on-surface">课程学习中心</span>
                  <span class="text-[11px] text-on-surface-variant">精选视频课 · 实时伴学</span>
                </div>
              </a>

              <!-- Tile 2: 专项练习 -->
              <a href="#space/practice" class="p-3.5 rounded-xl bg-surface-container-low hover:bg-surface-container transition-all border border-outline-variant/30 flex flex-col justify-between group/tile">
                <div class="flex items-center justify-between mb-2">
                  <div class="w-8 h-8 rounded-lg bg-secondary-fixed text-secondary flex items-center justify-center">
                    <span class="material-symbols-outlined text-[18px]">quiz</span>
                  </div>
                  <span class="material-symbols-outlined text-outline text-[16px] group-hover/tile:text-secondary transition-colors">arrow_forward</span>
                </div>
                <div class="flex flex-col">
                  <span class="font-semibold text-sm text-on-surface">专项练习与题库</span>
                  <span class="text-[11px] text-on-surface-variant">Hot100 · 408考研真题</span>
                </div>
              </a>

              <!-- Tile 3: 错题复习 -->
              <a href="#space/review" class="p-3.5 rounded-xl bg-surface-container-low hover:bg-surface-container transition-all border border-outline-variant/30 flex flex-col justify-between group/tile">
                <div class="flex items-center justify-between mb-2">
                  <div class="w-8 h-8 rounded-lg bg-tertiary-fixed text-tertiary flex items-center justify-center">
                    <span class="material-symbols-outlined text-[18px]">edit_note</span>
                  </div>
                  <span class="material-symbols-outlined text-outline text-[16px] group-hover/tile:text-tertiary transition-colors">arrow_forward</span>
                </div>
                <div class="flex flex-col">
                  <span class="font-semibold text-sm text-on-surface">错题复习与笔记</span>
                  <span class="text-[11px] text-on-surface-variant">艾宾浩斯记忆循环 · 错因</span>
                </div>
              </a>

              <!-- Tile 4: 学情分析 -->
              <a href="#space/analysis" class="p-3.5 rounded-xl bg-surface-container-low hover:bg-surface-container transition-all border border-outline-variant/30 flex flex-col justify-between group/tile">
                <div class="flex items-center justify-between mb-2">
                  <div class="w-8 h-8 rounded-lg bg-surface-container-high text-primary flex items-center justify-center">
                    <span class="material-symbols-outlined text-[18px]">insights</span>
                  </div>
                  <span class="material-symbols-outlined text-outline text-[16px] group-hover/tile:text-primary transition-colors">arrow_forward</span>
                </div>
                <div class="flex flex-col">
                  <span class="font-semibold text-sm text-on-surface">AI 学情诊断报告</span>
                  <span class="text-[11px] text-on-surface-variant">断层预警 · 针对性行动</span>
                </div>
              </a>
            </div>
          </div>

          <!-- Bottom CTA -->
          <a class="w-full py-2.5 px-4 rounded-xl bg-surface-container-high hover:bg-secondary-fixed text-secondary font-semibold text-sm flex items-center justify-center gap-2 transition-all group-hover:shadow-sm" href="#space/courses">
            <span>浏览课程学习中心</span>
            <span class="material-symbols-outlined text-[18px] transition-transform group-hover:translate-x-1">arrow_forward</span>
          </a>
        </div>
      </section>

      <!-- Section 3: Recent Activity & Quick Stats Banner -->
      <section class="w-full bg-surface-container-lowest/80 backdrop-blur-md rounded-2xl p-5 border border-outline-variant/30 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined text-[20px]">auto_stories</span>
          </div>
          <div class="flex flex-col">
            <span class="font-semibold text-sm text-on-surface">学涯知识网络连接进度</span>
            <span class="text-xs text-on-surface-variant">已沉淀 ${sessionCount} 个对话会话 · 当前课程已关联 ${docCount} 份资料与章节</span>
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <a href="#space/practice" class="px-3.5 py-1.5 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface text-xs font-semibold transition-all">
            开始今日刷题
          </a>
          <a href="#space/analysis" class="px-3.5 py-1.5 rounded-lg bg-primary text-on-primary hover:bg-primary-container text-xs font-semibold transition-all shadow-sm">
            查看学情分析报告
          </a>
        </div>
      </section>
    </div>
    `;
  }

  function mountListeners(root, { ask, navigate }) {
    if (!root) return;

    // Handle suggestion prompt chips
    root.querySelectorAll('.overview-prompt-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const prompt = btn.getAttribute('data-prompt');
        if (prompt) {
          navigate('#space/ask');
          setTimeout(() => {
            if (typeof ask === 'function') ask(prompt);
          }, 100);
        }
      });
    });

    // Handle overview input submit
    const input = root.querySelector('#overviewPromptInput');
    const submitBtn = root.querySelector('#overviewSubmitPromptBtn');
    function submit() {
      const q = input?.value?.trim();
      if (q) {
        navigate('#space/ask');
        setTimeout(() => {
          if (typeof ask === 'function') ask(q);
        }, 100);
      }
    }
    submitBtn?.addEventListener('click', submit);
    input?.addEventListener('keydown', e => {
      if (e.key === 'Enter') submit();
    });
  }

  window.XueyaOverview = { render, mountListeners };
})();
