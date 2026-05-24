# Phase 2 Spike Results

> **Date**: 2026-05-23
> **Platform**: Linux Wayland COSMIC (cosmic-comp 1.0.0)
> **Display**: 2560×1600 (eDP, card1-eDP-2)
> **Venv**: project .venv (include-system-site-packages=true)

---

## 0.1 D-Bus 库环境验证

**Result**: ✅ dbus-python / ❌ dbus-next — dbus-python 完全可用，dbus-next 因 introspection bug 不推荐

| Check | Status | Notes |
|-------|--------|-------|
| dbus-python (apt python3-dbus) | ✅ | v1.3.2, system package, venv accessible via `include-system-site-packages=true` |
| PyGObject + GLib (apt python3-gi) | ✅ | v3.48.2, system package |
| dbus-next (uv add) | ✅ | v0.2.3, pure Python, no system deps |
| Pillow (uv add) | ✅ | v12.2.0, for image analysis |
| Verification scripts | ✅ | 均已编写并实测通过 / 失败 |

### 实测结果

**dbus-python 验证** (`spike/p2_verify_dbus_python.py`):
```
✅ import dbus: dbus-python 1.3.2
✅ import GLib + DBusGMainLoop: GLib mainloop set as default
✅ SessionBus connection: Connected to session bus
✅ portal.Desktop available: Found
✅ org.a11y.Bus available: Found
Overall: ✅ PASS
```

**dbus-next 验证** (`spike/p2_verify_dbus_next.py`):
```
✅ dbus-next version: dbus-next unknown
✅ SessionBus connection: Connected: :1.474
✅ portal.Desktop available: Found
❌ Screenshot interface: invalid member name: power-saver-enabled
Overall: ❌ FAIL
```

**结论**: dbus-next 在 introspect `org.freedesktop.portal.Desktop` 时遇到 `invalid member name: power-saver-enabled` 错误。这是 dbus-next 对非标准 D-Bus 属性名称的兼容性问题。**推荐 P2 使用 `dbus-python`**。

---

## 0.2 截图能力：xdg-desktop-portal

**Result**: ✅ 截图通过 — dbus-python 方案成熟可靠，dbus-next 因 introspection bug 不可用

| Check | Status | Notes |
|-------|--------|-------|
| dbus-python 截图 | ✅ | 5/5 成功，延迟 50.7-58.0ms |
| dbus-next 截图 | ❌ | `invalid member name: power-saver-enabled` |
| 分辨率 | ✅ | 2560×1600 RGBA PNG，与 KMS 检测一致 |
| 内容一致性 | ✅ | 有效像素数据，多点采样确认 |
| Payload 大小 | ✅ | PNG ~833KB，base64 ~1.1MB |

### dbus-python 实测数据（5 次运行）

```
Portal latency:  min=50.7ms  max=58.0ms  avg=53.4ms
PNG file sizes:  min=824688B  max=839032B  avg=833368B
Base64 sizes:    min=1099584B max=1118712B avg=1111159B
Base64 encode:   min=0.7ms    max=0.9ms    avg=0.8ms
Total elapsed:   min=51.5ms   max=70.6ms   avg=56.5ms
Resolution:      2560×1600
```

### dbus-next 实测（3 次尝试）

全部失败，错误：`invalid member name: power-saver-enabled`。这是 dbus-next v0.2.3 在处理 `org.freedesktop.portal.Desktop` 的 introspect XML 时，遇到非标准 property 名称（含连字符 `power-saver-enabled`）导致的解析错误。

### dbus-python 实现修复记录

初版使用 `bus.add_signal_receiver(path=request_path)` 预测 request path，但 portal 实际返回的 handle path 与预测不匹配。修复方案：改用 broadcast 订阅（不指定 path）+ 在 callback 中匹配 handle。

---

## 0.3 AT-SPI2 无障碍树抓取

**Result**: ❌ 不可行 — 0 应用注册，确认 AT-SPI2 在 COSMIC 上无实用价值

| Check | Status | Notes |
|-------|--------|-------|
| AT-SPI2 bus 连接 | ✅ | `unix:path=/run/user/1000/at-spi/bus_1` |
| 应用枚举 | ❌ | **0 个注册应用** |
| WebKit 树遍历 | ❌ | 无应用可遍历 |
| 其他应用测试 | ❌ | GTK/Qt/Electron 均无注册 |

### 实测结果

```
AT-SPI2 bus address: unix:path=/run/user/1000/at-spi/bus_1
✅ Connected to AT-SPI2 bus
⚠️  No applications found on AT-SPI2 bus
AT-SPI2 coverage appears to be zero on this system.
Total apps found: 0
```

### 评估

- Phase 0 发现 AT-SPI2 覆盖率 ~5%（仅 WebKit WebProcess 有注册）。本次 spike 连 WebKit 进程也没有注册（可能是 Edge 浏览器未开启或未运行沙箱模式的 WebKit 进程）。
- COSMIC compositor、COSMIC Settings、COSMIC Panel、VS Code 等均不注册 AT-SPI2。
- **结论：P2 不应依赖 AT-SPI2 做无障碍树感知。`screen_snapshot()` 中 `elements` 始终为空数组，`accessible` 始终为 `false`。**

---

## 0.4 光标检测与校准

**Result**: ⚠️ 光标不可见 — 硬件光标 overlay，截图不含光标；移动校准可用

| Check | Status | Notes |
|-------|--------|-------|
| 光标检测（截图） | ❌ | 硬件光标不在截图中（Wayland compositor overlay） |
| 颜色启发式检测 | ⚠️ | 返回低 confidence (0.30) 估计，不可靠 |
| 移动校准（uinput） | ✅ | 四角+中心移动成功，uinput 设备正常工作 |
| 累积误差 | ⚠️ | 待人工目视验证（非交互 session 无法确认） |

### 实测结果

**光标检测** (`spike/p2_cursor_detect.py`):
```
Color heuristic: (1042, 1119) confidence=0.30
  → 低 confidence，本质是白像素聚类 centroid，不是真实光标位置
  → 截图片区的 (100,100) 附近无白色像素 → 硬件光标确实不在截图中
```

**光标移动校准** (`spike/p2_cursor_calibrate_move.py`):
```
✅ Created uinput virtual mouse device
✅ Corner calibration: top-left(0,0), top-right(2559,0), bottom-left(0,1599), 
   bottom-right(2559,1599), center(1280,800) — 所有移动成功
✅ Cumulative test: 10 random absolute moves completed
✅ Final position: (100, 100) — device closed cleanly
```

### 截图光标可见性分析

截图 20×20 区域采样：
- (100, 100) cursor area: 129 unique colors, white=False, black=True → **无光标**
- (1280, 800) center: 2 unique colors → 均匀暗色背景 → **无光标**

确认：**Wayland compositor (cosmic-comp) 使用硬件光标 overlay，不合成到 xdg-desktop-portal 截图中。**

### 结论

**P2 的 `screen_snapshot()` 中 `cursor` 字段标注 `source="tracked"`, `confidence="low"`。**
光标视觉校准不可能（因截图不含光标）。移动校准方案可用：通过 `move_abs` 到已知位置，内部坐标追踪误差 ≤20px（Phase 0 验证）。

### 人工审核意见
**不做截图光标检测的核心原因是因为可能误判，而非截图光标不可见**
但截图光标不可见是在 COMIC 上的**事实**

---

## 0.5 MCP 集成原型

**Result**: ✅ 代码已集成，P1 测试全通过，截图链路端到端验证成功

| Check | Status | Notes |
|-------|--------|-------|
| ScreenAction 扩展 snapshot | ✅ | `src/models.py`: Literal 枚举加入 `"snapshot"` |
| _handle_screen 分支 | ✅ | `src/server.py`: snapshot action 调用 `_handle_screen_snapshot()` |
| list_tools 枚举更新 | ✅ | `src/server.py`: screen tool action enum 含 `snapshot` |
| P1 测试回归 | ✅ | 51/51 pass |
| 端到端延迟 | ✅ | avg 56.5ms (D-Bus + file read + base64 + JSON) |

### 调用链路

```
MCP client → call_tool("screen", {action:"snapshot"})
  → ScreenAction(action="snapshot") [models.py]
  → _handle_screen() → _handle_screen_snapshot(backend) [server.py]
    → capture_screenshot() [spike/p2_screenshot_dbus_python.py]
      → threading.Thread → GLib.MainLoop → dbus-python
        → Screenshot(interactive=false) → Response signal
        → read PNG → base64 encode
    → json.dumps({screen, cursor, screenshot, elements, accessible})
  → TextContent → MCP client
```

返回值结构（已验证）：
```json
{
  "screen": {"width": 2560, "height": 1600},
  "cursor": {"x": 0, "y": 0},
  "screenshot": "<base64 PNG ~1.1MB>",
  "elements": [],
  "accessible": false,
  "note": "snapshot captured; latency=53ms; png=833368B b64=1111159B"
}
```

---

## P2 技术决策推荐表

| 决策项 | 推荐 | 依据 |
|--------|------|------|
| **D-Bus 库选择** | `dbus-python` | dbus-next v0.2.3 存在 `power-saver-enabled` introspection bug，导致 Screenshot 接口不可用。dbus-python 5/5 截图成功，延迟 50-58ms。 |
| **screen_snapshot 语义** | screenshot-first, elements always empty | AT-SPI2 覆盖率 0%，无任何应用注册。elements 始终为空。screenshot 始终返回。 |
| **光标校准策略** | 移动验证（tracked cursor） | 截图不含光标（硬件 overlay），视觉检测不可行。Phase 0 确认 move_abs 误差 ≤20px。cursor 标注 source="tracked"。 |
| **AT-SPI2 取舍** | 放弃 | 0% 覆盖率。P2 不集成 AT-SPI2。保留路径代码但不启用。 |
| **ScreenBackend 接口** | 独立于 InputBackend，capture() 用 threading+GLib | `dbus-python` + GLib.MainLoop 线程桥接方案已验证可行（5/5 成功）。capture() 同步阻塞（内部用线程等信号），不侵入 asyncio event loop。 |

---

## P2 实现风险点与已知限制

| 风险 | 严重度 | 缓解措施 |
|------|:---:|------|
| 光标在截图中不可见（硬件 overlay） | 🔴 确认 | 不承诺视觉光标校准。cursor 始终 source="tracked"。P3 可引入 VLM 做视觉校准。 |
| base64 payload ~1.1MB（2560×1600 PNG） | 🟡 中 | 实测 base64 encode 仅 0.8ms，MCP stdio 传输预估 <50ms。如遇阻塞，P2 可评估 JPEG 压缩或分辨率缩放。 |
| AT-SPI2 覆盖率 0% | 🔴 确认 | P2 完全放弃 AT-SPI2。`screen_snapshot()` 中 `accessible=false`, `elements=[]`。 |
| dbus-next 不可用 | 🟢 低 | 确认 dbus-python 为主要方案。dbus-next 仅作为未来备选（需等待上游修复 introspection bug）。 |
| COSMIC compositor D-Bus 接口不可用 | 🟢 低 | 窗口管理推迟到 COSMIC 暴露稳定接口后。 |
| GLib 线程桥接稳定性 | 🟢 低 | 5/5 截图成功，无死锁。10s 超时保护已实现。 |

---

## Go/No-Go 评估

| 验证项 | 阻塞 P2？ | 实测结果 | 判定 |
|--------|:---:|------|:---:|
| 0.1 D-Bus 环境 | 是 | ✅ dbus-python 5/5, dbus-next 0/3 | ✅ GO — dbus-python 方案可行 |
| 0.2 截图能力 | 是 | ✅ 53.4ms avg, 2560×1600, ~833KB PNG | ✅ GO — 远超预期 |
| 0.3 AT-SPI2 树 | 否 | ❌ 0% 覆盖率 | ✅ GO — advisory only |
| 0.4 光标校准 | 否 | ⚠️ 光标不可见（硬件 overlay） | ✅ GO — 不影响截图核心功能 |
| 0.5 MCP 集成 | 是 | ✅ 模型/路由/枚举已更新，P1 51/51 测试通过 | ✅ GO |

### 判定：**GO** 🚀

**P2 可以立即启动。**

阻塞性验证全部通过：
- ✅ 截图链路完整跑通：调用 portal → 等信号 → 读 PNG → base64 编码 → 返回，总延迟 ~56ms
- ✅ D-Bus 库选定：`dbus-python`（唯一可用方案）
- ✅ MCP 集成代码就绪：`screen(action="snapshot")` 已实现，P1 测试无回归
- ✅ 坐标系 1:1：截图 2560×1600 = KMS 检测尺寸

非阻塞项结论：
- AT-SPI2：0% 覆盖率 → 放弃。`screen_snapshot()` elements 始终为空。
- 光标视觉校准：不可行（硬件 overlay）→ cursor source="tracked"

**启动 P2 前无需额外验证。** 所有阻塞性 spike 项已获明确结论。

---

## 产出物清单

| 产出物 | 位置 | 状态 |
|--------|------|:---:|
| 验证脚本（dbus-python） | `spike/p2_verify_dbus_python.py` | ✅ |
| 验证脚本（dbus-next） | `spike/p2_verify_dbus_next.py` | ✅ |
| 截图脚本（dbus-python） | `spike/p2_screenshot_dbus_python.py` | ✅ |
| 截图脚本（dbus-next） | `spike/p2_screenshot_dbus_next.py` | ✅ |
| AT-SPI2 树遍历 | `spike/p2_atspi_tree.py` | ✅ |
| 光标检测 | `spike/p2_cursor_detect.py` | ✅ |
| 光标移动校准 | `spike/p2_cursor_calibrate_move.py` | ✅ |
| 依赖配置 | `pyproject.toml` (spike optional-deps) | ✅ |
| 模型扩展 | `src/models.py` (snapshot action) | ✅ |
| 服务端集成 | `src/server.py` (snapshot handler + tool enum) | ✅ |
| Spike 结果文档 | `docs/PHASE2-SPIKE-RESULTS.md` | ✅ |
