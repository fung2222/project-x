#!/usr/bin/env python
"""回調位策略獨立回測：驗證「強勢 + 回調 10-15%」有冇 edge（vs SPY）。

設定（可重複、預先定義，唔會事後改）：
- 訊號 = 3月回報>0 + 離52週高 -8%~-18% + MA50向上 + 收市企穩MA50(1.0-1.05)
- 買入 = 訊號後下一交易日開市價（避免用未公開數據）
- 止損 = -8%（固定）
- 止盈 = +16%（固定 2R）
- 時間止損 = 30 交易日
- 手續費 = 每筆 $2（買）+ $2（賣）＝來回 $4
- 持倉上限 = 3 隻；每注 = 本金 25%（初始本金 US$10,000）
- 比較基準 = SPY 買入持有

輸出：勝率、平均盈虧、期望值、Profit Factor、最大回撤、總回報、CAGR、Sharpe、手續費佔比，同 SPY 對比。
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
FEE_PER_SIDE = 2.0
MAX_POS = 3
START_CAPITAL = 10000.0
POS_SIZE = 0.25


def load(path='data/backtest/prices_5y.csv'):
    df = pd.read_csv(path, header=[0, 1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index)
    return df


def signal_series(df, t):
    close = df[t]['Close']
    high = df[t]['High']
    ret_3m = close / close.shift(63) - 1
    high52 = high.rolling(252).max()
    drop = close / high52 - 1
    ma50 = close.rolling(50).mean()
    ma50_up = ma50 > ma50.shift(10)
    ratio = close / ma50
    sig = ((ret_3m > 0) & (drop >= -0.18) & (drop <= -0.08)
           & ma50_up & (ratio >= 1.0) & (ratio <= 1.05))
    return sig


def run_backtest(df):
    trades = []
    for t in UNIVERSE:
        if t not in df.columns.get_level_values(0):
            continue
        sig = signal_series(df, t)
        open_px = df[t]['Open']
        close_px = df[t]['Close']
        high_px = df[t]['High']
        low_px = df[t]['Low']
        in_pos = False
        entry_date = entry_price = None
        hold_days = 0
        for i in range(1, len(df)):
            date = df.index[i]
            if not in_pos:
                if bool(sig.iloc[i - 1]):
                    entry_price = float(open_px.iloc[i])
                    if entry_price <= 0 or np.isnan(entry_price):
                        continue
                    entry_date = date
                    in_pos = True
                    hold_days = 0
            else:
                hold_days += 1
                sl_price = entry_price * (1 + STOP_LOSS)
                tp_price = entry_price * (1 + TAKE_PROFIT)
                low = float(low_px.iloc[i])
                high = float(high_px.iloc[i])
                close = float(close_px.iloc[i])
                exit_price = reason = None
                if low <= sl_price:
                    exit_price, reason = sl_price, 'SL'
                elif high >= tp_price:
                    exit_price, reason = tp_price, 'TP'
                elif hold_days >= TIME_STOP:
                    exit_price, reason = close, 'TIME'
                if exit_price is not None:
                    pnl_pct = exit_price / entry_price - 1
                    trades.append(dict(
                        ticker=t, entry_date=entry_date, exit_date=date,
                        entry=entry_price, exit=exit_price,
                        pnl_pct=pnl_pct, reason=reason, hold_days=hold_days,
                    ))
                    in_pos = False
    return trades


def stats(trades, df, start_capital=START_CAPITAL):
    n = len(trades)
    if n == 0:
        return None
    pnl = pd.DataFrame(trades)
    pnl['pnl_usd'] = start_capital * POS_SIZE * pnl['pnl_pct'] - FEE_PER_SIDE * 2
    wins = pnl[pnl['pnl_usd'] > 0]
    losses = pnl[pnl['pnl_usd'] <= 0]
    win_rate = len(wins) / n
    gross_win = wins['pnl_usd'].sum()
    gross_loss = abs(losses['pnl_usd'].sum())
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float('inf')
    expectancy = pnl['pnl_usd'].mean()
    total_pnl = pnl['pnl_usd'].sum()
    total_fee = FEE_PER_SIDE * 2 * n
    # 累計權益曲線（依交易順序）
    equity = start_capital + pnl['pnl_usd'].cumsum()
    cummax = equity.cummax()
    mdd = ((equity - cummax) / cummax).min()
    # 時間跨度
    days = (df.index[-1] - df.index[0]).days
    years = days / 365.25
    cagr = (equity.iloc[-1] / start_capital) ** (1 / years) - 1 if years > 0 else 0
    # Sharpe（用每筆交易 P&L 近似，唔係時間序列）
    sharpe = pnl['pnl_usd'].mean() / pnl['pnl_usd'].std() if pnl['pnl_usd'].std() > 0 else 0
    return dict(
        n=n, win_rate=win_rate, profit_factor=profit_factor, expectancy=expectancy,
        total_pnl=total_pnl, total_return=total_pnl / start_capital, mdd=mdd,
        cagr=cagr, sharpe=sharpe, total_fee=total_fee,
        fee_ratio=total_fee / gross_win if gross_win > 0 else 0,
        avg_win=wins['pnl_usd'].mean() if len(wins) else 0,
        avg_loss=losses['pnl_usd'].mean() if len(losses) else 0,
        equity=equity,
    )


def bench_return(df):
    c = df[BENCH]['Close'].dropna()
    return c.iloc[-1] / c.iloc[0] - 1


if __name__ == '__main__':
    df = load()
    trades = run_backtest(df)
    s = stats(trades, df)
    print('=' * 60)
    print('回調位策略獨立回測（5 年，2021-11 → 2026-11）')
    print('=' * 60)
    if s is None:
        print('冇交易產生')
        sys.exit(0)
    print(f'交易次數       : {s["n"]}')
    print(f'勝率           : {s["win_rate"]*100:.1f}%')
    print(f'平均賺         : US${s["avg_win"]:.2f}')
    print(f'平均蝕         : US${s["avg_loss"]:.2f}')
    print(f'期望值（每筆） : US${s["expectancy"]:.2f}')
    print(f'Profit Factor  : {s["profit_factor"]:.2f}')
    print(f'總 P&L         : US${s["total_pnl"]:.2f}')
    print(f'總回報         : {s["total_return"]*100:.1f}%')
    print(f'最大回撤       : {s["mdd"]*100:.1f}%')
    print(f'CAGR           : {s["cagr"]*100:.1f}%')
    print(f'Sharpe（近似） : {s["sharpe"]:.2f}')
    print(f'手續費總計     : US${s["total_fee"]:.2f}（佔總盈利 {s["fee_ratio"]*100:.0f}%）')
    print('-' * 60)
    br = bench_return(df)
    print(f'SPY 同期買入持有回報 : {br*100:.1f}%')
    print(f'策略 vs SPY          : {s["total_return"]*100:.1f}% vs {br*100:.1f}%')
    print('=' * 60)
    # 按 reason 分佈
    from collections import Counter
    print('平倉原因分佈:', dict(Counter(x['reason'] for x in trades)))
    # 分年回報（驗證穩定性，唔好淨係睇總數）
    pnl = pd.DataFrame(trades)
    pnl['pnl_usd'] = START_CAPITAL * POS_SIZE * pnl['pnl_pct'] - FEE_PER_SIDE * 2
    pnl['year'] = pd.to_datetime(pnl['exit_date']).dt.year
    print('-' * 60)
    print('分年 P&L（驗證穩定性）：')
    for yr, g in pnl.groupby('year'):
        print(f'  {yr}: US${g["pnl_usd"].sum():+.0f}（{len(g)} 筆，勝率 {(g["pnl_usd"]>0).mean()*100:.0f}%）')
