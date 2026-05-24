# Phase 2: 感知技术验证 Spike

> **目标**：写 P2 代码前，把截图、异步 D-Bus、坐标系对齐、光标可见性、AT-SPI2 现状五个关键未知数实测掉
> **时间**：1 天
> **平台**：当前机器（Linux Wayland COSMIC, 2560×1600）
> **前置**：P1 已完成，xdg-desktop-portal-cosmic 可用

---

## 为什么必须先做

P0 已确认 portal 截图 `interactive=false` 可行、AT-SPI2 覆盖率 ~5%。但 P2 的实际实现依赖四个 P0 没覆盖的细节：

1. **异步模型**：portal 是异步 `Request::Response` 信号，代码怎么写才对？
2. **坐标系**：截图像素坐标和 uinput 输入坐标是否 1:1？缩放/多屏是否脱钩？
3. **光标**：portal 截图是否包含鼠标光标？能识别 hotspot 吗？
4. **AT-SPI2 树**：P0 已扫过一次，P2 实现前用 `pyatspi` 重新验证可用 API

这四个问题的结论直接决定 P2 的架构和接口语义。不做 spike 就写代码 = 把假设写进 API。

---

## 验证清单

### 2.1 xdg-desktop-portal 异步模型

**验证点**：在 asyncio 环境下稳定调用 portal Screenshot，拿到 `file://` URI 并读取 PNG 数据。

```
需要验证的具体行为：
- 用 dbus-next（asyncio）能否完成 Request::Response 订阅
- 若 dbus-next 不可行，dbus-python + GLib 在 asyncio 线程池里的表现
- 从调用 Screenshot() 到拿到 Response 的端到端延迟（ms 级）
- 并发：连续 3 次调用是否都返回正确结果
- handle_token 唯一性管理（随机生成 vs 固定前缀）
- Response code=1（用户取消）和 code=2（其他终止）的实际触发场景
```

```python
# 验证脚本骨架（不要求跑通，当场调试）
import asyncio
# 方案 A: dbus-next
from dbus_next.aio import MessageBus
from dbus_next import Variant

async def test_portal_screenshot_dbus_next():
    bus = await MessageBus().connect()
    # 1. 内省 Screenshot 接口
    introspection = await bus.introspect(
        'org.freedesktop.portal.Desktop',
        '/org/freedesktop/portal/desktop'
    )
    # 2. 获取 proxy
    proxy = bus.get_proxy_object(
        'org.freedesktop.portal.Desktop',
        '/org/freedesktop/portal/desktop',
        introspection
    )
    screenshot = proxy.get_interface('org.freedesktop.portal.Screenshot')

    # 3. 构造唯一 token，预测 request path
    token = f"spike_p2_{id(asyncio.current_task())}"
    request_path = f"/org/freedesktop/portal/desktop/request/{bus.unique_name[1:].replace('.','_')}/{token}"

    # 4. 先订阅 Response 信号，再发 Screenshot 调用
    # (关键：避免 race condition)
    # ...

    print(f"Portal screenshot URI: ...")
    print(f"Elapsed: ... ms")
```

**判定标准**：

| 结果 | 含义 |
|:----:|------|
| ✅ dbus-next 能完整走通 screenshot → Response → 读文件 | dbus-next 作为 P2 异步方案 |
| ⚠️ dbus-next 有阻塞问题 | 试 dbus-python + asyncio 线程池 |
| ❌ 两种都不可靠 | 考虑同步阻塞截图（仅 portal 部分），接受延迟 |

---

### 2.2 截图像素坐标与输入坐标对齐

**验证点**：portal 截图的像素坐标系和 uinput 输入坐标系是否是同一个空间。

```
需要验证的具体行为：
- 截图尺寸 (w,h) 是否始终等于 KMS 检测的尺寸
- uinput move_abs(100,100) 后截图，光标所在像素是否确实是 (100,100)
- 如果有缩放因子（fractional scaling），截图像素和输入坐标的比例关系
- 窗口模式下截图区域和全屏截图区域的关系
- 连续 10 次 move_abs + 截图，观察光标位置偏移是否稳定在 ≤20px
```

```python
# 验证脚本骨架
# 1. 启动 MCP server（已有 uinput）
# 2. 全屏截图 → 记录尺寸
# 3. move_abs(200, 200) → 延时 → 全屏截图
# 4. 目视或程序检测光标在截图的大致位置
# 5. 重复 5 个不同坐标点
# 6. 对比 KMS 尺寸 vs 截图尺寸
```

**判定标准**：

| 结果 | 含义 |
|:----:|------|
| ✅ 截图尺寸 = KMS 尺寸，且输入坐标与截图像素误差 ≤20px | 坐标系 1:1，P2 可直接用截图坐标做视觉校准 |
| ⚠️ 尺寸一致但光标位置有固定偏移 | 需加 offset 校准常数 |
| ❌ 尺寸不一致或有缩放因子 | P2 必须建坐标映射层，不能假设 1:1 |

---

### 2.3 截图中光标可见性

**验证点**：xdg-desktop-portal-cosmic 的截图是否包含鼠标光标指针。

```
需要验证的具体行为：
- 默认截图是否包含光标指针
- 如果有 cursor_mode 选项（portal v4+），不同 mode 下的表现
- 如果包含光标，光标 hotspot（实际点击点）和视觉指针尖端的偏移
- 如果包含光标，能否通过简单图像处理（模板匹配/色块检测）定位
- 在不同 cursor theme 下的表现（DMZ-white / Adwaita / Breeze）
- 特殊光标形状下是否也能识别（text/pointer/hand/resize）
```

```bash
# 快速探测
# 1. 手动截图并保存为 with_cursor.png
# 2. 截图前把光标移动到屏幕 (400,300)
# 3. 用 image viewer 打开截图，肉眼确认光标是否出现
# 4. 如果出现，光标尖端是否大致在 (400,300) 附近

# 程序探测（需要 Pillow）
python3 -c "
from PIL import Image
img = Image.open('/tmp/screenshot.png')
# 检查 (400,300) 附近 20×20 像素区域是否有明显的光标像素
region = img.crop((380, 280, 420, 320))
print(f'Cursor region size: {region.size}')
print(f'Dominant colors in cursor region: ...')
"
```

**判定标准**：

| 结果 | 含义 |
|:----:|------|
| ✅ 截图包含光标，且 hotspot 可识别 | P2 可做光标视觉校准（`screen_snapshot` 含 `cursor.source="detected"`） |
| ⚠️ 包含光标但识别不稳定 | 仅做 tracked cursor + low confidence，校准为 best-effort |
| ❌ 不包含光标 | P2 完全不承诺视觉校准，cursor 始终 `source="tracked"` |

> ⚠️ 这是 P2 架构的关键分叉点。如果截图不含光标，`screen_snapshot()` 的 cursor 字段只能标注 `source="tracked"` 且 `confidence="low"`。

---

### 2.4 临时文件生命周期与安全

**验证点**：portal 返回的 `file://` URI 的文件访问权限、持久性和清理行为。

```
需要验证的具体行为：
- URI 格式：file:///tmp/screenshot-XXXXXX.png 还是其他路径
- 文件权限（world-readable? 还是只有当前用户？）
- 文件是否在 portal session 结束后自动清理
- 多次截图是否覆盖旧文件还是创建新文件
- 文件系统 tmp 目录的可用空间（2560×1600 RGBA PNG ≈ 500KB-2MB/张）
- 高频截图（每 500ms 一张）下 /tmp 的 inode 消耗
```

```bash
# 快速探测
# 1. 取一次截图，记录 URI
# 2. ls -la <截图路径>
# 3. 检查文件权限、所有者
# 4. 手动 rm 后，再次截图是否正常
# 5. 连续 10 次截图，观察是否每次创建新文件
```

**判定标准**：

| 结果 | 含义 |
|:----:|------|
| ✅ 文件权限 0600 或 0644，可 copy 到私有目录 | 按正常安全流程处理 |
| ⚠️ 文件权限宽松（如 0777） | 必须立即 copy + 删除原文件 |
| ❌ 文件在截图后不可读 | 需检查 Documents portal 映射问题 |

**P2 安全约定（无论 spike 结果如何都执行）**：
- 截图后立即 copy 到进程私有临时目录（`/tmp/ai-gui-mcp/`）
- 不记录截图路径到日志
- `screen_snapshot()` 返回自己管理的文件 URI，不返回 portal 原始 URI
- 截图生命周期由 MCP server 管理，session 结束或超时后清理

---

### 2.5 AT-SPI2 树可用性（P2 实现前重新验证）

**验证点**：用 `pyatspi`（或 `dasbus`/`dbus-python`）在 COSMIC 上读取无障碍树，确认 P2 可用的 API 子集。

```
需要验证的具体行为：
- pyatspi 能否在此环境导入和使用（依赖 PyGObject/gi）
- Registry.getDesktop(0) 能否正常工作
- 对 COSMIC Settings、COSMIC Files、VS Code、Firefox 分别能拿到什么
- 能拿到哪些属性：name、role、states、bbox（Component.getExtents）、actions
- 树遍历性能：深度限制、节点数上限、超时设置
- a11y bus 是否默认启用（P0 发现默认 IsEnabled=false）
```

```python
# 验证脚本骨架
# 方案 A: pyatspi（如果 gi 可用）
import pyatspi
desktop = pyatspi.Registry.getDesktop(0)
for app in desktop:
    print(f"App: {app.name}")
    # 遍历子节点...

# 方案 B: dasbus（如果 gi 不可用但有 dasbus）
# ...

# 方案 C: dbus-python 直接调 AT-SPI2 DBus 接口
# ...
```

**判定标准**：

| 结果 | 含义 |
|:----:|------|
| ✅ pyatspi 可用，能拿到至少一个应用的 name/role/bbox | P2 使用 pyatspi 做 AccessibilityProvider |
| ⚠️ pyatspi 不可用但 dbus-python/dasbus 可以 | 封装轻量 AT-SPI2 客户端 |
| ❌ 三种都拿不到任何有价值数据 | P2 完全不集成 AT-SPI2，`screen_snapshot` 中 `accessibility.available=false` |

> 注意：P0 已确认 COSMIC 原生应用 AT-SPI2 近零覆盖。这个 spike 不是重新验证覆盖率，而是确认"如果未来有新应用支持 AT-SPI2，我们的代码能否正确读取树"。无论覆盖率如何，AT-SPI2 在 P2 中始终是 opportunistic 角色。

---

## Phase 2 Go/No-Go 判定

| 验证项 | 阻塞 P2？ | 说明 |
|--------|:---:|------|
| 2.1 异步模型 | **是** | 选不定异步方案，P2 的截图链路没法写 |
| 2.2 坐标对齐 | **是** | 坐标系不 1:1，P2 必须加映射层，架构要调 |
| 2.3 光标可见 | 否 | 影响 `cursor` 字段语义，但不阻塞截图功能 |
| 2.4 文件安全 | 否 | 安全约定可直接执行，不依赖 spike |
| 2.5 AT-SPI2 | 否 | 可选增强，不可用就跳过 |

### Go 条件
- 2.1 和 2.2 必须通过 → P2 可进入实现
- 2.3 的结果决定 `screen_snapshot()` 的 cursor 字段承诺级别
- 2.5 的结果决定是否包含 AccessibilityProvider

---

## P2 Spike 产出物

完成后记录一份简短结论，直接追加到本文档末尾：

```
Phase 2 Spike 结论
═══════════

2.1 异步模型:    ✅ 方案 X / ⚠️ 需调整 / ❌ 方案 Y
2.2 坐标对齐:    ✅ 1:1 / ⚠️ 有固定偏移 / ❌ 有缩放因子
2.3 光标可见:    ✅ 可见可识别 / ⚠️ 可见不稳定 / ❌ 不可见
2.4 文件安全:    按安全约定执行
2.5 AT-SPI2:    ✅ pyatspi 可用 / ⚠️ 需替代库 / ❌ 不再集成

P2 Go/No-Go:    GO / NO-GO — 理由
```
