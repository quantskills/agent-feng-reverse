"""
峰哥反向指标 — K线图信号标注 & 走势分析
=========================================
从 Pandadata 获取股票日K线，在图上标出峰哥历次信号，
并显示信号后N日走势（涨跌标注）。
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import mplfinance as mpf

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CHART_DIR = Path(__file__).resolve().parent.parent / "output" / "charts"

# ==================== Pandadata 数据获取 ====================

def _init_pandadata():
    """初始化 Pandadata API 认证。"""
    os.environ.setdefault("DEFAULT_USERNAME", "super_data_user")
    os.environ.setdefault("DEFAULT_PASSWORD", "panda@2026^_^")
    os.environ.setdefault("JAVA_SERVICE_BASE_URL", "http://pandadata.pandaaiquant.com")
    try:
        from panda_data import init_token
        init_token()
        return True
    except Exception as e:
        print(f"  ⚠️ Pandadata 认证失败: {e}")
        return False


def normalize_code(code: str) -> str:
    """标准化A股代码为 Pandadata 格式。"""
    code = code.strip().split(".")[0]  # 去掉已有后缀
    if code.startswith("6"):
        return f"{code}.SH"
    elif code.startswith(("0", "3")):
        return f"{code}.SZ"
    elif code.startswith(("4", "8")):
        return f"{code}.BJ"
    return code


def fetch_kline(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取股票日K线数据。

    Args:
        stock_code: A股代码，如 "000001" 或 "000001.SZ"
        start_date: "YYYY-MM-DD"
        end_date: "YYYY-MM-DD"

    Returns:
        DataFrame with columns: date, open, high, low, close, volume
    """
    if not _init_pandadata():
        print("  ⚠️ 无法连接 Pandadata，尝试用模拟数据")
        return _generate_mock_kline(start_date, end_date)

    try:
        from panda_data import get_stock_daily
        symbol = normalize_code(stock_code)
        df = get_stock_daily(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if df is None or df.empty:
            print(f"  ⚠️ Pandadata 返回空数据，尝试模拟数据")
            return _generate_mock_kline(start_date, end_date)

        # 选择需要的列
        needed = {"open", "high", "low", "close", "volume"}
        avail = set(df.columns)
        if not needed.issubset(avail):
            print(f"  ⚠️ 缺少K线数据列，尝试模拟数据")
            return _generate_mock_kline(start_date, end_date)

        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)
        return df

    except Exception as e:
        print(f"  ⚠️ Pandadata 调用失败: {e}")
        return _generate_mock_kline(start_date, end_date)


def _generate_mock_kline(start_date: str, end_date: str) -> pd.DataFrame:
    """生成模拟K线数据（Pandadata 不可用时用于测试）。"""
    print("  📊 使用模拟K线数据")
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    dates = pd.date_range(start, end, freq="B")  # 仅交易日

    import numpy as np
    np.random.seed(42)
    n = len(dates)
    base = 10
    closes = base + np.cumsum(np.random.randn(n) * 0.3)
    opens = closes + np.random.randn(n) * 0.2
    highs = np.maximum(opens, closes) + abs(np.random.randn(n)) * 0.3
    lows = np.minimum(opens, closes) - abs(np.random.randn(n)) * 0.3
    volumes = np.random.randint(100000, 10000000, n)

    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes
    }, index=dates)
    df.index.name = "date"
    return df


# ==================== 信号查询 ====================

def query_signals_for_stock(stock_code: str, start_date: str, end_date: str) -> list[dict]:
    """从 signal_store 查询某只股票在日期范围内的信号。"""
    from scripts.signal_store import get_signals_by_stock
    signals = get_signals_by_stock(stock_code)
    # 过滤日期范围
    return [
        s for s in signals
        if start_date <= s["date"] <= end_date
    ]


# ==================== 核心绘图函数 ====================

def plot_signal_chart(
    stock_code: str,
    stock_name: str = "",
    start_date: str = "",
    end_date: str = "",
    show_days: int = 10,
    save_path: str = "",
) -> str:
    """绘制K线图 + 信号标注 + 后N日走势。

    功能：
    1. 蜡烛图展示股价走势
    2. 🟢 绿色上箭头 = 反向看多信号（峰哥看空→我们做多）
    3. 🔴 红色下箭头 = 反向看空信号（峰哥看多→我们做空）
    4. 箭头旁标注信号后N日涨跌幅

    Args:
        stock_code: 股票代码
        stock_name: 股票名称（可选）
        start_date: 起始日期，默认3个月前
        end_date: 截止日期，默认今天
        show_days: 信号后显示多少交易日
        save_path: 保存路径，默认 auto

    Returns:
        保存的 PNG 文件路径
    """
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start = datetime.now() - timedelta(days=180)
        start_date = start.strftime("%Y-%m-%d")

    # 取K线数据（多取一些给后N日留空间）
    fetch_end = (pd.Timestamp(end_date) + timedelta(days=show_days * 2)).strftime("%Y-%m-%d")
    df = fetch_kline(stock_code, start_date, fetch_end)
    if df.empty:
        print(f"❌ 无法获取 {stock_code} 的K线数据")
        return ""

    # 截取到 end_date
    df_plot = df[df.index <= end_date].copy()

    # 查询信号
    try:
        signals = query_signals_for_stock(stock_code, start_date, end_date)
    except Exception:
        signals = []

    # 构建信号标记列
    df_plot["bullish_marker"] = float("nan")
    df_plot["bearish_marker"] = float("nan")
    df_plot["bullish_text"] = ""
    df_plot["bearish_text"] = ""

    annotations = []

    for sig in signals:
        sig_date = sig["date"]
        try:
            sig_ts = pd.Timestamp(sig_date)
        except ValueError:
            continue
        if sig_ts not in df_plot.index:
            # 尝试找最近交易日
            nearby = df_plot.index[df_plot.index >= sig_ts]
            if len(nearby) == 0:
                continue
            sig_ts = nearby[0]

        candle = df_plot.loc[sig_ts]
        rev = sig["reverse_signal"]
        label = sig.get("signal_label", "")
        strength = sig.get("reverse_strength", 1)

        # 标注位置：看多在 candles 上方，看空在下方
        price_range = candle["high"] - candle["low"]
        y_offset = price_range * 1.5 if price_range > 0 else candle["close"] * 0.02

        if rev == "bullish":
            df_plot.at[sig_ts, "bullish_marker"] = candle["high"] + y_offset * 0.5
            df_plot.at[sig_ts, "bullish_text"] = f"BULL:{label}"

            future = df[df.index >= sig_ts].head(show_days + 1)
            if len(future) > 1:
                entry = candle["close"]
                exit_p = future.iloc[min(show_days, len(future)-1)]["close"]
                ret = (exit_p - entry) / entry * 100
                annotations.append({
                    "date": sig_ts, "type": "bullish", "label": label,
                    "entry": entry, "exit": exit_p,
                    "return": ret, "strength": strength,
                })
        elif rev == "bearish":
            df_plot.at[sig_ts, "bearish_marker"] = candle["low"] - y_offset * 0.5
            df_plot.at[sig_ts, "bearish_text"] = f"BEAR:{label}"

            future = df[df.index >= sig_ts].head(show_days + 1)
            if len(future) > 1:
                entry = candle["close"]
                exit_p = future.iloc[min(show_days, len(future)-1)]["close"]
                ret = (entry - exit_p) / entry * 100  # 做空收益
                annotations.append({
                    "date": sig_ts, "type": "bearish", "label": label,
                    "entry": entry, "exit": exit_p,
                    "return": ret, "strength": strength,
                })

    # 准备 addplot（只加有实际标记的）
    addplots = []
    if df_plot["bullish_marker"].notna().sum() > 0:
        addplots.append(mpf.make_addplot(
            df_plot["bullish_marker"], type="scatter",
            marker="^", color="lime", alpha=0.9,
            label="BULL Rev",
        ))
    if df_plot["bearish_marker"].notna().sum() > 0:
        addplots.append(mpf.make_addplot(
            df_plot["bearish_marker"], type="scatter",
            marker="v", color="red", alpha=0.9,
            label="BEAR Rev",
        ))

    # 标题（不使用emoji避免GBK问题）
    title = f"{stock_code} {stock_name} — Feng Ge Reverse Signal"
    if annotations:
        total_ret = sum(a["return"] for a in annotations)
        avg_ret = total_ret / len(annotations)
        wins = sum(1 for a in annotations if a["return"] > 0)
        title += f"\nSignals:{len(annotations)} Wins:{wins} Losses:{len(annotations)-wins} AvgRet:{avg_ret:+.1f}%"

    # 绘图
    CHART_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = mpf.plot(
        df_plot, type="candle",
        addplot=addplots if addplots else None,
        volume=True,
        style="charles",
        title=title,
        figsize=(16, 10),
        returnfig=True,
        tight_layout=True,
    )

    ax = axes[0]

    # 在信号位置添加文字标注
    for idx, row in df_plot.iterrows():
        if row["bullish_text"]:
            ax.annotate(
                row["bullish_text"],
                xy=(mdates.date2num(idx), row["bullish_marker"]),
                xytext=(0, 15), textcoords="offset points",
                fontsize=9, color="green", fontweight="bold",
                ha="center",
                arrowprops=dict(arrowstyle="->", color="green", lw=1),
            )
        if row["bearish_text"]:
            ax.annotate(
                row["bearish_text"],
                xy=(mdates.date2num(idx), row["bearish_marker"]),
                xytext=(0, -20), textcoords="offset points",
                fontsize=9, color="red", fontweight="bold",
                ha="center",
                arrowprops=dict(arrowstyle="->", color="red", lw=1),
            )

    # 后N日走势连线 + 涨跌标注
    for ann in annotations:
        sig_date = ann["date"]
        sig_num = mdates.date2num(sig_date)
        # 找信号日后 show_days 个交易日的实际位置
        future_idx = df.index[df.index >= sig_date]
        if len(future_idx) > 1:
            end_idx = min(show_days, len(future_idx) - 1)
            target = future_idx[end_idx]
            future_candle = df.loc[target]
            # 画从信号日到目标日的连线
            y_start = df_plot.loc[sig_date] if sig_date in df_plot.index else df.iloc[0]
            y_start_price = y_start["close"]

            # 计算画线终点在图上 y 位置
            # 用收盘价位置
            y_end_price = future_candle["close"]
            # 画垂直线标注
            color = "green" if ann["return"] > 0 else "red"
            ax.annotate(
                f"{ann['return']:+.1f}%",
                xy=(mdates.date2num(target), y_end_price),
                xytext=(15, 0), textcoords="offset points",
                fontsize=10, color=color, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=color, lw=1.5),
            )

    ax.legend(loc="best", fontsize=10)
    ax.grid(True, alpha=0.3)

    if not save_path:
        safe_code = stock_code.replace(".", "_")
        save_path = str(CHART_DIR / f"{safe_code}_{start_date}_{end_date}.png")

    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[CHART] 图表已保存: {save_path}")
    return save_path


# ==================== 多股对比图 ====================

def plot_multi_stock_charts(stock_codes: list[str], stock_names: list[str] = None,
                            start_date: str = "", end_date: str = "",
                            show_days: int = 10) -> list[str]:
    """批量生成多只股票的信号标注图。"""
    if not stock_names:
        stock_names = stock_codes
    paths = []
    for i, code in enumerate(stock_codes):
        name = stock_names[i] if i < len(stock_names) else code
        print(f"\n[CHART] 绘制 {code} {name}...")
        path = plot_signal_chart(code, name, start_date, end_date, show_days)
        if path:
            paths.append(path)
    return paths


# ==================== CLI ====================

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python plot_signals.py <stock_code> [start_date] [end_date]")
        print("示例: python plot_signals.py 000001 2026-06-01 2026-07-21")
        sys.exit(1)

    code = sys.argv[1]
    start = sys.argv[2] if len(sys.argv) > 2 else ""
    end = sys.argv[3] if len(sys.argv) > 3 else ""
    plot_signal_chart(code, "", start, end)
