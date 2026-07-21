---
name: agent-feng-reverse
description: 峰哥虚拟交易系统 - 自主运行的反向指标虚拟交易Agent。自动跟踪微博、分析信号、执行反向虚拟交易、生成K线图表和交易报告。
license: GPL-3.0-only
metadata:
  organization: QuantSkills
  organization_url: https://github.com/quantskills
  repository: skill-feng-reverse
  repository_url: https://github.com/quantskills/skill-feng-reverse
  project_type: agent
  collection: feng-reverse
  creator: xixihaha-dzh
  maintainer: xixihaha-dzh
quantSkills:
  project_type: agent
  category: trading
  tags:
  - a-share
  - weibo
  - reverse-indicator
  - virtual-trading
  - autonomous
  - contrarian
  platforms:
  - claude-code
  - cursor
  status: draft
  validation_level: runnable
  maintainer_type: custom
  maintainer: xixihaha-dzh
  summary_zh: 自主运行的峰哥反向指标虚拟交易系统，自动跟踪微博、分析信号、执行反向虚拟交易、生成K线图表和交易报告
  summary_en: Autonomous virtual trading system that tracks Feng Ge's Weibo, analyzes signals, executes reverse virtual trades, and generates chart reports
---

# 峰哥虚拟交易系统

## 概述

此 Agent 将峰哥反向指标的数据 + 分析 + 交易能力整合为一个**自主运行的虚拟交易系统**。按设定的时间表自动执行完整的生命周期，无需人工介入。

## Agent 工作流

```
采集 → 分析 → 交易 → 验证 → 图表 → 报告
```

| 阶段 | 模块 | 说明 |
|:----:|------|------|
| 1 | `collect()` | 采集微博数据，去重 |
| 2 | `analyze()` | NLP分析 + 行为检测 + 反向信号 |
| 3 | `trade()` | 自动开平仓，止盈止损管理 |
| 4 | `verify()` | Pandadata 回测验证 |
| 5 | `chart()` | K线信号标注图 |
| 6 | `report()` | 日报 + 交易P&L |

## 与 SKILL 的区别

| 特性 | SKILL (原) | AGENT (新) |
|------|-----------|-----------|
| 触发方式 | 用户提问 | 定时器 / CLI |
| 数据输入 | 手动粘贴 / WebSearch | 缓存文件 / 自动读取 |
| 交易决策 | 用户参考 | 系统自动执行（虚拟） |
| 运行模式 | 单次交互 | 可循环 / 可调度 |
| 持仓管理 | 无 | 自动止盈止损 |
| 错误处理 | 用户重试 | 自动跳过续跑 |

## 启动方式

```bash
# 单次运行（日常模式）
python scripts/agent_runner.py --daily

# 持续监控模式（每 N 分钟循环）
python scripts/agent_runner.py --watch --interval 30

# 定时任务模式（被 cron 触发）
python scripts/agent_runner.py --cron

# 查看运行状态
python scripts/agent_runner.py --status

# 通过 main.py
python main.py --agent
```

## 调度建议

| 场景 | 频率 | 命令 |
|------|------|------|
| 盘后更新 | 每日 15:30 | `--daily` |
| 盘中监控 | 每 30 分钟 | `--watch --interval 30` |
| 每日早报 | 每日 09:00 | `--daily` |
| 人工触发 | 按需 | `--daily` |

### Cron 设置 (Linux/Mac)

```cron
30 15 * * 1-5 cd /path/to/skill-feng-reverse && python scripts/agent_runner.py --daily >> output/agent_cron.log 2>&1
0 9 * * 1-5 cd /path/to/skill-feng-reverse && python scripts/agent_runner.py --daily >> output/agent_morning.log 2>&1
```

### Windows 任务计划

创建 `run_agent.bat`:
```batch
cd /d D:\Pycharmproject\skill-feng-reverse
python scripts\agent_runner.py --daily >> output\agent_cron.log 2>&1
```

然后在"任务计划程序"中设置每日 15:30 触发。

## 虚拟交易规则

### 开仓规则
| 反向信号 | 操作 | 方向 |
|---------|------|:----:|
| bullish（峰哥看空→我们看多） | 买入 | long |
| bearish（峰哥看多→我们看空） | 卖出 | short |

### 平仓规则
| 条件 | 触发值 | 说明 |
|------|:------:|------|
| 止盈 | 收益 >= +10% | 自动止盈 |
| 止损 | 收益 <= -5% | 自动止损 |
| 超时 | 持仓 > 30天 | 强制平仓 |
| 反向信号 | 同一标的新信号 | 平仓换方向 |

### 仓位管理
- 单只股票最多 1 笔未平仓头寸
- 全部使用收盘价作为入场出场价
- 不设杠杆，不计算交易成本（简化模型）

## 数据依赖

- **Pandadata API** — 获取股票K线数据和最新价格（必需）
- **微博数据** — 通过缓存文件或 WebSearch 获取

## 输出文件

| 文件 | 说明 |
|------|------|
| `output/Agent交易报告_YYYYMMDD_HHMM.md` | Agent 自动生成的图文报告 |
| `output/signal_store.db` | 信号 + 交易 + Agent日志数据库 |
| `output/charts/` | K线信号标注图 |
| `output/agent_cron.log` | Cron 运行日志 |

## 局限性

1. 微博数据可能有数小时延迟，无法实时
2. 虚拟交易使用收盘价，未考虑滑点和交易成本
3. 仅基于峰哥亡命天涯单一信源
4. 反向指标可能随时间衰减
5. 未考虑大盘环境、板块轮动等宏观因素
6. 不支持多账户、风险控制、资金管理等高级功能
