# Phase 3A 草案 — 感知抽象与 GUI Parser 设计

> 状态：讨论稿（跨 session 延续用）
>
> 目的：固化 P3A 当前已讨论出的抽象边界、对象模型与非目标，避免后续 session 重新推导。

---

## 1. P3A 的定位

P3A 不是 agent，不是 planner，也不是 action 层增强。

**P3A 的唯一目标**：

> 把当前整屏 observation 转成可被 AI 稳定消费的结构化 GUI 理解结果。

也就是：

```text
raw screenshot
    ↓
GUI parser
    ↓
structured elements + layout summary
```

P3A 优先解决“先能够看到、看懂东西”，**不优先解决**“按语义点击”。

---

## 2. 这次讨论得出的核心修正

### 2.1 不再引入第二个“看”入口（如 `see`）

此前讨论曾尝试把 P3 感知能力拆成 `screen` 与 `see` 两个顶层入口，但这会产生抽象错位：

- screenshot 似乎在两边都存在
- accessibility tree 挂在 `screen` 下
- vision parse 挂在 `see` 下
- provider 实现细节泄漏到 tool 心智模型

**当前结论**：不要让 `screen` + `see` 并存。

> 顶层应保持**单一读侧入口**；底层 `screenshot / accessibility / vision` 统一视为 provider。

---

## 3. 推荐的三层抽象

```text
Tool / API 层
└─ screen
   ├─ size / cursor            # state query
   └─ snapshot / analyze / image  # perception query

Provider / Backend 层
└─ PerceptionService
   ├─ ScreenshotProvider
   ├─ AccessibilityProvider
   └─ VisionProvider

Data Contract 层
├─ ScreenState
├─ SnapshotResult
└─ AnalysisResult
```

### 3.1 Tool / API 层

对外继续保留 `screen` 作为唯一读侧入口，原因：

- 保持 4 tool 最小工具面
- 兼容 P2 已有 `screen(action="snapshot")`
- 避免 `screen` / `see` 双真相

但语义需要收紧：

> `screen` 不只是“截图工具”，而是“环境读取 / 感知入口”。

其中：

- `size` / `cursor` 属于 **state query**
- `snapshot` / `analyze` / `image` 属于 **perception query**

### 3.2 Provider / Backend 层

真正的统一不应该发生在 tool 命名，而应该发生在 provider 编排层。

底层 provider 的职责：

- `ScreenshotProvider`：生成 raw screenshot observation
- `AccessibilityProvider`：提供可选结构化树增强
- `VisionProvider`：执行 GUI parser / OCR / 结构化视觉分析

关键原则：

> provider 决定“数据从哪来”，不决定“对外 API 长什么样”。

### 3.3 Data Contract 层

原始 observation 与解释结果需要分开，不能混成一个万能结果体。

- `ScreenState`：尺寸、光标等即时状态
- `SnapshotResult`：raw observation
- `AnalysisResult`：parsed observation

---

## 4. `screen` 顶层接口草案

### 4.1 `screen(action="snapshot")`

职责：**创建 observation handle**，而不是直接把大图吐回上层。

默认应返回轻量对象，例如：

```json
{
  "snapshot_id": "snap_xxx",
  "created_at": "2026-05-24T12:34:56Z",
  "screen": {"width": 2560, "height": 1600},
  "source": "portal",
  "has_image": true
}
```

设计原则：

- 默认返回 handle，不默认返回大 payload
- `snapshot_id` 成为后续分析与派生结果的锚点

### 4.2 `screen(action="analyze", snapshot_id?)`

职责：返回 **P3A 主产物** —— GUI parser 结果。

若不传 `snapshot_id`，外部可走便捷模式；但内部语义仍应先绑定到某个 snapshot，再返回结果。

### 4.3 `screen(action="image", snapshot_id)`

职责：按需取 raw image payload。

这是给 multimodal AI、调试、核对用的重载荷接口，不应成为默认调用路径。

---

## 5. Observation 生命周期

### 5.1 作用域

对外语义使用 **session-scoped observation**。

但初版实现允许退化成：

> 当前 MCP 进程内的默认 session。

也就是说：

- 语义上按 session 理解
- 实现上先不追求跨重启/跨进程恢复

### 5.2 历史策略

历史记录需要有，但默认只做**短期、会话内、内存中、可淘汰**。

联合淘汰策略：

- 最近 N 个
- TTL
- 总内存上限

不默认长期保存，不自动落盘。

### 5.3 缓存策略

`analyze` 是 `snapshot` 的派生物，因此初版缓存键直接为：

```text
snapshot_id
```

P3A 初版**不做 analyze profile**；同一张图只对应一种标准 parser 结果。

---

## 6. P3A 的主结果形态

### 6.1 整体原则

P3A 主结果应更像 **parser result**，而不是 report。

- report / summary / diff 都是派生视图
- parser 结果才是主契约

### 6.2 `AnalysisResult` 草案

```json
{
  "snapshot_id": "snap_xxx",
  "overall_quality": "high|medium|low",
  "warnings": [
    {
      "code": "dense_ui_possible_misses",
      "severity": "medium",
      "message": "UI is dense; some small interactive elements may be missing"
    }
  ],
  "layout_summary": {
    "screen_kind": {
      "kind": "ide|browser|settings|dialog|file_manager|unknown",
      "detail": "optional"
    },
    "main_regions": [
      {
        "id": "region_sidebar",
        "type": "sidebar|toolbar|editor|content|dialog|panel|list|table|form|unknown",
        "detail": "optional",
        "bbox": [0, 0, 200, 1600]
      }
    ],
    "active_dialog": {
      "present": false,
      "region_ref": null,
      "element_ref": null
    },
    "notes": null
  },
  "elements": [
    {
      "id": "el_001",
      "type": "button|input|checkbox|radio|tab|menuitem|link|window|dialog|sidebar|toolbar|panel|list|table|form|text|unknown",
      "bbox": [100, 50, 80, 24],
      "text": "Save",
      "description": "save button",
      "confidence": 0.92,
      "parent_id": null,
      "children_ids": [],
      "region_ref": "region_toolbar"
    }
  ]
}
```

### 6.3 为什么 bbox 必须存在：Reference Gap 论证

P3A 输出 `ParsedElement.bbox` 不是「给 AI 提供一个可选的坐标提示」，而是消除 AI 推理歧义的**必要条件**。

DeepSeek 2026-04 的「Thinking with Visual Primitives」论文指出：当前 VLM 面临的核心瓶颈不是「看不清」（Perception Gap），而是 **Reference Gap**——自然语言在密集空间布局中过于模糊，导致推理链中出现逻辑崩溃和幻觉。

> 自然语言无法精确指代「左边第三个按钮」「搜索框下方那个下拉菜单」。

模型学会在推理过程中交错插入空间标记（点、bbox）作为「最小思维单元」后，在空间推理基准上达到 GPT-5.4 / Claude-Sonnet-4.6 / Gemini-3-Flash 同等水平，且视觉 token 消耗显著更低。

**对 P3A 的推论**：`ParsedElement.bbox` 不是「额外信息」，它是 AI 消费 GUI 理解结果时消除 Reference Gap 的**唯一锚点**。这也是为什么 element 模型设计为 `{bbox, type, text}` 三元组——bbox 提供空间锚定，type/text 提供语义标签，二者缺一不可。

> 来源: [Thinking with Visual Primitives](https://github.com/mitkox/Thinking-with-Visual-Primitives) (DeepSeek, 2026-04)

---

## 7. P3A 的解析粒度

### 7.1 选择：中密度 GUI parser

P3A 不走极稀疏，也不走 dense parse。

当前已讨论出的方向是：

> **可交互元素 + 关键结构元素**

### 7.2 元素范围

#### 可交互元素

- button
- input
- checkbox
- radio
- tab
- menuitem
- link

#### 关键结构元素

- window
- dialog
- sidebar
- toolbar
- panel
- list
- table
- form

### 7.3 组织方式

选择：

- 主消费入口是 `elements[]` 扁平列表
- 保留 `parent_id / children_ids`
- element 显式挂 `region_ref`

也就是：

> 局部结构通过 parent/children 表达，全局归属通过 region_ref 表达。

---

## 8. 质量与失败语义

### 8.1 best-effort，而不是全-or-nothing

P3A 的 GUI parser 应该是 **best-effort**：

- 能返回部分结果时就尽量返回
- 不能假装“看不全就等于彻底失败”

区分：

- **硬错误**：系统没法工作（snapshot 不存在、provider 崩溃）
- **软失败**：系统工作了，但看得不够好（低质量、界面过密、OCR 差）

### 8.2 质量字段

使用两层质量表达：

- `overall_quality`: `high | medium | low`
- element 级 `confidence`

### 8.3 warning 结构

`warnings[]` 必须结构化，不使用纯文本。

建议字段：

- `code`
- `severity`
- `message`

---

## 9. 明确的非目标（P3A 不做）

以下内容明确不进入 P3A 初版核心范围：

- diff
- region / area 局部分析
- analyze profile（如 fast / rich）
- semantic click
- screen_find / click_element 的动作能力
- 长期持久化
- 强稳定跨帧 tracking
- 复杂 agent planning
- report / 长摘要作为主接口

---

## 10. 为什么不继续用顶层单值 `source`

P2 当前 `ScreenSnapshot.source = screenshot | accessibility | vision` 在单 provider 阶段还能工作；
但 P3 进入融合后，这个抽象会失真。

例如一次 analyze 可能同时使用：

- screenshot
- OCR
- vision parse
- accessibility hint

因此长期更稳的方向是：

> 不再让顶层单值 `source` 承担全部来源语义；来源信息应逐步下沉到 artifact / field provenance。

---

## 11. 当前阶段最重要的一句话

> P3A 的关键不是“先上哪个模型”，而是先把 **tool/API 层、provider/backends 层、data contract 层** 三层分清；并且坚持单一读侧入口，避免让 provider 细节渗漏到 AI 的工具心智模型里。

---

## 12. 后续可继续收敛的点

当前草案之后，下一轮讨论建议聚焦：

1. `element.type` / `region.type` / `warning.code` 的第一版受控枚举表
2. `AnalysisResult` 与现有 `ScreenSnapshot` 的兼容演进方式
3. `PerceptionService` 是否作为显式内部抽象写进正式设计
4. P3A Spike 的验收集与质量门槛
