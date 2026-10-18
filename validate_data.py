"""数据校验 (第二版): 只检查、不修改 data/raw 里的原始数据
输出: 屏幕汇总 + 可疑日期明细 + data/validation_report.csv
"""
import glob
import os

import pandas as pd

RAW = os.path.join("data", "raw")
REPORT = os.path.join("data", "validation_report.csv")
JUMP = 0.11  # 主板单日涨跌幅上限是 10%, 超过 11% 基本不是真实行情
NAMES = {
    "600519": "贵州茅台", "601318": "中国平安", "601398": "工商银行",
    "600900": "长江电力", "000002": "万科A", "600276": "恒瑞医药",
    "002415": "海康威视", "002594": "比亚迪", "600111": "北方稀土",
    "601888": "中国中免", "000300": "沪深300",
}
SHORT = {
    "缺失值个数": "缺失", "重复日期": "重复", "日期未排序": "乱序",
    "价格<=0": "价<=0", "最高<最低": "高<低", "开收盘超出高低范围": "开收越界",
    "单日涨跌超11%": "涨跌>11%", "成交量为0的天数": "量=0",
    "相对沪深300缺少的交易日": "缺交易日",
}

# 以沪深300 的交易日作为"标准交易日历"
bench = pd.read_csv(os.path.join(RAW, "000300.csv"), parse_dates=["date"])
bench_dates = set(bench["date"])

rows = []
missing_detail, jump_detail, zero_detail = {}, [], {}
for path in sorted(glob.glob(os.path.join(RAW, "*.csv"))):
    code = os.path.basename(path)[:-4]
    df = pd.read_csv(path, parse_dates=["date"])
    price_cols = [c for c in ["open", "high", "low", "close"] if c in df.columns]
    ret = df["close"].pct_change()
    big = df.index[ret.abs() > JUMP]

    r = {"代码": code, "名称": NAMES.get(code, ""), "行数": len(df)}
    r["缺失值个数"] = int(df[price_cols].isna().sum().sum())
    r["重复日期"] = int(df["date"].duplicated().sum())
    r["日期未排序"] = int(not df["date"].is_monotonic_increasing)
    r["价格<=0"] = int((df[price_cols] <= 0).any(axis=1).sum())
    r["最高<最低"] = int((df["high"] < df["low"]).sum())
    r["开收盘超出高低范围"] = int((
        (df["open"] > df["high"]) | (df["open"] < df["low"]) |
        (df["close"] > df["high"]) | (df["close"] < df["low"])
    ).sum())
    r["单日涨跌超11%"] = len(big)
    if "volume" in df.columns:
        zero = df.loc[df["volume"] == 0, "date"]
        r["成交量为0的天数"] = len(zero)
        if len(zero):
            zero_detail[code] = list(zero.dt.date)
    missing = sorted(bench_dates - set(df["date"]))
    r["相对沪深300缺少的交易日"] = len(missing)
    if missing:
        missing_detail[code] = missing
    for i in big:
        jump_detail.append((code, NAMES.get(code, ""), df.loc[i, "date"].date(),
                            df.loc[i - 1, "close"], df.loc[i, "close"], ret[i]))
    rows.append(r)

report = pd.DataFrame(rows)
report.to_csv(REPORT, index=False, encoding="utf-8-sig")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)
pd.set_option("display.unicode.east_asian_width", True)
print(report.rename(columns=SHORT).to_string(index=False))

if missing_detail:
    print("\n【缺少的交易日】(对照沪深300, 可能是停牌, 也可能是数据缺失)")
    for code, days in missing_detail.items():
        show = ", ".join(d.strftime("%Y-%m-%d") for d in days[:15])
        print(f"  {code} {NAMES.get(code, '')} 共{len(days)}天: {show}{' ...' if len(days) > 15 else ''}")
if jump_detail:
    print(f"\n【单日涨跌超过{JUMP:.0%}的日期】(疑似复权错误或数据错误)")
    for code, name, d, prev, cur, pct in jump_detail:
        print(f"  {code} {name} {d}: 前一日收盘 {prev} -> 当日收盘 {cur} ({pct:+.1%})")
if zero_detail:
    print("\n【成交量为0的日期】")
    for code, days in zero_detail.items():
        print(f"  {code} {NAMES.get(code, '')}: {', '.join(str(d) for d in days[:15])}")
print(f"\n报告已保存: {REPORT}")
