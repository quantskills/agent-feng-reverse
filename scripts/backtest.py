"""
峰哥反向指标 — 回测验证 & 虚拟交易系统
========================================
核心功能：
1. 信号验证：对每条含股票代码的信号，验证 N 日后走势
2. 虚拟交易：记录"峰哥反向策略"的模拟交易盈亏
3. 回测报告：胜率、收益率、分组统计、交易清单
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Windows terminal encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "gb2312", "cp936"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.signal_store import (
    init_db, get_unverified_signals, get_all_signals,
    save_verification, get_verifications, get_backtest_metrics,
    open_trade, close_trade, get_trade_summary, get_open_trades,
    get_connection,
)

# ==================== Pandadata K线获取 ====================

def _init_pandadata():
    os.environ.setdefault("DEFAULT_USERNAME", "super_data_user")
    os.environ.setdefault("DEFAULT_PASSWORD", "panda@2026^_^")
    os.environ.setdefault("JAVA_SERVICE_BASE_URL", "http://pandadata.pandaaiquant.com")
    try:
        from panda_data import init_token
        init_token()
        return True
    except Exception:
        return False


def normalize_code(code: str) -> str:
    """标准化A股代码为 Pandadata 格式。"""
    code = code.strip().split(".")[0]
    if code.startswith("6"):
        return f"{code}.SH"
    elif code.startswith(("0", "3")):
        return f"{code}.SZ"
    elif code.startswith(("4", "8")):
        return f"{code}.BJ"
    return code


def fetch_price_df(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取价格数据用于回测。"""
    if not _init_pandadata():
        return pd.DataFrame()

    try:
        from panda_data import get_stock_daily
        symbol = normalize_code(stock_code)
        df = get_stock_daily(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if df is None or df.empty:
            return pd.DataFrame()

        # 选择需要的列
        needed = {"open", "high", "low", "close", "volume"}
        avail = set(df.columns)
        if not needed.issubset(avail):
            return pd.DataFrame()

        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return df.sort_index()
    except Exception:
        return pd.DataFrame()


# ==================== 信号验证核心 ====================

def verify_signal(signal: dict, windows: list[int] = None) -> list[dict]:
    """验证单个信号对所有股票代码的预测准确性。

    反向逻辑：
    - reverse_signal == "bullish"：预期股价上涨（做多）
    - reverse_signal == "bearish"：预期股价下跌（做空）

    Returns:
        list of verification dicts（每只股票一条）
    """
    if windows is None:
        windows = [5, 10, 20]

    stock_codes = json.loads(signal.get("stock_codes", "[]"))
    if not stock_codes:
        return []

    signal_date = signal["date"]
    reverse_signal = signal["reverse_signal"]
    results = []

    for code in stock_codes[:3]:  # 最多3只
        try:
            result = _verify_single_stock(
                code, signal_date, reverse_signal, windows
            )
            if result:
                result["signal_id"] = signal["id"]
                results.append(result)
        except Exception as e:
            print(f"  ⚠️ {code} 验证失败: {e}")

    return results


def _verify_single_stock(stock_code: str, signal_date: str,
                         reverse_signal: str, windows: list[int]) -> dict:
    """验证单只股票在信号后的走势。"""
    # 取数据：信号日前5天到信号日后 max_window+5 天
    max_w = max(windows)
    start = (pd.Timestamp(signal_date) - timedelta(days=10)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(signal_date) + timedelta(days=max_w * 2)).strftime("%Y-%m-%d")

    df = fetch_price_df(stock_code, start, end)
    if df.empty:
        return {}

    # 找信号日后的第一个交易日作为入场
    entry_idx = df.index[df.index >= signal_date]
    if len(entry_idx) == 0:
        return {}
    entry_date = entry_idx[0]
    entry_price = df.loc[entry_date, "close"]

    # 从 entry_date 取后续数据
    df_after = df[df.index >= entry_date]
    if len(df_after) < 2:
        return {}

    result = {
        "stock_code": stock_code,
        "entry_date": entry_date.strftime("%Y-%m-%d"),
        "entry_price": round(entry_price, 2),
    }

    # 计算每个窗口的涨跌
    for w in windows:
        exit_idx = min(w, len(df_after) - 1)
        exit_price = df_after.iloc[exit_idx]["close"]
        exit_date = df_after.index[exit_idx]

        if reverse_signal == "bullish":
            # 我们做多：预期上涨
            ret = (exit_price - entry_price) / entry_price * 100
            correct = 1 if ret > 0.5 else (0 if ret < -0.5 else None)
        elif reverse_signal == "bearish":
            # 我们做空：预期下跌
            ret = (entry_price - exit_price) / entry_price * 100
            correct = 1 if ret > 0.5 else (0 if ret < -0.5 else None)
        else:
            ret = 0
            correct = None

        result.update({
            f"price_{w}d": round(exit_price, 2),
            f"return_{w}d": round(ret, 2),
            f"correct_{w}d": correct,
        })

    return result


# ==================== 批量回测 ====================

def run_backtest(max_signals: int = None) -> dict:
    """对所有未验证的信号进行批量验证。"""
    if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "gb2312", "cp936"):
        sys.stdout.reconfigure(encoding="utf-8")

    init_db()
    print("[BT] 开始回测验证...")

    signals = get_unverified_signals()
    print(f"   待验证信号: {len(signals)}")

    if max_signals:
        signals = signals[:max_signals]

    total_verified = 0
    for i, sig in enumerate(signals):
        print(f"   [{i+1}/{len(signals)}] {sig['date']} {sig['signal_label']}", end="")
        results = verify_signal(sig)

        if not results:
            print(" — 无股票代码或数据不足")
            continue

        for r in results:
            save_verification(sig["id"], r["stock_code"], r)
            total_verified += 1

            # 开虚拟交易
            if r.get("entry_price") and r.get("entry_date"):
                reverse = sig["reverse_signal"]
                direction = "long" if reverse == "bullish" else "short"
                trade_id = open_trade(
                    sig["id"], r["stock_code"], "",
                    r["entry_date"], direction, r["entry_price"],
                )
                # 如果有 20d 价格，直接平仓
                if r.get("price_20d"):
                    exit_date = pd.Timestamp(r["entry_date"]) + timedelta(days=30)
                    close_trade(trade_id, r["price_20d"],
                                exit_date.strftime("%Y-%m-%d"), "回测自动平仓(20d)")

        print(f" — ✅ {len(results)}只验证完成")

    print(f"\n✅ 回测完成，共验证 {total_verified} 条信号-股票对")
    return get_backtest_metrics()


# ==================== 回测报告 ====================

def generate_backtest_report(metrics: dict = None) -> str:
    """生成回测 + 虚拟交易 Markdown 报告。"""
    if metrics is None:
        metrics = get_backtest_metrics()

    trade_summary = get_trade_summary()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    report = f"""# 峰哥反向指标 — 回测 & 虚拟交易报告

**生成时间**: {now}
**说明**: 以下数据基于"峰哥反向指标"逻辑——峰哥看多→我们做空，峰哥看空→我们做多。

---

## 一、信号验证总览

| 指标 | 数值 |
|------|:----:|
| 已验证信号数 | {metrics['total_verifications']} |
| 5日胜率 | {metrics['win_rate_5d']}% |
| 10日胜率 | {metrics['win_rate_10d']}% |
| 20日胜率 | {metrics['win_rate_20d']}% |
| 5日平均收益 | {metrics['avg_return_5d']}% |
| 10日平均收益 | {metrics['avg_return_10d']}% |
| 20日平均收益 | {metrics['avg_return_20d']}% |

"""
    if metrics['total_verifications'] == 0:
        report += """
> ⚠️ 暂无已验证信号。请先运行 `python main.py --verify` 或 `python main.py --track` 来积累信号数据。

"""

    report += f"""## 二、虚拟交易系统

| 指标 | 数值 |
|------|:----:|
| 总交易数 | {trade_summary['total_trades']} |
| 已平仓 | {trade_summary['closed_trades']} |
| 盈利 | {trade_summary['wins']} |
| 亏损 | {trade_summary['losses']} |
| 胜率 | {trade_summary['win_rate']}% |
| 累计收益率 | {trade_summary['total_return_pct']}% |
| 平均单笔收益 | {trade_summary['avg_return_pct']}% |

"""

    if trade_summary.get("by_direction"):
        report += "### 多空方向表现\n\n| 方向 | 交易数 | 平均收益 |\n|------|:------:|:--------:|\n"
        for d in trade_summary["by_direction"]:
            label = {"long": "做多（峰哥看空→买入）", "short": "做空（峰哥看多→卖出）"}
            report += f"| {label.get(d['direction'], d['direction'])} | {d['count']} | {d['avg_return']}% |\n"

    # 最近交易
    report += "\n### 最近交易\n\n| 日期 | 股票 | 方向 | 入场 | 出场 | 收益 | 状态 |\n|------|:----:|:----:|:----:|:----:|:----:|:----:|\n"
    conn = get_connection()
    rows = conn.execute("""
        SELECT t.*, s.date FROM trades t
        JOIN signals s ON t.signal_id = s.id
        ORDER BY t.id DESC LIMIT 20
    """).fetchall()
    conn.close()
    for r in rows:
        d = dict(r)
        dir_label = "🟢多" if d["direction"] == "long" else "🔴空"
        status_icon = "✅" if d["status"] == "closed" else "⏳"
        ret = f"{d['return_pct']:+.1f}%" if d["return_pct"] else "-"
        exit_p = f"{d['exit_price']:.2f}" if d["exit_price"] else "-"
        report += f"| {d['date']} | {d['stock_code']} | {dir_label} | {d['entry_price']:.2f} | {exit_p} | {ret} | {status_icon} |\n"

    # 验证明细
    report += "\n## 三、逐条验证明细\n\n"
    verifications = get_verifications()
    if verifications:
        report += "| 日期 | 股票 | 入场价 | 5日收益 | 10日收益 | 20日收益 | 5日正确 |\n"
        report += "|------|:----:|:------:|:-------:|:--------:|:--------:|:-------:|\n"
        for v in verifications[:30]:
            ok = "✅" if v.get("correct_5d") == 1 else ("❌" if v.get("correct_5d") == 0 else "➖")
            r5 = f"{v['return_5d']:+.1f}%" if v.get("return_5d") else "-"
            r10 = f"{v['return_10d']:+.1f}%" if v.get("return_10d") else "-"
            r20 = f"{v['return_20d']:+.1f}%" if v.get("return_20d") else "-"
            report += f"| {v.get('entry_date', '-')} | {v['stock_code']} | {v.get('entry_price', '-')} | {r5} | {r10} | {r20} | {ok} |\n"
    else:
        report += "暂无验证数据。\n"

    report += """

## ⚠️ 风险提示

- 本回测基于有限历史数据，**不代表未来表现**
- 信号数量较少时，胜率统计意义有限
- 未考虑交易成本（佣金、滑点等）
- 虚拟交易为简化模型，使用收盘价作为入场出场价格
- 峰哥反向指标为经验逻辑，请结合其他分析方法综合判断
"""

    return report


# ==================== 计算持仓市值 ====================

def calculate_portfolio_value(initial_capital: float = 100000) -> dict:
    """计算虚拟组合当前净值。"""
    trades_summary = get_trade_summary()
    open_trades_list = get_open_trades()

    # 已平仓盈亏
    closed_pnl = trades_summary["total_return_pct"]  # 简化：累计百分比

    # 未平仓按现价估算
    open_pnl = 0
    for t in open_trades_list:
        # 暂用入场价
        open_pnl += 0

    total_pnl = closed_pnl + open_pnl
    nav = initial_capital * (1 + total_pnl / 100)

    return {
        "initial_capital": initial_capital,
        "nav": round(nav, 2),
        "total_return_pct": round(total_pnl, 1),
        "closed_pnl_pct": round(closed_pnl, 1),
        "open_positions": len(open_trades_list),
    }


# ==================== CLI ====================

if __name__ == "__main__":
    import sys
    init_db()

    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        metrics = run_backtest()
        print(f"\n📊 回测结果: 胜率5d={metrics['win_rate_5d']}% 胜率10d={metrics['win_rate_10d']}%")
    else:
        report = generate_backtest_report()
        out_path = Path(__file__).resolve().parent.parent / "output" / f"回测报告_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        out_path.write_text(report, encoding="utf-8")
        out_path.write_text(report, encoding="utf-8")
        print(f"📄 回测报告已保存: {out_path}")
        print(report[:500])
