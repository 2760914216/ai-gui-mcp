## Why

Phase 0 Spike 已验证 uinput 鼠标/键盘注入、屏幕分辨率检测、坐标追踪精度在当前 Linux Wayland COSMIC 环境下全部可行。现在是时候构建 MCP 工具层的第一个里程碑：让 AI 能通过标准化接口执行桌面 GUI 操作。

## What Changes

- 新建完整项目骨架：`pyproject.toml`、`config.yaml`、源码目录结构
- 实现 `InputBackend` 抽象接口（`src/backends/base.py`）— 为后续跨平台扩展奠定基础
- 实现 `UInputBackend`（`src/backends/uinput.py`）— Linux uinput 内核级鼠标键盘模拟
- 定义 pydantic 数据模型（`src/models.py`）— 入参校验
- 实现 MCP Server（`src/server.py`）— 4 个 tool：mouse、keyboard、screen、batch
- 实现 batch 批量执行器 — 顺序执行混合操作，遇错中止
- 实现 KMS/sysfs 屏幕分辨率自动检测
- 内部坐标追踪 — Wayland 无法读全局光标位置，靠相对移动累积
- 编写测试：mouse、keyboard、batch 的单元与集成测试

## Capabilities

### New Capabilities

- `input-backend-abstraction`: 跨平台输入后端抽象接口，定义鼠标/键盘/屏幕查询的标准方法签名
- `uinput-backend`: Linux uinput 内核级鼠标键盘模拟实现 — 移动、点击、拖拽、滚动、按键、组合键、文本输入
- `mcp-action-tools`: MCP Server 暴露 4 个 GUI 操作 tool（mouse/keyboard/screen/batch），含 action 参数路由与坐标 clamp
- `batch-executor`: 批量操作执行器 — 顺序执行混合 mouse/keyboard/screen 操作，遇错中止并返回完成计数

### Modified Capabilities

<!-- No existing capabilities to modify — this is the first implementation phase -->

## Impact

- **新增**: `src/` 目录下全部源码（~8 个文件）
- **新增**: `pyproject.toml` — 项目元数据与依赖声明（mcp, evdev, pydantic, pyyaml）
- **新增**: `config.yaml` — 运行时配置
- **新增**: `src/tests/` — 测试套件
- **依赖**: Python ≥3.10, evdev ≥1.6, mcp ≥1.0, pydantic ≥2.0
- **环境**: 需要 `/dev/uinput` 写入权限（ACL 或 input 组）
- **平台约束**: Linux Wayland COSMIC，不引入任何 X11 依赖
