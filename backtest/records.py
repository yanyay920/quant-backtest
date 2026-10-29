"""实验记录自动导出: 把每组的样本内 / 样本外指标写入 records/实验记录.csv"""
import json
import os
from datetime import datetime

import pandas as pd

from config import RECORDS_DIR

RECORDS_FILE = os.path.join(RECORDS_DIR, "实验记录.csv")

# (CSV 列名后缀, compute_metrics 中的键名)
METRIC_COLUMNS = [("总收益", "总收益"), ("年化收益", "年化收益"), ("最大回撤", "最大回撤"),
                  ("夏普", "夏普比率"), ("胜率", "胜率"), ("交易次数", "交易次数")]

COLUMNS = (["实验编号", "记录时间", "策略", "参数"]
           + ["样本内_" + col for col, _ in METRIC_COLUMNS]
           + ["样本外_" + col for col, _ in METRIC_COLUMNS])


def canonical_params(params):
    """把参数整理成便于比较的字典: 键转字符串, 整数值的浮点数转成整数 (2.0 与 2 视为同一参数)。"""
    result = {}
    for key, value in (params or {}).items():
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        result[str(key)] = value
    return result


def params_json(params):
    """参数 -> JSON 字符串 (键排序, 便于去重比较)"""
    return json.dumps(canonical_params(params), sort_keys=True, ensure_ascii=False)


def load_records(path=None):
    """读取实验记录; 文件不存在或为空时返回只有列名的空表"""
    path = path or RECORDS_FILE
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, encoding="utf-8-sig")
    return df.reindex(columns=COLUMNS)


def _metrics_cells(prefix, metrics):
    """把 compute_metrics 的结果转成带区间前缀的 CSV 单元格"""
    return {prefix + col: metrics.get(key, float("nan")) for col, key in METRIC_COLUMNS}


def log_experiment(strategy, params, in_metrics, out_metrics, path=None):
    """记录一次实验, 返回实验编号。

    - 策略和参数完全相同视为同一个实验: 已存在则更新该行的记录时间和指标, 不新增行
    - 参数以键排序的 JSON 字符串保存
    - 文件或 records 目录不存在时自动创建, 编码 utf-8-sig
    - 实验编号从 1 开始递增
    """
    path = path or RECORDS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    records = load_records(path).to_dict("records")
    key = params_json(params)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = {"记录时间": now, "策略": strategy, "参数": key}
    row.update(_metrics_cells("样本内_", in_metrics))
    row.update(_metrics_cells("样本外_", out_metrics))

    found = next((i for i, rec in enumerate(records)
                  if str(rec.get("策略")) == strategy and str(rec.get("参数")) == key), None)
    if found is not None:
        number = int(records[found]["实验编号"])
        records[found].update(row)
        records[found]["实验编号"] = number
    else:
        number = 1 if not records else max(int(rec["实验编号"]) for rec in records) + 1
        row["实验编号"] = number
        records.append(row)

    pd.DataFrame(records, columns=COLUMNS).to_csv(path, index=False, encoding="utf-8-sig")
    return number
