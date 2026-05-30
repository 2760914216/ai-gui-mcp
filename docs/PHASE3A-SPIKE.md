# P3A Spike — 视觉模型选型验证

> 目标：在 COSMIC 环境下实测候选视觉 GUI parser 模型，确定 P3A-4 的 `VisionProvider` 具体实现引擎。
>
> **最后更新**: 2026-05-25 | **数据截止**: 2026-05-25
>
> ⚠️ 所有基准数字均标注来源链接和时间。选型时请以当时 leaderboard 最新数据为准。

---

## 目录

1. [背景与问题定义](#1-背景与问题定义)
2. [方案分类体系](#2-方案分类体系)
3. [Category 1: 专用 GUI Grounding 模型（纯定位输出）](#3-category-1-专用-gui-grounding-模型纯定位输出)
4. [Category 2: 端到端 GUI Agent VLM（动作输出）](#4-category-2-端到端-gui-agent-vlm动作输出)
5. [Category 3: 屏幕解析工具（检测+描述）](#5-category-3-屏幕解析工具检测描述)
6. [Category 4: 通用 VLM（指令跟随）](#6-category-4-通用-vlm指令跟随)
7. [Category 5: 组合/管道方案（多模型协同）](#7-category-5-组合管道方案多模型协同)
8. [Category 6: 推理时扩展技术（不换模型，换策略）](#8-category-6-推理时扩展技术不换模型换策略)
9. [基准测试全景](#9-基准测试全景)
10. [决策框架](#10-决策框架)
11. [验收截图集](#11-验收截图集)
12. [Go/No-Go 标准](#12-gono-go-标准)
13. [实施步骤](#13-实施步骤)
14. [来源索引](#14-来源索引)

---

## 1. 背景与问题定义

### 1.1 P3A 的角色

P3A 定义了 `VisionProvider` 抽象接口：

```python
def parse(image: RawImage, a11y_hints: A11yTree | None) -> AnalysisResult
```

输入：RGB 截图（PNG bytes）+ 可选无障碍树提示
输出：`AnalysisResult` — 包含 `elements[]`（可交互元素 + 结构元素）、`layout_summary`（屏幕类型、主区域）、`overall_quality`

COSMIC 环境下 AT-SPI2 覆盖率实测为 **≈5%**，因此视觉解析路径是感知主力。

### 1.1.1 设计方向的验证

P3A 选择输出结构化 bbox（而非纯文本描述或直接动作）是经过理论验证的正确方向：

- **「Thinking with Visual Primitives」** (DeepSeek, 2026-04)：证明视觉基元（bbox/点）作为推理链中的「最小思维单元」能消除自然语言的 Reference Gap，是精确空间推理的前提。该模型在空间推理基准上达到 GPT-5.4 / Claude-4.6 同等水平。
- **「Action with Visual Primitives」** (AVP, 2025)：证明 VLM 通过 visual primitives 与执行模块解耦的架构模式（VLM 推理 → bbox 输出 → 执行模块消费），在机器人领域带来 27.61% 成功率提升。

这两种模式与 P3A 的 VisionProvider（输出 bbox）→ 上层 Agent（消费 bbox）架构完全吻合。

### 1.2 选型关键约束

| 约束 | 要求 |
|------|------|
| 接口契约 | 必须满足 `parse(image, a11y_hints) -> AnalysisResult` |
| 输出粒度 | element bbox + type + text/description + confidence |
| 延迟上限 | 本地 ≤ 3s P95，云端 ≤ 10s P95 |
| 隐私 | 优先本地模型；必须保留云端降级路径 |
| 运行环境 | Wayland/COSMIC，无 X11 依赖 |
| 许可 | 宽松许可优先；GPL/AGPL 需标记风险 |

### 1.3 旧版 Spike 的问题

前一版（v1）只有 5 个候选模型（OmniParser v2、UI-TARS-7B/72B、Qwen-VL-Max、Claude 3.5 Sonnet），存在以下缺陷：

- **时效性差**：引用数据停留在 2024 年底，未覆盖 2025-2026 新模型
- **分类粗糙**：未区分"纯定位模型"和"端到端 Agent 模型"
- **遗漏关键模型**：KV-Ground、ShowUI、UGround、Ferret-UI Lite、GUI-Actor、V2P 等均未提及
- **缺少管道方案**：未覆盖 OmniParser+VLM 组合、一致性路由等多模型协同
- **无推理时扩展**：未涉及 Zoom-in、RegionFocus、Mark-Grid Scaffold 等技术
- **基准数据陈旧**：ScreenSpot-Pro 旧数据串表，无来源验证

本版全面重写。

---

## 2. 方案分类体系

当前 GUI 视觉理解的技术路线可归为 **六大类**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GUI 视觉理解方案分类                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────┐  ┌──────────────────────┐                │
│  │  1. 专用 Grounding   │  │  2. 端到端 Agent VLM │                │
│  │     纯定位输出        │  │     动作输出          │                │
│  │  KV-Ground, UGround, │  │  UI-TARS, ShowUI,    │                │
│  │  GUI-Actor, OS-Atlas │  │  CogAgent             │                │
│  └──────────┬───────────┘  └──────────┬───────────┘                │
│             │                         │                             │
│  ┌──────────┴───────────┐  ┌──────────┴───────────┐                │
│  │  3. 屏幕解析工具      │  │  4. 通用 VLM         │                │
│  │     检测+描述         │  │     指令跟随          │                │
│  │  OmniParser,         │  │  Qwen-VL, GPT-4o,    │                │
│  │  ScreenAI             │  │  Claude, Gemini       │                │
│  └──────────┬───────────┘  └──────────┬───────────┘                │
│             │                         │                             │
│  ┌──────────┴─────────────────────────┴───────────┐                │
│  │  5. 组合/管道方案（多模型协同）                   │                │
│  │  OmniParser+VLM, KV-Ground+路由, MEGA-GUI        │                │
│  └──────────┬──────────────────────────────────────┘                │
│             │                                                       │
│  ┌──────────┴──────────────────────────────────────┐                │
│  │  6. 推理时扩展（不换模型，换策略）                 │                │
│  │  Zoom-In, RegionFocus, Mark-Grid, Chain-of-Ground│                │
│  └─────────────────────────────────────────────────┘                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**对 P3A 的意义**：我们需要的是 Category 1 或 3 的能力（输出结构化元素列表），但 Category 5/6 的技术可以叠加在任意基座模型上提升精度。

---

## 3. Category 1: 专用 GUI Grounding 模型（纯定位输出）

> 输入：截图 + 自然语言描述 → 输出：bbox 坐标
> P3A 适配：天然匹配 `parse()` 的输出需求，是首选方案

### 3.1 KV-Ground (Kingsware × Vocaela AI)

| 属性 | 值 |
|------|-----|
| 版本 | KV-Ground-8B / KV-Ground-4B（两版基座） |
| 基座模型 | GUI-Owl-1.5-8B-Instruct / GUI-Owl-1.5-4B-Instruct / Qwen3-VL-4B-Instruct |
| 训练方式 | SFT → GRPO 强化学习；MLLM-as-judge 数据清洗 |
| 许可 | CC BY-NC-SA 4.0（模型），MIT（代码） |
| 定位 | **纯 grounding 模型**，不执行动作 |

**基准分数（ScreenSpot-Pro）**：

| 模型变体 | ScreenSpot-Pro | ScreenSpot-v2 | OSWorld-G |
|----------|---------------|---------------|-----------|
| KV-Ground-8B | **73.2%** | 94.6% | 68.1% |
| KV-Ground-4B (GUI-Owl) | 67.0% | 94.1% | 64.2% |
| KV-Ground-4B (Qwen3-VL) | 63.2% | 94.6% | 64.0% |

> 来源: [GitHub vocaela/kv-ground](https://github.com/vocaela/kv-ground) — 2026-05 最新

**Zoom-In 叠加后**：

| 模型 + Zoom-In | ScreenSpot-Pro |
|----------------|---------------|
| KV-Ground-8B + Zoom-In | **80.5%**（全系统 No.1）|
| KV-Ground-4B + Zoom-In | 76.4% |

**输入/输出**：

- 输入：高分辨率截图 + 自然语言指令（如 "click the Save button"）
- 输出：归一化坐标 [0-1000] 格式的 bbox 坐标
- 不做推理，不做动作规划——只输出坐标

**优势**：
- ✅ ScreenSpot-Pro 开源模型 No.1（73.2% pure，80.5% with Zoom-In）
- ✅ 4B/8B 紧凑参数，适合本地部署
- ✅ 专为高分辨率专业桌面优化（RPA 场景）
- ✅ 四轮数据清洗（MLLM-as-judge），数据质量高

**劣势**：
- ❌ 仅输出坐标，无元素类型/文本/描述（需另外提取）
- ❌ CC BY-NC-SA 许可限制商用
- ❌ 不输出 layout_summary / screen_kind（需上层补充）
- ❌ 生态较小（社区贡献不如 OmniParser）

**P3A 适配评估**：
- bbox 输出 ✅ → 可直接映射到 `ParsedElement.bbox`
- 缺少 type/text/confidence — 需要额外 OCR + 分类层
- 需要 wrapper 将 grounding 结果转换为 AnalysisResult

**链接**：
- GitHub: https://github.com/vocaela/kv-ground
- HuggingFace: https://huggingface.co/collections/vocaela/kv-ground
- Leaderboard: https://gui-agent.github.io/grounding-leaderboard/

---

### 3.2 UGround (OSU × Orby AI)

| 属性 | 值 |
|------|-----|
| 版本 | UGround-V1（2B/7B/72B） |
| 基座模型 | Qwen2-VL |
| 训练数据 | 10M GUI 元素 + 1.3M 截图（最大 GUI grounding 数据集） |
| 发表 | ICLR 2025 Oral（1.8% 录取率） |
| 许可 | 开源 |

**基准分数**：

| 模型 | ScreenSpot | ScreenSpot-Pro | AndroidWorld |
|------|-----------|----------------|--------------|
| UGround-V1-2B | 77.7% | — | — |
| UGround-V1-7B | 86.3% | 31.1% | 44% |
| UGround-V1-72B | — | 34.5% | — |

> 来源: [arXiv 2410.05243](https://arxiv.org/abs/2410.05243), [GitHub OSU-NLP-Group/UGround](https://github.com/OSU-NLP-Group/UGround)

**输入/输出**：

- 输入：截图 + 自然语言引用表达式
- 输出：bbox 坐标
- 设计为 SeeAct-V 框架的定位模块

**优势**：
- ✅ ICLR 2025 Oral，学术质量高
- ✅ 最大规模 GUI grounding 训练数据
- ✅ 3 个参数规模可选，覆盖边缘到云端
- ✅ 基于 Web 的合成数据方法，可持续扩展

**劣势**：
- ❌ ScreenSpot-Pro 表现显著弱于 KV-Ground（31.1% vs 73.2%）
- ❌ 不输出结构化元素详情
- ❌ 需要配合上层规划模型使用

---

### 3.3 GUI-Actor (Microsoft)

| 属性 | 值 |
|------|-----|
| 基座模型 | Qwen2.5-VL 系列 |
| 训练方式 | 仅微调动作头（~100M 参数），基础 VLM 冻结 |
| 创新点 | **坐标无关 grounding**——注意力机制驱动，无需输出坐标 |

**基准分数（ScreenSpot-Pro）**：

| 模型 | ScreenSpot-Pro |
|------|---------------|
| GUI-Actor-7B (Qwen2.5-VL) | 44.6% |
| GUI-Actor-3B (Qwen2.5-VL) | 42.2% |
| UI-TARS-72B（对比基线） | 38.1% |

> 来源: [arXiv 2506.03143](https://arxiv.org/abs/2506.03143), [Microsoft Research](https://microsoft.github.io/gui-actor-coordinate-free-visual-grounding-for-gui-agents)

**输入/输出**：

- 输入：截图 + 指令
- 输出：动作（click/type）+ 通过注意力头隐式定位
- 不显式输出 bbox——验证器在候选区域中选择最优

**优势**：
- ✅ 仅微调轻量动作头（~100M），训练成本极低
- ✅ 7B 规模超越 72B 的 UI-TARS
- ✅ 多候选区域 + 验证器，鲁棒性好

**劣势**：
- ❌ 不显式输出 bbox 坐标（注意力隐式定位）
- ❌ 适配 P3A 的 `ParsedElement.bbox` 输出需要额外解码步骤
- ❌ 目前仅论文阶段，工程化成熟度待验证

---

### 3.4 V2P (Valley-to-Peak Training)

| 模型 | ScreenSpot-Pro |
|------|---------------|
| V2P-7B | **50.54%** |
| SE-GUI-7B（对比） | 47.3% |
| UI-TARS-72B（对比） | 38.1% |

> 来源: 论文引用，2025 年发表。通过抑制注意力损失和 Fitts-Gaussian 标记损失实现精确注意力对齐

**关键创新**：通过训练目标改进（而非扩大模型），在 7B 规模超越 72B 模型。对数据有限场景特别有效。

---

### 3.5 OS-Atlas (OS-Copilot)

| 属性 | 值 |
|------|-----|
| 基座模型 | InternVL2-4B / Qwen2-VL-7B |
| 训练数据 | 2.3M+ 截图 + 13M+ GUI 元素 |
| 特点 | 跨 5 平台（Win/Mac/Linux/Android/Web）统一 |

**基准分数**：

| 模型 | ScreenSpot-Pro | ScreenSpot |
|------|---------------|-----------|
| OS-Atlas-7B | 18.9% | — |
| OS-Atlas-4B | — | — |

> 来源: [arXiv 2410.23218](https://arxiv.org/abs/2410.23218)

**注意**：ScreenSpot-Pro 数据偏低，但其跨平台数据合成工具包很有价值。

---

### 3.6 ShowUI (NUS Show Lab × Microsoft)

| 模型 | ScreenSpot (Zero-shot) |
|------|----------------------|
| ShowUI-4.2B | 75.1% |

> CVPR 2025，首个从零训练的端到端 GUI VLA。基于 Phi-3.5-vision-instruct。
> 来源: [arXiv 2411.17465](https://arxiv.org/abs/2411.17465), [GitHub showlab/ShowUI](https://github.com/showlab/ShowUI)

**边界说明**：ShowUI 输出动作（非纯 bbox），更接近 Category 2，但因其定位能力值得关注。

---

### 3.7 专用 Grounding 模型对比总览

| 模型 | ScreenSpot-Pro | 参数 | 训练数据规模 | 许可 | 输出格式 | P3A 适配 | 推荐优先级 |
|------|---------------|------|-------------|------|---------|---------|-----------|
| **KV-Ground-8B** | **73.2%** | 8B | — | CC BY-NC-SA | 坐标 | 需 wrapper | ⭐⭐⭐⭐⭐ |
| KV-Ground-4B | 67.0% | 4B | — | CC BY-NC-SA | 坐标 | 需 wrapper | ⭐⭐⭐⭐ |
| V2P-7B | 50.5% | 7B | — | — | 坐标 | 需 wrapper | ⭐⭐⭐⭐ |
| GUI-Actor-7B | 44.6% | 7B | — | — | 隐式注意力 | 复杂 | ⭐⭐⭐ |
| UGround-V1-7B | 31.1% | 7B | 10M 元素 | 开源 | 坐标 | 需 wrapper | ⭐⭐⭐ |
| UGround-V1-72B | 34.5% | 72B | 同上 | 开源 | 坐标 | 需 wrapper | ⭐⭐（重） |
| OS-Atlas-7B | 18.9% | 7B | 13M 元素 | 开源 | 坐标 | 需 wrapper | ⭐⭐ |

**关键发现**：KV-Ground-8B 在专用 grounding 模型中大幅领先。4B 版本以 ⅛ 参数达到第二梯队性能，性价比突出。

---

## 4. Category 2: 端到端 GUI Agent VLM（动作输出）

> 输入：截图 + 任务指令 → 输出：动作序列（click/type/scroll + 坐标）
> P3A 适配：过重，但可作为整体 agent 方案而非 parser

### 4.1 UI-TARS (ByteDance Seed)

| 版本 | 日期 | 基座 | 关键特性 |
|------|------|------|---------|
| UI-TARS v1 | 2025-01 | Qwen2.5-VL | 2B/7B/72B 三规模 |
| UI-TARS-1.5 | 2025-04 | Qwen2.5-VL | 强化学习推理，ScreenSpot-Pro 61.6% |
| UI-TARS-2 | 2025-09 | — | System-2 推理，OSWorld 47.5% |

**基准分数（精选）**：

| 基准 | UI-TARS-1.5 (72B) | UI-TARS-2 | OpenAI CUA | Claude 3.7 |
|------|-------------------|-----------|------------|------------|
| ScreenSpot-Pro | **61.6%** | — | 23.4% | 27.7% |
| ScreenSpot-v2 | 94.2% | — | 87.9% | 87.6% |
| OSWorld | 42.5% | **47.5%** | 36.4% | 28.0% |
| AndroidWorld | 64.2% | **73.3%** | — | — |
| Online-Mind2Web | 75.8% | **88.2%** | 71.0% | 62.9% |

> 来源: [GitHub bytedance/UI-TARS](https://github.com/bytedance/UI-TARS), [arXiv 2501.12326](https://arxiv.org/abs/2501.12326), [arXiv 2509.02544](https://arxiv.org/abs/2509.02544)

**输入/输出**：

- 输入：截图 base64 + 自然语言任务指令
- 输出：`Thought: ... Action: click(start_box='(x,y)')` 格式
- 统一动作空间：click, dbl_click, right_click, drag, type, scroll, hotkey, wait, finished

**优势**：
- ✅ 端到端能力最强（规划 + 定位 + 动作）
- ✅ ScreenSpot-Pro 专用模型中 Top 3
- ✅ 多版本可选（7B 可本地部署）
- ✅ 开源 + 活跃维护

**劣势**：
- ❌ 输出完整动作序列，不是结构化元素列表
- ❌ 提取 bbox 需要解析 action 字符串
- ❌ 7B 版本 VRAM 需求约 14GB（FP16）
- ❌ 过重——P3A 只需要 parser，不需要 agent

**P3A 适配**：
- 可以作为完整的 agent 方案，但对 parser 角色来说 overkill
- 如果要提取结构化元素列表，需要额外 wrapper 解析 action 输出

**链接**：
- GitHub: https://github.com/bytedance/UI-TARS
- HuggingFace: https://huggingface.co/ByteDance-Seed/UI-TARS-1.5-7B
- API: https://openrouter.ai/bytedance/ui-tars-1.5-7b ($0.10/$0.20 per 1M tokens)

---

### 4.2 CogAgent (清华 × 智谱 AI)

| 模型 | 规模 | 特点 |
|------|------|------|
| CogAgent-18B | 18B | 11B 视觉 + 7B 语言 |
| CogAgent-9B | 9B | 2024-12 最新版 |

支持 1120×1120 高分辨率输入，双语（中英文）GUI 操作。

> 来源: [GitHub THUDM/CogVLM](https://github.com/THUDM/CogVLM), [arXiv 2312.08914](https://arxiv.org/abs/2312.08914)

**P3A 适配**：同理，输出动作而非结构化元素，并非 parser 最优选。

---

### 4.3 Ferret-UI Lite (Apple, 2026-02)

| 模型 | 参数 | 特点 |
|------|------|------|
| Ferret-UI Lite | 3B | 移动端+桌面端紧凑模型 |

91% 准确率（UI 元素识别），3B 参数可部署在移动设备。

> 来源: Apple Machine Learning Research, 2026-02

**P3A 适配**：参数极小，但主要面向移动端（iOS/Android），桌面端 COSMIC 适配待验证。

---

### 4.4 端到端 Agent 模型对比

| 模型 | 最强基准 | 规模 | 部署难度 | P3A Parser 适合度 |
|------|---------|------|---------|-------------------|
| UI-TARS-1.5-7B | ScreenSpot-Pro 49.6% | 7B | 中 | ⭐⭐ |
| UI-TARS-2 | OSWorld 47.5% | — | 高 | ⭐⭐ |
| CogAgent-9B | Mind2Web | 9B | 中 | ⭐⭐ |
| ShowUI-4.2B | ScreenSpot 75.1% | 4.2B | 低 | ⭐⭐ |
| Ferret-UI Lite-3B | 元素识别 91% | 3B | 极低 | ⭐⭐ |

**结论**：端到端 Agent 模型能力强但输出不匹配 P3A parser 需求。若未来 P3B 需要 agent 能力，UI-TARS 是首选。

---

## 5. Category 3: 屏幕解析工具（检测+描述）

> 输入：截图 → 输出：结构化元素列表（bbox + 语义描述）
> P3A 适配：最贴合 `AnalysisResult` 的需求

### 5.1 OmniParser v2 (Microsoft)

| 属性 | 值 |
|------|-----|
| 版本 | v2.0.1 (2025-09-12) |
| 架构 | YOLOv8（检测）+ Florence-2（描述） |
| 许可 | CC-BY-4.0（代码），AGPL（检测模型），MIT（描述模型） |

**基准分数**：

| 配置 | ScreenSpot-Pro |
|------|---------------|
| OmniParser v2 + GPT-4o | 39.6% |
| GPT-4o 基线 | 0.8% |

> 来源: [Microsoft Research - OmniParser V2](https://www.microsoft.com/en-us/research/articles/omniparser-v2-turning-any-llm-into-a-computer-use-agent/), [HuggingFace microsoft/OmniParser-v2.0](https://huggingface.co/microsoft/OmniParser-v2.0)

**推理延迟**：

| GPU | 延迟 |
|-----|------|
| NVIDIA A100 | 0.6s/帧 |
| NVIDIA RTX 4090 | 0.8s/帧 |
| NVIDIA T4 (Replicate) | ~5s |

**输入/输出**：

- 输入：UI 截图 (PNG/JPG)
- 输出：**结构化元素列表** — 每个元素含 bbox、功能描述、交互性预测、唯一 ID
- 管道输出可直接作为 `ParsedElement[]`

**核心工作流**：
1. YOLOv8 检测可交互区域 → bbox
2. Florence-2 为每个区域生成功能描述
3. OCR 提取文本
4. 合并去重（重叠率 90% 阈值）
5. 输出结构化 JSON → 送入下游 VLM 推理

**优势**：
- ✅ **唯一输出结构化元素列表的工具**——天然匹配 P3A
- ✅ 与模型解耦，可接入任意 VLM 做后续推理
- ✅ 微软维护，24.8k GitHub Stars
- ✅ OmniTool 提供 Docker 化 Windows 测试环境
- ✅ v2 比 v1 延迟降低 60%

**劣势**：
- ❌ 检测模型 AGPL 许可（商业部署风险）
- ❌ ScreenSpot-Pro standalone 不高（39.6%），依赖下游 VLM
- ❌ 两阶段管道增加整体延迟
- ❌ 需要 GPU（RTX 4090 级别）

**P3A 适配评估**：
- ✅✅✅ 输出天然匹配：bbox + 描述 + 交互性
- ⚠️ 需将 YOLOv8+Florence-2 管道包装为 VisionProvider
- 可同时作为 grounding 模块 + 元素描述模块

**链接**：
- GitHub: https://github.com/microsoft/OmniParser
- HuggingFace: https://huggingface.co/microsoft/OmniParser-v2.0
- 论文: https://arxiv.org/abs/2408.00203

---

### 5.2 ScreenAI (Google DeepMind)

| 模型 | 参数 | 特点 |
|------|------|------|
| ScreenAI | 5B | PaLI 架构 + pix2struct patching |

IJCAI 2024。专注 UI 和信息图表理解，但版本较老。

> 来源: [Google Research — ScreenAI](https://arxiv.org/abs/2402.04615)

**P3A 适配**：版本较老，生态不如 OmniParser。

---

### 5.3 屏幕解析工具对比

| 工具 | 输出格式 | 许可风险 | 性能 (SS-Pro) | 生态 | P3A 推荐 |
|------|---------|---------|--------------|------|---------|
| **OmniParser v2** | bbox + 描述 + ID | AGPL（模型） | 39.6% (+VLM) | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| ScreenAI 5B | — | — | — | ⭐⭐ | ⭐⭐ |

---

## 6. Category 4: 通用 VLM（指令跟随）

> 输入：截图 + prompt → 输出：文本描述（可能含坐标）
> P3A 适配：需要大量 prompt 工程，可靠性不如专用模型

### 6.1 Qwen-VL 系列 (Alibaba)

| 模型 | ScreenSpot | ScreenSpot-Pro | 参数 |
|------|-----------|----------------|------|
| **Qwen3-VL-32B Instruct** | **95.8%** (No.1) | 54.6% | 33B |
| Qwen3-VL-8B Instruct | 94.4% | — | 9B |
| Qwen3-VL-4B Instruct | 94.0% | — | 4B |
| Qwen2.5-VL-72B Instruct | 87.1% | 43.6% | 72B |
| Qwen2.5-VL-7B Instruct | 84.7% | 29.0% | 8B |

> 来源: [ScreenSpot Leaderboard (llm-stats)](https://llm-stats.com/benchmarks/screenspot), [Qwen2.5-VL](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)

**关键能力**：
- ✅ 原生输出归一化坐标 [0-1000]
- ✅ JSON/XML/文本格式 bbox
- ✅ 动态分辨率 + MRoPE
- ✅ ScreenSpot 包揽前 5 名

**API 定价**：

| 模型 | 输入 | 输出 |
|------|------|------|
| qwen3-vl-plus | $0.20/1M | $1.60/1M |
| qwen3-vl-flash | $0.05/1M | $0.40/1M |

> 来源: [Qwen Cloud Pricing](https://docs.qwencloud.com/developer-guides/getting-started/pricing)

**优势**：
- ✅ ScreenSpot 绝对王者（95.8%）
- ✅ 原生坐标输出
- ✅ 多规模可选（4B-235B）
- ✅ 中文优化（COSMIC 环境友好）
- ✅ 廉价 API 降级路径

**劣势**：
- ❌ ScreenSpot-Pro 仍弱于专用模型（54.6% vs KV-Ground 73.2%）
- ❌ 通用模型，非 GUI 专项优化
- ❌ prompt 工程敏感——需精心设计指令

---

### 6.2 GPT-4o / GPT-4.1 (OpenAI)

| 基准 | GPT-4o |
|------|--------|
| ScreenSpot-Pro | **0.8%** |
| ScreenSpot | 18.3% |

> 来源: [ScreenSpot-Pro arXiv](https://arxiv.org/abs/2504.07981)

**关键发现**：GPT-4o 原生 grounding 能力极差（0.8%），但作为"规划器"有价值——ScreenSeeker 框架用 GPT-4o 做区域搜索，将 OS-Atlas-7B 从 18.9% 提升至 48.1%。

**P3A 适配**：不适合做 parser，但可作为管道中的语义推理层。

---

### 6.3 Claude (Anthropic)

| 基准 | 分数 |
|------|------|
| OSWorld-Verified (Sonnet 4.6) | 72.5% |
| OSWorld-Verified (Opus 4.6) | 72.7% |
| ScreenSpot-Pro (Claude 4.7) | 87.6%（with tools）|

> 来源: [Anthropic Claude 4.6 System Card](https://www-cdn.anthropic.com/4263b940cabb546aa0e3283f35b686f4f3b2ff47/claude-opus-4-and-claude-sonnet-4-system-card.pdf)

**关键差异**：Claude Computer Use 不输出 bbox——直接输出动作（`click(x,y)`）。适合端到端 agent，不适合做 parser。

---

### 6.4 Gemini 2.5 (Google)

| 基准 | 直接预测 | Mark-Grid Scaffold |
|------|---------|-------------------|
| ScreenSpot-v2 | 5.50% | **72.09%** |

> 来源: [Auxiliary Reasoning arXiv](https://arxiv.org/abs/2509.11548)

原生 grounding 极弱，但通过 grid 叠加技术可大幅提升——属于 Category 6 技术。

---

### 6.5 通用 VLM 对比

| 模型 | ScreenSpot-Pro | 原生 bbox | API 可用 | 适合 P3A |
|------|---------------|----------|---------|---------|
| Qwen3-VL-32B | 54.6% | ✅ | ✅ | ⭐⭐⭐⭐ |
| Qwen2.5-VL-72B | 43.6% | ✅ | ✅ | ⭐⭐⭐⭐ |
| GPT-4o | 0.8% | ❌ | ✅ | ⭐（规划器） |
| Claude 4 | 87.6%* | ❌ | ✅ | ⭐⭐（agent） |
| Gemini 2.5 Pro | 6.96% | ❌ | ✅ | ⭐ |
| DeepSeek-VL2 | — | ✅ (特殊 token) | ❌ | ⭐⭐ |
| InternVL3-8B | — | ✅ | ❌ | ⭐⭐ |

> *Claude 分数为 with tools，非 pure grounding

---

## 7. Category 5: 组合/管道方案（多模型协同）

> 将专用 grounding 模型 + 推理 VLM 组合，各取所长
> P3A 适配：核心架构参考——P3A 的 PerceptionService 本身就是管道

### 7.1 OmniParser + VLM 管道

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  截图输入     │────▶│  OmniParser  │────▶│     VLM      │────▶ 动作/分析
│              │     │  (检测+描述)  │     │ (语义推理)    │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                    元素 bbox + 描述 + ID
```

这是最成熟的管道方案。OmniParser 负责"看到什么"，VLM 负责"该做什么"。

**支持的 VLM**：GPT-4o, Claude, Qwen2.5-VL, DeepSeek-R1

**ScreenSpot-Pro (OmniParser v2 + GPT-4o)**: 39.6%

> 来源: [Microsoft OmniParser](https://github.com/microsoft/OmniParser)

---

### 7.2 KV-Ground-8B + Qwen3.5-27B 一致性路由

```
                    ┌──────────────────┐
        ┌──────────▶│  KV-Ground-8B    │──▶ bbox_A
        │           │  + Zoom-In       │
 截图+指令          └──────────────────┘
        │           ┌──────────────────┐
        └──────────▶│  Qwen3.5-27B     │──▶ bbox_B
                    │  + Zoom-In       │
                    └──────────────────┘
                            │
                    ┌───────┴───────┐
                    │ Zoom一致性比较 │
                    │ 选距离更近者   │
                    └───────┬───────┘
                            ▼
                       最终 bbox
```

**核心创新**：利用 Zoom-In 管道的中间结果作为置信度信号——正确预测的 zoom-in 第二步应该接近裁剪中心。

**ScreenSpot-Pro**: 80.9%（开源系统 No.1）

**Oracle 上限**: 85.1%

> 来源: [arXiv 2604.15376](https://arxiv.org/abs/2604.15376), [GitHub omxyz/zoom-consistency-routing](https://github.com/omxyz/zoom-consistency-routing)

**优势**：
- ✅ 无需训练，路由信号是管道自然产物
- ✅ 跨模型架构可比较（纯几何量）
- ✅ 当前公开系统最高 ScreenSpot-Pro 分

**劣势**：
- ❌ 需同时运行两个模型，计算成本翻倍
- ❌ 仅捕获 16.5% oracle 提升空间
- ❌ 信号强度中等 (|ρ| ≈ 0.13)

---

### 7.3 MEGA-GUI (Samsung SDS)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Gemini 2.5  │────▶│  UI-TARS-72B │────▶│  最终坐标     │
│  ROI 自适应  │     │  细粒度定位   │     │              │
│  缩放        │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
     Stage 1              Stage 2
```

**ScreenSpot-Pro**: 73.18%
**OSWorld-G**: 68.63%

> 来源: [arXiv 2511.13087](https://arxiv.org/abs/2511.13087)

---

### 7.4 组合方案对比

| 方案 | ScreenSpot-Pro | 模型数 | 延迟 | 复杂度 | P3A 参考价值 |
|------|---------------|-------|------|--------|-------------|
| OmniParser + VLM | 39.6% | 2-3 | 中 | 低 | ⭐⭐⭐⭐⭐ |
| KV-Ground + 路由 | **80.9%** | 2 | 高（双跑） | 中 | ⭐⭐⭐⭐ |
| MEGA-GUI | 73.18% | 2 | 高 | 高 | ⭐⭐⭐ |
| SeeAct-V (UGround+GPT-4o) | — | 2 | 中 | 中 | ⭐⭐⭐ |

**对 P3A 的启示**：
- P3A 的 `PerceptionService` 本身就是管道编排层
- 初期可用单模型；后期可升级为 OmniParser + Qwen-VL 组合
- 一致性路由是"免费"的置信度信号，值得关注

---

## 8. Category 6: 推理时扩展技术（不换模型，换策略）

> 通过推理策略改进（而非重新训练），显著提升任意基座模型的 grounding 精度
> P3A 适配：可作为 VisionProvider 的内部优化策略

### 8.1 Zoom-In / RegionFocus

**原理**：两阶段推理——先粗定位，再裁剪放大精细定位

```
步骤 1: 全图推理 → 粗略 bbox
步骤 2: bbox 区域裁剪放大 → 精细 bbox
```

**效果**：

| 模型 | 直接 | + Zoom-In | 提升 |
|------|------|-----------|------|
| KV-Ground-8B | 73.2% | 80.5% | +7.3% |
| Qwen2.5-VL-72B | 47.8% | 61.6% | +13.8% |
| UI-TARS-72B | 38.1% | 61.6% | +23.5% |

> 来源: [ICCV 2025 — RegionFocus](https://openaccess.thecvf.com/content/ICCV2025/papers/Luo_Visual_Test-time_Scaling_for_GUI_Agent_Grounding_ICCV_2025_paper.pdf)

**延迟代价**：2× 模型推理（全图 + 裁剪区域）

---

### 8.2 Mark-Grid Scaffold (Auxiliary Reasoning)

**原理**：将连续坐标预测转化为离散网格 ID 预测

```
原图 → 叠加 8×8 网格（每格标 ID）→ VLM 预测目标在哪些格 → 从格子坐标反算 bbox
```

**效果（Gemini-2.5-Flash）**：

| 方法 | ScreenSpot-v2 |
|------|--------------|
| 直接预测 | 5.50% |
| Coordinate Scaffold | 35.30% |
| Axis-Grid Scaffold | 56.37% |
| **Mark-Grid Scaffold** | **72.09%** |

> 来源: [arXiv 2509.11548](https://arxiv.org/abs/2509.11548)

**优势**：
- ✅ 无需重新训练
- ✅ 对通用 VLM 效果显著（Gemini 从 5.5% → 72.1%）
- ✅ 对 GPT-4o 效果同样显著（20.8% → 63.0%）
- ✅ 实现简单（叠加网格图 → 推理 → 解码）

---

### 8.3 Chain-of-Ground (Princeton)

**原理**：多步迭代推理——每步基于前一步结果修正

```
Step 1: 模型 A (粗) → bbox_v1
Step 2: bbox_v1 区域 → 模型 B (中) → bbox_v2
Step 3: bbox_v2 区域 → 模型 A (细) → 最终 bbox
```

**ScreenSpot-Pro**: 68.4%（三步），66.7%（两步）

> 来源: [arXiv 2512.01979](https://arxiv.org/abs/2512.01979), [GitHub Princeton-AI2-Lab/Chain-of-Ground](https://github.com/Princeton-AI2-Lab/Chain-of-Ground)

---

### 8.4 ScreenSeeker

**原理**：利用强规划 VLM（GPT-4o）生成候选搜索区域

**效果**：OS-Atlas-7B 从 18.9% → 48.1%（+254%）

> 来源: [ScreenSpot-Pro arXiv](https://arxiv.org/abs/2504.07981)

---

### 8.5 推理时扩展技术对比

| 技术 | 提升幅度 | 延迟代价 | 实现难度 | P3A 适用 |
|------|---------|---------|---------|---------|
| **Zoom-In** | 7-23% | 2× | 低 | ⭐⭐⭐⭐⭐ |
| **Mark-Grid** | 10-67% | 1× | 低 | ⭐⭐⭐⭐ |
| Chain-of-Ground | 4-5% | 2-3× | 中 | ⭐⭐⭐ |
| ScreenSeeker | 254%* | 中 | 中 | ⭐⭐ |

> *从极低基线出发，实际绝对值仍不突出

**对 P3A 的建议**：
- **Zoom-In 应作为 VisionProvider 的标配能力**（实现简单，提升稳定）
- Mark-Grid Scaffold 可作为通用 VLM 的备选增强策略
- 多步管道会增加延迟，初期建议单步+Zoom-In

---

## 9. 基准测试全景

### 9.1 核心基准简介

| 基准 | 样本数 | 平台 | 难度 | 当前最佳 | URL |
|------|--------|------|------|---------|-----|
| **ScreenSpot** | 1,272 | 移动/桌面/Web | 中 | Qwen3-VL-32B 95.8% | [leaderboard](https://gui-agent.github.io/grounding-leaderboard/) |
| **ScreenSpot-v2** | ~1,300 | 多平台 | 中 | Qwen3-VL-32B 95.8% | 同上 |
| **ScreenSpot-Pro** | 1,581 | 专业高分辨率 | 极高 | Claude 4.7 87.6% (with tools) | [leaderboard](https://gui-agent.github.io/grounding-leaderboard/screenspot.html) |
| **OSWorld** | 369 | 真实桌面 | 高 | Claude Opus 4.6 72.7% | [leaderboard](https://llm-stats.com/benchmarks/osworld) |
| **OSWorld-G** | — | 仅 grounding | 高 | KV-Ground-8B 68.1% | — |
| **AutoGUI-v2** | — | 功能理解 | 高 | OpenCUA-72B 67.9% | [GitHub](https://github.com/ZJULiHongxin/AutoGUI-v2) |

### 9.2 为什么 ScreenSpot-Pro 最关键

ScreenSpot-Pro 是 **唯一直接对应 P3A 需求的基准**：

- ✅ 测试的是"定位 UI 元素"（即 grounding），不是"完成任务"
- ✅ 高分辨率专业软件（Photoshop、IDE、CAD），类似 COSMIC 桌面环境
- ✅ 目标元素平均仅占 0.07% 屏幕面积——极度考验精确性
- ✅ 有公开 leaderboard，持续更新

ScreenSpot（v1/v2）已趋于饱和（Top 模型 95.8%），区分度不足。

### 9.3 注意：基准的局限性

- **数据污染风险**：部分模型可能在 ScreenSpot 测试集上训练过
- **分辨率差异**：ScreenSpot 截图分辨率远低于 2K COSMIC 桌面
- **平台偏差**：绝大多数基准截图来自 Windows/macOS，Linux/Wayland 截图零覆盖
- **串表风险**：聚合网站（如某些 LLM stats 站）可能张冠李戴

**建议**：以 COSMIC 实测为准，基准仅作参考排序。

---

## 10. 决策框架

### 10.1 P3A 需求优先级

```
必须满足（P0）:
├─ bbox 输出（可交互元素定位）       ← 核心功能
├─ 延迟 ≤ 3s P95（本地）            ← 用户体验
└─ parse(image, a11y_hints) 接口   ← 架构契约

应该满足（P1）:
├─ 元素类型分类（button/input/...） ← 结构化理解
├─ 文本提取（OCR）                  ← 语义理解
└─ confidence 分数                  ← 质量信号

最好满足（P2）:
├─ layout_summary（屏幕类型）       ← 高层上下文
├─ 区域检测（sidebar/toolbar...）   ← 布局理解
└─ 多平台一致性                     ← 未来扩展
```

### 10.2 三种候选架构

#### 架构 A：纯 Grounding + 后处理（推荐）

```
截图 → KV-Ground-8B (bbox) → OCR (text) → 规则分类 (type) → AnalysisResult
       └── 可选 + Zoom-In
```

| 维度 | 评估 |
|------|------|
| 精度 | ⭐⭐⭐⭐⭐ (SS-Pro 73-80%) |
| 延迟 | ⭐⭐⭐⭐ (单模型 ~1-2s) |
| 复杂度 | ⭐⭐⭐ (需要 OCR + 分类层) |
| 许可 | ⚠️ CC BY-NC-SA |
| 维护 | ⭐⭐⭐ (需要后处理管道) |

#### 架构 B：OmniParser 单管道

```
截图 → OmniParser v2 (检测+描述+OCR) → 映射到 AnalysisResult.elements[]
```

| 维度 | 评估 |
|------|------|
| 精度 | ⭐⭐⭐ (SS-Pro 39.6%) |
| 延迟 | ⭐⭐⭐ (0.8s 检测 + VLM 推理) |
| 复杂度 | ⭐⭐⭐⭐⭐ (开箱即用元素列表) |
| 许可 | ⚠️ AGPL (检测模型) |
| 维护 | ⭐⭐⭐⭐⭐ (微软维护，生态大) |

#### 架构 C：通用 VLM + Prompt 工程

```
截图 → Qwen3-VL-8B + "list all buttons with bbox" prompt → 解析 JSON → AnalysisResult
```

| 维度 | 评估 |
|------|------|
| 精度 | ⭐⭐⭐⭐ (SS 94.4%，SS-Pro 待验证) |
| 延迟 | ⭐⭐⭐⭐ (单模型 ~1-2s) |
| 复杂度 | ⭐⭐⭐⭐ (纯 prompt，无管道) |
| 许可 | ⭐⭐⭐⭐⭐ (Apache 2.0) |
| 维护 | ⭐⭐⭐⭐ (需要 prompt 迭代) |

### 10.3 推荐决策路径

```
Step 1: 先验证架构 C（Qwen3-VL-8B + prompt）
        ├─ 最快上线，零额外依赖
        ├─ 如果 prompt 工程能达到 SS-Pro ≥ 50%，直接用
        └─ 如果不够 →

Step 2: 加入架构 B（OmniParser v2）
        ├─ 输出天然匹配 AnalysisResult
        ├─ 注意 AGPL 许可风险
        └─ 如果许可或精度不满意 →

Step 3: 采用架构 A（KV-Ground-8B + 后处理）
        ├─ 精度最高，但工程量大
        ├─ 需要自建 OCR + 分类层
        └─ 注意 CC BY-NC-SA 许可

降级路径（所有架构通用）:
        └─ Qwen3-VL-Plus API ($0.20/1M input) 作为云端降级
```

### 10.4 不推荐的路径

| 路径 | 原因 |
|------|------|
| 端到端 Agent 模型（UI-TARS 等）作 parser | 输出动作非元素列表，overkill |
| GPT-4o / Claude 作 parser | 原生 grounding 极差（0.8%），成本高 |
| 多模型管道（MEGA-GUI 等） | 初版不需要如此复杂，延迟过高 |
| 仅依赖 ScreenSpot（非 Pro）选型 | 基准已饱和，无区分度 |

---

## 11. 验收截图集

收集 10-15 张 COSMIC 真实截图，覆盖以下场景：

| # | 场景 | 应用 | 关键验证点 |
|---|------|------|------------|
| 1 | IDE 主界面 | VS Code / Lapce | editor 区域、sidebar、toolbar 识别 |
| 2 | IDE 右键菜单 | VS Code | menu 元素、menu item 识别 |
| 3 | 浏览器页面 | Edge | content 区域、导航栏、tab 识别 |
| 4 | 浏览器弹窗 | Edge 权限请求 | dialog 识别、按钮元素 |
| 5 | 系统设置 | COSMIC Settings | sidebar 导航、form 识别、toggle |
| 6 | 设置子页面 | COSMIC Settings → Display | 复杂 form 元素、下拉框 |
| 7 | 文件管理器 | COSMIC Files | list/table 视图、sidebar、toolbar |
| 8 | 文件管理器右键 | COSMIC Files context menu | 弹出菜单检测 |
| 9 | 终端 | Terminoloy | terminal 区域、深色主题 |
| 10 | 对话框 | COSMIC Save File dialog | 文件选择器、输入框、按钮 |
| 11 | 混合窗口 | 多窗口重叠 | 前景/背景区分 |
| 12 | COSMIC 桌面 | 空桌面 + panel | 最小化界面，panel 检测 |
| 13 | 应用启动器 | COSMIC App Launcher | 搜索框、list 识别 |
| 14 | 通知弹窗 | COSMIC notification | 小型弹窗检测 |
| 15 | Flatpak 权限对话框 | Flatpak portal | portal 对话框识别 |

**新增场景（本版）**：

| # | 场景 | 验证点 |
|---|------|--------|
| 16 | 高 DPI 截图（2x/3x scaling） | 不同缩放比例下的坐标精度 |
| 17 | 深色主题密集 UI | 低对比度元素检测 |
| 18 | 非整数缩放（125%/150%） | 坐标变换验证 |

---

## 12. Go/No-Go 标准

### 必须满足（Hard Gates）

- 候选模型必须满足 `parse(image, a11y_hints) -> AnalysisResult` 接口契约
- 延迟在可接受范围内（本地 ≤ 3s P95，云端 ≤ 10s P95）
- 至少一种模型满足以下最低质量指标：

### 最低质量阈值

| 指标 | Go 阈值 | 测量方式 |
|------|---------|---------|
| 可交互元素召回率 (button/input/checkbox 等) | ≥ 60% | 人工标注对比 |
| 屏幕类型分类准确率 | ≥ 70% | 15 张截图分类 |
| 主区域检测率 (sidebar/toolbar/content) | ≥ 50% | COSMIC 典型布局 |
| bbox IoU（vs ground truth） | ≥ 0.5 | 像素级 |
| ScreenSpot-Pro 得分 | ≥ 50% | 公开 leaderboard 横向参考 |

### 优先策略

1. **先简单后复杂**：优先验证架构 C（通用 VLM + prompt），再考虑管道
2. **本地优先**：本地模型优先于云 API（延迟可控、隐私友好）
3. **必须保留云 API 降级路径**（无 GPU 用户可用 Qwen-VL API）
4. **宽松许可优先**：Apache 2.0 / MIT > CC BY-NC-SA > AGPL

---

## 13. 实施步骤

### Phase A: 数据准备（1-2 天）

1. **收集验收截图集**（15-18 张 COSMIC 截图，上述场景）
2. **人工标注 ground truth**：
   - 元素 bbox（[x, y, w, h]）
   - 元素类型（button/input/...）
   - 屏幕类别（ide/browser/settings/...）
   - 主区域（sidebar/toolbar/...）
3. **搭建评估框架**：自动化脚本调用候选模型 parse 截图，计算指标

### Phase B: 快速验证（2-3 天）

**优先验证架构 C — Qwen3-VL**：

4. **Qwen3-VL-8B + prompt 工程**
   - 设计 `"list all interactive elements with bbox, type, text"` 类 prompt
   - 测量元素召回率、bbox IoU、类型准确率
   - 验证 Zoom-In 叠加效果
   - 评估 prompt 稳定性（相同截图重复调用 5 次）

5. **Qwen3-VL API 降级测试**
   - 测试 qwen3-vl-flash / plus 的延迟和精度
   - 作为无 GPU 用户的降级路径验证

### Phase C: 管道验证（3-4 天）

6. **OmniParser v2**
   - 部署 YOLOv8 + Florence-2 管道
   - 测量结构化元素输出质量
   - 对比与 Qwen-VL prompt 方案的差异

7. **KV-Ground-8B**（如果许可允许）
   - 部署 8B 模型
   - 测量纯 grounding 精度
   - 评估叠加 OCR + 分类层的工程成本

### Phase D: 分析决策（1-2 天）

8. **结果分析**
   - 延迟、召回率、精度、边界情况对比
   - 输出对比矩阵

9. **决策 + 实现**
   - 选定主模型 + 备选降级方案
   - 实现真实 `VisionProvider`
   - 集成 Zoom-In 作为可选的推理时增强

---

## 14. 来源索引

### 专用 Grounding 模型

| 模型 | 关键来源 |
|------|---------|
| KV-Ground | [GitHub](https://github.com/vocaela/kv-ground), [HF Collection](https://huggingface.co/collections/vocaela/kv-ground) |
| UGround | [GitHub](https://github.com/OSU-NLP-Group/UGround), [arXiv 2410.05243](https://arxiv.org/abs/2410.05243) |
| GUI-Actor | [Microsoft Research](https://microsoft.github.io/gui-actor-coordinate-free-visual-grounding-for-gui-agents), [arXiv 2506.03143](https://arxiv.org/abs/2506.03143) |
| OS-Atlas | [GitHub](https://github.com/OS-Copilot/OS-Atlas), [arXiv 2410.23218](https://arxiv.org/abs/2410.23218) |
| ShowUI | [GitHub](https://github.com/showlab/ShowUI), [arXiv 2411.17465](https://arxiv.org/abs/2411.17465) |

### 端到端 Agent 模型

| 模型 | 关键来源 |
|------|---------|
| UI-TARS | [GitHub](https://github.com/bytedance/UI-TARS), [arXiv 2501.12326](https://arxiv.org/abs/2501.12326), [arXiv 2509.02544](https://arxiv.org/abs/2509.02544) |
| CogAgent | [GitHub](https://github.com/THUDM/CogVLM), [arXiv 2312.08914](https://arxiv.org/abs/2312.08914) |

### 屏幕解析工具

| 工具 | 关键来源 |
|------|---------|
| OmniParser | [GitHub](https://github.com/microsoft/OmniParser), [HF](https://huggingface.co/microsoft/OmniParser-v2.0), [arXiv 2408.00203](https://arxiv.org/abs/2408.00203) |

### 通用 VLM

| 模型 | 关键来源 |
|------|---------|
| Qwen-VL | [HF Collection](https://huggingface.co/collections/Qwen/qwen3-vl), [Qwen3-VL](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct), [Pricing](https://docs.qwencloud.com/developer-guides/getting-started/pricing) |
| Claude | [System Card](https://www-cdn.anthropic.com/4263b940cabb546aa0e3283f35b686f4f3b2ff47/claude-opus-4-and-claude-sonnet-4-system-card.pdf) |
| Gemini | [Auxiliary Reasoning arXiv 2509.11548](https://arxiv.org/abs/2509.11548) |

### 组合管道

| 方案 | 关键来源 |
|------|---------|
| KV-Ground + 一致性路由 | [arXiv 2604.15376](https://arxiv.org/abs/2604.15376), [GitHub](https://github.com/omxyz/zoom-consistency-routing) |
| MEGA-GUI | [arXiv 2511.13087](https://arxiv.org/abs/2511.13087) |
| OmniParser + VLM | [Microsoft Research](https://www.microsoft.com/en-us/research/articles/omniparser-v2-turning-any-llm-into-a-computer-use-agent/) |

### 推理时扩展

| 技术 | 关键来源 |
|------|---------|
| RegionFocus / Zoom-In | [ICCV 2025](https://openaccess.thecvf.com/content/ICCV2025/papers/Luo_Visual_Test-time_Scaling_for_GUI_Agent_Grounding_ICCV_2025_paper.pdf) |
| Mark-Grid Scaffold | [arXiv 2509.11548](https://arxiv.org/abs/2509.11548) |
| Chain-of-Ground | [arXiv 2512.01979](https://arxiv.org/abs/2512.01979), [GitHub](https://github.com/Princeton-AI2-Lab/Chain-of-Ground) |
| ScreenSeeker | [ScreenSpot-Pro arXiv 2504.07981](https://arxiv.org/abs/2504.07981) |

### 设计理论与参考架构

| 来源 | 链接 |
|------|------|
| Thinking with Visual Primitives (DeepSeek, 2026-04) | [GitHub](https://github.com/mitkox/Thinking-with-Visual-Primitives) |
| Action with Visual Primitives (AVP) | [arXiv 2605.22183](https://arxiv.org/abs/2605.22183) |

### 基准测试

| 基准 | 关键来源 |
|------|---------|
| ScreenSpot 全系列 Leaderboard | https://gui-agent.github.io/grounding-leaderboard/ |
| ScreenSpot 排名 (llm-stats) | https://llm-stats.com/benchmarks/screenspot |
| OSWorld Leaderboard | https://llm-stats.com/benchmarks/osworld |
| AutoGUI-v2 | [GitHub](https://github.com/ZJULiHongxin/AutoGUI-v2), [arXiv 2604.24441](https://arxiv.org/abs/2604.24441) |

---

## 输出

- `docs/PHASE3A-SPIKE-RESULTS.md` — 详细测试结果与决策依据
- `src/providers/vision.py` — 替换 `DummyVisionProvider` 为真实实现
