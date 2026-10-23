"""趋势跟踪: 双均线。短期均线在长期均线上方就持有, 否则空仓。"""
from .base import Strategy


class TrendFollowing(Strategy):
    name = "trend"
    default_params = {"fast": 10, "slow": 30}

    def signals(self, df):
        fast, slow = int(self.params["fast"]), int(self.params["slow"])
        if fast >= slow:
            raise ValueError("fast (短均线天数) 必须小于 slow (长均线天数)")
        ma_fast = df["close"].rolling(fast).mean()
        ma_slow = df["close"].rolling(slow).mean()
        sig = (ma_fast > ma_slow).astype(int)
        sig[ma_slow.isna()] = 0  # 数据不够算长均线的头几天不开仓
        return sig
