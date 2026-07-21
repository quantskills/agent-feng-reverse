# 峰哥反向指标 · skill-feng-reverse

追踪微博「**峰哥亡命天涯**」的公开发言，提取其股票/市场观点，基于反向指标逻辑生成信号和跟踪报告。

峰哥是A股社区公认的反向指标——其公开观点具有稳定的反向参考价值。

## 项目状态

> 社区项目 · 研究实验性 · 未认证

## 核心理念

| 峰哥表现 | 反向信号 |
|---------|---------|
| 强烈看多某股/板块 | 🔴 谨慎/看空 |
| 强烈看空某股/板块 | 🟢 关注/看多 |
| 晒持仓收益/浮盈 | 🔴 可能见顶 |
| 晒亏损/割肉 | 🟢 可能见底 |
| **卸载交易软件/销户** | 🟢 **强烈看多（底部特征）** |
| **重新下载/全仓回归** | 🔴 **强烈看空（顶部特征）** |

## 项目结构

```
├── SKILL.md                         ← Skill 定义与完整工作流
├── main.py                          ← Python 入口
├── agents/                          ← Agent 加载器（Claude Code / Cursor / OpenAI）
│   ├── portable-loader.md
│   ├── cursor-rule.mdc
│   └── openai.yaml
├── scripts/                         ← Python 分析工具链
│   ├── fetch_posts.py               ← 微博数据采集
│   ├── analyze_sentiment.py         ← 观点分析与反向信号生成
│   └── generate_report.py           ← Markdown 报告生成
├── references/                      ← 方法论文档
│   ├── sources.md                   ← 数据源与搜索策略
│   ├── methodology.md               ← 反向指标方法论（含行为信号理论）
│   └── cases.md                     ← 经典案例库
└── output/                          ← 报告输出
```

## 使用方式

### 在 Claude Code 中使用

```
@skill-feng-reverse 峰哥今天说了什么
@skill-feng-reverse 分析峰哥最近一周的观点
```

### 命令行使用

```bash
# 交互模式，手动粘贴微博内容
python main.py --mode interactive

# 快速分析单条文本
python scripts/analyze_sentiment.py "今天满仓抄底某股票！"
```

## 方法论亮点：行为信号

本 skill 创新性地引入**行为信号分析**框架，将峰哥的实际行为（卸载软件、销户、回归、晒单等）作为比口头表达更高权重的信号来源。

典型行为循环：
```
卸载/销户（底部）→ 沉默 → 偷偷装回软件 → 小仓位试水 →
全仓买入（顶部）→ 被套 → 死扛 → 情绪崩溃 → 再次卸载/销户（底部）
```

详见 `references/methodology.md`。

## 数据来源

- 微博公开数据（通过 WebSearch / 公开搜索获取）
- Pandadata 行情数据（可选，用于验证观点准确性）

## 许可证

GNU General Public License v3.0

## 维护者

- **xixihaha-dzh** — 创建者与维护者

## 免责声明

本工具仅供研究与教育参考，不构成任何投资建议。反向信号是概率参考，过去表现不代表未来结果。所有分析结果仅供参考，使用者需自行承担投资风险。
