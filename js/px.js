// Project X — shared site helpers (merged v3). All numbers come from JSON written by the Python jobs.
const PX = {
  site: 'https://fung2222.github.io/project-x/',
  async json(path) {
    try {
      const r = await fetch(`${path}${path.includes('?') ? '&' : '?'}t=${Date.now()}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    } catch (e) { console.warn('load failed', path, e.message); return null; }
  },
  usd(v, d = 2) { return v == null || isNaN(v) ? '—' : `$${Number(v).toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d})}`; },
  hkd(v) { return v == null || isNaN(v) ? '—' : `HK$${Math.round(Number(v)).toLocaleString('en-US')}`; },
  pct(v, d = 2) { if (v == null || isNaN(v)) return '—'; const n = Number(v); return `${n > 0 ? '+' : ''}${n.toFixed(d)}%`; },
  cls(v) { return v > 0 ? 'up' : v < 0 ? 'down' : ''; },
  esc(s) { return s == null ? '' : String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); },
  // freshness: warn if a timestamp is older than `hours` (weekends tolerated)
  freshness(iso, hours = 30, label = '數據') {
    if (!iso) return `<div class="fresh-warn">⚠️ ${label}未有時間戳</div>`;
    const t = new Date(iso); const age = (Date.now() - t.getTime()) / 3.6e6;
    const dow = new Date().getDay(); const tol = (dow === 0 || dow === 1) ? hours + 48 : hours;
    return age > tol ? `<div class="fresh-warn">⚠️ ${label}已經 ${Math.round(age)} 小時冇更新（${PX.esc(iso)}）— 可能漏跑，請睇 🩺 系統健康</div>` : '';
  },
  nav() {
    const pages = [['index.html','🏠','首頁'],['opportunities.html','🚀','機會掃描'],['signals.html','📊','信號'],
                   ['portfolio.html','💼','組合'],['reports.html','📰','報告'],['learn.html','📚','學習']];
    const cur = location.pathname.split('/').pop() || 'index.html';
    document.getElementById('px-header').innerHTML = `
      <header><div class="header-inner"><div class="logo"><img src="img/icon-32.svg" width="28" height="28" alt="PX"><span>Project X</span></div>
      <div class="update-time" id="update-time">載入中…</div></div></header>
      <nav><div class="nav-inner">${pages.map(([h,i,t]) => `<a href="${h}" class="nav-link${h === cur ? ' active' : ''}"><span class="nav-icon">${i}</span>${t}</a>`).join('')}</div></nav>`;
    document.getElementById('px-footer').innerHTML = `<p>⚠️ 教育／模擬用途，唔係投資建議。所有預測都係情境參考，唔係保證。紙上組合由系統自動執行；真錢落單由 Roy 自己喺富途做。</p>
      <p>數據：Yahoo Finance（yfinance）、Finnhub（報價後備、業績日）。指標用已收市日 bar。</p>`;
  },
  // ISO timestamp -> 'YYYY-MM-DD HH:MM HKT' (naive timestamps are box-local HKT)
  hkt(iso) {
    if (!iso || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(iso)) return iso || '';
    const hasTz = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
    const d = new Date(hasTz ? iso : iso.slice(0, 19) + '+08:00');
    if (isNaN(d)) return iso;
    const h = new Date(d.getTime() + 8 * 3600e3).toISOString();
    return h.slice(0, 10) + ' ' + h.slice(11, 16) + ' HKT';
  },
  setUpdated(txt) {
    const el = document.getElementById('update-time');
    if (el) el.textContent = String(txt).replace(/\d{4}-\d{2}-\d{2}T[\d:.]+(Z|[+-]\d{2}:?\d{2})?/g, m => PX.hkt(m));
  },
  // tiny SVG line chart (no external library)
  lineChart(series, labels, colors = ['#0f766e', '#94a3b8']) {
    const W = 900, H = 220, P = 30;
    const all = series.flat().filter(v => v != null);
    if (all.length < 2) return '<div class="empty">📊 未夠數據畫圖</div>';
    let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * 0.1 || 1; lo -= pad; hi += pad;
    const x = i => P + i * (W - 2 * P) / Math.max(1, labels.length - 1);
    const y = v => H - P - (v - lo) / (hi - lo) * (H - 2 * P);
    const paths = series.map((s, k) => {
      const pts = s.map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean);
      return `<polyline fill="none" stroke="${colors[k % colors.length]}" stroke-width="2.5" points="${pts.join(' ')}"/>`;
    }).join('');
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><line x1="${P}" y1="${H-P}" x2="${W-P}" y2="${H-P}" stroke="#e2e8f0"/>
      <text x="2" y="${P}" font-size="11" fill="#718096">${hi.toFixed(0)}</text><text x="2" y="${H-P}" font-size="11" fill="#718096">${lo.toFixed(0)}</text>
      <text x="${P}" y="${H-8}" font-size="11" fill="#718096">${PX.esc(labels[0])}</text><text x="${W-P-70}" y="${H-8}" font-size="11" fill="#718096">${PX.esc(labels[labels.length-1])}</text>${paths}</svg>`;
  },
  oppCard(x, i, fx) {
    const cat = x.earnings_date ? `<span class="badge ${x.earnings_days != null && x.earnings_days <= 10 ? 'badge-warn' : ''}">📅 業績 ${PX.esc(x.earnings_date)}${x.earnings_days != null ? `（${x.earnings_days} 交易日）` : ''}</span>` : '<span class="badge">📅 業績日未知</span>';
    const live = x.live_price ? ` <span class="muted">現 ${PX.usd(x.live_price)} <span class="${PX.cls(x.live_change_pct)}">${PX.pct(x.live_change_pct)}</span></span>` : '';
    return `<div class="opp"><div class="opp-head"><div><span class="opp-rank">#${i + 1}</span><span class="opp-ticker">${PX.esc(x.ticker)}</span>
      <span class="badge">${PX.esc(x.theme || '')}</span><span class="badge badge-ok">${PX.esc(x.setup)}</span>${live}</div>
      <div class="opp-score">分數 ${Number(x.score).toFixed(0)}</div></div>
      <div class="kv"><div><span>入場區</span>${PX.usd(x.entry_zone[0])}–${PX.usd(x.entry_zone[1])}</div>
      <div><span>止損</span><b class="down">${PX.usd(x.stop)}</b>（−${Number(x.stop_pct).toFixed(1)}%）</div>
      <div><span>目標（${PX.esc(x.target_mode)}）</span><b class="up">${PX.usd(x.target)}</b>（+${Number(x.target_pct).toFixed(1)}%）</div>
      <div><span>回報／風險</span>R:R ${Number(x.rr).toFixed(1)}</div>
      <div><span>建議注碼</span>${x.shares} 股 ≈ ${PX.usd(x.cost_usd, 0)} / ${PX.hkd(x.cost_hkd)}</div>
      <div><span>最大風險（2%）</span>${PX.usd(x.risk_usd, 0)} · 來回手續費 ${x.fee_drag_pct != null ? Number(x.fee_drag_pct).toFixed(1) + '%（要升過呢個先打和）' : '—'}</div></div>
      <div>${cat}</div><div class="why" style="margin-top:6px">💡 ${PX.esc((x.why || []).join('；'))}</div></div>`;
  },
};
