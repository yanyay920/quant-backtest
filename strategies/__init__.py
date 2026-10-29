from .meanrev import MeanReversion
from .multifactor import MultiFactor
from .trend import TrendFollowing

STRATEGIES = {  # 策略类型名 -> 策略类; 以后新增策略只需在这里登记
    "trend": TrendFollowing,
    "meanrev": MeanReversion,
    "multifactor": MultiFactor,
}


def build_strategy(name, params=None):
    if name not in STRATEGIES:
        raise SystemExit(f"未知策略类型 '{name}', 可选: {', '.join(STRATEGIES)}")
    return STRATEGIES[name](**(params or {}))
