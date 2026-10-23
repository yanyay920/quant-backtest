"""读取 data/<六位代码>.csv (列: date,open,high,low,close,volume)"""
import os

import pandas as pd

from config import BENCHMARK, DATA_DIR, STOCKS


def load_stock(code):
    path = os.path.join(DATA_DIR, f"{code}.csv")
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def load_universe(codes=None):
    codes = list(codes) if codes else list(STOCKS)
    return {c: load_stock(c) for c in codes}


def load_benchmark():
    return load_stock(BENCHMARK)
