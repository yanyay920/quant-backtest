# AI 使用记录

本项目开发过程中使用了下列 AI 工具。AI 生成的代码，我会在自己的电脑上运行、核对结果后再提交到 Git。以下按时间如实记录。

| 时间 | 工具 | 用途说明 |
|---|---|---|
| 2026-10-16 ~ 10-17 | Claude | 阅读任务书并梳理要求，制定执行计划文档；指导安装 Miniforge、Git，创建 GitHub 私有仓库并推送 |
| 2026-10-18 | Claude | 生成 `download_data.py`：用 AkShare 下载股票池十只和沪深300的日线前复权数据 |
| 2026-10-18 | Claude | 生成 `validate_data.py`：数据校验脚本（缺失值、重复日期、价格异常、涨跌幅异常、相对沪深300缺少的交易日），并协助解读校验结果 |
| 2026-10-21 ~ 10-23 | Claude | 生成 `cross_check.py`：用 BaoStock 交叉校验 AkShare 数据，发现东方财富接口的前复权结果与新浪、BaoStock 不一致；联网查证长江电力、海康威视的停牌日期 |
| 2026-10-23 | Claude | 生成 `clean_data.py`：清洗数据并输出 `data/<代码>.csv`，自动记录数据来源与获取日期 |
| 2026-10-23 | Claude | 生成回测引擎 v1：`config.py`、`run.py`、`backtest/`（data、engine、metrics、report）、`strategies/`（base、trend）、`tests/test_engine.py`；实现 T+1、涨跌停不成交、停牌不成交、佣金与印花税规则，以及年化收益、最大回撤、夏普、胜率 |
| 2026-10-23 | Claude | 生成均值回归（布林带）策略 `strategies/meanrev.py`、`tests/test_strategies.py`、`verify_benchmark.py`（用公开年度涨幅核验沪深300数据） |
| （之后补充） | TRAE | 使用 TRAE 时在这里继续添加：时间 / 做了什么 / 提示词要点 / 我如何检查结果 |

## 备注

- 每次使用 AI 后，在这里补一行；没有用过的工具不要写。
