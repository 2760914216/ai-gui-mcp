## Why

Phase 2（Perception Layer）需要为 AI 提供屏幕感知能力——截图、无障碍树、窗口管理。但 Phase 0 Spike 发现 AT-SPI2 在 COSMIC 上覆盖率仅 ~5%，原"无障碍树为主、视觉为兜底"的设计前提已经崩塌。此外，D-Bus 异步截图、光标校准协议、ScreenBackend/InputBackend 边界、工具面设计等问题均未在真实环境中验证过。参照 Phase 0 Spike 的先验证再编码原则，P2 启动前必须先做一个 mini-spike，把技术未定点全部实测一遍。

## What Changes

- 新增 `src/backends/screen/` 目录，包含 `ScreenBackend` 抽象接口和 xdg-desktop-portal 截图实现（spike 阶段为原型代码，非最终交付）
- 在现有 `screen` tool 上增加 `action=snapshot` 原型，验证截图→base64 的完整链路
- 验证 D-Bus 异步模型与现有同步 InputBackend 的兼容性（`dbus-python` + GLib vs `dbus-next` vs `dasbus`）
- 实测 AT-SPI2 树抓取：用 `dbus-python` 直连 AT-SPI2 bus，尝试获取 WebKit 进程的完整元素树（含 bbox/role/name/states）
- 实现光标校准原型：截图→检测光标像素位置→更新内部 `_x,_y`
- 形成 P2 实现决策文档，输出结论：每个 spike 项的可选方案、实测数据、推荐选择

## Capabilities

### New Capabilities

- `screen-capture`: xdg-desktop-portal 截图能力——非交互式全屏截图，返回 base64 PNG 数据
- `screen-snapshot-semantics`: `screen_snapshot()` 的语义定义——AT-SPI2 覆盖率 ~5% 的现实下，返回结构如何设计（空 elements + 纯截图 vs 内置粗粒度视觉标注）
- `cursor-calibration`: 光标校准协议——通过截图检测光标像素位置，校准内部坐标追踪
- `screen-backend-abstraction`: `ScreenBackend` 抽象接口定义——与现有 `InputBackend` 的职责边界划分

### Modified Capabilities

- `mcp-action-tools`: `screen` tool 扩展 `snapshot` action（原型阶段），`batch` tool 需支持 screen action 的异步结果传递

## Impact

- **新增依赖**: `dbus-python`（或替代方案 `dasbus`/`dbus-next`）用于 D-Bus 截图和 AT-SPI2 通信
- **新增模块**: `src/backends/screen/` — ScreenBackend 抽象 + xdg-portal 实现（spike 原型）
- **代码侵入**: P1 现有 `server.py`、`models.py`、`config.yaml` 需少量扩展以支持 `screen snapshot` action（原型阶段，最终设计以 spike 结论为准）
- **不改动**: `InputBackend` 接口保持不变，spike 仅新增 `ScreenBackend`，不修改现有 uinput 实现
- **文档产出**: `docs/PHASE2-SPIKE-RESULTS.md` — 验证结论与 P2 实现决策
