# A 股量化回测系统

对固定十只 A 股（2019-01-01 ~ 2024-12-31，日线前复权）回测三种策略：趋势跟踪（双均线）、均值回复（布林带）、多因子打分。支持命令行回测、网格寻优（样本内 / 样本外切分）、实验记录自动导出和 Flask 绩效报告页。

## 一、运行（10 分钟内）

环境：Windows，Python 3.10+。

1. 安装依赖：`pip install -r requirements.txt`（运行只需要 pandas、matplotlib、flask；akshare、baostock 只用于重新下载和校验数据）
2. 双击 `启动.bat`，浏览器自动打开 http://127.0.0.1:5000，点"运行三策略回测"和"运行参数寻优"即可。
3. 或用命令行：

```
python run.py --strategy trend --params fast=20,slow=200 --start 2019-01-01 --end 2024-12-31
python optimize.py --strategy all
python app.py
```

`run.py` 每次回测会自动写入 `records/实验记录.csv`（策略和参数相同只记一行），加 `--no-record` 可关闭。自测：运行 `tests/` 下的四个 `test_*.py`。

## 二、目录

```
app.py  启动.bat  run.py  optimize.py  config.py  requirements.txt
backtest/    data.py 读行情 | engine.py 撮合 | metrics.py 绩效 | records.py 实验记录 | optimizer.py 寻优 | report.py dashboard.py 展示
strategies/  trend.py  meanrev.py  multifactor.py（在 __init__.py 登记）
data/        十只股票和沪深300 的日线 CSV（date,open,high,low,close,volume）
records/     实验记录.csv  对比结果.csv  寻优汇总.csv  数据校验与清洗记录
strategy/    strategy.json（最优策略配置）
tests/  templates/  demo/  ai_log.md  提交信息.txt
download_data.py  cross_check.py  validate_data.py  clean_data.py  verify_benchmark.py  数据获取、校验、清洗、核验脚本
```

## 三、数据流转

```
AkShare / BaoStock --下载、交叉校验--> clean_data.py --> data/<代码>.csv
data/*.csv --> backtest/data.py --> strategies/*.py（每日收盘后给出 0/1 信号）
           --> backtest/engine.py（次日开盘撮合）--> backtest/metrics.py（绩效指标）
run.py / optimize.py / app.py 调用以上三层
           --> records/*.csv、strategy/strategy.json、报告页
```

## 四、撮合规则（任务书规定）

信号当日收盘后计算、次日开盘价成交；T+1；涨停开盘不买、跌停开盘不卖；停牌不交易；佣金万 2.5（最低 5 元）、卖出印花税万 5；初始资金 100 万，平均分给十只股票。

## 五、最优策略（strategy/strategy.json）

趋势跟踪 fast=20, slow=200：样本内（2019–2022）夏普 0.772，样本外（2023–2024）夏普 0.638，样本外总收益 10.33%（沪深 300 同期 1.81%）。三折滚动验证判定为"不稳健"。

## 六、口径与局限

- 选参按任务书"选样本外表现最好的组合"，样本外信息参与了选参；按样本内选参的对照结果见 `records/对比结果.csv`。
- 基准是沪深 300 价格指数（不含分红），股票用前复权价格（含分红）；空仓资金按零利息计。
- 数据从 2019-01-02 起，长均线在样本内有预热期，样本外没有。
- 每只股票独立使用 1/10 资金，多因子是单只股票的时间序列打分，没有做股票之间的横向选股；买入按 100 股整数倍。

AI 工具使用记录见 `ai_log.md`。
