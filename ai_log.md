# AI 使用记录

本项目开发过程中使用了两种 AI 工具：Claude（Anthropic，对话式助手）和 TRAE CN（编辑器内的 AI 编程工具），没有使用 Qoder 和 WorkBuddy。AI 生成或修改的代码，我都在自己的电脑上运行自测或相应命令、核对输出后再提交到 Git。以下按时间如实记录。

| 时间 | 工具 | 用途说明 |
|---|---|---|
| 2026-10-16 ~ 10-17 | Claude | 阅读任务书并梳理要求，制定执行计划文档；指导安装 Miniforge、Git，创建 GitHub 私有仓库并推送 |
| 2026-10-18 | Claude | 生成 `download_data.py`（用 AkShare 下载股票池十只和沪深300 的日线前复权数据）、`validate_data.py`（数据校验：缺失值、重复日期、价格异常、涨跌幅异常、相对沪深300 缺少的交易日），并协助解读校验结果 |
| 2026-10-21 ~ 10-23 | Claude | 生成 `cross_check.py`（用 BaoStock 交叉校验 AkShare 数据，发现东方财富接口的前复权结果与新浪、BaoStock 不一致）；联网查证长江电力、海康威视的停牌日期 |
| 2026-10-23 | Claude | 生成 `clean_data.py`（清洗数据，输出 `data/<代码>.csv`，自动记录数据来源与获取日期）；生成回测引擎初版：`config.py`、`run.py`、`backtest/`（data、engine、metrics、report）、`strategies/`（base、trend）、`tests/test_engine.py`，实现 T+1、涨跌停不成交、停牌不成交、佣金与印花税规则和绩效指标 |
| 2026-10-24 | Claude | 生成均值回归（布林带）策略 `strategies/meanrev.py`、`tests/test_strategies.py`、`verify_benchmark.py`（用公开的沪深300 年度涨跌幅核验基准数据，联网查证公开数据） |
| 2026-10-25 | Claude | 编写给 TRAE 的"参数寻优与实验记录"需求说明 |
| 2026-10-25 | TRAE CN | 按需求说明实现 `backtest/records.py`（实验记录自动导出与去重）、`backtest/optimizer.py`（网格寻优、样本内外切分、选最优）、`optimize.py`（命令行），新增 `tests/test_optimizer.py`，修改 `config.py`、`run.py`；检查：运行三个自测和 `optimize.py --strategy all`，实验记录 65 条 |
| 2026-10-26 | Claude | 代码与测试复核（另一次对话中上传项目压缩包，审阅代码、复跑测试，指出选参使用了样本外信息、样本内预热不对称、基准口径等问题）；编写给 TRAE 的第二份需求说明（选参对照、寻优汇总、三折滚动验证） |
| 2026-10-26 | TRAE CN | 按第二份需求说明实现样本内选参对照、`寻优汇总.csv`、三折滚动验证，扩展 `对比结果.csv` 和 `strategy.json`（修改 `optimizer.py`、`tests/test_optimizer.py`）；检查：自测通过，实验记录仍为 65 条 |
| 2026-10-27 | Claude | 编写给 TRAE 的第三份需求说明（多因子打分策略） |
| 2026-10-28 | TRAE CN | 按第三份需求说明新增 `strategies/multifactor.py`（动量、低波动、量能三因子打分），在 `optimizer.py` 增加 16 组参数网格，补充测试；检查：运行自测和 `optimize.py --strategy multifactor` |
| 2026-10-29 | Claude | 编写给 TRAE 的第四份需求说明（报告页、一键启动、依赖文件） |
| 2026-10-29 | TRAE CN | 新增 `app.py`、`backtest/dashboard.py`、`templates/index.html`（Flask 报告页）、`启动.bat`、`requirements.txt`、`tests/test_app.py`；检查：四个自测通过，浏览器打开页面并点击三策略回测和参数寻优 |
| 2026-10-29 ~ 10-31 | Claude | 核对导出的实验记录和 `strategy.json`（独立重算选参规则、样本内对照、寻优汇总，并与 `strategy.json` 对账）；起草 `README.md`、`提交信息.txt`；编写给 TRAE 的第五份需求说明（报告页表格排版） |
| 2026-10-31 ~ 11-01 | TRAE CN | 按第五份需求说明优化报告页表格排版（表格可横向滚动、参数列换行、空值显示、补充说明文字），修改 `templates/index.html` 等；检查：页面显示正常，四个自测通过 |
| 2026-11-01 | Claude | 整理本 AI 使用记录；指导演示录屏和 GitHub 提交 |
| 2026-11-03 | Claude | 在全新克隆上最终复核仓库：核对数据、实验记录、strategy.json 和测试；发现并指出重复和多余文件、缺少演示文件夹、报告页在新版 pandas 下的兼容问题，并给出一行修复（由我手动修改） |

## 备注

1. 分工：Claude 负责数据获取、校验、清洗脚本，回测引擎初版、趋势跟踪和均值回归策略、代码审查与数据核验，以及起草 README、提交信息、本记录和给 TRAE 的需求说明；TRAE 负责参数寻优、实验记录导出、多因子策略、报告页、一键启动和页面排版。
2. 给 TRAE 的需求说明由 Claude 起草，我粘贴到 TRAE 中执行；这些说明文件没有放入仓库。
3. 实验记录的最终版由 `optimize.py --strategy all` 一次运行生成（2026-10-29），共 81 条；`records/`、`strategy/` 下的数据文件均由程序导出，没有手工修改。
4. 过程中的两点说明：TRAE 曾生成一份手写的选参对照说明文档，因不是程序导出的材料，已删除；TRAE 曾想运行项目文件夹之外的临时校准脚本，我选择了拒绝。
5. `README.md`、`提交信息.txt`、本文件由 Claude 起草，我核对修改后定稿。
