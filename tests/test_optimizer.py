"""寻优与实验记录自测: python tests/test_optimizer.py
覆盖: 实验记录去重、最优组合的选择规则 (任务书规则 + 样本内对照)、参数网格合法性、
strategy.json 必需字段、三折切分、寻优汇总统计。
"""
import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUT_SAMPLE  # noqa: E402
from backtest.data import load_benchmark  # noqa: E402
from backtest.optimizer import (build_strategy_payload, build_summary, export_strategy_json,  # noqa: E402
                                iter_param_grid, select_best, select_best_in_sample,
                                split_out_sample)
from backtest.records import COLUMNS, load_records, log_experiment  # noqa: E402


def metrics(sharpe=1.0, n_trades=12, total=0.10):
    """构造 compute_metrics 风格的假指标"""
    return {"总收益": total, "年化收益": 0.05, "最大回撤": -0.20,
            "夏普比率": sharpe, "胜率": 0.5, "交易次数": n_trades, "期末净值": 1 + total}


def test_log_experiment_dedup():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "records", "实验记录.csv")
        first = log_experiment("trend", {"fast": 10, "slow": 30}, metrics(), metrics(), path=path)
        again = log_experiment("trend", {"slow": 30, "fast": 10}, metrics(sharpe=2.0), metrics(), path=path)
        df = load_records(path)
        assert len(df) == 1, "策略和参数相同, 重复记录应只保留一行"
        assert first == again == 1, "同一实验应保持同一个实验编号"
        assert abs(float(df.iloc[0]["样本内_夏普"]) - 2.0) < 1e-9, "重复记录时应更新指标"
        assert list(df.columns) == COLUMNS, "列必须与任务书一致"

        # 整数值的浮点参数 (2.0) 与整数参数 (2) 视为同一组
        third = log_experiment("meanrev", {"window": 20, "k_in": 2.0, "k_out": 0},
                               metrics(), metrics(), path=path)
        fourth = log_experiment("meanrev", {"window": 20, "k_in": 2, "k_out": 0},
                                metrics(), metrics(), path=path)
        assert third == fourth == 2 and len(load_records(path)) == 2
        assert os.path.exists(path), "records 目录和文件应自动创建"
    print("通过: 实验记录去重、编号递增、自动建文件")


def test_select_best_rule():
    rows = pd.DataFrame([
        # 参数 A: 两个条件都满足, 样本外夏普 2.0 -> 应被选中
        {"参数": "A", "样本内_夏普": 1.0, "样本外_夏普": 2.0, "样本外_交易次数": 20},
        # 参数 B: 样本外夏普最高, 但样本内夏普 <= 0 -> 应被过滤
        {"参数": "B", "样本内_夏普": -0.5, "样本外_夏普": 3.0, "样本外_交易次数": 30},
        # 参数 C: 样本内夏普和样本外夏普都不错, 但样本外交易次数不足 -> 应被过滤
        {"参数": "C", "样本内_夏普": 1.0, "样本外_夏普": 2.5, "样本外_交易次数": 5},
        # 参数 D: 两个条件都满足, 但样本外夏普低于 A
        {"参数": "D", "样本内_夏普": 0.5, "样本外_夏普": 1.5, "样本外_交易次数": 10},
    ])
    best = select_best(rows)
    assert best["参数"] == "A", "应在过滤后按样本外夏普降序选第一组"

    none_ok = rows.copy()
    none_ok["样本内_夏普"] = 0.0
    try:
        select_best(none_ok)
        raise AssertionError("没有任何组合满足条件时应报错")
    except ValueError:
        pass
    print("通过: 选最优的过滤条件与排序")


def test_select_best_in_sample_rule():
    rows = pd.DataFrame([
        # 参数 A: 样本内夏普最高且条件满足 -> 应被选中 (尽管样本外夏普最低)
        {"参数": "A", "样本内_夏普": 2.0, "样本内_交易次数": 20, "样本外_夏普": 0.1, "样本外_交易次数": 3},
        # 参数 B: 样本内夏普更高, 但样本内交易次数不足 -> 应被过滤
        {"参数": "B", "样本内_夏普": 3.0, "样本内_交易次数": 5, "样本外_夏普": 2.0, "样本外_交易次数": 30},
        # 参数 C: 样本内夏普 <= 0 -> 应被过滤
        {"参数": "C", "样本内_夏普": -0.5, "样本内_交易次数": 30, "样本外_夏普": 3.0, "样本外_交易次数": 30},
        # 参数 D: 条件满足, 但样本内夏普低于 A (样本外夏普高于 A, 不能因为它被选中)
        {"参数": "D", "样本内_夏普": 1.0, "样本内_交易次数": 12, "样本外_夏普": 2.5, "样本外_交易次数": 11},
    ])
    best = select_best_in_sample(rows)
    assert best["参数"] == "A", "应在过滤后按样本内夏普降序选第一组, 完全不看样本外指标"

    none_ok = rows.copy()
    none_ok["样本内_夏普"] = 0.0
    try:
        select_best_in_sample(none_ok)
        raise AssertionError("没有任何组合满足条件时应报错")
    except ValueError:
        pass
    print("通过: 样本内对照选参的过滤条件与排序")


def test_split_out_sample():
    folds = split_out_sample(3)
    assert len(folds) == 3, "应切成 3 段"

    days = load_benchmark().index
    out_days = days[(days >= pd.Timestamp(OUT_SAMPLE[0])) & (days <= pd.Timestamp(OUT_SAMPLE[1]))]
    counts = [len(out_days[(out_days >= start) & (out_days <= end)]) for start, end in folds]
    assert sum(counts) == len(out_days), "三段应合起来覆盖完整样本外"
    assert max(counts) - min(counts) <= 1, f"每段交易日数相差不超过 1 天, 实际 {counts}"
    for (s1, e1), (s2, e2) in zip(folds, folds[1:]):
        assert e1 < s2, "三段互不重叠"
    assert folds[0][0] == out_days[0] and folds[-1][1] == out_days[-1], "首尾应与样本外对齐"
    print("通过: 三折切分互不重叠、覆盖完整样本外、段间交易日数相差 <= 1")


def test_build_summary_stats():
    def frame(strategy):
        return pd.DataFrame([
            {"策略": strategy, "参数": json.dumps({"fast": 10, "slow": 30}), "样本外_夏普": 1.0, "样本外_交易次数": 12},
            {"策略": strategy, "参数": json.dumps({"fast": 20, "slow": 60}), "样本外_夏普": 3.0, "样本外_交易次数": 15},
            {"策略": strategy, "参数": json.dumps({"fast": 5, "slow": 40}), "样本外_夏普": 2.0, "样本外_交易次数": 11},
            {"策略": strategy, "参数": json.dumps({"fast": 30, "slow": 200}), "样本外_夏普": 0.5, "样本外_交易次数": 20},
        ])

    trend_results, meanrev_results = frame("trend"), frame("meanrev")
    summary = build_summary([trend_results.iloc[1], meanrev_results.iloc[2]],
                            {"trend": trend_results, "meanrev": meanrev_results})
    assert list(summary["策略"]) == ["trend", "meanrev"]

    top = summary.iloc[0]
    assert top["组合数"] == 4
    assert abs(top["样本外夏普_最大"] - 3.0) < 1e-9
    assert abs(top["样本外夏普_中位数"] - 1.5) < 1e-9, "中位数应为 (1.0 + 2.0) / 2 = 1.5"
    assert abs(top["样本外夏普_最小"] - 0.5) < 1e-9
    assert json.loads(top["选中组合（JSON）"]) == {"fast": 20, "slow": 60}
    assert top["选中组合的样本外夏普排名"] == "第1名 / 共4组"
    assert top["选中组合的样本外卖出笔数"] == 15

    second = summary.iloc[1]  # 选中的是样本外夏普 2.0 的一组, 比它高的只有 3.0 -> 第 2 名
    assert second["选中组合的样本外夏普排名"] == "第2名 / 共4组"
    assert second["选中组合的样本外卖出笔数"] == 11
    print("通过: 寻优汇总的最大 / 中位数 / 最小值与排名计算")


def test_param_grid():
    trend = iter_param_grid("trend")
    assert len(trend) == 29, f"trend 应有 29 组合, 实际 {len(trend)}"
    assert all(p["fast"] < p["slow"] for p in trend), "trend 网格不能出现 fast >= slow"
    assert len({json.dumps(p, sort_keys=True) for p in trend}) == 29, "trend 组合不应重复"

    meanrev = iter_param_grid("meanrev")
    assert len(meanrev) == 36, f"meanrev 应有 36 组合, 实际 {len(meanrev)}"

    multifactor = iter_param_grid("multifactor")
    assert len(multifactor) == 16, f"multifactor 应有 16 组合, 实际 {len(multifactor)}"
    assert len({json.dumps(p, sort_keys=True) for p in multifactor}) == 16, "multifactor 组合不应重复"
    assert all("weights" not in p and {"w_mom", "w_lowvol", "w_volume"} <= set(p)
               for p in multifactor), "weights 应展开成三个独立权重参数"
    assert ({(p["w_mom"], p["w_lowvol"], p["w_volume"]) for p in multifactor}
            == {(1, 0, 0), (0.5, 0.5, 0), (0.5, 0.25, 0.25), (0.34, 0.33, 0.33)}), "权重组不符合任务书"
    assert len(trend) + len(meanrev) + len(multifactor) == 81, "三个策略合计应有 81 组合"
    print("通过: 参数网格数量与 fast < slow 过滤")


def test_strategy_json_fields():
    payload = build_strategy_payload("trend", {"fast": 10, "slow": 30},
                                     metrics(), metrics(sharpe=1.5, n_trades=np.int64(12)))
    required = ["策略类型", "参数", "样本内指标", "样本外指标", "选择规则说明", "生成时间"]
    for key in required:
        assert key in payload, f"strategy.json 缺少字段: {key}"

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "strategy", "strategy.json")
        export_strategy_json(payload, path)
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        assert all(key in saved for key in required)
        assert saved["参数"] == {"fast": 10, "slow": 30}
        assert saved["样本外指标"]["夏普比率"] == 1.5
    print("通过: strategy.json 必需字段与导出")


if __name__ == "__main__":
    test_log_experiment_dedup()
    test_select_best_rule()
    test_select_best_in_sample_rule()
    test_split_out_sample()
    test_build_summary_stats()
    test_param_grid()
    test_strategy_json_fields()
    print("\n全部通过")
