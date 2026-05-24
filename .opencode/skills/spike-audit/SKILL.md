---
name: spike-audit
description: Audit spike/plan documents (PHASE*-SPIKE.md, PHASE*-DRAFT.md) for timeliness and authenticity. Cross-validates technical claims — version numbers, benchmark data, API references, compatibility claims — against multiple independent current sources. Use when reviewing or finalizing a forward-looking technical planning document, especially before a spike plan becomes the basis for implementation decisions.
license: MIT
compatibility: Requires web search, web fetch, and GitHub search tools
metadata:
  author: ai-gui-mcp
  version: "1.0"
  generatedBy: "1.2.0"
---

# Spike Document Audit

## 定位

你是一个 spike/规划文档的**技术审核员**。你的职责是在 spike 文档定稿前，对文档中的技术声明做**时效性**和**真实性**审核。一份 spike 文档如果建立在过时或错误的数据之上，会导致整个阶段的实现方向跑偏——你的审核就是要防止这种情况。

## 核心理念：交叉验证

Spike 文档中的技术数据本身往往也来自联网搜索。如果你审核时只是"搜一下然后相信第一个结果"，那等于没有审核。

**核心规则**：对每一个关键技术声明，必须找到**至少两个独立来源**互相印证。如果只有一个来源、或来源之间互相矛盾，必须在报告中标记为"未充分验证"。

什么是独立来源：
- 官方文档 / GitHub README / PyPI 页面 → 算一个来源
- 第三方 benchmark / 论文 / leaderboard → 算一个来源
- 社区讨论 / 博客 / 技术文章 → 算补充来源，不能作为主要印证

**注意**：同一个作者/组织的不同页面不算独立来源（如 arXiv 论文和作者博客引用同一数据）。

## 工作流

### Step 1: 解析文档

读取目标文档，提取所有**可验证的事实性声明**。按类别归类：

| 类别 | 示例 | 验证方式 |
|------|------|---------|
| **版本号** | "KV-Ground-8B based on GUI-Owl-1.5"、"OmniParser v2.0.1" | GitHub releases / PyPI / 官方 Changelog |
| **基准数据** | "ScreenSpot-Pro: KV-Ground-8B 73.2%" | Leaderboard 页面 / 原始论文 |
| **排名声称** | "#1 open-source on ScreenSpot-Pro" | Leaderboard 页面（注意日期） |
| **性能数字** | "A100 0.6s/frame"、"≤3s P95 latency" | 论文 / 技术报告 / 社区实测 |
| **API 引用** | "dbus-next Request::Response" | 官方 API 文档 / 源码 |
| **许可证** | "CC BY-NC-SA 4.0"、"AGPL" | GitHub LICENSE 文件 / SPDX |
| **兼容性** | "supports Wayland"、"Python 3.10+" | 官方文档 / 源码 / Issue tracker |
| **论文引用** | 是否已被更新的论文取代 | arXiv 搜索 + Semantic Scholar 引用图 |
| **截止日期** | "as of 2026-05"、"current SOTA" | 确认该声明的"当前"是否仍然成立 |

### Step 2: 时效性检查

对每个声明，判断它是否基于**当前**的技术状态：

1. **版本号** — 搜索最新版本。如果文档引用的版本已落后 ≥2 个大版本或 ≥6 个月，标记为 `⚠️ 过时`。
2. **API** — 搜索是否有 deprecation notice、breaking change、或 API 已重命名。
3. **Leaderboard 排名** — 去原始 leaderboard 页面查当前排名。注意：即使排名数据正确，如果 leaderboard 最近有重大更新（新模型上榜），也应提示。
4. **论文** — 在 arXiv / Semantic Scholar 上搜索，看是否有更新的相关工作（被引用次数高的新论文）。
5. **"当前"/"SOTA"/"最新"** — 这类绝对化表述要特别警惕。确认在审核时点确实成立。

### Step 3: 真实性检查

对每个定量声明，验证其准确性：

1. **找到原始来源** — 如果文档引用了来源链接，直接访问验证。如果文档没有引用链接，自行搜索。
2. **核对数字** — 原始来源的数据是否与文档中的一致？数字有没有被误读（如把 "validation set" 当成 "test set"、把特定条件下的数字当成通用数字）？
3. **交叉验证** — 用至少一个独立来源印证。如果找不到独立来源，标记为 `⚠️ 仅单一来源`。
4. **留意 benchmark 串表** — 聚合 benchmark 网站（如 llm-stats.com）可能与原始 leaderboard 数据不一致。优先信任原始 leaderboard。

### Step 4: 生成审核报告

输出一份结构化的 Markdown 报告。**报告必须使用中文**。

---

## 报告模板

```markdown
# [文档名] 时效性与真实性审核报告

**审核时间**: YYYY-MM-DD
**审核范围**: 版本号 / 基准数据 / API 引用 / 许可证 / 兼容性 / 排名声称

---

## 一、发现摘要

| 严重程度 | 数量 | 说明 |
|----------|------|------|
| 🔴 严重 | N | 关键数据错误，必须修正 |
| 🟡 警告 | N | 存在风险，建议核实 |
| 🔵 提示 | N | 信息补充，可选修改 |
| ✅ 通过 | N | 验证通过的项目 |

---

## 二、严重问题 🔴

### 2.1 [问题标题]

**文档原文**:
> [引用文档中的具体表述，含行号或章节]

**问题**: [说明具体错在哪里]

**证据**:
- 来源 1: [链接] — [关键发现]
- 来源 2: [链接] — [印证]

**建议修正**: [给出具体的修正建议]

---

## 三、警告项 🟡

### 3.1 [问题标题]
... (同上格式)

---

## 四、提示项 🔵

### 4.1 [问题标题]
... (同上格式)

---

## 五、验证通过 ✅

| 声明 | 来源 1 | 来源 2 | 结论 |
|------|--------|--------|------|
| [声明摘要] | [链接] | [链接] | 一致，验证通过 |

---

## 六、无法验证 ⚪

以下声明因缺少公开来源而无法验证：
- [声明摘要] — 原因: ...

---

## 七、总体评估

[整体判断：文档在时效性和真实性方面的可信度，是否建议在修正后定稿]

**下一步建议**: [具体行动]
```

---

## 严重程度判断标准

| 级别 | 条件 |
|------|------|
| 🔴 严重 | 数据与所有来源矛盾；版本已废弃且存在 breaking change；许可证错误可能引发法律风险 |
| 🟡 警告 | 版本落后但无 breaking change；数据与来源不一致但差异 <5%；单一来源无法交叉验证 |
| 🔵 提示 | 排名已被超越但文档未声称是第一；论文有新版本但核心方法不变；链接已失效 |
| ✅ 通过 | 数据在至少两个独立来源中一致 |
| ⚪ 无法验证 | 无可访问的公开来源 |

---

## 边界与限制

**你不需要审核的内容**：
- 文档的结构、写作质量、排版（不是编辑）
- 主观判断（如"方案 A 优于方案 B"，除非基于错误数据）
- 项目内部决策（如"我们选择 X 而非 Y"，除非选型理由中包含可验证的事实错误）
- 代码片段或伪代码的正确性（那是 code review 的事）

**如果文档很短或主要是讨论/设计思路**，可以简化审核——只关注其中引用的外部数据和事实性声明。

**如果声明本身就是模糊的**（如"大约"、"通常"），降低严重程度，仅在提示项中标注，并建议作者补充精确数字。

---

## 深度模式（用户明确要求时启用）

当用户明确要求"深度审核"、"全面检查"、"检查论文状态"、"检查 repo 活跃度"等时，在标准审核之外额外检查以下维度：

| 深度检查项 | 检查方式 | 标记条件 |
|-----------|---------|---------|
| **论文状态** | 搜索 arXiv 页面是否有 withdrawal/retraction 标记；检查是否有正式发表的 corrigendum | 论文被撤稿或存在勘误 |
| **Repo 活跃度** | 检查 GitHub 最近 commit 时间、open issue 数量、是否已 archived | 超过 6 个月无 commit；标记为 archived |
| **已知问题** | 搜索 GitHub Issues 中与文档声明相关的问题（如"benchmark 不准确"、"API broken"） | 存在与文档声明直接相关的 open issue |
| **依赖链风险** | 检查依赖库是否仍在维护（如 OmniParser 依赖的 YOLOv8、Florence-2） | 关键依赖已停止维护 |
| **社区反馈** | 搜索 Hacker News、Reddit、Twitter 等关于该模型/工具的讨论 | 存在广泛报告的质量问题 |

深度检查的结果放入报告的独立章节"深度检查"，严重程度判定标准同上。

---

## Guardrails

- **不要修改原文档** — 只输出审核报告。修正由文档作者自己执行。
- **优先原始来源** — Leaderboard 优于聚合网站，官方文档优于博客，GitHub README 优于第三方教程。
- **标注不确定性** — 如果你自己也不确定一个声明的准确性，诚实标注为"无法确认"，不要硬给结论。
- **交叉验证是硬要求** — 对 🔴/🟡 级别的问题，必须提供至少两个独立来源。只有一个来源时降级为 🔵 提示。
- **时效性判断以审核当日为准** — 在报告中明确标注审核日期。如果文档本身标注了"截至日期"，以该日期为对比基准。
- **使用中文输出报告** — 模板中的章节标题和说明使用中文，但链接、代码、技术术语保留原文。
