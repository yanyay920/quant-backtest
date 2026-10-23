"""策略基类: 策略只负责"看数据、给信号", 不碰撮合和资金。

signals(df) 返回一个与 df 同索引的 Series, 取值 1 (想持有) 或 0 (想空仓),
表示"该日收盘后"策略想要的仓位。引擎会在下一个交易日开盘价执行。
"""


class Strategy:
    name = "base"
    default_params = {}

    def __init__(self, **params):
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.name} 策略没有这些参数: {sorted(unknown)}; "
                             f"可用参数: {sorted(self.default_params)}")
        self.params = {**self.default_params, **params}

    def signals(self, df):
        raise NotImplementedError
