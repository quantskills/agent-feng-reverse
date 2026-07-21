"""
峰哥反向指标 — 自动跟踪流水线
================================
一站式执行：采集 → 分析 → 存储 → 验证 → 绘图 → 报告

可用作 cron 定时任务：
    python auto_track.py --input weibo_data.json
    python auto_track.py --interactive
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows terminal encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "gb2312", "cp936"):
    sys.stdout.reconfigure(encoding="utf-8")

from scripts.signal_store import init_db, save_signal_from_analysis, get_signal_stats
from scripts.analyze_sentiment import analyze_sentiment, generate_reverse_signal
from scripts.generate_report import generate_report
from scripts.backtest import run_backtest, generate_backtest_report


def process_posts(posts: list[dict], data_source: str = "manual",
                  auto_verify: bool = True, save_report: bool = True,
                  save_charts: bool = False) -> dict:
    """运行完整流水线。

    Args:
        posts: [{"content": str, "date": str}, ...]
        data_source: 数据来源描述
        auto_verify: 是否自动运行回测验证
        save_report: 是否生成报告
        save_charts: 是否生成K线图

    Returns:
        {"signals_saved": int, "report_path": str, "metrics": dict}
    """
    init_db()
    print(f"\n{'='*50}")
    print(f"📡 峰哥反向指标 — 自动跟踪")
    print(f"{'='*50}")

    results = []
    signals_saved = 0

    for i, post in enumerate(posts):
        text = post.get("content", "")
        date = post.get("date", datetime.now().strftime("%Y-%m-%d"))
        if not text.strip():
            continue

        print(f"\n[{i+1}/{len(posts)}] 分析: {text[:60]}...")

        # 分析
        analysis = analyze_sentiment(text)
        signal = generate_reverse_signal(analysis, text)

        # 显示结果
        rev = signal["signal"]
        icon = "🟢" if rev == "bullish" else ("🔴" if rev == "bearish" else "⚪")
        strength_dots = "⭐" * signal["signal_strength"]
        print(f"   {icon} {signal['signal_label']} {strength_dots}")
        print(f"   {signal['reason']}")

        # 存入数据库
        sid = save_signal_from_analysis(text, date, analysis, signal)
        signals_saved += 1
        print(f"   💾 已保存 (id={sid})")

        results.append({
            "post": post,
            "analysis": analysis,
            "signal": signal,
        })

    # 运行回测验证
    if auto_verify and signals_saved > 0:
        print(f"\n🔍 运行回测验证...")
        metrics = run_backtest()
    else:
        metrics = {}

    # 生成报告
    report_path = ""
    if save_report and results:
        print(f"\n📄 生成报告...")
        report_text = generate_report(
            posts=[r["post"] for r in results],
            analysis_results=[{
                "analysis": r["analysis"],
                "signal": r["signal"],
            } for r in results],
            data_source=data_source,
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        report_dir = Path(__file__).resolve().parent.parent / "output"
        report_dir.mkdir(exist_ok=True)
        report_path = str(report_dir / f"峰哥反向指标_{timestamp}.md")
        Path(report_path).write_text(report_text, encoding="utf-8")
        print(f"   ✅ 报告已保存: {report_path}")

    # 生成K线图
    if save_charts:
        print(f"\n📈 生成K线图...")
        # 收集所有提到的股票代码
        all_codes = set()
        for r in results:
            codes = r["analysis"].get("stock_codes", [])
            all_codes.update(codes)
        if all_codes:
            from scripts.plot_signals import plot_multi_stock_charts
            dates = [r["post"]["date"] for r in results if r["post"].get("date")]
            start = min(dates) if dates else ""
            end = max(dates) if dates else ""
            plot_multi_stock_charts(list(all_codes), start_date=start, end_date=end)

    print(f"\n{'='*50}")
    print(f"✅ 完成！保存了 {signals_saved} 条信号")
    if report_path:
        print(f"📄 报告: {report_path}")

    return {
        "signals_saved": signals_saved,
        "report_path": report_path,
        "metrics": metrics,
    }


def interactive_mode():
    """交互式输入并运行完整流水线。"""
    print("📝 输入峰哥的微博内容（每行一条，空行结束）:")
    posts = []
    while True:
        try:
            line = input()
            if not line:
                break
            posts.append({
                "content": line,
                "date": datetime.now().strftime("%Y-%m-%d"),
            })
        except EOFError:
            break

    if not posts:
        print("没有输入内容。")
        return

    process_posts(posts, data_source="手动输入", auto_verify=True,
                  save_report=True, save_charts=True)


def file_mode(filepath: str):
    """从文件读取并运行流水线。"""
    path = Path(filepath)
    if not path.exists():
        print(f"❌ 文件不存在: {filepath}")
        return

    ext = path.suffix.lower()
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        posts = data if isinstance(data, list) else data.get("posts", data.get("weibo_posts", []))
    elif ext == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        posts = [{"content": l, "date": datetime.now().strftime("%Y-%m-%d")} for l in lines]
    else:
        print(f"❌ 不支持的文件格式: {ext}")
        return

    for p in posts:
        if "date" not in p:
            p["date"] = datetime.now().strftime("%Y-%m-%d")

    print(f"📂 从 {filepath} 加载了 {len(posts)} 条内容")
    process_posts(posts, data_source=f"文件({path.name})",
                  auto_verify=True, save_report=True, save_charts=True)


def cron_mode():
    """定时任务模式 — 自动检查未验证信号并更新报告。"""
    print("⏰ 定时任务模式...")
    init_db()

    stats = get_signal_stats()
    print(f"📊 当前状态: 信号{stats['total_signals']}条, 交易{stats['total_trades']}笔")

    # 运行回测（验证未验证的信号）
    if stats.get("signals_with_stock_codes", 0) > 0:
        metrics = run_backtest()
        print(f"📊 回测: 胜率5d={metrics['win_rate_5d']}%")

    # 生成回测报告
    report_text = generate_backtest_report()
    ts = datetime.now().strftime("%Y%m%d")
    report_dir = Path(__file__).resolve().parent.parent / "output"
    report_path = report_dir / f"回测报告_{ts}.md"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"📄 回测报告已更新: {report_path}")


# ==================== CLI ====================

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "--interactive" or sys.argv[1] == "-i":
            interactive_mode()
        elif sys.argv[1] == "--file" or sys.argv[1] == "-f":
            if len(sys.argv) > 2:
                file_mode(sys.argv[2])
            else:
                print("请指定文件路径: python auto_track.py --file <path>")
        elif sys.argv[1] == "--cron":
            cron_mode()
        else:
            print("用法:")
            print("  python auto_track.py --interactive    # 交互模式")
            print("  python auto_track.py --file <path>    # 从文件加载")
            print("  python auto_track.py --cron           # 定时任务")
    else:
        interactive_mode()
