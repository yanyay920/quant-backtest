"""策略信号自测 (不需要真实数据): python tests/test_strategies.py
重点检查均值回复(布林带)的买卖信号逻辑和边界条件。
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.engine import simulate_stock  # noqa: E402
from strategies import build_strategy  # noqa: E402
from strategies.meanrev import MeanReversion  # noqa: E402
from strategies.multifactor import MultiFactor  # noqa: E402
from strategies.trend import TrendFollowing  # noqa: E402


def frame(closes, start="2024-01-02", volume=None):
    closes = np.asarray(closes, dtype=float)
    idx = pd.bdate_range(start, periods=len(closes))
    if volume is None:
        volume = 1000
    return pd.DataFrame({"open": closes, "high": closes + 0.05, "low": closes - 0.05,
                         "close": closes, "volume": volume}, index=idx)


def zigzag(n=30):
    """围绕 10.2 小幅上下波动 (标准差约 0.2), 用来"热身"布林带"""
    return [10.0 if i % 2 == 0 else 10.4 for i in range(n)]


def test_trend_basic():
    df = frame(np.linspace(10, 20, 80))               # 一路上涨
    sig = TrendFollowing(fast=5, slow=20).signals(df)
    assert (sig.iloc[:19] == 0).all(), "不够算长均线的头几天不开仓"
    assert (sig.iloc[25:] == 1).all(), "一路上涨时应一直持有"
    try:
        TrendFollowing(fast=30, slow=10).signals(df)
        raise AssertionError("fast>=slow 应报错")
    except ValueError:
        pass
    print("通过: 趋势跟踪基本逻辑")


def test_meanrev_buy_hold_sell():
    closes = zigzag(30) + [8.0, 9.0, 9.5, 10.0, 10.2, 14.0, 12.0, 10.5, 10.2]
    #         序号 0..29 热身  30    31   32   33    34    35    36    37    38
    df = frame(closes)
    sig = MeanReversion(window=20, k_in=2, k_out=2).signals(df)
    assert (sig.iloc[:19] == 0).all(), "热身期 (数据不够) 不开仓"
    assert sig.iloc[30] == 1, "第31天收盘 8.0 跌破下轨 -> 想持有"
    assert (sig.iloc[31:35] == 1).all(), "价格在通道中间时, 保持持有"
    assert sig.iloc[35] == 0, "第36天收盘 14.0 涨破上轨 -> 想空仓"
    assert (sig.iloc[36:] == 0).all(), "卖出后价格回到通道中间, 不会自动再买"
    print("通过: 均值回复 买入->保持->卖出->不重复买入")


def test_meanrev_rebuy_after_exit():
    closes = zigzag(30) + [8.0, 14.0] + zigzag(2) + [5.0]
    df = frame(closes)
    sig = MeanReversion(window=20, k_in=2, k_out=2).signals(df)
    assert sig.iloc[30] == 1 and sig.iloc[31] == 0
    assert sig.iloc[-1] == 1, "再次跌破下轨 -> 可以再次买入"
    print("通过: 均值回复 卖出后可以再次买入")


def test_meanrev_k_out_zero_sells_at_mean():
    closes = zigzag(30) + [8.0, 9.0, 10.6, 10.0]
    df = frame(closes)
    sig = MeanReversion(window=20, k_in=2, k_out=0).signals(df)
    assert sig.iloc[30] == 1
    assert sig.iloc[31] == 1, "9.0 仍低于均线, 继续持有"
    assert sig.iloc[32] == 0, "10.6 回到均线之上, k_out=0 时卖出"
    print("通过: k_out=0 回到均线就卖")


def test_meanrev_flat_price_no_signal():
    sig = MeanReversion().signals(frame([10.0] * 60))   # 价格不动 -> 标准差为 0
    assert (sig == 0).all(), "标准差为 0 时不应产生买入信号"
    print("通过: 价格不动时不交易")


def test_meanrev_bad_params():
    df = frame(zigzag(40))
    for bad in ({"window": 1}, {"k_in": 0}, {"k_in": -1}, {"k_out": -0.5}):
        try:
            MeanReversion(**bad).signals(df)
            raise AssertionError(f"参数 {bad} 应报错")
        except ValueError:
            pass
    try:
        MeanReversion(foo=1)
        raise AssertionError("未知参数应报错")
    except ValueError:
        pass
    print("通过: 非法参数会报错")


def test_no_lookahead_in_signals():
    rng = np.random.default_rng(0)
    closes = 10 + np.cumsum(rng.normal(0, 0.2, 200))
    df1 = frame(closes)
    changed = closes.copy()
    changed[150:] += rng.normal(0, 3, 50)               # 只改动未来 (第151天起) 的价格
    df2 = frame(changed)
    for name, params in (("meanrev", {}), ("trend", {})):
        s1 = build_strategy(name, params).signals(df1)
        s2 = build_strategy(name, params).signals(df2)
        assert (s1.iloc[:150] == s2.iloc[:150]).all(), f"{name}: 过去的信号不应受未来价格影响"
    print("通过: 信号不使用未来数据")


def test_signal_to_next_open_trade():
    closes = zigzag(30) + [8.0, 8.1, 8.2, 14.0, 13.9, 13.8]
    df = frame(closes)
    sig = MeanReversion(window=20, k_in=2, k_out=2).signals(df)
    _, trades = simulate_stock(df, sig, 100_000, df.index[0], df.index[-1])
    first_buy = [t for t in trades if t["side"] == "buy"][0]
    assert first_buy["date"] == df.index[31], "第31天(序号30)出信号, 第32天(序号31)开盘买入"
    sells = [t for t in trades if t["side"] == "sell"]
    assert sells and sells[0]["date"] == df.index[34], "第34天(序号33)出卖出信号, 第35天(序号34)开盘卖出"
    print("通过: 均值回复信号 -> 次日开盘成交")


def mf_frame():
    """多因子测试用行情: 前 100 天价格完全不变 (热身), 之后依次上涨 / 横盘 / 下跌 / 再上涨。

    成交量始终小幅波动, 保证量能因子有定义; 价格在上涨段第 1 天就开始变化,
    所以总分从序号 100 起才可能有效。
    """
    rng = np.random.default_rng(11)
    n = 200
    rets = np.zeros(n)
    rets[100:115] = rng.normal(0.012, 0.004, 15)      # 上涨
    rets[115:150] = rng.normal(0, 0.004, 35)          # 横盘
    rets[150:185] = rng.normal(-0.012, 0.004, 35)     # 下跌
    rets[185:] = rng.normal(0, 0.002, n - 185)        # 再次上涨
    closes = np.empty(n)
    closes[:100] = 10.0
    closes[100:] = 10 * np.cumprod(1 + rets[100:])
    volume = 1_000_000 + 200_000 * np.sin(np.arange(n) * 0.9)
    return frame(closes, volume=volume)


MF_PARAMS = {"lookback": 5, "zwin": 30, "w_mom": 1, "w_lowvol": 0, "w_volume": 0,
             "enter": 1.0, "leave": 0.0}


def test_multifactor_warmup_and_state():
    df = mf_frame()
    sig = MultiFactor(**MF_PARAMS).signals(df)
    assert (sig.iloc[:100] == 0).all(), "数据不够算总分的头几天不开仓"
    assert sig.iloc[100] == 1, "总分升过 enter (1.0) -> 想持有"
    assert (sig.iloc[115:117] == 1).all(), "总分落在 leave(0) 与 enter(1) 之间 -> 保持持有"
    assert sig.iloc[117] == 0, "总分跌破 leave (0) -> 想空仓"
    assert (sig.iloc[117:185] == 0).all(), "卖出后总分未再升过 enter, 不会自动再买"
    assert sig.iloc[185] == 1, "再次出现强势上涨 -> 再次买入"
    print("通过: 多因子 热身期/买入/保持/卖出")


def test_multifactor_flat_data_no_signal():
    df = frame([10.0] * 200, volume=[1000.0] * 200)
    sig = MultiFactor().signals(df)   # 价格和成交量都不动 -> 各因子标准差为 0
    assert (sig == 0).all(), "标准差为 0 时不应产生信号, 也不能除零报错"
    print("通过: 多因子 价格与成交量不变时不交易")


def test_multifactor_bad_params():
    df = mf_frame()
    for bad in ({"enter": 0.0, "leave": 0.0}, {"enter": -0.5, "leave": 0.0},
                {"w_mom": -0.1}, {"w_mom": 0, "w_lowvol": 0, "w_volume": 0},
                {"lookback": 4}, {"zwin": 29}):
        try:
            MultiFactor(**bad).signals(df)
            raise AssertionError(f"参数 {bad} 应报错")
        except ValueError:
            pass
    try:
        MultiFactor(foo=1)
        raise AssertionError("未知参数应报错")
    except ValueError:
        pass
    print("通过: 多因子非法参数会报错")


def test_multifactor_no_lookahead():
    rng = np.random.default_rng(3)
    n = 240
    closes = 10 * np.cumprod(1 + rng.normal(0.0005, 0.015, n))
    volume = 1_000_000 * (1 + rng.uniform(-0.3, 0.3, n))
    changed = closes.copy()
    changed[180:] *= np.cumprod(1 + rng.normal(0, 0.05, n - 180))   # 只改动末尾 60 天
    changed_volume = volume.copy()
    changed_volume[180:] *= rng.uniform(0.5, 1.5, n - 180)
    s1 = MultiFactor().signals(frame(closes, volume=volume))
    s2 = MultiFactor().signals(frame(changed, volume=changed_volume))
    assert (s1.iloc[:180] == s2.iloc[:180]).all(), "过去 180 天的信号不应受末尾价格/成交量变化影响"
    print("通过: 多因子信号不使用未来数据")


if __name__ == "__main__":
    test_trend_basic()
    test_meanrev_buy_hold_sell()
    test_meanrev_rebuy_after_exit()
    test_meanrev_k_out_zero_sells_at_mean()
    test_meanrev_flat_price_no_signal()
    test_meanrev_bad_params()
    test_no_lookahead_in_signals()
    test_multifactor_warmup_and_state()
    test_multifactor_flat_data_no_signal()
    test_multifactor_bad_params()
    test_multifactor_no_lookahead()
    test_signal_to_next_open_trade()
    print("\n全部通过")
