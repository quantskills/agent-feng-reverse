"""
峰哥反向指标 — 微博数据采集脚本
================================
数据来源策略（按优先级）：
1. WebSearch（通过 Claude 的 WebSearch 能力）
2. 本地存档文件（JSON/CSV/TXT）
3. 手动输入

此脚本主要处理本地存档数据的读取和格式化。
"""

import json
import csv
import re
import sys
from pathlib import Path
from typing import Optional


def load_from_json(filepath: str) -> list[dict]:
    """从 JSON 文件加载微博数据。"""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 支持两种格式：直接的列表 或 { "weibo_posts": [...] }
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "weibo_posts" in data:
        return data["weibo_posts"]
    else:
        raise ValueError(f"无法识别的 JSON 格式: {filepath}")


def load_from_csv(filepath: str) -> list[dict]:
    """从 CSV 文件加载微博数据。"""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    posts = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            posts.append(row)

    return posts


def load_from_text(filepath: str) -> list[dict]:
    """从纯文本文件加载微博数据。

    格式约定：每条微博用空行分隔。
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 按空行分割
    raw_posts = re.split(r"\n\s*\n", content.strip())
    posts = []
    for i, raw in enumerate(raw_posts, 1):
        lines = raw.strip().split("\n")
        posts.append({
            "id": f"txt_{i}",
            "content": " ".join(lines),
            "date": "",
            "time": "",
            "source": "text_file",
        })

    return posts


def format_posts_for_analysis(posts: list[dict]) -> str:
    """将微博数据格式化为分析友好的文本。"""
    lines = []
    for i, post in enumerate(posts, 1):
        date = post.get("date", post.get("created_at", ""))
        time = post.get("time", "")
        content = post.get("content", post.get("text", ""))
        dt = f"{date} {time}".strip()
        lines.append(f"[{i}] [{dt}] {content}")

    return "\n".join(lines)


def save_to_cache(posts: list[dict], filepath: str):
    """将微博数据缓存到本地 JSON 文件。"""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "count": len(posts),
        "posts": posts,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"已缓存 {len(posts)} 条微博到 {filepath}")


def main():
    """CLI 入口。"""
    if len(sys.argv) < 3:
        print("用法: python fetch_posts.py <format> <filepath>")
        print("  支持格式: json, csv, txt")
        print("  示例: python fetch_posts.py json ./weibo_data.json")
        sys.exit(1)

    fmt = sys.argv[1].lower()
    filepath = sys.argv[2]

    loaders = {
        "json": load_from_json,
        "csv": load_from_csv,
        "txt": load_from_text,
    }

    if fmt not in loaders:
        print(f"不支持格式: {fmt}，可选: {', '.join(loaders.keys())}")
        sys.exit(1)

    try:
        posts = loaders[fmt](filepath)
        print(f"成功加载 {len(posts)} 条微博")
        print("\n--- 预览 ---")
        print(format_posts_for_analysis(posts[:3]))

        # 自动缓存
        cache_path = Path(filepath).with_suffix(".formatted.json")
        save_to_cache(posts, str(cache_path))

    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
