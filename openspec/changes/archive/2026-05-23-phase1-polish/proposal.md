## Why

P1 Action Layer 实测发现 6 项问题（P0-P2 级），其中 click 必须传坐标导致 AI 无法使用 "move_rel + click" 工作流，batch 丢失中间结果导致无法在一次往返中完成 "取屏幕信息 → 计算 → 操作"，光标跟踪漂移使绝对移动在外部干扰后全错。这些不是锦上添花——P0 级是缺陷，P1 级是持续疼痛点。所有改动在 Action 层内部，与 Phase 2 Perception 层无架构冲突，且 batch 改数组格式是 Phase 2 的正向前置。

## What Changes

- **mouse click/dbl_click/right_click 的 x,y 改为可选** — 缺坐标时直接在当前光标位置点击，无需用户用 down/up 变通
- **screen 新增 `action="cursor"`** — 返回当前内部追踪的光标位置 (x, y)，解决 stateless AI session 的位置追踪问题
- **batch 返回值从计数改为结果数组** — 保留每个步骤的返回值（含 screen.size 的结果），遇错返回已完成步骤的结果 + 错误信息
- **启动时打印光标位置警告** — 当光标位置未知时（server 重启后），日志提示 "cursor position unknown, tracking assumes (0,0)"
- **启动时打印分辨率差异日志** — 当 KMS 检测值与 config.yaml 配置值不一致时，日志提示实际使用的分辨率
- **drag 接口参数名清晰化** — 将 drag 的 (x, y, dx, dy) 改为语义更明确的 (x1, y1, x2, y2)，减少 AI 混淆

## Capabilities

### Modified Capabilities
- `mcp-action-tools`: mouse click/dbl_click/right_click 的 x,y 参数从必填改为可选；screen 工具新增 cursor action；启动时分辨率差异日志
- `batch-executor`: 返回值格式从 `{"completed": N, "total": M}` 改为 `[result1, result2, ...]`，遇错返回已完成结果 + 错误
- `uinput-backend`: 新增光标位置查询能力；启动时位置未知警告；drag 参数命名从 (x,y,dx,dy) 改为 (x1,y1,x2,y2)
- `input-backend-abstraction`: drag 方法签名变更（参数重命名）；新增 `get_cursor_position()` 抽象方法

## Impact

- `src/models.py` — MouseAction 的 x,y 在 click/dbl_click/right_click 时不强制要求
- `src/server.py` — `_handle_mouse()` 路由逻辑：缺坐标时跳过 move 直接 down/up；新增 `_handle_screen()` cursor action；batch 执行器改为返回数组
- `src/config.py` — 启动时检测 KMS vs config 分辨率差异并打印日志
- `src/backends/base.py` — `InputBackend` 新增 `get_cursor_position()` 抽象方法；drag 签名改为 (x1, y1, x2, y2)
- `src/backends/uinput.py` — 实现 `get_cursor_position()`；启动时打印位置未知警告；drag 适配新签名
- `src/tests/` — 更新受影响的测试用例
