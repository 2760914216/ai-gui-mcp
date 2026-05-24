## Why

P3A 是 AI GUI MCP 从"看到"到"看懂"的关键一步。当前 P2 的 `screen(action="snapshot")` 只能返回裸截图——AI 面对 2560×1600 的 base64 图像没有结构化感知能力，无法定位按钮、输入框、布局区域。已有 `docs/PHASE3A-DRAFT.md` 完成了语义收敛，现在需要将其固化为可实施的正式设计。

## What Changes

- **新增** `screen` tool 的 `analyze` / `image` action，`snapshot` 改为返回轻量 observation handle
- **新增** `PerceptionService` 内部编排层，负责 capture → analyze → image 的 provider 组装
- **新增** session-scoped `ObservationStore`，管理 `snapshot_id`、TTL、缓存和淘汰策略
- **新增** `SnapshotResult` / `AnalysisResult` / `ScreenState` 公开数据契约
- **新增** `ScreenshotProvider` / `AccessibilityProvider` / `VisionProvider` 内部 provider 抽象
- **新增** GUI parser 第一版受控枚举：`element.type`、`region.type`、`warning.code`
- **BREAKING**: `screen(action="snapshot")` 返回值从 `ScreenSnapshot`（内嵌 base64 图）改为 `SnapshotResult`（轻量 handle）；raw 图像改由 `screen(action="image", snapshot_id)` 按需获取
- **BREAKING**: `ScreenSnapshot.source` 单值字段不再作为分析结果来源标记；`AnalysisResult` 不再包含顶层 `source` 字段
- **修改** `ScreenBackend` 的定位：从"直接返回终态结果"改为 provider 适配层角色
- **修改** `ScreenAction` 的 action 枚举：从 `["size", "cursor", "snapshot"]` 扩展为 `["size", "cursor", "snapshot", "analyze", "image"]`

## Capabilities

### New Capabilities

- `observation-store`: session-scoped snapshot 存储，以 `snapshot_id` 为键管理 raw image artifact、元数据和 analysis 缓存。支持 N+TTL+内存上限联合淘汰策略。初版退化为进程内默认 session。
- `gui-parser-result`: `AnalysisResult` 作为 P3A 主产物——包含 `layout_summary`（屏幕类型、主区域、活跃对话框）、`elements[]`（扁平可交互元素 + 关键结构元素）、`overall_quality` 和结构化 `warnings[]`。采用中密度解析：可交互元素 (button/input/checkbox/radio/tab/menuitem/link) + 关键结构元素 (window/dialog/sidebar/toolbar/panel/list/table/form)。
- `perception-service`: 薄编排层 `PerceptionService`，封装 `ScreenshotProvider` + `AccessibilityProvider` + `VisionProvider` 的装配逻辑。`server.py` 只路由 tool action，不直接接触 provider。

### Modified Capabilities

- `screen-perception-models`: 新增 `ScreenState`（继承当前尺寸/光标查询）、`SnapshotResult`（替换 `ScreenSnapshot` 的公开角色）、`AnalysisResult`（取代 `elements` 字段的扁平列表语义）。`ScreenSnapshot` 降级为内部过渡模型。
- `screen-snapshot-semantics`: `screen(action="snapshot")` 从"返回完整截图数据"改为"创建 observation handle"（返回 `snapshot_id` + 轻量元数据）。raw 图像获取移入 `screen(action="image", snapshot_id)`。结构化解析结果移入 `screen(action="analyze", snapshot_id?)`。单一 `source` 字段不再作为 API 主标志。
- `screen-backend-abstraction`: `ScreenBackend` 从"终态感知返回者"改为 provider 角色；`PerceptionService` 成为新的内部编排入口。`XdgPortalBackend` 重定位为 `ScreenshotProvider` 实现。

## Impact

- **新增文件**: `src/services/perception.py`（PerceptionService）, `src/stores/observation.py`（ObservationStore），`src/providers/base.py`（provider 抽象）, `src/providers/screenshot.py`, `src/providers/a11y.py`, `src/providers/vision.py`
- **新增测试**: `src/tests/test_perception_service.py`, `src/tests/test_observation_store.py`, `src/tests/test_analysis_result.py`
- **修改文件**: `src/models.py`（新增 ScreenState/SnapshotResult/AnalysisResult，扩展 ScreenAction）, `src/server.py`（新增 analyze/image 路由，snapshot 改 handle 语义，注入 PerceptionService）, `src/backends/__init__.py`（调整导出）, `config.yaml`（新增 perception.service/cache/history 配置段）
- **不影响**: `src/backends/base.py`, `src/backends/uinput.py`, P1 所有 mouse/keyboard/batch 功能
- **依赖**: `pyyaml`, `pydantic>=2.0`（已有）。parser 具体视觉模型依赖在 P3A Spike 后确定
