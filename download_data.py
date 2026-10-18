"""下载股票池十只 + 沪深300 的日线前复权数据 (2019-01-01 ~ 2024-12-31)
数据来源: AkShare (东方财富接口, 失败时自动改用新浪接口)
保存位置: data/raw/<代码>.csv
"""
import os
import time

import akshare as ak
import pandas as pd

START, END = "20190101", "20241231"
OUT = os.path.join("data", "raw")
os.makedirs(OUT, exist_ok=True)

STOCKS = {
    "600519": "贵州茅台", "601318": "中国平安", "601398": "工商银行",
    "600900": "长江电力", "000002": "万科A", "600276": "恒瑞医药",
    "002415": "海康威视", "002594": "比亚迪", "600111": "北方稀土",
    "601888": "中国中免",
}
CN = {"日期": "date", "开盘": "open", "收盘": "close", "最高": "high",
      "最低": "low", "成交量": "volume", "成交额": "amount"}
COLS = ["date", "open", "high", "low", "close", "volume", "amount"]


def prefix(code):
    return ("sh" if code.startswith("6") else "sz") + code


def fetch_stock(code):
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                start_date=START, end_date=END, adjust="qfq")
        return df.rename(columns=CN)
    except Exception as e:
        print("  东方财富接口失败, 改用新浪:", e)
        return ak.stock_zh_a_daily(symbol=prefix(code), start_date=START,
                                   end_date=END, adjust="qfq")


def fetch_index():
    try:
        df = ak.index_zh_a_hist(symbol="000300", period="daily",
                                start_date=START, end_date=END)
        return df.rename(columns=CN)
    except Exception as e:
        print("  指数接口失败, 改用新浪:", e)
        df = ak.stock_zh_index_daily(symbol="sh000300")
        df["date"] = pd.to_datetime(df["date"])
        return df[(df["date"] >= "2019-01-01") & (df["date"] <= "2024-12-31")]


def save(df, code):
    df = df[[c for c in COLS if c in df.columns]]
    path = os.path.join(OUT, f"{code}.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  已保存 {path}, 共 {len(df)} 行")


jobs = list(STOCKS.items()) + [("000300", "沪深300")]
for code, name in jobs:
    print(f"下载 {code} {name} ...")
    try:
        df = fetch_index() if code == "000300" else fetch_stock(code)
        save(df, code)
    except Exception as e:
        print("  失败:", e)
    time.sleep(1)
print("完成。")
