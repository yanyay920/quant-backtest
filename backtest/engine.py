"""回测撮合引擎 (规则来自任务书, 不得更改):
  1. 信号在当日收盘后产生, 次一交易日开盘价成交 (避免未来函数)
  2. T+1: 当日买入的股票, 次一交易日起才能卖出
  3. 涨停开盘不能买入, 跌停开盘不能卖出 (当日不成交, 之后每天按最新信号继续尝试)
  4. 停牌日没有行情行, 无法成交; 复牌后的第一个交易日再按最新信号成交
  5. 佣金万2.5 (最低5元), 卖出另收印花税万5; 买入按 100 股整数倍
资金分配: 初始资金平均分成 N 份 (N=股票数), 每只股票独立使用自己那一份,
         组合净值 = 各份资产相加。
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import (COMMISSION_MIN, COMMISSION_RATE, INITIAL_CAPITAL, LIMIT_PCT,
                    LIMIT_TOL, LOT_SIZE, STAMP_TAX_RATE)
from backtest.data import load_benchmark


def commission(amount):
    return max(COMMISSION_MIN, amount * COMMISSION_RATE)


def buy_total(amount):
    """买入成交额 + 佣金"""
    return amount + commission(amount)


def sell_net(amount):
    """卖出成交额 - 佣金 - 印花税"""
    return amount - commission(amount) - amount * STAMP_TAX_RATE


def max_buy_shares(cash, price):
    """现金够买的最大股数 (100 股整数倍, 含佣金)"""
    if not price > 0:
        return 0
    lots = int(cash // (price * LOT_SIZE))
    while lots > 0 and buy_total(lots * LOT_SIZE * price) > cash:
        lots -= 1
    return lots * LOT_SIZE


def simulate_stock(df, target, capital, start, end):
    """单只股票回测。

    df: 该股票完整历史行情 (索引为日期, 停牌日没有行)
    target: 每日收盘后的目标仓位 (1 持有 / 0 空仓), 与 df 同索引
    返回 (每日收盘总资产 Series, 成交记录 list)
    """
    dates = df.index
    op = df["open"].to_numpy(dtype=float)
    cl = df["close"].to_numpy(dtype=float)
    tg = target.reindex(dates).fillna(0).to_numpy()
    i0 = dates.searchsorted(pd.Timestamp(start), side="left")
    i1 = dates.searchsorted(pd.Timestamp(end), side="right")
    limit = LIMIT_PCT - LIMIT_TOL

    cash, shares, buy_i, entry_cost = float(capital), 0, -1, 0.0
    equity, trades = [], []
    for i in range(i0, i1):
        if i > 0:
            want = tg[i - 1] == 1            # 昨天收盘后的信号
            gap = op[i] / cl[i - 1] - 1.0    # 今天开盘相对昨收的涨跌幅
            if want and shares == 0:
                if gap < limit:              # 涨停开盘买不进
                    n = max_buy_shares(cash, op[i])
                    if n > 0:
                        amount = n * op[i]
                        fee = commission(amount)
                        cash -= amount + fee
                        shares, buy_i, entry_cost = n, i, amount + fee
                        trades.append({"date": dates[i], "side": "buy", "price": op[i],
                                       "shares": n, "amount": amount, "fee": fee,
                                       "pnl": np.nan, "ret": np.nan})
            elif (not want) and shares > 0:
                if buy_i < i and gap > -limit:   # T+1; 跌停开盘卖不出
                    amount = shares * op[i]
                    net = sell_net(amount)
                    pnl = net - entry_cost
                    cash += net
                    trades.append({"date": dates[i], "side": "sell", "price": op[i],
                                   "shares": shares, "amount": amount, "fee": amount - net,
                                   "pnl": pnl, "ret": pnl / entry_cost})
                    shares, buy_i, entry_cost = 0, -1, 0.0
        equity.append(cash + shares * cl[i])
    return pd.Series(equity, index=dates[i0:i1]), trades


@dataclass
class BacktestResult:
    nav: pd.Series            # 策略净值 (总资产 / 初始资金)
    bench_nav: pd.Series      # 基准净值 (沪深300 首日开盘买入持有)
    trades: pd.DataFrame      # 全部成交记录
    strategy: str
    params: dict = field(default_factory=dict)
    start: str = ""
    end: str = ""


def run_backtest(strategy, data, start, end, capital=INITIAL_CAPITAL, bench=None):
    """多只股票组合回测。data: {代码: 行情DataFrame}"""
    bench = load_benchmark() if bench is None else bench
    calendar = bench.index[(bench.index >= pd.Timestamp(start)) & (bench.index <= pd.Timestamp(end))]
    slot = capital / len(data)

    equities, all_trades = [], []
    for code, df in data.items():
        target = strategy.signals(df)          # 用完整历史算信号 (均线等需要预热)
        eq, trades = simulate_stock(df, target, slot, start, end)
        equities.append(eq.rename(code))
        for t in trades:
            t["code"] = code
        all_trades += trades

    eq_df = pd.concat(equities, axis=1).reindex(calendar).ffill().fillna(slot)
    nav = eq_df.sum(axis=1) / capital

    bench_close = bench.loc[calendar, "close"]
    bench_nav = bench_close / bench.loc[calendar[0], "open"]

    cols = ["date", "code", "side", "price", "shares", "amount", "fee", "pnl", "ret"]
    trades_df = pd.DataFrame(all_trades, columns=cols).sort_values(["date", "code"]).reset_index(drop=True)
    return BacktestResult(nav=nav, bench_nav=bench_nav, trades=trades_df,
                          strategy=strategy.name, params=dict(strategy.params),
                          start=str(start), end=str(end))
