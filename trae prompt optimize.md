# 给 TRAE 的需求说明：参数寻优 + 实验记录自动导出

## 项目背景（请先阅读现有代码，不要重写）

这是一个 A 股量化回测项目（Python 3.10，pandas）。项目文件夹里已有：

- `config.py`：股票池、费率、初始资金等常量
- `run.py`：命令行入口，例如 `python run.py --strategy trend --params fast=10,slow=30`
- `backtest/data.py`、`backtest/engine.py`（`run_backtest`、`simulate_stock`）、`backtest/metrics.py`（`compute_metrics`）、`backtest/report.py`
- `strategies/`：`base.py`、`trend.py`（双均线，参数 fast / slow）、`meanrev.py`（布林带，参数 window / k_in / k_out）；`strategies/__init__.py` 里的 `STRATEGIES` 字典登记所有策略
- `tests/test_engine.py`、`tests/test_strategies.py`：自测，必须一直通过
- `data/<六位代码>.csv`：十只股票和 000300 的行情（不要修改）

## 硬性约束

1. 不要修改 `backtest/engine.py` 里的撮合规则（次日开盘成交、T+1、涨跌停不成交、停牌不成交、佣金与印花税），不要改动 `data/` 下任何文件。
2. 复用已有的 `run_backtest` 和 `compute_metrics`，不要重新实现回测或指标。
3. 代码按模块拆分，不要把所有逻辑塞进一个文件；函数写中文 docstring。
4. 每次改完运行 `python tests\test_engine.py` 和 `python tests\test_strategies.py`，必须全部通过。

## 要实现的功能

### 1. `config.py` 增加样本内 / 样本外时段

```python
IN_SAMPLE = ("2019-01-01", "2022-12-31")   # 样本内：用来调参
OUT_SAMPLE = ("2023-01-01", "2024-12-31")  # 样本外：只用来检验
```

### 2. `backtest/records.py`：实验记录自动导出

函数 `log_experiment(strategy, params, in_metrics, out_metrics)`：

- 写入 `records/实验记录.csv`（编码 utf-8-sig；文件或 records 文件夹不存在时自动创建）
- 列：实验编号、记录时间、策略、参数（JSON 字符串，键排序）、样本内_总收益、样本内_年化收益、样本内_最大回撤、样本内_夏普、样本内_胜率、样本内_交易次数、样本外_（同样 6 项）
- 去重：策略和参数完全相同视为同一个实验，已存在就更新那一行的指标和时间，不新增行（任务书只统计"策略或参数有实际变化"的实验）
- 实验编号从 1 开始递增

### 3. `backtest/optimizer.py`：网格寻优

- 每个策略的参数网格写在文件顶部的字典里，方便修改：
  - trend：fast ∈ {5, 10, 15, 20, 30}，slow ∈ {30, 40, 60, 90, 120, 200}，只保留 fast < slow 的组合（共 29 组）
  - meanrev：window ∈ {10, 20, 30, 60}，k_in ∈ {1.5, 2.0, 2.5}，k_out ∈ {0, 1, 2}（共 36 组）
- 对每一组参数：分别在 `IN_SAMPLE` 和 `OUT_SAMPLE` 区间跑 `run_backtest` 和 `compute_metrics`（两个区间各自独立回测，从空仓开始），然后调用 `log_experiment` 落一条记录
- 选最优参数：在"样本内夏普 > 0 且样本外交易次数 >= 10"的组合里，选样本外夏普最高的一组（任务书规定"选样本外表现最好的组合"，加条件是防止碰运气）。没有任何组合满足条件时，要明确报错提示
- 返回完整结果表

### 4. 命令行 `optimize.py`（放在项目根目录）

```
python optimize.py --strategy trend
python optimize.py --strategy meanrev
python optimize.py --strategy all      # 默认，两个都跑
```

运行时在屏幕显示进度，并打印"样本外夏普最高的前 5 组"。结束后自动导出：

- `records/实验记录.csv`：所有组合（见第 2 点）
- `records/对比结果.csv`：每个策略的最优参数各一行，加沪深 300 买入持有一行；列包含样本内和样本外的总收益、年化收益、最大回撤、夏普
- `strategy/strategy.json`：全局最优的一组（在各策略的最优里再选样本外夏普最高的），内容包含：策略类型、参数、样本内指标、样本外指标、选择规则说明、生成时间

### 5. 修改 `run.py`：每次回测自动落一条记录

`run.py` 跑完后，用同样的策略和参数，再分别算样本内、样本外指标并调用 `log_experiment`（和 optimize 用同一个函数，所以重复运行同一组参数不会增加行数）。增加 `--no-record` 开关可以关闭。如果用了 `--codes` 只回测部分股票，则不落记录。

### 6. `tests/test_optimizer.py`

至少覆盖：

- `log_experiment` 去重：同一组参数记两次，只有一行
- 选最优的规则：构造几条假结果，验证过滤条件和排序
- 参数网格里没有 fast >= slow 的组合
- `strategy.json` 包含所有必需字段

## 完成后请告诉我

新增和修改了哪些文件，以及我应该运行哪些命令来验证。
