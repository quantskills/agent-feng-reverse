---
name: skill-feng-reverse
description: 追踪微博"峰哥亡命天涯"的发言，提取其股票/市场观点，生成反向操作信号和跟踪报告。峰哥是A股知名反向指标——其公开观点具有稳定反向参考价值。Use when the user asks for 峰哥反向指标, 峰哥亡命天涯, 反向指标, 峰哥观点, 峰哥持仓, or to check what Feng Ge is saying about the market.
license: GPL-3.0-only
metadata:
  organization: QuantSkills
  organization_url: https://github.com/quantskills
  repository: skill-feng-reverse
  repository_url: https://github.com/quantskills/skill-feng-reverse
  project_type: skill
  collection: feng-reverse
  creator: xixihaha-dzh
  maintainer: xixihaha-dzh
quantSkills:
  project_type: skill
  category: monitor
  tags:
  - a-share
  - weibo
  - reverse-indicator
  - sentiment
  - feng-ge
  - contrarian
  - backtest
  - chart
  - database
  platforms:
  - claude-code
  - cursor
  status: draft
  validation_level: runnable
  maintainer_type: custom
  maintainer: xixihaha-dzh
  summary_zh: 追踪微博"峰哥亡命天涯"的发言，提取股票/市场观点，生成反向操作信号。峰哥是A股知名反向指标，其公开观点具有稳定的反向参考价值。
  summary_en: Tracks Weibo user "峰哥亡命天涯" (Feng Ge), a well-known A-share reverse indicator. Extracts stock/market opinions from his posts and generates contrarian trading signals.
---

# 峰哥反向指标

追踪微博「峰哥亡命天涯」的公开发言，提取其对个股、板块、大盘的观点与预测，基于**反向指标逻辑**生成信号和跟踪报告。

**项目状态**：社区项目 / 研究实验性 / 未认证
**维护者**：xixihaha-dzh
**许可证**：GPL-3.0-only

## 核心理念

峰哥亡命天涯是A股社区公认的**反向指标**。大量历史案例表明：

| 峰哥表现 | 反向信号 | 逻辑 |
|---------|---------|------|
| 强烈看多某股/某板块 | 🔴 谨慎/看空 | 历史高概率见顶 |
| 强烈看空某股/某板块 | 🟢 关注/看多 | 历史高概率见底 |
| 晒持仓收益/浮盈 | 🔴 可能见顶 | 过度自信信号 |
| 晒亏损/割肉 | 🟢 可能见底 | 恐慌情绪信号 |
| 频繁提及某只股票 | 🔴 回避 | "奶死"效应 |
| 骂某只股票/板块 | 🟢 关注 | 情绪宣泄见底 |
| **卸载交易软件/销户/宣布退出** | 🟢 **强烈看多** | **行为信号：反复割肉离场=底部特征** |
| **重新下载软件/回归市场** | 🔴 **强烈看空** | **行为信号：追高回归=顶部特征** |

> ⚠️ 反向信号是概率参考，不是绝对规则。峰哥的反向准确率需要通过持续跟踪来验证和校准。本工具仅为研究与教育目的，不构成投资建议。

## 行为信号（重要补充）

峰哥的**行为动作**比口头表达更具信号价值。典型行为信号包括：

| 行为 | 实际含义 | 反向信号 | 历史验证 |
|------|---------|---------|---------|
| 卸载同花顺 / 删软件 | 清仓离场，彻底放弃 | 🟢 强烈反向看多（底部信号） | 已发生多次，每次卸载后市场反弹 |
| 重新安装 / 全仓买入 | 追高回归，怕踏空 | 🔴 强烈反向看空（顶部信号） | 每次回归都是阶段性高点 |
| 销户 / 宣布永久退出 | 绝望割肉 | 🟢 强烈反向看多 | 经典见底行为 |
| 频繁晒单 / 炫耀盈利 | 过度自信 | 🔴 见顶预警 | 需结合持仓判断 |
| 连续多日不发言 | 已无资金加仓 / 躺平 | 🟢 可能见底 | 沉默往往是底部特征 |

**行为信号 > 口头信号**：动作比语言更真实，行为信号权重应高于文本分析。

## 工作流程

### Step 1：数据采集

获取峰哥的近期微博数据：

**方案A — WebSearch（推荐，无需凭证）：**
用 `WebSearch` 搜索 "峰哥亡命天涯 微博" 或 "峰哥亡命天涯 site:weibo.com" 获取最新公开可见的发言。
关键词策略：
- `"峰哥亡命天涯 微博 股票"` — 获取股票相关内容
- `"峰哥亡命天涯 最新发言"` — 获取最新动态
- `"峰哥亡命天涯 site:weibo.com"` — 直接从微博搜索

**方案B — 历史数据库：**
如本地有保存的微博数据文件（JSON/CSV/TXT），直接读取 `references/` 或用户指定路径下的存档文件。

**方案C — 手动输入：**
用户可以直接粘贴峰哥的微博截图文字或链接。

**数据来源说明**：
- 微博数据通过 WebSearch / 公开网站获取，可能存在数小时至数天的延迟
- 不保证覆盖全部微博内容
- 不存储用户私人数据，仅分析公开可见的发言

### Step 2：观点提取

对每条微博进行NLP分析，提取：

1. **标的识别**：提取提到的个股（股票名称/代码）、板块/行业、指数
2. **观点分类**：
   - `bullish` — 看多、看好、加仓、持有、抄底、涨停
   - `bearish` — 看空、不看好、减仓、清仓、止损、跌停、**卸载、销户、退出**
   - `neutral` — 中性、观望、无明确方向
3. **行为识别**（权重更高）：
   - `action_uninstall` — 卸载交易软件
   - `action_reinstall` — 回归/重新买入
   - `action_cancel_account` — 销户
   - `action_show_profit` — 晒盈利
   - `action_show_loss` — 晒亏损
4. **强度评估**：
   - `strong` — 有明确语气/重复强调/带情绪/有行为动作
   - `moderate` — 一般性提及
   - `weak` — 顺带提及、玩笑口吻
5. **操作类型**：买入、卖出、持有、观望、仓位调整
6. **时间锚定**：是否提到具体时间点（明日、本周、月底等）

### Step 3：反向信号生成

| 原始信号 | 行为证据 | 反向信号 | 强度 |
|---------|---------|---------|:----:|
| 强烈看多 | + 晒持仓/晒盈利 | 🔴 强烈反向看空 | ⭐⭐⭐ |
| 强烈看多 | 无持仓证据 | 🔴 反向偏空 | ⭐⭐ |
| 轻微看好 | — | 🔴 轻度反向 | ⭐ |
| 强烈看空 | + 骂街/情绪化 | 🟢 强烈反向看多 | ⭐⭐⭐ |
| 看空/吐槽 | — | 🟢 反向偏多 | ⭐⭐ |
| 轻微看空 | — | 🟢 轻度反向 | ⭐ |
| **卸载软件/销户** | + 宣布退出 | 🟢 **强烈反向看多** | ⭐⭐⭐ |
| **重新安装/回归** | + 全仓买入 | 🔴 **强烈反向看空** | ⭐⭐⭐ |
| 晒亏损/割肉 | + 情绪崩溃 | 🟢 强烈反向看多 | ⭐⭐⭐ |
| 晒盈利/新高 | — | 🔴 强烈反向看空 | ⭐⭐⭐ |

### Step 4：报告生成

根据采集和分析结果，生成结构化的 Markdown 报告，保存到 `output/` 目录。

### Step 5：信号数据库持久化

每次分析结果自动存入 SQLite 数据库 `output/signal_store.db`：

**signals 表** — 存储每条分析结果（日期、原文、股票代码、板块、情绪、强度、行为信号、反向信号）
**trades 表** — 虚拟反向交易记录（做多/做空、入场价、出场价、盈亏）
**verifications 表** — 回测验证结果（信号日 vs N日后涨跌幅）

```bash
python main.py --stats   # 查看数据库统计
```

### Step 6：K线图信号标注

通过 Pandadata API 获取股票日K线，用 mplfinance 绘制蜡烛图，叠加信号标记：
- 🟢 绿色上箭头 = 反向看多信号（峰哥看空→我们做多）
- 🔴 红色下箭头 = 反向看空信号（峰哥看多→我们做空）
- 标注信号后 N 日涨跌幅

图表保存到 `output/charts/` 目录（PNG，150dpi）。

```bash
python main.py --chart 688981 2026-06-01 2026-07-21
python main.py --chart 600519 2026-06-01 2026-07-21
```

### Step 7：回测验证 & 虚拟交易系统

对每条含股票代码的信号：
1. 通过 Pandadata 获取信号日后 N 个交易日的股价
2. 按反向逻辑判断预测是否正确
3. 自动开虚拟交易（做多/做空），计算盈亏
4. 汇总胜率、平均收益、多空方向表现

```bash
python main.py --backtest    # 运行回测
python main.py --portfolio   # 查看虚拟交易盈亏
```

### Step 8：自动跟踪流水线

```bash
python main.py --track        # 完整流水线：输入→分析→存库→回测→K线图→报告
python main.py --cron         # 定时任务
python scripts/auto_track.py --file data.json  # 从文件批量处理
```

## 报告模板

```markdown
# 峰哥反向指标日报 — YYYY-MM-DD

## 📡 本期数据概况
- **数据来源**：[WebSearch / 历史存档 / 手动输入]
- **覆盖时间范围**：YYYY-MM-DD ~ YYYY-MM-DD
- **共分析 N 条微博

## 📊 信号总览

| 信号类型 | 数量 | 占比 |
|---------|:----:|:----:|
| 🔴 反向看空 | N | N% |
| 🟢 反向看多 | N | N% |
| ⚪ 无明显信号 | N | N% |

## 🔄 详细分析

### 1. YYYY-MM-DD
**原文**：> ...
**观点**：看多/看空（强度）
**行为信号**：有/无
**涉及标的**：股票/板块
**反向信号**：🟢/🔴 信号类型（强度: ⭐⭐）
**理由**：...

## ⚠️ 风险提示
本报告基于"峰哥反向指标"的社区经验逻辑生成，仅供研究参考，不构成任何投资建议。反向信号是概率参考，过去表现不代表未来结果。
```

## 输出格式

- 报告保存到 `output/峰哥反向指标_YYYYMMDD.md`
- 如有历史报告，可要求叠加分析胜率趋势
- 报告语言：中文（除非用户另有要求）

## CLI 命令参考

```bash
# 分析跟踪
python main.py --track                # 完整流水线（交互输入→分析→存库→回测→K线→报告）
python main.py --interactive          # 交互分析+存库
python main.py --file <path>          # 从JSON/TXT文件分析
python main.py --cron                 # 定时任务模式

# K线图表
python main.py --chart <code> [start] [end]  # K线图+信号标注
python main.py --chart 688981 2026-06-01 2026-07-21  # 示例：中芯国际

# 回测 & 交易
python main.py --backtest             # 运行回测验证
python main.py --portfolio            # 查看虚拟交易盈亏
python main.py --stats                # 数据库统计

# 在 Claude Code 中使用
@skill-feng-reverse 峰哥今天说了什么
@skill-feng-reverse 分析峰哥最近一周的观点
@skill-feng-reverse 峰哥最近在看什么股票
@skill-feng-reverse 更新峰哥反向指标胜率统计
```

## 自动化（定时运行）

当用户要求定时监控时，可设置 cron 定时运行：
- 频率：每日盘中/盘后
- 运行时读取最新微博，生成当日报告
- 自动累积到历史数据库，更新胜率统计

## 项目边界与风险声明

### 数据边界
- **数据来源**：微博公开数据（通过 WebSearch / 公开搜索获取），Pandadata 行情数据（可选）
- **覆盖范围**：仅限峰哥亡命天涯的公开微博发言
- **时效性**：WebSearch 存在数小时至数天延迟，不保证实时性
- **完整性**：不保证覆盖全部发言，通过多种搜索策略尽量获取

### 分析假设
- 峰哥亡命天涯作为一个整体具有反向指标属性（基于社区观察和历史案例）
- 峰哥口头表达与真实操作存在相关性
- 情绪化发言比中性发言更具信号价值
- **行为信号（卸载/销户/回归）比口头信号权重更高**

### 已知限制
1. 峰哥发言含大量反讽、夸张、玩梗，AI 分析可能误判
2. 选择性展示偏差：峰哥可能选择性晒单，不代表全部操作
3. 反向指标可能随时间衰减（如果市场共识形成后可能自我失效）
4. 样本量有限，单次信号统计显著性不足
5. 峰哥的言论内容受平台审核影响，可能无法完整获取
6. 无法区分峰哥的真实操作与直播/节目效果

### 风险边界
- 本工具**不是**投资建议，也**不是**量化交易信号
- 仅供研究与教育参考
- 不得仅依赖反向信号做出投资决策
- 过往反向正确率不代表未来表现
- 所有信号为概率参考，存在完全错误的可能
- 使用者需自行承担所有投资风险

## 资源文件

- `references/sources.md`: 数据来源和搜索策略
- `references/methodology.md`: 反向指标方法论（含行为信号理论）
- `references/cases.md`: 经典反向案例记录
- `output/signal_store.db`: SQLite 信号数据库
- `output/charts/`: K线图信号标注 PNG 文件
- `scripts/fetch_posts.py`: 微博数据采集脚本
- `scripts/analyze_sentiment.py`: 观点分析脚本（含行为信号识别）
- `scripts/signal_store.py`: 信号数据库 & 虚拟交易系统
- `scripts/plot_signals.py`: K线图信号标注（mplfinance + Pandadata）
- `scripts/backtest.py`: 回测验证引擎
- `scripts/auto_track.py`: 自动跟踪流水线
- `scripts/generate_report.py`: 报告生成脚本

## 质量标准

- 每条分析必须标注数据来源和获取时间
- 观点分类需附原文引用，避免过度解读
- 反向信号必须标注强度等级
- **行为信号与口头信号分开标注**，明确信息来源
- 胜率统计需标明统计口径和样本量
- 报告末尾必须有完整风险提示
- 不构成投资建议，不承诺盈利
