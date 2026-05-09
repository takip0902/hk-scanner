/* 港股強勢股 Scanner — 前端邏輯 */

let state = {
  data: null,
  filter: 'all',
  search: '',
  sortKey: 'rs_rating',
  sortDir: 'desc',
};

// HTML 轉義 helper—避免 data 中的特殊字元被當作 HTML 解析
function esc(v) {
  if (v === null || v === undefined) return '';
  return String(v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const SORT_LABELS = {
  code: '代碼',
  name: '名稱',
  rs_rating: 'RS Rating',
  streak: '入選天數',
  category: '類別',
  close: '收市價',
  above_ma50_pct: '距均線%',
  pct_5d: '5日漲幅',
  pct_20d: '20日漲幅',
  pct_from_52w_high: '距52W高',
  ma50: 'MA50',
  ma100: 'MA100',
  ma200: 'MA200',
  avg_turnover_m: '平均成交額',
  last_date: '數據日期',
};

async function loadData() {
  // 優先讀取 inline 數據（離線可用），否則 fetch JSON
  if (window.SCANNER_DATA) {
    state.data = window.SCANNER_DATA;
    renderAll();
    return;
  }
  try {
    const res = await fetch('data.json?t=' + Date.now());
    if (!res.ok) throw new Error('無法載入數據');
    state.data = await res.json();
    renderAll();
  } catch (err) {
    document.getElementById('stocks-tbody').innerHTML =
      `<tr><td colspan="15" class="empty-state">數據載入失敗：${esc(err.message)}</td></tr>`;
  }
}

function renderAll() {
  if (!state.data) return;
  renderMeta();
  renderStats();
  renderTable();
  renderRemoved();
}

function renderMeta() {
  document.getElementById('scan-date').textContent = state.data.scan_date || '--';
  const prev = state.data.previous_date;
  const isFirstRun = !prev || prev === state.data.scan_date;
  document.getElementById('prev-date').textContent = isFirstRun ? '首日基線' : prev;
  // 取股票中最新的 last_date 作為「收市數據日期」
  const dates = (state.data.stocks || []).map(s => s.last_date).filter(Boolean);
  const dataDate = dates.length ? dates.sort().reverse()[0] : '--';
  const dd = document.getElementById('data-date');
  if (dd) dd.textContent = dataDate;
}

function renderStats() {
  document.getElementById('stat-total').textContent = state.data.total_qualified ?? 0;
  document.getElementById('stat-new').textContent = state.data.new_count ?? 0;
  document.getElementById('stat-removed').textContent = state.data.removed_count ?? 0;
  document.getElementById('stat-kept').textContent = state.data.kept_count ?? 0;
  document.getElementById('stat-universe').textContent = state.data.data_available ?? 0;
}

function renderTable() {
  const tbody = document.getElementById('stocks-tbody');
  let stocks = [...(state.data.stocks || [])];

  // 篩選
  if (state.filter === 'new') stocks = stocks.filter(s => s.is_new);
  else if (state.filter === 'kept') stocks = stocks.filter(s => !s.is_new);

  // 搜尋
  if (state.search) {
    const q = state.search.toLowerCase();
    stocks = stocks.filter(s =>
      s.code.includes(q) ||
      (s.name && s.name.toLowerCase().includes(q))
    );
  }

  // 排序
  stocks.sort((a, b) => {
    const va = a[state.sortKey];
    const vb = b[state.sortKey];
    if (typeof va === 'number' && typeof vb === 'number') {
      return state.sortDir === 'desc' ? vb - va : va - vb;
    }
    const sa = String(va ?? ''), sb = String(vb ?? '');
    return state.sortDir === 'desc' ? sb.localeCompare(sa) : sa.localeCompare(sb);
  });

  if (!stocks.length) {
    tbody.innerHTML = `<tr><td colspan="15" class="empty-state">沒有符合條件的股票</td></tr>`;
    return;
  }

  tbody.innerHTML = stocks.map(s => {
    const upDown = (v) => v > 0 ? 'up' : (v < 0 ? 'down' : '');
    const fmt = (v, prefix = '') => {
      if (v === null || v === undefined) return '--';
      const sign = v > 0 ? '+' : '';
      return `${sign}${v.toFixed(2)}${prefix}`;
    };
    const rs = s.rs_rating || 0;
    const rsClass = rs >= 90 ? 'rs-elite' : rs >= 80 ? 'rs-strong' : rs >= 70 ? 'rs-ok' : 'rs-weak';
    const cat = s.category === 'new' ? '<span class="cat-new">新股</span>' : '<span class="cat-std">標準</span>';
    const streak = s.streak || 1;
    const streakClass = streak >= 30 ? 'streak-strong' : streak >= 10 ? 'streak-ok' : '';
    return `
      <tr class="${s.is_new ? 'is-new' : ''}">
        <td class="code">${esc(s.code)}</td>
        <td class="name">${esc(s.name || '—')}</td>
        <td class="num rs ${rsClass}">${rs}</td>
        <td class="num streak ${streakClass}">${streak}日</td>
        <td class="num">${s.close.toFixed(3)}</td>
        <td class="num ${upDown(s.above_ma50_pct)}">${fmt(s.above_ma50_pct, '%')}</td>
        <td class="num ${upDown(s.pct_5d)}">${fmt(s.pct_5d, '%')}</td>
        <td class="num ${upDown(s.pct_20d)}">${fmt(s.pct_20d, '%')}</td>
        <td class="num ${upDown(s.pct_from_52w_high)}">${fmt(s.pct_from_52w_high, '%')}</td>
        <td class="num">${s.ma50.toFixed(3)}</td>
        <td class="num">${s.ma100.toFixed(3)}</td>
        <td class="num">${s.ma200.toFixed(3)}</td>
        <td class="num">${s.avg_turnover_m.toFixed(1)}</td>
        <td>${cat}</td>
        <td class="num">${esc(s.last_date)}</td>
      </tr>
    `;
  }).join('');

  // 更新排序標籤
  document.getElementById('sort-label').textContent =
    SORT_LABELS[state.sortKey] + (state.sortDir === 'desc' ? ' ↓' : ' ↑');

  // 更新表頭高亮
  document.querySelectorAll('th[data-sort]').forEach(th => {
    th.classList.toggle('active-sort', th.dataset.sort === state.sortKey);
    th.classList.toggle('asc', th.dataset.sort === state.sortKey && state.sortDir === 'asc');
  });
}

function renderRemoved() {
  const removed = state.data.removed_stocks || [];
  const section = document.getElementById('removed-section');
  const tbody = document.getElementById('removed-tbody');

  if (!removed.length) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';
  tbody.innerHTML = removed.map(s => {
    const upDown = (v) => v > 0 ? 'up' : (v < 0 ? 'down' : '');
    return `
      <tr>
        <td class="code">${esc(s.code)}</td>
        <td class="name">${esc(s.name || '—')}</td>
        <td class="num">${s.close.toFixed(3)}</td>
        <td class="num ${upDown(s.above_ma50_pct)}">${s.above_ma50_pct > 0 ? '+' : ''}${s.above_ma50_pct.toFixed(2)}%</td>
        <td class="num">${esc(s.last_date)}</td>
      </tr>
    `;
  }).join('');
}

// === 事件綁定 ===
document.getElementById('search').addEventListener('input', (e) => {
  state.search = e.target.value.trim();
  renderTable();
});

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.filter = btn.dataset.filter;
    renderTable();
  });
});

document.querySelectorAll('th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.sort;
    if (state.sortKey === key) {
      state.sortDir = state.sortDir === 'desc' ? 'asc' : 'desc';
    } else {
      state.sortKey = key;
      state.sortDir = (key === 'code' || key === 'name' || key === 'last_date') ? 'asc' : 'desc';
    }
    renderTable();
  });
});

// 啟動
loadData();
