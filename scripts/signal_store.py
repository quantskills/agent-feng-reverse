"""
峰哥反向指标 — 信号数据库 & 虚拟交易系统
=========================================
SQLite 持久化存储，支持信号记录、虚拟交易、回测查询。

信号表 (signals)：存储每次分析的完整结果
交易表 (trades)：虚拟反向交易记录（峰哥看多→我们做空，峰哥看空→我们做多）
验证表 (verifications)：信号 vs 实际走势的对比结果
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_DIR = Path(__file__).resolve().parent.parent / "output"
DB_PATH = DB_DIR / "signal_store.db"


def get_connection() -> sqlite3.Connection:
    """获取数据库连接（WAL模式，Row工厂）。"""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构（幂等）。"""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,
            source_text     TEXT NOT NULL,
            stock_codes     TEXT DEFAULT '[]',
            sectors         TEXT DEFAULT '[]',
            sentiment       TEXT NOT NULL,
            strength        TEXT NOT NULL,
            final_strength  TEXT NOT NULL,
            behavioral_detected    INTEGER DEFAULT 0,
            behavioral_action      TEXT DEFAULT '[]',
            behavioral_weight      INTEGER DEFAULT 0,
            reverse_signal  TEXT NOT NULL,
            reverse_strength INTEGER DEFAULT 0,
            signal_label    TEXT NOT NULL,
            reason          TEXT DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id       INTEGER NOT NULL,
            stock_code      TEXT NOT NULL,
            stock_name      TEXT DEFAULT '',
            trade_date      TEXT NOT NULL,
            direction       TEXT NOT NULL,      -- 'long' (反向看多=做多) / 'short' (反向看空=做空)
            entry_price     REAL,
            exit_price      REAL,
            exit_date       TEXT,
            return_pct      REAL,
            pnl             REAL,
            status          TEXT DEFAULT 'open', -- 'open' / 'closed'
            close_reason    TEXT DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        );

        CREATE TABLE IF NOT EXISTS verifications (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id       INTEGER NOT NULL,
            stock_code      TEXT NOT NULL,
            entry_date      TEXT,
            entry_price     REAL,
            price_5d        REAL,
            price_10d       REAL,
            price_20d       REAL,
            return_5d       REAL,
            return_10d      REAL,
            return_20d      REAL,
            correct_5d      INTEGER,
            correct_10d     INTEGER,
            correct_20d     INTEGER,
            verified_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES signals(id),
            UNIQUE(signal_id, stock_code)
        );

        CREATE TABLE IF NOT EXISTS agent_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time        TEXT NOT NULL,
            mode            TEXT NOT NULL,
            posts_fetched   INTEGER DEFAULT 0,
            signals_saved   INTEGER DEFAULT 0,
            trades_opened   INTEGER DEFAULT 0,
            trades_closed   INTEGER DEFAULT 0,
            charts_generated INTEGER DEFAULT 0,
            report_path     TEXT DEFAULT '',
            errors          TEXT DEFAULT '[]',
            duration_seconds REAL DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_agent_log_time ON agent_log(run_time);

        CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(date);
        CREATE INDEX IF NOT EXISTS idx_signals_reverse ON signals(reverse_signal);
        CREATE INDEX IF NOT EXISTS idx_trades_stock ON trades(stock_code);
        CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
        CREATE INDEX IF NOT EXISTS idx_verifications_signal ON verifications(signal_id);
    """)
    conn.commit()
    conn.close()


# ==================== 信号存储 ====================

def save_signal(
    date: str,
    source_text: str,
    stock_codes: list,
    sectors: list,
    sentiment: str,
    strength: str,
    final_strength: str,
    behavioral: dict,
    reverse_signal: str,
    reverse_strength: int,
    signal_label: str,
    reason: str,
) -> int:
    """保存一条信号，返回 signal_id。"""
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO signals
        (date, source_text, stock_codes, sectors, sentiment, strength, final_strength,
         behavioral_detected, behavioral_action, behavioral_weight,
         reverse_signal, reverse_strength, signal_label, reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        date, source_text,
        json.dumps(stock_codes, ensure_ascii=False),
        json.dumps(sectors, ensure_ascii=False),
        sentiment, strength, final_strength,
        1 if behavioral.get("detected") else 0,
        json.dumps([s["action"] for s in behavioral.get("signals", [])], ensure_ascii=False),
        behavioral.get("max_weight", 0),
        reverse_signal, reverse_strength, signal_label, reason,
    ))
    signal_id = cur.lastrowid
    conn.commit()
    conn.close()
    return signal_id


def save_signal_from_analysis(post_text: str, post_date: str, analysis: dict, signal: dict) -> int:
    """便捷包装：从 analyze_sentiment 的输出直接存入数据库。"""
    behavioral = analysis.get("behavioral", {})
    return save_signal(
        date=post_date,
        source_text=post_text[:500],
        stock_codes=analysis.get("stock_codes", []),
        sectors=analysis.get("sectors", []),
        sentiment=analysis.get("sentiment", "neutral"),
        strength=analysis.get("strength", "weak"),
        final_strength=analysis.get("final_strength", "weak"),
        behavioral=behavioral,
        reverse_signal=signal.get("signal", "neutral"),
        reverse_strength=signal.get("signal_strength", 0),
        signal_label=signal.get("signal_label", ""),
        reason=signal.get("reason", ""),
    )


# ==================== 查询 ====================

def get_all_signals(limit: int = 200, offset: int = 0) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY date DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signals_by_stock(stock_code: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM signals WHERE stock_codes LIKE ? ORDER BY date DESC",
        (f"%{stock_code}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signals_by_date_range(start: str, end: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM signals WHERE substr(date,1,10) >= ? AND substr(date,1,10) <= ? ORDER BY date", (start, end)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unverified_signals() -> list[dict]:
    """返回有股票代码但尚未验证的信号。"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.* FROM signals s
        LEFT JOIN verifications v ON s.id = v.signal_id
        WHERE s.stock_codes != '[]' AND v.id IS NULL
        ORDER BY s.date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signal_stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    by_type = conn.execute(
        "SELECT reverse_signal, COUNT(*) as cnt FROM signals GROUP BY reverse_signal"
    ).fetchall()
    by_strength = conn.execute(
        "SELECT reverse_strength, COUNT(*) as cnt FROM signals GROUP BY reverse_strength"
    ).fetchall()
    with_stocks = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE stock_codes != '[]'"
    ).fetchone()[0]
    total_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    open_trades = conn.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0]
    conn.close()
    return {
        "total_signals": total,
        "by_reverse_type": dict(by_type),
        "by_reverse_strength": dict(by_strength),
        "signals_with_stock_codes": with_stocks,
        "total_trades": total_trades,
        "open_trades": open_trades,
    }


# ==================== Agent 日志 ====================

def log_agent_run(run_data: dict) -> int:
    """记录一次 Agent 运行日志。"""
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO agent_log
        (run_time, mode, posts_fetched, signals_saved, trades_opened, trades_closed,
         charts_generated, report_path, errors, duration_seconds)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        run_data.get("run_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        run_data.get("mode", "daily"),
        run_data.get("posts_fetched", 0),
        run_data.get("signals_saved", 0),
        run_data.get("trades_opened", 0),
        run_data.get("trades_closed", 0),
        run_data.get("charts_generated", 0),
        run_data.get("report_path", ""),
        json.dumps(run_data.get("errors", []), ensure_ascii=False),
        run_data.get("duration_seconds", 0),
    ))
    log_id = cur.lastrowid
    conn.commit()
    conn.close()
    return log_id


def get_agent_status() -> dict:
    """获取 Agent 运行状态。"""
    conn = get_connection()
    last = conn.execute(
        "SELECT * FROM agent_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    recent = conn.execute(
        "SELECT COUNT(*) as runs, SUM(signals_saved) as total_sigs, "
        "SUM(trades_opened) as total_opens, SUM(trades_closed) as total_closes "
        "FROM agent_log WHERE run_time >= date('now', '-7 days')"
    ).fetchone()
    conn.close()
    return {
        "last_run": dict(last) if last else None,
        "weekly": dict(recent) if recent else {"runs": 0, "total_sigs": 0, "total_opens": 0, "total_closes": 0},
    }


# ==================== Agent 交易管理 ====================

def get_signals_since(last_date: str) -> list[dict]:
    """获取指定日期之后的所有信号（含该日）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM signals WHERE substr(date,1,10) >= ? ORDER BY date", (last_date,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trades_by_stock(stock_code: str, status: str = "open") -> list[dict]:
    """查询某只股票的未平仓交易。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT t.*, s.date as signal_date FROM trades t "
        "JOIN signals s ON t.signal_id = s.id "
        "WHERE t.stock_code=? AND t.status=? ORDER BY t.id", (stock_code, status)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_price_for_stock(stock_code: str) -> float | None:
    """通过 Pandadata 获取股票最新收盘价。"""
    import os
    os.environ.setdefault("DEFAULT_USERNAME", "super_data_user")
    os.environ.setdefault("DEFAULT_PASSWORD", "panda@2026^_^")
    try:
        from panda_data import init_token, get_stock_daily
        init_token()
        # 标准化股票代码
        code = stock_code.strip().split(".")[0]
        if code.startswith("6"):
            symbol = f"{code}.SH"
        elif code.startswith(("0", "3")):
            symbol = f"{code}.SZ"
        else:
            symbol = code
        df = get_stock_daily(symbol=symbol)
        if df is not None and not df.empty:
            # 取最新收盘价
            if "close" in df.columns:
                return float(df.iloc[-1]["close"])
    except Exception:
        return None
    return None


def auto_close_trades(config: dict = None) -> list[dict]:
    """检查所有未平仓头寸，满足条件自动平仓。

    Args:
        config: {"take_profit_pct": 10, "stop_loss_pct": -5, "max_hold_days": 30}

    Returns:
        list of closed trade dicts
    """
    if config is None:
        config = {"take_profit_pct": 10, "stop_loss_pct": -5, "max_hold_days": 30}

    conn = get_connection()
    open_trades = conn.execute(
        "SELECT t.*, s.date as signal_date FROM trades t "
        "JOIN signals s ON t.signal_id = s.id WHERE t.status='open'"
    ).fetchall()
    conn.close()

    closed = []
    for t in open_trades:
        trade = dict(t)
        current_price = get_latest_price_for_stock(trade["stock_code"])
        if current_price is None:
            continue

        entry = trade["entry_price"]
        direction = trade["direction"]
        if direction == "long":
            ret = (current_price - entry) / entry * 100
        else:
            ret = (entry - current_price) / entry * 100

        reason = None
        if ret >= config.get("take_profit_pct", 10):
            reason = "take_profit"
        elif ret <= config.get("stop_loss_pct", -5):
            reason = "stop_loss"
        else:
            # 检查持仓天数
            try:
                signal_date = trade.get("signal_date", trade["trade_date"])
                sd = datetime.strptime(signal_date[:10], "%Y-%m-%d") if signal_date else datetime.now()
                days_held = (datetime.now() - sd).days
                if days_held > config.get("max_hold_days", 30):
                    reason = "max_hold_reached"
            except Exception:
                pass

        if reason:
            close_trade(trade["id"], current_price, datetime.now().strftime("%Y-%m-%d"), reason)
            closed.append({**trade, "exit_price": current_price, "return_pct": round(ret, 2), "close_reason": reason})

    return closed


# ==================== 虚拟交易系统 ====================

def open_trade(signal_id: int, stock_code: str, stock_name: str,
               trade_date: str, direction: str, entry_price: float) -> int:
    """开仓：根据反向信号创建虚拟交易。"""
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO trades (signal_id, stock_code, stock_name, trade_date, direction, entry_price, status)
        VALUES (?,?,?,?,?,?, 'open')
    """, (signal_id, stock_code, stock_name, trade_date, direction, entry_price))
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()
    return trade_id


def close_trade(trade_id: int, exit_price: float, exit_date: str, close_reason: str = ""):
    """平仓：计算盈亏并关闭交易。"""
    conn = get_connection()
    trade = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    if not trade or trade["status"] == "closed":
        conn.close()
        return

    entry = trade["entry_price"]
    direction = trade["direction"]
    if direction == "long":
        return_pct = (exit_price - entry) / entry * 100
    else:
        return_pct = (entry - exit_price) / entry * 100
    pnl = return_pct  # 简单按百分比

    conn.execute("""
        UPDATE trades SET exit_price=?, exit_date=?, return_pct=?, pnl=?, status='closed', close_reason=?
        WHERE id=?
    """, (exit_price, exit_date, return_pct, pnl, close_reason, trade_id))
    conn.commit()
    conn.close()


def get_open_trades() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM trades WHERE status='open' ORDER BY trade_date"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trade_summary() -> dict:
    """交易系统总览。"""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    closed = conn.execute("SELECT COUNT(*) FROM trades WHERE status='closed'").fetchone()[0]
    wins = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status='closed' AND return_pct > 0"
    ).fetchone()[0]
    losses = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status='closed' AND return_pct <= 0"
    ).fetchone()[0]
    total_return = conn.execute(
        "SELECT COALESCE(SUM(return_pct), 0) FROM trades WHERE status='closed'"
    ).fetchone()[0]
    avg_return = conn.execute(
        "SELECT COALESCE(AVG(return_pct), 0) FROM trades WHERE status='closed'"
    ).fetchone()[0]

    by_dir = conn.execute(
        "SELECT direction, COUNT(*), AVG(return_pct) FROM trades WHERE status='closed' GROUP BY direction"
    ).fetchall()

    conn.close()
    win_rate = (wins / closed * 100) if closed > 0 else 0
    return {
        "total_trades": total,
        "closed_trades": closed,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_return_pct": round(total_return, 1),
        "avg_return_pct": round(avg_return, 1),
        "by_direction": [{"direction": r[0], "count": r[1], "avg_return": round(r[2], 1)} for r in by_dir],
    }


# ==================== 验证/回测 ====================

def save_verification(signal_id: int, stock_code: str, data: dict):
    """保存信号验证结果。"""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO verifications
        (signal_id, stock_code, entry_date, entry_price,
         price_5d, price_10d, price_20d,
         return_5d, return_10d, return_20d,
         correct_5d, correct_10d, correct_20d)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        signal_id, stock_code,
        data.get("entry_date"), data.get("entry_price"),
        data.get("price_5d"), data.get("price_10d"), data.get("price_20d"),
        data.get("return_5d"), data.get("return_10d"), data.get("return_20d"),
        data.get("correct_5d"), data.get("correct_10d"), data.get("correct_20d"),
    ))
    conn.commit()
    conn.close()


def get_verifications(signal_id: int = None, stock_code: str = None) -> list[dict]:
    conn = get_connection()
    query = "SELECT * FROM verifications WHERE 1=1"
    params = []
    if signal_id:
        query += " AND signal_id=?"
        params.append(signal_id)
    if stock_code:
        query += " AND stock_code=?"
        params.append(stock_code)
    rows = conn.execute(query + " ORDER BY entry_date", params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_backtest_metrics() -> dict:
    """汇总回测指标。"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT v.*, s.reverse_signal, s.reverse_strength, s.sectors
        FROM verifications v
        JOIN signals s ON v.signal_id = s.id
        WHERE v.correct_5d IS NOT NULL
    """).fetchall()
    conn.close()

    if not rows:
        return {"total": 0, "win_rate_5d": 0, "win_rate_10d": 0, "win_rate_20d": 0}

    data = [dict(r) for r in rows]
    total = len(data)
    win_5d = sum(1 for d in data if d["correct_5d"] == 1)
    win_10d = sum(1 for d in data if d["correct_10d"] == 1)
    win_20d = sum(1 for d in data if d["correct_20d"] == 1)

    returns_5d = [d["return_5d"] for d in data if d["return_5d"] is not None]
    returns_10d = [d["return_10d"] for d in data if d["return_10d"] is not None]
    returns_20d = [d["return_20d"] for d in data if d["return_20d"] is not None]

    return {
        "total_verifications": total,
        "win_rate_5d": round(win_5d / total * 100, 1) if total else 0,
        "win_rate_10d": round(win_10d / total * 100, 1) if total else 0,
        "win_rate_20d": round(win_20d / total * 100, 1) if total else 0,
        "avg_return_5d": round(sum(returns_5d) / len(returns_5d), 2) if returns_5d else 0,
        "avg_return_10d": round(sum(returns_10d) / len(returns_10d), 2) if returns_10d else 0,
        "avg_return_20d": round(sum(returns_20d) / len(returns_20d), 2) if returns_20d else 0,
    }


def close():
    """清理。"""
    pass


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "gb2312", "cp936"):
        sys.stdout.reconfigure(encoding="utf-8")
    init_db()
    print(f"[OK] 数据库已初始化: {DB_PATH}")
    stats = get_signal_stats()
    print(f"[DB] 信号总数: {stats['total_signals']}")
    print(f"[DB] 交易总数: {stats['total_trades']} (未平仓: {stats['open_trades']})")
