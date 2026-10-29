"""网格寻优: 对每个策略的参数组合分别在样本内 / 样本外回测, 写入实验记录并选出最优组合。

除任务书规则选参外, 还提供:
  - select_best_in_sample: 按样本内夏普选参的对照组 (不使用样本外信息)
  - rolling_validation:    样本外三折滚动验证 (检验选中参数是否稳健)
  - build_summary:         寻优汇总 (网格规模、样本外夏普分布、选中组合排名)
对照组与三折验证的回测只做屏幕展示 / 写对比汇总, 不写入实验记录。
"""
import itertools
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

from config import BENCHMARK_NAME, IN_SAMPLE, OUT_SAMPLE
from backtest.data import load_benchmark, load_universe
from backtest.engine import run_backtest
from backtest.metrics import compute_metrics
from backtest.records import METRIC_COLUMNS, log_experiment, params_json
from strategies import build_strategy

# 参数网格: 需要调整搜索范围时直接改这里
# multifactor 的三个因子权重必须成组出现, 用 weights 一次性列出 (w_mom, w_lowvol, w_volume),
# iter_param_grid 会把它展开成三个独立参数; leave / zwin 使用策略默认值。
PARAM_GRIDS = {
    "trend": {"fast": [5, 10, 15, 20, 30], "slow": [30, 40, 60, 90, 120, 200]},
    "meanrev": {"window": [10, 20, 30, 60], "k_in": [1.5, 2.0, 2.5], "k_out": [0, 1, 2]},
    "multifactor": {"lookback": [20, 60],
                    "weights": [(1, 0, 0), (0.5, 0.5, 0), (0.5, 0.25, 0.25), (0.34, 0.33, 0.33)],
                    "enter": [0.3, 0.6]},
}

SELECT_RULE = ("在样本内夏普 > 0 且样本外交易次数 >= 10 的组合中，按样本外夏普从高到低选第一组；"
               "多个策略时，再在各策略最优组合中选样本外夏普最高的一组")

SELECTION_RULE_NOTE = "本规则按任务书要求使用样本外夏普选参，样本外信息参与了选参。"

SELECT_RULE_IN_SAMPLE = ("对照组: 在样本内交易次数 >= 10 且样本内夏普 > 0 的组合中，"
                         "按样本内夏普从高到低选第一组 (不使用样本外信息)")

RULE_OUT = "样本外最优（任务书规则）"
RULE_IN = "样本内最优（对照）"
RULE_BENCH = "基准"

RESULT_COLUMNS = (["策略", "参数"]
                  + ["样本内_" + col for col, _ in METRIC_COLUMNS]
                  + ["样本外_" + col for col, _ in METRIC_COLUMNS])

COMPARISON_COLUMNS = ["策略", "选参规则", "参数",
                      "样本内_总收益", "样本内_年化收益", "样本内_最大回撤", "样本内_夏普",
                      "样本外_总收益", "样本外_年化收益", "样本外_最大回撤", "样本外_夏普"]

SUMMARY_COLUMNS = ["策略", "组合数", "样本外夏普_最大", "样本外夏普_中位数", "样本外夏普_最小",
                   "选中组合（JSON）", "选中组合的样本外夏普排名", "选中组合的样本外卖出笔数"]


def iter_param_grid(strategy):
    """返回该策略所有合法参数组合 (trend 只保留 fast < slow; multifactor 展开权重组)"""
    grid = PARAM_GRIDS[strategy]
    keys = list(grid)
    combos = []
    for values in itertools.product(*(grid[key] for key in keys)):
        params = dict(zip(keys, values))
        if "fast" in params and "slow" in params and params["fast"] >= params["slow"]:
            continue
        if "weights" in params:
            # (w_mom, w_lowvol, w_volume) -> 三个独立参数
            params["w_mom"], params["w_lowvol"], params["w_volume"] = params.pop("weights")
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


def split_out_sample(folds=3, bench=None):
    """把 OUT_SAMPLE 按交易日数量平均切成 folds 段。

    用沪深300的交易日历切分: 各段互不重叠、合起来正好覆盖整个样本外、
    每段交易日数相差不超过 1 天。返回 [(段首日, 段末日), ...]。
    """
    bench = load_benchmark() if bench is None else bench
    days = bench.index[(bench.index >= pd.Timestamp(OUT_SAMPLE[0]))
                       & (bench.index <= pd.Timestamp(OUT_SAMPLE[1]))]
    if len(days) < folds:
        raise ValueError(f"样本外交易日数 ({len(days)}) 少于折数 ({folds})")
    return [(chunk[0], chunk[-1]) for chunk in np.array_split(days, folds)]


def rolling_validation(strategy_name, params, data=None, bench=None, folds=3):
    """样本外 folds 折滚动验证: 每折单独回测 (从空仓开始, 该折之前的数据用于均线预热)。

    返回 {"折数": folds, "各折": [{折, 开始, 结束, 交易日数, 策略总收益, 基准总收益}, ...],
          "稳健": 三段策略总收益是否全部 > 0}。
    """
    data = load_universe() if data is None else data
    bench = load_benchmark() if bench is None else bench
    strategy = build_strategy(strategy_name, params)

    fold_rows = []
    for i, (start, end) in enumerate(split_out_sample(folds, bench), 1):
        result = run_backtest(strategy, data, start, end, bench=bench)
        metrics = compute_metrics(result.nav, result.trades)
        fold_rows.append({
            "折": i, "开始": str(pd.Timestamp(start).date()), "结束": str(pd.Timestamp(end).date()),
            "交易日数": len(result.nav), "策略总收益": metrics["总收益"],
            "基准总收益": float(result.bench_nav.iloc[-1] - 1.0),
        })
    return {"折数": folds, "各折": fold_rows,
            "稳健": all(row["策略总收益"] > 0 for row in fold_rows)}


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


def select_best_in_sample(results):
    """对照组选参: 在"样本内交易次数 >= 10 且样本内夏普 > 0"的组合里选样本内夏普最高的一组。

    与 select_best 的任务书规则相对照, 该规则完全不使用样本外信息;
    没有任何组合满足条件时抛出 ValueError。
    """
    ok = results[(results["样本内_夏普"] > 0) & (results["样本内_交易次数"] >= 10)]
    if ok.empty:
        raise ValueError("没有组合满足 样本内夏普 > 0 且 样本内交易次数 >= 10")
    return ok.sort_values("样本内_夏普", ascending=False).iloc[0]


def metrics_from_row(row, prefix):
    """从结果表的一行取出某个区间 (prefix 为 '样本内_' 或 '样本外_') 的指标字典"""
    return {key: row[prefix + col] for col, key in METRIC_COLUMNS}


def benchmark_metrics(bench, interval):
    """沪深300 买入持有一组区间的指标: 区间首日开盘买入, 期末收盘 (与引擎基准算法一致)"""
    start, end = interval
    calendar = bench.index[(bench.index >= pd.Timestamp(start)) & (bench.index <= pd.Timestamp(end))]
    nav = bench.loc[calendar, "close"] / bench.loc[calendar[0], "open"]
    return compute_metrics(nav)


def _comparison_row(row, rule):
    """把一个选中行整理成对比结果表的一行, 并标上选参规则"""
    result = {col: row[col] for col in COMPARISON_COLUMNS if col in row}
    result["选参规则"] = rule
    return result


def build_comparison(best_rows, control_rows, bench):
    """对比结果表: 每个策略两行 (任务书规则最优 + 样本内对照组), 再加沪深300买入持有一行。

    best_rows / control_rows: 各策略的选中行 (dict 或 Series), control_rows 按"策略"列匹配;
    某个策略没有对照组时只输出任务书规则那一行。
    """
    controls = {row["策略"]: row for row in control_rows}
    rows = []
    for result in best_rows:
        rows.append(_comparison_row(result, RULE_OUT))
        control = controls.get(result["策略"])
        if control is not None:
            rows.append(_comparison_row(control, RULE_IN))

    in_bench = benchmark_metrics(bench, IN_SAMPLE)
    out_bench = benchmark_metrics(bench, OUT_SAMPLE)
    rows.append({
        "策略": f"{BENCHMARK_NAME}买入持有", "选参规则": RULE_BENCH, "参数": "",
        "样本内_总收益": in_bench["总收益"], "样本内_年化收益": in_bench["年化收益"],
        "样本内_最大回撤": in_bench["最大回撤"], "样本内_夏普": in_bench["夏普比率"],
        "样本外_总收益": out_bench["总收益"], "样本外_年化收益": out_bench["年化收益"],
        "样本外_最大回撤": out_bench["最大回撤"], "样本外_夏普": out_bench["夏普比率"],
    })
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)


def export_comparison(best_rows, control_rows, bench, path):
    """写出对比结果 CSV (utf-8-sig), 返回对比结果表"""
    table = build_comparison(best_rows, control_rows, bench)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    table.to_csv(path, index=False, encoding="utf-8-sig")
    return table


def build_summary(best_rows, results_by_strategy):
    """寻优汇总表: 每个策略一行, 汇总网格规模、样本外夏普分布、选中组合及其排名与卖出笔数。

    best_rows: select_best 选出的行列表; results_by_strategy: 策略名 -> 该策略完整结果表。
    """
    rows = []
    for best in best_rows:
        results = results_by_strategy[best["策略"]]
        sharpe = results["样本外_夏普"].astype(float)
        n = len(results)
        rank = int((sharpe > float(best["样本外_夏普"])).sum()) + 1  # 并列时取并列中的小名次
        rows.append({
            "策略": best["策略"], "组合数": n,
            "样本外夏普_最大": float(sharpe.max()),
            "样本外夏普_中位数": float(sharpe.median()),
            "样本外夏普_最小": float(sharpe.min()),
            "选中组合（JSON）": best["参数"],
            "选中组合的样本外夏普排名": f"第{rank}名 / 共{n}组",
            "选中组合的样本外卖出笔数": int(best["样本外_交易次数"]),
        })
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def export_summary(best_rows, results_by_strategy, path):
    """写出寻优汇总 CSV (utf-8-sig), 返回汇总表"""
    table = build_summary(best_rows, results_by_strategy)
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


def control_from_row(row):
    """把样本内对照组的选中行整理成 strategy.json 里 control_in_sample 的内容"""
    if row is None:
        return None
    return {
        "策略类型": row["策略"],
        "参数": json.loads(row["参数"]),
        "样本内指标": _metrics_dict(metrics_from_row(row, "样本内_")),
        "样本外指标": _metrics_dict(metrics_from_row(row, "样本外_")),
    }


def build_strategy_payload(strategy_name, params, in_metrics, out_metrics,
                           control=None, rolling=None, generated_at=None):
    """构造 strategy.json 的内容: 策略类型、参数、样本内/样本外指标、选择规则说明、
    按样本内选参的对照组 (control_in_sample)、三折滚动验证 (rolling_validation)、生成时间"""
    return {
        "策略类型": strategy_name,
        "参数": json.loads(params_json(params)),
        "样本内指标": _metrics_dict(in_metrics),
        "样本外指标": _metrics_dict(out_metrics),
        "选择规则说明": SELECT_RULE,
        "selection_rule": SELECTION_RULE_NOTE,
        "control_in_sample": control,
        "rolling_validation": rolling,
        "生成时间": generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def export_strategy_json(payload, path):
    """写出 strategy.json (utf-8), 返回文件路径"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
