/* The three practice entries have deliberately different content sources. Stitch Screen 2 Enhanced */
(() => {
  const home = () => `
  <section class="practice-hub flex flex-col gap-6 animate-fade-in pb-12" aria-label="计算机练习空间">
    <!-- HERO WORKSPACE BANNER (Stitch Screen 2) -->
    <div class="w-full rounded-2xl bg-surface-container-lowest/85 backdrop-blur-xl p-6 sm:p-8 shadow-sm border border-outline-variant/30 relative overflow-hidden">
      <div class="absolute -right-24 -bottom-24 w-80 h-80 rounded-full bg-gradient-to-tr from-primary/10 via-secondary/5 to-transparent blur-2xl pointer-events-none"></div>
      
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center relative z-10">
        <!-- Left: Vision & Intent -->
        <div class="lg:col-span-7 flex flex-col gap-3">
          <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container text-primary font-label-md text-xs font-semibold w-fit">
            <span class="material-symbols-outlined text-[15px]">bolt</span>
            <span>PRACTICE, WITH PURPOSE</span>
          </div>
          
          <div class="flex flex-col gap-1">
            <h1 class="font-display-lg text-2xl lg:text-3xl text-on-surface tracking-tight font-bold">
              把理解，练成自己的能力。
            </h1>
            <p class="font-body-lg text-sm text-on-surface-variant max-w-xl">
              从经典算法、课程巩固到 408 备考，找到最适合你现在节奏的针对性练习。基于你的薄弱认知图谱，AI 实时生成解题支架。
            </p>
          </div>

          <div class="flex flex-wrap items-center gap-3 pt-2">
            <div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-container-low text-on-surface text-xs border border-outline-variant/20">
              <span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
              <span>今日建议练习量：<strong class="font-code-sm text-primary font-semibold">12 题</strong></span>
            </div>
            <div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-container-low text-on-surface text-xs border border-outline-variant/20">
              <span class="material-symbols-outlined text-[15px] text-tertiary">history</span>
              <span>连续坚持：<strong class="font-code-sm text-tertiary font-semibold">19 天</strong></span>
            </div>
            <div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-container-low text-on-surface text-xs border border-outline-variant/20">
              <span class="material-symbols-outlined text-[15px] text-secondary">verified</span>
              <span>408 知识点覆盖：<strong class="font-code-sm text-secondary font-semibold">68.4%</strong></span>
            </div>
          </div>
        </div>

        <!-- Right: LeetCode Hot 100 Highlight Glass Card -->
        <div class="lg:col-span-5">
          <div class="relative group rounded-xl p-5 bg-gradient-to-br from-surface-container-low/95 via-surface-container-lowest/90 to-surface-container/60 shadow-sm border border-outline-variant/30 backdrop-blur-md transition-all hover:shadow-md">
            <div class="flex items-start justify-between mb-3">
              <div class="flex items-center gap-2.5">
                <div class="w-10 h-10 rounded-lg bg-primary-container text-on-primary flex items-center justify-center shadow-sm">
                  <span class="material-symbols-outlined text-[20px]">terminal</span>
                </div>
                <div>
                  <span class="text-[11px] text-primary font-semibold tracking-wider uppercase">算法专项精炼</span>
                  <h3 class="font-headline-md text-base text-on-surface font-bold">力扣 Hot 100</h3>
                </div>
              </div>
              <span class="px-2.5 py-0.5 rounded-full bg-secondary-fixed text-on-secondary-fixed text-[11px] font-semibold">
                阶段 4 / 17
              </span>
            </div>
            <p class="text-xs text-on-surface-variant mb-3">
              100 道经典算法，沿着 17 个专题一步步练出解题思路。强化双指针、动态规划与图论。
            </p>
            <!-- Progress bar -->
            <div class="flex flex-col gap-1.5 mb-4 bg-surface-container-lowest/80 p-2.5 rounded-lg border border-outline-variant/20">
              <div class="flex justify-between items-center text-xs">
                <span class="text-on-surface-variant">当前：哈希表与滑动窗口</span>
                <span class="font-code-sm text-primary font-bold">28 / 100 题 (28%)</span>
              </div>
              <div class="w-full h-1.5 rounded-full bg-surface-container overflow-hidden">
                <div class="h-full bg-gradient-to-r from-primary to-tertiary rounded-full transition-all" style="width: 28%"></div>
              </div>
            </div>
            <!-- CTA Row -->
            <div class="flex items-center gap-2">
              <a href="#space/practice/hot100" class="flex-1 h-9 px-4 rounded-lg bg-primary text-on-primary font-semibold text-xs flex items-center justify-center gap-2 shadow-sm hover:bg-primary-container active:scale-[0.99] transition-all">
                <span>开始算法练习</span>
                <span class="material-symbols-outlined text-[16px]">arrow_forward</span>
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- CORE EXERCISE MODULES GRID (Stitch Screen 2) -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" id="practicePaths">
      <!-- MODULE 1: 我的小测与作答 -->
      <a class="stitch-card p-6 flex flex-col justify-between group hover:-translate-y-1 transition-all border border-outline-variant/30" href="#space/practice/ai">
        <div>
          <div class="flex items-center justify-between mb-4">
            <div class="w-10 h-10 rounded-xl bg-tertiary-fixed text-tertiary flex items-center justify-center">
              <span class="material-symbols-outlined text-[20px]">assignment</span>
            </div>
            <span class="px-2.5 py-0.5 rounded-full bg-surface-container text-on-surface-variant text-[11px] font-semibold">本人题目与评阅</span>
          </div>
          <span class="text-[11px] font-bold text-tertiary tracking-wider uppercase">QUIZ / 02</span>
          <h2 class="font-headline-md text-base text-on-surface font-bold mt-1 mb-2">我的小测与作答</h2>
          <p class="text-xs text-on-surface-variant leading-relaxed">
            从聊天主动请求小测，或在这里生成个性化练习。保留原答案、AI 评阅、复核与人工修正，题目仅本人可见。
          </p>
        </div>
        <div class="pt-4 mt-4 border-t border-outline-variant/20 flex items-center justify-between text-xs text-tertiary font-semibold">
          <span>打开我的小测</span>
          <span class="material-symbols-outlined text-[16px] group-hover:translate-x-1 transition-transform">arrow_forward</span>
        </div>
      </a>

      <!-- MODULE 2: 408 考研题库 -->
      <a class="stitch-card p-6 flex flex-col justify-between group hover:-translate-y-1 transition-all border border-outline-variant/30" href="#space/practice/exam408">
        <div>
          <div class="flex items-center justify-between mb-4">
            <div class="w-10 h-10 rounded-xl bg-secondary-fixed text-secondary flex items-center justify-center">
              <span class="material-symbols-outlined text-[20px]">school</span>
            </div>
            <span class="px-2.5 py-0.5 rounded-full bg-surface-container text-on-surface-variant text-[11px] font-semibold">240 单选 · 60 综合</span>
          </div>
          <span class="text-[11px] font-bold text-secondary tracking-wider uppercase">POSTGRADUATE / 03</span>
          <h2 class="font-headline-md text-base text-on-surface font-bold mt-1 mb-2">408 考研题库</h2>
          <p class="text-xs text-on-surface-variant leading-relaxed">
            覆盖数据结构、计组、操作系统与网络四科，按知识点分组。151 道历年考点改编与 149 道原创模拟。
          </p>
        </div>
        <div class="pt-4 mt-4 border-t border-outline-variant/20 flex items-center justify-between text-xs text-secondary font-semibold">
          <span>进入 408 练习</span>
          <span class="material-symbols-outlined text-[16px] group-hover:translate-x-1 transition-transform">arrow_forward</span>
        </div>
      </a>

      <!-- MODULE 3: 错题复习与笔记 -->
      <a class="stitch-card p-6 flex flex-col justify-between group hover:-translate-y-1 transition-all border border-outline-variant/30" href="#space/review">
        <div>
          <div class="flex items-center justify-between mb-4">
            <div class="w-10 h-10 rounded-xl bg-error-container/60 text-error flex items-center justify-center">
              <span class="material-symbols-outlined text-[20px]">edit_note</span>
            </div>
            <span class="px-2.5 py-0.5 rounded-full bg-error-container text-error text-[11px] font-semibold">艾宾浩斯复习</span>
          </div>
          <span class="text-[11px] font-bold text-error tracking-wider uppercase">REVIEW / 04</span>
          <h2 class="font-headline-md text-base text-on-surface font-bold mt-1 mb-2">错题复习与笔记</h2>
          <p class="text-xs text-on-surface-variant leading-relaxed">
            错因归因（概念混淆/计算失误/审题遗漏）、正误对比、一键重练与随手记重点，让错过的彻底掌握。
          </p>
        </div>
        <div class="pt-4 mt-4 border-t border-outline-variant/20 flex items-center justify-between text-xs text-error font-semibold">
          <span>前往错题复习</span>
          <span class="material-symbols-outlined text-[16px] group-hover:translate-x-1 transition-transform">arrow_forward</span>
        </div>
      </a>
    </div>

    <footer class="text-xs text-outline text-center py-2">
      固定题库与本人小测分别保存；进度、原答案和评阅来源可核对。
    </footer>
  </section>
  `;

  const materials = () => `
  <section class="practice-materials-page flex flex-col gap-4 max-w-xl mx-auto p-6 bg-surface-container-lowest rounded-2xl shadow-sm border border-outline-variant/30">
    <a href="#space/practice" class="text-xs text-primary font-semibold flex items-center gap-1 hover:underline">
      <span class="material-symbols-outlined text-[16px]">arrow_back</span> 返回练习首页
    </a>
    <div class="flex flex-col gap-2">
      <div class="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
        <span class="material-symbols-outlined text-[20px]">folder</span>
      </div>
      <span class="text-[11px] font-bold text-outline tracking-wider uppercase">COURSE PRACTICE</span>
      <h1 class="text-lg font-bold text-on-surface">资料学习与知识点练习</h1>
      <p class="text-xs text-on-surface-variant">资料可信解析并完成必要确认后自动生成题目，从知识点图谱进入对应练习。</p><a class="button button-blue" href="#space/materials">进入课程资料学习</a>
    </div>
    <div class="flex gap-2 pt-2">
      <a class="px-4 py-2 rounded-xl bg-primary text-on-primary text-xs font-semibold" href="#space/practice/hot100">先练算法 Hot100</a>
      <a class="px-4 py-2 rounded-xl bg-surface-container text-on-surface text-xs font-semibold hover:bg-surface-container-high" href="#space/practice/exam408">或者开始 408 练习 →</a>
    </div>
  </section>
  `;

  window.XueyaPracticeHub = { home, materials };
})();
