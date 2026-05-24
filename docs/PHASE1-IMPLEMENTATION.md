# Phase 1: Action Layer — 实现计划

> **前置**：Phase 0 Spike 全部验证通过
> **目标**：AI 能通过 MCP 执行鼠标键盘操作
> **平台**：Linux Wayland COSMIC，uinput 内核级输入

---

## 1. 设计决策（已确认）

| 决策 | 选择 | 原因 |
|------|------|------|
| Tool 面 | 4 个 tool（mouse/keyboard/screen/batch） | 最小面 + batch 批量操作 |
| 输入方案 | uinput + `InputBackend` 抽象接口 | 内核级，后端可替换 |
| 坐标追踪 | 内部追踪 | Wayland 无法读全局光标 |
| 截图 | P1 不做 | AI 无视觉能力 |
| Transport | stdio | 本地部署 |
| 数据模型 | pydantic | 入参校验 |

---

## 2. MCP Tool 定义

```yaml
tool: mouse
  description: 模拟鼠标操作
  parameters:
    action: str    # move | move_rel | click | dbl_click | right_click | down | up | scroll | drag
    x, y: int      # move/click/dbl_click/right_click（click 系列 x,y 可选，缺省时原地点击）
    dx, dy: int    # move_rel / scroll
    x1, y1: int    # drag 起点坐标
    x2, y2: int    # drag 终点坐标
    button: str    # left | right | middle (默认 left)

tool: keyboard
  description: 模拟键盘操作
  parameters:
    action: str    # type | press | down | up
    text: str      # action=type
    keys: list[str] # action=press, 如 ["ctrl","s"]
    key: str       # action=down/up

tool: screen
  description: 获取屏幕信息
  parameters:
    action: str    # size | cursor（P1: size + cursor）
  → size: {width: int, height: int}
  → cursor: {x: int, y: int}（内部追踪位置）

tool: batch
  description: 批量执行多个操作，减少 AI 往返
  parameters:
    actions: list[Action]
      # 每项: {"tool": "mouse", "args": {"action": "click", "x": 200, "y": 50}}
      # 可混用 mouse/keyboard/screen 操作
      # 顺序执行，遇错中止，返回已执行步数
```

**AI 调用示例**：
```
mouse(action="click", x=200, y=50)
mouse(action="move_rel", dx=-100, dy=0)
keyboard(action="type", text="hello world")
keyboard(action="press", keys=["ctrl", "s"])
screen(action="size") → {"width": 1920, "height": 1080}

batch(actions=[
  {"tool":"mouse","args":{"action":"move","x":500,"y":100}},
  {"tool":"mouse","args":{"action":"click"}},
  {"tool":"keyboard","args":{"action":"type","text":"hello"}},
])
```

---

## 3. 后端抽象接口

```
src/backends/
├── __init__.py
├── base.py       # InputBackend 抽象基类
└── uinput.py     # Linux uinput 实现
```

### base.py — 抽象接口

```python
from abc import ABC, abstractmethod

class InputBackend(ABC):
    """跨平台输入后端的统一接口。P1 实现 uinput，后续可加 XTest/Win/macOS。"""

    # ── 鼠标 ──
    @abstractmethod
    def move_abs(self, x: int, y: int) -> None: ...
    @abstractmethod
    def move_rel(self, dx: int, dy: int) -> None: ...
    @abstractmethod
    def click(self, x: int, y: int, button: str = "left") -> None: ...
    @abstractmethod
    def dbl_click(self, x: int, y: int, button: str = "left") -> None: ...
    @abstractmethod
    def right_click(self, x: int, y: int) -> None: ...
    @abstractmethod
    def mouse_down(self, button: str = "left") -> None: ...
    @abstractmethod
    def mouse_up(self, button: str = "left") -> None: ...
    @abstractmethod
    def scroll(self, dy: int, dx: int = 0) -> None: ...
    @abstractmethod
    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None: ...

    # ── 键盘 ──
    @abstractmethod
    def type_text(self, text: str) -> None: ...
    @abstractmethod
    def press_combo(self, keys: list[str]) -> None: ...
    @abstractmethod
    def key_down(self, key: str) -> None: ...
    @abstractmethod
    def key_up(self, key: str) -> None: ...

    # ── 查询 ──
    @abstractmethod
    def screen_size(self) -> tuple[int, int]: ...

    # ── 生命周期 ──
    @abstractmethod
    def close(self) -> None: ...
```

### uinput.py — COSMIC/Wayland 实现

```python
# 核心实现思路
class UInputBackend(InputBackend):
    def __init__(self):
        self._mouse = UInput({...}, name="ai-gui-mcp-mouse")
        self._kbd = UInput({...}, name="ai-gui-mcp-keyboard")
        self._x, self._y = 0, 0   # 内部追踪

    def move_abs(self, x, y):
        dx, dy = x - self._x, y - self._y
        self.move_rel(dx, dy)

    def move_rel(self, dx, dy):
        self._mouse.write(EV_REL, REL_X, dx)
        self._mouse.write(EV_REL, REL_Y, dy)
        self._mouse.syn()
        self._x += dx; self._y += dy
    # ...
```

**为什么 P1 就要建抽象层**：即使当前只有一个后端，接口定义本身就是文档。P2 加截图后端、P5 跨平台时，只需加新实现类，不改调用方。

---

## 4. pydantic 数据模型

```python
# src/models.py
from pydantic import BaseModel, Field
from typing import Literal, Optional

class MouseAction(BaseModel):
    action: Literal["move","move_rel","click","dbl_click","right_click","down","up","scroll","drag"]
    x: Optional[int] = None
    y: Optional[int] = None
    dx: Optional[int] = None
    dy: Optional[int] = None
    x1: Optional[int] = None    # drag 起点
    y1: Optional[int] = None    # drag 起点
    x2: Optional[int] = None    # drag 终点
    y2: Optional[int] = None    # drag 终点
    button: Literal["left","right","middle"] = "left"

class KeyboardAction(BaseModel):
    action: Literal["type","press","down","up"]
    text: Optional[str] = None
    keys: Optional[list[str]] = None
    key: Optional[str] = None

class ScreenAction(BaseModel):
    action: Literal["size", "cursor", "snapshot"]

class BatchAction(BaseModel):
    tool: Literal["mouse","keyboard","screen"]
    args: dict

class BatchRequest(BaseModel):
    actions: list[BatchAction]

# ── P2 感知输出模型 ──

class ScreenInfo(BaseModel):
    width: int
    height: int

class CursorInfo(BaseModel):
    x: int
    y: int
    source: Literal["tracked", "detected"]

class UIElement(BaseModel):
    id: str
    role: Optional[str] = None
    name: Optional[str] = None
    bbox: Optional[list[int]] = None
    states: Optional[list[str]] = None
    parent: Optional[str] = None
    confidence: Optional[float] = None

class ScreenSnapshot(BaseModel):
    screen: ScreenInfo
    cursor: CursorInfo
    screenshot: Optional[str] = None
    elements: list[UIElement] = []
    source: Literal["screenshot", "accessibility", "vision"]
    note: Optional[str] = None
```

---

## 5. 目录结构（最终）

```
src/
├── __init__.py
├── server.py          # MCP Server 入口（tool 注册 + handler）
├── config.py          # YAML 配置加载
├── models.py          # pydantic 入参/出参模型
├── backends/
│   ├── __init__.py
│   ├── base.py        # InputBackend 抽象接口
│   ├── uinput.py      # Linux uinput 实现
│   ├── portal.py      # xdg-desktop-portal 截图后端 (P2)
│   └── screen.py      # ScreenBackend 抽象接口 (P2)
└── tests/
    ├── test_mouse.py
    ├── test_keyboard.py
    └── test_batch.py
```

---

## 6. 配置文件

```yaml
# config.yaml
server:
  name: "ai-gui-mcp"
  transport: "stdio"

input:
  backend: "uinput"             # 后端选择
  uinput:
    device_name: "ai-gui-mcp-virtual"

screen:
  # KMS 检测优先，此处为回退值
  width: 2560
  height: 1600

perception:                     # P2 启用
  screenshot:
    method: xdg-desktop-portal
    timeout_ms: 10000

behavior:                       # P4 启用
  profile: "none"
```

---

## 7. 核心依赖

```toml
[project]
name = "ai-gui-mcp"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.0.0",
    "evdev>=1.6.0",
    "pyyaml>=6.0",
    "pydantic>=2.0.0",
    "dbus-next>=0.2.3",
    "pillow>=12.2.0",
]
[project.optional-dependencies]
dev = ["pytest>=8.0.0"]
```

---

## 8. 开发步骤

**Step 0** — 环境准备
- [ ] Phase 0 Spike 全部通过
- [ ] 加入 `input` 组：`sudo usermod -aG input $USER`（重新登录）

**Step 1** — 项目骨架 + 后端接口
- [ ] `pyproject.toml` + `config.yaml`
- [ ] `src/backends/base.py` — `InputBackend` 抽象类
- [ ] `src/models.py` — pydantic 模型
- [ ] `src/config.py` — YAML 加载

**Step 2** — uinput 后端实现
- [ ] `src/backends/uinput.py` — 鼠标：move_abs/rel, click, dbl_click, right_click, scroll, drag
- [ ] 键盘：type_text（含 Shift 字符映射）, press_combo, key_down/up
- [ ] 内部坐标追踪 `_x, _y`
- [ ] 屏幕分辨率获取
- [ ] 测试：移动鼠标、点击、打字均生效

**Step 3** — MCP Server
- [ ] `src/server.py` — 4 个 tool 注册 + handler 逻辑
- [ ] handler 路由：mouse/keyboard/screen/batch → 对应 InputBackend 方法
- [ ] batch 执行器：顺序执行，遇错中止，返回 `{completed: N, total: M}`
- [ ] 坐标 clamp：越界返回错误而非乱点

**Step 4** — 端到端验证
- [ ] 每个 action 至少一个测试用例
- [ ] batch 测试：3+ 个混合操作顺序执行
- [ ] 权限错误友好提示（未在 input 组等）
- [ ] 和 MCP 客户端联调（OpenCode）

---

> **依赖**：Phase 0 Spike 结论（已通过，见 PHASE0-SPIKE-RESULTS.md）。  
> **状态**：✅ P1 已完成。
