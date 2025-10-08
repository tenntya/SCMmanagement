(() => {
  const state = {
    tab: 'houchozan',
    datasets: {},
    filtered: [],
    page: 1,
    pageSize: 50,
    sort: { index: -1, dir: 1 },
    formatSpec: {},
    nameFilter: {},
    filterCollapsed: {},
    baseWidths: {},
    columnWidths: {},
    rowChecks: { short: new Set() },
    globalFilters: { classification: '' },
  };

  const qs = (sel, el) => (el ?? document).querySelector(sel);
  const qsa = (sel, el) => Array.from((el ?? document).querySelectorAll(sel));

  const WIDTH_STORAGE_KEY = 'pmTableWidths:v1';
  const DEFAULT_MIN_WIDTH = 96;
  const MAX_COL_WIDTH = 720;
  const HEADER_FONT = '600 13px "Segoe UI", "Noto Sans JP", sans-serif';
  const CELL_FONT = '13px "Segoe UI", "Noto Sans JP", sans-serif';
  const MAX_SAMPLE_ROWS = 200;
  const SHORT_CHECK_COL_WIDTH = 52;
  let measureCtx = null;

  function getMeasureContext(font) {
    if (!measureCtx) {
      const canvas = document.createElement('canvas');
      measureCtx = canvas.getContext('2d');
    }
    if (!measureCtx) return null;
    if (font) measureCtx.font = font;
    return measureCtx;
  }

  function measureTextWidth(text, font) {
    const ctx = getMeasureContext(font || CELL_FONT);
    if (!ctx) return String(text ?? '').length * 14;
    if (font) ctx.font = font;
    const lines = String(text ?? '').split(/\r?\n/);
    let max = 0;
    for (const line of lines) {
      const metrics = ctx.measureText(line || ' ');
      max = Math.max(max, metrics.width);
    }
    return max;
  }

  function clampWidth(px) {
    if (!Number.isFinite(px)) return DEFAULT_MIN_WIDTH;
    return Math.min(MAX_COL_WIDTH, Math.max(DEFAULT_MIN_WIDTH, Math.ceil(px)));
  }

  function parseNumericValue(val) {
    if (val === null || val === undefined) return NaN;
    const cleaned = String(val).replace(/[\s,]/g, '');
    if (!cleaned) return NaN;
    const num = Number(cleaned);
    return Number.isFinite(num) ? num : NaN;
  }


  // One-shot force flag for API data reload
  try {
    const _origFetch = window.fetch.bind(window);
    window.fetch = (url, opts) => {
      try {
        if (window._pmForceOnce && typeof url === 'string' && url.startsWith('/api/data/')) {
          const sep = url.includes('?') ? '&' : '?';
          url = url + sep + 'force=1';
          window._pmForceOnce = false;
        }
      } catch {}
      return _origFetch(url, opts);
    };
  } catch {}

  function init() {
    try {
      const saved = localStorage.getItem(WIDTH_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed === 'object') state.columnWidths = parsed;
      }
    } catch {}
    // If launched by the app, enable auto-quit on window close
    try {
      const usp = new URLSearchParams(location.search);
      if (usp.get('launched') === '1') {
        window._pmAutoQuit = true;
        let sent = false;
        const tryQuit = () => {
          if (!window._pmAutoQuit || sent) return;
          sent = true;
          try { navigator.sendBeacon('/api/quit', 'bye'); } catch {}
        };
        window.addEventListener('pagehide', tryQuit);
        window.addEventListener('beforeunload', tryQuit);
      }
    } catch {}
    // 動的に「当日検収確認」タブを追加
    const tabsSeg = qs('.tabs-segmented');
    const hzBtn = qs('.tab[data-tab="houchozan"]');
    if (tabsSeg && hzBtn && !qs('.tab[data-tab="houchozan_today"]')) {
      const btn = document.createElement('button');
      btn.className = 'tab';
      btn.dataset.tab = 'houchozan_today';
      btn.textContent = '当日検収確認';
      hzBtn.after(btn);
    }
    qsa('.tab').forEach(b => b.addEventListener('click', () => setActiveTab(b.dataset.tab)));
    qs('#refreshBtn')?.addEventListener('click', () => { window._pmForceOnce = true; loadData(state.tab); });
    qs('#tableAutoFit')?.addEventListener('click', () => autoFitActiveTab());
    qs('#tableResetWidths')?.addEventListener('click', () => { resetColumnWidths(state.tab); renderTable(); });
    const prodTgl = qs('#prodToggle');
    if (prodTgl) prodTgl.addEventListener('change', () => { window._pmForceOnce = true; loadData(state.tab); });
    qs('#prevPage')?.addEventListener('click', () => { if (state.page>1){ state.page--; renderTable(); }});
    qs('#nextPage')?.addEventListener('click', () => { const max = Math.max(1, Math.ceil(state.filtered.length/state.pageSize)); if (state.page<max){ state.page++; renderTable(); }});
    qsa('input[name="logic"]').forEach(el => el.addEventListener('change', () => { applyFilters(); renderTable(); }));
    qsa('input[type="text"][data-col], select[data-col], input[type="date"][data-col]').forEach(el => {
      if (el.classList.contains('edit-cell')) return;
      el.addEventListener('input', () => { applyFilters(); renderTable(); });
      el.addEventListener('change', () => { applyFilters(); renderTable(); });
    });
    const nameSelects = [
      { id: '#hzNameSelect', tab: 'houchozan' },
      { id: '#hzNameSelect', tab: 'houchozan_today' },
      { id: '#tiNameSelect', tab: 'text_items' },
      { id: '#shortNameSelect', tab: 'short' },
    ];
    nameSelects.forEach(({ id, tab }) => {
      const el = qs(id);
      if (el) {
        el.addEventListener('change', () => {
          state.nameFilter[tab] = el.value || '';
          if (state.tab === tab) { applyFilters(); renderTable(); renderDates(); }
        });
      }
    });
    const globalKindSelect = qs('#globalKindSelect');
    if (globalKindSelect) {
      globalKindSelect.value = state.globalFilters.classification || '';
      globalKindSelect.addEventListener('change', () => {
        state.globalFilters.classification = globalKindSelect.value || '';
        applyFilters();
        renderTable();
        renderNameOptions(state.tab);
      });
    }

    // restore collapsed state
    try { const saved = localStorage.getItem('filterCollapsed'); if (saved) state.filterCollapsed = JSON.parse(saved) || {}; } catch {}
    setupFilterCards();
    setActiveTab('houchozan');
  }

  function setupFilterCards() {
    qsa('.filter-card').forEach(card => {
      const id = card.id || '';
      const tab = id.replace(/^filters-card-/, '') || 'houchozan';
      const title = qs('.card-title', card);
      if (title && !qs('.chevron', title)) {
        const chev = document.createElement('span');
        chev.className = 'chevron';
        chev.textContent = '▾';
        title.appendChild(chev);
      }
      if (state.filterCollapsed[tab] === undefined) state.filterCollapsed[tab] = true; // default: collapsed
      const applyCollapsed = () => {
        const isCollapsed = !!state.filterCollapsed[tab];
        card.classList.toggle('collapsed', isCollapsed);
        const btn = qs('.toggle-filters', card);
        if (btn) { btn.textContent = isCollapsed ? 'フィルターを表示' : 'フィルターを隠す'; btn.setAttribute('aria-expanded', String(!isCollapsed)); }
      };
      title?.addEventListener('click', () => {
        state.filterCollapsed[tab] = !state.filterCollapsed[tab];
        try { localStorage.setItem('filterCollapsed', JSON.stringify(state.filterCollapsed)); } catch {}
        applyCollapsed();
      });
      // Optional: also support an injected button if present
      qs('.toggle-filters', card)?.addEventListener('click', () => {
        state.filterCollapsed[tab] = !state.filterCollapsed[tab];
        try { localStorage.setItem('filterCollapsed', JSON.stringify(state.filterCollapsed)); } catch {}
        applyCollapsed();
      });
      applyCollapsed();
    });
  }

  function setActiveTab(tab) {
    state.tab = tab;
    qsa('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    qsa('.filter-card').forEach(c => c.classList.add('hidden'));
    const tabForCard = (tab === 'houchozan_today') ? 'houchozan' : tab;
    const card = qs(`#filters-card-${tabForCard}`);
    card?.classList.remove('hidden');
    if (card) {
      // reflect saved collapsed state for this tab
      const isCollapsed = state.filterCollapsed[tab] === undefined ? true : !!state.filterCollapsed[tab];
      card.classList.toggle('collapsed', isCollapsed);
      // 当日検収確認はフィルターを初期化（残留条件で絞り過ぎるのを防止）
      if (tab === 'houchozan_today') {
        qsa('input[type="text"][data-col], input[type="date"][data-col], select[data-col]', card).forEach(el => {
          if (el.tagName === 'SELECT') { el.value = ''; }
          else { el.value = ''; }
        });
        state.nameFilter[tab] = '';
        const sel = qs('#hzNameSelect');
        if (sel) sel.value = '';
      }
    }
    // Avoid re-fetching on every tab switch if cached
    if (state.datasets[tab]) {
      applyFilters();
      renderTable();
      renderDates();
      renderNameOptions(tab);
    } else {
      loadData(tab);
    }
  }

  async function loadData(tab) {
    try {
      // サンプルモード廃止: 常に本番データ参照
      const res = await fetch(`/api/data/${tab}`);
      if (!res.ok) {
        try { console.error('API load failed', tab, res.status, res.url); } catch {}
        renderError(`HTTP ${res.status} で取得に失敗: ${res.url || ('/api/data/' + tab)}`);
        return;
      }
      const data = await res.json();
      if (data.error) return renderError(data.error);
      state.datasets[tab] = data;
      if (tab === 'short') {
        const initial = Array.isArray(data.checkedKeys) ? data.checkedKeys.map(v => String(v ?? '')) : [];
        state.rowChecks.short = new Set(initial);
        data.checkedKeys = initial;
      }
      const spec = buildFormatSpec(data, tab);
      state.formatSpec[tab] = spec;
      state.baseWidths[tab] = buildWidthSpec(data, spec);
      alignColumnWidths(tab, data.headers || [], spec);
      persistColumnWidths();
      applyFilters();
      renderTable();
      renderDates();
      renderNameOptions(tab);
    } catch (e) {
      renderError('データ取得エラー: ' + (e?.message || 'unknown'));
    }
  }

  function renderError(msg) {
    qs('#table-container').innerHTML = `<div style="padding:16px;color:#b91c1c;background:#fee2e2;border:1px solid #fecaca;border-radius:8px">エラー: ${msg}</div>`;
  }

  function buildFilterPredicates(ds) {
    let frow = qs(`#filters-${state.tab}`);
    if (!frow && state.tab === 'houchozan_today') {
      frow = qs('#filters-houchozan');
    }
    const preds = [];
    const headers = Array.isArray(ds && ds.headers) ? ds.headers : [];
    const letters = (ds && ds.letters) ? ds.letters : [];
    qsa('input[type="text"][data-col], select[data-col]', frow).forEach(el => {
      const col = el.dataset.col;
      const val = (el.value || '').trim();
      if (!val) return;
      if (col === '__kind__') {
        // 品目種別は後段の専用ロジックで処理する
        return;
      }
      if (col && col.length <= 3 && /^[A-Z]+$/.test(col)) {
        const idx = letters.indexOf(col);
        if (idx >= 0) preds.push((r) => String(r[idx] || '').includes(val));
        return;
      }
      preds.push((r, headers) => {
        const idx = headerIndex(headers, col);
        return idx >= 0 && String(r[idx] || '').includes(val);
      });
    });
    // P列の期間
    const from = qs('input[data-col="P"][data-date="from"]', frow)?.value;
    const to = qs('input[data-col="P"][data-date="to"]', frow)?.value;
    if (from || to) {
      const idx = letters.indexOf('P');
      const fromD = from ? new Date(from) : null;
      const toD = to ? new Date(to) : null;
      preds.push((r) => {
        if (idx < 0) return true;
        const d = parseDateGuess2(r[idx]);
        if (!d) return false;
        if (fromD && d < fromD) return false;
        if (toD && d > toD) return false;
        return true;
      });
    }
    // 名称フィルタ
    const nameVal = state.nameFilter[state.tab] || '';
    const nameLetter = (state.datasets[state.tab] || {}).nameLetter || 'C';
    if (nameVal) {
      const idx2 = letters.indexOf(nameLetter);
      if (idx2 >= 0) preds.push((r) => String(r[idx2] || '').includes(nameVal));
    }
    // 品目種別フィルタ (発注残のみ使用)
    if (state.tab === 'houchozan' || state.tab === 'houchozan_today') {
      const kindSel = qs('select[data-col="__kind__"]', frow);
      const kval = (kindSel?.value || '').trim();
      if (kval) {
        let codeIdx = letters.indexOf('D');
        if (codeIdx < 0) codeIdx = letters.indexOf('C');
        if (codeIdx < 0) codeIdx = letters.indexOf('B');
        if (codeIdx < 0) codeIdx = letters.indexOf('A');
        preds.push((r) => classifyKind(String(r[codeIdx] || '')) === kval);
      }
    }
    const globalKind = (state.globalFilters?.classification || '').trim().toUpperCase();
    if (globalKind) {
      const idxKind = headerIndex(headers, '分類');
      if (idxKind >= 0) {
        preds.push((r) => String(r[idxKind] || '').trim().toUpperCase() === globalKind);
      }
    }
    return preds;
  }

  function applyFilters() {
    const ds = state.datasets[state.tab];
    if (!ds) return;
    const rows = ds.rows || [];
    const headers = ds.headers || [];
    const letters = ds.letters || [];
    const preds = buildFilterPredicates(ds);
    const useAnd = (qs('input[name="logic"]:checked')?.value || 'AND') === 'AND';
    state.filtered = rows.filter(r => {
      if (!preds.length) return true;
      if (useAnd) return preds.every(p => p(r, headers, letters));
      return preds.some(p => p(r, headers, letters));
    });
    state.page = 1;
    state.sort = { index: -1, dir: 1 };
  }

  function headerIndex(headers, token) {
    const t = String(token || '').trim();
    if (!t) return -1;
    let idx = headers.indexOf(t);
    if (idx >= 0) return idx;
    // 一部文字化けしても最短一致
    idx = headers.findIndex(h => String(h||'').includes(t));
    return idx;
  }

  function classifyKind(code) {
    const t = String(code || '').trim();
    if (!t) return 'テキスト品';
    if (t.startsWith('W-')) return '消耗品';
    return '通常';
  }

  function ensureRowCheckSet(tab) {
    if (!state.rowChecks[tab]) state.rowChecks[tab] = new Set();
    return state.rowChecks[tab];
  }

  function renderTable() {
    const ds = state.datasets[state.tab];
    if (!ds) return;
    const { headers } = ds;
    const spec = state.formatSpec[state.tab] || { dates: new Set(), ints: new Set() };
    const cont = qs('#table-container');
    const pageStart = (state.page - 1) * state.pageSize;
    const pageEnd = pageStart + state.pageSize;
    const pageRows = state.filtered.slice(pageStart, pageEnd);
    const isShort = state.tab === 'short';
    const keyIdx = (ds.letters || []).indexOf(ds.keyLetter || '');
    let checkboxIdx = -1;
    if (isShort) {
      checkboxIdx = headers.findIndex(h => String(h || '').includes('備') || String(h || '').includes('自由'));
      if (checkboxIdx < 0) checkboxIdx = headers.length;
    }
    const checkSet = isShort ? ensureRowCheckSet('short') : null;
    const widths = getColumnWidths(headers, spec);
    let totalWidth = widths.reduce((sum, w) => sum + w, 0);
    if (checkboxIdx >= 0) totalWidth += SHORT_CHECK_COL_WIDTH;
    const headerCells = [];
    const colParts = [];
    headers.forEach((h, idx) => {
      if (checkboxIdx === idx) {
        headerCells.push('<th class="row-check-header">チェック</th>');
        colParts.push(`<col class="short-check-col" style="width:${SHORT_CHECK_COL_WIDTH}px">`);
      }
      headerCells.push(`<th class="sortable" data-idx="${idx}">${h}</th>`);
      colParts.push(`<col style="width:${widths[idx]}px">`);
    });
    if (checkboxIdx === headers.length) {
      headerCells.push('<th class="row-check-header">チェック</th>');
      colParts.push(`<col class="short-check-col" style="width:${SHORT_CHECK_COL_WIDTH}px">`);
    }
    const rowsHtml = pageRows.map((row, rowOffset) => {
      const rawKey = keyIdx >= 0 ? row[keyIdx] : `${pageStart + rowOffset}`;
      const key = String(rawKey ?? '');
      const checked = Boolean(isShort && checkSet?.has(key));
      const cells = [];
      headers.forEach((header, idx) => {
        if (checkboxIdx === idx) {
          cells.push(shortCheckboxCellHtml(key, checked));
        }
        cells.push(cellHtml(idx, header, row[idx], row, spec));
      });
      if (checkboxIdx === headers.length) {
        cells.push(shortCheckboxCellHtml(key, checked));
      }
      const rowClass = checked ? ' class="row-checked"' : '';
      return `<tr${rowClass} data-key="${escapeHtml(key)}">${cells.join('')}</tr>`;
    }).join('');
    const targetWidth = Math.max(totalWidth, cont.clientWidth || 0);
    cont.innerHTML = `<table style="min-width:100%; width:${targetWidth}px"><colgroup>${colParts.join('')}</colgroup><thead><tr>${headerCells.join('')}</tr></thead><tbody>${rowsHtml}</tbody></table>`;
    const tableEl = qs('table', cont);
    setupColumnResizers(tableEl, widths, headers, spec);
    qsa('th.sortable', cont).forEach(th => th.addEventListener('click', () => {
      const idx = Number(th.dataset.idx);
      const dir = state.sort.index === idx ? -state.sort.dir : 1;
      sortBy(idx, dir);
      renderTable();
    }));
    qs('#pageInfo').textContent = `${state.page} / ${Math.max(1, Math.ceil(state.filtered.length / state.pageSize))} (${state.filtered.length}件)`;
    cont.querySelectorAll('input.edit-cell')?.forEach(input => input.addEventListener('change', onEditChange));
    if (isShort) {
      cont.querySelectorAll('input.short-check').forEach(input => input.addEventListener('change', onShortCheckToggle));
    }
  }  function shortCheckboxCellHtml(key, checked) {
    const flag = checked ? ' checked' : '';
    return `<td class="row-check-cell"><input type="checkbox" class="short-check" data-key="${escapeHtml(key)}" aria-label="チェック" title="チェック"${flag}></td>`;
  }



  function minWidthFor(header, idx, spec) {
    const h = String(header || '');
    if (!h) return DEFAULT_MIN_WIDTH;
    if (h.includes('自由') || h.includes('備考') || h.includes('メモ')) return 240;
    if (h.includes('名称')) return 150;
    if (spec && spec.ints && spec.ints.has(idx)) return Math.max(DEFAULT_MIN_WIDTH, 90);
    if (spec && spec.dates && spec.dates.has(idx)) return Math.max(DEFAULT_MIN_WIDTH, 120);
    if (h.includes('日')) return Math.max(DEFAULT_MIN_WIDTH, 120);
    return Math.max(DEFAULT_MIN_WIDTH, 110);
  }

function cellHtml(i, header, val, row, spec) {
    const normalizedHeader = String(header || '').trim();
    const ds = state.datasets[state.tab] || {};
    const dsHeaders = Array.isArray(ds.headers) ? ds.headers : [];
    const rawHeader = String(dsHeaders[i] || '').trim();
    const heuristics = `${normalizedHeader}|${rawHeader}`;
    const includesOne = (tokens) => tokens.some(token => token && heuristics.includes(token));

    let canEdit = false;
    switch (state.tab) {
      case 'short':
        canEdit = includesOne(['自由', '備']);
        break;
      case 'houchozan':
      case 'text_items':
      case 'reschedule':
        canEdit = includesOne(['自由']);
        break;
      case 'houchozan_today':
        canEdit = includesOne(['自由']);
        if (normalizedHeader.includes('自由')) canEdit = true;
        break;
      default:
        canEdit = false;
    }

    if (state.tab === 'short' && !canEdit) {
      const isLastColumn = i === row.length - 1;
      if (isLastColumn) {
        canEdit = true;
      }
    }

    if (canEdit) {
      const esc = (String(val || '')).replaceAll('&', '&amp;').replaceAll('<', '&lt;');
      return `<td><input class="edit-cell" type="text" value="${esc}" data-col="${header}" data-idx="${i}" /></td>`;
    }
    const display = formatCell(i, header, val, spec);
    const title = String(val ?? '');
    return `<td title="${escapeHtml(title)}">${display}</td>`;
  }

  function onEditChange(e) {
    const input = e.target;
    const ds = state.datasets[state.tab];
    if (!ds) return;
    const keyIdx = (ds.letters || []).indexOf(ds.keyLetter || '');
    const rowIndex = (state.page - 1) * state.pageSize + Array.from(input.closest('tr').parentNode.children).indexOf(input.closest('tr'));
    const row = state.filtered[rowIndex];
    const key = keyIdx >= 0 && row ? String(row[keyIdx] || '') : '';
    const colIdx = Number(input.dataset.idx);
    const value = input.value || '';
    if (row && Number.isFinite(colIdx)) {
      row[colIdx] = value;
      if (Array.isArray(ds.rows)) {
        const dsRowIndex = ds.rows.indexOf(row);
        if (dsRowIndex >= 0) ds.rows[dsRowIndex][colIdx] = value;
      }
    }
    fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tab: state.tab, key, field: input.dataset.col, value }) }).catch(()=>{});
  }
  function onShortCheckToggle(e) {
    const input = e.target;
    if (!input || input.type !== 'checkbox') return;
    const key = input.dataset.key || '';
    if (!key) return;
    const checked = Boolean(input.checked);
    const set = ensureRowCheckSet('short');
    if (checked) set.add(key); else set.delete(key);
    const row = input.closest('tr');
    if (row) row.classList.toggle('row-checked', checked);
    if (state.datasets.short) {
      state.datasets.short.checkedKeys = Array.from(set);
    }
    fetch('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tab: 'short', key, field: '__checked__', value: checked })
    }).catch(() => {});
  }


  function sortBy(idx, dir) {
    state.sort = { index: idx, dir };
    const spec = state.formatSpec[state.tab] || { dates: new Set(), ints: new Set() };
    state.filtered.sort((a, b) => compareBySpec(a[idx], b[idx], spec, idx) * dir);
  }

  function buildFormatSpec(ds) {
    const headers = Array.isArray(ds.headers) ? ds.headers : [];
    const rows = Array.isArray(ds.rows) ? ds.rows : [];
    const sample = rows.slice(0, MAX_SAMPLE_ROWS);
    const dates = new Set();
    const ints = new Set();
    headers.forEach((h, i) => {
      const label = String(h || '');
      if (label.includes('日') || /Date/i.test(label)) {
        dates.add(i);
      }
      const normalized = label.replace(/\s+/g, '').toLowerCase();
      const isQuantityHeader = label.includes('数量') || normalized.includes('qty');
      if (isQuantityHeader) {
        const hasNumeric = sample.some((row) => {
          if (!row) return false;
          const num = parseNumericValue(row[i]);
          return Number.isFinite(num);
        });
        if (hasNumeric) ints.add(i);
      }
    });
    return { dates, ints };
  }

  function buildWidthSpec(ds, spec, sampleRows) {
    const headers = ds.headers || [];
    const rows = Array.isArray(sampleRows) && sampleRows.length ? sampleRows : (ds.rows || []);
    const defaultSpec = spec || { dates: new Set(), ints: new Set() };
    const sample = rows.slice(0, MAX_SAMPLE_ROWS);
    return headers.map((h, idx) => {
      const headerWidth = measureTextWidth(h, HEADER_FONT);
      let maxWidth = headerWidth;
      for (let i = 0; i < sample.length; i += 1) {
        const row = sample[i];
        if (!row) continue;
        maxWidth = Math.max(maxWidth, measureTextWidth(row[idx], CELL_FONT));
      }
      const padded = maxWidth + 28;
      const min = minWidthFor(h, idx, defaultSpec);
      return clampWidth(Math.max(min, padded));
    });
  }

  function ensureBaseWidths(tab, headers, spec) {
    if (!headers.length) return;
    if (!state.baseWidths[tab] || state.baseWidths[tab].length !== headers.length) {
      const ds = state.datasets[tab];
      if (ds) {
        state.baseWidths[tab] = buildWidthSpec(ds, spec);
      } else {
        state.baseWidths[tab] = headers.map((h, idx) => minWidthFor(h, idx, spec));
      }
    }
  }

  function alignColumnWidths(tab, headers, spec) {
    if (!headers.length) return;
    ensureBaseWidths(tab, headers, spec);
    const base = state.baseWidths[tab] || headers.map((h, idx) => minWidthFor(h, idx, spec));
    const stored = Array.isArray(state.columnWidths[tab]) ? state.columnWidths[tab] : [];
    const next = headers.map((h, idx) => {
      const min = minWidthFor(h, idx, spec);
      const fallback = base[idx] ?? min;
      const candidate = Number(stored[idx]);
      const chosen = Number.isFinite(candidate) && candidate > 0 ? candidate : fallback;
      return clampWidth(Math.max(min, chosen));
    });
    state.columnWidths[tab] = next;
  }

  function getColumnWidths(headers, spec) {
    const tab = state.tab;
    alignColumnWidths(tab, headers, spec);
    return (state.columnWidths[tab] || []).slice();
  }

  function persistColumnWidths() {
    try {
      localStorage.setItem(WIDTH_STORAGE_KEY, JSON.stringify(state.columnWidths));
    } catch {}
  }

  function updateTableWidth(tableEl, widths) {
    if (!tableEl || !widths || !widths.length) return;
    const container = tableEl.parentElement;
    const total = widths.reduce((sum, w) => sum + w, 0);
    const target = Math.max(total, container?.clientWidth || 0);
    tableEl.style.width = `${target}px`;
  }

  function setupColumnResizers(tableEl, widths, headers, spec) {
    if (!tableEl) return;
    const tab = state.tab;
    const cols = qsa('col', tableEl);
    const ths = qsa('thead th', tableEl);
    ths.forEach((th, idx) => {
      const dataIdx = Number(th.dataset.idx);
      if (!Number.isFinite(dataIdx)) {
        th.classList.add('no-resize');
        return;
      }
      th.classList.add('resizable');
      const handle = document.createElement('span');
      handle.className = 'col-resizer';
      th.appendChild(handle);
      let startX = 0;
      let startWidth = widths[dataIdx] || minWidthFor(headers[dataIdx], dataIdx, spec);
      const min = () => minWidthFor(headers[dataIdx], dataIdx, spec);
      const onMove = (ev) => {
        const delta = ev.clientX - startX;
        const nextWidth = clampWidth(Math.max(min(), startWidth + delta));
        if (cols[idx]) cols[idx].style.width = `${nextWidth}px`;
        widths[dataIdx] = nextWidth;
        th.style.width = `${nextWidth}px`;
        qsa(`tbody td:nth-child(${idx + 1})`, tableEl).forEach(td => {
          td.style.width = `${nextWidth}px`;
        });
        updateTableWidth(tableEl, widths);
      };
      const onUp = () => {
        handle.classList.remove('active');
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        state.columnWidths[tab] = widths.slice();
        persistColumnWidths();
      };
      handle.addEventListener('mousedown', (ev) => {
        ev.preventDefault();
        startX = ev.clientX;
        startWidth = widths[dataIdx] || min();
        handle.classList.add('active');
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      });
      handle.addEventListener('dblclick', (ev) => {
        ev.preventDefault();
        ensureBaseWidths(tab, headers, spec);
        const base = state.baseWidths[tab] || [];
        const baseWidth = base[dataIdx] ?? min();
        widths[dataIdx] = clampWidth(Math.max(min(), baseWidth));
        if (cols[idx]) cols[idx].style.width = `${widths[dataIdx]}px`;
        th.style.width = `${widths[dataIdx]}px`;
        qsa(`tbody td:nth-child(${idx + 1})`, tableEl).forEach(td => {
          td.style.width = `${widths[dataIdx]}px`;
        });
        updateTableWidth(tableEl, widths);
        state.columnWidths[tab] = widths.slice();
        persistColumnWidths();
      });
    });
    updateTableWidth(tableEl, widths);
    state.columnWidths[tab] = widths.slice();
  }


  function autoFitActiveTab() {
    const tab = state.tab;
    const ds = state.datasets[tab];
    if (!ds) return;
    const spec = state.formatSpec[tab] || { dates: new Set(), ints: new Set() };
    const rows = state.filtered.length ? state.filtered : (ds.rows || []);
    const measureSource = { headers: ds.headers || [], rows };
    state.baseWidths[tab] = buildWidthSpec(measureSource, spec, rows);
    state.columnWidths[tab] = (state.baseWidths[tab] || []).slice();
    persistColumnWidths();
    renderTable();
  }

  function resetColumnWidths(tab) {
    const ds = state.datasets[tab];
    if (!ds) return;
    const spec = state.formatSpec[tab] || { dates: new Set(), ints: new Set() };
    ensureBaseWidths(tab, ds.headers || [], spec);
    state.columnWidths[tab] = (state.baseWidths[tab] || []).slice();
    persistColumnWidths();
  }


  function formatCell(i, header, val, spec) {
    const raw = val ?? '';
    const v = String(raw ?? '');
    if (spec?.ints?.has(i)) {
      const num = parseNumericValue(raw);
      if (Number.isFinite(num)) {
        const whole = Math.trunc(num);
        return escapeHtml(whole.toLocaleString('ja-JP'));
      }
      return escapeHtml(v).replaceAll('\n', '<br>');
    }
    return escapeHtml(v).replaceAll('\n', '<br>');
  }

  function compareBySpec(x, y, spec, idx) {
    const sx = x ?? '';
    const sy = y ?? '';
    if (spec.ints?.has(idx)) { const nx = Number(String(sx).replace(/,/g,''))||0; const ny = Number(String(sy).replace(/,/g,''))||0; return nx - ny; }
    if (spec.dates?.has(idx)) { const dx = parseDateGuess2(sx)?.getTime()||0; const dy = parseDateGuess2(sy)?.getTime()||0; return dx - dy; }
    return String(sx).localeCompare(String(sy), 'ja');
  }

  // Robust date parser supporting YYYYMMDD, YYYY/MM/DD, YYYY-MM-DD and Japanese date-like strings
  function parseDateGuess2(s) {
    const t = String(s||'').trim();
    if (!t) return null;
    if (/^\d{8}$/.test(t)) {
      const y = Number(t.slice(0,4));
      const m = Number(t.slice(4,6));
      const d = Number(t.slice(6,8));
      const dt = new Date(y, m-1, d);
      return (dt && dt.getFullYear()===y && (dt.getMonth()+1)===m && dt.getDate()===d) ? dt : null;
    }
    let m1 = t.match(/^(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})$/);
    if (m1) {
      const y = Number(m1[1]), m = Number(m1[2]), d = Number(m1[3]);
      const dt = new Date(y, m-1, d);
      return (dt && dt.getFullYear()===y && (dt.getMonth()+1)===m && dt.getDate()===d) ? dt : null;
    }
    m1 = t.match(/^(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
    if (m1) {
      const y = Number(m1[1]), m = Number(m1[2]), d = Number(m1[3]);
      const dt = new Date(y, m-1, d);
      return (dt && dt.getFullYear()===y && (dt.getMonth()+1)===m && dt.getDate()===d) ? dt : null;
    }
    const parsed = Date.parse(t);
    return isNaN(parsed) ? null : new Date(parsed);
  }

  function renderNameOptions(tab) {
    const selectId = (tab === 'houchozan' || tab === 'houchozan_today') ? '#hzNameSelect' : (tab === 'text_items' ? '#tiNameSelect' : (tab === 'short' ? '#shortNameSelect' : null));
    if (!selectId) return;
    const sel = qs(selectId);
    if (!sel) return;
    const ds = state.datasets[tab];
    if (!ds) { sel.innerHTML = ''; return; }
    const letters = ds.letters || [];
    const headers = Array.isArray(ds.headers) ? ds.headers : [];
    const nameLetter = ds.nameLetter || 'C';
    const idx = letters.indexOf(nameLetter);
    if (idx < 0) { sel.innerHTML = ''; return; }
    const rows = Array.isArray(ds.rows) ? ds.rows : [];
    const globalKind = (state.globalFilters?.classification || '').trim().toUpperCase();
    let sourceRows = rows;
    if (globalKind) {
      const idxKind = headerIndex(headers, '分類');
      if (idxKind >= 0) {
        sourceRows = sourceRows.filter(r => String(r[idxKind] || '').trim().toUpperCase() === globalKind);
      }
    }
    const uniq = new Set(sourceRows.map(r => String(r[idx] || '').trim()));
    const options = ['<option value="">(指定なし)</option>'].concat(
      Array.from(uniq)
        .filter(Boolean)
        .slice(0, 2000)
        .map((v) => '<option value="' + escapeHtml(v) + '">' + escapeHtml(v) + '</option>')
    );
    sel.innerHTML = options.join('');
    const cur = state.nameFilter[tab] || '';
    sel.value = cur;
    if (sel.value !== cur) {
      sel.value = '';
      state.nameFilter[tab] = '';
    }
  }

  function renderDates() {
    const ds = state.datasets[state.tab];
    const el = qs('#dataDates');
    if (!ds || !el) return;
    el.innerHTML = (ds.sourceDates || []).map(d => `<span class="badge">${d}</span>`).join('');
  }

  function escapeHtml(s) {
    return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
  }

  // 上書き: 自由入力/備考カラムは判定をヘッダの語で行い、
  // houchozan_today でも編集可能にする
    document.addEventListener('DOMContentLoaded', init);
})();
