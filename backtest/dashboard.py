"""绩效报告页的数据与绘图函数 (供 app.py 调用)。

页面上的所有数字都来自这里的实际运行结果或 records/、strategy/ 下已导出的文件。
三策略回测只做回测和指标计算, 不写实验记录 (不调用 log_experiment / evaluate_intervals)。
"""
import base64
import io
import json
import os

import pandas as pd

from config import BENCHMARK_NAME, DATA_END, DATA_START, RECORDS_DIR
from backtest.data import load_benchmark, load_universe
from backtest.engine import run_backtest
from backtest.metrics import compute_metrics
from backtest.records import load_records
from backtest.report import _fmt, plt  # 复用已配置好中文字体的 pyplot
from strategies import STRATEGIES, build_strategy

METRIC_KEYS = ["总收益", "年化收益", "最大回撤", "夏普比率", "胜率", "交易次数"]


def fmt_metric(key, value):
    """指标格式化; 缺失值 (None / NaN) 显示为 '-'"""
    if value is None or value != value:
        return "-"
    return _fmt(key, value)


def format_metrics(metrics):
    """compute_metrics 的结果 -> {指标名: 显示字符串}"""
    return {key: fmt_metric(key, metrics.get(key)) for key in METRIC_KEYS}


def _format_table(df):
    """把结果表格式化成便于展示的字符串表 (收益/回撤/胜率用百分比)"""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            continue
        if any(word in col for word in ("收益", "回撤", "胜率")):
            df[col] = df[col].map(lambda v: "-" if pd.isna(v) else f"{v:.2%}")
        elif "夏普" in col:
            df[col] = df[col].map(lambda v: "-" if pd.isna(v) else f"{v:.3f}")
        elif any(word in col for word in ("次数", "笔数", "组合数", "编号", "交易日数")):
            df[col] = df[col].map(lambda v: "-" if pd.isna(v) else str(int(v)))
    return df


def _table_html(df):
    """DataFrame -> HTML 表格 (单元格内容已做 HTML 转义)"""
    return _format_table(df).to_html(classes="data", index=False, border=0, escape=True)


def load_best_params(records_dir=RECORDS_DIR):
    """从 records/寻优汇总.csv 读每个策略的选中参数; 文件缺失或解析失败时返回 {}"""
    path = os.path.join(records_dir, "寻优汇总.csv")
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        return {row["策略"]: json.loads(row["选中组合（JSON）"]) for _, row in df.iterrows()}
    except (FileNotFoundError, KeyError, ValueError):
        return {}


def load_strategy_payload(path):
    """读取 strategy/strategy.json; 不存在时返回 None (页面显示提示而不是报错)"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def load_clean_log(records_dir=RECORDS_DIR):
    """读取 records/clean_log.txt; 不存在时返回 None"""
    try:
        with open(os.path.join(records_dir, "clean_log.txt"), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def optimize_tables(records_dir=RECORDS_DIR):
    """参数寻优板块的表格: 对比结果、寻优汇总、样本外夏普前 10 条实验记录、记录总条数。

    文件不存在时对应项为 None, 由页面显示"尚未生成"提示。
    """
    out = {"comparison": None, "summary": None, "top10": None, "total": None}
    try:
        out["comparison"] = _table_html(
            pd.read_csv(os.path.join(records_dir, "对比结果.csv"), encoding="utf-8-sig"))
    except FileNotFoundError:
        pass
    try:
        out["summary"] = _table_html(
            pd.read_csv(os.path.join(records_dir, "寻优汇总.csv"), encoding="utf-8-sig"))
    except FileNotFoundError:
        pass
    records = load_records(os.path.join(records_dir, "实验记录.csv"))
    if len(records):
        out["total"] = len(records)
        top = records.sort_values("样本外_夏普", ascending=False).head(10)
        out["top10"] = _table_html(top)
    return out


def nav_chart_base64(navs, bench_nav, title):
    """多策略净值对比图 -> base64 PNG (内存中生成, 不落盘)。navs: {名称: 净值Series}"""
    fig, ax = plt.subplots(figsize=(10, 5))
    for name, nav in navs.items():
        ax.plot(nav.index, nav.values, label=f"策略净值 ({name})")
    ax.plot(bench_nav.index, bench_nav.values,
            label=f"{BENCHMARK_NAME}买入持有", alpha=0.85, color="black")
    ax.axhline(1.0, color="gray", lw=0.8, ls="--")
    ax.set_title(title)
    ax.set_ylabel("净值 (初始 = 1)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def run_portfolio(codes=None, records_dir=RECORDS_DIR):
    """三策略全区间回测 (只展示, 不写实验记录)。

    每个策略用 records/寻优汇总.csv 里的选中参数, 缺失时用策略默认参数。
    返回 {rows: [{name, params, metrics(已格式化)}...], bench: 基准指标, chart: base64,
          start, end}; 最后带一行沪深300买入持有。
    """
    best = load_best_params(records_dir)
    bench = load_benchmark()
    universe = load_universe(codes)

    rows, navs = [], {}
    bench_nav = None
    for name in STRATEGIES:
        params = best.get(name) or dict(STRATEGIES[name]().params)
        result = run_backtest(build_strategy(name, params), universe,
                              DATA_START, DATA_END, bench=bench)
        metrics = compute_metrics(result.nav, result.trades)
        params_text = ", ".join(f"{k}={v}" for k, v in result.params.items())
        rows.append({"name": name, "params": params_text,
                     "metrics": format_metrics(metrics)})
        navs[name] = result.nav
        bench_nav = result.bench_nav

    bench_metrics = compute_metrics(bench_nav)
    bench_metrics["胜率"] = float("nan")
    bench_metrics["交易次数"] = float("nan")
    rows.append({"name": f"{BENCHMARK_NAME}买入持有", "params": "基准",
                 "metrics": format_metrics(bench_metrics)})

    chart = nav_chart_base64(navs, bench_nav, f"三策略净值对比 {DATA_START} ~ {DATA_END}")
    return {"rows": rows, "chart": chart, "start": DATA_START, "end": DATA_END}
