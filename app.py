"""绩效报告页 (Flask)。启动方式:
  python app.py        然后浏览器打开 http://127.0.0.1:5000
  或直接双击 启动.bat

页面结构: 概览 / 最优策略 / 三策略回测 / 参数寻优 / 数据与口径说明。
所有数字来自实际回测结果或 records/、strategy/ 下已导出的文件; 页面不写实验记录。
"""
import contextlib
import io
import os
import threading
import time

from flask import Flask, jsonify, render_template, request

from config import (BENCHMARK_NAME, DATA_END, DATA_START, IN_SAMPLE,
                    INITIAL_CAPITAL, OUT_SAMPLE, RECORDS_DIR, ROOT, STOCKS)
from backtest import dashboard


def create_app(records_dir=RECORDS_DIR, strategy_path=None):
    """应用工厂; 测试时可用 records_dir / strategy_path 指向临时目录模拟文件缺失"""
    app = Flask(__name__)
    strategy_path = strategy_path or os.path.join(ROOT, "strategy", "strategy.json")
    app.add_template_filter(lambda v, k: dashboard.fmt_metric(k, v), "mfmt")

    # 寻优后台任务状态 (同一时间只允许一个任务)
    task = {"state": "idle", "started": None, "elapsed": None, "log": "", "error": ""}
    task_lock = threading.Lock()

    @app.route("/")
    def index():
        overview = {
            "data_range": f"{DATA_START} ~ {DATA_END}",
            "stocks": STOCKS,
            "benchmark": BENCHMARK_NAME,
            "in_sample": f"{IN_SAMPLE[0]} ~ {IN_SAMPLE[1]}",
            "out_sample": f"{OUT_SAMPLE[0]} ~ {OUT_SAMPLE[1]}",
            "capital": INITIAL_CAPITAL,
        }
        return render_template(
            "index.html", overview=overview,
            payload=dashboard.load_strategy_payload(strategy_path),
            tables=dashboard.optimize_tables(records_dir),
            clean_log=dashboard.load_clean_log(records_dir))

    @app.post("/api/backtest")
    def api_backtest():
        """三策略回测 (只展示结果, 不写实验记录); codes 可选, 逗号分隔"""
        body = request.get_json(silent=True) or request.form
        codes = [c for c in (body.get("codes") or "").split(",") if c] or None
        try:
            return jsonify({"ok": True, **dashboard.run_portfolio(codes, records_dir)})
        except (ValueError, FileNotFoundError) as exc:
            return jsonify({"ok": False, "error": str(exc)})

    def _optimize_worker():
        """在后台线程里执行与 python optimize.py --strategy all 相同的代码"""
        import optimize as optimize_cli
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                optimize_cli.main(["--strategy", "all"])
            task["state"] = "done"
        except SystemExit as exc:
            task["state"] = "done" if exc.code in (0, None) else "error"
            task["error"] = "" if exc.code in (0, None) else str(exc)
        except Exception as exc:  # 寻优失败时页面显示错误, 不崩溃
            task["state"] = "error"
            task["error"] = str(exc)
        finally:
            task["elapsed"] = round(time.time() - task["started"], 1)
            task["log"] = buf.getvalue()[-4000:]

    @app.post("/api/optimize")
    def api_optimize():
        """启动参数寻优后台任务; 已有任务在运行时拒绝"""
        with task_lock:
            if task["state"] == "running":
                return jsonify({"ok": False, "error": "已有寻优任务在运行中"})
            task.update(state="running", started=time.time(),
                        elapsed=None, log="", error="")
            threading.Thread(target=_optimize_worker, daemon=True).start()
        return jsonify({"ok": True})

    @app.get("/api/optimize/status")
    def api_optimize_status():
        """轮询寻优状态: idle / running / done / error + 耗时"""
        state = dict(task)
        if state["state"] == "running" and state["started"]:
            state["elapsed"] = round(time.time() - state["started"], 1)
        state.pop("started", None)
        return jsonify(state)

    @app.get("/api/tables")
    def api_tables():
        """寻优完成后刷新表格: 对比结果 / 寻优汇总 / 样本外夏普前 10 条记录 / 总条数"""
        return jsonify(dashboard.optimize_tables(records_dir))

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
