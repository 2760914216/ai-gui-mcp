## 1. 环境准备

- [x] 1.1 验证 `/dev/uinput` 写入权限（ACL 或 input 组）
- [x] 1.2 确认 Python ≥3.10 可用
- [x] 1.3 创建 `pyproject.toml` 并配置项目元数据与依赖（mcp, evdev, pydantic, pyyaml, pytest）
- [x] 1.4 执行 `uv sync` 或 `pip install -e .` 创建虚拟环境并安装依赖

## 2. 项目骨架 + 后端抽象接口

- [x] 2.1 创建 `src/` 目录结构（`src/__init__.py`, `src/backends/__init__.py`, `src/tests/`）
- [x] 2.2 创建 `config.yaml` — server name, transport, input backend, uinput device names, screen fallback
- [x] 2.3 实现 `src/backends/base.py` — `InputBackend` 抽象基类，含全部 mouse/keyboard/screen/close 抽象方法
- [x] 2.4 实现 `src/models.py` — pydantic 模型（`MouseAction`, `KeyboardAction`, `ScreenAction`, `BatchAction`, `BatchRequest`）
- [x] 2.5 实现 `src/config.py` — YAML 配置加载，含 `_deep_get()` 辅助方法

## 3. uinput 后端实现

- [x] 3.1 实现 `src/backends/uinput.py` 的 `UInputBackend.__init__()` — 创建 mouse + keyboard 两个 uinput 设备
- [x] 3.2 实现鼠标方法：`move_rel`, `move_abs`, `click`, `dbl_click`, `right_click`, `mouse_down`, `mouse_up`
- [x] 3.3 实现滚轮：`scroll(dy, dx)` 使用 `REL_WHEEL` 和 `REL_HWHEEL`
- [x] 3.4 实现拖拽：`drag(x1, y1, x2, y2)` — move+down+move+up 序列
- [x] 3.5 实现键盘方法：`type_text`（含 Shift 字符映射表），`press_combo`，`key_down`，`key_up`
- [x] 3.6 实现 `screen_size()` — 解析 `/sys/class/drm/` 获取分辨率，回退到 `config.yaml`
- [x] 3.7 实现 `close()` — 销毁两个 uinput 设备，释放资源
- [x] 3.8 编写 `src/tests/test_mouse.py` — 测试所有鼠标操作（使用 mock uinput）
- [x] 3.9 编写 `src/tests/test_keyboard.py` — 测试所有键盘操作（使用 mock uinput）

## 4. MCP Server

- [x] 4.1 实现 `src/server.py` — MCP Server 入口，注册 4 个 tool 定义
- [x] 4.2 实现 mouse tool handler — action 路由，坐标 clamp（0 ≤ x < width, 0 ≤ y < height）
- [x] 4.3 实现 keyboard tool handler — action 路由（type/press/down/up）
- [x] 4.4 实现 screen tool handler — `action="size"` → `backend.screen_size()`
- [x] 4.5 实现 batch tool handler — 顺序执行，遇错中止，返回 `{completed, total, error}`
- [x] 4.6 集成 pydantic 入参校验到所有 tool handler
- [x] 4.7 编写 `src/tests/test_batch.py` — 测试 batch 顺序执行、遇错中止、混合操作

## 5. 端到端验证

- [x] 5.1 手动测试：在真实桌面环境运行 mouse 操作（移动、点击），观察实际效果
- [x] 5.2 手动测试：在文本编辑器中运行 keyboard 操作（打字、Ctrl+S），验证字符输出
- [x] 5.3 手动测试：batch 操作（3+ 个混合 mouse/keyboard 操作顺序执行）
- [x] 5.4 手动测试：screen size 返回正确分辨率
- [x] 5.5 修复测试中发现的问题，确保所有 spec 场景满足
- [x] 5.6 运行完整测试套件 `pytest src/tests/` — 全部通过
