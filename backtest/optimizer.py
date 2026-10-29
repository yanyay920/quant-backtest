"""网格寻优: 对每个策略的参数组合分别在样本内 / 样本外回测, 写入实验记录并选出最优组合"""
import itertools
import json
import os
from datetime import datetime

import pandas as pd

from config import BENCHMARK_NAME, IN_SAMPLE, OUT_SAMPLE
from backtest.data import load_benchmark, load_universe
from backtest.engine import run_backtest
from backtest.metrics import compute_metrics
from backtest.records import METRIC_COLUMNS, log_experiment, params_json
from strategies import build_strategy

# 参数网格: 需要调整搜索范围时直接改这里
PARAM_GRIDS = {
    "trend": {"fast": [5, 10, 15, 20, 30], "slow": [30, 40, 60, 90, 120, 200]},
    "meanrev": {"window": [10, 20, 30, 60], "k_in": [1.5, 2.0, 2.5], "k_out": [0, 1, 2]},
}

SELECT_RULE = ("在样本内夏普 > 0 且样本外交易次数 >= 10 的组合中，按样本外夏普从高到低选第一组；"
               "多个策略时，再在各策略最优组合中选样本外夏普最高的一组")

RESULT_COLUMNS = (["策略", "参数"]
                  + ["样本内_" + col for col, _ in METRIC_COLUMNS]
                  + ["样本外_" + col for col, _ in METRIC_COLUMNS])

COMPARISON_COLUMNS = ["策略", "参数",
                      "样本内_总收益", "样本内_年化收益", "样本内_最大回撤", "样本内_夏普",
                      "样本外_总收益", "样本外_年化收益", "样本外_最大回撤", "样本外_夏普"]


def iter_param_grid(strategy):
    """返回该策略所有合法参数组合 (trend 只保留 fast < slow)"""
    grid = PARAM_GRIDS[strategy]
    keys = list(grid)
    combos = []
    for values in itertools.product(*(grid[key] for key in keys)):
        params = dict(zip(keys, values))
        if "fast" in params and "slow" in params and params["fast"] >= params["slow"]:
            continue
        combos.append(params)
    return combos


def evaluate_intervals(strategy_name, params, data=None, bench=None, log=True):
    """在 IN_SAMPLE 和 OUT_SAMPLE 两个区间各自独立回测 (均从空仓开始), 返回 (样本内指标, 样本外指标)。

    log=True 时用同一组策略和参数调用 log_experiment 写入实验记录。
    """
    data = load_universe() if data is None else data
    bench = load_benchmark() if bench is None else bench
    strategy = build_strategy(strategy_name, params)

    in_result = run_backtest(strategy, data, IN_SAMPLE[0], IN_SAMPLE[1], bench=bench)
    out_result = run_backtest(strategy, data, OUT_SAMPLE[0], OUT_SAMPLE[1], bench=bench)
    in_metrics = compute_metrics(in_result.nav, in_result.trades)
    out_metrics = compute_metrics(out_result.nav, out_result.trades)

    if log:
        log_experiment(strategy_name, strategy.params, in_metrics, out_metrics)
    return in_metrics, out_metrics


def _result_row(strategy_name, params, in_metrics, out_metrics):
    """把一组参数的两个区间指标整理成结果表的一行"""
    row = {"策略": strategy_name, "参数": params_json(params)}
    row.update({"样本内_" + col: in_metrics[key] for col, key in METRIC_COLUMNS})
    row.update({"样本外_" + col: out_metrics[key] for col, key in METRIC_COLUMNS})
    return row


def run_grid_search(strategy_name, data=None, bench=None, verbose=True):
    """遍历策略的参数网格, 每组参数回测样本内与样本外并落记录, 返回完整结果表 (DataFrame)。"""
    data = load_universe() if data is None else data
    bench = load_benchmark() if bench is None else bench
    combos = iter_param_grid(strategy_name)
    rows = []
    for i, params in enumerate(combos, 1):
        in_metrics, out_metrics = evaluate_intervals(strategy_name, params, data, bench)
        rows.append(_result_row(strategy_name, params, in_metrics, out_metrics))
        if verbose:
            print(f"  [{i}/{len(combos)}] {params_json(params)}  "
                  f"样本内夏普={in_metrics['夏普比率']:.3f}  "
                  f"样本外夏普={out_metrics['夏普比率']:.3f}  "
                  f"样本外交易次数={out_metrics['交易次数']}")
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def select_best(results):
    """按规则选最优组合, 返回结果表中的一行。

    results: run_grid_search 返回的完整结果表 (DataFrame)。
    先过滤 样本内夏普 > 0 且 样本外交易次数 >= 10, 再取样本外夏普最高的一组;
    没有任何组合满足条件时抛出 ValueError。
    """
    ok = results[(results["样本内_夏普"] > 0) & (results["样本外_交易次数"] >= 10)]
    if ok.empty:
        raise ValueError("没有组合满足 样本内夏普 > 0 且 样本外交易次数 >= 10")
    return ok.sort_values("样本外_夏普", ascending=False).iloc[0]


def metrics_from_row(row, prefix):
    """从结果表的一行取出某个区间 (prefix 为 '样本内_' 或 '样本外_') 的指标字典"""
    return {key: row[prefix + col] for col, key in METRIC_COLUMNS}


def benchmark_metrics(bench, interval):
    """沪深300 买入持有一组区间的指标: 区间首日开盘买入, 期末收盘 (与引擎基准算法一致)"""
    start, end = interval
    calendar = bench.index[(bench.index >= pd.Timestamp(start)) & (bench.index <= pd.Timestamp(end))]
    nav = bench.loc[calendar, "close"] / bench.loc[calendar[0], "open"]
    return compute_metrics(nav)


def build_comparison(best_results, bench):
    """每个策略最优参数各一行, 再加沪深300买入持有一行, 返回对比结果表"""
    rows = []
    for _, result in best_results.iterrows():
        rows.append({col: result[col] for col in COMPARISON_COLUMNS if col in result})

    in_bench = benchmark_metrics(bench, IN_SAMPLE)
    out_bench = benchmark_metrics(bench, OUT_SAMPLE)
    rows.append({
        "策略": f"{BENCHMARK_NAME}买入持有", "参数": "",
        "样本内_总收益": in_bench["总收益"], "样本内_年化收益": in_bench["年化收益"],
        "样本内_最大回撤": in_bench["最大回撤"], "样本内_夏普": in_bench["夏普比率"],
        "样本外_总收益": out_bench["总收益"], "样本外_年化收益": out_bench["年化收益"],
        "样本外_最大回撤": out_bench["最大回撤"], "样本外_夏普": out_bench["夏普比率"],
    })
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)


def export_comparison(best_results, bench, path):
    """写出对比结果 CSV (utf-8-sig), 返回对比结果表"""
    table = build_comparison(best_results, bench)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    table.to_csv(path, index=False, encoding="utf-8-sig")
    return table


def _metrics_dict(metrics):
    """转成适合写入 JSON 的指标字典 (缺失值用 null, numpy 数值转成 Python 类型)"""
    result = {}
    for _, key in METRIC_COLUMNS:
        value = metrics[key]
        if pd.isna(value):
            result[key] = None
        elif key == "交易次数":
            result[key] = int(value)
        else:
            result[key] = float(value)
    return result


def build_strategy_payload(strategy_name, params, in_metrics, out_metrics, generated_at=None):
    """构造 strategy.json 的内容: 策略类型、参数、样本内/样本外指标、选择规则说明、生成时间"""
    return {
        "策略类型": strategy_name,
        "参数": json.loads(params_json(params)),
        "样本内指标": _metrics_dict(in_metrics),
        "样本外指标": _metrics_dict(out_metrics),
        "选择规则说明": SELECT_RULE,
        "生成时间": generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def export_strategy_json(payload, path):
    """写出 strategy.json (utf-8), 返回文件路径"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
