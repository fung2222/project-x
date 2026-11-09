#!/usr/bin/env python
"""回調位策略精準回測 v2（優化版）：portfolio simulation + 時間序列 Sharpe + Walk-forward + 敏感度測試。

修正 v1 弱點：
1. Sharpe 改用「每日權益時間序列」（唔係每筆交易粗計）
2. Walk-forward（訓練期/測試期）＋敏感度測試（防過度擬合）
3. 訊號預先向量化計算（避免逐日重算 rolling，快好多）
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UNIVERSE = [
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'AVGO', 'AMD', 'CRM',
    'ORCL', 'NOW', 'ADBE', 'INTU', 'QCOM', 'NFLX', 'TSLA',
    'COST', 'WMT', 'MCD', 'PEP', 'KO', 'NKE', 'SBUX', 'HD', 'PG',
    'LLY', 'UNH', 'JNJ', 'ABBV', 'MRK', 'PFE', 'AMGN',
    'V', 'MA', 'JPM', 'GS', 'BAC', 'MS',
    'GE', 'CAT', 'HON', 'RTX', 'BA', 'DE', 'LMT',
]
BENCH = 'SPY'

STOP_LOSS = -0.08
TAKE_PROFIT = 0.16
TIME_STOP = 30
FEE = 2.0
MAX_POS = 3
CAPITAL = 10000.0
POS_SIZE = 0.25

BASE = dict(hi_drop=-0.08, lo_drop=-0.18, ma_lo=1.0, ma_hi=1.05)


def load(path='data/backtest/prices_5y.csv'):
    df = pd.read_csv(path, header=[0, 1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index)
    return df


def precompute_signals(df, hi_drop, lo_drop, ma_lo, ma_hi):
    """一次過計算所有 ticker 嘅訊號，返回 {ticker: boolean Series}。"""
    sig_map = {}
    for t in UNIVERSE:
        if t not in df.columns.get_level_values(0):
            continue
        close = df[t]['Close']
        high = df[t]['High']
        ret_3m = close / close.shift(63) - 1
        high52 = high.rolling(252).max()
        drop = close / high52 - 1
        ma50 = close.rolling(50).mean()
        ma50_up = ma50 > ma50.shift(10)
        ratio = close / ma50
        sig = ((ret_3m > 0) & (drop >= lo_drop) & (drop <= hi_drop)
               & ma50_up & (ratio >= ma_lo) & (ratio <= ma_hi))
        sig_map[t] = sig
    return sig_map


def run(df, sig_map, start_idx=0, end_idx=None):
    if end_idx is None:
        end_idx = len(df)
    cash = CAPITAL
    positions = {}
    trades = []
    equity_curve = []

    for i in range(max(1, start_idx), end_idx):
        date = df.index[i]

        # 1. 持倉退出（SL / TP / 時間）
        for t in list(positions.keys()):
            p = positions[t]
            close = float(df[t]['Close'].iloc[i])
            low = float(df[t]['Low'].iloc[i])
            high = float(df[t]['High'].iloc[i])
            sl = p['entry_price'] * (1 + STOP_LOSS)
            tp = p['entry_price'] * (1 + TAKE_PROFIT)
            p['hold_days'] += 1
            exit_price = reason = None
            if low <= sl:
                exit_price, reason = sl, 'SL'
            elif high >= tp:
                exit_price, reason = tp, 'TP'
            elif p['hold_days'] >= TIME_STOP:
                exit_price, reason = close, 'TIME'
            if exit_price is not None:
                cash += p['shares'] * exit_price - FEE
                trades.append(dict(
                    ticker=t, entry_date=p['entry_date'], exit_date=date,
                    entry=p['entry_price'], exit=exit_price,
                    pnl_pct=exit_price / p['entry_price'] - 1,
                    reason=reason, hold_days=p['hold_days']))
                del positions[t]

        # 2. 新訊號 → 今日開市買
        if len(positions) < MAX_POS:
            for t in UNIVERSE:
                if t in positions or len(positions) >= MAX_POS or t not in sig_map:
                    continue
                try:
                    if bool(sig_map[t].iloc[i - 1]):
                        open_px = float(df[t]['Open'].iloc[i])
                        if open_px <= 0 or np.isnan(open_px):
                            continue
                        invest = CAPITAL * POS_SIZE
                        if cash >= invest:
                            shares = invest / open_px
                            cash -= invest - FEE
                            positions[t] = dict(
                                shares=shares, entry_price=open_px,
                                entry_date=date, hold_days=0)
                except Exception:
                    continue

        # 3. 每日 mark-to-market
        equity = cash + sum(
            p['shares'] * float(df[t]['Close'].iloc[i])
            for t, p in positions.items())
        equity_curve.append((date, equity))

    return trades, equity_curve


def calc_sharpe(equity_curve):
    eq = pd.Series([e for _, e in equity_curve])
    ret = eq.pct_change().dropna()
    if len(ret) < 2 or ret.std() == 0:
        return 0.0
    return ret.mean() / ret.std() * np.sqrt(252)


def summarize(trades, equity_curve, label=''):
    n = len(trades)
    if n == 0:
        print(f'[{label}] 冇交易')
        return None
    pnl = pd.DataFrame(trades)
    pnl['pnl_usd'] = CAPITAL * POS_SIZE * pnl['pnl_pct'] - FEE * 2
    wins = pnl[pnl['pnl_usd'] > 0]
    losses = pnl[pnl['pnl_usd'] <= 0]
    win_rate = len(wins) / n
    pf = wins['pnl_usd'].sum() / abs(losses['pnl_usd'].sum()) if len(losses) else float('inf')
    total_pnl = pnl['pnl_usd'].sum()
    eq = pd.Series([e for _, e in equity_curve])
    mdd = ((eq - eq.cummax()) / eq.cummax()).min()
    sharpe = calc_sharpe(equity_curve)
    print(f'[{label}] 交易 {n} 筆｜勝率 {win_rate*100:.0f}%｜PF {pf:.2f}｜'
          f'總P&L ${total_pnl:+.0f}｜MDD {mdd*100:.1f}%｜Sharpe {sharpe:.2f}')
    return dict(n=n, win_rate=win_rate, pf=pf, total_pnl=total_pnl,
                mdd=mdd, sharpe=sharpe)


def bench_return(df, start_idx=0, end_idx=None):
    c = df[BENCH]['Close']
    if end_idx is None:
        end_idx = len(c)
    c = c.iloc[start_idx:end_idx].dropna()
    return c.iloc[-1] / c.iloc[0] - 1


if __name__ == '__main__':
    df = load()
    n = len(df)

    print('=' * 66)
    print('精準回測 v2：時間序列 Sharpe + Walk-forward + 敏感度測試')
    print('=' * 66)

    # 1. 全期
    print('\n【1】全期（2021-11 → 2026-11，原版參數）')
    sig = precompute_signals(df, **BASE)
    trades, eq = run(df, sig)
    summarize(trades, eq, '全期')
    print(f'    SPY 同期買入持有：+{bench_return(df)*100:.1f}%')

    # 2. Walk-forward
    print('\n【2】Walk-forward（訓練 2021-11~2023-10 vs 測試 2023-11~2026-11）')
    split = int(n * 0.4)
    tr_trades, tr_eq = run(df, sig, end_idx=split)
    te_trades, te_eq = run(df, sig, start_idx=split)
    summarize(tr_trades, tr_eq, '訓練期')
    print(f'    SPY 訓練期：+{bench_return(df, 0, split)*100:.1f}%')
    summarize(te_trades, te_eq, '測試期')
    print(f'    SPY 測試期：+{bench_return(df, split, n)*100:.1f}%')

    # 3. 敏感度測試
    print('\n【3】敏感度測試（改一個參數，其他固定）')
    variants = [
        ('基準 -8~-18%', dict(hi_drop=-0.08, lo_drop=-0.18)),
        ('回調淺 -5~-15%', dict(hi_drop=-0.05, lo_drop=-0.15)),
        ('回調深 -10~-20%', dict(hi_drop=-0.10, lo_drop=-0.20)),
        ('企穩窄 0.97-1.03', dict(ma_lo=0.97, ma_hi=1.03)),
        ('企穩闊 1.0-1.08', dict(ma_lo=1.0, ma_hi=1.08)),
    ]
    for label, delta in variants:
        p = dict(BASE)
        p.update(delta)
        s2 = precompute_signals(df, **p)
        t2, e2 = run(df, s2)
        summarize(t2, e2, label)

    print('\n=' * 66)
    print('提示：改少少參數結果就大崩（甚至轉蝕）= 原參數可能 overfit。')
    print('=' * 66)
