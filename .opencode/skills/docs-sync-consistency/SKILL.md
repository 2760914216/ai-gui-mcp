---
name: docs-sync-consistency
description: Use when maintaining this project's documentation — determining which docs are editable, which are read-only, and which should be ignored, then checking consistency across in-scope docs and archived OpenSpec records.
---

# Docs Sync Consistency

**核心原则：** 从 AGENTS.md 收集全部文档 → 归类到三类桶 → 读 editable + read-only → 仅编辑 editable → 对 read-only 仅报告 → 忽略 ignore。

## P 工作流筛选规则

### 第一步：从 AGENTS.md 获取全部文档

读取 `AGENTS.md`，收集其中引用的**所有**项目文档路径（仅路径）。此时不做任何过滤——无论 AGENTS.md 中是否标注了「不可更新」「仅参考」「草稿」等标记，一律先纳入清单，再进入分类步骤。

### 第二步：三类文档分类

| 分类 | 读 | 写 | 判定规则 |
|------|:--:|:--:|----------|
| **可更新 (editable)** | ✅ | ✅ | 默认分类：无特殊说明即为此类 |
| **不可更新 (read-only)** | ✅ | ❌ | 见下方规则 |
| **忽略 (ignore)** | ❌ | ❌ | 见下方规则 |

**可更新 (editable)** — 默认分类。任何未特别标注的文档都属于此类，包括 `AGENTS.md` 本身。

**不可更新 (read-only)** — 满足以下**任一**条件：
- 路径在 `openspec/` 下（含 `openspec/config.yaml`、`openspec/changes/`、`openspec/specs/` 等所有子路径）
- `AGENTS.md` 中该文档的引用附带了不可更新/只读标记（如「不可更新」「仅参考」「只读」「不用更新」）
- 用户在对话中明确指定为不可更新/只读

**忽略 (ignore)** — 满足以下**任一**条件：
- 路径在 `ignore_draft/` 下
- 用户在对话中明确指定为忽略

### 第三步：执行工作流

1. **收集** — 从 `AGENTS.md` 获取全部文档路径清单
2. **分类** — 按上述规则将每个文件归入三类之一
3. **读取** — 读取 editable 和 read-only 文件（不读 ignore 文件）。对 read-only 文件中的过时声明或冲突，可在报告中引用，但不得编辑
4. **检查 drift**：
   - 失效链接或已移动的文件
   - editable 文档之间的事实不一致
   - editable 文档与归档 OpenSpec 决策（`openspec/changes/archive/**`）的偏离
   - AGENTS.md 条目过于冗长、过时或不再准确的内容
   - read-only 文件中的冲突（报告但不编辑）
5. **报告** — 使用下方报告格式产出提案
6. **确认** — 等待用户批准，不自行编辑
7. **执行** — 仅编辑 editable 且被批准的文件
8. **完成报告** — 列出实际变更及原因，提及未解决的 read-only 问题

## AGENTS.md 维护标准

- 保持简洁，避免冗长重复
- 移除过时或误导性条目
- 优先使用指针引用而非内嵌大段细节
- 修复失效路径、过时状态标记和无效规则

## docs/ 维护标准（仅适用于 editable 文件）

- 保持各文档之间的事实一致性
- 与归档 OpenSpec 决策对齐（`openspec/specs/**`、`openspec/changes/archive/**`）
- 以当前项目决策为准，而非旧草稿
- 对于 read-only 文件中的冲突，报告但不编辑
- 不将活跃 `openspec/changes/**` 中的内容视为权威来源

## 报告格式

在编辑前先产出以下格式的简短报告：

```markdown
## 文档维护提案

### 可更新 (editable)
- <路径> — AGENTS.md 引用，无排除标记
- <路径> — 用户未排除

### 只读 (read-only)
- <路径> — openspec/ 下，不可编辑
- <路径> — AGENTS.md 标注不可更新
- <路径> — 用户指定不可更新

### 忽略 (ignore)
- <路径> — ignore_draft/ 下
- <路径> — 用户指定忽略

### 建议变更
- <文件>: <修改内容> — <原因>

### 只读文件中的问题（仅报告，不编辑）
- <文件>: <问题> — 已排除编辑
```

**必须在用户确认后方可编辑。**

执行后产出完成报告，列出实际变更内容、原因，并提及未解决的只读文件问题。

## 快速参考

| 情形 | 行动 |
|------|------|
| AGENTS.md 引用某文档，无特殊标记 | 归入 **editable** |
| 路径在 `openspec/` 下 | 归入 **read-only** |
| AGENTS.md 中标注「不可更新」「仅参考」「只读」「不用更新」 | 归入 **read-only** |
| 用户在对话中说"不要改 X.md" | 归入 **read-only** |
| 用户在对话中说"忽略 Y.md" | 归入 **ignore** |
| 路径在 `ignore_draft/` 下 | 归入 **ignore** |
| 归档 OpenSpec 与 editable 文档冲突 | 提议编辑 editable 文档 |
| 归档 OpenSpec 与 read-only 文档冲突 | 报告问题，不编辑 |
| 活跃 OpenSpec change 与文档冲突 | 暂不报告；活跃变更非权威来源 |
| 所有文档均为 read-only 或 ignore | 报告本轮无可编辑文档 |

## 示例

**场景**：AGENTS.md 中 `项目规约` 表引用了 5 个 `docs/` 文件和 1 个 `openspec/config.yaml`。假设 `docs/FUTURE-REFERENCE.md` 被标注为「仅作信息参考，不可更新」。

**分类结果**：

| 文件 | 分类 | 原因 |
|------|------|------|
| `AGENTS.md` | editable | 默认，可编辑 |
| `docs/ROADMAP.md` | editable | 无标记 |
| `docs/PHASE0-SPIKE.md` | editable | 无标记 |
| `docs/PHASE1-IMPLEMENTATION.md` | editable | 无标记 |
| `docs/SPIKE-RESULTS.md` | editable | 无标记 |
| `docs/FUTURE-REFERENCE.md` | read-only | AGENTS.md 标注不可更新 |
| `openspec/config.yaml` | read-only | openspec/ 下 |
| `ignore_draft/overview.md` | ignore | ignore_draft/ 下 |

对 `docs/FUTURE-REFERENCE.md` 中的过时声明，在「只读文件中的问题」中提及但不编辑。

## 常见错误

- 在提案报告前直接编辑
- 编辑 read-only 分类的文件
- 编辑 `openspec/` 来"使文档对齐"
- 以活跃 OpenSpec change 为权威依据
- 让 `AGENTS.md` 积累冗长重复的内容
- 静默忽略 read-only 文件中的冲突而不报告
- 在收集阶段就跳过 AGENTS.md 中标注了排除标记的文件（应先纳入清单再分类）

## 红旗信号

- 「我可以顺手把链接的文档也改了。」
- 「用户要求一致性，我把所有东西都更新了。」
- 「报告可以在编辑之后补。」
- 「活跃 OpenSpec 的工作和归档的差不多。」

如果出现以上任何念头，停下来，回到三类分类规则重新判断。
