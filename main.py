"""
峰哥反向指标 — Skill 主入口
=============================
追踪微博「峰哥亡命天涯」的发言，提取股票/市场观点，生成反向操作信号。

工作流程：
1. 通过 WebSearch 获取峰哥最新微博
2. 分析每条的 sentiment/stock/sector
3. 应用反向指标逻辑生成信号
4. 输出结构化报告

用法：
    python main.py --mode today          # 今日峰哥观点分析
    python main.py --mode search         # 搜索最新微博并分析
    python main.py --mode file <path>    # 从本地文件分析
"""

import sys
import json
from datetime import datetime
from pathlib import Path


def print_banner():
    banner = """
╔══════════════════════════════════════╗
║       峰哥反向指标 · Feng Ge        ║
║     Reverse Indicator Tracker        ║
║    微博：@峰哥亡命天涯               ║
╚══════════════════════════════════════╝
    """
    print(banner)


def print_help():
    print("用法:")
    print("  python main.py --mode today         # 查看今日分析")
    print("  python main.py --mode search        # 搜索最新微博并分析")
    print("  python main.py --mode file <path>   # 从本地 JSON/TXT 文件分析")
    print("  python main.py --mode interactive   # 交互模式，手动输入微博")
    print()
    print("更多功能:")
    print("  python scripts/fetch_posts.py json <path>       # 采集微博数据")
    print("  python scripts/analyze_sentiment.py <text>     # 分析单条文本")
    print("  python scripts/generate_report.py <json>       # 生成报告")
    print()
    print("参考文件:")
    print("  SKILL.md              — 完整工作流和方法论")
    print("  references/           — 数据源、方法论文档、案例库")


def interactive_mode():
    """交互式输入模式。"""
    print("请输入峰哥的微博内容（每行一条，输入空行结束）：")
    posts = []
    while True:
        line = input()
        if not line:
            break
        posts.append(line)

    if not posts:
        print("没有输入内容。")
        return

    from scripts.analyze_sentiment import analyze_posts, format_results
    results = analyze_posts(posts)
    print("\n=== 分析结果 ===\n")
    print(format_results(results))

    # 询问是否生成报告
    save = input("\n是否生成 Markdown 报告？(y/n): ").strip().lower()
    if save == "y":
        from scripts.generate_report import generate_report, save_report
        post_dicts = [{"content": p, "date": datetime.now().strftime("%Y-%m-%d")} for p in posts]
        report = generate_report(post_dicts, results, data_source="手动输入")
        path = save_report(report)
        print(f"报告已保存: {path}")


def main():
    print_banner()

    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    mode = sys.argv[1]
    if mode == "--help" or mode == "-h":
        print_help()
    elif mode == "--mode":
        if len(sys.argv) < 3:
            print("请指定模式: today / search / file / interactive")
            sys.exit(1)
        sub_mode = sys.argv[2]
        if sub_mode == "interactive":
            interactive_mode()
        elif sub_mode == "today":
            print("📡 今日模式：请使用 @skill-feng-reverse 在 Claude 中触发，")
            print("   或运行 interactive 模式手动输入微博内容。")
            print()
            print("推荐命令:")
            print("  python main.py --mode interactive")
        elif sub_mode == "search":
            print("🔍 搜索模式：请在 Claude 中使用 @skill-feng-reverse 并附加搜索意图，")
            print("   例如：「@skill-feng-reverse 搜索峰哥今天的最新微博」")
        elif sub_mode == "file":
            if len(sys.argv) < 4:
                print("请指定文件路径: python main.py --mode file <path>")
                sys.exit(1)
            filepath = sys.argv[3]
            if not Path(filepath).exists():
                print(f"文件不存在: {filepath}")
                sys.exit(1)

            from scripts.fetch_posts import load_from_json, load_from_csv, load_from_text, format_posts_for_analysis
            from scripts.analyze_sentiment import analyze_posts, format_results

            ext = Path(filepath).suffix.lower()
            loaders = {".json": load_from_json, ".csv": load_from_csv, ".txt": load_from_text}
            loader = loaders.get(ext)
            if not loader:
                print(f"不支持的文件格式: {ext}")
                sys.exit(1)

            posts = loader(filepath)
            texts = [p.get("content", p.get("text", "")) for p in posts]
            results = analyze_posts(texts)
            print(f"\n共分析 {len(posts)} 条微博\n")
            print(format_results(results))
        else:
            print(f"未知模式: {sub_mode}")
            print_help()
    else:
        print_help()


if __name__ == "__main__":
    main()
