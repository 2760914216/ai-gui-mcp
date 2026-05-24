## Context

当前 P2 实现采用直连模型：`server.py → ScreenBackend.capture() → ScreenSnapshot(base64 图)`。`ScreenSnapshot` 既是原始观测又是终态返回——`source` 单值字段试图标记三种来源（screenshot/accessibility/vision），`elements` 在 COSMIC 上始终为空，`screenshot` 字段始终携带 ~1.1MB base64 payload。

P3A 要解决的核心问题是：**屏幕截图只是 raw observation，AI 需要的是结构化 GUI 理解结果**。`docs/PHASE3A-DRAFT.md` 已收敛出三层抽象方向——保持 `screen` 为唯一读侧入口，底层 provider 负责采集，顶层 `AnalysisResult` 负责解析结果。但 Draft 未解答"现有 P2 公开接口如何过渡"这一关键问题。

COSMIC 环境下 AT-SPI2 覆盖率实际为 0%，因此视觉解析路径是感知主力。当前不引入无障碍树作为核心路径，但 provider 抽象预留其插槽。

## Goals / Non-Goals

**Goals:**
- 保持 4-tool 结构，`screen` 仍为唯一读侧入口
- `screen(snapshot)` 改为返回轻量 observation handle（`SnapshotResult`）
- 新增 `screen(analyze)` 返回结构化 `AnalysisResult`（P3A 主产物）
- 新增 `screen(image)` 按需返回 raw image/base64 payload
- 引入 `PerceptionService` 作为内部编排层，收口 provider 装配
- 引入 session-scoped `ObservationStore`，管理 snapshot 生命周期
- 定义 `SnapshotResult` / `AnalysisResult` / `ScreenState` 公开数据契约
- 冻结第一版 element.type / region.type / warning.code 受控枚举

**Non-Goals:**
- 不做 diff、region 局部分析、analyze profile
- 不做 semantic click / screen_find / click_element（P3B 范畴）
- 不做长期持久化历史、跨进程/跨重启恢复
- 不做多模型结果并存（同一 snapshot 只对应一种标准 parser 结果）
- 不做 field-level provenance
- 不修改 `InputBackend` 及其所有现有方法
- 不修改 mouse/keyboard/batch tool

## Decisions

### 决策 1：增量迁移，提前引入 PerceptionService

**选择**：不先做大重构，而是在现有 `ScreenBackend` 前面加一层薄 `PerceptionService`。迁移分三步：① 建立 ObservationStore + 新数据模型（内部先落，公开接口不变）；② 切 `screen` action 到新语义（同时废弃旧 `ScreenSnapshot` 公开契约）；③ 将 `XdgPortalBackend` 收口为 `ScreenshotProvider` 适配层。

```
迁移前（P2）
server.py → ScreenBackend.capture() → ScreenSnapshot

迁移后（P3A）
server.py → PerceptionService ─┬─ ScreenshotProvider (原 XdgPortalBackend)
                               ├─ AccessibilityProvider (空实现)
                               └─ VisionProvider
              │
              ▼
         ObservationStore (snapshot_id → raw + metadata + cached analysis)
              │
              ▼
         公开接口 → SnapshotResult / AnalysisResult / image payload
```

**理由**：
- 现有 `server.py` 直连 `ScreenBackend` 的模式已很简洁；加一层薄 Service 是最小修改
- 避免先把全部 provider 架构铺满再切 API——交付周期长，风险高
- 沿途可以用 `ScreenBackend → ScreenshotProvider` 适配器保持兼容

**替代方案**：
- 一次性大重构：把 provider/provenance/service 全铺开再上线 → 改动面大、验证难
- 让 `ScreenSnapshot` 长期留在公开层，`AnalysisResult` 并排 → 双契约维护成本高、语义分裂

### 决策 2：公开数据契约三层分离

**选择**：公开层定义三个独立模型，不混装：

```python
class ScreenState(BaseModel):
    """即时状态查询结果（size/cursor 返回）"""
    width: int
    height: int
    cursor_x: int
    cursor_y: int
    cursor_source: Literal["tracked", "detected"]

class SnapshotResult(BaseModel):
    """snapshot handle（轻量）"""
    snapshot_id: str
    created_at: str  # ISO 8601
    screen: ScreenState
    has_image: bool
    image_format: str | None  # "png"
    note: str | None

class AnalysisResult(BaseModel):
    """P3A 主产物"""
    snapshot_id: str
    overall_quality: Literal["high", "medium", "low"]
    warnings: list[AnalysisWarning]
    layout_summary: LayoutSummary
    elements: list[ParsedElement]
```

`ScreenSnapshot` 降级为内部过渡模型，仅在 `PerceptionService` 和 provider 之间流转，不作为 MCP tool 返回值。

**理由**：
- `SnapshotResult` 不包含 base64 图——这是 Draft 的核心约定：snapshot 创建 handle，不默认返回大 payload
- `AnalysisResult` 不包含 `source` 字段——Draft 已明确：来源信息下沉到 artifact/provenance 层
- 三模型独立允许各自独立演进（比如后续 snapshot 加 region 裁剪不影响 analysis 结构）

### 决策 3：snapshot_id 语义与 ObservationStore 设计

**选择**：`snapshot_id` 格式 `snap_{uuid_short}`，由 `ObservationStore.create()` 生成。每次 `screen(snapshot)` 调用必然产生新 snapshot_id（即使 capture 失败也返回一个含 error 的 handle，但 `has_image=false`）。

存储策略：
- **数据结构**：内存 dict，键为 `snapshot_id`，值为 `ObservationRecord`（含 raw image bytes、metadata、cached analysis）
- **淘汰策略**：最近 N 个（默认 16）+ TTL（默认 300s）+ 总内存上限（默认 256MB）
- **缓存策略**：`analyze` 结果以 `snapshot_id` 为缓存键（P3A 初版不做 analyze profile，一张图只有一种标准解析结果）
- **作用域**：语义上 session-scoped；初版退化为当前 MCP 进程内默认 session

**理由**：
- `uuid_short` 足够唯一且比完整 UUID 短，适合日志/调试
- 三项联合淘汰避免任一维度失控
- 不做跨进程持久化——P3A 非目标，且引入序列化会扩大设计面

### 决策 4：中密度 GUI Parser，flat elements + region ref

**选择**：`AnalysisResult.elements` 为扁平列表，每个 `ParsedElement` 通过 `parent_id/children_ids` 表达局部层级，通过 `region_ref` 表达全局归属。

元素范围：
- **可交互元素**：button, input, checkbox, radio, tab, menuitem, link
- **关键结构元素**：window, dialog, sidebar, toolbar, panel, list, table, form

```python
class ParsedElement(BaseModel):
    id: str
    type: Literal["button","input","checkbox","radio","tab","menuitem","link",
                   "window","dialog","sidebar","toolbar","panel","list","table","form",
                   "text","unknown"]
    bbox: list[int]  # [x, y, w, h]
    text: str | None
    description: str | None
    confidence: float | None  # 0.0-1.0, null for accessibility
    parent_id: str | None
    children_ids: list[str]
    region_ref: str | None
```

**理由**：
- 扁平列表是 AI 最直接的消费形态（token-efficient，无递归解析）
- `parent_id/children_ids` 保留局部结构但不强制完整树
- `region_ref` 把元素挂到布局区域，避免 AI 从坐标"猜"元素属于 sidebar 还是 content
- best-effort 语义：parser 能返回部分结果时就返回，通过 `overall_quality` 和 element 级 `confidence` 表达可信度

### 决策 5：provider 抽象与降级链

**选择**：定义三个 provider 抽象，装配在 `PerceptionService` 层：

```python
class ScreenshotProvider(ABC):
    def capture(self) -> RawImage: ...

class AccessibilityProvider(ABC):
    def is_available(self) -> bool: ...
    def get_tree(self, max_depth=5, max_nodes=200) -> A11yTree: ...

class VisionProvider(ABC):
    def parse(self, image: RawImage, a11y_hints: A11yTree | None) -> AnalysisResult: ...
```

当前 `XdgPortalBackend` 先做 `ScreenshotProvider` 适配层。`AccessibilityProvider` 在 COSMIC 下始终返回空（`is_available() → False`），但不妨碍接口存在。`VisionProvider` 在 P3A Spike 后确定具体模型引擎。

**理由**：
- Provider 抽象是 Draft 的核心设计——决定"数据从哪来"，不决定"对外 API 长什么样"
- 三层 provider 允许后面独立替换：截图方案换成 wlr-screencopy 不动其他层；视觉模型从 OmniParser 换成 UI-TARS 不动截图层
- COSMIC 实测 AT-SPI2 覆盖率 0%，但不删除 `AccessibilityProvider`——保持架构对未来 GNOME/KDE 场景的开放性

### 决策 6：provenance 与失败语义

**选择**：P3A v1 不在 `AnalysisResult` 层做 full provenance。`SnapshotResult.note` 可记录 capture 来源（如 "xdg-desktop-portal"）。`AnalysisResult` 通过 `overall_quality` + `warnings[]` 表达质量，不设置顶层 `source` 字段。

```python
class AnalysisWarning(BaseModel):
    code: Literal[
        "image_unavailable",
        "provider_timeout",
        "dense_ui_possible_misses",
        "ocr_low_confidence",
        "partial_parse",
        "unsupported_layout"
    ]
    severity: Literal["low", "medium", "high"]
    message: str
```

失败分为硬错误和软失败：
- **硬错误**：snapshot 不存在、provider 崩溃 → 返回 MCP tool error
- **软失败**：图像可用但解析不理想 → 正常返回 `AnalysisResult`，`overall_quality="low"`，附带 `warnings`

**理由**：
- Draft 已明确不要顶层单值 `source`，用 `providers_used`/artifact provenance 替
- P3A v1 先做 provider 级标记就够；field-level provenance 会拖慢整体节奏
- best-effort 原则：能返回部分结果就返回，不做 all-or-nothing

### 决策 7：screen action 参数与默认行为

**选择**：

| action | 参数 | 返回 | 说明 |
|--------|------|------|------|
| `size` | — | `ScreenState` | 不变 |
| `cursor` | — | `ScreenState` | 不变 |
| `snapshot` | — | `SnapshotResult` | 创建 handle，不返回大图 |
| `analyze` | `snapshot_id?` | `AnalysisResult` | 无参时内部先 snapshot 再 analyze |
| `image` | `snapshot_id` | `{snapshot_id, mime_type, image_base64}` | 按需取 raw |

`analyze` 不传 `snapshot_id` 时自动创建新的 snapshot 作为分析锚点。这是语法糖——内部语义仍然是"先绑定到某个 snapshot，再返回分析结果"。

**理由**：
- 保持 4-tool，`screen` action 从 3 个扩到 5 个——仍在"最小工具面"原则内
- `snapshot_id` 是后续 diff/对比的基础——即使 P3A 不做 diff，数据模型要预留
- `image` 作为重载荷接口独立出去，避免 snapshot 每次都被迫传输 1.1MB

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| **BREAKING**: 现有 `screen(snapshot)` 消费者可能依赖 base64 直接返回 | 计划中明确 breaking；若有外部消费者，可在 P3A-1 阶段提供短期兼容标志（`compat_snapshot_embed_image=true`），写清 P3A-3 移除 |
| 视觉模型延迟可能很高（OmniParser ~800ms on 4090） | `overall_quality` 和 `warnings` 预先设计超时/降级语义；本地模型和云 API 均需有超时配置 |
| `ObservationStore` 内存压力（2560×1600 RGBA PNG ~3MB raw per snapshot） | TTL + N + memory budget 三重门；默认 256MB 上限约可容纳 ~80 张未分析快照 |
| `VisionProvider` 具体实现依赖外部模型（尚待 P3A Spike） | Provider 抽象先落，实现留到 Spike 后；初版可返回 mock `AnalysisResult` 用于 API 层集成测试 |
| P2 `ScreenSnapshot` 到 P3A 三模型的过渡期测试覆盖 | 保留 `ScreenSnapshot` 相关测试但标记 `deprecated`；P3A 新增全套独立测试 |
| `AccessibilityProvider` 在 COSMIC 上永远是空——可能被质疑"白占接口" | 架构设计明确这是 Linux 通用抽象，不因单一 compositor 的现状移除；空实现本身就是合法状态 |

## Migration Plan

```
P3A-1: 内部层建设（公开接口不变）
  ├─ src/models.py: 新增 ScreenState / SnapshotResult / AnalysisResult (不删除 ScreenSnapshot)
  ├─ src/stores/observation.py: 实现 ObservationStore
  ├─ src/services/perception.py: 实现 PerceptionService 骨架（转发到现有 ScreenBackend）
  └─ 验证: 所有现有 P1/P2 测试不回归

P3A-2: 公开 API 切换
  ├─ src/server.py: screen action 扩展 snapshot/analyze/image
  ├─ snapshot 走 SnapshotResult，废弃 ScreenSnapshot 公开契约
  ├─ 加短期兼容标志（如需要）
  └─ 验证: 新 API 返回正确的 handle / analysis result / image

P3A-3: Provider 收口
  ├─ src/providers/: ScreenshotProvider 抽象 + 基于 XdgPortalBackend 的适配实现
  ├─ src/providers/a11y.py: AccessibilityProvider + 空实现
  ├─ PerceptionService 切换到 provider 编排
  └─ 验证: 集成测试覆盖 provider 降级路径

P3A-4: VisionProvider + Spike
  ├─ P3A Spike: 验证候选视觉模型（OmniParser / UI-TARS / 云 VLM）在 COSMIC 上的时效/精度
  ├─ src/providers/vision.py: VisionProvider 实现
  └─ 验证: 10-15 张验收截图集，确认 AnalysisResult 质量达标
```

## Open Questions

1. **视觉模型选型**：OmniParser v2（本地 4090 ~800ms）vs UI-TARS-7B（本地更轻）vs 云 VLM API（无需 GPU）——Spike 后确定。原则：同一资源量级选当时 leaderboard 最优
2. **P3A Spike 验收集**：需要 10-15 张 COSMIC 真实截图（IDE、浏览器、设置、文件管理器、对话框），确认 parser 在目标场景下的召回率与精度
3. **兼容模式存续期**：若加 `compat_snapshot_embed_image`，最迟到哪个阶段移除
4. **VisionProvider 的超时/降级契约**：parser 的最小可用延迟阈值和降级行为
5. **`element.id` 的稳定性**：同一元素跨 snapshot 是否保持稳定 id——初版不做 tracking，但字段预留
