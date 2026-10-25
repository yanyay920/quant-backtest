"""核验基准数据: 把 data/000300.csv 算出的沪深300 年度涨跌幅, 和公开数据逐年对比。
公开口径: 沪深300 历年年度涨跌幅 (理杏仁 lixinger.com 沪深300 页面, 价格指数):
  2019 +36.07%  2020 +27.21%  2021 -5.20%  2022 -21.63%  2023 -11.38%  2024 +14.68%
说明: 公开口径 = 当年最后一个收盘 / 上年最后一个收盘 - 1。
  2020~2024 我们的数据里有上年年末收盘价, 可以精确对比 (误差应小于 0.1%);
  2019 缺少 2018 年末收盘价, 只能用 2019-01-02 的开盘价当基数, 允许误差放宽到 0.6%。
只读取数据, 不修改任何文件。
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest.data import load_benchmark  # noqa: E402

PUBLIC = {2019: 36.07, 2020: 27.21, 2021: -5.20, 2022: -21.63, 2023: -11.38, 2024: 14.68}

df = load_benchmark()
year_end = df["close"].groupby(df.index.year).last()

print("沪深300 (data/000300.csv) 年度涨跌幅核验")
print(f"{'年份':<6}{'我们的数据':>12}{'公开数据':>12}{'差异':>10}  结果")
all_ok = True
for year, pub in PUBLIC.items():
    if year == 2019:
        base, tol, note = df["open"].iloc[0], 0.6, " (基数=2019-01-02开盘价)"
    else:
        base, tol, note = year_end[year - 1], 0.1, ""
    ours = (year_end[year] / base - 1) * 100
    diff = ours - pub
    ok = abs(diff) <= tol
    all_ok &= ok
    print(f"{year:<6}{ours:>11.2f}%{pub:>11.2f}%{diff:>+9.2f}%  {'通过' if ok else '请核对!'}{note}")

close = df["close"]
peak_date = close.idxmax()
drawdown = close / close.cummax() - 1
trough_date = drawdown.idxmin()
peak_before = close.loc[:trough_date].idxmax()
print(f"\n最高收盘: {peak_date.date()}  {close.max():.2f}   (公开资料: 2021-02-10 高点 5930.91)")
print(f"最大回撤: {drawdown.min():.2%}  高点 {peak_before.date()} {close.loc[peak_before]:.2f}"
      f" -> 低点 {trough_date.date()} {close.loc[trough_date]:.2f}")
print(f"数据范围: {df.index[0].date()} ~ {df.index[-1].date()}, 共 {len(df)} 个交易日")
print("\n结论:", "年度涨跌幅全部与公开数据吻合" if all_ok else "有年份对不上, 请把这张表发给我")
