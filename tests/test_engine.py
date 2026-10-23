"""引擎规则自测 (不需要真实数据): python tests/test_engine.py
逐条验证任务书的撮合规则: 次日开盘成交、T+1、涨跌停不成交、停牌不成交、佣金与印花税。
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.engine import (commission, max_buy_shares, sell_net, simulate_stock)  # noqa: E402


def make_df(opens, closes, start="2024-01-02", skip=()):
    dates = pd.bdate_range(start, periods=len(opens))
    df = pd.DataFrame({"open": opens, "high": np.maximum(opens, closes) + 0.1,
                       "low": np.minimum(opens, closes) - 0.1, "close": closes,
                       "volume": 1000}, index=dates)
    return df.drop(df.index[list(skip)]) if skip else df


def run(df, target_days, cap=100_000):
    """target_days: 想持有的日期序号集合 (收盘后的信号)"""
    target = pd.Series([1 if i in target_days else 0 for i in range(len(df))], index=df.index)
    return simulate_stock(df, target, cap, df.index[0], df.index[-1])


def test_fees():
    assert commission(1_000) == 5                      # 最低 5 元
    assert abs(commission(1_000_000) - 250) < 1e-9     # 万 2.5
    amount = 100_000
    assert abs(sell_net(amount) - (amount - 25 - 50)) < 1e-9   # 佣金 25 + 印花税 50
    n = max_buy_shares(100_000, 10.0)
    assert n % 100 == 0 and n * 10 + commission(n * 10) <= 100_000
    print("通过: 佣金/印花税/整手")


def test_next_open_and_t_plus_1():
    opens = [10.0 + 0.2 * i for i in range(8)]
    closes = [10.0 + 0.2 * i + 0.05 for i in range(8)]
    df = make_df(opens, closes)
    # 第 2 天收盘出买入信号 (序号1), 第 4 天收盘出卖出信号 (序号3 起为 0)
    eq, trades = run(df, target_days={1, 2})
    buy, sell = trades[0], trades[1]
    assert buy["date"] == df.index[2] and abs(buy["price"] - opens[2]) < 1e-9, "应在信号次日(第3天)开盘价买入"
    assert sell["date"] == df.index[4] and abs(sell["price"] - opens[4]) < 1e-9, "第4天收盘信号, 应在第5天开盘价卖出"
    assert sell["date"] > buy["date"], "T+1: 卖出日必须晚于买入日"
    print("通过: 次日开盘成交 + T+1")


def test_limit_up_blocks_buy():
    opens = [10, 10, 11.0, 11.5, 12, 12, 12, 12]    # 第3天开盘相对昨收 +10% (涨停)
    closes = [10, 10, 11.0, 11.5, 12, 12, 12, 12]
    df = make_df(opens, closes)
    _, trades = run(df, target_days={1, 2, 3, 4, 5, 6, 7})
    assert trades[0]["date"] == df.index[3], "涨停日买不进, 应顺延到第4天"
    print("通过: 涨停开盘不能买入")


def test_limit_down_blocks_sell():
    opens = [10, 10, 10, 10, 9.0, 9.2, 9.3, 9.4]    # 第5天开盘相对昨收 -10% (跌停)
    closes = [10, 10, 10, 10, 9.0, 9.2, 9.3, 9.4]
    df = make_df(opens, closes)
    _, trades = run(df, target_days={1, 2})          # 第3天收盘起想空仓
    buys = [t for t in trades if t["side"] == "buy"]
    sells = [t for t in trades if t["side"] == "sell"]
    assert buys and sells
    assert sells[0]["date"] == df.index[5], "跌停日卖不出, 应顺延到第6天"
    print("通过: 跌停开盘不能卖出")


def test_suspension():
    opens = [10.0 + 0.1 * i for i in range(12)]
    closes = [10.0 + 0.1 * i for i in range(12)]
    df = make_df(opens, closes, skip=(4, 5, 6))      # 第5~7天停牌, 没有行情行
    full = pd.bdate_range("2024-01-02", periods=12)
    # 信号在停牌前最后一天(第4天)出现, 引擎只能在复牌后第一个有行情的日子成交
    target = pd.Series(0, index=df.index)
    target.loc[df.index[3]:] = 1
    _, trades = simulate_stock(df, target, 100_000, df.index[0], df.index[-1])
    assert trades[0]["date"] == df.index[4], "应在复牌后的第一个交易日成交"
    assert trades[0]["date"] not in [full[4], full[5], full[6]]
    print("通过: 停牌期间不成交, 复牌后成交")


def test_no_lookahead():
    opens = [10, 10, 10, 10, 10, 10]
    closes = [10, 10, 10, 10, 10, 10]
    df = make_df(opens, closes)
    _, trades = run(df, target_days={0})             # 第 1 天收盘的信号
    assert trades[0]["date"] == df.index[1], "不能在信号当天成交"
    print("通过: 无未来函数 (信号当日不成交)")


def test_buy_hold_accounting():
    opens = [10.0 + 0.05 * i for i in range(30)]
    closes = [10.0 + 0.05 * i + 0.02 for i in range(30)]
    df = make_df(opens, closes)
    eq, trades = run(df, target_days=set(range(30)), cap=100_000)
    n = trades[0]["shares"]
    spent = n * opens[1] + commission(n * opens[1])           # 第2天开盘买入
    expected_last = 100_000 - spent + n * closes[-1]
    assert abs(eq.iloc[-1] - expected_last) < 1e-6, "期末资产 = 剩余现金 + 持股市值"
    assert abs(eq.iloc[0] - 100_000) < 1e-9, "买入前净值不变"
    print("通过: 买入持有账务核对")


if __name__ == "__main__":
    test_fees()
    test_next_open_and_t_plus_1()
    test_limit_up_blocks_buy()
    test_limit_down_blocks_sell()
    test_suspension()
    test_no_lookahead()
    test_buy_hold_accounting()
    print("\n全部通过")
