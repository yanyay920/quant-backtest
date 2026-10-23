"""数据交叉校验: 用 BaoStock 的前复权日线, 核对 AkShare 下载的 data/raw 数据
只读取 data/raw, 不修改; BaoStock 数据另存到 records/crosscheck/
输出: 屏幕汇总 + 差异明细 + records/crosscheck_report.csv
(报告不放进 data/, 因为提交时 data/ 里只放每只标的一个 CSV)
"""
import os

import baostock as bs
import pandas as pd

RAW = os.path.join("data", "raw")
OUT = os.path.join("records", "crosscheck")
REPORT = os.path.join("records", "crosscheck_report.csv")
os.makedirs(OUT, exist_ok=True)
os.makedirs("records", exist_ok=True)

STOCKS = {
    "600519": "贵州茅台", "601318": "中国平安", "601398": "工商银行",
    "600900": "长江电力", "000002": "万科A", "600276": "恒瑞医药",
    "002415": "海康威视", "002594": "比亚迪", "600111": "北方稀土",
    "601888": "中国中免",
}
RET_DIFF = 0.005  # 两个数据源的日收益率相差超过 0.5% 就列出来看
FIELDS = "date,open,high,low,close,volume,amount,tradestatus"


def bs_code(code):
    return ("sh." if code.startswith("6") else "sz.") + code


def fetch_baostock(code):
    rs = bs.query_history_k_data_plus(
        bs_code(code), FIELDS, start_date="2019-01-01", end_date="2024-12-31",
        frequency="d", adjustflag="2")  # 2 = 前复权
    if rs.error_code != "0":
        raise RuntimeError(rs.error_msg)
    df = rs.get_data()
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.to_csv(os.path.join(OUT, f"baostock_{code}.csv"), index=False, encoding="utf-8-sig")
    return df


lg = bs.login()
print("BaoStock 登录:", lg.error_msg)

rows, details = [], []
for code, name in STOCKS.items():
    print(f"核对 {code} {name} ...")
    try:
        b = fetch_baostock(code)
    except Exception as e:
        print("  BaoStock 下载失败:", e)
        continue
    a = pd.read_csv(os.path.join(RAW, f"{code}.csv"), parse_dates=["date"])
    suspended = b[b["tradestatus"] == "0"]["date"]
    b = b[b["tradestatus"] != "0"]  # 去掉 BaoStock 里标记为停牌的日子

    only_a = sorted(set(a["date"]) - set(b["date"]))
    only_b = sorted(set(b["date"]) - set(a["date"]))
    m = a.merge(b, on="date", suffixes=("_ak", "_bs")).sort_values("date").reset_index(drop=True)
    m["ret_ak"] = m["close_ak"].pct_change()
    m["ret_bs"] = m["close_bs"].pct_change()
    m["diff"] = (m["ret_ak"] - m["ret_bs"]).abs()
    bad = m[m["diff"] > RET_DIFF]
    ratio = m["close_bs"] / m["close_ak"]
    # BaoStock 成交量单位是"股": 比值约 0.01 说明 AkShare 这只用的是"手"(东方财富), 约 1 说明是"股"(新浪)
    vol_ratio = (m["volume_ak"] / m["volume_bs"].replace(0, float("nan"))).median()
    if vol_ratio < 0.05:
        src = "东方财富(手)"
    elif 0.5 < vol_ratio < 2:
        src = "新浪(股)"
    else:
        src = "无法判断"

    rows.append({
        "代码": code, "名称": name, "AkShare行数": len(a), "BaoStock行数": len(b),
        "BaoStock标记停牌天数": len(suspended),
        "仅AkShare有": len(only_a), "仅BaoStock有": len(only_b),
        "收盘价比值最小": round(ratio.min(), 4), "收盘价比值最大": round(ratio.max(), 4),
        "收益率差异超0.5%天数": len(bad),
        "成交量比值(Ak/Bs)": round(vol_ratio, 4), "推测AkShare来源": src,
    })
    if only_b:
        details.append(f"{code} {name} 仅BaoStock有的日期(AkShare缺): "
                       + ", ".join(d.strftime("%Y-%m-%d") for d in only_b[:10]))
    for _, r in bad.head(10).iterrows():
        details.append(
            f"{code} {name} {r['date'].date()}: AkShare收益 {r['ret_ak']:+.1%} "
            f"(收盘{r['close_ak']}) | BaoStock收益 {r['ret_bs']:+.1%} (收盘{r['close_bs']})")

bs.logout()

report = pd.DataFrame(rows)
report.to_csv(REPORT, index=False, encoding="utf-8-sig")
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", None)
pd.set_option("display.unicode.east_asian_width", True)
print()
print(report.to_string(index=False))
print("\n【差异明细】")
print("\n".join(details) if details else "  没有发现两个数据源差异超过阈值的日子")
print(f"\n报告已保存: {REPORT}")
