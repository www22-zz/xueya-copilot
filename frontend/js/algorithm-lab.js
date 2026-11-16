/* 学涯 · 算法交互实验室（数据驱动 3D 演示渲染器）
 * 数据来源：GET /api/learning/space/algorithm-demo/{id}?sample=N 的 demo-2 schema。
 * 设计原则：
 *  - 只渲染后端提供的确定性教学快照，不执行任何用户代码；
 *  - 按 demo.viz 选择独立渲染器，每个渲染器对 state 字段做自适应提取，缺字段时优雅降级；
 *  - 播放、步进、重置、速度、示例切换与 3D 旋转缩放全部在前端完成。
 */
(function () {
  'use strict';

  /* ================= 常量 ================= */

  const RETURN_LIST = '/#space/practice/hot100';
  const MAX_STEPS = 4000;
  const DEFAULT_SPEED = 800;
  const SPEED_OPTIONS = [[1600, '慢'], [800, '标准'], [350, '快']];
  const POINTER_KEYS = ['left', 'right', 'mid', 'l', 'r', 'i', 'j', 'slow', 'fast', 'start', 'end', 'low', 'high', 'pivot', 'cur', 'current', 'index', 'pos', 'p', 'q', 'k', 'match', 'ptr', 'next', 'prev', 'h'];
  const POINTER_LABELS = { left: 'L', right: 'R', mid: 'M', l: 'L', r: 'R', slow: 'S', fast: 'F', start: 'S', end: 'E', low: 'L', high: 'H', pivot: 'P', cur: 'C', current: 'C', index: 'I', pos: 'P', match: 'M', ptr: 'P', next: 'N', prev: 'P', h: 'H' };
  const VIZ_LABELS = {
    grid: '三维网格', matrix: '矩阵立方体', array: '数组与指针', dp: '动态规划状态表',
    tree: '树结构遍历', 'linked-list': '链表指针', graph: '图与遍历', string: '字符串匹配',
    'stack-queue': '栈 / 队列', backtracking: '回溯搜索', design: '操作流水线', scalar: '状态变量'
  };
  /** 每个可视化类型的默认视角：网格/矩阵保留明显 3D，文本类只做轻微透视保证可读。 */
  const DEFAULT_POSES = {
    grid: { tilt: 58, angle: -28 },
    matrix: { tilt: 55, angle: -25 },
    dp: { tilt: 30, angle: -12 },
    tree: { tilt: 16, angle: -6 },
    'linked-list': { tilt: 22, angle: -10 },
    graph: { tilt: 8, angle: 0 },
    array: { tilt: 26, angle: -12 },
    string: { tilt: 22, angle: -8 },
    'stack-queue': { tilt: 10, angle: -5 },
    backtracking: { tilt: 12, angle: -5 },
    design: { tilt: 7, angle: -4 },
    scalar: { tilt: 10, angle: -4 }
  };

  /* ================= 基础工具 ================= */

  /** HTML 转义，所有来自接口的文本都必须经过它。 */
  function esc(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
      if (ch === '&') return '&amp;';
      if (ch === '<') return '&lt;';
      if (ch === '>') return '&gt;';
      if (ch === '"') return '&quot;';
      return '&#39;';
    });
  }

  function isObj(value) { return !!value && typeof value === 'object' && !Array.isArray(value); }
  function isArr(value) { return Array.isArray(value); }
  function has(value) { return value !== undefined && value !== null; }
  function clampNum(value, min, max) { return Math.min(max, Math.max(min, value)); }

  /** 宽松数字解析：接口里数字可能是 3 或 "3"。 */
  function asNum(value) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) return Number(value);
    return null;
  }

  /** 从对象中按候选键顺序取第一个非空字段。 */
  function pick(source, keys) {
    if (!isObj(source)) return undefined;
    for (let index = 0; index < keys.length; index += 1) {
      const value = source[keys[index]];
      if (value !== undefined && value !== null) return value;
    }
    return undefined;
  }

  function firstValue() {
    for (let index = 0; index < arguments.length; index += 1) {
      if (arguments[index] !== undefined && arguments[index] !== null) return arguments[index];
    }
    return undefined;
  }

  /** 把任意快照值压缩成可读文本，用于变量表 / 卡片；depth 限制嵌套展开层数。 */
  function fmt(value, limit, depth) {
    const cap = typeof limit === 'number' ? limit : 48;
    const level = typeof depth === 'number' ? depth : 0;
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number' || typeof value === 'bigint') return String(value);
    if (typeof value === 'string') return value.length > cap ? value.slice(0, cap) + '…' : value;
    if (isArr(value)) {
      if (value.length === 0) return '[]';
      if (isArr(value[0])) {
        if (level >= 2) return value.length + '×' + (isArr(value[0]) ? value[0].length : 0) + ' 表格';
        const shownRows = value.slice(0, 4).map(function (row) {
          if (!isArr(row)) return fmt(row, 12, level + 1);
          const items = row.slice(0, 4).map(function (item) { return fmt(item, 12, level + 1); });
          return '[' + items.join(', ') + (row.length > 4 ? ', …' : '') + ']';
        });
        return '[' + shownRows.join(', ') + (value.length > 4 ? ', …' : '') + ']';
      }
      const flat = value.every(function (item) { return typeof item === 'number' || typeof item === 'string' || typeof item === 'boolean'; });
      if (flat) {
        const shown = value.slice(0, 8).map(function (item) { return typeof item === 'string' ? JSON.stringify(item) : String(item); });
        return '[' + shown.join(', ') + (value.length > 8 ? ', … 共 ' + value.length + ' 项]' : ']');
      }
      if (level >= 2) return '[' + value.length + ' 项]';
      return '[' + value.slice(0, 4).map(function (item) { return fmt(item, 16, level + 1); }).join(', ') + (value.length > 4 ? ', …' : '') + ']';
    }
    if (isObj(value)) {
      if (typeof value.__type__ === 'string') {
        const items = isArr(value.values) ? value.values : [];
        const shown = items.slice(0, 8).map(function (item) { return fmt(item, 16, level + 1); });
        return value.__type__ + '[' + shown.join(', ') + (items.length > 8 ? ', …' : '') + ']';
      }
      const keys = Object.keys(value);
      if (level >= 3) return '{' + keys.length + ' 个字段}';
      if (keys.length <= 4) {
        const parts = keys.map(function (key) { return key + ': ' + fmt(value[key], 20, level + 1); });
        return '{' + parts.join(', ') + '}';
      }
      return '{' + keys.slice(0, 5).join(', ') + ', …}';
    }
    return String(value);
  }

  /** 创建 DOM 元素。 */
  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clearNode(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  const SVG_NS = 'http://www.w3.org/2000/svg';
  function svgNode(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) { node.setAttribute(key, String(attrs[key])); });
    }
    return node;
  }

  /** 规范化“已访问集合”：支持 [[r,c]]、二维布尔表、对象映射、标量数组。 */
  function markSet(raw) {
    const set = Object.create(null);
    if (raw === undefined || raw === null) return set;
    if (isArr(raw)) {
      raw.forEach(function (item) {
        if (isArr(item) && item.length >= 2) {
          const row = asNum(item[0]);
          const col = asNum(item[1]);
          if (row !== null && col !== null) set[row + ',' + col] = true;
        } else if (isObj(item)) {
          const inner = firstValue(item.id, item.value, item.val, item.index, item.key);
          if (has(inner)) set[String(inner)] = true;
          const row = asNum(firstValue(item.r, item.row));
          const col = asNum(firstValue(item.c, item.col));
          if (row !== null && col !== null) set[row + ',' + col] = true;
        } else if (has(item)) {
          set[String(item)] = true;
        }
      });
    } else if (isObj(raw)) {
      Object.keys(raw).forEach(function (key) { if (raw[key]) set[key] = true; });
    } else {
      set[String(raw)] = true;
    }
    return set;
  }

  /** 节点是否命中标记集合（同时比较 id / 值 / 下标）。 */
  function matchMark(ids, set) {
    if (!ids || !set) return false;
    for (let index = 0; index < ids.length; index += 1) {
      if (set[String(ids[index])]) return true;
    }
    return false;
  }

  function countKeys(map) {
    let total = 0;
    Object.keys(map).forEach(function (key) { if (map[key]) total += 1; });
    return total;
  }

  /** 把坐标值规范成 [row, col]。 */
  function coordOf(value) {
    if (isArr(value) && value.length >= 2) {
      const row = asNum(value[0]);
      const col = asNum(value[1]);
      if (row !== null && col !== null) return [row, col];
    }
    if (isObj(value)) {
      const row = asNum(firstValue(value.r, value.row, value.i));
      const col = asNum(firstValue(value.c, value.col, value.j));
      if (row !== null && col !== null) return [row, col];
    }
    if (typeof value === 'string') {
      const parts = value.split(',');
      if (parts.length === 2) {
        const row = asNum(parts[0]);
        const col = asNum(parts[1]);
        if (row !== null && col !== null) return [row, col];
      }
    }
    return null;
  }

  /** 规范化二维网格：支持数字/字符二维数组，也支持字符串行。 */
  function normalizeGrid(value) {
    if (!isArr(value) || value.length === 0) return null;
    if (value.every(function (row) { return typeof row === 'string'; })) {
      return value.map(function (row) { return row.split(''); });
    }
    if (value.every(function (row) { return isArr(row) && row.length > 0; })) {
      return value.map(function (row) { return row.slice(); });
    }
    return null;
  }

  /** 单元格取值是否为 truthy 的陆地/1。 */
  function isTruthyCell(value) {
    return value === true || value === 1 || value === '1';
  }

  /** 判断是否是 0/1 二值网格（决定用陆地/水域配色）。 */
  function isBinaryGrid(grid) {
    for (let row = 0; row < grid.length; row += 1) {
      for (let col = 0; col < grid[row].length; col += 1) {
        const value = grid[row][col];
        if (!(value === true || value === false || value === 0 || value === 1 || value === '0' || value === '1')) return false;
      }
    }
    return true;
  }

  /* ================= 快照读取 ================= */

  /** 旧版追踪把状态字段直接放在 step 顶层，这里做兼容提取。 */
  function legacyState(step) {
    const state = {};
    Object.keys(step).forEach(function (key) {
      if (key === 'line' || key === 'note' || key === 'highlight' || key === 'state' || key === 'lineNumber') return;
      state[key] = step[key];
    });
    return state;
  }

  /** 合并 demo.inputs 与当前步快照：inputs 提供静态结构，快照覆盖动态状态。 */
  function stateOf(demo, step) {
    const state = {};
    if (isObj(demo.inputs)) {
      Object.keys(demo.inputs).forEach(function (key) { state[key] = demo.inputs[key]; });
    }
    const raw = isObj(step.state) ? step.state : legacyState(step);
    Object.keys(raw).forEach(function (key) { state[key] = raw[key]; });
    return state;
  }

  /** 从数组类字段中提取一维数组。 */
  function pickArray(state, demo, keys) {
    const sources = [state, demo.inputs];
    for (let sourceIndex = 0; sourceIndex < sources.length; sourceIndex += 1) {
      const source = sources[sourceIndex];
      for (let keyIndex = 0; keyIndex < keys.length; keyIndex += 1) {
        const raw = source ? source[keys[keyIndex]] : undefined;
        if (isArr(raw) && raw.every(function (item) { return !isArr(item) && !isObj(item); })) return raw.slice();
      }
    }
    return null;
  }

  /** 指针标签：L / R / M / i / j ... */
  function pointerLabel(key) {
    const name = String(key);
    return POINTER_LABELS[name] || name;
  }

  /** 读取当前数组上的指针（数字下标）。 */
  function pointersOf(state, demo, length) {
    const found = [];
    const seen = Object.create(null);
    const explicit = isObj(state.pointers) ? state.pointers : null;
    const configured = demo.layout && isArr(demo.layout.pointers) ? demo.layout.pointers.map(String) : null;
    const keys = configured && configured.length ? configured : POINTER_KEYS;
    keys.forEach(function (key) {
      const raw = explicit && explicit[key] !== undefined ? explicit[key] : state[key];
      const index = asNum(raw);
      if (index === null) return;
      if (index < 0 || index > length) return;
      const id = String(key);
      if (seen[id]) return;
      seen[id] = true;
      found.push({ key: id, label: pointerLabel(id), index: index });
    });
    return found;
  }

  /** 选择立方体尺寸，避免大网格溢出舞台。 */
  function cubeCellSize(rows, cols, limit) {
    const maxSide = Math.max(rows, cols);
    if (maxSide <= 5) return 64;
    if (maxSide <= 7) return 52;
    if (maxSide <= 10) return 40;
    if (maxSide <= 14) return 32;
    if (maxSide <= 20) return 24;
    return Math.max(14, Math.floor(limit / maxSide));
  }

  /** 共用几何：生成三维立方体网格（grid / matrix 两个渲染器语义各自独立）。 */
  function buildCubeCells(inst, grid, cell, contentFor) {
    const rows = grid.length;
    const cols = grid[0].length;
    const depth = Math.max(12, Math.round(cell * 0.62));
    clearNode(inst.root);
    inst.cells = [];
    inst.rows = rows;
    inst.cols = cols;
    inst.cell = cell;
    inst.depth = depth;
    inst.width = cols * cell;
    inst.height = rows * cell;
    inst.root.style.width = inst.width + 'px';
    inst.root.style.height = inst.height + 'px';
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const cube = make('div', 'cube');
        cube.style.setProperty('--cell', cell + 'px');
        cube.style.setProperty('--depth', depth + 'px');
        cube.style.left = (col * cell) + 'px';
        cube.style.top = (row * cell) + 'px';
        cube.title = '(' + row + ', ' + col + ')';
        const top = make('div', 'top');
        top.textContent = contentFor(row, col);
        cube.appendChild(top);
        cube.appendChild(make('div', 'front'));
        cube.appendChild(make('div', 'side'));
        inst.root.appendChild(cube);
        inst.cells.push({ cube: cube, top: top, row: row, col: col, key: row + ',' + col });
      }
    }
  }

  /** 缺字段时的统一降级：展示当前快照的状态变量卡，避免舞台空白。 */
  function renderStateFallback(inst, state, message) {
    clearNode(inst.root);
    const wrap = make('div', 'fallback-state');
    wrap.appendChild(make('p', 'fallback-note', message));
    const cards = make('div', 'fallback-cards');
    const keys = Object.keys(state).slice(0, 10);
    keys.forEach(function (key) {
      const card = make('div', 'fallback-card');
      card.appendChild(make('span', 'fallback-key', key));
      card.appendChild(valueView(state[key]));
      cards.appendChild(card);
    });
    if (!keys.length) cards.appendChild(make('div', 'fallback-card', '当前步骤没有状态变量'));
    wrap.appendChild(cards);
    inst.root.appendChild(wrap);
    inst.width = 540;
    inst.height = Math.max(220, 100 + Math.ceil(keys.length / 2) * 56);
    inst.root.style.width = inst.width + 'px';
    inst.root.style.height = inst.height + 'px';
    return { fallback: true, caption: message + ' · 已降级为状态变量卡' };
  }

  /* ================= 渲染器 1：grid 三维网格 ================= */

  const vizGrid = {
    id: 'grid',
    label: '三维网格 · DFS / BFS',
    legend: function () {
      return [
        { tone: 'current', label: '当前格' },
        { tone: 'visited', label: '已访问' },
        { tone: 'accent', label: '陆地 / 元素' },
        { tone: 'dim', label: '水域 / 空' }
      ];
    },
    build: function () {
      return { root: make('div', 'grid-scene'), cells: null, rows: 0, cols: 0, cell: 56, grid: null, width: 320, height: 256 };
    },
    render: function (inst, demo, step, state) {
      const grid = normalizeGrid(firstValue(pick(state, ['grid', 'matrix', 'board', 'cells', 'maze']), pick(demo.inputs, ['grid', 'matrix', 'board']), inst.grid));
      if (!grid) {
        return renderStateFallback(inst, state, '当前快照缺少二维网格（state.grid）');
      }
      const cell = cubeCellSize(grid.length, grid[0].length, 600);
      const signature = grid.length + 'x' + grid[0].length + '@' + cell;
      if (signature !== inst.signature) {
        buildCubeCells(inst, grid, cell, function (row, col) {
          const value = grid[row][col];
          if (isBinaryGrid(grid)) return isTruthyCell(value) ? '1' : '';
          return fmt(value, 3);
        });
        inst.signature = signature;
        inst.baseGrid = grid.map(function (row) { return row.slice(); });
        inst.lastGrid = grid.map(function (row) { return row.slice(); });
      }
      inst.grid = grid;
      const binary = isBinaryGrid(grid);
      const visited = markSet(pick(state, ['visited', 'seen', 'explored', 'marked', 'closed']));
      let current = coordOf(pick(state, ['current', 'cur', 'cell', 'pos', 'position', 'node']));
      if (!current) {
        // 官方参考解常在 dfs(i, j) 内层帧留下 i/j，可视为当前格。
        const row = asNum(firstValue(state.i, state.r));
        const col = asNum(firstValue(state.j, state.c));
        if (row !== null && col !== null) current = [row, col];
      }
      let flooded = 0;
      const baseGrid = inst.baseGrid || grid;
      const lastGrid = inst.lastGrid || grid;
      const numericStates = !binary && grid.every(function (row) {
        return row.every(function (value) {
          const numeric = asNum(value);
          return numeric !== null && numeric >= 0 && numeric <= 9 && Math.round(numeric) === numeric;
        });
      });
      inst.cells.forEach(function (cellInfo) {
        const value = grid[cellInfo.row][cellInfo.col];
        const baseValue = baseGrid[cellInfo.row] ? baseGrid[cellInfo.row][cellInfo.col] : value;
        const classes = ['cube'];
        if (binary) {
          if (isTruthyCell(value)) classes.push('land');
          else if (isTruthyCell(baseValue) && !isTruthyCell(value)) { classes.push('visited'); flooded += 1; }
          else classes.push('water');
        } else if (numericStates) {
          // 多态网格按数值着色：0 空、1 待处理、2 已处理，其余值依次用状态色。
          const numeric = asNum(value);
          classes.push(numeric === 0 ? 'water' : 'value-' + String(numeric));
        } else {
          classes.push('neutral');
        }
        if (visited[cellInfo.key]) classes.push('visited');
        if (current && current[0] === cellInfo.row && current[1] === cellInfo.col) classes.push('current');
        const lastValue = lastGrid[cellInfo.row] ? lastGrid[cellInfo.row][cellInfo.col] : value;
        if (binary && String(lastValue) !== String(value)) classes.push('changed');
        cellInfo.cube.className = classes.join(' ');
        if (!binary) cellInfo.top.textContent = fmt(value, 3);
      });
      inst.lastGrid = grid.map(function (row) { return row.slice(); });
      const parts = ['网格 ' + grid.length + '×' + grid[0].length];
      const count = pick(state, ['count', 'islands', 'answer', 'total', 'result']);
      if (count !== undefined) parts.push('计数 ' + fmt(count, 16));
      if (current) parts.push('当前 (' + current[0] + ', ' + current[1] + ')');
      if (flooded > 0) parts.push('已处理 ' + flooded + ' 格');
      if (countKeys(visited) > 0) parts.push('已访问 ' + countKeys(visited));
      const stack = pick(state, ['stack', 'dfsStack']);
      if (isArr(stack)) parts.push('递归栈 ' + stack.length + ' 层');
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 2：matrix 矩阵立方体 ================= */

  const vizMatrix = {
    id: 'matrix',
    label: '矩阵 · 立方体阵列',
    legend: function () {
      return [
        { tone: 'current', label: '当前元素' },
        { tone: 'visited', label: '已处理' },
        { tone: 'accent', label: '矩阵值' },
        { tone: 'pointer', label: '行列高亮' }
      ];
    },
    build: function () {
      return { root: make('div', 'matrix-scene'), cells: null, rows: 0, cols: 0, cell: 56, signature: '', width: 320, height: 256 };
    },
    render: function (inst, demo, step, state) {
      const grid = normalizeGrid(firstValue(pick(state, ['matrix', 'grid', 'board', 'table', 'cells']), pick(demo.inputs, ['matrix', 'grid', 'board']), inst.grid));
      if (!grid) {
        return renderStateFallback(inst, state, '当前快照缺少矩阵（state.matrix / state.grid）');
      }
      const cell = cubeCellSize(grid.length, grid[0].length, 600);
      const signature = grid.length + 'x' + grid[0].length + '@' + cell;
      if (signature !== inst.signature) {
        buildCubeCells(inst, grid, cell, function (row, col) { return fmt(grid[row][col], 4); });
        inst.cells.forEach(function (cellInfo) {
          cellInfo.cube.classList.add('matrix-cube');
        });
        inst.signature = signature;
      }
      inst.grid = grid;
      const visited = markSet(pick(state, ['visited', 'seen', 'visitedCells', 'done']));
      let current = coordOf(pick(state, ['current', 'cur', 'cell', 'pos']));
      const rowIndex = asNum(firstValue(state.i, state.row, state.r));
      const colIndex = asNum(firstValue(state.j, state.col, state.c));
      if (!current && rowIndex !== null && colIndex !== null) current = [rowIndex, colIndex];
      const focusRow = asNum(firstValue(state.row, state.r, rowIndex));
      const focusCol = asNum(firstValue(state.col, state.c, colIndex));
      inst.cells.forEach(function (cellInfo) {
        const classes = ['cube', 'matrix-cube'];
        const key = cellInfo.key;
        if (visited[key]) classes.push('visited');
        if (focusRow !== null && cellInfo.row === focusRow) classes.push('focus-line');
        if (focusCol !== null && cellInfo.col === focusCol) classes.push('focus-line');
        if (current && current[0] === cellInfo.row && current[1] === cellInfo.col) classes.push('current');
        cellInfo.cube.className = classes.join(' ');
        cellInfo.top.textContent = fmt(grid[cellInfo.row][cellInfo.col], 4);
      });
      const parts = ['矩阵 ' + grid.length + '×' + grid[0].length];
      if (current) parts.push('当前 [' + current[0] + '][' + current[1] + '] = ' + fmt(grid[current[0]] ? grid[current[0]][current[1]] : ''));
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 3：array 数组与指针 ================= */

  /** 常见数组入参名；找不到时再按 demo.inputs 的形状扫描。 */
  const ARRAY_KEYS = ['nums', 'arr', 'array', 'values', 'vals', 'height', 'prices', 'temperatures', 'a', 'numbers', 'items', 'seq', 'coins', 'weights', 'ratings'];

  function firstArrayValue(source) {
    if (!isObj(source)) return null;
    const keys = Object.keys(source);
    for (let index = 0; index < keys.length; index += 1) {
      const value = source[keys[index]];
      if (isArr(value) && value.length > 0 && value.every(function (item) { return !isArr(item) && !isObj(item); })) return value.slice();
    }
    return null;
  }

  function scanStateArray(state) {
    const skip = { stack: 1, queue: 1, res: 1, ans: 1, results: 1, path: 1, track: 1, visited: 1, seen: 1, order: 1, dp: 1, table: 1, grid: 1, matrix: 1, board: 1, output: 1, mapping: 1, directions: 1, indegree: 1 };
    const keys = Object.keys(state);
    for (let index = keys.length - 1; index >= 0; index -= 1) {
      const key = keys[index];
      if (skip[key]) continue;
      const value = state[key];
      if (isArr(value) && value.length > 0 && value.length <= 80 && value.every(function (item) { return !isArr(item) && !isObj(item); })) return value.slice();
    }
    return null;
  }

  function extractArrayValues(state, demo, fallback) {
    const explicit = pickArray(state, demo, ARRAY_KEYS);
    if (explicit && explicit.length) return explicit;
    const fromInputs = firstArrayValue(demo.inputs);
    if (fromInputs) return fromInputs;
    const fromState = scanStateArray(state);
    if (fromState) return fromState;
    return fallback || null;
  }

  function appendPointerChip(container, pointer) {
    if (!container) return;
    const chip = make('span', 'array-pointer', pointer.label);
    chip.title = '指针 ' + pointer.key + ' = ' + pointer.index;
    container.appendChild(chip);
  }

  function buildArrayCells(inst, values, cell) {
    clearNode(inst.root);
    inst.cells = [];
    inst.endpoint = null;
    inst.cell = cell;
    const width = values.length * (cell + 12) + 12 + (values.length <= 30 ? cell + 12 : 0) + 48;
    inst.width = width;
    inst.height = cell + 150;
    inst.root.style.width = inst.width + 'px';
    inst.root.style.height = inst.height + 'px';
    values.forEach(function (value, index) {
      const item = make('div', 'array-cell');
      item.style.width = cell + 'px';
      const pointers = make('div', 'array-pointers');
      const strong = make('strong', 'array-value', fmt(value, 8));
      const caption = make('span', 'array-index', index);
      item.appendChild(pointers);
      item.appendChild(strong);
      item.appendChild(caption);
      item.title = '下标 ' + index + ' = ' + fmt(value, 40);
      inst.root.appendChild(item);
      inst.cells.push({ cell: item, pointers: pointers, value: strong, index: index });
    });
    if (values.length > 0 && values.length <= 30) {
      const endpoint = make('div', 'array-cell endpoint');
      endpoint.style.width = cell + 'px';
      const pointers = make('div', 'array-pointers');
      endpoint.appendChild(pointers);
      endpoint.appendChild(make('strong', 'array-value', '∅'));
      endpoint.appendChild(make('span', 'array-index', values.length));
      endpoint.title = '数组边界（越界位置）';
      inst.root.appendChild(endpoint);
      inst.endpoint = { cell: endpoint, pointers: pointers };
    }
  }

  const vizArray = {
    id: 'array',
    label: '数组与指针',
    legend: function () {
      return [
        { tone: 'current', label: '当前 / 中点' },
        { tone: 'pointer', label: '指针 left / right / i / j' },
        { tone: 'accent', label: '数组元素' },
        { tone: 'dim', label: '数组边界' }
      ];
    },
    build: function () {
      return { root: make('div', 'array-scene'), cells: [], endpoint: null, values: null, signature: '', cell: 64, width: 320, height: 214 };
    },
    render: function (inst, demo, step, state) {
      const values = extractArrayValues(state, demo, inst.values);
      if (!values) {
        return renderStateFallback(inst, state, '当前快照缺少一维数组（state.nums / 入参数组）');
      }
      const count = values.length;
      const cell = count > 24 ? 34 : count > 16 ? 42 : count > 10 ? 52 : 64;
      const signature = JSON.stringify(values);
      if (signature !== inst.signature || cell !== inst.cell) {
        buildArrayCells(inst, values, cell);
        inst.signature = signature;
      }
      inst.values = values;
      const pointers = pointersOf(state, demo, count);
      inst.cells.forEach(function (item) { clearNode(item.pointers); item.cell.classList.remove('current'); });
      if (inst.endpoint) clearNode(inst.endpoint.pointers);
      let currentIndex = asNum(firstValue(state.mid, state.current, state.cur, state.index, state.pos, state.i));
      if (currentIndex !== null && (currentIndex < 0 || currentIndex >= count)) currentIndex = null;
      pointers.forEach(function (pointer) {
        if (pointer.index === count) {
          if (inst.endpoint) appendPointerChip(inst.endpoint.pointers, pointer);
          return;
        }
        if (inst.cells[pointer.index]) appendPointerChip(inst.cells[pointer.index].pointers, pointer);
      });
      inst.cells.forEach(function (item) {
        item.cell.classList.toggle('current', currentIndex !== null && currentIndex === item.index);
      });
      const parts = ['数组长度 ' + count];
      if (has(state.target)) parts.push('target = ' + fmt(state.target, 20));
      if (pointers.length) {
        parts.push(pointers.map(function (pointer) { return pointer.label + '=' + pointer.index; }).join(' '));
      }
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 4：dp 动态规划状态表 ================= */

  const DP_KEYS = ['dp', 'table', 'f', 'g', 'memo', 'cache', 'ways', 'states', 'lengths', 'counts'];

  function normalizeTable(raw) {
    if (!isArr(raw) || raw.length === 0) return null;
    if (isArr(raw[0])) {
      let cols = 0;
      raw.forEach(function (row) { if (isArr(row) && row.length > cols) cols = row.length; });
      if (cols === 0) return null;
      return raw.map(function (row) {
        const copy = isArr(row) ? row.slice() : [];
        while (copy.length < cols) copy.push(undefined);
        return copy;
      });
    }
    if (raw.every(function (item) { return typeof item === 'string' && item.length > 1; })) {
      return raw.map(function (row) { return row.split(''); });
    }
    if (raw.every(function (item) { return !isArr(item) && !isObj(item); })) return [raw.slice()];
    return null;
  }

  function extractDpTable(state, demo, fallback) {
    for (let index = 0; index < DP_KEYS.length; index += 1) {
      const key = DP_KEYS[index];
      const raw = firstValue(state[key], demo.inputs ? demo.inputs[key] : undefined);
      if (raw !== undefined) {
        const table = normalizeTable(raw);
        if (table) return table;
      }
    }
    const inputKeys = isObj(demo.inputs) ? Object.keys(demo.inputs) : [];
    const stateKeys = Object.keys(state).slice().reverse();
    for (let index = 0; index < stateKeys.length; index += 1) {
      const key = stateKeys[index];
      if (inputKeys.indexOf(key) >= 0) continue;
      const table = normalizeTable(state[key]);
      if (table && table.length >= 1) return table;
    }
    for (let index = 0; index < inputKeys.length; index += 1) {
      const table = normalizeTable(demo.inputs[inputKeys[index]]);
      if (table) return table;
    }
    if (fallback) return fallback;
    return null;
  }

  function dpCellSize(rows, cols) {
    const maxSide = Math.max(rows, cols);
    if (maxSide <= 6) return 50;
    if (maxSide <= 8) return 44;
    if (maxSide <= 10) return 38;
    if (maxSide <= 14) return 32;
    if (maxSide <= 18) return 27;
    if (maxSide <= 24) return 22;
    return Math.max(14, Math.floor(520 / maxSide));
  }

  function buildDpTable(inst, table, cell) {
    const rows = table.length;
    const cols = table[0].length;
    clearNode(inst.root);
    inst.cells = [];
    inst.rows = rows;
    inst.cols = cols;
    inst.cell = cell;
    const gap = cell >= 30 ? 6 : 4;
    const grid = make('div', 'dp-table');
    grid.style.gridTemplateColumns = 'repeat(' + cols + ', ' + cell + 'px)';
    grid.style.gap = gap + 'px';
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const cellEl = make('div', 'dp-cell');
        grid.appendChild(cellEl);
        inst.cells.push({ el: cellEl, row: row, col: col });
      }
    }
    inst.root.appendChild(grid);
    inst.width = cols * (cell + gap) - gap + 40;
    inst.height = rows * (cell + gap) - gap + 40;
    inst.root.style.width = inst.width + 'px';
    inst.root.style.height = inst.height + 'px';
  }

  const vizDp = {
    id: 'dp',
    label: '动态规划状态表',
    legend: function () {
      return [
        { tone: 'current', label: '当前状态' },
        { tone: 'accent', label: '已填充（值越大越亮）' },
        { tone: 'pointer', label: '行列关联' },
        { tone: 'dim', label: '未填充' }
      ];
    },
    build: function () {
      return { root: make('div', 'dp-scene'), cells: [], rows: 0, cols: 0, cell: 44, signature: '', width: 360, height: 240, prevValues: null };
    },
    render: function (inst, demo, step, state) {
      const table = extractDpTable(state, demo, inst.table);
      if (!table) {
        return renderStateFallback(inst, state, '当前快照缺少 DP 表（该步可能尚未初始化状态数组）');
      }
      const cell = dpCellSize(table.length, table[0].length);
      const signature = table.length + 'x' + table[0].length + '@' + cell;
      if (signature !== inst.signature) {
        buildDpTable(inst, table, cell);
        inst.signature = signature;
        inst.prevValues = null;
      }
      inst.table = table;
      let rowIndex = asNum(firstValue(state.i, state.row, state.r));
      let colIndex = asNum(firstValue(state.j, state.col, state.c));
      const current = coordOf(pick(state, ['current', 'cell', 'pos']));
      if (current) { rowIndex = current[0]; colIndex = current[1]; }
      let currentRow = null;
      let currentCol = null;
      if (table.length === 1) {
        // 一维滚动 DP（如 LCS 的空间优化版）：j（或 i）是当前列下标。
        const index1d = colIndex !== null ? colIndex : rowIndex;
        if (index1d !== null && index1d >= 0 && index1d < table[0].length) { currentRow = 0; currentCol = index1d; }
      } else if (rowIndex !== null && colIndex !== null && rowIndex >= 0 && rowIndex < table.length && colIndex >= 0 && colIndex < table[0].length) {
        currentRow = rowIndex;
        currentCol = colIndex;
      }
      let maxValue = 0;
      table.forEach(function (row) {
        row.forEach(function (value) {
          const numeric = asNum(value);
          if (numeric !== null && Math.abs(numeric) > maxValue) maxValue = Math.abs(numeric);
        });
      });
      inst.cells.forEach(function (cellInfo) {
        const value = table[cellInfo.row] ? table[cellInfo.row][cellInfo.col] : undefined;
        const empty = value === undefined || value === null || value === '' || value === '.';
        const numeric = asNum(value);
        const previousValue = inst.prevValues && inst.prevValues[cellInfo.row] ? inst.prevValues[cellInfo.row][cellInfo.col] : value;
        const classes = ['dp-cell'];
        if (empty) classes.push('empty');
        else classes.push('filled');
        if (currentRow !== null && cellInfo.row === currentRow && cellInfo.col === currentCol) classes.push('current');
        else if (table.length > 1 && ((rowIndex !== null && cellInfo.row === rowIndex) || (colIndex !== null && cellInfo.col === colIndex))) classes.push('related');
        if (!empty && String(previousValue) !== String(value)) classes.push('changed');
        cellInfo.el.className = classes.join(' ');
        cellInfo.el.textContent = empty ? '' : fmt(value, 6);
        if (!empty && numeric !== null) {
          const level = maxValue > 0 ? clampNum(Math.abs(numeric) / maxValue, 0, 1) : 0;
          const hue = Math.round(205 - 45 * level);
          const light = Math.round(24 + 20 * level);
          cellInfo.el.style.backgroundColor = 'hsl(' + hue + ' 42% ' + light + '%)';
        } else {
          cellInfo.el.style.backgroundColor = '';
        }
      });
      inst.prevValues = table.map(function (row) { return row.slice(); });
      const parts = ['状态表 ' + table.length + '×' + table[0].length];
      if (currentRow !== null && currentCol !== null) {
        const value = table[currentRow] ? table[currentRow][currentCol] : undefined;
        if (table.length === 1) parts.push('dp[' + currentCol + '] = ' + fmt(value, 12));
        else parts.push('dp[' + currentRow + '][' + currentCol + '] = ' + fmt(value, 12));
      }
      const result = pick(state, ['result', 'answer']);
      if (result !== undefined) parts.push('结果 ' + fmt(result, 20));
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 5：tree 树结构 ================= */

  /** 后端把结构对象包装成 {__type__: 'TreeNode', values: [层序含 null]}。 */
  function wrapperOf(value) {
    if (!isObj(value) || typeof value.__type__ !== 'string') return null;
    return { type: value.__type__, values: isArr(value.values) ? value.values : [], cycle: value.cycle === true };
  }

  function treeFromLevelOrder(values) {
    const slots = [];
    values.forEach(function (value, index) {
      if (value === null || value === undefined) { slots.push(null); return; }
      slots.push({ id: 't' + index, val: value, ids: ['t' + index, String(index), String(value)], children: [] });
    });
    const nodes = slots.filter(function (node) { return !!node; });
    for (let index = 0; index < slots.length; index += 1) {
      const node = slots[index];
      if (!node) continue;
      const left = slots[index * 2 + 1];
      const right = slots[index * 2 + 2];
      if (left) node.children.push(left);
      if (right) node.children.push(right);
    }
    if (!nodes.length) return null;
    return { nodes: nodes, root: slots[0] || nodes[0] };
  }

  function flattenTreeRoot(rootValue) {
    const nodes = [];
    let counter = 0;
    function walk(value) {
      if (value === null || value === undefined) return null;
      const info = wrapperOf(value);
      if (info && String(info.type).indexOf('TreeNode') >= 0) return treeFromLevelOrder(info.values).root;
      if (!isObj(value)) {
        const leaf = { id: 'n' + counter, val: value, ids: ['n' + counter, String(counter), String(value)], children: [] };
        counter += 1;
        nodes.push(leaf);
        return leaf;
      }
      const label = firstValue(value.val, value.value, value.label, value.data, '');
      const node = { id: 'n' + counter, val: label, ids: ['n' + counter, String(counter), String(label)], children: [] };
      counter += 1;
      nodes.push(node);
      [value.left, value.right].forEach(function (child) {
        if (child === null || child === undefined) return;
        const built = walk(child);
        if (built) node.children.push(built);
      });
      return node;
    }
    const root = walk(rootValue);
    return root ? { nodes: nodes, root: root } : null;
  }

  function treeFromFlat(rawNodes, rawEdges) {
    const nodes = [];
    const byId = Object.create(null);
    rawNodes.forEach(function (raw, index) {
      let value = raw;
      const ids = [];
      if (isObj(raw)) {
        value = firstValue(raw.val, raw.value, raw.label, raw.data, '');
        ids.push(raw.id, raw.key, raw.index, index);
      } else {
        ids.push(index);
      }
      const node = { id: 'f' + index, val: value, ids: ['f' + index, String(index), String(value)], children: [] };
      ids.forEach(function (id) { if (has(id)) { node.ids.push(String(id)); byId[String(id)] = node; } });
      nodes.push(node);
    });
    function resolve(value) {
      if (!has(value) || isObj(value)) return null;
      return byId[String(value)] || null;
    }
    rawEdges.forEach(function (edge) {
      let from;
      let to;
      if (isArr(edge) && edge.length >= 2) { from = edge[0]; to = edge[1]; }
      else if (isObj(edge)) { from = firstValue(edge.parent, edge.from, edge.source, edge.a); to = firstValue(edge.child, edge.to, edge.target, edge.b); }
      const parent = resolve(from);
      const child = resolve(to);
      if (parent && child) parent.children.push(child);
    });
    if (!rawEdges.length) {
      rawNodes.forEach(function (raw, index) {
        if (!isObj(raw)) return;
        [raw.left, raw.right].forEach(function (child) {
          const target = resolve(child);
          if (target) nodes[index].children.push(target);
        });
      });
    }
    const childIds = Object.create(null);
    nodes.forEach(function (node) { node.children.forEach(function (child) { childIds[child.id] = true; }); });
    const root = nodes.filter(function (node) { return !childIds[node.id]; })[0] || nodes[0];
    return root ? { nodes: nodes, root: root } : null;
  }

  function treeFromAny(value) {
    if (!has(value)) return null;
    const info = wrapperOf(value);
    if (info && String(info.type).indexOf('TreeNode') >= 0 && info.values.length) return treeFromLevelOrder(info.values);
    if (isObj(value) && (value.left !== undefined || value.right !== undefined || value.val !== undefined || value.value !== undefined)) return flattenTreeRoot(value);
    return null;
  }

  /** 层序数组（含 null 占位）可直接还原成二叉树；inputs.root 常用这种形式。 */
  function treeFromLevelArray(value) {
    if (!isArr(value) || !value.length) return null;
    if (!value.some(function (item) { return item === null || item === undefined; })) return null;
    return treeFromLevelOrder(value);
  }

  function extractTree(state, demo) {
    const inputRoot = pick(demo.inputs, ['root', 'tree', 'bst']);
    if (isArr(inputRoot)) {
      const level = treeFromLevelOrder(inputRoot);
      if (level) return level;
    }
    const fromInputObject = treeFromAny(inputRoot);
    if (fromInputObject) return fromInputObject;
    if (isObj(demo.inputs)) {
      const inputKeys = Object.keys(demo.inputs);
      for (let index = 0; index < inputKeys.length; index += 1) {
        const value = demo.inputs[inputKeys[index]];
        const found = treeFromAny(value) || (inputKeys[index] === 'root' ? treeFromLevelArray(value) : null);
        if (found) return found;
      }
    }
    const rawNodes = pick(demo.inputs, ['nodes', 'vertices', 'nodeList']);
    const rawEdges = pick(demo.inputs, ['edges', 'links']);
    if (isArr(rawNodes) && rawNodes.length) {
      const flat = treeFromFlat(rawNodes, isArr(rawEdges) ? rawEdges : []);
      if (flat) return flat;
    }
    // state.root 常是递归函数的当前子树参数；仅在没有完整输入树时作为树源。
    const fromState = treeFromAny(pick(state, ['root', 'tree', 'bst']));
    if (fromState) return fromState;
    if (isObj(state)) {
      const stateKeys = Object.keys(state);
      for (let index = 0; index < stateKeys.length; index += 1) {
        const found = treeFromAny(state[stateKeys[index]]);
        if (found) return found;
      }
    }
    return null;
  }

  function computeTreeLayout(tree) {
    const positions = Object.create(null);
    const seen = Object.create(null);
    let order = 0;
    let maxDepth = 0;
    function walk(node, depth) {
      if (!node || seen[node.id]) return null;
      seen[node.id] = true;
      if (depth > maxDepth) maxDepth = depth;
      const xs = [];
      node.children.forEach(function (child) {
        const value = walk(child, depth + 1);
        if (value !== null) xs.push(value);
      });
      let x;
      if (!xs.length) { x = order; order += 1; }
      else { x = (Math.min.apply(null, xs) + Math.max.apply(null, xs)) / 2; }
      positions[node.id] = { x: x, y: depth };
      return x;
    }
    walk(tree.root, 0);
    tree.nodes.forEach(function (node) {
      if (!positions[node.id]) { positions[node.id] = { x: order, y: maxDepth + 1 }; order += 1; }
    });
    const gapX = 96;
    const gapY = 88;
    const width = Math.max(380, order * gapX + 60);
    const height = Math.max(240, (maxDepth + 3) * gapY);
    const placed = Object.create(null);
    Object.keys(positions).forEach(function (id) {
      placed[id] = { x: 50 + positions[id].x * gapX, y: 50 + positions[id].y * gapY, depth: positions[id].y };
    });
    return { positions: placed, width: width, height: height, maxDepth: maxDepth };
  }

  function buildTreeScene(inst, tree) {
    const layout = computeTreeLayout(tree);
    clearNode(inst.root);
    const edges = svgNode('svg', { class: 'tree-edges', width: layout.width, height: layout.height });
    const nodeEls = Object.create(null);
    const edgeEls = [];
    tree.nodes.forEach(function (node) {
      const from = layout.positions[node.id];
      node.children.forEach(function (child) {
        const to = layout.positions[child.id];
        const line = svgNode('line', { x1: from.x, y1: from.y, x2: to.x, y2: to.y, class: 'tree-edge' });
        edges.appendChild(line);
        edgeEls.push({ line: line, parent: node.id, child: child.id });
      });
    });
    inst.root.appendChild(edges);
    tree.nodes.forEach(function (node) {
      const pos = layout.positions[node.id];
      const el = make('div', 'tree-node');
      el.style.left = pos.x + 'px';
      el.style.top = pos.y + 'px';
      el.style.setProperty('--tz', ((pos.depth || 0) * 18) + 'px');
      el.appendChild(make('span', 'tree-node-value', fmt(node.val, 10)));
      el.title = '节点 ' + fmt(node.val, 40);
      inst.root.appendChild(el);
      nodeEls[node.id] = el;
    });
    inst.root.style.width = layout.width + 'px';
    inst.root.style.height = layout.height + 'px';
    inst.width = layout.width;
    inst.height = layout.height;
    inst.tree = tree;
    inst.nodeEls = nodeEls;
    inst.edgeEls = edgeEls;
  }

  function nodeInSet(node, set) {
    if (!set) return false;
    for (let index = 0; index < node.ids.length; index += 1) {
      if (set[node.ids[index]]) return true;
    }
    return false;
  }

  function nodeMatches(node, raw) {
    if (raw === undefined || raw === null) return false;
    if (isObj(raw)) {
      const value = firstValue(raw.val, raw.value, raw.label, raw.data);
      if (has(value) && String(value) === String(node.val)) return true;
      const info = wrapperOf(raw);
      if (info && info.values.length && String(info.values[0]) === String(node.val)) return true;
      const id = firstValue(raw.id, raw.key, raw.index);
      return has(id) ? node.ids.indexOf(String(id)) >= 0 : false;
    }
    const text = String(raw);
    return node.ids.indexOf(text) >= 0 || String(node.val) === text;
  }

  const vizTree = {
    id: 'tree',
    label: '树结构遍历',
    legend: function () {
      return [
        { tone: 'current', label: '当前节点' },
        { tone: 'visited', label: '已访问' },
        { tone: 'pointer', label: '关联节点（p / q / node）' },
        { tone: 'dim', label: '未访问' }
      ];
    },
    build: function () {
      return { root: make('div', 'tree-scene'), tree: null, nodeEls: null, edgeEls: null, signature: '', width: 520, height: 360 };
    },
    render: function (inst, demo, step, state) {
      const tree = extractTree(state, demo);
      if (!tree) {
        return renderStateFallback(inst, state, '当前快照缺少树节点（TreeNode 包装或层序数组）');
      }
      const signature = tree.nodes.map(function (node) { return node.id + ':' + node.val + '>' + node.children.map(function (child) { return child.id; }).join('.'); }).join('|');
      if (signature !== inst.signature) {
        buildTreeScene(inst, tree);
        inst.signature = signature;
      }
      const visited = markSet(pick(state, ['visited', 'seen', 'explored']));
      const pathSet = markSet(pick(state, ['path', 'route', 'trail']));
      const currentMarks = [];
      ['root', 'current', 'cur', 'curr', 'node', 'currentNode', 'p', 'q', 'left', 'right'].forEach(function (key) {
        if (state[key] !== undefined && state[key] !== null) currentMarks.push({ key: key, value: state[key] });
      });
      const marked = Object.create(null);
      const currentLabels = [];
      const relatedLabels = [];
      let visitedCount = 0;
      tree.nodes.forEach(function (node) {
        const el = inst.nodeEls[node.id];
        const classes = ['tree-node'];
        const isVisited = nodeInSet(node, visited);
        if (isVisited) { classes.push('visited'); visitedCount += 1; }
        if (nodeInSet(node, pathSet)) classes.push('path');
        let isCurrent = false;
        let isRelated = false;
        currentMarks.forEach(function (mark) {
          if (!nodeMatches(node, mark.value)) return;
          const relatedKey = mark.key === 'p' || mark.key === 'q' || mark.key === 'left' || mark.key === 'right';
          if (relatedKey) {
            isRelated = true;
            if (relatedLabels.indexOf(mark.key) < 0) relatedLabels.push(mark.key);
          } else {
            isCurrent = true;
            if (currentLabels.indexOf(mark.key) < 0) currentLabels.push(mark.key);
          }
        });
        if (isCurrent) classes.push('current');
        if (isRelated) classes.push('related');
        if (isVisited || isCurrent || isRelated || classes.indexOf('path') >= 0) marked[node.id] = true;
        el.className = classes.join(' ');
      });
      inst.edgeEls.forEach(function (edge) {
        const active = !!marked[edge.parent] && !!marked[edge.child];
        edge.line.setAttribute('class', active ? 'tree-edge active' : 'tree-edge');
      });
      const parts = ['节点 ' + tree.nodes.length];
      if (visitedCount > 0) parts.push('已访问 ' + visitedCount);
      if (currentLabels.length) parts.push('当前 ' + currentLabels.join('/'));
      if (relatedLabels.length) parts.push('关联 ' + relatedLabels.join('/'));
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 6：linked-list 链表 ================= */

  /** 从包装对象取链值；随机链表 Node 的 values 是 [值, random 下标] 对。 */
  function chainValuesFromWrapper(info) {
    if (!info || !isArr(info.values) || !info.values.length) return null;
    if (info.type === 'Node' || info.type === 'RandomNode') {
      return info.values.map(function (item) { return isArr(item) ? fmt(item[0], 8) : fmt(item, 8); });
    }
    return info.values.map(function (item) { return fmt(item, 8); });
  }

  const LIST_POINTER_KEYS = ['prev', 'curr', 'current', 'next', 'node', 'p', 'q', 'slow', 'fast', 'headA', 'headB', 'l1', 'l2', 'list1', 'list2', 'head', 'newHead'];

  function extractLinkedChains(state, demo) {
    const chains = [];
    const seen = Object.create(null);
    function add(label, value) {
      const info = wrapperOf(value);
      if (!info) return;
      const values = chainValuesFromWrapper(info);
      if (!values || !values.length) return;
      const cycle = info.cycle === true;
      const signature = JSON.stringify(values) + '|' + (cycle ? 'cycle' : '');
      if (seen[signature]) return;
      seen[signature] = true;
      chains.push({ label: label, values: values, cycle: cycle, type: info.type });
    }
    if (isObj(demo.inputs)) Object.keys(demo.inputs).forEach(function (key) { add(key, demo.inputs[key]); });
    Object.keys(state).forEach(function (key) { add(key, state[key]); });
    if (chains.length) {
      const preferred = ['head', 'list', 'root', 'headA', 'l1', 'list1', 'headB', 'l2', 'list2'];
      chains.sort(function (a, b) {
        const ai = preferred.indexOf(a.label);
        const bi = preferred.indexOf(b.label);
        return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
      });
      return { chains: chains.slice(0, 4), fromValues: false };
    }
    const values = pickArray(state, demo, ['values', 'vals', 'nums', 'list', 'items']);
    if (values && values.length) {
      return { chains: [{ label: 'list', values: values.map(function (item) { return fmt(item, 8); }), cycle: false, type: 'array' }], fromValues: true };
    }
    const nested = pick(state, ['head', 'list', 'linkedList']);
    if (isObj(nested)) {
      const collected = [];
      let node = nested;
      let guard = 0;
      while (has(node) && guard < 100) {
        if (isObj(node)) {
          collected.push(fmt(firstValue(node.val, node.value, node.data, '?'), 8));
          node = node.next;
        } else {
          collected.push(fmt(node, 8));
          node = null;
        }
        guard += 1;
      }
      if (collected.length) return { chains: [{ label: 'head', values: collected, cycle: false, type: 'nested' }], fromValues: false };
    }
    return { chains: [], fromValues: false };
  }

  function buildListScene(inst, chains) {
    clearNode(inst.root);
    inst.rows = [];
    let maxLength = 0;
    chains.forEach(function (chain) { if (chain.values.length > maxLength) maxLength = chain.values.length; });
    const compact = maxLength > 12;
    const nodeWidth = compact ? 56 : 82;
    const arrowWidth = compact ? 22 : 36;
    chains.forEach(function (chain, chainIndex) {
      const row = make('div', 'list-row');
      row.appendChild(make('span', 'list-row-label', chain.label));
      const track = make('div', 'list-track');
      const items = [];
      chain.values.forEach(function (value, index) {
        const node = make('div', 'list-node');
        node.style.width = nodeWidth + 'px';
        const pointers = make('div', 'list-pointers');
        node.appendChild(pointers);
        node.appendChild(make('span', 'list-node-value', value));
        node.title = chain.label + '[' + index + '] = ' + value;
        track.appendChild(node);
        items.push({ el: node, pointers: pointers, index: index, value: value });
        const isLast = index === chain.values.length - 1;
        const arrow = make('span', 'list-arrow', isLast && chain.cycle ? '↺' : '→');
        if (isLast && chain.cycle) arrow.classList.add('cycle');
        track.appendChild(arrow);
      });
      const tail = make('div', 'list-node list-null');
      tail.style.width = (compact ? 46 : 60) + 'px';
      tail.appendChild(make('span', 'list-node-value', chain.cycle ? '环' : 'null'));
      track.appendChild(tail);
      row.appendChild(track);
      inst.root.appendChild(row);
      inst.rows.push({ label: chain.label, items: items, chain: chain });
    });
    inst.width = 150 + maxLength * (nodeWidth + arrowWidth);
    inst.height = 30 + chains.length * (compact ? 66 : 88);
    inst.root.style.width = inst.width + 'px';
    inst.root.style.height = inst.height + 'px';
    inst.chains = chains;
  }

  const vizLinked = {
    id: 'linked-list',
    label: '链表指针',
    legend: function () {
      return [
        { tone: 'current', label: '指针指向' },
        { tone: 'visited', label: '已访问' },
        { tone: 'accent', label: '节点值' },
        { tone: 'dim', label: 'null / 环' }
      ];
    },
    build: function () {
      return { root: make('div', 'list-scene'), rows: [], chains: [], signature: '', width: 520, height: 220 };
    },
    render: function (inst, demo, step, state) {
      const result = extractLinkedChains(state, demo);
      const chains = result.chains;
      if (!chains.length) {
        return renderStateFallback(inst, state, '当前快照缺少链表节点（ListNode / Node 包装）');
      }
      const signature = JSON.stringify(chains.map(function (chain) { return [chain.label, chain.values, chain.cycle]; }));
      if (signature !== inst.signature) {
        buildListScene(inst, chains);
        inst.signature = signature;
      }
      const visited = markSet(pick(state, ['visited', 'seen']));
      const primary = inst.rows[0];
      inst.rows.forEach(function (row) {
        row.items.forEach(function (item) {
          clearNode(item.pointers);
          item.el.classList.remove('current', 'visited');
          if (visited[String(item.index)] || visited[String(item.value)]) item.el.classList.add('visited');
        });
      });
      // 每条链自己的指针变量（prev / curr / next / p / q ...）标在本链首节点上；
      // 兄弟链表 headA / headB / l1 / l2 是独立输入，不做跨链误标。
      const POINTER_LABEL_KEYS = ['prev', 'curr', 'current', 'next', 'node', 'p', 'q', 'slow', 'fast', 'mid', 'left', 'right', 'newHead'];
      inst.rows.forEach(function (row, rowIndex) {
        if (rowIndex === 0 || !row.items.length) return;
        if (POINTER_LABEL_KEYS.indexOf(row.label) < 0) return;
        const chip = make('span', 'list-pointer', row.label);
        chip.title = row.label + ' 指向该节点';
        row.items[0].pointers.appendChild(chip);
        row.items[0].el.classList.add('current');
      });
      if (primary) {
        LIST_POINTER_KEYS.forEach(function (key) {
          const chainRow = inst.rows.filter(function (row) { return row.label === key; })[0];
          if (chainRow) return;
          const numeric = asNum(state[key]);
          if (numeric === null || !primary.items[numeric]) return;
          const chip = make('span', 'list-pointer', key);
          primary.items[numeric].pointers.appendChild(chip);
          primary.items[numeric].el.classList.add('current');
        });
      }
      const parts = ['链表 ' + chains[0].label + ' · ' + chains[0].values.length + ' 个节点'];
      if (chains[0].cycle) parts.push('有环');
      if (chains.length > 1) parts.push('另显示 ' + (chains.length - 1) + ' 条链');
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 7：graph 图与遍历 ================= */

  function normalizeGraph(state, demo) {
    const inputs = isObj(demo.inputs) ? demo.inputs : {};
    const order = [];
    const indexOf = Object.create(null);
    function register(id) {
      if (!has(id)) return null;
      const key = String(id);
      if (!(key in indexOf)) { indexOf[key] = order.length; order.push(key); }
      return key;
    }
    const graphRaw = firstValue(pick(state, ['graph', 'adj', 'adjacency', 'neighbors']), pick(inputs, ['graph', 'adj', 'adjacency', 'neighbors']));
    let adjacencyList = null;
    let adjacencyMap = null;
    if (isArr(graphRaw)) {
      if (graphRaw.length && graphRaw.every(function (row) { return isArr(row); })) adjacencyList = graphRaw;
    } else if (isObj(graphRaw)) {
      adjacencyMap = graphRaw;
    }
    const rawNodes = firstValue(pick(state, ['nodes', 'vertices', 'vertexes']), pick(inputs, ['nodes', 'vertices']));
    const rawEdges = firstValue(pick(state, ['edges', 'links', 'connections']), pick(inputs, ['edges', 'links']));
    const nodeCount = asNum(firstValue(state.numCourses, state.n, inputs.numCourses, inputs.n));
    if (isArr(rawNodes)) {
      rawNodes.forEach(function (node, index) {
        const id = isObj(node) ? firstValue(node.id, node.key, node.name, node.label, index) : node;
        register(id);
      });
    }
    if (adjacencyList) adjacencyList.forEach(function (targets, index) { register(index); });
    if (adjacencyMap) Object.keys(adjacencyMap).forEach(function (key) { register(key); });
    if (nodeCount !== null && nodeCount <= 200) {
      for (let index = 0; index < nodeCount; index += 1) register(index);
    }
    const nodeCoords = Object.create(null);
    if (isArr(rawNodes)) {
      rawNodes.forEach(function (raw, index) {
        if (!isObj(raw)) return;
        const x = asNum(raw.x);
        const y = asNum(raw.y);
        if (x !== null && y !== null) nodeCoords[String(firstValue(raw.id, raw.key, raw.name, index))] = [x, y];
      });
    }
    const edgePairs = [];
    const seenEdges = Object.create(null);
    function addEdge(from, to) {
      const a = register(from);
      const b = register(to);
      if (a === null || b === null) return;
      const key = a + '>' + b;
      if (seenEdges[key]) return;
      seenEdges[key] = true;
      edgePairs.push([a, b]);
    }
    if (adjacencyList) {
      adjacencyList.forEach(function (targets, index) {
        if (!isArr(targets)) return;
        targets.forEach(function (target) { addEdge(index, target); });
      });
    }
    if (adjacencyMap) {
      Object.keys(adjacencyMap).forEach(function (key) {
        const targets = adjacencyMap[key];
        if (isArr(targets)) targets.forEach(function (target) { addEdge(key, target); });
      });
    }
    if (isArr(rawEdges)) {
      rawEdges.forEach(function (edge) {
        if (isArr(edge) && edge.length >= 2) addEdge(edge[0], edge[1]);
        else if (isObj(edge)) addEdge(firstValue(edge.from, edge.a, edge.source, edge.u), firstValue(edge.to, edge.b, edge.target, edge.v));
      });
    }
    if (!order.length) return null;
    let directed = state.directed === true;
    if (!directed && adjacencyList) {
      for (let index = 0; index < adjacencyList.length && !directed; index += 1) {
        const targets = adjacencyList[index];
        if (!isArr(targets)) continue;
        for (let cursor = 0; cursor < targets.length; cursor += 1) {
          const to = asNum(targets[cursor]);
          if (to === null || !isArr(adjacencyList[to])) continue;
          const reverse = adjacencyList[to].some(function (value) { return asNum(value) === index; });
          if (!reverse) { directed = true; break; }
        }
      }
    }
    const labels = firstValue(pick(state, ['labels', 'names']), pick(inputs, ['labels', 'names']));
    const nodes = order.map(function (id, index) {
      return {
        id: id,
        index: index,
        label: isArr(labels) && has(labels[index]) ? labels[index] : id,
        ids: [id, String(index)],
        x: null,
        y: null,
        coord: nodeCoords[id] || null
      };
    });
    const edges = edgePairs.map(function (pair) {
      return [indexOf[pair[0]], indexOf[pair[1]]];
    });
    const indegreeRaw = firstValue(pick(state, ['indegree', 'inDegree', 'degrees']), pick(inputs, ['indegree', 'inDegree', 'degrees']));
    const indegree = isArr(indegreeRaw) ? indegreeRaw.map(asNum) : null;
    return { nodes: nodes, edges: edges, directed: directed, indegree: indegree };
  }

  function layoutGraph(graph) {
    const width = 620;
    const height = 440;
    const allCoords = graph.nodes.length > 1 && graph.nodes.every(function (node) { return !!node.coord; });
    if (allCoords) {
      let minX = Infinity; let maxX = -Infinity; let minY = Infinity; let maxY = -Infinity;
      graph.nodes.forEach(function (node) {
        minX = Math.min(minX, node.coord[0]); maxX = Math.max(maxX, node.coord[0]);
        minY = Math.min(minY, node.coord[1]); maxY = Math.max(maxY, node.coord[1]);
      });
      const spanX = Math.max(maxX - minX, 1);
      const spanY = Math.max(maxY - minY, 1);
      graph.nodes.forEach(function (node) {
        node.x = 70 + ((node.coord[0] - minX) / spanX) * (width - 140);
        node.y = 70 + ((node.coord[1] - minY) / spanY) * (height - 140);
      });
      return { width: width, height: height };
    }
    const total = graph.nodes.length;
    const cx = width / 2;
    const cy = height / 2;
    const radius = total <= 1 ? 0 : Math.min(215, 80 + total * 16);
    graph.nodes.forEach(function (node, index) {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(total, 1);
      node.x = total === 1 ? cx : cx + Math.cos(angle) * radius;
      node.y = total === 1 ? cy : cy + Math.sin(angle) * radius + 6;
    });
    return { width: width, height: height };
  }

  function buildGraphScene(inst, graph) {
    const size = layoutGraph(graph);
    clearNode(inst.root);
    const svg = svgNode('svg', { class: 'graph-edges', width: size.width, height: size.height });
    let markerId = null;
    if (graph.directed) {
      inst.markerSeq = (inst.markerSeq || 0) + 1;
      markerId = 'graph-arrow-' + inst.markerSeq;
      const defs = svgNode('defs', {});
      const marker = svgNode('marker', { id: markerId, markerWidth: '8', markerHeight: '8', refX: '7', refY: '3', orient: 'auto' });
      marker.appendChild(svgNode('path', { d: 'M0,0 L7,3 L0,6 z', fill: '#8bb7ff' }));
      defs.appendChild(marker);
      svg.appendChild(defs);
    }
    const edgeEls = [];
    graph.edges.forEach(function (pair) {
      const from = graph.nodes[pair[0]];
      const to = graph.nodes[pair[1]];
      if (!from || !to || from === to) return;
      const line = svgNode('line', { x1: from.x, y1: from.y, x2: to.x, y2: to.y, class: 'graph-edge' });
      if (markerId) line.setAttribute('marker-end', 'url(#' + markerId + ')');
      svg.appendChild(line);
      edgeEls.push({ line: line, from: from.index, to: to.index });
    });
    const nodeEls = [];
    graph.nodes.forEach(function (node) {
      const group = svgNode('g', { class: 'graph-node', transform: 'translate(' + node.x + ',' + node.y + ')' });
      group.appendChild(svgNode('circle', { r: '23', class: 'graph-node-circle' }));
      const label = svgNode('text', { class: 'graph-node-label', 'text-anchor': 'middle', dy: '5' });
      label.textContent = fmt(node.label, 4);
      group.appendChild(label);
      const badge = svgNode('text', { class: 'graph-node-badge', 'text-anchor': 'middle', y: '44' });
      group.appendChild(badge);
      svg.appendChild(group);
      nodeEls.push({ group: group, badge: badge, node: node });
    });
    inst.root.appendChild(svg);
    inst.root.style.width = size.width + 'px';
    inst.root.style.height = size.height + 'px';
    inst.width = size.width;
    inst.height = size.height;
    inst.graph = graph;
    inst.nodeEls = nodeEls;
    inst.edgeEls = edgeEls;
  }

  function graphMarkSet(raw, graph) {
    const set = markSet(raw);
    graph.nodes.forEach(function (node) { if (set[node.id]) set[String(node.index)] = true; });
    return set;
  }

  const vizGraph = {
    id: 'graph',
    label: '图与遍历',
    legend: function () {
      return [
        { tone: 'current', label: '当前节点' },
        { tone: 'visited', label: '已访问 / 已选课' },
        { tone: 'pointer', label: '待访问（队列 / 栈）' },
        { tone: 'dim', label: '未访问' }
      ];
    },
    build: function () {
      return { root: make('div', 'graph-scene'), graph: null, nodeEls: null, edgeEls: null, signature: '', width: 620, height: 440, markerSeq: 0 };
    },
    render: function (inst, demo, step, state) {
      const graph = normalizeGraph(state, demo);
      if (!graph) {
        return renderStateFallback(inst, state, '当前快照缺少邻接表 / 边（state.graph / prerequisites）');
      }
      const signature = JSON.stringify({
        nodes: graph.nodes.map(function (node) { return node.id; }),
        edges: graph.edges,
        directed: graph.directed
      });
      if (signature !== inst.signature) {
        buildGraphScene(inst, graph);
        inst.signature = signature;
      }
      const visited = graphMarkSet(pick(state, ['taken', 'visited', 'seen', 'explored']), graph);
      const frontier = graphMarkSet(firstValue(state.queue, state.frontier, state.stack), graph);
      const currentRaw = firstValue(state.node, state.current, state.cur, state.curr);
      const currentNode = graph.nodes.filter(function (node) { return nodeMatches(node, currentRaw); })[0] || null;
      const order = isArr(pick(state, ['order', 'visitedOrder', 'visitOrder'])) ? pick(state, ['order', 'visitedOrder', 'visitOrder']) : null;
      const orderIndex = Object.create(null);
      if (order) order.forEach(function (value, index) { orderIndex[String(value)] = index + 1; });
      let visitedCount = 0;
      inst.nodeEls.forEach(function (entry) {
        const node = entry.node;
        const classes = ['graph-node'];
        const seen = nodeInSet(node, visited);
        if (seen) { classes.push('visited'); visitedCount += 1; }
        if (nodeInSet(node, frontier)) classes.push('frontier');
        if (currentNode && currentNode.index === node.index) classes.push('current');
        entry.group.setAttribute('class', classes.join(' '));
        let badgeText = '';
        if (orderIndex[node.id] !== undefined) badgeText = '#' + orderIndex[node.id];
        else if (orderIndex[String(node.index)] !== undefined) badgeText = '#' + orderIndex[String(node.index)];
        else if (graph.indegree && graph.indegree[node.index] !== null) badgeText = '入度 ' + graph.indegree[node.index];
        entry.badge.textContent = badgeText;
      });
      inst.edgeEls.forEach(function (edge) {
        const classes = ['graph-edge'];
        if (currentNode && (edge.from === currentNode.index || edge.to === currentNode.index)) {
          if (nodeInSet(inst.graph.nodes[edge.from], visited) || nodeInSet(inst.graph.nodes[edge.to], visited)) classes.push('active');
        } else if (nodeInSet(inst.graph.nodes[edge.from], visited) && nodeInSet(inst.graph.nodes[edge.to], visited)) {
          classes.push('visited');
        }
        edge.line.setAttribute('class', classes.join(' '));
      });
      const parts = ['图 ' + graph.nodes.length + ' 节点 · ' + graph.edges.length + ' 条边' + (graph.directed ? ' · 有向' : '')];
      if (visitedCount > 0) parts.push('已访问 ' + visitedCount);
      if (currentNode) parts.push('当前 ' + fmt(currentNode.label, 8));
      const queue = firstValue(state.queue, state.frontier, state.stack);
      if (isArr(queue)) parts.push((state.queue !== undefined ? '队列 ' : '待访问 ') + '[' + queue.map(function (item) { return fmt(item, 6); }).join(', ') + ']');
      const takenCount = asNum(state.taken);
      if (takenCount !== null) parts.push('已完成 ' + takenCount + ' / ' + graph.nodes.length);
      const result = pick(state, ['result', 'canFinish']);
      if (result !== undefined) parts.push('结果 ' + fmt(result, 12));
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 8：string 字符串匹配 ================= */

  const STRING_KEYS = ['s', 'string', 'text', 'word', 'str', 'chars', 'sequence', 'roman', 'result', 'answer', 'res'];

  function textFromValue(value) {
    if (typeof value === 'string') return value;
    if (isArr(value) && value.length && value.every(function (item) { return !isArr(item) && !isObj(item); })) {
      return value.map(function (item) { return fmt(item, 4); }).join('');
    }
    return null;
  }

  function extractStringState(state, demo) {
    const inputs = isObj(demo.inputs) ? demo.inputs : {};
    const inputTexts = [];
    Object.keys(inputs).forEach(function (key) {
      if (typeof inputs[key] === 'string' && inputs[key].length) inputTexts.push({ key: key, text: inputs[key] });
    });
    let primary = null;
    let primaryKey = '';
    for (let index = 0; index < STRING_KEYS.length; index += 1) {
      const key = STRING_KEYS[index];
      const text = textFromValue(state[key]);
      if (text !== null && text.length) { primary = text; primaryKey = key; break; }
    }
    if (primary === null && inputTexts.length) { primary = inputTexts[0].text; primaryKey = inputTexts[0].key; }
    if (primary === null) {
      let best = null;
      let bestKey = '';
      Object.keys(state).forEach(function (key) {
        if (typeof state[key] !== 'string' || !state[key].length) return;
        if (best === null || state[key].length > best.length) { best = state[key]; bestKey = key; }
      });
      if (best !== null) { primary = best; primaryKey = bestKey; }
    }
    if (primary === null) return null;
    let secondary = null;
    let secondaryKey = '';
    inputTexts.forEach(function (entry) {
      if (secondary !== null || entry.key === primaryKey || entry.text === primary) return;
      secondary = entry.text;
      secondaryKey = entry.key;
    });
    if (secondary === null) {
      Object.keys(state).forEach(function (key) {
        if (secondary !== null || key === primaryKey) return;
        if (typeof state[key] !== 'string' || !state[key].length || state[key] === primary) return;
        if (key === 'operation' || key === 'note') return;
        secondary = state[key];
        secondaryKey = key;
      });
    }
    return { primary: primary, primaryKey: primaryKey, secondary: secondary, secondaryKey: secondaryKey };
  }

  function matchedIndexSet(state, length) {
    const set = Object.create(null);
    ['matched', 'matchedIndices', 'matchPositions', 'positions', 'equalIndexes'].forEach(function (key) {
      const raw = state[key];
      if (!isArr(raw)) return;
      raw.forEach(function (item) {
        if (isArr(item) && item.length >= 2) {
          const value = asNum(item[1]);
          if (value !== null && value >= 0 && value < length) set[value] = true;
        } else {
          const value = asNum(item);
          if (value !== null && value >= 0 && value < length) set[value] = true;
        }
      });
    });
    const flags = pick(state, ['match', 'matches', 'matchedFlags', 'equal']);
    if (isArr(flags) && flags.length === length) {
      flags.forEach(function (flag, index) { if (flag) set[index] = true; });
    }
    return set;
  }

  function stringRow(label, text, cell, className) {
    const row = make('div', 'string-row ' + className);
    row.appendChild(make('span', 'string-row-label', label));
    const track = make('div', 'string-track');
    const cells = [];
    text.split('').forEach(function (ch, index) {
      const item = make('div', 'string-cell');
      item.style.width = cell + 'px';
      const pointers = make('div', 'string-pointers');
      item.appendChild(pointers);
      item.appendChild(make('span', 'string-char', ch === ' ' ? '␣' : ch));
      item.appendChild(make('span', 'string-index', index));
      item.title = label + '[' + index + '] = ' + ch;
      track.appendChild(item);
      cells.push({ el: item, pointers: pointers, index: index, char: ch });
    });
    row.appendChild(track);
    return { row: row, cells: cells, label: label };
  }

  function buildStringScene(inst, model) {
    clearNode(inst.root);
    const length = model.primary.length;
    const cell = length > 40 ? 22 : length > 24 ? 30 : length > 16 ? 38 : 52;
    inst.cell = cell;
    inst.primaryRow = stringRow(model.primaryKey || '字符串', model.primary, cell, 'primary');
    inst.root.appendChild(inst.primaryRow.row);
    inst.secondaryRow = null;
    if (model.secondary) {
      inst.secondaryRow = stringRow(model.secondaryKey || '模式', model.secondary, cell, 'secondary');
      inst.root.appendChild(inst.secondaryRow.row);
    }
    inst.width = Math.max(360, 110 + length * (cell + 8));
    inst.height = 150 + (model.secondary ? 96 : 0);
    inst.root.style.width = inst.width + 'px';
    inst.root.style.height = inst.height + 'px';
    inst.model = model;
  }

  const vizString = {
    id: 'string',
    label: '字符串匹配',
    legend: function () {
      return [
        { tone: 'current', label: '当前位置' },
        { tone: 'pointer', label: '指针 i / j / left / right' },
        { tone: 'visited', label: '已匹配' },
        { tone: 'accent', label: '字符' }
      ];
    },
    build: function () {
      return { root: make('div', 'string-scene'), primaryRow: null, secondaryRow: null, model: null, signature: '', cell: 52, width: 420, height: 240 };
    },
    render: function (inst, demo, step, state) {
      const model = extractStringState(state, demo);
      if (!model) {
        return renderStateFallback(inst, state, '当前快照缺少字符串变量');
      }
      const signature = model.primary + '|' + (model.secondary || '');
      if (signature !== inst.signature) {
        buildStringScene(inst, model);
        inst.signature = signature;
      }
      const matched = matchedIndexSet(state, model.primary.length);
      const pointers = pointersOf(state, demo, model.primary.length - 1);
      inst.primaryRow.cells.forEach(function (item) {
        clearNode(item.pointers);
        item.el.classList.remove('current');
        item.el.classList.toggle('matched', !!matched[item.index]);
      });
      if (inst.secondaryRow) {
        inst.secondaryRow.cells.forEach(function (item) { clearNode(item.pointers); item.el.classList.remove('current'); });
      }
      pointers.forEach(function (pointer) {
        if (inst.primaryRow.cells[pointer.index]) {
          const chip = make('span', 'string-pointer', pointer.label);
          chip.title = '指针 ' + pointer.key + ' = ' + pointer.index;
          inst.primaryRow.cells[pointer.index].pointers.appendChild(chip);
        }
        if (inst.secondaryRow && inst.secondaryRow.cells[pointer.index] && pointer.index < model.secondary.length) {
          const chip = make('span', 'string-pointer secondary', pointer.label);
          inst.secondaryRow.cells[pointer.index].pointers.appendChild(chip);
        }
      });
      const current = asNum(firstValue(state.current, state.cur, state.right, state.j, state.i, state.ptr, state.pos, state.left, state.l));
      if (current !== null && inst.primaryRow.cells[current]) inst.primaryRow.cells[current].el.classList.add('current');
      const matchedCount = countKeys(matched);
      const parts = ['字符串长度 ' + model.primary.length];
      if (pointers.length) parts.push(pointers.map(function (pointer) { return pointer.label + '=' + pointer.index; }).join(' '));
      if (matchedCount > 0) parts.push('已匹配 ' + matchedCount);
      const window = firstValue(state.window, state.counter, state.count);
      if (isObj(window)) parts.push('窗口 ' + fmt(window, 36));
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 9：stack-queue 栈 / 队列 ================= */

  const STACK_NAME_KEYS = ['stack', 'min_stack', 'mono_stack', 'st', '栈'];
  const QUEUE_NAME_KEYS = ['queue', 'deque', 'q', '队列', 'waiting'];

  function extractStackQueue(state, demo) {
    const hint = String((demo.layout && demo.layout.primary) || '').toLowerCase();
    const stacks = [];
    const queues = [];
    Object.keys(state).forEach(function (key) {
      const value = state[key];
      if (!isArr(value)) return;
      if (value.length && value.every(function (item) { return isArr(item) || isObj(item); })) return;
      const lowered = key.toLowerCase();
      const queueName = lowered.indexOf('queue') >= 0 || lowered.indexOf('deque') >= 0 || key.indexOf('队') >= 0;
      const stackName = lowered.indexOf('stack') >= 0 || key.indexOf('栈') >= 0;
      if (queueName) queues.push({ key: key, values: value.slice() });
      else if (stackName) stacks.push({ key: key, values: value.slice() });
    });
    if (!stacks.length && !queues.length) {
      const generic = pick(state, ['items', 'elements', 'values', 'vals', 'data']);
      if (isArr(generic) && generic.every(function (item) { return !isArr(item) && !isObj(item); })) {
        const isQueue = hint.indexOf('queue') >= 0 || hint.indexOf('队') >= 0;
        if (isQueue) queues.push({ key: 'queue', values: generic.slice() });
        else stacks.push({ key: 'stack', values: generic.slice() });
      }
    }
    if (!stacks.length && !queues.length) return null;
    return { stacks: stacks.slice(0, 2), queues: queues.slice(0, 2) };
  }

  function buildStackPanel(entry, previousSize) {
    const panel = make('div', 'sq-panel stack-panel');
    const head = make('div', 'sq-panel-head');
    head.appendChild(make('span', 'sq-panel-title', entry.key + ' · 栈'));
    head.appendChild(make('span', 'sq-panel-hint', entry.values.length ? '栈顶 ↑' : '长度 0'));
    panel.appendChild(head);
    const list = make('div', 'stack-list');
    const items = [];
    const grew = previousSize !== undefined && entry.values.length > previousSize;
    for (let index = entry.values.length - 1; index >= 0; index -= 1) {
      const item = make('div', 'stack-item' + (index === entry.values.length - 1 ? ' top' : ''));
      if (grew && index === entry.values.length - 1) item.classList.add('entering');
      item.appendChild(make('span', 'stack-item-value', fmt(entry.values[index], 12)));
      item.appendChild(make('span', 'stack-item-index', index));
      list.appendChild(item);
      items.push(item);
    }
    if (!entry.values.length) list.appendChild(make('div', 'sq-empty', '空栈'));
    panel.appendChild(list);
    panel.dataset.size = String(entry.values.length);
    return { panel: panel, items: items, entry: entry, kind: 'stack' };
  }

  function buildQueuePanel(entry, previousSize) {
    const panel = make('div', 'sq-panel queue-panel');
    const head = make('div', 'sq-panel-head');
    head.appendChild(make('span', 'sq-panel-title', entry.key + ' · 队列'));
    head.appendChild(make('span', 'sq-panel-hint', entry.values.length ? '队首 ← · 队尾 →' : '长度 0'));
    panel.appendChild(head);
    const list = make('div', 'queue-list');
    const items = [];
    const grew = previousSize !== undefined && entry.values.length > previousSize;
    entry.values.forEach(function (value, index) {
      const item = make('div', 'queue-item');
      if (index === 0) item.classList.add('front');
      if (index === entry.values.length - 1) item.classList.add('rear');
      if (grew && index >= previousSize) item.classList.add('entering');
      item.appendChild(make('span', 'queue-item-value', fmt(value, 12)));
      item.appendChild(make('span', 'queue-item-index', index));
      list.appendChild(item);
      items.push(item);
    });
    if (!entry.values.length) list.appendChild(make('div', 'sq-empty', '空队列'));
    panel.appendChild(list);
    panel.dataset.size = String(entry.values.length);
    return { panel: panel, items: items, entry: entry, kind: 'queue' };
  }

  const vizStackQueue = {
    id: 'stack-queue',
    label: '栈 / 队列',
    legend: function () {
      return [
        { tone: 'current', label: '栈顶 / 队首' },
        { tone: 'pointer', label: '队尾' },
        { tone: 'accent', label: '元素' },
        { tone: 'dim', label: '空结构' }
      ];
    },
    build: function () {
      return { root: make('div', 'sq-scene'), panels: [], signature: '', sizes: Object.create(null), width: 460, height: 320 };
    },
    render: function (inst, demo, step, state) {
      const model = extractStackQueue(state, demo);
      if (!model) {
        return renderStateFallback(inst, state, '当前快照缺少栈 / 队列列表（变量名含 stack / queue）');
      }
      const signature = JSON.stringify({
        stacks: model.stacks.map(function (entry) { return [entry.key, entry.values]; }),
        queues: model.queues.map(function (entry) { return [entry.key, entry.values]; })
      });
      if (signature !== inst.signature) {
        clearNode(inst.root);
        inst.panels = [];
        const previousSizes = inst.sizes || Object.create(null);
        model.stacks.forEach(function (entry) { inst.panels.push(buildStackPanel(entry, previousSizes[entry.key])); });
        model.queues.forEach(function (entry) { inst.panels.push(buildQueuePanel(entry, previousSizes[entry.key])); });
        inst.panels.forEach(function (panel) { inst.root.appendChild(panel.panel); });
        const sizes = Object.create(null);
        model.stacks.concat(model.queues).forEach(function (entry) { sizes[entry.key] = entry.values.length; });
        inst.sizes = sizes;
        inst.signature = signature;
        inst.width = 500;
        inst.height = Math.max(240, 100 + model.stacks.length * 130 + model.queues.length * 120);
        inst.root.style.width = inst.width + 'px';
        inst.root.style.height = inst.height + 'px';
      }
      const parts = [];
      model.stacks.forEach(function (entry) {
        const top = entry.values.length ? fmt(entry.values[entry.values.length - 1], 10) : '空';
        parts.push('栈 ' + entry.key + ' 大小 ' + entry.values.length + ' · 栈顶 ' + top);
      });
      model.queues.forEach(function (entry) {
        const front = entry.values.length ? fmt(entry.values[0], 10) : '空';
        const rear = entry.values.length ? fmt(entry.values[entry.values.length - 1], 10) : '空';
        parts.push('队列 ' + entry.key + ' 长度 ' + entry.values.length + ' · 队首 ' + front + ' · 队尾 ' + rear);
      });
      if (state.operation !== undefined) parts.push('操作 ' + fmt(state.operation, 24));
      if (state.returned !== undefined) parts.push('返回 ' + fmt(state.returned, 20));
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 10：backtracking 回溯搜索 ================= */

  function noteDepth(note) {
    const text = String(note || '');
    const marker = '递归深度';
    const index = text.lastIndexOf(marker);
    if (index < 0) return null;
    let cursor = index + marker.length;
    while (cursor < text.length && (text.charAt(cursor) === ' ' || text.charAt(cursor) === ':' || text.charAt(cursor) === '：')) cursor += 1;
    let digits = '';
    while (cursor < text.length && text.charAt(cursor) >= '0' && text.charAt(cursor) <= '9') { digits += text.charAt(cursor); cursor += 1; }
    return digits ? Number(digits) : null;
  }

  function extractBacktracking(state, demo, step) {
    const frames = isArr(state.stack) ? state.stack : (isArr(state.frames) ? state.frames : null);
    const pathRaw = pick(state, ['path', 'track', 'route', 'combination', 'subset', 'permutation', 'picked']);
    let path = null;
    if (isArr(pathRaw)) path = pathRaw.slice();
    else if (typeof pathRaw === 'string') path = pathRaw.split('');
    const choices = firstValue(pick(state, ['choices', 'candidates', 'options', 'remaining', 'nums', 'numbers']), firstArrayValue(demo.inputs), null);
    let usedFlags = null;
    const flagsRaw = pick(state, ['used', 'taken', 'pickedFlags']);
    if (isArr(flagsRaw) && flagsRaw.length && flagsRaw.every(function (item) { return typeof item === 'boolean'; })) usedFlags = flagsRaw;
    let usedIndices = null;
    const indicesRaw = pick(state, ['usedIndices', 'usedIndexes', 'chosenIndexes', 'pickedIndices', 'indices']);
    if (isArr(indicesRaw) && indicesRaw.length && indicesRaw.every(function (item) { return asNum(item) !== null; })) usedIndices = indicesRaw.map(asNum);
    const results = pick(state, ['res', 'ans', 'results', 'solutions', 'answers', 'output']);
    const board = firstValue(pick(state, ['board', 'queens']), null);
    const depth = noteDepth(step.note);
    return {
      frames: frames,
      path: path,
      choices: isArr(choices) ? choices.slice(0, 24) : null,
      usedFlags: usedFlags,
      usedIndices: usedIndices,
      results: isArr(results) ? results : null,
      board: normalizeGrid(board),
      depth: depth,
      current: pick(state, ['current', 'choice', 'num', 'row', 'col'])
    };
  }

  function buildBoardGrid(board) {
    const grid = make('div', 'bt-board');
    const rows = board.length;
    const cols = board[0].length;
    const cell = Math.min(26, Math.max(12, Math.floor(220 / Math.max(rows, cols))));
    grid.style.gridTemplateColumns = 'repeat(' + cols + ', ' + cell + 'px)';
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const value = board[row][col];
        const item = make('div', 'bt-board-cell');
        if (value === 'Q' || value === 1 || value === '1' || value === true) item.classList.add('queen');
        item.textContent = value === 'Q' || value === 1 || value === '1' || value === true ? 'Q' : '';
        grid.appendChild(item);
      }
    }
    return grid;
  }

  const vizBacktracking = {
    id: 'backtracking',
    label: '回溯搜索',
    legend: function () {
      return [
        { tone: 'current', label: '当前选择' },
        { tone: 'visited', label: '已在路径中' },
        { tone: 'pointer', label: '候选 / 已用' },
        { tone: 'dim', label: '未选' }
      ];
    },
    build: function () {
      return { root: make('div', 'bt-scene'), signature: '', width: 560, height: 360 };
    },
    render: function (inst, demo, step, state) {
      const model = extractBacktracking(state, demo, step);
      if (!model.path && !model.choices && !model.board && !model.results && model.depth === null && !model.frames) {
        return renderStateFallback(inst, state, '当前快照缺少路径 / 候选 / 棋盘');
      }
      const signature = JSON.stringify({
        frames: model.frames,
        path: model.path,
        choices: model.choices,
        usedFlags: model.usedFlags,
        usedIndices: model.usedIndices,
        results: model.results ? model.results.length : 0,
        board: model.board,
        depth: model.depth
      });
      clearNode(inst.root);
      const scene = make('div', 'bt-inner');
      const depth = model.depth !== null ? model.depth : (model.frames ? model.frames.length : null);
      if (depth !== null || model.frames) {
        const head = make('div', 'bt-depth');
        head.appendChild(make('span', 'bt-depth-label', '递归深度'));
        head.appendChild(make('span', 'bt-depth-value', depth !== null ? depth : model.frames.length));
        if (model.frames) {
          const frameText = model.frames.slice(-4).map(function (frame) { return fmt(frame, 20); }).join(' → ');
          head.appendChild(make('span', 'bt-depth-frames', frameText));
        }
        scene.appendChild(head);
      }
      if (model.path || model.choices) {
        const panel = make('div', 'bt-panel');
        panel.appendChild(make('div', 'bt-panel-title', '当前路径'));
        const track = make('div', 'bt-path');
        const pathValues = model.path || [];
        if (!pathValues.length) track.appendChild(make('span', 'bt-empty', '（空路径，尚未选择）'));
        pathValues.forEach(function (value) {
          track.appendChild(make('span', 'bt-chip', fmt(value, 10)));
          track.appendChild(make('span', 'bt-arrow', '→'));
        });
        panel.appendChild(track);
        scene.appendChild(panel);
      }
      if (model.choices) {
        const panel = make('div', 'bt-panel');
        panel.appendChild(make('div', 'bt-panel-title', '候选集合'));
        const track = make('div', 'bt-choices');
        model.choices.forEach(function (value, index) {
          const item = make('div', 'bt-choice');
          item.appendChild(make('span', 'bt-choice-value', fmt(value, 8)));
          item.appendChild(make('span', 'bt-choice-index', index));
          const used = (model.usedFlags && model.usedFlags[index]) || (model.usedIndices && model.usedIndices.indexOf(index) >= 0);
          if (used) item.classList.add('used');
          if ((model.path || []).some(function (itemValue) { return String(itemValue) === String(value); })) item.classList.add('on-path');
          track.appendChild(item);
        });
        panel.appendChild(track);
        scene.appendChild(panel);
      }
      if (model.board) {
        const panel = make('div', 'bt-panel');
        panel.appendChild(make('div', 'bt-panel-title', '棋盘 / 矩阵'));
        panel.appendChild(buildBoardGrid(model.board));
        scene.appendChild(panel);
      }
      if (model.results) {
        const panel = make('div', 'bt-panel');
        panel.appendChild(make('div', 'bt-panel-title', '已找到 ' + model.results.length + ' 个解'));
        const track = make('div', 'bt-results');
        model.results.slice(0, 6).forEach(function (value) { track.appendChild(make('span', 'bt-result', fmt(value, 24))); });
        if (model.results.length > 6) track.appendChild(make('span', 'bt-empty', '…'));
        panel.appendChild(track);
        scene.appendChild(panel);
      }
      inst.root.appendChild(scene);
      inst.width = 560;
      inst.height = Math.max(240, 80 + ((model.path || model.choices) ? 64 : 0) + (model.choices ? 110 : 0) + (model.board ? 210 : 0) + (model.results ? 80 : 0));
      inst.root.style.width = inst.width + 'px';
      inst.root.style.height = inst.height + 'px';
      inst.signature = signature;
      const parts = [];
      if (depth !== null) parts.push('递归深度 ' + depth);
      if (model.path) parts.push('路径长度 ' + model.path.length);
      if (model.results) parts.push('已找到 ' + model.results.length + ' 个解');
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 11：design 操作流水线 ================= */

  /** 值卡片：一维数组显示 chips；[[k,v]] 保序对显示 k → v；其它显示格式化文本。 */
  function valueView(value) {
    if (isArr(value) && value.length > 0 && value.length <= 16 && value.every(function (item) { return !isArr(item) && !isObj(item); })) {
      const chips = make('div', 'value-chips');
      value.forEach(function (item) { chips.appendChild(make('span', 'value-chip', fmt(item, 10))); });
      return chips;
    }
    if (isArr(value) && value.length > 0 && value.length <= 12 && value.every(function (item) {
      return isArr(item) && item.length <= 4 && item.every(function (part) { return !isArr(part) && !isObj(part); });
    })) {
      const chips = make('div', 'value-chips');
      value.forEach(function (item) {
        chips.appendChild(make('span', 'value-chip', item.map(function (part) { return fmt(part, 10); }).join(' → ')));
      });
      return chips;
    }
    return make('span', 'value-text', fmt(value, 80));
  }

  /** 把设计类操作对象 {method, args, kwargs} 转成可读标签，如 put(1, 1)。 */
  function operationLabel(op) {
    if (isObj(op)) {
      const method = fmt(firstValue(op.method, op.op, op.name, op.action, op.type, 'op'), 30);
      const args = isArr(op.args) ? op.args : [];
      const kwargs = isObj(op.kwargs) ? op.kwargs : {};
      const pieces = args.map(function (value) { return fmt(value, 20); });
      Object.keys(kwargs).forEach(function (key) { pieces.push(key + '=' + fmt(kwargs[key], 20)); });
      return method + '(' + pieces.join(', ') + ')';
    }
    return fmt(op, 60);
  }

  /** 去掉空白后比较操作文本，兼容后端 operation='put(1, 1)' 与标签 'put(1,1)'。 */
  function normalizeOperationText(text) {
    return String(text === null || text === undefined ? '' : text).split(' ').join('');
  }

  function extractDesign(state, demo) {
    const inputs = isObj(demo.inputs) ? demo.inputs : {};
    let ops = firstValue(pick(inputs, ['operations', 'ops', 'actions']), pick(state, ['operations', 'ops', 'actions']));
    if (!isArr(ops)) ops = null;
    const currentOperation = firstValue(state.operation, state.op, state.call);
    let currentIndex = asNum(firstValue(state.index, state.i, state.step, state.pos, state.cursor));
    let matchIndices = null;
    if (ops && has(currentOperation)) {
      const operationText = normalizeOperationText(currentOperation);
      matchIndices = [];
      ops.forEach(function (op, index) {
        if (normalizeOperationText(operationLabel(op)) === operationText) matchIndices.push(index);
      });
    }
    const returned = firstValue(state.returned, state.return, state.output);
    const inputKeys = isObj(demo.inputs) ? Object.keys(demo.inputs) : [];
    const attrs = [];
    Object.keys(state).forEach(function (key) {
      if (key === 'operation' || key === 'returned' || key === 'return' || key === 'output' || key === 'highlight') return;
      // inputs 里的 className/constructor/operations 是调用序列，不是实例属性快照。
      if (inputKeys.indexOf(key) >= 0 && key !== 'operation') return;
      attrs.push({ key: key, value: state[key] });
    });
    return {
      ops: ops,
      currentIndex: currentIndex,
      matchIndices: matchIndices,
      currentOperation: currentOperation,
      returned: returned,
      attrs: attrs,
      result: demo.result,
      documented: pick(inputs, ['documentedOutput', 'expectedOutput']),
      className: pick(inputs, ['className', 'class'])
    };
  }

  const vizDesign = {
    id: 'design',
    label: '操作流水线',
    legend: function () {
      return [
        { tone: 'current', label: '当前操作' },
        { tone: 'visited', label: '已完成' },
        { tone: 'dim', label: '待执行' },
        { tone: 'accent', label: '实例属性 / 返回值' }
      ];
    },
    build: function () {
      return { root: make('div', 'design-scene'), signature: '', width: 620, height: 360 };
    },
    render: function (inst, demo, step, state) {
      const model = extractDesign(state, demo);
      if (!model.ops && model.currentOperation === undefined && !model.attrs.length) {
        return renderStateFallback(inst, state, '当前快照缺少操作序列（operation / operations）');
      }
      if (model.matchIndices && model.matchIndices.length) {
        if (model.matchIndices.length === 1) {
          model.currentIndex = model.matchIndices[0];
        } else {
          const lastIndex = typeof inst.lastOpIndex === 'number' ? inst.lastOpIndex : -1;
          let nextIndex = -1;
          model.matchIndices.forEach(function (index) { if (nextIndex < 0 && index > lastIndex) nextIndex = index; });
          model.currentIndex = nextIndex >= 0 ? nextIndex : model.matchIndices[0];
        }
        inst.lastOpIndex = model.currentIndex;
      } else if (model.currentIndex !== null && model.ops && model.currentIndex >= model.ops.length) {
        model.currentIndex = null;
      }
      clearNode(inst.root);
      const scene = make('div', 'design-inner');
      if (model.className) scene.appendChild(make('div', 'design-class', '设计类：' + fmt(model.className, 30)));
      if (model.ops) {
        const line = make('div', 'design-pipeline');
        model.ops.forEach(function (op, index) {
          const item = make('div', 'design-op');
          item.appendChild(make('span', 'design-op-index', index + 1));
          item.appendChild(make('span', 'design-op-label', fmt(operationLabel(op), 42)));
          if (model.currentIndex !== null) {
            if (index < model.currentIndex) item.classList.add('done');
            else if (index === model.currentIndex) item.classList.add('current');
            else item.classList.add('pending');
          }
          line.appendChild(item);
        });
        scene.appendChild(line);
      }
      const current = make('div', 'design-current');
      current.appendChild(make('span', 'design-current-label', '当前操作'));
      current.appendChild(make('span', 'design-current-value', model.currentOperation !== undefined ? fmt(model.currentOperation, 60) : '（未开始）'));
      if (model.returned !== undefined) {
        current.appendChild(make('span', 'design-returned', '返回 ' + fmt(model.returned, 24)));
      }
      scene.appendChild(current);
      const attrs = make('div', 'design-attrs');
      model.attrs.forEach(function (attr) {
        const card = make('div', 'design-attr');
        card.appendChild(make('span', 'design-attr-key', attr.key));
        card.appendChild(valueView(attr.value));
        attrs.appendChild(card);
      });
      if (model.attrs.length) scene.appendChild(attrs);
      if (model.result !== undefined) {
        const result = make('div', 'design-result');
        result.appendChild(make('span', 'design-result-label', '演示结果'));
        result.appendChild(valueView(model.result));
        scene.appendChild(result);
      }
      inst.root.appendChild(scene);
      inst.width = 620;
      const pipelineRows = model.ops ? Math.max(1, Math.ceil(model.ops.length / 5)) : 0;
      inst.height = Math.max(300, 92 + pipelineRows * 58 + 58 + Math.min(model.attrs.length, 8) * 50 + (model.result !== undefined ? 58 : 0));
      inst.root.style.width = inst.width + 'px';
      inst.root.style.height = inst.height + 'px';
      const parts = [];
      if (model.className) parts.push('类 ' + fmt(model.className, 24));
      if (model.ops) parts.push('操作 ' + (model.currentIndex !== null ? model.currentIndex + 1 : 0) + ' / ' + model.ops.length);
      if (model.returned !== undefined) parts.push('返回 ' + fmt(model.returned, 16));
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器 12：scalar 状态变量 ================= */

  const vizScalar = {
    id: 'scalar',
    label: '状态变量',
    legend: function () {
      return [
        { tone: 'current', label: '本步变化字段' },
        { tone: 'accent', label: '普通字段' },
        { tone: 'dim', label: '结果字段' }
      ];
    },
    build: function () {
      return { root: make('div', 'scalar-scene'), signature: '', width: 520, height: 300 };
    },
    render: function (inst, demo, step, state) {
      const keys = Object.keys(state);
      if (!keys.length) {
        return { unavailable: true, caption: '当前快照为空', message: '当前步骤没有可展示的状态变量' };
      }
      const highlights = isArr(step.highlight) ? step.highlight.map(String) : [];
      const ordered = keys.slice().sort(function (a, b) {
        const ah = highlights.indexOf(a) >= 0 ? 0 : 1;
        const bh = highlights.indexOf(b) >= 0 ? 0 : 1;
        return ah - bh;
      });
      const shown = ordered.slice(0, 24);
      const scene = make('div', 'scalar-inner');
      shown.forEach(function (key) {
        const card = make('div', 'scalar-card');
        if (highlights.indexOf(key) >= 0) card.classList.add('active');
        if (key === 'result' || key === 'answer' || key === 'res') card.classList.add('result');
        card.appendChild(make('span', 'scalar-key', key));
        card.appendChild(valueView(state[key]));
        scene.appendChild(card);
      });
      if (ordered.length > shown.length) scene.appendChild(make('div', 'scalar-more', '另有 ' + (ordered.length - shown.length) + ' 个字段，见右侧变量表'));
      clearNode(inst.root);
      inst.root.appendChild(scene);
      inst.width = 540;
      inst.height = Math.max(220, 80 + Math.ceil(shown.length / 2) * 54);
      inst.root.style.width = inst.width + 'px';
      inst.root.style.height = inst.height + 'px';
      const parts = ['状态字段 ' + keys.length + ' 个'];
      if (highlights.length) parts.push('本步变化 ' + highlights.join(', '));
      if (has(state.result)) parts.push('结果 ' + fmt(state.result, 20));
      return { caption: parts.join(' · ') };
    }
  };

  /* ================= 渲染器注册表 ================= */

  const RENDERERS = {
    grid: vizGrid,
    matrix: vizMatrix,
    array: vizArray,
    dp: vizDp,
    tree: vizTree,
    'linked-list': vizLinked,
    graph: vizGraph,
    string: vizString,
    'stack-queue': vizStackQueue,
    backtracking: vizBacktracking,
    design: vizDesign,
    scalar: vizScalar
  };

  /* ================= 页面状态与页面外壳 ================= */

  const root = document.getElementById('lab');
  const app = {
    id: '',
    sample: 0,
    token: '',
    demo: null,
    steps: [],
    index: 0,
    timer: null,
    playing: false,
    speed: DEFAULT_SPEED,
    angle: -28,
    tilt: 58,
    zoom: 1,
    fitZoom: 1,
    requestSeq: 0,
    controller: null,
    viz: '',
    renderer: null,
    instance: null,
    warnings: [],
    els: null
  };

  const SWATCH_CLASS = {
    current: 'swatch-current',
    visited: 'swatch-visited',
    accent: 'swatch-accent',
    dim: 'swatch-dim',
    pointer: 'swatch-pointer'
  };

  /** 根据错误码给出中文提示，未知错误码保留原始信息。 */
  function describeError(error) {
    const code = error && error.code ? String(error.code) : 'UNKNOWN';
    const known = {
      QUESTION_REQUIRED: '缺少 question 参数。请从算法练习页的「打开交互演示」入口进入本页。',
      DEMO_NOT_AVAILABLE: '该题暂未提供交互演示（后端尚未生成官方参考解追踪），请回到原题查看题解。',
      DEMO_SAMPLE_NOT_FOUND: '所选示例不存在，请切换示例或返回原题。',
      DEMO_SAMPLE_INVALID: '该示例的输入格式与官方参考解不匹配，暂时无法生成演示。',
      DEMO_EXECUTION_FAILED: '追踪引擎执行官方参考解失败，已停止播放以避免展示错误步骤。',
      DEMO_TIMEOUT: '追踪引擎执行超时，请稍后重试或继续阅读题解。',
      DEMO_RESULT_MISMATCH: '追踪结果与官方样例输出不一致，已停止播放以避免展示错误演示。',
      DEMO_NO_STEPS: '该题暂无可播放的演示步骤。',
      DEMO_EMPTY: '接口没有返回演示数据。',
      DEMO_SCHEMA_OLD: '演示接口返回的仍是旧版数据（缺少 demo-2 契约），暂不能播放；请等待后端追踪引擎更新后重试。',
      BAD_JSON: '接口返回了无法解析的数据，请确认后端版本与本页一致。',
      NETWORK: '无法连接本机学涯服务，请确认后端已启动后重试。',
      AUTH_REQUIRED: '登录状态已失效，请重新登录后再打开演示。',
      ORIGIN_FORBIDDEN: '演示仅支持本机访问（127.0.0.1 / localhost）。',
      HTTP_404: '演示接口不存在（404），后端可能尚未部署该功能。'
    };
    if (known[code]) return known[code];
    if (code.indexOf('HTTP_') === 0) return '演示接口请求失败（' + code + '），请稍后重试。';
    return '无法打开本题演示：' + (error && error.message ? String(error.message) : code);
  }

  function setBusy(busy) {
    if (root) root.setAttribute('aria-busy', busy ? 'true' : 'false');
    if (!app.els) return;
    app.els.stage.classList.toggle('loading', !!busy);
    [app.els.prev, app.els.next, app.els.play, app.els.reset, app.els.sample, app.els.speed].forEach(function (el) {
      if (el) el.disabled = !!busy;
    });
  }

  function showLoading() {
    if (!app.els) {
      root.innerHTML = '<div class="lab-loading" role="status"><span class="spinner" aria-hidden="true"></span><p>正在读取原题示例…</p></div>';
      return;
    }
    setBusy(true);
    if (app.els.caption) {
      app.els.caption.hidden = false;
      app.els.caption.textContent = '正在载入示例…';
    }
  }

  function showError(error) {
    stopTimer();
    if (app.controller) {
      try { app.controller.abort(); } catch (ignore) { /* 忽略重复取消 */ }
      app.controller = null;
    }
    const message = describeError(error);
    const detail = error && error.detail ? String(error.detail) : '';
    const origin = app.id ? '/#space/practice/hot100/' + encodeURIComponent(app.id) : RETURN_LIST;
    root.setAttribute('aria-busy', 'false');
    root.innerHTML = [
      '<section class="lab-error" role="alert">',
      '<p class="eyebrow">学涯 / 算法交互实验室</p>',
      '<h1>演示暂时无法播放</h1>',
      '<p class="lab-error-message">' + esc(message) + '</p>',
      detail ? '<p class="lab-error-detail">接口信息：' + esc(detail) + '</p>' : '',
      '<div class="lab-error-actions">',
      '<a class="button" href="' + RETURN_LIST + '">返回 Hot100</a>',
      '<a class="button button-ghost" href="' + origin + '">返回原题</a>',
      '<button type="button" class="button button-ghost" data-retry>重新加载</button>',
      '</div>',
      '<p class="footnote">演示只展示后端生成的确定性教学步骤，不会执行用户提交的代码。</p>',
      '</section>'
    ].join('');
    const retry = root.querySelector('[data-retry]');
    if (retry) {
      retry.addEventListener('click', function () {
        showLoading();
        loadSample(app.sample);
      });
    }
  }

  function renderWarnings() {
    if (!app.els || !app.els.warnings) return;
    const box = app.els.warnings;
    if (!app.warnings.length) {
      box.hidden = true;
      box.innerHTML = '';
      return;
    }
    const items = app.warnings.map(function (text) { return '<li>' + esc(text) + '</li>'; }).join('');
    box.hidden = false;
    box.innerHTML = '<strong>提示</strong><ul>' + items + '</ul>';
  }

  function updateExample(demo) {
    if (!app.els) return;
    const sample = isObj(demo.sample) ? demo.sample : {};
    if (app.els.exampleInput) app.els.exampleInput.textContent = fmt(firstValue(sample.input, ''), 400);
    if (app.els.exampleOutput) app.els.exampleOutput.textContent = '预期输出 ' + fmt(firstValue(sample.output, ''), 80);
    if (app.els.exampleNote) app.els.exampleNote.textContent = has(sample.explanation) ? String(sample.explanation) : '';
    if (app.els.result) {
      app.els.result.textContent = demo.result !== undefined ? '演示结果：' + fmt(demo.result, 60) : '';
    }
  }

  function renderMeta(demo) {
    if (!app.els || !app.els.meta) return;
    const meta = isObj(demo.meta) ? demo.meta : {};
    const blocks = [];
    if (meta.coreIdea) blocks.push('<div class="meta-block"><h3>核心思路</h3><p>' + esc(meta.coreIdea) + '</p></div>');
    const complexity = meta.complexity;
    if (complexity) {
      let text = '';
      if (typeof complexity === 'string') text = complexity;
      else if (isObj(complexity)) {
        const labels = { time: '时间', space: '空间', average: '平均', worst: '最坏', best: '最好' };
        text = Object.keys(complexity).map(function (key) { return (labels[key] || key) + ' ' + fmt(complexity[key], 24); }).join(' · ');
      }
      if (text) blocks.push('<div class="meta-block"><h3>复杂度</h3><p>' + esc(text) + '</p></div>');
    }
    if (isArr(meta.hints) && meta.hints.length) {
      const items = meta.hints.map(function (hint) { return '<li>' + esc(fmt(hint, 220)) + '</li>'; }).join('');
      blocks.push('<details class="meta-block"><summary>提示（' + meta.hints.length + '）</summary><ul>' + items + '</ul></details>');
    }
    if (meta.summary) blocks.push('<div class="meta-block"><h3>演示结论</h3><p>' + esc(meta.summary) + '</p></div>');
    app.els.meta.innerHTML = blocks.join('');
    if (app.els.codeLang) app.els.codeLang.textContent = demo.codeLanguage ? '（' + fmt(demo.codeLanguage, 16) + '）' : '';
  }

  /** 构建整页外壳（示例切换会整体重建）。 */
  function renderShell(demo) {
    const sampleCount = Math.max(1, Math.round(asNum(demo.sampleCount) || 1));
    const sampleIndexRaw = asNum(demo.sampleIndex);
    const sampleIndex = sampleIndexRaw !== null ? clampNum(Math.round(sampleIndexRaw), 0, sampleCount - 1) : 0;
    const numberText = fmt(firstValue(demo.number, demo.questionId, app.id), 12);
    const titleText = fmt(firstValue(demo.title, app.id), 60);
    const origin = app.id ? '/#space/practice/hot100/' + encodeURIComponent(app.id) : RETURN_LIST;
    const badges = [];
    if (demo.topic) badges.push('<span class="badge">' + esc(fmt(demo.topic, 24)) + '</span>');
    if (demo.difficulty) badges.push('<span class="badge badge-difficulty">' + esc(fmt(demo.difficulty, 12)) + '</span>');
    const sampleOptions = [];
    for (let index = 0; index < sampleCount; index += 1) {
      sampleOptions.push('<option value="' + index + '"' + (index === sampleIndex ? ' selected' : '') + '>示例 ' + (index + 1) + '</option>');
    }
    const speedOptions = SPEED_OPTIONS.map(function (entry) {
      return '<option value="' + entry[0] + '"' + (entry[0] === app.speed ? ' selected' : '') + '>' + entry[1] + '</option>';
    }).join('');
    const codeLines = (isArr(demo.code) ? demo.code : []).map(function (line, index) {
      return '<li data-line="' + (index + 1) + '"><code>' + esc(line) + '</code></li>';
    }).join('');
    const vizKey = fmt(demo.viz, 40);
    const vizLabel = VIZ_LABELS[vizKey] || '数据驱动三维演示';
    document.title = '#' + numberText + ' ' + titleText + ' · 算法交互实验室 · 学涯';
    root.setAttribute('aria-busy', 'false');
    root.innerHTML = [
      '<section class="lab-page">',
      '<header class="lab-head">',
      '<div class="lab-title">',
      '<p class="eyebrow">学涯 / 算法交互实验室</p>',
      '<h1>#' + esc(numberText) + ' ' + esc(titleText) + '</h1>',
      badges.length ? '<div class="lab-badges">' + badges.join('') + '</div>' : '',
      '</div>',
      '<div class="lab-actions">',
      '<a class="button" href="' + origin + '">返回原题 ↗</a>',
      '<a class="button button-ghost" href="' + RETURN_LIST + '">返回 Hot100</a>',
      '</div>',
      '</header>',
      '<div class="lab-warnings" data-warnings hidden></div>',
      '<section class="example" aria-label="示例输入与预期输出">',
      '<label class="sample-picker">原题示例 <select data-sample>' + sampleOptions + '</select></label>',
      '<code class="example-input" data-example-input></code>',
      '<strong class="example-output" data-example-output></strong>',
      '<span class="result-chip" data-result></span>',
      '<p class="example-note" data-example-note></p>',
      '</section>',
      '<div class="lab-layout">',
      '<section class="stage-area">',
      '<div class="stage-title"><span data-viz-name>' + esc(vizLabel) + '</span><span class="stage-hint">拖动旋转 · 滚轮缩放 · 双击复位</span></div>',
      '<div class="stage" data-stage tabindex="0" role="application" aria-label="三维演示舞台：拖动旋转，滚轮缩放">',
      '<div class="stage-scene" data-scene></div>',
      '<div class="stage-empty" data-stage-empty hidden></div>',
      '<div class="stage-caption" data-caption hidden></div>',
      '</div>',
      '<div class="legend" data-legend aria-label="图例"></div>',
      '<div class="controls">',
      '<button type="button" data-prev>上一步</button>',
      '<button type="button" class="play-button" data-play aria-pressed="false">播放</button>',
      '<button type="button" data-next>下一步</button>',
      '<button type="button" data-reset>重置</button>',
      '<label class="speed-picker">速度 <select data-speed>' + speedOptions + '</select></label>',
      '<div class="progress" aria-hidden="true"><span class="progress-bar" data-progress></span></div>',
      '</div>',
      '</section>',
      '<aside class="trace" aria-label="执行轨迹">',
      '<div class="trace-head"><p class="eyebrow">执行轨迹</p><p class="step-count"><span data-step>第 1 / 1 步</span><span class="viz-tag" data-viz-tag></span></p></div>',
      '<h2 class="trace-note" data-note aria-live="polite"></h2>',
      '<section class="variables"><h3>变量表</h3><div data-variables></div></section>',
      '<section class="code-panel"><h3>参考代码 <small data-code-lang></small></h3><ol class="code" data-code>' + codeLines + '</ol></section>',
      '<section class="meta" data-meta></section>',
      '<p class="footnote">演示解释官方参考解，不执行用户提交的代码。</p>',
      '</aside>',
      '</div>',
      '</section>'
    ].join('');
    app.els = {
      sample: root.querySelector('[data-sample]'),
      exampleInput: root.querySelector('[data-example-input]'),
      exampleOutput: root.querySelector('[data-example-output]'),
      exampleNote: root.querySelector('[data-example-note]'),
      result: root.querySelector('[data-result]'),
      warnings: root.querySelector('[data-warnings]'),
      stage: root.querySelector('[data-stage]'),
      scene: root.querySelector('[data-scene]'),
      empty: root.querySelector('[data-stage-empty]'),
      caption: root.querySelector('[data-caption]'),
      vizName: root.querySelector('[data-viz-name]'),
      vizTag: root.querySelector('[data-viz-tag]'),
      legend: root.querySelector('[data-legend]'),
      prev: root.querySelector('[data-prev]'),
      play: root.querySelector('[data-play]'),
      next: root.querySelector('[data-next]'),
      reset: root.querySelector('[data-reset]'),
      speed: root.querySelector('[data-speed]'),
      progress: root.querySelector('[data-progress]'),
      step: root.querySelector('[data-step]'),
      note: root.querySelector('[data-note]'),
      variables: root.querySelector('[data-variables]'),
      code: root.querySelector('[data-code]'),
      codeLang: root.querySelector('[data-code-lang]'),
      meta: root.querySelector('[data-meta]')
    };
    updateExample(demo);
    renderMeta(demo);
    app.els.sample.addEventListener('change', function (event) {
      const next = Number(event.target.value);
      if (!Number.isFinite(next) || next < 0) return;
      showLoading();
      loadSample(next);
    });
    app.els.prev.addEventListener('click', function () { stopTimer(); moveStep(-1); });
    app.els.next.addEventListener('click', function () { stopTimer(); moveStep(1); });
    app.els.play.addEventListener('click', togglePlay);
    app.els.reset.addEventListener('click', resetAll);
    app.els.speed.addEventListener('change', function (event) {
      app.speed = Number(event.target.value) || DEFAULT_SPEED;
      if (app.timer) restartTimer();
    });
    bindStage();
  }

  /* ================= 渲染与联动 ================= */

  function computeFit(width, height) {
    const stage = app.els && app.els.stage;
    const stageWidth = stage && stage.clientWidth ? stage.clientWidth : 900;
    const stageHeight = stage && stage.clientHeight ? stage.clientHeight : 520;
    return clampNum(Math.min((stageWidth - 56) / Math.max(width, 1), (stageHeight - 64) / Math.max(height, 1)), 0.24, 1.35);
  }

  function applyPose() {
    if (!app.els || !app.els.scene) return;
    app.els.scene.style.setProperty('--tilt', app.tilt + 'deg');
    app.els.scene.style.setProperty('--spin', app.angle + 'deg');
    app.els.scene.style.setProperty('--zoom', app.zoom.toFixed(3));
  }

  function resetView() {
    const pose = DEFAULT_POSES[app.viz] || DEFAULT_POSES.scalar;
    app.angle = pose.angle;
    app.tilt = pose.tilt;
    app.zoom = app.fitZoom || 1;
    applyPose();
  }

  /** 按 viz 选择渲染器并创建场景实例；未知类型回退 scalar。 */
  function buildScene(demo) {
    let viz = fmt(demo.viz, 40);
    let renderer = RENDERERS[viz];
    if (!renderer) {
      app.warnings.push('未知可视化类型 ' + (viz || '（空）') + '，已回退为状态变量卡。');
      viz = 'scalar';
      renderer = RENDERERS.scalar;
    }
    const scene = app.els.scene;
    clearNode(scene);
    scene.setAttribute('data-viz', viz);
    scene.className = 'stage-scene';
    const initialState = stateOf(demo, demo.steps[0] || {});
    let instance;
    try {
      instance = renderer.build(demo, initialState);
    } catch (error) {
      app.warnings.push('场景构建失败，已回退为状态变量卡：' + (error && error.message ? error.message : '未知错误'));
      viz = 'scalar';
      renderer = RENDERERS.scalar;
      instance = renderer.build(demo, initialState);
    }
    scene.appendChild(instance.root);
    scene.style.width = (instance.width || 420) + 'px';
    scene.style.height = (instance.height || 300) + 'px';
    app.viz = viz;
    app.renderer = renderer;
    app.instance = instance;
    const label = VIZ_LABELS[viz] || renderer.label || viz;
    if (app.els.vizName) app.els.vizName.textContent = label + ' · 数据驱动三维演示';
    if (app.els.vizTag) app.els.vizTag.textContent = 'viz · ' + viz;
    applyPose();
    renderWarnings();
  }

  function updateVariables(state, step) {
    const container = app.els.variables;
    if (!container) return;
    const highlights = isArr(step.highlight) ? step.highlight.map(String) : [];
    const keys = Object.keys(state);
    const ordered = keys.slice().sort(function (a, b) {
      const ah = highlights.indexOf(a) >= 0 ? 0 : 1;
      const bh = highlights.indexOf(b) >= 0 ? 0 : 1;
      return ah - bh;
    });
    const limit = 16;
    const rows = ordered.slice(0, limit).map(function (key) {
      const active = highlights.indexOf(key) >= 0;
      const full = fmt(state[key], 400);
      return '<tr' + (active ? ' class="active"' : '') + '><th scope="row">' + esc(key) + '</th><td title="' + esc(full) + '">' + esc(fmt(state[key], 60)) + '</td></tr>';
    });
    if (ordered.length > limit) {
      rows.push('<tr class="muted"><th scope="row">…</th><td>另有 ' + (ordered.length - limit) + ' 个字段</td></tr>');
    }
    container.innerHTML = rows.length ? '<table><tbody>' + rows.join('') + '</tbody></table>' : '<p class="variables-empty">本步没有状态变量</p>';
  }

  function renderLegend(state) {
    const box = app.els.legend;
    if (!box) return;
    const layoutLegend = app.demo && app.demo.layout && isArr(app.demo.layout.legend) ? app.demo.layout.legend : null;
    let entries = null;
    if (layoutLegend && layoutLegend.length) {
      const tones = ['current', 'visited', 'accent', 'dim', 'pointer'];
      entries = layoutLegend.map(function (item, index) {
        if (isObj(item)) {
          return {
            tone: fmt(firstValue(item.tone, item.color, tones[index % tones.length]), 20),
            label: fmt(firstValue(item.label, item.text, item), 60)
          };
        }
        return { tone: tones[index % tones.length], label: fmt(item, 80) };
      });
    } else if (app.renderer && typeof app.renderer.legend === 'function') {
      entries = app.renderer.legend(app.demo, state) || [];
    }
    box.innerHTML = (entries || []).map(function (entry) {
      const swatch = SWATCH_CLASS[entry.tone] || 'swatch-accent';
      return '<span class="legend-item"><i class="swatch ' + swatch + '" aria-hidden="true"></i>' + esc(entry.label) + '</span>';
    }).join('');
  }

  function updateCode(step) {
    const container = app.els.code;
    if (!container) return;
    const line = asNum(step.line);
    let active = null;
    for (let index = 0; index < container.children.length; index += 1) {
      const item = container.children[index];
      const lineNumber = Number(item.getAttribute('data-line'));
      const isActive = line !== null && line > 0 && lineNumber === line;
      item.classList.toggle('active', isActive);
      if (isActive) active = item;
    }
    if (active) {
      container.scrollTop = Math.max(0, active.offsetTop - container.clientHeight / 2);
    }
  }

  function syncControls() {
    if (!app.els) return;
    const total = app.steps.length;
    if (app.els.prev) app.els.prev.disabled = app.index <= 0;
    if (app.els.next) app.els.next.disabled = app.index >= total - 1;
    if (app.els.play) {
      app.els.play.textContent = app.playing ? '暂停' : '播放';
      app.els.play.setAttribute('aria-pressed', app.playing ? 'true' : 'false');
      app.els.play.classList.toggle('playing', app.playing);
    }
    if (app.els.reset) app.els.reset.disabled = false;
    if (app.els.progress) {
      const ratio = total > 1 ? app.index / (total - 1) : 1;
      app.els.progress.style.width = (ratio * 100).toFixed(2) + '%';
    }
  }

  /** 渲染当前步：三维场景 + 右侧轨迹 + 控件状态。 */
  function draw() {
    if (!app.demo || !app.els) return;
    const step = app.steps[app.index] || {};
    const state = stateOf(app.demo, step);
    let info = {};
    if (app.renderer && app.instance) {
      try {
        info = app.renderer.render(app.instance, app.demo, step, state, app.index) || {};
      } catch (error) {
        info = {
          unavailable: true,
          caption: '场景渲染失败',
          message: '当前步骤渲染失败：' + (error && error.message ? error.message : '未知错误')
        };
      }
    }
    if (app.instance) {
      app.els.scene.style.width = (app.instance.width || 420) + 'px';
      app.els.scene.style.height = (app.instance.height || 300) + 'px';
    }
    if (info.unavailable) {
      app.els.empty.hidden = false;
      app.els.empty.textContent = info.message || info.caption || '当前快照缺少可视化字段';
      app.els.scene.classList.add('is-empty');
    } else {
      app.els.empty.hidden = true;
      app.els.scene.classList.remove('is-empty');
    }
    app.els.scene.classList.toggle('is-fallback', !!info.fallback);
    if (app.els.caption) {
      if (info.caption) {
        app.els.caption.hidden = false;
        app.els.caption.textContent = info.caption;
      } else {
        app.els.caption.hidden = true;
        app.els.caption.textContent = '';
      }
    }
    app.els.note.textContent = has(step.note) ? String(step.note) : '（本步没有文字说明）';
    app.els.step.textContent = '第 ' + (app.index + 1) + ' / ' + app.steps.length + ' 步';
    const rawState = isObj(step.state) ? step.state : legacyState(step);
    updateVariables(Object.keys(rawState).length ? rawState : state, step);
    renderLegend(state);
    updateCode(step);
    syncControls();
    applyPose();
    if (app.els.result) app.els.result.classList.toggle('done', app.index >= app.steps.length - 1);
    if (app.els.vizTag && app.demo) app.els.vizTag.textContent = 'viz · ' + app.viz;
  }

  /* ================= 播放控制 ================= */

  function stopTimer() {
    if (app.timer) {
      clearInterval(app.timer);
      app.timer = null;
    }
    app.playing = false;
    if (app.els && app.els.play) {
      app.els.play.textContent = '播放';
      app.els.play.setAttribute('aria-pressed', 'false');
      app.els.play.classList.remove('playing');
    }
  }

  function moveStep(delta) {
    if (!app.steps.length) return;
    const next = clampNum(app.index + delta, 0, app.steps.length - 1);
    if (next === app.index) return;
    app.index = next;
    draw();
  }

  function tickTimer() {
    if (!app.playing) return;
    if (app.index >= app.steps.length - 1) {
      stopTimer();
      syncControls();
      return;
    }
    app.index += 1;
    draw();
    if (app.index >= app.steps.length - 1) {
      stopTimer();
      syncControls();
    }
  }

  function togglePlay() {
    if (!app.steps.length) return;
    if (app.timer) {
      stopTimer();
      syncControls();
      return;
    }
    if (app.index >= app.steps.length - 1) app.index = 0;
    app.playing = true;
    draw();
    app.timer = setInterval(tickTimer, app.speed);
    syncControls();
  }

  function restartTimer() {
    if (!app.timer) return;
    clearInterval(app.timer);
    app.timer = setInterval(tickTimer, app.speed);
  }

  function resetAll() {
    stopTimer();
    app.index = 0;
    resetView();
    draw();
    syncControls();
  }

  /* ================= 3D 交互 ================= */

  function bindStage() {
    const stage = app.els.stage;
    if (!stage) return;
    let drag = null;
    stage.addEventListener('pointerdown', function (event) {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      drag = { x: event.clientX, y: event.clientY, angle: app.angle, tilt: app.tilt };
      try { stage.setPointerCapture(event.pointerId); } catch (ignore) { /* 部分浏览器不支持 */ }
      stage.classList.add('dragging');
    });
    stage.addEventListener('pointermove', function (event) {
      if (!drag) return;
      app.angle = drag.angle + (event.clientX - drag.x) * 0.35;
      app.tilt = clampNum(drag.tilt - (event.clientY - drag.y) * 0.3, 10, 82);
      applyPose();
    });
    function endDrag(event) {
      if (!drag) return;
      drag = null;
      stage.classList.remove('dragging');
      try { stage.releasePointerCapture(event.pointerId); } catch (ignore) { /* 忽略 */ }
    }
    stage.addEventListener('pointerup', endDrag);
    stage.addEventListener('pointercancel', endDrag);
    stage.addEventListener('wheel', function (event) {
      event.preventDefault();
      app.zoom = clampNum(app.zoom - event.deltaY * 0.0012, 0.35, 2.4);
      applyPose();
    }, { passive: false });
    stage.addEventListener('dblclick', function () { resetView(); });
    stage.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowLeft') { event.preventDefault(); stopTimer(); moveStep(-1); }
      else if (event.key === 'ArrowRight') { event.preventDefault(); stopTimer(); moveStep(1); }
      else if (event.key === ' ' || event.key === 'Spacebar') { event.preventDefault(); togglePlay(); }
      else if (event.key === 'Home') { event.preventDefault(); resetAll(); }
    });
  }

  function bindGlobal() {
    document.addEventListener('keydown', function (event) {
      if (event.defaultPrevented) return;
      const target = event.target;
      if (!target) return;
      const tag = String(target.tagName || '').toUpperCase();
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || tag === 'BUTTON' || tag === 'A' || target.isContentEditable) return;
      if (event.key === 'ArrowLeft') { event.preventDefault(); stopTimer(); moveStep(-1); }
      else if (event.key === 'ArrowRight') { event.preventDefault(); stopTimer(); moveStep(1); }
      else if (event.key === ' ' || event.key === 'Spacebar') { event.preventDefault(); togglePlay(); }
      else if (event.key === 'Home') { event.preventDefault(); resetAll(); }
    });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) stopTimer();
    });
    window.addEventListener('resize', function () {
      if (!app.instance) return;
      const previousFit = app.fitZoom;
      app.fitZoom = computeFit(app.instance.width, app.instance.height);
      if (Math.abs(app.zoom - previousFit) < 0.002) {
        app.zoom = app.fitZoom;
        applyPose();
      }
    });
    window.addEventListener('pagehide', cleanup);
    window.addEventListener('beforeunload', cleanup);
  }

  /** 页面隐藏 / 卸载时停表、中止在途请求，避免定时器泄漏。 */
  function cleanup() {
    stopTimer();
    app.requestSeq += 1;
    if (app.controller) {
      try { app.controller.abort(); } catch (ignore) { /* 忽略 */ }
      app.controller = null;
    }
  }

  /* ================= 数据加载 ================= */

  function updateUrl() {
    try {
      const query = '?question=' + encodeURIComponent(app.id) + '&sample=' + app.sample;
      if (location.search !== query) history.replaceState(null, '', location.pathname + query);
    } catch (ignore) { /* file:// 或受限环境忽略 */ }
  }

  async function ensureToken() {
    if (app.token) return app.token;
    let boot = null;
    try {
      const response = await fetch('/api/platform/bootstrap', { cache: 'no-store' });
      boot = await response.json();
    } catch (error) {
      throw { code: 'NETWORK' };
    }
    if (!boot || boot.ok === false || typeof boot.token !== 'string' || !boot.token) throw { code: 'NETWORK' };
    app.token = boot.token;
    return app.token;
  }

  function applyDemo(demo, requestedSample) {
    app.demo = demo;
    if (demo.questionId) app.id = String(demo.questionId);
    app.steps = demo.steps.slice(0, MAX_STEPS);
    app.warnings = [];
    if (demo.steps.length > MAX_STEPS) app.warnings.push('演示步骤过多，仅展示前 ' + MAX_STEPS + ' 步。');
    if (isArr(demo.warnings)) {
      demo.warnings.forEach(function (text) { if (text) app.warnings.push(String(text)); });
    }
    app.index = 0;
    const sampleIndexRaw = asNum(demo.sampleIndex);
    app.sample = sampleIndexRaw !== null ? Math.max(0, Math.round(sampleIndexRaw)) : requestedSample;
    renderShell(demo);
    buildScene(demo);
    const pose = DEFAULT_POSES[app.viz] || DEFAULT_POSES.scalar;
    app.tilt = pose.tilt;
    app.angle = pose.angle;
    app.zoom = 1;
    draw();
    app.fitZoom = computeFit(app.instance.width, app.instance.height);
    resetView();
    updateUrl();
    setBusy(false);
    syncControls();
    app.els.stage.focus({ preventScroll: true });
  }

  async function loadSample(sampleIndex) {
    stopTimer();
    app.requestSeq += 1;
    const seq = app.requestSeq;
    if (app.controller) {
      try { app.controller.abort(); } catch (ignore) { /* 忽略 */ }
    }
    app.controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const sample = Number.isInteger(sampleIndex) && sampleIndex >= 0 ? sampleIndex : 0;
    showLoading();
    try {
      const token = await ensureToken();
      if (seq !== app.requestSeq) return;
      const response = await fetch('/api/learning/space/algorithm-demo/' + encodeURIComponent(app.id) + '?sample=' + sample, {
        headers: { 'X-Xueya-Token': token },
        cache: 'no-store',
        signal: app.controller ? app.controller.signal : undefined
      });
      let payload = null;
      try { payload = await response.json(); } catch (error) { payload = null; }
      if (seq !== app.requestSeq) return;
      if (!payload) throw { code: 'BAD_JSON' };
      if (!response.ok || payload.ok === false) throw { code: payload.error || ('HTTP_' + response.status) };
      const demo = payload.demo;
      if (!isObj(demo)) throw { code: 'DEMO_EMPTY' };
      if (demo.schemaVersion !== 'demo-2') throw { code: 'DEMO_SCHEMA_OLD', detail: 'schemaVersion=' + fmt(demo.schemaVersion, 40) };
      if (!isArr(demo.steps) || demo.steps.length === 0) throw { code: 'DEMO_NO_STEPS' };
      if (demo.questionId) app.id = String(demo.questionId);
      applyDemo(demo, sample);
    } catch (error) {
      if (seq !== app.requestSeq) return;
      if (error && error.name === 'AbortError') return;
      showError(error);
    }
  }

  /* ================= 启动 ================= */

  function boot() {
    const params = new URLSearchParams(location.search);
    const question = (params.get('question') || '').trim();
    const sampleParam = asNum(params.get('sample'));
    app.sample = sampleParam !== null && sampleParam >= 0 ? Math.floor(sampleParam) : 0;
    bindGlobal();
    if (!question || !/^[A-Za-z0-9_-]+$/.test(question)) {
      showError({ code: 'QUESTION_REQUIRED' });
      return;
    }
    app.id = question;
    showLoading();
    loadSample(app.sample);
  }

  boot();
})();
