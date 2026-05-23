## Context

Phase 0 Spike 已完成并归档。在 Linux Wayland COSMIC (cosmic-comp 1.0.0, 2560×1600) 上验证：
- uinput 鼠标注入 ✅ — 相对移动（`EV_REL`）可行，点击事件被接收
- uinput 键盘注入 ✅ — 按键/组合键/文本输入均被应用接收
- 分辨率检测 ✅ — KMS/sysfs (`/sys/class/drm/card1-eDP-2/modes`) 提供 2560×1600
- 坐标追踪 ✅ — 内部相对移动追踪误差 ≤20px，cosmic-comp 无指针加速干扰

当前代码库是空白状态：`src/`、`pyproject.toml`、`config.yaml` 均不存在。

这是一个新项目的第一阶段实现。虽然只有一个后端实现，但架构上必须支持后续扩展（P2 截图、P5 跨平台）。

## Goals / Non-Goals

**Goals:**
- 通过 MCP stdio transport 暴露 mouse/keyboard/screen/batch 四个 tool
- uinput 内核级输入模拟，支持鼠标（移动/点击/拖拽/滚动）和键盘（打字/组合键/按键按下释放）
- 在 Wayland COSMIC 环境下可靠工作（不依赖 X11）
- `InputBackend` 抽象接口从第一天就存在，为后续后端替换铺垫
- 自动检测屏幕分辨率（KMS/sysfs），含手动配置回退
- 内部坐标追踪（Wayland 无法读取全局光标位置）
- 坐标边界 clamping，越界操作返回错误

**Non-Goals:**
- ❌ 截图/视觉能力 — 这是 P2 的内容
- ❌ AT-SPI2 无障碍树 — P2
- ❌ 类人交互行为（贝塞尔轨迹、变速移动）— P4
- ❌ 多平台支持（Windows/macOS）— P5
- ❌ X11 方案 — 本项目仅 Wayland
- ❌ 多显示器 — 单显示器环境
- ❌ MCP transport 除 stdio 外的其他方式

## Decisions

### D1: 4-Tool + action 参数设计

**选择**: mouse/keyboard/screen/batch 四个 tool，操作类型通过 `action` 参数区分

**备选**: 15+ 细粒度 tool（如 `move_mouse`、`click_mouse`、`type_text` 等）

**理由**:
- 减少 AI 选择困难（AGENTS.md 明确要求 3-4 个大 tool）
- action 参数在 MCP tool schema 中天然支持 discriminated union
- batch tool 解决多次往返问题，AI 可一次发送多个操作
- 参考了项目早期用户反馈：工具面过大导致 AI 行为不稳定

### D2: InputBackend 抽象接口从 P1 开始

**选择**: 在 P1（仅一个 uinput 实现）就建抽象接口

**备选**: P1 直接写 uinput，等 P2 或 P5 时再抽抽象层

**理由**:
- 接口定义本身就是文档 — 明确输入后端的契约
- P2 加截图后端、P5 跨平台时只需加新实现类，不改调用方
- 建抽象层的边际成本极低（一个 ABC 类 + 10 个方法签名）
- 符合项目架构原则"后端可替换"

### D3: uinput 相对移动 + 内部坐标追踪

**选择**: 使用 `EV_REL` 相对移动 + 内部追踪 `_x, _y` 变量，`move_abs` 转换为 `move_rel(dx, dy)`

**备选**: 使用 `EV_ABS` 绝对坐标

**理由**:
- uinput `EV_ABS` 需要配置触控板/触摸屏参数（min/max/resolution），与真实鼠标行为不符
- 相对移动是最通用的方式，所有平台后端都可以实现
- Spike 0.4 验证了追踪误差 ≤20px，满足 GUI 操作精度需求
- cosmic-comp 不应用指针加速，不会引入额外漂移

### D4: KMS/sysfs 分辨率检测

**选择**: 主路径 KMS/sysfs（解析 `/sys/class/drm/card*/status` + `modes`），回退 `config.yaml` 手动配置

**备选**: wlr-randr, COSMIC DBus interface

**理由**:
- wlr-randr 未安装在此环境
- COSMIC DBus `com.system76.CosmicComp` 不可用（"The name is not activatable"）
- KMS/sysfs 是唯一不需要额外安装包、不需要交互授权、在非交互 session 中可用的方案
- 作为内核接口，KMS 跨 compositor 通用性最好

### D5: stdio transport

**选择**: MCP transport 仅用 stdio

**理由**: 项目本地部署，AI 客户端在同一台机器上运行。stdio 是本地 IPC 最可靠的方式，无需网络端口管理、无需认证。

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| 内部坐标追踪长期漂移 | 鼠标点击偏移导致操作失败目标 | 每次 `move_abs` 前计算增量，P2 引入截图校验 |
| `/dev/uinput` ACL 被重置 | 失去写入权限，所有操作失败 | 错误消息提示用户添加 `input` 组：`sudo usermod -aG input $USER` |
| uinput 设备名冲突 | 已有同名虚拟设备，创建失败 | 使用带前缀的唯一名称 `ai-gui-mcp-mouse/keyboard` |
| 分辨率检测失败（如 headless） | 无法自动获取屏幕尺寸 | 回退到 `config.yaml` 的 `screen.width/height` 手动配置 |
| KMS sysfs 路径在不同硬件上可能变化 | 自动检测逻辑找不到正确的 DRM 设备 | 遍历所有 `card*` 设备找首个 `connected` 输出，多设备时优先 `eDP` |
| pydantic v2 与 mcp SDK 潜在版本冲突 | 安装失败 | 在 pyproject.toml 中锁定最低版本，`uv lock` 验证依赖解析 |

## Open Questions

无 — 所有 P1 设计决策已通过 Spike 验证确认。
