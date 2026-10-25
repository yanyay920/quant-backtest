"""均值回复: 布林带 (在均线上下各画一条"标准差通道", 价格偏离太多就赌它会回来)

买入: 收盘价跌破下轨 (均线 - k_in 倍标准差)  -> 目标仓位 = 持有
卖出: 收盘价涨破上轨 (均线 + k_out 倍标准差) -> 目标仓位 = 空仓
      k_out = 0 表示"回到均线就卖"
价格在通道中间时保持原状态: 已持有就继续持有, 已空仓就继续空仓 (不会在通道里反复买卖)。
标准差用样本标准差 (pandas 默认 ddof=1); 数据不够算均线的头几天不开仓。
"""
import numpy as np
import pandas as pd

from .base import Strategy


class MeanReversion(Strategy):
    name = "meanrev"
    default_params = {"window": 20, "k_in": 2.0, "k_out": 2.0}

    def signals(self, df):
        window = int(self.params["window"])
        k_in, k_out = float(self.params["k_in"]), float(self.params["k_out"])
        if window < 2:
            raise ValueError("window (均线天数) 至少为 2")
        if k_in <= 0:
            raise ValueError("k_in (买入通道宽度, 标准差倍数) 必须大于 0")
        if k_out < 0:
            raise ValueError("k_out (卖出通道宽度, 标准差倍数) 不能为负数; 0 表示回到均线就卖")

        close = df["close"]
        ma = close.rolling(window).mean()
        sd = close.rolling(window).std()
        raw = pd.Series(np.nan, index=df.index)
        raw[close < ma - k_in * sd] = 1.0     # 跌破下轨 -> 想持有
        raw[close > ma + k_out * sd] = 0.0    # 涨破上轨 -> 想空仓
        # 两个条件不会同时成立; 都不成立的日子 (含数据不足的头几天, 比较结果为假) 沿用前一天的状态
        return raw.ffill().fillna(0).astype(int)
