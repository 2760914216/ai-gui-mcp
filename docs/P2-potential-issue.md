# Phase 2 潜在问题分析

> 基于 Phase 0 Spike 实测数据 + Phase 1 代码库现状 + Phase 2 规划文档的交叉分析
> 
> 创建日期：2026-05-23

---

## 全景图

```
┌──────────────────────────────────────────────────────────────────┐
│                        P1 (已完成)                                 │
│                                                                   │
│  ┌─────────┐   ┌──────────┐   ┌───────┐   ┌──────────┐         │
│  │  mouse  │   │ keyboard │   │ screen│   │  batch   │         │
│  └────┬────┘   └────┬─────┘   └───┬───┘   └────┬─────┘         │
│       └──────────┴───────────┴──────────┘                       │
│                        │                                          │
│              InputBackend (抽象)                                   │
│                        │                                          │
│              UInputBackend (uinput 实现)                           │
│              内部坐标跟踪 (0,0) ← ⚠️ 盲的                          │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      P2 (计划中)                                   │
│                                                                   │
│  原设计:                                                          │
│  ┌─────────────────────┐     ┌─────────────────────┐             │
│  │   AT-SPI2 无障碍树   │     │   截图 (xdg-portal)  │             │
│  │   (主力 80%)         │     │   (辅助 20%)         │             │
│  └─────────────────────┘     └─────────────────────┘             │
│                                                                   │
│  现实 (Phase 0 Spike):                                            │
│  ┌─────────────────────┐     ┌─────────────────────┐             │
│  │   AT-SPI2 覆盖率     │     │   截图 (xdg-portal)  │             │
│  │   ~5% (仅 WebKit)   │     │   必须承担 ~95%      │             │
│  └─────────────────────┘     └─────────────────────┘             │
└──────────────────────────────────────────────────────────────────┘
```

**核心矛盾**：原计划 Phase 2 的感知主力是无障碍树，视觉只是兜底。Phase 0 Spike 实测发现 AT-SPI2 在 COSMIC 上覆盖率仅 ~5%（仅 WebKit 沙箱进程有树，COSMIC compositor/settings/panel 全部零覆盖）。这意味着 Phase 2 的设计前提已经被推翻。

---

## 问题 1：`screen_snapshot()` 设计前提崩塌 🔴

### 现状

原设计输出结构：

```json
{
  "method": "accessibility_tree",
  "screen": {"width": 1920, "height": 1080},
  "elements": [
    {"id":"e1","role":"push_button","name":"保存","bbox":[100,50,200,80],
     "states":["enabled","visible","focusable"],"parent":"e0"},
    {"id":"e2","role":"text","name":"搜索...","bbox":[300,30,500,55],
     "states":["editable","visible","focused"]}
  ],
  "annotated_screenshot": "<base64 PNG with SoM overlays>"
}
```

这个结构假设无障碍树是**主力数据源**（elements 数组丰富），annotated_screenshot 是**辅助视觉参考**。

### Phase 0 实测数据

| 应用 | 树可用 | 名称/角色 | BBox | 备注 |
|------|:---:|:---:|:---:|------|
| COSMIC compositor | ❌ | ❌ | ❌ | 不在 AT-SPI2 bus |
| COSMIC Settings | ❌ | ❌ | ❌ | 不在 AT-SPI2 bus |
| COSMIC Panel Buttons | ❌ | ❌ | ❌ | 不在 AT-SPI2 bus |
| VS Code | ❌ | ❌ | ❌ | 不在 AT-SPI2 bus |
| WebKit WebProcess | ✅ | ❓ | ❓ | 唯一注册的应用 |

**覆盖率：~5%**

### 后果

如果绝大多数应用没有无障碍树，`screen_snapshot()` 返回的 `elements` 数组在大多数情况下是**空数组**。此时：

- AI 只能依赖 annotated_screenshot 来理解界面
- 但 SoM overlay（Set-of-Mark，在截图上标注可交互元素）本身依赖无障碍树或视觉识别来生成标注框
- 没有无障碍树 → 没有 bbox → 无法生成 SoM overlay → annotated_screenshot 退化为普通截图

```
                     ┌──────────────────┐
                     │ screen_snapshot() │
                     └────────┬─────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │ AT-SPI2 路径     │             │ 视觉识别路径     │
    │ (覆盖率 ~5%)     │             │ (需要 Phase 3)   │
    │                  │             │                  │
    │ elements: [...]  │             │ 当前不可用        │
    │ bbox: 有         │             │                  │
    └─────────────────┘             └─────────────────┘
              │                               │
              └───────────┬───────────────────┘
                          ▼
              ┌─────────────────────┐
              │  95% 的情况下       │
              │  elements = []      │
              │  SoM overlay = 无法生成│
              │  = 退化到纯截图      │
              └─────────────────────┘
```

### 需要决策

1. **方案 A：接受退化** — `screen_snapshot()` 在无树时返回空 elements + 纯截图，AI 自行理解截图
2. **方案 B：视觉降级** — `screen_snapshot()` 内置简单的视觉识别（边缘检测/色块分割），生成粗粒度的 SoM overlay
3. **方案 C：推迟 semantic 感知** — P2 只做截图 + 窗口管理 + 差分，不做元素级别的结构化感知；语义感知留给 P3
4. **方案 D：P2/P3 合并或并行** — 承认视觉识别是硬需求，将 Phase 3 视觉能力提前与 P2 并行开发

---

## 问题 2：光标定位是盲的 → 需要校准协议 🟡

### 现状

P1 的 UInputBackend 内部维护 `_x, _y` 坐标：

```python
class UInputBackend(InputBackend):
    def __init__(self, ...):
        self._x = 0
        self._y = 0
        logger.warning("Cursor position unknown, assuming (0,0)")
```

每次 server 启动时坐标归零。Wayland 不暴露全局光标位置，所以 `get_cursor_position()` 返回的是内部推算值，不是系统真实坐标。

### P2 的矛盾

P2 需要：
- 截图中标注光标位置 → 需要知道光标在截图坐标系中的真实坐标
- 点击操作后验证"我点了哪里" → 需要屏幕坐标和输入坐标一致

但 P1 给的：
- `_x, _y` 从 (0,0) 开始累计相对位移 → 存在累积误差
- 物理鼠标移动 → 内部坐标完全失效
- server 重启 → 坐标归零

```
  P1 内部 (_x,_y)          P2 截图坐标
  ┌──────────┐            ┌──────────┐
  │ 基于相对  │    ──?──▶  │ 基于像素  │
  │ 位移推算  │   没有校准  │ 绝对坐标  │
  │ 累积误差  │            │ 准确      │
  └──────────┘            └──────────┘
```

### 可能的方案

**校准协议**：server 启动后，AI 执行一次校准流程——
1. 截图获取屏幕尺寸
2. 移动光标到 (0,0)（左上角）
3. 再移动到 (width, height)（右下角）
4. 截图验证光标确实在预期位置
5. 建立内部坐标与屏幕坐标的映射

但这引入了一个**鸡生蛋问题**：校准本身依赖 cursor 操作和截图能力，而这些是 P1+P2 正在构建的。AI 需要有一个"bootstrap"流程。

### 更根本的问题

即使校准成功，以下场景也会破坏校准：
- 用户移动了物理鼠标
- 多显示器配置变化
- 分辨率热切换（外接显示器）

P2 的 `screen_snapshot()` 可以考虑每次截图时顺便做一次微校准（检测光标在截图中的位置，更新内部状态）。

---

## 问题 3：D-Bus 异步模型入侵 🟡

### 现状

P1 的代码是**全同步**的：

```python
# 所有操作都是同步调用
backend.move_abs(100, 200)  # 立即返回
backend.click()               # 立即返回
backend.screen_size()         # 立即返回
```

没有任何异步框架、事件循环、或回调机制。

### P2 的需求

xdg-desktop-portal 截图使用 D-Bus 异步协议：

```
┌──────────┐  Screenshot()    ┌──────────────┐
│  Client   │ ───────────────▶ │  xdg-portal   │
│  (我们的) │                  └──────────────┘
│           │  Response 信号     (异步返回)
│           │ ◀───────────────── file:///tmp/xxx.png
│           │
│  需要 GLib mainloop 或 asyncio event loop
│  来订阅并等待 Response 信号
└──────────┘
```

SPIKE-RESULTS.md 已确认：
- `dbus-python` + GLib mainloop 可以正常工作
- `interactive=false` 时无用户弹窗，生产级可用
- 但需要 GLib mainloop 订阅异步 `Response` 信号

### 架构影响

这不仅是"加一个依赖"的问题，而是影响整个 server 的执行模型：

| 决策项 | 选项 | 影响 |
|--------|------|------|
| 事件循环 | `GLib.MainLoop` | 引入 GLib 依赖，与 Python asyncio 生态不兼容 |
| 事件循环 | `asyncio` + dbus-next | 纯 Python 方案，但 dbus-next 成熟度不如 dbus-python |
| 混合 | `asyncio` + 线程池桥接 dbus-python | 复杂度高，但保持 P1 风格 |
| ScreenBackend 接口 | 同步（内部阻塞等信号） | 简单但阻塞 MCP server |
| ScreenBackend 接口 | 异步（async/await） | 需要 InputBackend 也改为异步以保持一致性 |

### 建议

先做一个 P2 专属的 mini-spike，验证：
1. `dbus-python` 在 asyncio 线程池中的可行性
2. 或者直接用 `dasbus`（尽管它依赖 `gi`，需实测确认是否真的有问题）
3. 或者用 dbus-next（纯 Python asyncio D-Bus 实现）

---

## 问题 4：工具面膨胀 vs 最小工具面哲学 🟡

### 现状

AGENTS.md 明确约定：

> 15+ 细粒度 tool 会造成 AI 选择困难。本项目采用 3-4 个大 tool + action 参数的设计。

P1 实现了 4 个 tool：mouse / keyboard / screen / batch

### P2 新增能力

| 能力 | 描述 | 可能的归属 |
|------|------|-----------|
| `screen_snapshot()` | 截图 + 无障碍树 + 窗口列表 | screen（扩展） |
| `screen_observe(region?)` | 区域截图（可带坐标标尺） | screen（扩展） |
| `screen_diff()` | 差分截图（仅返回变化区域） | screen（扩展） |
| `window_list` | 枚举所有窗口 | 新 tool? screen? |
| `window_focus(title)` | 聚焦指定窗口 | 新 tool? screen? |
| `element_find(description)` | 无障碍树中搜索元素 | 新 tool? screen? |

### 如果全放 screen 里

```
screen action enum 膨胀:
  P1: size, cursor                    ← 2 个
  P2: snapshot, observe, diff,        ← +6 个
      window_list, window_focus,
      element_find
  ─────────────────────────────────
  总计: 8 个 action
```

而且语义混杂：
- `size` / `cursor` → 输入系统信息
- `snapshot` / `observe` / `diff` → 视觉感知
- `window_list` / `window_focus` → 窗口管理
- `element_find` → 无障碍树查询

### 如果拆 tool

```
方案 A: 保持 4 tool，扩大 screen
  mouse / keyboard / screen(8 actions) / batch
  
方案 B: 拆出 perception tool  
  mouse / keyboard / screen(size,cursor) / perception(snapshot,observe,diff,window*,element*) / batch
  
方案 C: 按功能域拆分
  mouse / keyboard / screen(size,cursor) / capture(snapshot,observe,diff) / window(list,focus) / element(find) / batch
```

### 考量

- **方案 B** 最符合"最小工具面"哲学：4 个 tool 变 5 个（mouse/keyboard/screen/perception/batch）
- 但 perception tool 自身 action 就 6 个，内部也需要路由
- 而且 window_focus 本质是输入操作（调用 compositor 切换窗口），不是纯感知
- element_find 和 screen_snapshot 的输出有关联（都在操作无障碍树），放一起合理

---

## 问题 5：ScreenBackend 与 InputBackend 边界 🟡

### 现状

P1 的 `InputBackend` 已经包含了一些屏幕相关的方法：

```python
class InputBackend(ABC):
    # 鼠标操作
    def move_abs(x, y): ...
    def click(): ...
    
    # 键盘操作  
    def type_text(text): ...
    
    # ⚠️ 屏幕相关（这些属于 InputBackend 还是 ScreenBackend?）
    def screen_size() -> ScreenSize: ...
    def get_cursor_position() -> tuple[int, int]: ...
```

### P2 的 ScreenBackend

P2 需要新增：

```python
class ScreenBackend(ABC):
    def capture() -> bytes: ...                    # 截图
    def capture_region(x, y, w, h) -> bytes: ...   # 区域截图
    def get_accessibility_tree() -> ...: ...        # 无障碍树
    def list_windows() -> ...: ...                  # 窗口列表
    def focus_window(title) -> ...: ...             # 聚焦窗口
    def diff(previous, current) -> ...: ...         # 差分
```

### 边界问题

```
        screen_size() 属于谁？
        ┌──────────────┴──────────────┐
        ▼                             ▼
  InputBackend                  ScreenBackend
  "屏幕尺寸影响                "屏幕尺寸是
   输入坐标范围"               感知的基础参数"
   
        get_cursor_position() 属于谁？
        ┌──────────────┴──────────────┐
        ▼                             ▼
  InputBackend                  ScreenBackend
  "光标位置影响                "截图需要标注
   鼠标操作的起点"             光标位置"
```

### 可能的重构方向

```
方案 A: 保持现状 + 新增 ScreenBackend
  InputBackend 继续持有 screen_size / cursor_position
  ScreenBackend 从 InputBackend 获取这些信息
  → 两个 Backend 之间有依赖关系

方案 B: 提取共享 SystemInfo
         ┌──────────────────┐
         │   SystemInfo     │  ← 新增：共享的系统状态
         │  - screen_size   │
         │  - cursor_pos    │
         └───┬──────────┬───┘
             │          │
    ┌────────▼──┐  ┌───▼──────────┐
    │InputBackend│  │ScreenBackend │
    │ (uinput)   │  │ (xdg-portal) │
    └────────────┘  └──────────────┘
  → 但增加了一个新抽象层

方案 C: 合并为一个 Backend
  把屏幕相关能力都放进 InputBackend，不建 ScreenBackend
  → 违反单一职责，InputBackend 变得臃肿
```

### 另一个实际问题

`window_focus(title)` — 这算输入还是感知？

- 它通过 compositor 协议切换窗口 → 像输入操作
- 但它需要先"感知"有哪些窗口 → 像感知操作
- 在 P1 中，没有窗口管理能力
- 在 P2 中，`window_list` + `window_focus` 是配套的

也许应该放进 ScreenBackend，因为它依赖 D-Bus / compositor 接口，和 uinput 的输入模拟不是同一个技术栈。

---

## 问题 6：测试策略 🟡

### P1 测试策略（成功）

```python
@patch('src.backends.uinput.UInput')
def test_click(mock_uinput):
    backend = UInputBackend()
    backend.click()
    # 验证 mock 收到了正确的 write() 调用
```

策略：mock `evdev.UInput`，不依赖 `/dev/uinput` 设备。简单、可重复、CI 友好。

### P2 面临的测试挑战

| 测试目标 | Mock 难度 | 说明 |
|----------|:---:|------|
| 截图返回 | 🟢 容易 | mock 返回固定 PNG bytes / 文件路径 |
| AT-SPI2 树结构 | 🟡 中等 | 需要构造复杂的嵌套元素结构，但可行 |
| xdg-portal D-Bus 交互 | 🔴 困难 | 需要 mock D-Bus 连接、方法调用、信号订阅 |
| 差分截图算法 | 🟡 中等 | 需要真实/模拟的图片数据 |
| 光标校准协议 | 🔴 困难 | 涉及截图+鼠标+坐标的多步骤交互 |
| 窗口列表 | 🟡 中等 | 需要 mock compositor 响应 |

### 建议

1. **分层测试**：
   - 单元测试：mock 所有外部依赖（D-Bus, AT-SPI2, 文件系统）
   - 集成测试：需要真实 Wayland 环境（本地开发用，CI 可跳过）
   
2. **为 D-Bus mock 做准备**：
   - 把 D-Bus 交互封装在独立的方法中（如 `_call_screenshot_portal()`）
   - 测试时 mock 这些方法，验证参数传递和返回值处理
   
3. **差分算法**：
   - 用固定的测试图片对（before.png / after.png）
   - 验证 diff 输出的正确性

---

## 问题 7：config.yaml 扩展 🟢

### 现状

```yaml
# 当前 config.yaml — 只有 input 部分
input:
  backend: uinput
  uinput:
    resolution_x: 1920
    resolution_y: 1080
```

### P2 需要的配置

```yaml
input:
  backend: uinput
  uinput:
    resolution_x: 1920
    resolution_y: 1080

# P2 新增
perception:
  screenshot:
    method: xdg-desktop-portal     # 截图后端
    format: png                     # png / jpeg
    quality: 90                     # jpeg 质量 (仅 jpeg)
    tmp_dir: /tmp/ai-gui-mcp       # 截图临时目录
    
  accessibility:
    enabled: true                   # 是否启用 AT-SPI2
    backend: at-spi2                # 或 dasbus / dbus-python
    timeout_ms: 5000                # 树获取超时
    
  screen_diff:
    algorithm: pixel                # pixel / perceptual_hash / ssim
    threshold: 0.05                 # 变化检测阈值
    
  window:
    include_minimized: false        # 是否包含最小化窗口
    max_results: 100                # 窗口列表最大数量
```

### 配置模块需要增强

当前 `config.py`：
- 只有 `_deep_get(d, key_path, default)` 辅助函数
- `load_config()` 返回原始 dict，无验证
- 文件不存在时静默返回 `{}`

需要：
- pydantic 模型验证配置结构
- 合理的默认值
- 清晰的错误提示（缺少必填字段时）

---

## 问题优先级总览

```
紧急度
  ▲
  │  🔴 P1: screen_snapshot() 设计前提崩塌
  │        → 无障碍~5%时，返回什么？需要架构决策
  │        → 阻塞整个 P2 的方向
  │
  │  🟡 P2: 光标定位是盲的，需要校准协议
  │  🟡 P3: D-Bus 异步模型入侵
  │        → 技术阻塞点，不做就写不了代码
  │
  │  🟡 P4: 工具面膨胀 vs 最小工具面
  │  🟡 P5: ScreenBackend / InputBackend 边界
  │        → 设计决策，影响代码结构但不阻塞
  │
  │  🟡 P6: 测试策略
  │  🟢 P7: config.yaml 扩展
  │        → 可在开发过程中逐步解决
  └──────────────────────────────────────▶ 时间
```

---

## 建议的下一步

### 立即（开始 P2 前）

1. **决定 `screen_snapshot()` 的语义**（问题 1）— 这是所有后续工作的前提
2. **做 P2 mini-spike** — 验证 D-Bus 异步模型（问题 3）和光标校准（问题 2）
3. **决定 Backend 架构**（问题 5）— 定接口骨架

### 开发中解决

4. **决定工具面设计**（问题 4）— 可以边写边调整
5. **建立测试策略**（问题 6）— 与开发并行
6. **扩展 config.yaml**（问题 7）— 需要什么加什么

### 参考文档

- [ROADMAP.md](ROADMAP.md) — Phase 2 概述
- [SPIKE-RESULTS.md](SPIKE-RESULTS.md) — Phase 0 实测数据（AT-SPI2 覆盖率、截图可行性）
- [FUTURE-REFERENCE.md](FUTURE-REFERENCE.md) — 待确认技术选型
- [AI-GUI-MCP-ROADMAP-v2.md](AI-GUI-MCP-ROADMAP-v2.md) — P2 详细设计 + P3 并行建议
- [P1-potential-issue.md](P1-potential-issue.md) — P1 的问题记录（参考格式）
