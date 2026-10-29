"""参数寻优命令行入口。例:
  python optimize.py --strategy trend
  python optimize.py --strategy meanrev
  python optimize.py --strategy all      (默认, 两个都跑)
"""
import argparse
import json
import os

import pandas as pd

from config import RECORDS_DIR, ROOT
from backtest.data import load_benchmark, load_universe
from backtest.optimizer import (PARAM_GRIDS, build_strategy_payload, export_comparison,
                                export_strategy_json, metrics_from_row, run_grid_search,
                                select_best)


def _fmt(value, pattern):
    """格式化指标; 缺失值显示为 '-'"""
    return "-" if value != value else pattern.format(value)


def print_top(results, k=5):
    """打印样本外夏普最高的前 k 组"""
    print(f"\n样本外夏普最高的前 {k} 组:")
    top = results.sort_values("样本外_夏普", ascending=False).head(k)
    for rank, (_, row) in enumerate(top.iterrows(), 1):
        print(f"  {rank}. {row['参数']}  "
              f"样本内夏普={_fmt(row['样本内_夏普'], '{:.3f}')}  "
              f"样本外夏普={_fmt(row['样本外_夏普'], '{:.3f}')}  "
              f"样本外总收益={_fmt(row['样本外_总收益'], '{:.2%}')}  "
              f"样本外交易次数={int(row['样本外_交易次数'])}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="参数网格寻优")
    ap.add_argument("--strategy", default="all", choices=["all"] + list(PARAM_GRIDS),
                    help="策略类型: all / trend / meanrev (默认 all)")
    args = ap.parse_args(argv)

    names = list(PARAM_GRIDS) if args.strategy == "all" else [args.strategy]
    data, bench = load_universe(), load_benchmark()

    best_rows = []
    for name in names:
        print(f"\n=== {name} 参数网格寻优 ===")
        results = run_grid_search(name, data, bench, verbose=True)
        print_top(results)
        try:
            best = select_best(results)
        except ValueError as exc:
            print(f"\n错误: {name} {exc}")
            continue
        best_rows.append(best)
        print(f"\n{name} 最优参数: {best['参数']}  "
              f"样本内夏普={_fmt(best['样本内_夏普'], '{:.3f}')}  "
              f"样本外夏普={_fmt(best['样本外_夏普'], '{:.3f}')}")

    if not best_rows:
        raise SystemExit("错误: 没有任何策略找到满足条件的组合, 未生成 对比结果.csv 和 strategy.json")

    comparison_path = os.path.join(RECORDS_DIR, "对比结果.csv")
    export_comparison(pd.DataFrame(best_rows), bench, comparison_path)
    print(f"\n对比结果已保存: {comparison_path}")

    best = max(best_rows, key=lambda row: row["样本外_夏普"])
    payload = build_strategy_payload(
        best["策略"], json.loads(best["参数"]),
        metrics_from_row(best, "样本内_"), metrics_from_row(best, "样本外_"))
    strategy_path = export_strategy_json(payload, os.path.join(ROOT, "strategy", "strategy.json"))
    print(f"全局最优策略已保存: {strategy_path}")
    print(f"全局最优: {best['策略']} {best['参数']}")
    return best_rows


if __name__ == "__main__":
    main()
