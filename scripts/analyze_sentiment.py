"""
峰哥反向指标 — 观点分析与反向信号生成脚本
=========================================
分析微博文本，提取观点、识别标的、生成反向信号。
"""

import json
import re
import sys
from typing import Optional

# Windows terminal encoding workaround
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "gb2312", "cp936"):
    sys.stdout.reconfigure(encoding="utf-8")


# A股股票代码模式：6位数字，通常以 0/3/6/8/4 开头
STOCK_CODE_PATTERN = re.compile(r"[03684]\d{5}")

# A股常见板块/概念关键词
SECTOR_KEYWORDS = {
    "AI": ["人工智能", "AI", "算力", "大模型", "机器人", "ai"],
    "新能源": ["新能源", "光伏", "锂电", "电池", "风电", "新能源车", "电车"],
    "半导体": ["半导体", "芯片", "集成电路", "光刻", "封测"],
    "白酒": ["白酒", "茅台", "五粮液", "消费"],
    "医药": ["医药", "医疗", "创新药", "中药", "生物"],
    "金融": ["银行", "券商", "保险", "证券", "金融"],
    "地产": ["地产", "房地产", "楼市", "房产"],
    "军工": ["军工", "国防", "航天"],
    "消费": ["消费", "零售", "食品", "饮料", "家电"],
    "周期": ["有色", "煤炭", "钢铁", "化工", "石油"],
}

# 看多信号词（中文）
BULLISH_WORDS = [
    "加仓", "买入", "抄底", "满仓", "重仓", "梭哈",
    "大涨", "暴涨", "突破", "起飞", "牛市", "主升",
    "牛逼", "稳了", "放心", "吃肉", "大肉", "涨停",
    "看好", "看涨", "做多", "持有", "持股待涨",
    "上车", "发车", "猛干", "全仓", "进攻",
    "底部", "低估", "便宜", "反弹", "反转",
    "机会", "行情", "爆发", "拉升", "走强",
    "新高", "破位向上",
]

# 看空信号词（中文）
BEARISH_WORDS = [
    "减仓", "清仓", "卖出", "割肉", "空仓", "轻仓",
    "大跌", "暴跌", "崩盘", "完蛋", "熊市", "主跌",
    "垃圾", "废物", "坑人", "骗局", "狗屎", "恶心",
    "看空", "看跌", "做空", "止损", "离场", "跑路",
    "下车", "清完", "全部卖了",
    "顶部", "高估", "太贵", "危险", "风险",
    "撤退", "逃顶", "出局", "破位", "杀跌",
    "新低", "破位向下", "阴跌", "闪崩",
    # 行为信号：卸载/销户/退出 — 峰哥经典"不玩了"模式
    "卸载同花顺", "卸载软件", "销户", "退出股市",
    "不玩了", "不玩儿了", "再也不玩", "拜拜",
    "彻底卸载", "删软件", "删app",
]


def extract_stock_codes(text: str) -> list[str]:
    """提取文本中的 A 股股票代码。"""
    codes = STOCK_CODE_PATTERN.findall(text)
    # 过滤掉疑似非股票数字（年份、日期等）
    valid_codes = []
    for code in codes:
        # 排除年份（20xx/19xx）
        if code.startswith("20") or code.startswith("19"):
            continue
        # 排除明显是日期的数字
        if len(code) != 6:
            continue
        valid_codes.append(code)
    return list(set(valid_codes))


def extract_sectors(text: str) -> list[str]:
    """提取文本中提到的板块/行业。"""
    mentioned = []
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text.lower():
                mentioned.append(sector)
                break
    return mentioned


def analyze_sentiment(text: str) -> dict:
    """分析单条微博的情绪和观点。

    Returns:
        {
            "bullish_score": int,   # 看多得分
            "bearish_score": int,   # 看空得分
            "sentiment": str,       # bullish / bearish / neutral
            "strength": str,        # strong / moderate / weak
            "stock_codes": [...],
            "sectors": [...],
        }
    """
    bullish_count = sum(1 for w in BULLISH_WORDS if w in text)
    bearish_count = sum(1 for w in BEARISH_WORDS if w in text)

    # 情绪判断
    if bullish_count > bearish_count:
        sentiment = "bullish"
        score = bullish_count - bearish_count
    elif bearish_count > bullish_count:
        sentiment = "bearish"
        score = bearish_count - bullish_count
    else:
        sentiment = "neutral"
        score = 0

    # 强度判断
    has_exclamation = "！" in text or "!" in text
    has_repetition = len(set(re.findall(r"[加买减清卖割抄梭满](?:[仓入底仓仓肉仓柴)]|$)", text))) > 2
    has_position = bool(re.search(r"[持买加减清][仓有]", text))
    has_earnings_proof = ("晒" in text or "截图" in text) and ("收益" in text or "持仓" in text or "盈利" in text or "亏损" in text)

    strength_factors = 0
    if score >= 3:
        strength_factors += 1
    if has_exclamation:
        strength_factors += 1
    if has_repetition:
        strength_factors += 1
    if has_position:
        strength_factors += 1
    if has_earnings_proof:
        strength_factors += 2

    if strength_factors >= 3:
        strength = "strong"
    elif strength_factors >= 1:
        strength = "moderate"
    else:
        strength = "weak"

    return {
        "bullish_score": bullish_count,
        "bearish_score": bearish_count,
        "sentiment": sentiment,
        "strength": strength,
        "stock_codes": extract_stock_codes(text),
        "sectors": extract_sectors(text),
        "has_earnings_proof": has_earnings_proof,
    }


def generate_reverse_signal(analysis: dict, post_text: str = "") -> dict:
    """根据观点分析生成反向信号。

    Returns:
        {
            "signal": str,           # bearish / bullish / neutral
            "signal_label": str,     # 中文信号标签
            "signal_strength": int,  # 1-3
            "reason": str,           # 信号理由
        }
    """
    sentiment = analysis["sentiment"]
    strength = analysis["strength"]
    has_earnings = analysis.get("has_earnings_proof", False)

    strength_map = {"weak": 1, "moderate": 2, "strong": 3}

    # 反向映射
    if sentiment == "bullish":
        base_strength = strength_map.get(strength, 1)
        if has_earnings:
            base_strength = min(3, base_strength + 1)
        signal = "bearish"
        label = {
            1: "轻度反向看空",
            2: "反向看空",
            3: "强烈反向看空 [!]",
        }[base_strength]
        reason = f"峰哥看多（强度:{strength}），反向逻辑 → 谨慎/看空"
        if has_earnings:
            reason += "，且有持仓/收益证据，见顶风险增加"

    elif sentiment == "bearish":
        base_strength = strength_map.get(strength, 1)
        if has_earnings:
            base_strength = min(3, base_strength + 1)
        signal = "bullish"
        label = {
            1: "轻度反向看多",
            2: "反向看多",
            3: "强烈反向看多 [目标]",
        }[base_strength]
        reason = f"峰哥看空（强度:{strength}），反向逻辑 → 关注/看多"
        if has_earnings:
            reason += "，且有亏损/割肉证据，见底机会增加"

    else:
        signal = "neutral"
        label = "无明显信号"
        base_strength = 0
        reason = "峰哥观点中性，无明确方向信号"

    return {
        "signal": signal,
        "signal_label": label,
        "signal_strength": base_strength,
        "reason": reason,
    }


def analyze_posts(posts: list[str]) -> list[dict]:
    """批量分析多条微博。"""
    results = []
    for i, post in enumerate(posts, 1):
        analysis = analyze_sentiment(post)
        signal = generate_reverse_signal(analysis, post)

        results.append({
            "index": i,
            "text_preview": post[:100] + "..." if len(post) > 100 else post,
            "analysis": analysis,
            "signal": signal,
        })

    return results


def format_results(results: list[dict]) -> str:
    """将分析结果格式化为可读文本。"""
    lines = []
    for r in results:
        a = r["analysis"]
        s = r["signal"]
        lines.append(f"[{r['index']}] 观点: {a['sentiment']}({a['strength']}) | "
                     f"反向: {s['signal_label']} | "
                     f"股票: {','.join(a['stock_codes']) or '无'} | "
                     f"板块: {','.join(a['sectors']) or '无'}")
        lines.append(f"     {r['text_preview']}")
        lines.append(f"     {s['reason']}")
        lines.append("")

    return "\n".join(lines)


def main():
    """CLI 入口 — 从 stdin 或参数读取文本分析。"""
    import sys

    if len(sys.argv) > 1:
        # 从命令行参数读取
        text = " ".join(sys.argv[1:])
        posts = [text]
    else:
        # 从 stdin 读取（每行一条微博）
        posts = [line.strip() for line in sys.stdin if line.strip()]

    if not posts:
        print("请提供要分析的微博文本。")
        print("用法: python analyze_sentiment.py <微博文本>")
        print("  或: echo '微博内容' | python analyze_sentiment.py")
        sys.exit(1)

    results = analyze_posts(posts)
    print("\n=== 分析结果 ===\n")
    print(format_results(results))

    # 汇总统计
    total = len(results)
    signals = [r["signal"]["signal"] for r in results]
    bullish_s = signals.count("bullish")
    bearish_s = signals.count("bearish")
    neutral_s = signals.count("neutral")

    print("--- 汇总 ---")
    print(f"总分析数: {total}")
    print(f"[看多] 反向看多信号: {bullish_s}")
    print(f"[看空] 反向看空信号: {bearish_s}")
    print(f"[中性] 无明显信号: {neutral_s}")


if __name__ == "__main__":
    main()
