"""
峰哥反向指标 — Skill 主入口
=============================
追踪微博「峰哥亡命天涯」的发言，提取股票/市场观点，生成反向操作信号。

功能模式：
    python main.py --track              # 完整跟踪流水线（分析→存库→回测→报告）
    python main.py --chart <code>       # 生成K线图+信号标注
    python main.py --backtest           # 运行回测+虚拟交易
    python main.py --portfolio          # 查看虚拟交易系统盈亏
    python main.py --stats              # 查看数据库统计
    python main.py --interactive        # 交互分析
    python main.py --file <path>        # 从文件分析
    python main.py --cron               # 定时任务模式
"""

import sys
import json
from datetime import datetime
from pathlib import Path

# Windows terminal encoding fix
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "gb2312", "cp936"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent


def print_banner():
    banner = """
╔══════════════════════════════════════╗
║       峰哥反向指标 · Feng Ge        ║
║     Reverse Indicator Tracker        ║
║    微博：@峰哥亡命天涯               ║
║    虚拟交易系统 · K线信号标注 · 回测  ║
╚══════════════════════════════════════╝
    """
    print(banner)


def print_help():
    print("用法:")
    print("  python main.py --track                  # 完整流水线（分析→存库→回测→K线图→报告）")
    print("  python main.py --interactive            # 交互式输入微博内容")
    print("  python main.py --file <path>            # 从 JSON/TXT 文件分析")
    print("  python main.py --chart <code> [start] [end]  # 生成K线图+信号标注")
    print("  python main.py --backtest               # 运行回测验证")
    print("  python main.py --portfolio              # 查看虚拟交易系统")
    print("  python main.py --stats                  # 数据库统计")
    print("  python main.py --cron                   # 定时任务（更新回测+报告）")
    print()
    print("示例:")
    print("  python main.py --chart 000001 2026-06-01 2026-07-21")
    print("  python main.py --chart 半导体ETF  # 用stock_name搜信号")
    print()
    print("子脚本:")
    print("  python scripts/analyze_sentiment.py <text>   # 快速分析单条")
    print("  python scripts/auto_track.py --interactive   # 快速跟踪")
    print("  python scripts/signal_store.py               # 数据库工具")
    print("  python scripts/backtest.py --verify           # 快速回测")
    print()
    print("参考:")
    print("  SKILL.md        — 完整工作流")
    print("  references/     — 方法论文档")


# ==================== 命令处理 ====================

def cmd_track():
    """完整流水线：交互输入 → 分析 → 存库 → 回测 → K线图 → 报告"""
    from scripts.signal_store import init_db, get_signal_stats
    init_db()

    print("📝 输入峰哥的微博内容（每行一条，空行结束）:")
    posts = []
    while True:
        try:
            line = input()
            if not line:
                break
            posts.append(line)
        except EOFError:
            break

    if not posts:
        print("没有输入内容。")
        return

    from scripts.auto_track import process_posts
    post_dicts = [{"content": p, "date": datetime.now().strftime("%Y-%m-%d")} for p in posts]
    result = process_posts(
        post_dicts,
        data_source="手动输入",
        auto_verify=True,
        save_report=True,
        save_charts=True,
    )

    # 打印摘要
    if result.get("signals_saved", 0) > 0:
        print(f"\n📊 数据库当前统计:")
        stats = get_signal_stats()
        print(f"   信号: {stats['total_signals']}条 | 交易: {stats['total_trades']}笔 | 未平仓: {stats['open_trades']}")


def cmd_interactive():
    """交互模式：分析+存库（不自动回测）。"""
    from scripts.signal_store import init_db, save_signal_from_analysis, get_signal_stats
    from scripts.analyze_sentiment import analyze_sentiment, generate_reverse_signal, format_results

    init_db()

    print("📝 输入峰哥的微博内容（每行一条，空行结束）:")
    texts = []
    while True:
        try:
            line = input()
            if not line:
                break
            texts.append(line)
        except EOFError:
            break

    if not texts:
        print("没有输入内容。")
        return

    # 分析 + 存库
    saved = 0
    analysis_results = []
    for text in texts:
        a = analyze_sentiment(text)
        s = generate_reverse_signal(a, text)
        sid = save_signal_from_analysis(text, datetime.now().strftime("%Y-%m-%d"), a, s)
        saved += 1

        rev = s["signal"]
        icon = "🟢" if rev == "bullish" else ("🔴" if rev == "bearish" else "⚪")
        print(f"  {icon} {s['signal_label']} (信号#{sid})")
        print(f"     {s['reason']}")

        analysis_results.append({"analysis": a, "signal": s})

    print(f"\n💾 已保存 {saved} 条信号到数据库")

    # 询问更多操作
    print("\n后续操作:")
    print("  1. 生成 Markdown 报告")
    print("  2. 生成K线图表")
    print("  3. 运行回测验证")
    print("  4. 全部执行")
    choice = input("选择 (1/2/3/4, 回车跳过): ").strip()

    if choice in ("1", "4"):
        from scripts.generate_report import save_report
        post_dicts = [{"content": t, "date": datetime.now().strftime("%Y-%m-%d")} for t in texts]
        report = __import__("scripts.generate_report", fromlist=["generate_report"]).generate_report(
            post_dicts, analysis_results, data_source="手动输入"
        )
        path = save_report(report)
        print(f"📄 报告: {path}")

    if choice in ("2", "4"):
        from scripts.plot_signals import plot_multi_stock_charts
        all_codes = set()
        for t in texts:
            a = analyze_sentiment(t)
            all_codes.update(a.get("stock_codes", []))
        if all_codes:
            plot_multi_stock_charts(list(all_codes))
        else:
            print("  ⚠️ 未检测到股票代码，无法生成K线图")

    if choice in ("3", "4"):
        from scripts.backtest import run_backtest
        metrics = run_backtest()
        if metrics["total_verifications"] > 0:
            print(f"📊 回测: 胜率5d={metrics['win_rate_5d']}% 10d={metrics['win_rate_10d']}%")

    stats = get_signal_stats()
    print(f"\n📊 数据库: 信号{stats['total_signals']}条 | 交易{stats['total_trades']}笔")


def cmd_file(filepath: str):
    """从文件读取并运行完整流水线。"""
    path = Path(filepath)
    if not path.exists():
        print(f"❌ 文件不存在: {filepath}")
        return

    import json
    ext = path.suffix.lower()

    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        posts = data if isinstance(data, list) else data.get("posts", data.get("weibo_posts", []))
    elif ext == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        posts = [{"content": l} for l in lines]
    else:
        # 尝试用 fetch_posts 加载
        from scripts.fetch_posts import load_from_json, load_from_csv, load_from_text
        loaders = {".json": load_from_json, ".csv": load_from_csv, ".txt": load_from_text}
        loader = loaders.get(ext)
        if not loader:
            print(f"❌ 不支持的文件格式: {ext}")
            return
        posts = loader(filepath)

    for p in posts:
        if "date" not in p or not p["date"]:
            p["date"] = datetime.now().strftime("%Y-%m-%d")

    print(f"📂 加载了 {len(posts)} 条内容")

    from scripts.auto_track import process_posts
    process_posts(posts, data_source=f"文件({path.name})",
                  auto_verify=True, save_report=True, save_charts=True)


def cmd_chart(stock_code: str, start_date: str = "", end_date: str = ""):
    """生成K线图+信号标注。"""
    from scripts.plot_signals import plot_signal_chart

    if not start_date:
        from datetime import timedelta
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    path = plot_signal_chart(stock_code, "", start_date, end_date)
    if path:
        print(f"📈 图表已保存: {path}")
    else:
        print(f"❌ 生成失败")


def cmd_backtest():
    """运行回测验证。"""
    from scripts.backtest import run_backtest, generate_backtest_report
    from scripts.signal_store import get_signal_stats

    stats = get_signal_stats()
    print(f"📊 当前信号库: {stats['total_signals']}条")
    print(f"   有股票代码: {stats['signals_with_stock_codes']}条")
    print(f"   现有交易: {stats['total_trades']}笔")

    if stats["total_signals"] == 0:
        print("⚠️ 数据库为空，请先用 --track 或 --interactive 录入信号")
        return

    metrics = run_backtest()

    if metrics["total_verifications"] > 0:
        print(f"\n📊 回测结果:")
        print(f"   验证数: {metrics['total_verifications']}")
        print(f"   5日胜率: {metrics['win_rate_5d']}%")
        print(f"   10日胜率: {metrics['win_rate_10d']}%")
        print(f"   20日胜率: {metrics['win_rate_20d']}%")
        print(f"   5日均收益: {metrics['avg_return_5d']}%")
        print(f"   10日均收益: {metrics['avg_return_10d']}%")
        print(f"   20日均收益: {metrics['avg_return_20d']}%")

    # 生成回测报告
    report = generate_backtest_report(metrics)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = PROJECT_ROOT / "output" / f"回测报告_{ts}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\n📄 详细回测报告: {out_path}")


def cmd_portfolio():
    """查看虚拟交易系统。"""
    from scripts.signal_store import get_trade_summary, get_open_trades
    from scripts.backtest import calculate_portfolio_value

    summary = get_trade_summary()
    portfolio = calculate_portfolio_value()

    print("\n💼 峰哥反向交易系统")
    print("=" * 40)
    print(f"总交易: {summary['total_trades']}笔")
    print(f"已平仓: {summary['closed_trades']}笔")
    print(f"  盈利: {summary['wins']}笔")
    print(f"  亏损: {summary['losses']}笔")
    print(f"  胜率: {summary['win_rate']}%")
    print(f"  累计收益: {summary['total_return_pct']}%")
    print(f"  平均单笔: {summary['avg_return_pct']}%")
    open_count = summary['total_trades'] - summary['closed_trades']
    print(f"未平仓: {open_count}笔")

    print(f"\n组合净值: ¥{portfolio['nav']:.2f} (本金¥{portfolio['initial_capital']})")
    print(f"总收益率: {portfolio['total_return_pct']}%")

    if summary.get("by_direction"):
        print("\n多空方向:")
        for d in summary["by_direction"]:
            label = {"long": "做多(看空→买入)", "short": "做空(看多→卖出)"}
            print(f"  {label.get(d['direction'], d['direction'])}: {d['count']}笔, 均收益{d['avg_return']}%")

    # 显示未平仓
    open_trades = get_open_trades()
    if open_trades:
        print(f"\n⏳ 未平仓头寸 ({len(open_trades)}笔):")
        for t in open_trades:
            dir_icon = "🟢多" if t["direction"] == "long" else "🔴空"
            print(f"  {t['trade_date']} {dir_icon} {t['stock_code']} @ ¥{t['entry_price']:.2f}")


def cmd_stats():
    """查看数据库统计。"""
    from scripts.signal_store import get_signal_stats, get_backtest_metrics
    from scripts.backtest import get_trade_summary

    stats = get_signal_stats()
    bt = get_backtest_metrics()
    ts = get_trade_summary()

    print("\n📊 数据库统计")
    print("=" * 40)
    print(f"信号总数: {stats['total_signals']}")
    print(f"有股票代码: {stats['signals_with_stock_codes']}")
    print(f"信号方向: {stats['by_reverse_type']}")
    print(f"信号强度: {stats['by_reverse_strength']}")
    print()
    print(f"💼 虚拟交易")
    print(f"交易总数: {stats['total_trades']} (未平仓: {stats['open_trades']})")
    print(f"胜率: {ts['win_rate']}% | 累计: {ts['total_return_pct']}%")
    print()
    print(f"🔍 回测验证")
    print(f"已验证: {bt['total_verifications']}条")
    if bt['total_verifications'] > 0:
        print(f"5日胜率: {bt['win_rate_5d']}% (均收益{bt['avg_return_5d']}%)")
        print(f"10日胜率: {bt['win_rate_10d']}% (均收益{bt['avg_return_10d']}%)")
        print(f"20日胜率: {bt['win_rate_20d']}% (均收益{bt['avg_return_20d']}%)")


def cmd_cron():
    """定时任务模式。"""
    print("⏰ 定时任务模式...")
    from scripts.auto_track import cron_mode
    cron_mode()


# ==================== 主入口 ====================

def main():
    print_banner()

    if len(sys.argv) < 2:
        print_help()
        return

    cmd = sys.argv[1]

    if cmd in ("--help", "-h"):
        print_help()

    elif cmd == "--track":
        cmd_track()

    elif cmd == "--interactive":
        cmd_interactive()

    elif cmd == "--file":
        if len(sys.argv) < 3:
            print("请指定文件路径: python main.py --file <path>")
            return
        cmd_file(sys.argv[2])

    elif cmd == "--chart":
        if len(sys.argv) < 3:
            print("请指定股票代码: python main.py --chart 000001 [start] [end]")
            return
        start = sys.argv[3] if len(sys.argv) > 3 else ""
        end = sys.argv[4] if len(sys.argv) > 4 else ""
        cmd_chart(sys.argv[2], start, end)

    elif cmd == "--backtest":
        cmd_backtest()

    elif cmd == "--portfolio":
        cmd_portfolio()

    elif cmd == "--stats":
        cmd_stats()

    elif cmd == "--cron":
        cmd_cron()

    else:
        print(f"未知命令: {cmd}")
        print_help()


if __name__ == "__main__":
    main()
