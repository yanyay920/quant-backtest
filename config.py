"""全局配置: 股票池、费率、撮合规则常量 (任务书规定, 不得更改)"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
RECORDS_DIR = os.path.join(ROOT, "records")

STOCKS = {  # 固定股票池十只
    "600519": "贵州茅台", "601318": "中国平安", "601398": "工商银行",
    "600900": "长江电力", "000002": "万科A", "600276": "恒瑞医药",
    "002415": "海康威视", "002594": "比亚迪", "600111": "北方稀土",
    "601888": "中国中免",
}
BENCHMARK = "000300"  # 业绩比较基准: 沪深300 买入持有
BENCHMARK_NAME = "沪深300"

DATA_START, DATA_END = "2019-01-01", "2024-12-31"

INITIAL_CAPITAL = 1_000_000   # 初始资金一百万元
COMMISSION_RATE = 0.00025     # 佣金 万分之2.5 (买卖双向)
COMMISSION_MIN = 5.0          # 佣金最低 5 元
STAMP_TAX_RATE = 0.0005       # 印花税 万分之5 (仅卖出)
LOT_SIZE = 100                # 买入按 100 股整数倍 (A股一手; 任务书未规定, 此为通用做法)
LIMIT_PCT = 0.10              # 十只股票均为主板, 涨跌停幅度 10%
LIMIT_TOL = 0.003             # 价格四舍五入的容差: 开盘涨跌幅达到 9.7% 即按涨跌停处理
TRADING_DAYS = 252            # 夏普比率年化用
