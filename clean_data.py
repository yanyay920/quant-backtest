"""数据清洗: 生成提交用的 data/<六位代码>.csv (只含 date,open,high,low,close,volume)

数据来源决定 (依据 records/crosscheck_report.csv 的交叉校验结果):
  - 10 只股票: BaoStock 前复权日线。它和 AkShare(新浪) 在 5 只股票上几乎完全一致;
    AkShare(东方财富) 的前复权结果与二者不一致, 会把早期涨跌幅放大, 所以不采用。
  - 沪深300 基准: AkShare(新浪) 指数日线 (指数不需要复权)。
清洗规则: 去掉停牌日 (BaoStock tradestatus=0); 去掉含空值的行; 日期统一 YYYY-MM-DD;
         价格保留 4 位小数; 成交量为整数 (股)。
输出: data/<代码>.csv + records/clean_log.txt (可直接摘抄进 提交信息.txt)
"""
import os
from datetime import date

import pandas as pd

BS_DIR = os.path.join("records", "crosscheck")
RAW = os.path.join("data", "raw")
OUT = "data"
LOG = os.path.join("records", "clean_log.txt")
COLS = ["date", "open", "high", "low", "close", "volume"]
PRICE = ["open", "high", "low", "close"]
START, END = "2019-01-01", "2024-12-31"
JUMP = 0.11  # 主板单日涨跌幅上限 10%
NAMES = {  # 沪深300 放第一个, 作为标准交易日历
    "000300": "沪深300", "600519": "贵州茅台", "601318": "中国平安",
    "601398": "工商银行", "600900": "长江电力", "000002": "万科A",
    "600276": "恒瑞医药", "002415": "海康威视", "002594": "比亚迪",
    "600111": "北方稀土", "601888": "中国中免",
}


def mtime_date(path):
    return date.fromtimestamp(os.path.getmtime(path)).isoformat()


def check(df):
    ret = df["close"].pct_change()
    return {
        "空值": int(df[COLS].isna().sum().sum()),
        "重复日期": int(df["date"].duplicated().sum()),
        "日期乱序": int(not df["date"].is_monotonic_increasing),
        "价格<=0": int((df[PRICE] <= 0).any(axis=1).sum()),
        "最高<最低": int((df["high"] < df["low"]).sum()),
        "开收越界": int(((df["open"] > df["high"]) | (df["open"] < df["low"]) |
                       (df["close"] > df["high"]) | (df["close"] < df["low"])).sum()),
        "涨跌>11%": int((ret.abs() > JUMP).sum()),
        "成交量<=0": int((df["volume"] <= 0).sum()),
    }


os.makedirs("records", exist_ok=True)
log = [f"数据清洗记录 (清洗日期 {date.today()})",
       "说明: 10 只股票来自 BaoStock 前复权日线; 沪深300 来自 AkShare(新浪) 指数日线。",
       "      停牌日不补数据 (回测时按停牌不能交易处理)。", ""]
summary = []
bench_dates = set()

for code, name in NAMES.items():
    if code == "000300":
        path = os.path.join(RAW, "000300.csv")
        source = "AkShare(新浪)指数日线"
    else:
        path = os.path.join(BS_DIR, f"baostock_{code}.csv")
        source = "BaoStock前复权日线"
    df = pd.read_csv(path)
    got, n0 = mtime_date(path), len(df)

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date")
    df = df[(df["date"] >= START) & (df["date"] <= END)]
    susp = pd.Series(False, index=df.index)
    if "tradestatus" in df.columns:
        susp = df["tradestatus"].astype(str) == "0"
    susp_dates = list(df.loc[susp, "date"])
    df = df[~susp]
    for c in PRICE + ["volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    n_na = int(df[COLS].isna().any(axis=1).sum())
    df = df.dropna(subset=COLS)[COLS].copy()
    df[PRICE] = df[PRICE].round(4)
    df["volume"] = df["volume"].round().astype("int64")

    if code == "000300":
        bench_dates = set(df["date"])
    missing = sorted(bench_dates - set(df["date"]))
    unexplained = [d for d in missing if d not in set(susp_dates)]
    problems = check(df)

    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(os.path.join(OUT, f"{code}.csv"), index=False)

    log.append(f"{code} {name}: 来源={source}; 获取日期={got}; 原始行数={n0}; "
               f"剔除停牌日={len(susp_dates)}; 剔除空值行={n_na}; 最终行数={len(df)}; "
               f"相对沪深300缺少的交易日={len(missing)} (无法用停牌解释的={len(unexplained)})")
    if susp_dates:
        shown = ", ".join(d.strftime("%Y-%m-%d") for d in susp_dates[:15])
        log.append(f"    停牌日: {shown}{' ...' if len(susp_dates) > 15 else ''}")
    left = {k: v for k, v in problems.items() if v}
    if left:
        log.append(f"    清洗后仍有的问题: {left}")
    summary.append({"代码": code, "名称": name, "行数": len(df), "停牌剔除": len(susp_dates),
                    "缺交易日": len(missing), "无法解释": len(unexplained), **problems})

with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(log) + "\n")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)
pd.set_option("display.unicode.east_asian_width", True)
print(pd.DataFrame(summary).to_string(index=False))
print("\n" + "\n".join(log))
print(f"\n已生成 {len(NAMES)} 个文件到 {OUT}/ ; 清洗记录: {LOG}")
