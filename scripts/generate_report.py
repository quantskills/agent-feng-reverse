"""
峰哥反向指标 — 报告生成脚本
============================
将分析结果生成为 Markdown 报告。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


def _embed_charts(chart_paths: list[str]) -> str:
    """将图表路径转为 Markdown 图片引用。"""
    parts = []
    for cp in chart_paths:
        name = Path(cp).name
        parts.append(f"![{name}](charts/{name})")
    return "\n\n".join(parts)


def generate_report(
    posts: list[dict],
    analysis_results: list[dict],
    data_source: str = "WebSearch",
    report_date: Optional[str] = None,
    chart_paths: Optional[list[str]] = None,
    backtest_ref: bool = False,
) -> str:
    """生成完整的 Markdown 报告。

    Args:
        posts: 原始微博数据列表
        analysis_results: analyze_sentiment 的分析结果
        data_source: 数据来源描述
        report_date: 报告日期，默认今天

    Returns:
        Markdown 格式的报告文本
    """
    if report_date is None:
        report_date = datetime.now().strftime("%Y-%m-%d")

    # 统计
    total = len(posts)
    signals_bearish = [r for r in analysis_results if r["signal"]["signal"] == "bearish"]
    signals_bullish = [r for r in analysis_results if r["signal"]["signal"] == "bullish"]
    signals_neutral = [r for r in analysis_results if r["signal"]["signal"] == "neutral"]

    # 提取时间范围
    dates = [p.get("date", "") for p in posts if p.get("date")]
    date_range = f"{min(dates)} ~ {max(dates)}" if dates else "N/A"

    # 构建报告
    report = f"""# 峰哥反向指标日报 — {report_date}

## 📡 数据概况
- **数据来源**：{data_source}
- **覆盖时间**：{date_range}
- **分析条数**：{total} 条
- **生成时间**：{datetime.now().strftime("%Y-%m-%d %H:%M")}

## 📊 信号总览

| 信号类型 | 数量 | 占比 |
|---------|:----:|:----:|
| 🔴 反向看空（峰哥看多 → 谨慎） | {len(signals_bearish)} | {len(signals_bearish)/total*100:.0f}% |
| 🟢 反向看多（峰哥看空 → 关注） | {len(signals_bullish)} | {len(signals_bullish)/total*100:.0f}% |
| ⚪ 无明显信号 | {len(signals_neutral)} | {len(signals_neutral)/total*100:.0f}% |

## 📈 K线信号图

{_embed_charts(chart_paths) if chart_paths else '（本次信号未涉及具体股票代码，未生成K线图）'}

## 🔄 详细分析

"""

    for i, (post, result) in enumerate(zip(posts, analysis_results), 1):
        content = post.get("content", post.get("text", ""))
        date = post.get("date", "")
        a = result["analysis"]
        s = result["signal"]

        # 截取过长内容
        display_content = content[:200] + "..." if len(content) > 200 else content

        # 信号 emoji
        signal_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}[s["signal"]]
        sentiment_emoji = {"bullish": "📈", "bearish": "📉", "neutral": "➖"}[a["sentiment"]]

        stocks = ", ".join(a["stock_codes"]) or "未提及"
        sectors = ", ".join(a["sectors"]) or "未提及"

        report += f"""### {i}. {date}

**原文**：
> {display_content}

**观点分析**：{sentiment_emoji} {a['sentiment']}（强度: {a['strength']}）
**涉及标的**：股票 [{stocks}] · 板块 [{sectors}]

**{signal_emoji} 反向信号**：{s['signal_label']}（强度: {'⭐' * s['signal_strength']}）
**理由**：{s['reason']}

"""

    # 风险提示
    report += """## ⚠️ 风险提示

本报告基于"峰哥反向指标"的社区经验逻辑生成，仅供研究参考，**不构成任何投资建议**。

- 反向信号是概率参考，不是绝对规则
- 单次信号可能有误，请结合其他分析方法综合判断
- 过去表现不代表未来结果
- 市场有风险，投资需谨慎

---

*报告由 峰哥反向指标 skill 自动生成 | {date_time}*
""".format(date_time=datetime.now().strftime("%Y-%m-%d %H:%M"))

    return report


def save_report(report: str, output_dir: str = "output") -> str:
    """保存报告到文件。"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d_%H%M")
    filename = output_path / f"峰哥反向指标_{today}.md"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"报告已保存: {filename}")
    return str(filename)


def main():
    """CLI 入口 — 从 JSON 分析结果生成报告。"""
    import sys

    if len(sys.argv) < 2:
        print("用法: python generate_report.py <analysis_json> [output_dir]")
        print("  analysis_json: 包含 posts 和 results 的 JSON 文件路径")
        sys.exit(1)

    json_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"

    if not Path(json_path).exists():
        print(f"错误: 文件不存在 {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    posts = data.get("posts", [])
    results = data.get("analysis_results", [])

    if not posts or not results:
        print("错误: JSON 文件缺少 'posts' 或 'analysis_results' 字段")
        sys.exit(1)

    report = generate_report(posts, results)
    path = save_report(report, output_dir)
    print(f"报告已生成: {path}")


if __name__ == "__main__":
    main()
