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
    document.getElementById('px-footer').innerHTML = `<p>⚠️ 教育／模擬用途，唔係投資建議。所有預測都係情境參考，唔係保證。真倉由 Roy 自己喺富途落單（系統只記錄同提醒）；紙上組合由系統自動執行，做對照組。</p>
      <p>數據：Yahoo Finance（yfinance）、Finnhub（真倉 5 分鐘報價、報價後備、業績日、新聞）、Marketaux（新聞後備）。指標用已收市日 bar；攞唔到嘅數據會寫「數據暫缺」，唔會估。</p>`;
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
  // Roy's REAL Futu positions (data/futu_positions.json, schema real_positions_v2; written by `run.py pos ...`).
  // Prices = last_price persisted by the jobs (open/daily/hourly/close/morning); P&L net of the buy fee.
  realCard(futu, fx, opts = {}) {
    const rp = futu && futu.schema === 'real_positions_v2' ? futu : null;
    const pos = (rp && rp.positions) || [];
    const closed = (rp && rp.closed_trades) || [];
    const start = (rp && rp.start_capital_usd) || 1280;
    let value = 0, costOpen = 0, unreal = 0;
    const rows = pos.map(p => {
      const px = Number(p.last_price || p.entry_price), sh = Number(p.shares), e = Number(p.entry_price), f = Number(p.entry_fee_usd || 0);
      const pnl = (px - e) * sh - f, basis = e * sh + f;
      value += px * sh; costOpen += basis; unreal += pnl;
      const dsl = p.stop_loss_price ? (px - p.stop_loss_price) / px * 100 : null;
      const dtp = p.take_profit_price ? (p.take_profit_price - px) / px * 100 : null;
      const days = p.entry_date ? Math.max(0, Math.floor((Date.now() - new Date(p.entry_date + 'T00:00:00+08:00').getTime()) / 864e5)) : '—';
      const tag = p.stop_loss_price && px <= p.stop_loss_price ? '⛔ 已穿止蝕' : p.take_profit_price && px >= p.take_profit_price ? '🎯 已到止賺' : (dsl != null && dsl < 2 ? '🔴 近止蝕' : '');
      return `<div class="position-row" style="display:block"><div style="display:flex;justify-content:space-between"><div><b>${PX.esc(p.ticker)}</b> × ${sh} @ ${PX.usd(e)} <span class="muted">${PX.esc(p.entry_date || '')} · 持 ${days} 日 ${tag}</span></div>
        <div class="${PX.cls(pnl)}" style="font-weight:700">${PX.pct(pnl / basis * 100)}（${PX.usd(pnl)} / ${PX.hkd(pnl * fx)}）</div></div>
        <div class="muted">現價 ${PX.usd(px)}${p.last_price_at ? `（${PX.esc(PX.hkt(p.last_price_at))}）` : ''} · 止蝕 ${PX.usd(p.stop_loss_price)}（距 ${dsl != null ? dsl.toFixed(1) : '—'}%）· 止賺 ${PX.usd(p.take_profit_price)}（差 ${dtp != null ? dtp.toFixed(1) : '—'}%）</div>
        ${PX.reasonLine(opts.reasons, p.ticker)}</div>`;
    }).join('');
    const realized = closed.reduce((a, t) => a + Number(t.net_pnl_usd || 0), 0);
    const wins = closed.filter(t => Number(t.net_pnl_usd || 0) > 0).length;
    const equity = start + realized - costOpen + value;
    const lastAt = pos.map(p => p.last_price_at).filter(Boolean).sort().slice(-1)[0];
    const hist = opts.history && closed.length ? `<div class="tbl-wrap" style="margin-top:8px"><table class="tbl"><tr><th>股票</th><th>股數</th><th>買入</th><th>賣出</th><th>日期</th><th>持日</th><th>費用</th><th>淨 P&L</th><th>原因</th></tr>
      ${closed.slice().reverse().map(t => `<tr><td>${PX.esc(t.ticker)}</td><td>${t.shares}</td><td>${PX.usd(t.entry_price)}</td><td>${PX.usd(t.exit_price)}</td><td>${PX.esc(t.entry_date)}→${PX.esc(t.exit_date)}</td><td>${t.days_held ?? '—'}</td><td>${PX.usd(t.fees_usd)}</td>
      <td class="${PX.cls(t.net_pnl_usd)}">${PX.usd(t.net_pnl_usd)}（${PX.pct(t.net_pnl_pct)}）</td><td class="muted">${PX.esc(t.exit_reason)}</td></tr>`).join('')}</table></div>` : '';
    return `<div class="card hero"><h2>🏦 真倉（富途 · Roy 手動落單）${pos.length ? `（${pos.length}/3）` : ''}</h2>
      ${pos.length && lastAt ? PX.freshness(lastAt, 30, '真倉報價') : ''}
      ${pos.length ? `<div>估算總值 <b>${PX.usd(equity)}</b>（${PX.hkd(equity * fx)}）· 真倉回報 <b>${PX.pct((equity - start) / start * 100)}</b> · 未實現 ${PX.usd(unreal)} · 估算現金 ${PX.usd(start + realized - costOpen, 0)}</div>` : ''}
      ${rows || '<div>真倉：暫時冇持倉（買入後叫 Hermes 記錄）</div>'}
      <div style="font-size:12px;opacity:.85;margin-top:6px">${closed.length ? `已平倉 ${closed.length} 筆 · 已實現 ${PX.usd(realized)} · 勝率 ${(wins / closed.length * 100).toFixed(0)}% · ` : ''}${rp && rp.real_start_date ? `真倉 ${PX.esc(rp.real_start_date)} 起 · ` : ''}起始 ${PX.usd(start, 0)}（HKD 10,000）· 系統只記錄同提醒，永遠唔會自動落單</div></div>
      ${hist ? `<div class="card"><h2>🧾 真倉已平倉紀錄（${closed.length} 筆）</h2>${hist}</div>` : ''}`;
  },
  // one-line move reason from data/reasons.json (px/reasons.py: headline + move vs QQQ / sector ETF; never invented)
  reasonLine(reasons, t) {
    const r = reasons && reasons.reasons && reasons.reasons[t];
    if (!r || !r.text) return '';
    const link = r.url ? ` <a class="muted" href="${PX.esc(r.url)}" target="_blank" rel="noopener">新聞</a>` : '';
    return `<div class="why" style="margin-top:4px">💬 ${PX.esc(r.text)}${link} <span class="muted">${r.at ? PX.esc(PX.hkt(r.at)) : ''}</span></div>`;
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
      <div>${cat}</div>${x.reason_plain ? `<div class="why" style="margin-top:6px">💬 ${PX.esc(x.reason_plain)}</div>` : ''}<div class="why" style="margin-top:6px">💡 ${PX.esc((x.why || []).join('；'))}</div></div>`;
  },
};
