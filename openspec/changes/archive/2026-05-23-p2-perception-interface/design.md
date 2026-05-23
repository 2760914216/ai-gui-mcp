## Context

P1 交付了 `InputBackend` 抽象 + `UInputBackend` 实现，提供鼠标键盘模拟。P2 需要在此基础上将感知能力（截图 → 结构化输出）加入到系统中。

当前 `server.py` 的 `_handle_screen_snapshot()` 直接 `from spike.p2_screenshot_dbus_python import capture_screenshot`——这是 spike 验证阶段的临时代码。spike/ 目录的全部脚本仅为 P2 技术验证而生，不是生产代码。

P2 Spike 已验证的关键结论：
- **dbus-python** 是唯一可用的 D-Bus 库（dbus-next 有 introspection bug）
- **截图延迟 ~53ms avg**，2560×1600 RGBA PNG ~833KB → base64 ~1.1MB
- **AT-SPI2 覆盖率 0%**：COSMIC compositor/apps 均不注册
- **光标不可见**：COSMIC 使用硬件 overlay，截图不含光标指针
- **坐标系 1:1**：截图像素 = uinput 输入坐标

## Goals / Non-Goals

**Goals:**
- 定义 `ScreenBackend` 抽象接口，作为生产级感知后端契约
- 实现 `XdgPortalBackend(ScreenBackend)`，基于 dbus-python + GLib 线程桥接
- 定义 `ScreenSnapshot` / `UIElement` / `CursorInfo` 数据模型，统一所有感知后端的出参
- 重构 `server.py` 的 snapshot handler：解耦 spike 代码，改为调用 `ScreenBackend.capture()`
- 保持 4-tool 结构（mouse/keyboard/screen/batch），`snapshot` action 留在 screen tool 中

**Non-Goals:**
- 不做 AT-SPI2 树集成（当前覆盖率 0%，但 `UIElement` 模型已预留字段）
- 不做窗口管理（`window_list`, `window_focus`——COSMIC compositor 不暴露该 D-Bus 接口）
- 不做差分截图（`screen_diff`——P2 阶段 AI 可直接对比两次 snapshot 返回值）
- 不做光标视觉校准（硬件 overlay 确认无法检测——`cursor.source` 始终为 `"tracked"`）
- 不修改 `InputBackend` 及其现有方法
- 不做区域截图 `observe`（可后续加，不阻塞 P2 核心交付）

## Decisions

### 决策 1：ScreenBackend 独立于 InputBackend

**选择**：`ScreenBackend` 作为独立的抽象类，与 `InputBackend` 平级，不合并。

```
src/backends/
├── base.py       ← InputBackend（不变）
├── uinput.py     ← UInputBackend（不变）
├── screen.py     ← 🆕 ScreenBackend 抽象接口
└── portal.py     ← 🆕 XdgPortalBackend 实现
```

**理由**：
- 职责分离：InputBackend 管"操作"，ScreenBackend 管"感知"。输入模拟（uinput 内核设备）和屏幕截图（D-Bus portal）是完全不同的技术栈。
- 跨平台扩展：Windows UIA、macOS AX API 都只需要加 `ScreenBackend` 子类，不影响 `InputBackend`。
- 残留问题：`InputBackend` 当前有 `screen_size()` 和 `get_cursor_position()`。这两个方法短期保留（P1 依赖它们），长期当 `ScreenBackend` 成熟后可考虑迁移。本次不改。

**替代方案考虑**：
- 并入 InputBackend：简单但不干净。一个类同时操作 uinput 设备文件和 D-Bus portal 连接，违反单一职责。
- 不做抽象直接实现：省事但堵死扩展。以后加 GNOME AT-SPI2、Windows UIA、视觉识别都得重构调用方。

### 决策 2：capture() 返回 ScreenSnapshot 而非原始 bytes

**选择**：`ScreenBackend.capture() -> ScreenSnapshot`，其中 `ScreenSnapshot` 是 pydantic 模型。

```python
class ScreenSnapshot(BaseModel):
    screen: ScreenInfo                 # {width, height}
    cursor: CursorInfo                 # {x, y, source}
    screenshot: str | None             # base64 PNG
    elements: list[UIElement]          # 可能为空
    source: Literal["screenshot", "accessibility", "vision"]
```

**理由**：
- 调用方（server.py）不需要知道后端细节。它只拿到 `ScreenSnapshot`，序列化为 JSON 返回给 AI。
- `source` 字段告诉 AI "这个感知结果从哪来的"——`"screenshot"` 意味着裸图（COSMIC），`"accessibility"` 意味着有结构化元素（GNOME/Windows），`"vision"` 意味着视觉识别后的结果（P3）。
- `UIElement` 字段预留了无障碍树和视觉识别都需要的数据（id, role, name, bbox, confidence）。

**替代方案**：返回 `bytes` + 让 server 层自己拼 JSON → server 需要知道后端类型，紧耦合。

### 决策 3：dbus-python + GLib.MainLoop 线程桥接

**选择**：`XdgPortalBackend.capture()` 内部启动一个 daemon thread 运行 `GLib.MainLoop`，通过全局状态变量传递结果。

```python
# portal.py 核心模式
def capture(self) -> ScreenSnapshot:
    result_holder = {}  # mutable container for thread result
    def dbus_thread():
        # connect, subscribe signal, call Screenshot, run GLib.MainLoop
        result_holder["data"] = ...
    t = threading.Thread(target=dbus_thread, daemon=True)
    t.start()
    t.join(timeout=10.0)
    return ScreenSnapshot(...)
```

**理由**：
- dbus-python 依赖 GLib 事件循环，无法直接嵌入 asyncio
- MCP server 本身基于 asyncio（`@app.call_tool()`），但 handler 函数可以是同步的——`_handle_screen_snapshot()` 在 asyncio 上下文中以同步方式运行，线程 `join()` 不阻塞事件循环
- spike 已验证 5/5 成功，无死锁，10s 超时保护有效
- 不侵入 `InputBackend`（全同步），不修改 MCP server 的事件模型

**替代方案**：
- asyncio + dbus-next：dbus-next 有 `power-saver-enabled` introspection bug，实际不可用
- 同步阻塞（整个 server 卡在 GLib 循环）：会阻塞 MCP 其他 tool 调用，不可接受

### 决策 4：snapshot 留在 screen tool，不拆新 tool

**选择**：`screen` tool 的 action 枚举从 `["size", "cursor", "snapshot"]` 保持，后续可加 `"observe"`。不拆 `perception` 或 `capture` tool。

**理由**：
- 保持 4-tool 结构（AGENTS.md 明确约定最小工具面）
- screen 的三个 action 语义连贯：`size`（查尺寸）→ `cursor`（查光标）→ `snapshot`（看屏幕）
- 如果未来 action 超过 6 个再考虑拆分，P2 阶段不需要

### 决策 5：临时文件安全策略

**选择**：portal 返回 `file://` URI 的截图文件，读取后立即 base64 编码到内存。不复制文件到私有目录（因为 base64 已在内存中，文件仅用于读取时刻）。

**理由**：
- portal 截图文件位于 `/tmp/screenshot-XXXXXX.png`，权限由 portal 管理（通常 0600）
- 读取 → base64 编码 → 返回 JSON 后，文件内容已在 MCP 响应中。后续 `screen_snapshot()` 调用会产生新文件。
- P2-SPIKE.md 的安全约定（copy 到 `/tmp/ai-gui-mcp/`）被简化：既然不缓存文件，就不需要私有目录。

**风险**：高频率截图可能堆积 `/tmp` 文件 → 由 portal 自身管理（通常使用固定模板文件名覆盖，或由 tmpfiles 清理）。不在此次范围内处理。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| **dbus-python 是 system package**（非 pip 可安装）→ 用户环境可能没有 | pyproject.toml 不声明 `dbus-python` 为依赖；`XdgPortalBackend.__init__()` import 时若失败则抛出清晰的错误信息：`"dbus-python not available. Install via: sudo apt install python3-dbus"` |
| **GLib 线程桥接在边缘情况可能死锁** | 10s 超时 + daemon thread（主进程退出时自动清理）。spike 5/5 成功无死锁，但生产环境长期运行需观察 |
| **base64 payload ~1.1MB** 通过 stdio 传输可能阻塞 | spike 实测 base64 encode 仅 0.8ms，传输预估 <50ms。MCP stdio 是本地管道，非网络。若将来出现阻塞，可评估 JPEG 压缩或分辨率缩放 |
| **`ScreenBackend` 和 `InputBackend` 有重叠状态**（cursor position, screen_size） | 短期：`InputBackend` 保持现有方法，`ScreenBackend` 不查询光标。`_handle_screen_snapshot()` 从 `InputBackend` 读 cursor，从 `ScreenBackend` 读截图，在 server 层拼装。长期：P3 可引入共享 `SystemState` |
| **AT-SPI2 0% → elements 始终为空 → 当前 AI 只能用裸截图** | 这是现实，非 P2 问题。`elements=[]` 和 `source="screenshot"` 诚实告知 AI 当前能力边界。结构化感知留给 P3 视觉识别 |
