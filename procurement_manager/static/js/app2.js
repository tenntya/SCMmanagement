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
  };

  const qs = (sel, el) => (el ?? document).querySelector(sel);
  const qsa = (sel, el) => Array.from((el ?? document).querySelectorAll(sel));

  function init() {
    // 動的に「当日発注残管理」タブを追加
    const tabsSeg = qs('.tabs-segmented');
    const hzBtn = qs('.tab[data-tab="houchozan"]');
    if (tabsSeg && hzBtn && !qs('.tab[data-tab="houchozan_today"]')) {
      const btn = document.createElement('button');
      btn.className = 'tab';
      btn.dataset.tab = 'houchozan_today';
      btn.textContent = '当日発注残管理';
      hzBtn.after(btn);
    }
    qsa('.tab').forEach(b => b.addEventListener('click', () => setActiveTab(b.dataset.tab)));
    qs('#refreshBtn')?.addEventListener('click', () => loadData(state.tab));
    const prodTgl = qs('#prodToggle');
    if (prodTgl) prodTgl.addEventListener('change', () => loadData(state.tab));
    qs('#prevPage')?.addEventListener('click', () => { if (state.page>1){ state.page--; renderTable(); }});
    qs('#nextPage')?.addEventListener('click', () => { const max = Math.max(1, Math.ceil(state.filtered.length/state.pageSize)); if (state.page<max){ state.page++; renderTable(); }});
    qsa('input[name="logic"]').forEach(el => el.addEventListener('change', () => { applyFilters(); renderTable(); }));
    qsa('input[type="text"][data-col], select[data-col], input[type="date"][data-col]').forEach(el => {
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
      // 当日発注残管理はフィルターを初期化（残留条件で絞り過ぎるのを防止）
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
    loadData(tab);
  }

  async function loadData(tab) {
    try {
      // サンプルモード廃止: 常に本番データ参照
      const res = await fetch(`/api/data/${tab}`);
      const data = await res.json();
      if (data.error) return renderError(data.error);
      state.datasets[tab] = data;
      state.formatSpec[tab] = buildFormatSpec(data, tab);
      state.widthSpec = buildWidthSpec(data, tab);
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

  function renderTable() {
    const ds = state.datasets[state.tab];
    if (!ds) return;
    const { headers } = ds;
    const spec = state.formatSpec[state.tab] || { dates: new Set(), ints: new Set() };
    const cont = qs('#table-container');
    const start = (state.page - 1) * state.pageSize;
    const end = start + state.pageSize;
    const pageRows = state.filtered.slice(start, end);
    const ths = headers.map((h, i) => `<th class="sortable" data-idx="${i}">${h}</th>`).join('');
    const rowsHtml = pageRows.map(r => `<tr>${r.map((v, i) => cellHtml(i, headers[i], v, r, spec)).join('')}</tr>`).join('');
    const baseWidths = (state.widthSpec || []).slice();
    const avail = Math.max(0, cont.clientWidth || cont.getBoundingClientRect().width || 0);
    const finalWidths = shrinkToFit(baseWidths, headers, spec, avail);
    const colgroup = finalWidths.map(w => `<col style="width:${w}px">`).join('');
    cont.innerHTML = `<table><colgroup>${colgroup}</colgroup><thead><tr>${ths}</tr></thead><tbody>${rowsHtml}</tbody></table>`;
    qsa('th.sortable', cont).forEach(th => th.addEventListener('click', () => { const idx = Number(th.dataset.idx); const dir = state.sort.index === idx ? -state.sort.dir : 1; sortBy(idx, dir); renderTable(); }));
    qs('#pageInfo').textContent = `${state.page} / ${Math.max(1, Math.ceil(state.filtered.length / state.pageSize))} (${state.filtered.length}件)`;
    cont.querySelectorAll('input.edit-cell')?.forEach(input => input.addEventListener('change', onEditChange));
  }

  function shrinkToFit(widths, headers, spec, avail) {
    if (!widths || !widths.length || !avail) return widths || [];
    const total = widths.reduce((a,b)=>a+b,0);
    if (total === 0) return widths;
    if (total > avail) {
      const mins = widths.map((w, i) => minWidthFor(headers[i], i, spec));
      const ratio = avail / total;
      let w2 = widths.map((w, i) => Math.max(mins[i], Math.floor(w * ratio)));
      let sum = w2.reduce((a,b)=>a+b,0);
      if (sum <= avail) return w2;
      let guard = 0;
      while (sum > avail && guard < 8) {
        guard++;
        const over = sum - avail;
        const flexes = w2.map((w, i) => Math.max(0, w - mins[i]));
        const flexTotal = flexes.reduce((a,b)=>a+b,0);
        if (flexTotal <= 0) break;
        w2 = w2.map((w, i) => { if (flexes[i] <= 0) return w; const dec = Math.floor(over * (flexes[i] / flexTotal)); return Math.max(mins[i], w - dec); });
        sum = w2.reduce((a,b)=>a+b,0);
      }
      return w2;
    }
    const ratio = avail / total;
    let grown = widths.map(w => Math.floor(w * ratio));
    let diff = avail - grown.reduce((a,b)=>a+b,0);
    let i = 0;
    while (diff > 0 && i < grown.length) { grown[i] += 1; diff -= 1; i += 1; }
    return grown;
  }

  function minWidthFor(header, idx, spec) {
    if (header === '自由入力' || header === '備考') return 240;
    if (header === '分類') return 90;
    if (header && String(header).includes('日')) return 120;
    if (spec && spec.ints && spec.ints.has(idx)) return 90;
    if (spec && spec.dates && spec.dates.has(idx)) return 120;
    return 110;
  }

  function cellHtml(i, header, val, row, spec) {
    const editTargets = { houchozan: '自由入力', text_items: '自由入力', short: '備考', reschedule: '自由入力' };
    let canEdit = header === editTargets[state.tab];
    if (state.tab === 'houchozan_today' && header === '自由入劁E') { canEdit = true; }
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
    const row = state.filtered[(state.page - 1) * state.pageSize + Array.from(input.closest('tr').parentNode.children).indexOf(input.closest('tr'))];
    const key = keyIdx >= 0 ? String(row[keyIdx] || '') : '';
    fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tab: state.tab, key, field: input.dataset.col, value: input.value || '' }) }).catch(()=>{});
  }

  function sortBy(idx, dir) {
    state.sort = { index: idx, dir };
    const spec = state.formatSpec[state.tab] || { dates: new Set(), ints: new Set() };
    state.filtered.sort((a, b) => compareBySpec(a[idx], b[idx], spec, idx) * dir);
  }

  function buildFormatSpec(ds) {
    const headers = ds.headers || [];
    const dates = new Set();
    const ints = new Set();
    headers.forEach((h, i) => { if (String(h||'').includes('日') || String(h||'').match(/Date/i)) dates.add(i); });
    return { dates, ints };
  }

  function buildWidthSpec(ds) {
    const headers = ds.headers || [];
    return headers.map((h,i)=>minWidthFor(h,i,{dates:new Set(),ints:new Set()}));
  }

  function formatCell(i, header, val, spec) {
    const v = String(val ?? '');
    if (spec && spec.ints && spec.ints.has(i)) return v.replace(/(\d)(?=(\d{3})+(?!\d))/g,'$1,');
    return escapeHtml(v).replaceAll('\n','<br>');
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
    const nameLetter = ds.nameLetter || 'C';
    const idx = letters.indexOf(nameLetter);
    if (idx < 0) { sel.innerHTML = ''; return; }
    const uniq = new Set((ds.rows || []).map(r => String(r[idx]||'')));
    const options = ['<option value="">(指定なし)</option>'].concat(Array.from(uniq).filter(Boolean).slice(0,2000).map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`));
    sel.innerHTML = options.join('');
    const cur = state.nameFilter[tab] || '';
    sel.value = cur;
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

  document.addEventListener('DOMContentLoaded', init);
})();
