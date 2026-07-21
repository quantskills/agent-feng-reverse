"""
峰哥反向指标 — Agent 自主运行引擎
======================================
将 SKILL 工作流升级为 AGENT 模式：自动执行
  采集 → 分析 → 交易 → 验证 → 图表 → 报告

三种模式：
  python agent_runner.py --daily             单次运行（盘后/早报）
  python agent_runner.py --watch --interval 30  持续监控（盘中）
  python agent_runner.py --cron              定时任务触发
  python agent_runner.py --status            查看运行状态
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# 编码修复
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "gb2312", "cp936"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.signal_store import (
    init_db, save_signal_from_analysis, get_all_signals,
    get_signal_stats, get_trade_summary, get_open_trades,
    log_agent_run, get_agent_status, get_signals_since,
    auto_close_trades,
)
from scripts.analyze_sentiment import analyze_sentiment, generate_reverse_signal, analyze_posts

# ==================== 配置 ====================

DEFAULT_CONFIG = {
    "take_profit_pct": 10.0,
    "stop_loss_pct": -5.0,
    "max_hold_days": 30,
    "max_posts_per_run": 20,
    "data_dir": str(Path(__file__).resolve().parent.parent / "output"),
}


def load_config(mode: str = "daily", **overrides) -> dict:
    config = dict(DEFAULT_CONFIG)
    config["mode"] = mode
    config.update(overrides)
    return config


# ==================== 阶段1: 数据采集 ====================

def collect(config: dict) -> dict:
    """采集峰哥最新微博数据。

    数据来源（按优先级）：
    1. 直接参数传入 (config['input_posts'])
    2. 来自 stdin 管道 (piped input)
    3. 缓存文件 weibo_input.json

    都走完后自动清理，确保不重复处理。

    返回: {"posts": [...], "source": str, "new_count": int, "skipped": int}
    """
    posts = []
    source = "agent_auto"

    # 1. 从参数读取（Claude 直接传入）
    input_posts = config.get("input_posts")
    if input_posts:
        for p in input_posts:
            if isinstance(p, str):
                posts.append({"date": datetime.now().strftime("%Y-%m-%d"), "content": p})
            else:
                posts.append(p)
        source = "claude_websearch"

    # 2. 从 stdin 读取（管道输入）
    if not posts and not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                import json as _json
                try:
                    parsed = _json.loads(stdin_data)
                    if isinstance(parsed, list):
                        raw = parsed
                    elif isinstance(parsed, dict):
                        raw = parsed.get("posts", parsed.get("weibo_posts", []))
                    else:
                        raw = [{"content": stdin_data}]
                except _json.JSONDecodeError:
                    raw = [{"content": line} for line in stdin_data.split("\n") if line.strip()]

                for p in raw:
                    if isinstance(p, str):
                        posts.append({"date": datetime.now().strftime("%Y-%m-%d"), "content": p})
                    else:
                        if "date" not in p or not p.get("date"):
                            p["date"] = datetime.now().strftime("%Y-%m-%d")
                        posts.append(p)
                source = "stdin_pipe"
        except Exception:
            pass

    # 3. 从缓存文件读取
    cache_path = Path(config["data_dir"]) / "weibo_input.json"
    if not posts and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_posts = data if isinstance(data, list) else data.get("posts", [])
            for p in raw_posts:
                if isinstance(p, str):
                    posts.append({"date": datetime.now().strftime("%Y-%m-%d"), "content": p})
                else:
                    posts.append(p)
            source = f"cache({cache_path.name})"
            cache_path.unlink()
        except Exception as e:
            print(f"  [WARN] 缓存文件读取失败: {e}")

    # 去重：过滤已在 signal_store 中的内容
    existing = get_all_signals(limit=1000)
    existing_texts = {s["source_text"] for s in existing if s.get("source_text")}

    new_posts = []
    skipped = 0
    for p in posts:
        text = p.get("content", "")
        # 用前50字做hash去重
        key = text[:50]
        if key in existing_texts:
            skipped += 1
            continue
        new_posts.append(p)

    # 限制数量
    max_p = config.get("max_posts_per_run", 20)
    new_posts = new_posts[:max_p]

    return {"posts": new_posts, "source": source, "new_count": len(new_posts), "skipped": skipped}


# ==================== 阶段2: 分析信号 ====================

def analyze(posts: list[dict], config: dict) -> dict:
    """批量分析微博，生成信号并存入数据库。

    返回: {"signals_saved": int, "results": list[dict]}
    """
    if not posts:
        return {"signals_saved": 0, "results": []}

    saved = 0
    results = []

    for i, post in enumerate(posts):
        text = post.get("content", "")
        date = post.get("date", datetime.now().strftime("%Y-%m-%d"))
        if not text.strip():
            continue

        print(f"\n  [{i+1}/{len(posts)}] 分析: {text[:60]}...")

        analysis = analyze_sentiment(text)
        signal = generate_reverse_signal(analysis, text)

        # 存入数据库
        sid = save_signal_from_analysis(text, date, analysis, signal)
        saved += 1

        rev = signal["signal"]
        icon = "[多]" if rev == "bullish" else "[空]" if rev == "bearish" else "[-]"
        strength_dots = "*" * signal["signal_strength"]
        print(f"     {icon} {signal['signal_label']} {strength_dots} (id={sid})")
        print(f"     {signal['reason'][:80]}")

        results.append({
            "post": post,
            "analysis": analysis,
            "signal": signal,
            "signal_id": sid,
        })

    return {"signals_saved": saved, "results": results}


# ==================== 阶段3: 虚拟交易 ====================

def trade(analyze_result: dict, config: dict) -> dict:
    """自动执行虚拟交易。

    1. 对含股票代码的新信号开仓
    2. 管理已有头寸（止盈/止损/超时平仓）

    返回: {"opened": int, "closed": int, "trades": list}
    """
    opened = 0
    closed = 0
    trades = []

    # 1. 自动平仓已有头寸
    print("\n  [TRADE] 检查已有持仓...")
    closed_trades = auto_close_trades({
        "take_profit_pct": config.get("take_profit_pct", 10),
        "stop_loss_pct": config.get("stop_loss_pct", -5),
        "max_hold_days": config.get("max_hold_days", 30),
    })
    for ct in closed_trades:
        dir_icon = "[多]" if ct["direction"] == "long" else "[空]"
        print(f"     {dir_icon} 平仓 {ct['stock_code']} 收益{ct['return_pct']:+.1f}% 原因:{ct['close_reason']}")
        closed += 1

    # 2. 新信号开仓
    from scripts.signal_store import open_trade, get_trades_by_stock

    for r in analyze_result.get("results", []):
        analysis = r["analysis"]
        signal = r["signal"]
        signal_id = r["signal_id"]
        post_date = r["post"].get("date", "")

        stock_codes = analysis.get("stock_codes", [])
        rev = signal["signal"]

        if not stock_codes or rev == "neutral":
            continue

        # 检查该股票是否已有未平仓头寸
        for code in stock_codes[:3]:
            existing = get_trades_by_stock(code, status="open")
            if existing:
                print(f"     [SKIP] {code} 已有未平仓头寸")
                continue

            # 获取开盘价（用Pandadata最近的收盘价）
            direction = "long" if rev == "bullish" else "short"
            entry_price = _get_entry_price(code, post_date)
            if entry_price is None:
                print(f"     [WARN] {code} 无法获取入场价")
                continue

            tid = open_trade(signal_id, code, "", post_date, direction, entry_price)
            dir_icon = "[多]" if direction == "long" else "[空]"
            print(f"     {dir_icon} 开仓 {code} @ {entry_price:.2f} (trade_id={tid})")
            opened += 1
            trades.append({"id": tid, "code": code, "direction": direction, "price": entry_price})

    return {"opened": opened, "closed": closed, "trades": trades}


def _get_entry_price(stock_code: str, date_str: str) -> float | None:
    """获取指定日期附近的收盘价作为入场价。"""
    import os
    os.environ.setdefault("DEFAULT_USERNAME", "super_data_user")
    os.environ.setdefault("DEFAULT_PASSWORD", "panda@2026^_^")

    code = stock_code.strip().split(".")[0]
    if code.startswith("6"):
        symbol = f"{code}.SH"
    elif code.startswith(("0", "3")):
        symbol = f"{code}.SZ"
    else:
        symbol = code

    try:
        from panda_data import init_token, get_stock_daily
        init_token()
        start = (datetime.strptime(date_str[:10], "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
        end = (datetime.strptime(date_str[:10], "%Y-%m-%d") + timedelta(days=5)).strftime("%Y-%m-%d")
        df = get_stock_daily(symbol=symbol, start_date=start, end_date=end)
        if df is not None and not df.empty and "close" in df.columns:
            # 找最近交易日
            target = datetime.strptime(date_str[:10], "%Y-%m-%d")
            df = df.copy()
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            dates = df.index[df.index >= target.strftime("%Y-%m-%d")]
            if len(dates) > 0:
                return float(df.loc[dates[0], "close"])
    except Exception:
        pass
    return None


# ==================== 阶段4: 回测验证 ====================

def verify(config: dict) -> dict:
    """运行回测验证，检查未验证信号。"""
    from scripts.backtest import run_backtest

    print("\n  [VERIFY] 运行回测验证...")
    metrics = run_backtest()
    print(f"     已验证: {metrics['total_verifications']} | "
          f"5日胜率: {metrics['win_rate_5d']}% | "
          f"平均收益: {metrics['avg_return_5d']}%")
    return {"verified": metrics["total_verifications"], "metrics": metrics}


# ==================== 阶段5: K线图 ====================

def chart(analyze_result: dict, config: dict) -> dict:
    """生成K线信号标注图（含大盘指数）。"""
    from scripts.plot_signals import plot_signal_chart, plot_multi_stock_charts

    all_codes = set()
    for r in analyze_result.get("results", []):
        codes = r["analysis"].get("stock_codes", [])
        all_codes.update(codes)
    if not all_codes:
        signals = get_all_signals(limit=100)
        for s in signals:
            try:
                codes = json.loads(s.get("stock_codes", "[]"))
                all_codes.update(codes)
            except Exception:
                pass

    chart_paths = []
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    # 始终生成大盘指数
    for idx_code, idx_name in [("000688", "科创50"), ("000300", "沪深300"), ("000001", "上证指数")]:
        try:
            p = plot_signal_chart(idx_code, idx_name, start, end)
            if p:
                chart_paths.append(p)
        except Exception as e:
            print(f"    跳过 {idx_code}: {e}")
    print(f"  [CHART] 指数: {sum(1 for p in chart_paths if any(i in p for i in ['000688','000300','000001']))}/3张")

    if all_codes:
        print(f"  [CHART] 个股: {min(len(all_codes),5)}只...")
        more = plot_multi_stock_charts(list(all_codes)[:5], start_date=start, end_date=end)
        chart_paths.extend(more)

    if chart_paths:
        print(f"     图表合计: {len(chart_paths)}张")
    else:
        print(f"  [CHART] 无数据跳过")
    return {"charts": chart_paths}


def report(analyze_result: dict, trade_result: dict,
           verify_result: dict, chart_paths: list[str], config: dict) -> dict:
    """生成 Agent 运行报告。"""
    from scripts.generate_report import generate_report

    print(f"\n  [REPORT] 生成报告...")

    posts = [r["post"] for r in analyze_result.get("results", [])]
    analysis_format = [{
        "analysis": r["analysis"],
        "signal": r["signal"],
    } for r in analyze_result.get("results", [])]

    if not posts:
        posts = [{"date": datetime.now().strftime("%Y-%m-%d"), "content": "(agent auto run - no new posts)"}]
    if not analysis_format:
        a = analyze_sentiment("")
        s = generate_reverse_signal(a, "")
        analysis_format = [{"analysis": a, "signal": s}]

    trade_summary_data = get_trade_summary()

    report_text = generate_report(
        posts=posts,
        analysis_results=analysis_format,
        data_source=f"AGENT({config['mode']})",
        chart_paths=chart_paths,
        agent_mode=True,
        trade_summary=trade_summary_data,
        backtest_ref=True,
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    report_dir = Path(config["data_dir"])
    report_path = str(report_dir / f"Agent交易报告_{ts}.md")
    Path(report_path).write_text(report_text, encoding="utf-8")
    print(f"     报告: {report_path}")

    return {"report_path": report_path}


# ==================== 主流水线 ====================

def run_pipeline(config: dict) -> dict:
    """运行完整 Agent 流水线。"""
    start_time = time.time()
    print(f"\n{'='*55}")
    print(f"  峰哥虚拟交易系统 — Agent 运行 [{config['mode']}]")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    init_db()

    errors = []
    pipeline_result = {
        "mode": config["mode"],
        "posts_fetched": 0, "signals_saved": 0,
        "trades_opened": 0, "trades_closed": 0,
        "charts_generated": 0, "report_path": "",
        "errors": errors,
    }

    # 阶段1: 数据采集
    try:
        print("\n--- 阶段1: 数据采集 ---")
        collect_result = collect(config)
        pipeline_result["posts_fetched"] = collect_result["new_count"]
        print(f"  新微博: {collect_result['new_count']}条 (去重跳过{collect_result['skipped']}条)")
    except Exception as e:
        errors.append(f"collect: {e}")
        print(f"  [ERROR] 采集失败: {e}")
        collect_result = {"posts": [], "source": "error", "new_count": 0, "skipped": 0}

    # 阶段2: 分析信号
    try:
        print("\n--- 阶段2: 观点分析 ---")
        analyze_result = analyze(collect_result["posts"], config)
        pipeline_result["signals_saved"] = analyze_result["signals_saved"]
    except Exception as e:
        errors.append(f"analyze: {e}")
        print(f"  [ERROR] 分析失败: {e}")
        analyze_result = {"signals_saved": 0, "results": []}

    # 阶段3: 虚拟交易
    try:
        print("\n--- 阶段3: 虚拟交易 ---")
        trade_result = trade(analyze_result, config)
        pipeline_result["trades_opened"] = trade_result["opened"]
        pipeline_result["trades_closed"] = trade_result["closed"]
    except Exception as e:
        errors.append(f"trade: {e}")
        print(f"  [ERROR] 交易失败: {e}")
        trade_result = {"opened": 0, "closed": 0, "trades": []}

    # 阶段4: 回测验证
    verify_result = {"verified": 0, "metrics": {}}
    try:
        print("\n--- 阶段4: 回测验证 ---")
        verify_result = verify(config)
    except Exception as e:
        errors.append(f"verify: {e}")
        print(f"  [ERROR] 回测失败: {e}")

    # 阶段5: K线图
    chart_paths = []
    try:
        print("\n--- 阶段5: K线图 ---")
        chart_result = chart(analyze_result, config)
        chart_paths = chart_result["charts"]
        pipeline_result["charts_generated"] = len(chart_paths)
    except Exception as e:
        errors.append(f"chart: {e}")
        print(f"  [ERROR] K线图失败: {e}")

    # 阶段6: 报告
    try:
        print("\n--- 阶段6: 报告生成 ---")
        report_result = report(analyze_result, trade_result, verify_result, chart_paths, config)
        pipeline_result["report_path"] = report_result["report_path"]
    except Exception as e:
        errors.append(f"report: {e}")
        print(f"  [ERROR] 报告失败: {e}")

    # 记录运行日志
    duration = time.time() - start_time
    pipeline_result["duration_seconds"] = round(duration, 1)
    try:
        log_agent_run(pipeline_result)
    except Exception as e:
        errors.append(f"log: {e}")

    # 输出摘要
    print(f"\n{'='*55}")
    print(f"  Agent 运行完成 ({duration:.1f}秒)")
    print(f"  微博: {pipeline_result['posts_fetched']}条 | "
          f"信号: {pipeline_result['signals_saved']}条")
    print(f"  开仓: {pipeline_result['trades_opened']} | "
          f"平仓: {pipeline_result['trades_closed']}")
    print(f"  图表: {pipeline_result['charts_generated']}张 | "
          f"报告: {Path(pipeline_result['report_path']).name}")
    if errors:
        print(f"  [WARN] {len(errors)}个错误: {'; '.join(errors[:3])}")
    print(f"{'='*55}")

    return pipeline_result


# ==================== 持续监控 ====================

def watch_loop(config: dict):
    """持续监控模式，每隔 interval 分钟运行一次。"""
    interval = config.get("interval", 30)
    run_count = 0

    print(f"\n[WATCH] 持续监控模式 (每{interval}分钟运行一次)")
    print(f"[WATCH] Ctrl+C 停止\n")

    while True:
        run_count += 1
        print(f"\n[WATCH] 第{run_count}次运行 ({datetime.now().strftime('%H:%M:%S')})")
        try:
            run_pipeline(config)
        except KeyboardInterrupt:
            print(f"\n[WATCH] 用户中断")
            break
        except Exception as e:
            print(f"\n[WATCH] 运行异常: {e}")

        print(f"\n[WATCH] 等待{interval}分钟...")
        try:
            time.sleep(interval * 60)
        except KeyboardInterrupt:
            print(f"\n[WATCH] 用户中断")
            break


# ==================== CLI ====================

def print_status():
    """打印 Agent 运行状态。"""
    status = get_agent_status()
    stats = get_signal_stats()
    ts = get_trade_summary()

    print(f"\n{'='*45}")
    print(f"  峰哥虚拟交易系统 — 状态")
    print(f"{'='*45}")
    print(f"\n📊 信号库: {stats['total_signals']}条")
    print(f"💼 交易: {ts['total_trades']}笔 | 胜率{ts['win_rate']}% | 累计{ts['total_return_pct']}%")
    print(f"  未平仓: {stats['open_trades']}笔")

    if status["last_run"]:
        lr = status["last_run"]
        print(f"\n⏰ 上次运行: {lr['run_time']} ({lr['mode']})")
        print(f"  微博{lr['posts_fetched']}条 → 信号{lr['signals_saved']}条 → "
              f"开{lr['trades_opened']}平{lr['trades_closed']} → "
              f"图表{lr['charts_generated']}张")
        if lr["errors"] and lr["errors"] != "[]":
            print(f"  [WARN] 错误: {lr['errors']}")
    else:
        print(f"\n⏰ 上次运行: 从未运行")

    if status["weekly"]:
        w = status["weekly"]
        print(f"\n📅 本周: {w['runs']}次运行 | "
              f"{w['total_sigs']}条信号 | "
              f"开{w['total_opens']}平{w['total_closes']}")


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python agent_runner.py --daily            # 单次运行")
        print("  python agent_runner.py --watch            # 持续监控")
        print("  python agent_runner.py --watch --interval 30")
        print("  python agent_runner.py --cron             # 定时任务")
        print("  python agent_runner.py --status           # 查看状态")
        return

    cmd = sys.argv[1]
    input_posts = None

    if "--input" in sys.argv:
        idx = sys.argv.index("--input")
        if idx + 1 < len(sys.argv):
            raw = sys.argv[idx + 1]
            input_posts = [{"date": datetime.now().strftime("%Y-%m-%d"), "content": raw}]

    if cmd == "--daily":
        config = load_config(mode="daily", input_posts=input_posts)
        run_pipeline(config)

    elif cmd == "--watch":
        interval = 30
        if "--interval" in sys.argv:
            idx = sys.argv.index("--interval")
            if idx + 1 < len(sys.argv):
                interval = int(sys.argv[idx + 1])
        config = load_config(mode="watch", interval=interval)
        watch_loop(config)

    elif cmd == "--cron":
        config = load_config(mode="cron")
        run_pipeline(config)

    elif cmd == "--status":
        print_status()

    else:
        print(f"未知命令: {cmd}")
        print("用法: python agent_runner.py --daily|--watch|--cron|--status")


if __name__ == "__main__":
    main()
