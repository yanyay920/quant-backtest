"""绩效指标: 年化收益、最大回撤、夏普比率、胜率"""
import numpy as np

from config import TRADING_DAYS


def max_drawdown(nav):
    """净值从最高点到其后最低点的最大跌幅 (负数); 起点按初始净值 1.0 计入"""
    values = np.concatenate([[1.0], nav.to_numpy(dtype=float)])
    peak = np.maximum.accumulate(values)
    return float((values / peak - 1.0).min())


def compute_metrics(nav, trades=None):
    """nav: 净值序列 (起始资金 = 1.0); trades: 成交记录 DataFrame (可选, 用于胜率)"""
    final = float(nav.iloc[-1])
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    annual = final ** (1 / years) - 1 if years > 0 and final > 0 else float("nan")

    rets = nav.pct_change()
    rets.iloc[0] = nav.iloc[0] - 1.0          # 第一天相对初始资金的收益
    std = rets.std()
    sharpe = float(rets.mean() / std * np.sqrt(TRADING_DAYS)) if std and std > 0 else 0.0  # 无风险利率按 0

    win, n_trades = float("nan"), 0
    if trades is not None and len(trades):
        sells = trades[trades["side"] == "sell"]
        n_trades = len(sells)
        if n_trades:
            win = float((sells["pnl"] > 0).mean())   # 已平仓的每一笔买卖: 盈利占比

    return {"总收益": final - 1.0, "年化收益": annual, "最大回撤": max_drawdown(nav),
            "夏普比率": sharpe, "胜率": win, "交易次数": n_trades, "期末净值": final}
