"""结果展示: 控制台汇总表 + 净值曲线图"""
import os

import matplotlib
matplotlib.use("Agg")  # 只保存图片, 不弹窗
import matplotlib.pyplot as plt
import pandas as pd

from config import BENCHMARK_NAME

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "PingFang SC",
                                   "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _fmt(key, v):
    if key in ("总收益", "年化收益", "最大回撤", "胜率"):
        return "-" if v != v else f"{v:.2%}"
    if key == "交易次数":
        return str(int(v))
    return f"{v:.3f}"


def print_summary(result, strat_metrics, bench_metrics):
    keys = ["总收益", "年化收益", "最大回撤", "夏普比率", "胜率", "交易次数", "期末净值"]
    table = pd.DataFrame({
        f"策略({result.strategy})": [_fmt(k, strat_metrics[k]) for k in keys],
        BENCHMARK_NAME + "买入持有": [_fmt(k, bench_metrics[k]) if k != "胜率" and k != "交易次数" else "-"
                                      for k in keys],
    }, index=keys)
    pd.set_option("display.unicode.east_asian_width", True)
    print(f"\n策略: {result.strategy}  参数: {result.params}")
    print(f"回测区间: {result.start} ~ {result.end}")
    print(table.to_string())


def plot_nav(result, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(result.nav.index, result.nav.values, label=f"策略净值 ({result.strategy})")
    ax.plot(result.bench_nav.index, result.bench_nav.values, label=f"{BENCHMARK_NAME}买入持有", alpha=0.85)
    ax.axhline(1.0, color="gray", lw=0.8, ls="--")
    ax.set_title(f"{result.strategy} {result.params}  {result.start} ~ {result.end}")
    ax.set_ylabel("净值 (初始 = 1)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
