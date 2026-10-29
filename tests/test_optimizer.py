"""寻优与实验记录自测: python tests/test_optimizer.py
覆盖: 实验记录去重、最优组合的选择规则、参数网格合法性、strategy.json 必需字段。
"""
import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.optimizer import (build_strategy_payload, export_strategy_json,  # noqa: E402
                                iter_param_grid, select_best)
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


def test_param_grid():
    trend = iter_param_grid("trend")
    assert len(trend) == 29, f"trend 应有 29 组合, 实际 {len(trend)}"
    assert all(p["fast"] < p["slow"] for p in trend), "trend 网格不能出现 fast >= slow"
    assert len({json.dumps(p, sort_keys=True) for p in trend}) == 29, "trend 组合不应重复"

    meanrev = iter_param_grid("meanrev")
    assert len(meanrev) == 36, f"meanrev 应有 36 组合, 实际 {len(meanrev)}"
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
    test_param_grid()
    test_strategy_json_fields()
    print("\n全部通过")
