"""多因子打分: 动量 + 低波动 + 量能, 三因子各自滚动标准化后加权合成总分。

每只股票用自己的历史数据独立打分, 不做股票之间的横向排名:
引擎把总资金平均分成 N 份, 每只股票独立使用自己那一份资金回测,
因此打分也在每只股票自己的历史上做 (只和它自己的过去比较), 不依赖同期其他股票。

三个因子 (lookback 天):
  动量   ret = close.pct_change(lookback)                 涨得越多分越高
  低波动 vol = close.pct_change().rolling(lookback).std() 波动越小分越高 (取负号)
  量能   volu = volume.rolling(5).mean() / volume.rolling(60).mean() - 1

标准化: z(x) = ((x - x.rolling(zwin).mean()) / x.rolling(zwin).std()).clip(-3, 3)

总分: score = (w_mom*s_mom + w_lowvol*s_lowvol + w_volume*s_volume)
             / (w_mom + w_lowvol + w_volume)

买入: score > enter  -> 目标仓位 = 持有
卖出: score < leave  -> 目标仓位 = 空仓
两者之间保持原状态 (ffill); 数据不够算总分的头几天不开仓。
标准差为 0 (价格/成交量不变) 时 z 分数为 NaN, 不会误开仓, 也不会除零报错。
"""
import numpy as np
import pandas as pd

from .base import Strategy


class MultiFactor(Strategy):
    name = "multifactor"
    default_params = {"lookback": 20, "w_mom": 0.5, "w_lowvol": 0.25, "w_volume": 0.25,
                      "enter": 0.5, "leave": 0.0, "zwin": 120}

    def signals(self, df):
        lookback = int(self.params["lookback"])
        zwin = int(self.params["zwin"])
        w_mom = float(self.params["w_mom"])
        w_lowvol = float(self.params["w_lowvol"])
        w_volume = float(self.params["w_volume"])
        enter = float(self.params["enter"])
        leave = float(self.params["leave"])

        if lookback < 5:
            raise ValueError("lookback (因子计算窗口) 至少为 5")
        if zwin < 30:
            raise ValueError("zwin (滚动标准化的窗口) 至少为 30")
        if w_mom < 0 or w_lowvol < 0 or w_volume < 0:
            raise ValueError("w_mom / w_lowvol / w_volume (三个因子的权重) 都不能为负数")
        if w_mom + w_lowvol + w_volume <= 0:
            raise ValueError("三个因子的权重之和必须大于 0")
        if enter <= leave:
            raise ValueError("enter (买入阈值) 必须大于 leave (卖出阈值)")

        close = df["close"]
        volume = df["volume"]

        ret = close.pct_change(lookback)
        vol = close.pct_change().rolling(lookback).std()
        volu = volume.rolling(5).mean() / volume.rolling(60).mean() - 1

        def z(series):
            """滚动 z 分数; 标准差为 0 时结果为 NaN (0/0), 不会被当成买卖信号"""
            mean = series.rolling(zwin).mean()
            sd = series.rolling(zwin).std()
            return ((series - mean) / sd).clip(-3, 3)

        s_mom = z(ret)
        s_lowvol = -z(vol)
        s_volume = z(volu)
        total_weight = w_mom + w_lowvol + w_volume
        score = (w_mom * s_mom + w_lowvol * s_lowvol + w_volume * s_volume) / total_weight

        raw = pd.Series(np.nan, index=df.index)
        raw[score > enter] = 1.0     # 总分过买入阈值 -> 想持有
        raw[score < leave] = 0.0     # 总分破卖出阈值 -> 想空仓
        # 两个条件不会同时成立; 中间区域 (含数据不足的头几天) 沿用前一天的状态
        return raw.ffill().fillna(0).astype(int)
