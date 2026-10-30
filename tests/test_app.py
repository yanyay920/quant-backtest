"""绩效报告页自测: python tests/test_app.py
覆盖: 首页 200 与板块标题、导出文件缺失时不崩溃、寻优状态接口、
三策略回测接口 (只用 3 只股票) 且不写实验记录。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402
from backtest.records import RECORDS_FILE  # noqa: E402

SECTION_TITLES = ["概览", "最优策略", "三策略回测", "参数寻优", "数据与口径说明"]


def test_index_ok():
    """首页返回 200, 包含各板块标题"""
    resp = create_app().test_client().get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for title in SECTION_TITLES:
        assert title in html, f"首页缺少板块: {title}"
    print("通过: 首页 200 且包含全部板块标题")


def test_index_missing_exports():
    """导出文件全部缺失时首页仍返回 200, 显示提示而不报错"""
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(records_dir=tmp,
                         strategy_path=os.path.join(tmp, "strategy.json"))
        resp = app.test_client().get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "尚未生成" in html
    print("通过: 导出文件缺失时首页 200 并显示提示")


def test_status_endpoint():
    """寻优状态接口可访问, 返回合法状态"""
    resp = create_app().test_client().get("/api/optimize/status")
    assert resp.status_code == 200
    state = resp.get_json()["state"]
    assert state in ("idle", "running", "done", "error"), state
    print(f"通过: 状态接口 200, 当前状态 {state}")


def test_backtest_api_no_records_write():
    """三策略回测接口 (3 只股票): 返回三个策略的指标, 且实验记录内容完全不变"""
    with open(RECORDS_FILE, "rb") as f:
        before = f.read()

    resp = create_app().test_client().post(
        "/api/backtest", json={"codes": "600519,601318,002415"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"], data.get("error")

    rows = {row["name"]: row for row in data["rows"]}
    for name in ("trend", "meanrev", "multifactor", "沪深300买入持有"):
        assert name in rows, f"缺少 {name} 的结果"
    for name in ("trend", "meanrev", "multifactor"):
        for key in ("总收益", "年化收益", "最大回撤", "夏普比率", "胜率", "交易次数"):
            assert key in rows[name]["metrics"], f"{name} 缺少指标 {key}"
    assert data["chart"].startswith("data:image/png;base64,"), "缺少净值对比图"

    with open(RECORDS_FILE, "rb") as f:
        after = f.read()
    assert before == after, "三策略回测改动了实验记录!"
    print("通过: 三策略回测返回三个策略指标与净值图, 实验记录未变化")


def main():
    test_index_ok()
    test_index_missing_exports()
    test_status_endpoint()
    test_backtest_api_no_records_write()
    print("\n全部通过")


if __name__ == "__main__":
    main()
