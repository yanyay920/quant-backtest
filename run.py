"""命令行入口。例:
  python run.py --strategy trend --params fast=10,slow=30 --start 2019-01-01 --end 2024-12-31
  python run.py --strategy trend --codes 600519,601318      (只回测部分股票)
"""
import argparse
import os
import re

from config import DATA_END, DATA_START, RECORDS_DIR
from backtest.data import load_benchmark, load_universe
from backtest.engine import run_backtest
from backtest.metrics import compute_metrics
from backtest.optimizer import evaluate_intervals
from backtest.report import plot_nav, print_summary
from strategies import STRATEGIES, build_strategy


def parse_params(text):
    """'fast=10,slow=30' -> {'fast': 10, 'slow': 30}"""
    out = {}
    for item in filter(None, (text or "").split(",")):
        key, value = item.split("=")
        for cast in (int, float):
            try:
                value = cast(value)
                break
            except ValueError:
                continue
        out[key.strip()] = value
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="A股量化回测")
    ap.add_argument("--strategy", default="trend", help="策略类型: " + " / ".join(STRATEGIES))
    ap.add_argument("--params", default="", help="策略参数, 如 fast=10,slow=30")
    ap.add_argument("--start", default=DATA_START, help="起始日期 YYYY-MM-DD")
    ap.add_argument("--end", default=DATA_END, help="结束日期 YYYY-MM-DD")
    ap.add_argument("--codes", default="", help="只回测部分股票(逗号分隔), 默认全部十只")
    ap.add_argument("--no-plot", action="store_true", help="不生成净值曲线图")
    ap.add_argument("--no-record", action="store_true", help="不写入实验记录")
    args = ap.parse_args(argv)

    try:
        strategy = build_strategy(args.strategy, parse_params(args.params))
        codes = [c for c in args.codes.split(",") if c] or None
        bench = load_benchmark()
        universe = load_universe(codes)
        result = run_backtest(strategy, universe, args.start, args.end, bench=bench)
    except (ValueError, FileNotFoundError) as e:
        raise SystemExit(f"错误: {e}")

    bench_metrics = compute_metrics(result.bench_nav)
    strat_metrics = compute_metrics(result.nav, result.trades)
    print_summary(result, strat_metrics, bench_metrics)

    if not args.no_record and not codes:
        evaluate_intervals(args.strategy, strategy.params, data=universe, bench=bench)
        print(f"\n实验记录已更新: {os.path.join(RECORDS_DIR, '实验记录.csv')}")

    if not args.no_plot:
        tag = re.sub(r"[^0-9A-Za-z_.=-]+", "_", f"{args.strategy}_{args.params}_{args.start}_{args.end}")
        path = os.path.join(RECORDS_DIR, "charts", f"{tag}.png")
        plot_nav(result, path)
        print(f"\n净值曲线已保存: {path}")
    return result


if __name__ == "__main__":
    main()
