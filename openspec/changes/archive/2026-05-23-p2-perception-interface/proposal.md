## Why

P2 Spike 已验证截图链路完全可用（dbus-python, 53ms avg），且 AT-SPI2 在 COSMIC 上覆盖率 0%。当前 `server.py` 通过 `from spike.p2_screenshot_dbus_python import capture_screenshot` 直接调用 spike 临时代码——这不是可持续的架构。P2 需要交付一个可扩展的感知后端抽象（ScreenBackend），让截图作为当前唯一可用后端就绪化，同时为将来的 AT-SPI2、视觉识别、Windows UIA、macOS AX 等后端预留接口。不做这件事，后续 Phase 都建立在临时代码上。

## What Changes

- **新增** `ScreenBackend` 抽象接口，从 spike 原型升级为生产级代码，位于 `src/backends/screen.py`
- **新增** 感知数据模型（`ScreenSnapshot`, `UIElement`, `CursorInfo`），定义所有感知后端统一的出参结构，位于 `src/models.py`
- **新增** `XdgPortalBackend(ScreenBackend)` 实现，基于 dbus-python + GLib 线程桥接，位于 `src/backends/portal.py`
- **重构** `server.py` 的 `_handle_screen_snapshot()`：改为调用 `ScreenBackend.capture()` 而非直接 import spike 脚本
- **修改** `screen_snapshot()` 返回值语义：新增 `source` 字段（`"screenshot"` / `"accessibility"` / `"vision"`），`cursor` 结构化为 `{x, y, source}`）
- **修改** `cursor-calibration` 规范：确认 Wayland 硬件光标 overlay 无法在截图中检测，校准降级为 tracked-only
- **删除** `spike/` 目录中已验证的临时脚本（spike 结论已记录在 `docs/PHASE2-SPIKE-RESULTS.md`）
- **P1 测试回归**：51/51 必须全部通过

## Capabilities

### New Capabilities

- `screen-perception-models`: 定义 `ScreenSnapshot`、`UIElement`、`CursorInfo` 三个 pydantic 数据模型，作为所有感知后端统一的出参结构。`UIElement` 预留无障碍树和视觉识别两种来源的字段（id, role, name, bbox, states, confidence）。

### Modified Capabilities

- `screen-backend-abstraction`: 从 spike 原型阶段进入生产阶段。`capture()` 返回 `ScreenSnapshot` 而非原始 `bytes`。移除 spike-only 的 "prototype lives in spike/" 约束。
- `screen-snapshot-semantics`: 新增 `source` 字段区分感知来源（screenshot / accessibility / vision）。`cursor` 从简单 `{x,y}` 扩展为 `{x, y, source}`。放宽 `note` 字段为可选。
- `cursor-calibration`: 确认 Wayland 硬件光标 overlay 场景下 `detect_cursor()` 始终不可用（截图不含光标）。`cursor.source` 默认且仅可为 `"tracked"`。视觉校准留给 P3。

## Impact

- **新增文件**: `src/backends/screen.py`（抽象接口）, `src/backends/portal.py`（Portal 实现）
- **修改文件**: `src/models.py`（新增数据模型）, `src/server.py`（重构 snapshot handler）
- **删除文件**: `spike/p2_*` 全部临时脚本
- **不影响**: `src/backends/base.py`, `src/backends/uinput.py`, P1 所有现有功能
- **依赖**: `dbus-python` (system), `pyyaml`, `pydantic` (已在 pyproject.toml)
