## Context

Phase 1（Action Layer）已完成，AI 可以通过 mouse/keyboard/screen/batch 四个 MCP tool 执行鼠标键盘操作。当前架构：

| 组件 | 文件 | 职责 |
|------|------|------|
| MCP Server | `src/server.py` | Tool 注册 + action 路由 |
| 数据模型 | `src/models.py` | pydantic 入参校验 |
| 抽象接口 | `src/backends/base.py` | `InputBackend` 抽象类 |
| uinput 实现 | `src/backends/uinput.py` | Linux 内核级输入模拟 |
| 配置 | `config.yaml` | 后端选择、分辨率 |

P1 的局限：
- **光标位置是盲的**：内部从 (0,0) 开始累计相对位移，物理鼠标移动或 server 重启后位置完全失效
- **无感知能力**：没有截图、无障碍树、窗口管理
- **全同步**：所有操作同步执行，无事件循环机制

Phase 0 Spike 实测数据（见 `docs/SPIKE-RESULTS.md`）：
- AT-SPI2 覆盖率仅 ~5%（仅 WebKit 沙箱进程有树，COSMIC 全家桶零覆盖）
- xdg-desktop-portal 非交互式截图可用（`interactive=false`），返回 2560×1600 RGBA PNG
- 截图需要 D-Bus 异步协议（订阅 `Response` 信号）

P2 替代方案分析文档 `docs/P2-potential-issue.md` 列出 7 个待解决问题，本 spike 需要验证其中 4 个技术阻塞点。

## Goals / Non-Goals

**Goals:**

1. **验证 D-Bus 异步模型**：确定适合本项目的 D-Bus 方案（`dbus-python` + GLib / `dasbus` / `dbus-next`），解决 P1 同步架构与异步截图的兼容问题
2. **实现截图原型**：通过 xdg-desktop-portal 获取全屏截图，转为 base64 PNG，通过 MCP `screen snapshot` action 返回
3. **实测 AT-SPI2 树抓取**：用直连 AT-SPI2 bus 的方式获取 WebKit 进程的元素树，确认能否拿到 bbox/role/name/states
4. **实现光标校准原型**：截图→检测光标像素位置→更新内部 `_x,_y`，验证校准协议的可行性
5. **形成 P2 决策文档**：输出 `docs/PHASE2-SPIKE-RESULTS.md`，包含每项 spike 的可选方案、实测数据、推荐选择

**Non-Goals:**

- 不实现完整的 Perception Layer（那是 P2 正式实现的工作）
- 不引入视觉识别模型（OmniParser、VLM 等）——属于 Phase 3
- 不做差分截图算法、窗口管理、`element_find` ——这些在 spike 结论中规划，由 P2 实现
- 不修改 `InputBackend` 接口 —— spike 仅新增 `ScreenBackend`，不动现有代码
- 不做 CI 集成或单元测试 —— spike 是探索性原型，在真实环境中手动验证

## Decisions

### 决策 1：D-Bus 异步模型选型

**待验证方案**：

| 方案 | 描述 | 优势 | 风险 |
|------|------|------|------|
| A: `dbus-python` + GLib.MainLoop（线程桥接） | 在 Python 线程中运行 GLib mainloop，asyncio 通过 `run_in_executor` 桥接 | Phase 0 已验证可用；`dbus-python` 最成熟 | 需要 GLib 依赖；线程间通信复杂度 |
| B: `dasbus` | Pythonic D-Bus 封装，宣称无 GObject 依赖 | 代码更简洁，asyncio 友好 | Phase 0 实测发现 import 时仍需 `gi`（PyGObject） |
| C: `dbus-next` | 纯 Python asyncio D-Bus 实现 | 无系统依赖，天然支持 asyncio | 成熟度不如 dbus-python；社区较小 |

**Spike 验证方法**：
1. 用方案 A 实现截图原型（已在 Phase 0 验证 D-Bus 调用可行）
2. 用方案 C 做对比测试（能否完成相同的截图调用？延迟差异？错误处理差异？）
3. 方案 B 仅在方案 A 和 C 都不满意时尝试

**默认倾向**：方案 A（`dbus-python` + GLib + asyncio 线程桥接），因为 Phase 0 已确认调用链路可行。

### 决策 2：`screen_snapshot()` 语义设计

**核心矛盾**：原设计假设 elements 数组丰富（AT-SPI2 覆盖率 80%），但现实是 ~5%。`screen_snapshot()` 在 95% 的情况下 elements 为空数组。

**Spike 阶段原型输出结构**：

```json
{
  "screen": {"width": 2560, "height": 1600},
  "cursor": {"x": 1280, "y": 800},
  "screenshot": "<base64 PNG>",
  "elements": [],
  "accessible": false,
  "note": "AT-SPI2 tree unavailable for this application. Fallback to visual-only mode."
}
```

关键字段说明：
- `screenshot`: **始终返回**（这是 spike 的核心验证目标）
- `elements`: AT-SPI2 获取的元素（spike 仅测 WebKit 进程，验证能否拿到结构化数据）
- `accessible`: 布尔值，指示当前焦点应用是否暴露了无障碍树
- `note`: 人类可读的状态说明，帮助 AI 理解当前感知能力

**Spike 验证内容**：
- 截图延迟（调用 portal → 文件落盘 → 读取 → base64 编码）
- base64 字符串大小（2560×1600 PNG 约 500KB → base64 约 670KB）
- 对 MCP 传输的影响（大 payload 是否导致 stdio 阻塞）
- AT-SPI2 元素数据结构的完整性（bbox 精确度、role/name 填充率）

### 决策 3：光标校准协议

**问题**：P1 内部坐标 (0,0) 与实际光标位置脱节，且存在累积误差。

**Spike 校准流程**：
```
1. 截图（获取屏幕像素数据）
2. 在截图中检测光标像素（基于颜色/形状特征）
3. 将检测到的像素坐标作为真实光标位置
4. 更新 InputBackend._x, _y 为真实值
```

**简化版（spike 原型）**：由于 COSMIC 下光标是标准主题且形状固定，假设：
- 光标在截图中可见（截图时正在屏幕中）
- 用模板匹配或边缘检测定位光标（不依赖 ML 模型）
- 作为备选，支持手动校准：AI 传 `cursor_calibrate(x=100, y=200)` → server 截图验证光标确实在那里 → 确认校准

**Spike 验证内容**：
- 光标在 xdg-portal 截图中是否可见（Wayland compositor 可能用硬件光标，不在此次截图中）
- 如果硬件光标不可见，回退到"move_abs 到已知位置 + 截图验证"的校准方案
- 校准后内部坐标与实际屏幕坐标的偏差

### 决策 4：ScreenBackend / InputBackend 边界

**当前状态**：`InputBackend` 包含 `screen_size()` 和 `get_cursor_position()`，它们本质是"屏幕状态"而非"输入操作"。

**Spike 原型设计**：

```
InputBackend（不改动）              ScreenBackend（新增）
├── move_abs / move_rel            ├── capture() → bytes
├── click / dbl_click / etc.       ├── capture_base64() → str
├── scroll / drag                  ├── get_tree() → Element[]
├── type_text / press_combo        ├── detect_cursor(screenshot) → (x, y)
├── screen_size()  ← 保留          ├── screen_size() ← 独立获取
├── get_cursor_position() ← 保留   └── list_windows() → 后续
└── close()                        └── close()
```

**关键设计约束**：
- `ScreenBackend` **不依赖** `InputBackend` — 独立获取屏幕信息
- `ScreenBackend.capture()` 是异步方法（`async def`），因为它依赖 D-Bus 事件循环
- `InputBackend` 保持全同步，不引入异步
- Server 层负责协调两个 backend：
  - `screen(action="snapshot")` → 调用 `ScreenBackend.capture()` + 可选 `InputBackend.get_cursor_position()`
  - 校准流程：`ScreenBackend.capture()` → `ScreenBackend.detect_cursor()` → 更新 `InputBackend` 内部状态

### 决策 5：工具面设计（原型阶段）

**Spike 阶段的 tool 扩展**：最小化侵入，仅在现有 `screen` tool 加一个 action。

```
P1 screen actions:          P2 spike 扩展:
├── size                    ├── size（不变）
└── cursor                  ├── cursor（不变）
                            └── snapshot（新增）— 截图 + 基础元数据
```

**不做的事**（留给 P2 正式设计）：
- 不新建 `perception` tool
- 不扩展 `screen` action enum 超过 3 个
- batch 中的 `screen snapshot` action 暂不处理（spike 只验证单次调用）

### 决策 6：测试策略

**Spike 阶段**：全部手动验证，不写自动化测试。因为：
- D-Bus mock 复杂度高，不值得在 spike 阶段投入
- Spike 的目的是"在真实环境里跑通"，mock 环境遗漏实际边界条件
- 验证通过后，选定的方案在 P2 正式实现时才建立测试基础设施

**验证方法**：每项 spike 一个独立脚本，放在 `spike/` 目录（如 `spike/p2_01_screenshot.py`），手动在真实 Wayland 环境中运行并记录输出。

## Risks / Trade-offs

### 风险 1：硬件光标在截图中不可见 → 阻止光标校准
- **Mitigation**：Phase 0 截图已验证成功（`file:///tmp/screenshot-xxx.png`）。如果截图不含光标，回退到"移动到已知位置 + 截图验证区域"的替代校准方案。最坏情况：P2 靠 `screen cursor` 返回内部坐标 + 警告提示，视觉校准推迟到 P3（引入 VLM 后）。

### 风险 2：D-Bus 线程桥接的死锁/超时
- **Mitigation**：spike 脚本设置 10 秒超时。如果 GLib mainloop 在 asyncio 线程池中阻塞，立即换 `dbus-next` 方案。Spike 结论直接决定 P2 的 D-Bus 库选型。

### 风险 3：base64 截图过大导致 MCP stdio 阻塞
- **Mitigation**：spike 中测量 payload 大小和传输延迟。如果 >500ms，评估压缩选项（JPEG、分辨率缩放）。不在此次 spike 中实现压缩——先测瓶颈再定方案。

### 风险 4：AT-SPI2 树获取在 spike 中仍然失败（即使之前发现有 WebKit 进程）
- **Mitigation**：承认 AT-SPI2 在 COSMIC 上无实用价值。`screen_snapshot()` 在 P2 设计为截图-first，elements 永远是 optional/best-effort。Spike 的 AT-SPI2 测试是"最后一搏"——如果能稳定拿到哪怕一个应用的树，就保留该路径；如果连 WebKit 树都是空的，则在 P2 设计中明确放弃 AT-SPI2。

## Open Questions

- Q1：`dbus-next` 在 COSMIC 环境下能否正常完成 xdg-desktop-portal Screenshot 调用？（延迟、错误处理对比）
- Q2：截图 base64 在 MCP stdio 上的实际传输延迟是多少？（2560×1600 PNG ~670KB base64）
- Q3：AT-SPI2 WebKit 进程树能拿到多完整的数据？（bbox 精度、role 填充率、children 嵌套深度）
- Q4：光标在截图中的检测准确率如何？（硬件光标 vs 软件光标，不同应用背景下的检测难度）
- Q5：`dasbus` 的 `gi` 依赖在 COSMIC 上是否实际可满足？（Phase 0 发现 import 报错，需确认是新版修复还是仍然有问题）
