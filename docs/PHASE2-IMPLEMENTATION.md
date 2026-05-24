# Phase 2: Perception Layer — 实现计划

> **前置**：P1 已完成，P2 Spike 全部通过
> **目标**：AI 能「看见」屏幕——截图采集 + 坐标/光标置信度 + 可选无障碍树增强
> **平台**：Linux Wayland COSMIC，xdg-desktop-portal + uinput
> **设计原则**：图像优先、语义兜底、最小工具面

---

## 0. P2 定位修正

### 原假设（已推翻）

```
原设计：AT-SPI2 无障碍树（主力 80%）+ 截图（辅助 20%）
实测：AT-SPI2 覆盖率 ~5%（仅 WebKit 沙箱），COSMIC 原生应用近零
```

### 修正后定位

```
P2 = 截图采集层 + 坐标置信度 + 可选 AT-SPI2 增强
P3 = 视觉模型 + SoM 标注 + 语义元素识别

P2 不承诺：
- 元素级结构化感知（留给 P3）
- 窗口管理（window_list/focus，待验证 compositor 接口）
- 差分截图（待 snapshot_id 时序语义稳定后再做）
- 光标准确的视觉校准（依赖 Spike 2.3 结果）
```

---

## 1. 设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| Tool 面 | 保持 4 tool，扩展 `screen` action | 最小面原则，不加新 tool |
| 截图方案 | xdg-desktop-portal Screenshot | P0 已验证可行，interactive=false 无弹窗 |
| 异步模型 | 由 Spike 2.1 决定 | dbus-next asyncio 或 dbus-python 线程池 |
| AT-SPI2 角色 | 可选增强，不可用时降级 | COSMIC 覆盖率 ~5%，不能当主力 |
| 光标语义 | `source` + `confidence` 字段 | 不承诺绝对准确，外部干扰后可能漂移 |
| 坐标系 | 由 Spike 2.2 决定 | 需验证 1:1 映射或建立偏移常量 |
| 数据模型 | pydantic | 与 P1 一致，入参/出参校验 |
| 截图安全 | copy 到私有 tmp dir + 用后清理 | 不暴露 portal 原始路径，日志不记录截图内容 |
| ScreenBackend | 新增独立抽象，不塞进 InputBackend | InputBackend 保持专注输入，ScreenBackend 独立演进 |
| 返回格式 | JSON（含 image URI + 元数据） | 截图本身不 base64 嵌入，避免 token 膨胀 |

---

## 2. MCP Tool 定义

### P1 保持不变

```
mouse     — 不变
keyboard  — 不变
batch     — 不变（tool enum 扩展 "screen" 的新 action 自动支持）
```

### screen tool 扩展

P1 的 `screen` 只有 `size` / `cursor` 两个 action。P2 新增 `snapshot`：

```yaml
tool: screen
  description: 获取屏幕信息（尺寸、光标、截图快照、无障碍树）
  parameters:
    action: str    # size | cursor | snapshot
    # size/cursor 参数不变
    # snapshot 参数：
    include_a11y: bool   # 是否附带无障碍树（默认 false）
    region: str|null     # 区域裁剪 "x,y,w,h"（默认 null=全屏）
```

P2-A 不单独暴露 `observe` / `diff` / `window_*` / `element_find`，这些留给 P2-B 或 P3。

**AI 调用示例**：

```
# 全屏截图
screen(action="snapshot")
→ {"snapshot_id":"snap_xxx","screen":{"width":2560,"height":1600},"image":{...},"cursor":{...}}

# 带无障碍树
screen(action="snapshot", include_a11y=true)
→ 同上 + "accessibility":{"enabled":true,"available":true,"nodes":[...]}

# 区域截图
screen(action="snapshot", region="0,0,800,600")
→ 同上，image 为裁剪区域

# batch 中使用
batch(actions=[
  {"tool":"screen","args":{"action":"snapshot"}},
  {"tool":"mouse","args":{"action":"move","x":500,"y":300}},
  {"tool":"mouse","args":{"action":"click"}},
  {"tool":"screen","args":{"action":"snapshot"}},
])
```

### screen_snapshot 返回结构

```json
{
  "snapshot_id": "snap_20260523_143022_a1b2c3",
  "timestamp": "2026-05-23T14:30:22.123456",
  "screen": {
    "width": 2560,
    "height": 1600,
    "source": "kms"
  },
  "image": {
    "uri": "file:///tmp/ai-gui-mcp/snap_20260523_143022.png",
    "format": "png",
    "width": 2560,
    "height": 1600,
    "size_bytes": 556000,
    "source": "xdg-desktop-portal"
  },
  "cursor": {
    "x": 500,
    "y": 300,
    "source": "tracked",
    "confidence": "low"
  },
  "accessibility": {
    "enabled": true,
    "available": false,
    "reason": "at-spi bus accessible but no applications registered on COSMIC",
    "node_count": 0,
    "nodes": []
  }
}
```

**cursor 字段语义**（由 Spike 2.3 决定 level）：

| cursor.source | cursor.confidence | 出现条件 |
|---|---|---|
| `"tracked"` | `"low"` | 仅 uinput 内部推算，Spike 2.3 确定光标不可见 |
| `"tracked"` | `"medium"` | 校准后短期内，或光标在截图中可见但未精确定位 |
| `"detected"` | `"high"` | 截图含光标且成功定位 hotspot（理想情况） |
| `"unknown"` | `"none"` | server 刚启动且未做过任何操作 |

**accessibility 字段语义**：

| available | node_count | 含义 |
|:---:|:---:|---|
| `true` | >0 | AT-SPI2 可用且有应用注册了树 |
| `true` | 0 | AT-SPI2 可用但当前无应用暴露树（COSMIC 常态） |
| `false` | 0 | AT-SPI2 总线不可达或 a11y 未启用 |

**snapshot_id 约定**：
- 格式：`snap_{YYYYMMDD}_{HHMMSS}_{random6}`
- 幂等性：每次调用生成新 ID
- 用途：P2-B 做 diff 时引用两个 snapshot_id
- 不做全局状态（不维护"上次截图"隐式引用）

---

## 3. 后端架构

### 3.1 分层设计

```
┌──────────────────────────────────────────────────┐
│  server.py                                        │
│  call_tool("screen", {"action":"snapshot",...})   │
│  → _handle_screen() → _handle_snapshot()          │
└─────────────────────┬────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────┐
│  services/snapshot.py                             │
│  SnapshotService.capture(include_a11y, region)    │
│  - 调 ScreenshotBackend 截图                       │
│  - 调 AccessibilityProvider 取树（可选）            │
│  - 从 InputBackend 取 cursor/screen_size          │
│  - 组装 SnapshotResult                            │
└──────┬──────────────────┬────────────────────────┘
       │                  │
       ▼                  ▼
┌──────────────┐  ┌───────────────────────┐
│ InputBackend │  │ capture/               │
│ (P1 已有)    │  │   ScreenshotBackend    │
│              │  │   (新增，异步)          │
│ screen_size  │  │   capture_full()       │
│ get_cursor   │  │   capture_region()     │
└──────────────┘  └───────────────────────┘
                         │
                         ▼
                  ┌───────────────────────┐
                  │ capture/              │
                  │   AccessibilityProvider│
                  │   (新增，可选)          │
                  │   get_tree()          │
                  │   is_available()      │
                  └───────────────────────┘
```

### 3.2 ScreenshotBackend（新增异步抽象）

```python
# src/capture/base.py
from abc import ABC, abstractmethod

class ScreenshotBackend(ABC):
    """截图采集后端抽象。P2 实现 xdg-desktop-portal。"""

    @abstractmethod
    async def capture_full(self) -> ScreenshotResult:
        """全屏截图，返回图片数据 + 元数据。"""
        ...

    @abstractmethod
    async def capture_region(self, x: int, y: int, w: int, h: int) -> ScreenshotResult:
        """区域截图。"""
        ...

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""
        ...
```

### 3.3 PortalScreenshotBackend（xdg-desktop-portal 实现）

```python
# src/capture/portal.py
# 核心实现思路（异步方案由 Spike 2.1 决定）

class PortalScreenshotBackend(ScreenshotBackend):
    def __init__(self, tmp_dir="/tmp/ai-gui-mcp"):
        # 初始化 D-Bus 连接（dbus-next asyncio 或 dbus-python）
        # 确保 tmp_dir 存在且权限 0700
        ...

    async def capture_full(self):
        # 1. 生成唯一 handle_token
        # 2. 构造 request_path
        # 3. 先订阅 Request::Response 信号
        # 4. 再调用 Screenshot(interactive=False)
        # 5. 等待 Response 信号
        # 6. 解析 results["uri"]
        # 7. copy 到私有 tmp dir
        # 8. 返回 ScreenshotResult
        ...

    async def capture_region(self, x, y, w, h):
        # 先全屏截图，再 Pillow crop
        # （portal v3 支持 region 参数但非所有后端实现，保守先 crop）
        ...
```

**关键设计约束**：

| 约束 | 原因 |
|------|------|
| 先订阅再调用 | portal 官方建议，避免 race condition |
| handle_token 随机 | 不可预测，避免安全/冲突问题 |
| Response code ≠ 0 时返回 error | 区分成功(0)、取消(1)、终止(2) |
| 截图 copy 到私有 dir | 避免 portal 原始文件被外部读写 |
| URI scheme 校验 | 仅接受 `file://`，拒绝其他 scheme |
| 临时文件清理 | session 结束或 snapshot 超时后自动清理 |

### 3.4 AccessibilityProvider（可选增强）

```python
# src/capture/a11y.py
from abc import ABC, abstractmethod

class AccessibilityProvider(ABC):
    """无障碍树提供者。P2 实现 AT-SPI2。"""

    @abstractmethod
    def is_available(self) -> bool:
        """a11y 总线是否可用。"""
        ...

    @abstractmethod
    def get_tree(self, max_depth: int = 5, max_nodes: int = 200) -> A11yTree:
        """获取当前无障碍树（裁剪后）。"""
        ...
```

```python
# src/capture/a11y_atspi.py
# 核心实现思路

class AtspiAccessibilityProvider(AccessibilityProvider):
    def is_available(self):
        # 检查 AT-SPI2 总线可达性
        # 检查 IsEnabled 状态
        ...

    def get_tree(self, max_depth=5, max_nodes=200):
        # pyatspi.Registry.getDesktop(0)
        # DFS/BFS 遍历，限制深度和节点数
        # 对每个节点取：name, role, states, bbox, actions, children
        # 无 Component 的节点 bbox=None
        # 可见性过滤（STATE_SHOWING）
        ...
```

**AT-SPI2 注意事项**：

- COSMIC 上 `IsEnabled` 默认 false，**不做自动启用**（避免侵入式行为）
- 遍历必须有深度上限 + 节点数上限 + 超时，防止大树拖死 server
- 无树时 `available=true, node_count=0` 是正常降级，不是错误
- `reason` 字段帮助 AI 理解为什么没有树

### 3.5 InputBackend 不变

```python
# src/backends/base.py — 不修改
# screen_size() 和 get_cursor_position() 保持原样
# 用于 SnapshotService 获取屏幕尺寸和光标推算值
```

P2 不改变 InputBackend 的接口。`screen_size` 和 `get_cursor_position` 继续留在 InputBackend，因为：
- `screen_size` 影响输入坐标边界校验，和输入强相关
- `get_cursor_position` 是 uinput 内部追踪的结果，和输入执行关联
- 改动 InputBackend 会影响 P1 的 mouse/keyboard handler

### 3.6 SnapshotService（装配层）

```python
# src/services/snapshot.py
# 核心职责：组装 ScreenshotBackend + AccessibilityProvider + InputBackend 的输出

class SnapshotService:
    def __init__(self, screenshot: ScreenshotBackend,
                 input_backend: InputBackend,
                 a11y: AccessibilityProvider | None = None):
        ...

    async def capture(self, include_a11y=False, region=None) -> dict:
        # 1. 截图
        # 2. 取 screen_size（从截图元数据，同时对比 InputBackend.screen_size()）
        # 3. 取 cursor（InputBackend.get_cursor_position()）
        # 4. 可选取 a11y 树
        # 5. 组装为 screen_snapshot 返回结构
        # 6. 做一致性检查（截图尺寸 vs KMS 尺寸，警告不一致）
        ...
```

---

## 4. pydantic 数据模型

### 4.1 扩展 ScreenAction

```python
# src/models.py — 修改
class ScreenAction(BaseModel):
    action: Literal["size", "cursor", "snapshot"]  # 新增 snapshot
    include_a11y: bool = False                       # snapshot 参数
    region: Optional[str] = None                     # "x,y,w,h"
```

### 4.2 SnapshotResult（出参）

```python
# src/models.py — 新增
class ImageInfo(BaseModel):
    uri: str
    format: str
    width: int
    height: int
    size_bytes: int
    source: str  # "xdg-desktop-portal"

class CursorInfo(BaseModel):
    x: int
    y: int
    source: Literal["tracked", "detected", "unknown"]
    confidence: Literal["high", "medium", "low", "none"]

class AccessibilityInfo(BaseModel):
    enabled: bool
    available: bool
    reason: str = ""
    node_count: int
    nodes: list[dict] = []

class SnapshotResult(BaseModel):
    snapshot_id: str
    timestamp: str
    screen: ScreenInfo
    image: ImageInfo
    cursor: CursorInfo
    accessibility: AccessibilityInfo
```

---

## 5. 目录结构（变更）

```
src/
├── server.py              # 修改：_handle_screen 新增 snapshot 分支
├── models.py              # 修改：ScreenAction 扩展 + 新增出参模型
├── config.py              # 修改：读取 perception.* 配置段（可选）
├── backends/
│   ├── base.py            # 不变
│   └── uinput.py          # 不变
├── capture/               # 新增：感知采集层
│   ├── __init__.py
│   ├── base.py            # ScreenshotBackend 抽象
│   ├── portal.py          # PortalScreenshotBackend
│   ├── a11y.py            # AccessibilityProvider 抽象
│   └── a11y_atspi.py      # AT-SPI2 实现（可选）
├── services/              # 新增：服务装配层
│   ├── __init__.py
│   └── snapshot.py        # SnapshotService
└── tests/
    ├── test_mouse.py      # 不变
    ├── test_keyboard.py   # 不变
    ├── test_batch.py      # 不变
    ├── test_snapshot.py   # 新增：snapshot 测试
    └── test_portal.py     # 新增：portal mock 测试
```

---

## 6. 配置文件

```yaml
# config.yaml — 新增 perception 段
server:
  name: "ai-gui-mcp"
  transport: "stdio"

input:
  backend: "uinput"
  uinput:
    device_name: "ai-gui-mcp-virtual"

screen:
  width: 2560
  height: 1600

# P2 新增
perception:
  screenshot:
    backend: "xdg-desktop-portal"          # 截图后端
    tmp_dir: "/tmp/ai-gui-mcp"             # 截图临时目录
    tmp_retention_sec: 300                 # 截图文件保留时间
    timeout_ms: 5000                       # portal 响应超时
  accessibility:
    enabled: true                          # 是否尝试 AT-SPI2
    max_depth: 5                           # 树遍历深度上限
    max_nodes: 200                         # 节点数上限
    timeout_ms: 3000                       # 树获取超时

behavior:
  profile: "none"
```

---

## 7. 核心依赖

```toml
[project]
dependencies = [
    "mcp>=1.0.0",
    "evdev>=1.6.0",
    "pyyaml>=6.0",
    "pydantic>=2.0.0",
    "Pillow>=10.0.0",          # P2 新增：图片处理
]

# 由 Spike 2.1 决定二选一
# "dbus-next>=0.2.3",          # 选项 A：纯 Python asyncio D-Bus
# "dbus-python>=1.3.0",        # 选项 B：GLib 绑定

# 由 Spike 2.5 决定
# "pyatspi>=2.46.0",           # AT-SPI2 Python 绑定（依赖 gi/PyGObject）
```

---

## 8. 开发步骤

### Step 0 — P2 Spike（先做，不跳过）

- [ ] 2.1 异步模型验证
- [ ] 2.2 坐标对齐验证
- [ ] 2.3 光标可见性验证
- [ ] 2.4 文件安全验证
- [ ] 2.5 AT-SPI2 API 验证
- [x] 产出 [PHASE2-SPIKE-RESULTS.md](PHASE2-SPIKE-RESULTS.md) 结论

### Step 1 — 截图后端骨架

- [ ] 创建 `src/capture/base.py` — `ScreenshotBackend` 抽象
- [ ] 创建 `src/capture/portal.py` — `PortalScreenshotBackend`
- [ ] 写 `test_portal.py` — mock D-Bus 响应的单元测试
- [ ] 验证：mock 测试通过 + 真实环境手动截图成功

### Step 2 — SnapshotService

- [ ] 创建 `src/services/snapshot.py` — `SnapshotService`
- [ ] 组装截图 + cursor + screen_size
- [ ] 写 `test_snapshot.py` — mock 所有后端的单元测试
- [ ] 验证：mock 测试通过

### Step 3 — 数据模型

- [ ] 扩展 `src/models.py` — `ScreenAction` 加 `snapshot`
- [ ] 新增出参模型：`SnapshotResult`、`ImageInfo`、`CursorInfo`、`AccessibilityInfo`
- [ ] 验证：pydantic 模型校验测试通过

### Step 4 — server.py 集成

- [ ] `_handle_screen()` 新增 `snapshot` 分支
- [ ] `_create_backend()` 新增 `ScreenshotBackend` 初始化
- [ ] `server.py` 的 `main()` 中注入 `SnapshotService`
- [ ] 更新 `list_tools()` 中 screen tool 的 inputSchema
- [ ] 验证：MCP 客户端调用 `screen(action="snapshot")` 返回正确 JSON

### Step 5 — AT-SPI2 可选增强（条件执行）

- [ ] 创建 `src/capture/a11y.py` — `AccessibilityProvider` 抽象
- [ ] 创建 `src/capture/a11y_atspi.py` — AT-SPI2 实现
- [ ] SnapshotService 集成 `AccessibilityProvider`
- [ ] 验证：有树时返回 nodes，无树时 `available=false` 正常降级

### Step 6 — 配置文件

- [ ] `config.yaml` 加 `perception` 段
- [ ] `config.py` 读取新增配置
- [ ] 验证：配置缺省时的默认值行为正确

### Step 7 — 文档更新

- [ ] 更新 `docs/ROADMAP.md` — P2 状态
- [ ] 更新 `AGENTS.md` — 加入 P2 文档路径
- [ ] 更新 `docs/FUTURE-REFERENCE.md` — P1 已确认事项移到 P2 已确认

### Step 8 — 集成测试与打磨

- [ ] 端到端测试：启动 MCP → snapshot → 验证返回结构
- [ ] 连续 5 次 snapshot 的性能和稳定性
- [ ] batch 中 snapshot + mouse 组合操作
- [ ] tmp dir 清理验证（session 结束后无残留文件）

---

## 9. P2-A vs P2-B 边界

```
P2-A（本计划）:
  ✅ screen(action="snapshot")         — 截图采集
  ✅ screen(action="snapshot", include_a11y=true) — 可选无障碍树
  ✅ cursor source/confidence          — 光标可信度标注
  ✅ 截图安全约定                       — copy + cleanup

P2-B（后续，独立计划）:
  ⏸ screen(action="diff")             — 差分截图
  ⏸ screen(action="observe")          — 区域观察
  ⏸ screen(action="calibrate")        — 光标校准

P3（智能识别层）:
  ⏸ 视觉模型集成
  ⏸ SoM 标注
  ⏸ screen_analyze / element_find
  ⏸ 语义点击
```

---

## 10. 测试策略

### 单元测试（mock 所有外部依赖，CI 可跑）

| 测试目标 | Mock 方式 |
|----------|----------|
| PortalScreenshotBackend | mock D-Bus 连接和信号 |
| AccessibilityProvider | mock pyatspi/dbus 调用 |
| SnapshotService | 注入 mock backend |
| server snapshot handler | mock SnapshotService |

### 集成测试（需要真实 Wayland 环境，本地手动跑）

| 测试目标 | 说明 |
|----------|------|
| portal 截图真实调用 | 验证 2.1-2.4 的 spike 结论 |
| 坐标对齐 | 移动光标 → 截图 → 目视验证 |
| batch 组合操作 | snapshot + mouse + snapshot |
| 截图性能 | 连续调用延迟 |

---

## 11. 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|:---:|------|------|
| portal 截图不含光标 | 中 | 无法做视觉校准 | cursor 标注 `source="tracked"`，P3 再解决 |
| 坐标非 1:1 | 低 | 需要映射层 | 加偏移常量或映射函数 |
| dbus-next 不可靠 | 中 | 需换成 dbus-python | Spike 2.1 先验证 |
| 高频截图造成 /tmp 压力 | 低 | 磁盘/内存消耗 | tmp_retention_sec 配置控制，自动清理 |
| AT-SPI2 零覆盖 | 高 | a11y 字段永远空 | 已为此设计降级，available=false 非错误 |
