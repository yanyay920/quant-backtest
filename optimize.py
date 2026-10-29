"""参数寻优命令行入口。例:
  python optimize.py --strategy trend
  python optimize.py --strategy meanrev
  python optimize.py --strategy multifactor
  python optimize.py --strategy all      (默认, 三个都跑)
"""
import argparse
import json
import os

from config import RECORDS_DIR, ROOT
from backtest.data import load_benchmark, load_universe
from backtest.optimizer import (PARAM_GRIDS, build_strategy_payload, control_from_row,
                                export_comparison, export_strategy_json, export_summary,
                                metrics_from_row, rolling_validation, run_grid_search,
                                select_best, select_best_in_sample)


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


def print_rolling(label, rolling):
    """打印一组三折滚动验证的结果"""
    print(f"  {label}:")
    for fold in rolling["各折"]:
        print(f"    第{fold['折']}折 {fold['开始']}~{fold['结束']} ({fold['交易日数']}个交易日)  "
              f"策略总收益={fold['策略总收益']:+.2%}  沪深300={fold['基准总收益']:+.2%}")
    print(f"    判定: {'稳健' if rolling['稳健'] else '不稳健'}"
          f" (三段策略总收益全部 > 0 才算稳健)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="参数网格寻优")
    ap.add_argument("--strategy", default="all", choices=["all"] + list(PARAM_GRIDS),
                    help="策略类型: all / trend / meanrev / multifactor (默认 all)")
    args = ap.parse_args(argv)

    names = list(PARAM_GRIDS) if args.strategy == "all" else [args.strategy]
    data, bench = load_universe(), load_benchmark()

    best_rows, control_rows = [], []
    results_by_strategy = {}
    for name in names:
        print(f"\n=== {name} 参数网格寻优 ===")
        results = run_grid_search(name, data, bench, verbose=True)
        results_by_strategy[name] = results
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

        try:
            control = select_best_in_sample(results)
        except ValueError as exc:
            print(f"警告: {name} 选不出样本内对照组 ({exc})")
            continue
        control_rows.append(control)
        print(f"{name} 对照参数 (样本内最优): {control['参数']}  "
              f"样本内夏普={_fmt(control['样本内_夏普'], '{:.3f}')}  "
              f"样本外夏普={_fmt(control['样本外_夏普'], '{:.3f}')}")

    if not best_rows:
        raise SystemExit("错误: 没有任何策略找到满足条件的组合, 未生成 对比结果.csv 和 strategy.json")

    best = max(best_rows, key=lambda row: row["样本外_夏普"])

    # 三折滚动验证: 全局最优 + 每个策略的样本内对照组 (只打印, 不写实验记录)
    print("\n=== 三折滚动验证 (样本外按交易日平均切 3 段, 每段从空仓独立回测) ===")
    global_rolling = rolling_validation(best["策略"], json.loads(best["参数"]), data, bench)
    print_rolling(f"全局最优 {best['策略']} {best['参数']}", global_rolling)
    for control in control_rows:
        control_rolling = rolling_validation(control["策略"], json.loads(control["参数"]), data, bench)
        print_rolling(f"{control['策略']} 样本内对照 {control['参数']}", control_rolling)

    comparison_path = os.path.join(RECORDS_DIR, "对比结果.csv")
    export_comparison(best_rows, control_rows, bench, comparison_path)
    print(f"\n对比结果已保存: {comparison_path}")

    summary_path = os.path.join(RECORDS_DIR, "寻优汇总.csv")
    export_summary(best_rows, results_by_strategy, summary_path)
    print(f"寻优汇总已保存: {summary_path}")

    control_best = next((row for row in control_rows if row["策略"] == best["策略"]), None)
    payload = build_strategy_payload(
        best["策略"], json.loads(best["参数"]),
        metrics_from_row(best, "样本内_"), metrics_from_row(best, "样本外_"),
        control=control_from_row(control_best), rolling=global_rolling)
    strategy_path = export_strategy_json(payload, os.path.join(ROOT, "strategy", "strategy.json"))
    print(f"全局最优策略已保存: {strategy_path}")
    print(f"全局最优: {best['策略']} {best['参数']}")
    return best_rows


if __name__ == "__main__":
    main()
