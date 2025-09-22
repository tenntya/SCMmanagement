(() => {
  const state = {
    tab: 'houchozan',
    datasets: {},
    filtered: [],
    page: 1,
    pageSize: 50,
    sort: { index: -1, dir: 1 },
    formatSpec: {},
    useSample: false,
    nameFilter: {},
  };

  const qs = (sel, el=document) => el.querySelector(sel);
  const qsa = (sel, el=document) => Array.from(el.querySelectorAll(sel));

  function setActiveTab(tab) {
    state.tab = tab;
    qsa('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    // 縺・▲縺溘ｓ蜈ｨ繧ｫ繝ｼ繝・陦後ｒ髱櫁｡ｨ遉ｺ
    qsa('.filters-row').forEach(r => r.classList.add('hidden'));
    qsa('.filter-card').forEach(c => c.classList.add('hidden'));
    // 隧ｲ蠖薙き繝ｼ繝峨ｒ陦ｨ遉ｺ縺励√き繝ｼ繝牙・縺ｮ陦後ｒ縺吶∋縺ｦ陦ｨ遉ｺ
    const card = qs(`#filters-card-${tab}`);
    if (card) {
      card.classList.remove('hidden');
      qsa('.filters-row', card).forEach(r => r.classList.remove('hidden'));
    }
    loadData(tab);
  }

  async function loadData(tab) {
    try {
      const res = await fetch(`/api/data/${tab}?sample=${state.useSample ? 1 : 0}`);
      const data = await res.json();
      if (data.error) {
        renderError(data.error);
        return;
      }
      state.datasets[tab] = data;
      state.formatSpec[tab] = buildFormatSpec(data, tab);
      state.widthSpec = buildWidthSpec(data, tab);
      applyFilters();
      renderTable();
      renderDates();
      if (tab === 'text_items') renderTextItemNames();
      if (tab === 'short') renderShortNames();
      if (tab === 'houchozan') renderHouchozanNames();
    } catch (e) {
      renderError('データ取得エラー: ' + (e && e.message ? e.message : 'unknown'));
    }
  }

  function renderError(msg) {
    const cont = qs('#table-container');
    cont.innerHTML = `<div style="padding:16px;color:#b91c1c;background:#fee2e2;border:1px solid #fecaca;border-radius:8px">繧ｨ繝ｩ繝ｼ: ${msg}</div>`;
  }

  function applyFilters() {
    const ds = state.datasets[state.tab];
    if (!ds) return;
    const { headers, letters, rows } = ds;
    const logic = qs('input[name="logic"]:checked').value;
    const filters = buildFilterPredicates(ds);
    let arr = rows.slice();
    if (filters.length) {
      arr = arr.filter(r => {
        const checks = filters.map(fn => fn(r, headers, letters));
        return logic === 'AND' ? checks.every(Boolean) : checks.some(Boolean);
      });
    }
    state.filtered = arr;
    state.page = 1;
    if (state.sort.index >= 0) sortBy(state.sort.index, state.sort.dir);
  }

  function buildFilterPredicates(ds) {
    const frow = qs(`#filters-${state.tab}`);
    const preds = [];
    const letters = (ds && ds.letters) ? ds.letters : [];
    qsa('input[type="text"][data-col], select[data-col]', frow).forEach(el => {
      const col = el.dataset.col;
      const val = (el.value || '').trim();
      if (!val) return;
      if (col === '\u5206\u985e') {
        preds.push((r, headers) => {
          const idx = headers.indexOf('蛻・｡・);
          return idx >= 0 && String(r[idx] || '').includes(val);
        });
        return;
      }
      const idx = letters.indexOf(col);
      if (idx >= 0) {
        preds.push((r) => String(r[idx] || '').includes(val));
      }
    });
    // 譌･莉倡ｯ・峇・・蛻暦ｼ・    const from = qs('input[data-col="P"][data-date="from"]', frow)?.value;
    const to = qs('input[data-col="P"][data-date="to"]', frow)?.value;
    if (from || to) {
      const idx = letters.indexOf('P');
      const fromD = from ? new Date(from) : null;
      const toD = to ? new Date(to) : null;
      preds.push((r) => {
        if (idx < 0) return true;
        const d = parseDateGuess(r[idx]);
        if (!d) return false;
        if (fromD && d < fromD) return false;
        if (toD && d > toD) return false;
        return true;
      });
    }
        // 名称選択によるフィルター
    const nameVal = state.nameFilter[state.tab] || '';
    const nameLetter = (state.datasets[state.tab] || {}).nameLetter || 'C';
    if (nameVal) {
      const idx2 = letters.indexOf(nameLetter);
      if (idx2 >= 0) preds.push((r) => String(r[idx2] || '').includes(nameVal));
    }
    return preds;
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

    const ths = headers.map((h, i) => {
      const sortable = 'sortable';
      return `<th class="${sortable}" data-idx="${i}">${h}</th>`;
    }).join('');

    const rowsHtml = pageRows.map(r => {
      return `<tr>${r.map((v, i) => cellHtml(i, headers[i], v, r, spec)).join('')}</tr>`;
    }).join('');

    const baseWidths = (state.widthSpec || []).slice();
    const avail = Math.max(0, cont.clientWidth || cont.getBoundingClientRect().width || 0);
    const finalWidths = shrinkToFit(baseWidths, headers, spec, avail);
    const colgroup = finalWidths.map(w => `<col style="width:${w}px">`).join('');

    cont.innerHTML = `
      <table>
        <colgroup>${colgroup}</colgroup>
        <thead><tr>${ths}</tr></thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    `;

    // sort handlers
    qsa('th.sortable', cont).forEach(th => {
      th.addEventListener('click', () => {
        const idx = Number(th.dataset.idx);
        const dir = state.sort.index === idx ? -state.sort.dir : 1;
        sortBy(idx, dir);
        renderTable();
      });
    });

    // pager
    qs('#pageInfo').textContent = `${state.page} / ${Math.max(1, Math.ceil(state.filtered.length / state.pageSize))} (${state.filtered.length}莉ｶ)`;
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
        w2 = w2.map((w, i) => {
          if (flexes[i] <= 0) return w;
          const dec = Math.floor(over * (flexes[i] / flexTotal));
          return Math.max(mins[i], w - dec);
        });
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
    if (header === '閾ｪ逕ｱ蜈･蜉・ || header === '蛯呵・) return 240;
    if (header === '蛻・｡・) return 90;
    if (header && header.includes('譌･謨ｰ')) return 90;
    if (spec && spec.ints && spec.ints.has(idx)) return 90;
    if (spec && spec.dates && spec.dates.has(idx)) return 120;
    return 110;
  }

  function cellHtml(i, header, val, row, spec) {
    const editTargets = {
      'houchozan': '閾ｪ逕ｱ蜈･蜉・,
      'text_items': '閾ｪ逕ｱ蜈･蜉・,
      'short': '蛯呵・,
    };
    const canEdit = header === editTargets[state.tab];
    if (canEdit) {
      const esc = (String(val || '')).replaceAll('&', '&amp;').replaceAll('<', '&lt;');
      return `<td><input class="edit-cell" type="text" value="${esc}" data-col="${header}" data-idx="${i}" /></td>`;
    }
    const display = formatCell(i, header, val, spec);
    const title = String(val ?? '');
    return `<td title="${escapeHtml(title)}">${display}</td>`;
  }

  function sortBy(idx, dir) {
    state.sort = { index: idx, dir };
    const spec = state.formatSpec[state.tab] || { dates: new Set(), ints: new Set() };
    state.filtered.sort((a, b) => compareBySpec(a[idx], b[idx], spec, idx) * dir);
  }

  function compareBySpec(x, y, spec, idx) {
    const sx = x ?? '';
    const sy = y ?? '';
    if (spec.ints.has(idx)) {
      const nx = toInt(sx);
      const ny = toInt(sy);
      if (nx === ny) return 0;
      return nx < ny ? -1 : 1;
    }
    if (spec.dates.has(idx)) {
      const dx = toDateNum(sx);
      const dy = toDateNum(sy);
      if (dx === dy) return 0;
      return dx < dy ? -1 : 1;
    }
    if (sx === sy) return 0;
    return sx < sy ? -1 : 1;
  }

  function buildFormatSpec(ds, tab) {
    const dates = new Set();
    const ints = new Set();
    const { headers, letters, rows } = ds;
    const pIdx = letters.indexOf('P');
    if (pIdx >= 0 && (tab === 'houchozan' || tab === 'text_items')) dates.add(pIdx);
    headers.forEach((h, i) => {
      if (typeof h === 'string' && h.includes('謨ｰ驥・)) ints.add(i);
    });
    for (let i = 0; i < headers.length; i++) {
      if (ints.has(i)) continue;
      const name = headers[i];
      if (name === '閾ｪ逕ｱ蜈･蜉・ || name === '蛯呵・) continue;
      const sample = rows.slice(0, Math.min(300, rows.length)).map(r => String(r[i] ?? '').trim()).filter(Boolean);
      if (!sample.length) continue;
      const numericLike = sample.filter(s => /^-?\d+(?:[.,]\d+)?$/.test(s)).length;
      if (numericLike / sample.length >= 0.92) ints.add(i);
    }
    for (let i = 0; i < headers.length; i++) {
      const name = headers[i];
      if (name === '閾ｪ逕ｱ蜈･蜉・ || name === '蛯呵・) continue;
      if (dates.has(i)) continue;
      const sample = rows.slice(0, Math.min(300, rows.length)).map(r => String(r[i] ?? '').trim()).filter(Boolean);
      if (!sample.length) continue;
      const dateLike = sample.filter(s => (/^\d{8}$/.test(s) || /[\/-]/.test(s)) && parseDateGuess(s)).length;
      if (dateLike / sample.length >= 0.85) dates.add(i);
    }
    return { dates, ints };
  }

  function buildWidthSpec(ds, tab) {
    const { headers, letters, rows } = ds;
    const mapIF = {
      'B': 140, 'C': 160, 'D': 180, 'E': 260, 'I': 180, 'J': 180,
      'O': 150, 'P': 130, 'R': 160, 'Y': 160, 'AC': 220,
    };
    const mapShort = {
      'A': 140, 'B': 160, 'C': 180, 'D': 180, 'E': 220, 'F': 220,
      'G': 140, 'H': 140, 'I': 140, 'J': 150, 'K': 180, 'L': 180, 'M': 160,
    };
    const widths = [];
    for (let i = 0; i < headers.length; i++) {
      const letter = letters[i];
      let w = 160;
      if (tab === 'short') {
        if (letter && mapShort[letter]) w = mapShort[letter];
        if (headers[i] === '蛯呵・) w = 360;
      } else {
        if (letter && mapIF[letter]) w = mapIF[letter];
        if (headers[i] === '驕・ｻｶ譌･謨ｰ') w = 100;
        if (headers[i] === '蛻・｡・) w = 100;
        if (headers[i] === '閾ｪ逕ｱ蜈･蜉・) w = 380;
      }
      widths.push(w);
    }
    const spec = state.formatSpec[tab] || { dates: new Set(), ints: new Set() };
    const sampleCount = Math.min(200, rows.length);
    const perChar = 8;
    for (let i = 0; i < headers.length; i++) {
      let maxLen = 0;
      for (let r = 0; r < sampleCount; r++) {
        const disp = formatCell(i, headers[i], rows[r][i], spec);
        maxLen = Math.max(maxLen, String(disp).length);
      }
      const base = widths[i];
      const cap = (headers[i] === '閾ｪ逕ｱ蜈･蜉・ || headers[i] === '蛯呵・) ? 600 : 420;
      const minW = Math.max(base, 110);
      const byContent = 24 + maxLen * perChar;
      widths[i] = Math.min(cap, Math.max(minW, byContent));
    }
    return widths;
  }

  function formatCell(i, header, val, spec) {
    const s = String(val ?? '').trim();
    if (!s) return '';
    if (spec.ints.has(i)) return formatInt(s);
    if (spec.dates.has(i)) return formatDateStr(s);
    return escapeHtml(s);
  }

  function formatInt(s) {
    const v = Number(String(s).replace(/,/g, ''));
    if (!isFinite(v)) return escapeHtml(s);
    return String(Math.round(v));
  }

  function toInt(s) { const v = Number(String(s).replace(/,/g, '')); return isFinite(v) ? Math.round(v) : Number.NEGATIVE_INFINITY; }

  function toDateNum(s) {
    const d = parseDateGuess(s);
    return d ? (d.getFullYear() * 10000 + (d.getMonth()+1) * 100 + d.getDate()) : -1;
  }

  function formatDateStr(s) {
    const d = parseDateGuess(s);
    if (!d) return '';
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}/${m}/${dd}`;
  }

  function parseDateGuess(s) {
    const t = String(s).trim();
    if (!t) return null;
    if (/^\d{8}$/.test(t)) {
      const y = Number(t.slice(0,4));
      const m = Number(t.slice(4,6));
      const d = Number(t.slice(6,8));
      const dt = new Date(y, m-1, d);
      if (dt && dt.getFullYear() === y && (dt.getMonth()+1) === m && dt.getDate() === d) return dt;
    }
    const parsed = Date.parse(t);
    return isNaN(parsed) ? null : new Date(parsed);
  }

  function escapeHtml(s) {
    return String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
  }

  function currentKeyIndex() {
    const ds = state.datasets[state.tab];
    if (!ds) return -1;
    const { letters, keyLetter } = ds;
    return letters.indexOf(keyLetter);
  }

  async function handleEditSave(ev) {
    const el = ev.target;
    if (!el.classList.contains('edit-cell')) return;
    const ds = state.datasets[state.tab];
    const { headers } = ds;
    const field = el.dataset.col;
    const tr = el.closest('tr');
    const rowIndex = Array.from(tr.parentElement.children).indexOf(tr);
    const absIndex = (state.page - 1) * state.pageSize + rowIndex;
    const row = state.filtered[absIndex];
    const keyIdx = currentKeyIndex();
    const key = row[keyIdx];
    const value = el.value;
    try {
      const res = await fetch('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tab: state.tab, key, field, value })
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || '菫晏ｭ伜､ｱ謨・);
    } catch (e) {
      alert('菫晏ｭ倥お繝ｩ繝ｼ: ' + e.message);
    }
  }

  function exportCSV() {
    const ds = state.datasets[state.tab];
    if (!ds) return;
    const { headers } = ds;
    const spec = state.formatSpec[state.tab] || { dates: new Set(), ints: new Set() };
    const lines = [];
    lines.push(headers.join(','));
    for (const r of state.filtered) {
      const row = r.map((v, i) => {
        const s = String(formatCell(i, headers[i], v, spec));
        if (s.includes('"') || s.includes(',') || s.includes('\n')) {
          return '"' + s.replaceAll('"', '""') + '"';
        }
        return s;
      }).join(',');
      lines.push(row);
    }
    const blob = new Blob(["\ufeff" + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${state.tab}.csv`;
    a.click();
  }

  function hookEvents() {
    qsa('.tab').forEach(b => b.addEventListener('click', () => setActiveTab(b.dataset.tab)));
    qsa('.filters-row input, .filters-row select').forEach(el => {
      el.addEventListener('input', () => { applyFilters(); renderTable(); });
      el.addEventListener('change', () => { applyFilters(); renderTable(); });
    });
    qsa('input[name="logic"]').forEach(el => el.addEventListener('change', () => { applyFilters(); renderTable(); }));
    qs('#prevPage').addEventListener('click', () => { if (state.page > 1) { state.page--; renderTable(); } });
    qs('#nextPage').addEventListener('click', () => {
      const max = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));
      if (state.page < max) { state.page++; renderTable(); }
    });
    qs('#table-container').addEventListener('change', handleEditSave);
    qs('#exportBtn').addEventListener('click', exportCSV);
    qs('#refreshBtn').addEventListener('click', () => loadData(state.tab));
    window.addEventListener('resize', () => renderTable());

    const prodToggle = qs('#prodToggle');
    if (prodToggle) {
      const saved = localStorage.getItem('useSample');
      state.useSample = saved === null ? false : saved === 'true';
      prodToggle.checked = !state.useSample; // checked = 譛ｬ逡ｪ
      prodToggle.addEventListener('change', () => {
        state.useSample = !prodToggle.checked;
        localStorage.setItem('useSample', String(state.useSample));
        loadData(state.tab);
      });
    }

    // 逋ｺ豕ｨ谿・蜷咲ｧｰ縺ｯ繝・・繧ｿ縺九ｉ閾ｪ蜍慕函謌撰ｼ亥・蝗槭Ο繝ｼ繝牙ｾ後↓謠冗判・・  }

  function renderHouchozanNames() {
    const sel = qs('#hzNameSelect');
    if (!sel) return;
    const ds = state.datasets['houchozan'];
    if (!ds) return;
    const letter = ds.nameLetter || 'C';
    const idx = ds.letters.indexOf(letter);
    if (idx < 0) { sel.innerHTML = ''; return; }
    const set = new Set();
    for (const r of ds.rows) {
      const v = String(r[idx] ?? '').trim();
      if (v) set.add(v);
    }
    const options = ['(縺吶∋縺ｦ)', ...Array.from(set).sort((a,b)=> a.localeCompare(b, 'ja'))];
    sel.innerHTML = '';
    for (const name of options) {
      const o = document.createElement('option');
      o.value = name === '(縺吶∋縺ｦ)' ? '' : name;
      o.textContent = name;
      sel.appendChild(o);
    }
    sel.addEventListener('change', () => {
      const v = sel.value;
      const inputC = qs('#filters-houchozan input[data-col="C"]');
      if (inputC) {
        inputC.value = v;
        applyFilters();
        renderTable();
      }
    });
  }

  
  function buildNameOptions(ds) {
    const letter = ds.nameLetter || 'C';
    const idx = ds.letters.indexOf(letter);
    if (idx < 0) return ['(すべて)'];
    const set = new Set();
    for (const r of ds.rows) {
      const v = String(r[idx] ?? '').trim();
      if (v) set.add(v);
    }
    return ['(すべて)', ...Array.from(set).sort((a,b)=> a.localeCompare(b, 'ja'))];
  }

  function renderTextItemNames() {
    const sel = qs('#tiNameSelect');
    if (!sel) return;
    const ds = state.datasets['text_items'];
    if (!ds) return;
    const options = buildNameOptions(ds);
    sel.innerHTML = '';
    for (const name of options) {
      const o = document.createElement('option');
      o.value = name === '(すべて)' ? '' : name;
      o.textContent = name;
      sel.appendChild(o);
    }
    sel.addEventListener('change', () => {
      state.nameFilter['text_items'] = sel.value || '';
      applyFilters();
      renderTable();
    });
  }

  function renderShortNames() {
    const sel = qs('#shortNameSelect');
    if (!sel) return;
    const ds = state.datasets['short'];
    if (!ds) return;
    const options = buildNameOptions(ds);
    sel.innerHTML = '';
    for (const name of options) {
      const o = document.createElement('option');
      o.value = name === '(すべて)' ? '' : name;
      o.textContent = name;
      sel.appendChild(o);
    }
    sel.addEventListener('change', () => {
      state.nameFilter['short'] = sel.value || '';
      applyFilters();
      renderTable();
    });
  }
function renderDates() {
    const el = qs('#dataDates');
    if (!el) return;
    const ds = state.datasets[state.tab];
    if (!ds || !ds.sourceDates) { el.innerHTML = ''; return; }
    const badges = ds.sourceDates.map(d => `<span class="date-badge">${d}</span>`).join('');
    el.innerHTML = badges;
  }

  // init
  hookEvents();
  setActiveTab(state.tab);
})();



