// Project X — shared site helpers. All figures come from JSON written by the Python jobs.
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
  freshness(iso, hours = 30, label = '數據') {
    if (!iso) return `<div class="fresh-warn" role="status"><strong>數據提醒</strong>　${label}未有時間戳</div>`;
    const t = new Date(iso); const age = (Date.now() - t.getTime()) / 3.6e6;
    const dow = new Date().getDay(); const tol = (dow === 0 || dow === 1) ? hours + 48 : hours;
    return age > tol ? `<div class="fresh-warn" role="status"><strong>數據提醒</strong>　${label}已經 ${Math.round(age)} 小時冇更新（${PX.esc(iso)}），可能漏跑，請查閱系統健康報告。</div>` : '';
  },
  nav() {
    const pages = [
      ['index.html', '總覽'], ['portfolio.html', '組合'], ['signals.html', '信號'],
      ['opportunities.html', '突破研究'], ['pullback.html', '回調研究'],
      ['reports.html', '報告'], ['mentor.html', '師徒模式'], ['learn.html', '學習']
    ];
    const cur = location.pathname.split('/').pop() || 'index.html';
    document.body.dataset.page = cur.replace('.html', '');
    document.getElementById('px-header').innerHTML = `
      <a class="skip-link" href="#content">跳到主要內容</a>
      <header><div class="header-inner">
        <a class="logo" href="index.html" aria-label="Project X 首頁"><span class="logo-mark" aria-hidden="true">PX</span><span class="logo-copy"><strong>Project X</strong><small>投資研究與風控</small></span></a>
        <div class="update-wrap"><span class="status-dot" aria-hidden="true"></span><span class="update-time" id="update-time">載入中…</span></div>
      </div></header>
      <nav aria-label="主要導覽"><div class="nav-inner">${pages.map(([h, t]) => `<a href="${h}" class="nav-link${h === cur ? ' active' : ''}"${h === cur ? ' aria-current="page"' : ''}>${t}</a>`).join('')}</div></nav>`;
    document.getElementById('px-footer').innerHTML = `<footer><div class="footer-main"><div><b>Project X</b><p>研究、模擬、紀錄，先守風控再談回報。</p></div><p>教育／模擬用途，唔係投資建議。真倉由 Roy 自己喺富途落單，系統只記錄同提醒；紙上組合由系統自動執行，用作對照。</p></div><p class="footer-sources">數據：Yahoo Finance、Finnhub、Marketaux。指標只用已收市日線；缺失數據會如實標示，唔會估算補齊。</p></footer>`;
    requestAnimationFrame(() => document.querySelector('.nav-link.active')?.scrollIntoView({block: 'nearest', inline: 'center'}));
  },
  enhanceTables(root = document) {
    root.querySelectorAll('table.tbl').forEach(table => {
      const labels = [...table.querySelectorAll('thead th, tr:first-child th')].map(th => th.textContent.trim());
      table.classList.add('responsive-table');
      table.querySelectorAll('tr').forEach(row => [...row.children].forEach((cell, i) => {
        if (cell.tagName === 'TD') cell.dataset.label = labels[i] || `欄位 ${i + 1}`;
      }));
    });
  },
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
  lineChart(series, labels, colors = ['#005d71', '#89939c']) {
    const W = 900, H = 220, P = 38;
    const all = series.flat().filter(v => v != null && Number.isFinite(Number(v))).map(Number);
    if (all.length < 2) return '<div class="empty">未夠數據畫圖</div>';
    let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * 0.1 || 1; lo -= pad; hi += pad;
    const x = i => P + i * (W - 2 * P) / Math.max(1, labels.length - 1);
    const y = v => H - P - (v - lo) / (hi - lo) * (H - 2 * P);
    const paths = series.map((s, k) => {
      const pts = s.map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(Number(v)).toFixed(1)}`).filter(Boolean);
      return `<polyline fill="none" stroke="${colors[k % colors.length]}" stroke-width="3" points="${pts.join(' ')}" vector-effect="non-scaling-stroke"/>`;
    }).join('');
    const id = `chart-${++PX._chartId}`;
    const desc = `${labels[0] || ''} 至 ${labels[labels.length - 1] || ''}；數值範圍 ${Math.min(...all).toFixed(2)} 至 ${Math.max(...all).toFixed(2)}。`;
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="${id}-title ${id}-desc"><title id="${id}-title">權益走勢圖</title><desc id="${id}-desc">${PX.esc(desc)}</desc><line x1="${P}" y1="${H-P}" x2="${W-P}" y2="${H-P}" stroke="#d6dde1"/>
      <text x="2" y="${P}" font-size="12" fill="#5f6b76">${hi.toFixed(0)}</text><text x="2" y="${H-P}" font-size="12" fill="#5f6b76">${lo.toFixed(0)}</text>
      <text x="${P}" y="${H-8}" font-size="12" fill="#5f6b76">${PX.esc(labels[0])}</text><text x="${W-P}" text-anchor="end" y="${H-8}" font-size="12" fill="#5f6b76">${PX.esc(labels[labels.length-1])}</text>${paths}</svg>`;
  },
  _chartId: 0,
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
      const tag = p.stop_loss_price && px <= p.stop_loss_price ? '<span class="badge badge-bad">已穿止蝕</span>' : p.take_profit_price && px >= p.take_profit_price ? '<span class="badge badge-ok">已到止賺</span>' : (dsl != null && dsl < 2 ? '<span class="badge badge-warn">近止蝕</span>' : '');
      const isCore = String(p.ticker).toUpperCase() === 'VOO';
      const entryRisk = p.stop_loss_price ? Math.max(0, (e - Number(p.stop_loss_price)) * sh + f) : null;
      return `<article class="position-row position-block"><div class="position-top"><div><div class="position-name"><b>${PX.esc(p.ticker)}</b><span class="badge ${isCore ? 'badge-core' : ''}">${isCore ? '核心定投' : '衛星學習倉'}</span>${tag}</div><div class="position-detail">${sh} 股 @ ${PX.usd(e)} · ${PX.esc(p.entry_date || '')} · 持 ${days} 日</div></div><div class="${PX.cls(pnl)} position-pnl">${PX.pct(pnl / basis * 100)}<small>${PX.usd(pnl)} / ${PX.hkd(pnl * fx)}</small></div></div>
        <div class="position-detail">現價 ${PX.usd(px)}${p.last_price_at ? ` · ${PX.esc(PX.hkt(p.last_price_at))}` : ''} · 止蝕 ${PX.usd(p.stop_loss_price)}（距 ${dsl != null ? dsl.toFixed(1) : '—'}%）· 止賺 ${PX.usd(p.take_profit_price)}（差 ${dtp != null ? dtp.toFixed(1) : '—'}%）</div>
        ${opts.compact ? '' : `<div class="position-detail">市值佔起始資金 ${(px * sh / start * 100).toFixed(1)}%${entryRisk != null ? ` · 入場至止蝕風險 ${PX.usd(entryRisk)}（起始資金 ${(entryRisk / start * 100).toFixed(1)}%）` : ''}</div>${PX.reasonLine(opts.reasons, p.ticker)}`}</article>`;
    }).join('');
    const realized = closed.reduce((a, t) => a + Number(t.net_pnl_usd || 0), 0);
    const wins = closed.filter(t => Number(t.net_pnl_usd || 0) > 0).length;
    const equity = start + realized - costOpen + value;
    const coreValue = pos.filter(p => String(p.ticker).toUpperCase() === 'VOO').reduce((sum, p) => sum + Number(p.last_price || p.entry_price) * Number(p.shares), 0);
    const satelliteValue = value - coreValue;
    const corePct = equity ? coreValue / equity * 100 : 0, satellitePct = equity ? satelliteValue / equity * 100 : 0;
    const coreBar = value ? coreValue / value * 100 : 0;
    const lastAt = pos.map(p => p.last_price_at).filter(Boolean).sort().slice(-1)[0];
    const hist = opts.history && closed.length ? `<details class="card detail-card"><summary>真倉已平倉紀錄（${closed.length} 筆）</summary><div class="detail-body"><div class="tbl-wrap"><table class="tbl"><tr><th>股票</th><th>股數</th><th>買入</th><th>賣出</th><th>日期</th><th>持日</th><th>費用</th><th>淨 P&amp;L</th><th>原因</th></tr>
      ${closed.slice().reverse().map(t => `<tr><td>${PX.esc(t.ticker)}</td><td>${t.shares}</td><td>${PX.usd(t.entry_price)}</td><td>${PX.usd(t.exit_price)}</td><td>${PX.esc(t.entry_date)}→${PX.esc(t.exit_date)}</td><td>${t.days_held ?? '—'}</td><td>${PX.usd(t.fees_usd)}</td><td class="${PX.cls(t.net_pnl_usd)}">${PX.usd(t.net_pnl_usd)}（${PX.pct(t.net_pnl_pct)}）</td><td class="muted">${PX.esc(t.exit_reason)}</td></tr>`).join('')}</table></div></div></details>` : '';
    return `<section class="portfolio-shell" aria-label="真倉概覽"><div class="portfolio-lead"><div class="eyebrow light">REAL PORTFOLIO · 手動落單</div><div class="portfolio-title"><h2>真倉概覽</h2><span>核心＋衛星</span></div>
      <div class="equity-label">估算總值</div><div class="equity-value">${PX.usd(equity)}</div><div class="equity-hkd">${PX.hkd(equity * fx)}</div>
      <div class="real-return ${PX.cls(equity - start)}">真倉回報 ${PX.pct((equity - start) / start * 100)}</div>
      <div class="real-stats"><div><span>未實現</span><b>${PX.usd(unreal)}</b></div><div><span>估算現金</span><b>${PX.usd(start + realized - costOpen, 0)}</b></div></div>
      <div class="allocation"><div class="allocation-head"><span>持倉分布</span><span>${pos.length} 隻</span></div><div class="allocation-bar" aria-hidden="true"><i style="width:${coreBar.toFixed(1)}%"></i></div><div class="allocation-legend"><span>VOO 核心 ${corePct.toFixed(1)}%</span><span>衛星 ${satellitePct.toFixed(1)}%</span></div></div>
      <div class="hero-meta">${closed.length ? `已平倉 ${closed.length} 筆 · 已實現 ${PX.usd(realized)} · 勝率 ${(wins / closed.length * 100).toFixed(0)}% · ` : ''}${rp && rp.real_start_date ? `${PX.esc(rp.real_start_date)} 起 · ` : ''}起始 ${PX.usd(start, 0)}</div></div>
      <div class="portfolio-positions"><div class="section-heading compact"><h2>持倉明細</h2><span class="section-meta">系統只記錄，唔會自動落單</span></div>${pos.length && lastAt ? PX.freshness(lastAt, 30, '真倉報價') : ''}
      ${rows || '<div class="empty">暫時冇持倉，買入後叫 Hermes 記錄。</div>'}<p class="position-note">VOO 係核心長線定投；其他個股係衛星學習倉。25% 單注上限同 2% 風險規則只適用於衛星新倉。</p></div></section>${hist}`;
  },
  reasonLine(reasons, t) {
    const r = reasons && reasons.reasons && reasons.reasons[t];
    if (!r || !r.text) return '';
    const link = r.url ? ` <a class="muted" href="${PX.esc(r.url)}" target="_blank" rel="noopener">新聞來源</a>` : '';
    return `<div class="why"><b>市場原因</b>　${PX.esc(r.text)}${link} <span class="muted">${r.at ? PX.esc(PX.hkt(r.at)) : ''}</span></div>`;
  },
  oppCard(x, i, fx, opts = {}) {
    const cat = x.earnings_date ? `<span class="badge ${x.earnings_days != null && x.earnings_days <= 10 ? 'badge-warn' : ''}">業績 ${PX.esc(x.earnings_date)}${x.earnings_days != null ? `（${x.earnings_days} 交易日）` : ''}</span>` : '<span class="badge">業績日未知</span>';
    const live = x.live_price ? `<span class="live-price">現 ${PX.usd(x.live_price)} <span class="${PX.cls(x.live_change_pct)}">${PX.pct(x.live_change_pct)}</span></span>` : '';
    const reason = x.reason_plain || (x.why || []).join('；');
    return `<article class="opp${opts.compact ? ' opp-compact' : ''}" aria-label="${PX.esc(x.ticker)} 研究詳情"><div class="opp-head"><div class="opp-identity"><span class="opp-rank">${String(i + 1).padStart(2, '0')}</span><span class="opp-ticker">${PX.esc(x.ticker)}</span><span class="badge">${PX.esc(x.theme || '')}</span><span class="badge badge-ok">${PX.esc(x.setup)}</span></div><div class="opp-score"><span>研究分數</span>${Number(x.score || 0).toFixed(0)}</div></div>
      ${live ? `<div class="opp-live">${live}</div>` : ''}<div class="kv"><div><span>入場區</span>${PX.usd(x.entry_zone[0])}–${PX.usd(x.entry_zone[1])}</div>
      <div><span>止損</span><b class="down">${PX.usd(x.stop)}</b>（−${Number(x.stop_pct).toFixed(1)}%）</div>
      <div><span>目標（${PX.esc(x.target_mode)}）</span><b class="up">${PX.usd(x.target)}</b>（+${Number(x.target_pct).toFixed(1)}%）</div>
      <div><span>回報／風險</span>R:R ${Number(x.rr).toFixed(1)}</div>
      ${opts.compact ? '' : `<div><span>模擬注碼（預算參考）</span>${x.shares} 股 ≈ ${PX.usd(x.cost_usd, 0)} / ${PX.hkd(x.cost_hkd)}</div><div><span>最大風險（2%）</span>${PX.usd(x.risk_usd, 0)} · 來回手續費 ${x.fee_drag_pct != null ? Number(x.fee_drag_pct).toFixed(1) + '%（打和門檻）' : '—'}</div>`}</div>
      <div class="opp-footer">${cat}</div>${reason ? `<div class="why">${PX.esc(reason)}</div>` : ''}</article>`;
  },
};
