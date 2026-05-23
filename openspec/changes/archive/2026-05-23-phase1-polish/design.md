## Context

P1 Action Layer 完成后，`docs/P1-potential-issue.md` 记录了 6 项实测问题（P0-P2 级）。经审查实际代码，其中 3 项已在 P1 实现过程中修复：

| 问题 | 状态 | 说明 |
|------|------|------|
| P0-1 click 必须传坐标 | ✅ 已修 | `server.py` `_handle_mouse()` 已处理 x,y=None 的 click/dbl_click/right_click，回退到 mouse_down+up |
| P1-1 batch 丢中间结果 | ✅ 已修 | `_handle_batch()` 已返回 `{"results": [...], "completed": N, "total": M}` |
| P2-1 分辨率静默不一致 | ✅ 已修 | `server.py` `main()` 启动时已打印 KMS vs config 差异到 stderr |

**剩余待处理 3 项：**

| 问题 | 优先级 | 说明 |
|------|--------|------|
| P0-2 无位置查询能力 | P0 | 无法查询当前光标追踪位置。AI session 是 stateless，只能靠记忆 |
| P1-2 启动无校准 | P1 | uinput 初始化时 `_x=_y=0`，无任何警告。用户移动鼠标后所有绝对移动偏位 |
| P2-2 drag 接口不直观 | P2 | MCP API 用 (x,y,dx,dy)，AI 容易混淆绝对/相对语义 |

此外，已有修复未反映到 OpenSpec specs 中（batch 返回值格式、click 可选坐标），需同步更新。

## Goals / Non-Goals

**Goals:**
- 新增 `screen(action="cursor")` 返回当前内部追踪坐标
- `InputBackend` 新增 `get_cursor_position()` 抽象方法
- uinput 启动时打印光标位置未知警告（stderr）
- drag 的 MCP API 参数从 `(x, y, dx, dy)` 改为 `(x1, y1, x2, y2)`，与 backend 接口对齐
- 同步更新 specs：click 可选坐标、batch 返回数组格式、screen cursor action、drag 参数重命名

**Non-Goals:**
- ❌ 截图/视觉定位校准 — Phase 2 内容
- ❌ 读取真实光标位置（Wayland 无此能力）
- ❌ 修改 backend 内部逻辑（除新增 `get_cursor_position()` 和 drag 参数对齐）
- ❌ click 语义拆分（click vs click_at）— P3 远期讨论，本次不做

## Decisions

### D1: 光标位置通过 screen tool 的 cursor action 暴露

**选择**: `screen(action="cursor")` → `{"x": int, "y": int}`

**备选**: 
- 新增独立 tool `cursor` — 违反最小工具面原则
- 放在 mouse tool 里 `mouse(action="position")` — screen tool 更适合查询类操作

**理由**: screen tool 的定位是"获取屏幕信息"，cursor 位置属于屏幕信息。Phase 2 的 `screen(action="snapshot")` 也会返回屏幕信息。统一在 screen tool 下符合分类逻辑。

### D2: InputBackend 新增 `get_cursor_position()` 抽象方法

**选择**: 在 `InputBackend` ABC 中新增 `@abstractmethod get_cursor_position() -> tuple[int, int]`

**理由**: 
- 与 `screen_size()` 对称，都是查询类方法
- 跨平台后端都需要实现（即使某些平台能读真实位置）
- 不破坏现有接口，UInputBackend 只需返回 `(self._x, self._y)`

### D3: drag MCP API 参数改为 (x1, y1, x2, y2)

**选择**: MCP tool schema 中 drag 的参数从 `(x, y, dx, dy)` 改为 `(x1, y1, x2, y2)`，与 `InputBackend.drag(x1, y1, x2, y2)` 对齐。

**现状**: backend 已使用 `(x1, y1, x2, y2)`，但 MCP API 层暴露 `(x, y, dx, dy)` 并在 handler 中做转换 `x2 = x + dx`。这导致：
- AI 看到两套坐标语义，容易混淆
- handler 有额外转换逻辑
- 文档和实际行为不一致

**理由**: 统一为一种语义（起点+终点），消除转换层。**BREAKING** — 依赖 `(x, y, dx, dy)` 的调用方需要更新。但项目处于早期，无外部消费者。

### D4: 启动校准警告使用 stderr

**选择**: uinput `__init__()` 完成后立即 `print("[ai-gui-mcp] cursor position unknown, tracking assumes (0,0)", file=sys.stderr)`

**理由**:
- MCP stdio transport 中 stdout 被 MCP 协议占用，日志必须走 stderr
- 与已有的分辨率日志风格一致（同样 `print(..., file=sys.stderr)`）
- 不需要用户交互（用户不需要把光标移到 (0,0)），仅作提示
- Phase 2 引入截图后可做视觉校准，此警告届时可降级或移除

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| `get_cursor_position()` 返回的是追踪值，不是真实位置 | 方法名用 `cursor_position` 而非 `real_cursor_position`，文档说明是 tracked position |
| drag 参数改为 `(x1,y1,x2,y2)` 是 **BREAKING** 变更 | 无外部消费者，仅在项目内部使用。tasks 中标注 breaking change |
| 启动警告在正常使用时也是噪音（用户没碰鼠标时追踪是准的） | 警告仅一次，且对 debug 场景有价值。未来可加 `--quiet` 选项 |

## Open Questions

无 — 所有设计决策已在探索阶段确认。
