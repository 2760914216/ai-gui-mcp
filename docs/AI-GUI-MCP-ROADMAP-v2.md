# AI GUI MCP — 项目总体规划 (v2 · 优化版)

> ⚠️ **此文档为 V2 草稿，部分技术选型已被实际实现覆盖。优先级低于其余 docs/ 文档。**
> 
> 已被后续决策修正：
> - **Phase 1 技术栈**：V2 建议 X11/pyautogui → 实际统一使用 Wayland uinput（见 `docs/PHASE1-IMPLEMENTATION.md`）
> - **Phase 1 截图**：V2 包含 `src/screen/` 截图模块 → P1 实际不做截图（AGENTS.md 明确禁止）
> - **附录A X11 demo**：整体被 Wayland uinput 实现替代，仅接口设计思路可参考
> 
> **保留价值在于**：§4 关键技术修正、§6 技术参考（已校验 benchmark 数字）、分层降级设计、以及其余文档未提及的细节。
>
> ---
>
> 为 AI 编程助手（Cursor / OpenCode / Codex / Claude Code 等）提供 GUI 感知与操作能力的 MCP 工具。
> 核心理念：让 AI 像人一样「看」屏幕、「操作」界面，而非仅靠坐标机械点击。

---

## 1. 项目愿景

### 要解决的问题

AI 编程助手当前能读写文件、执行命令、调用 API，但**无法操作图形界面、无法「看见」GUI**。本项目为 AI 提供一套 GUI 交互原语：

```
AI 发出指令                          OS 执行
─────────────────────────────────────────────────────
"移动到搜索框并输入 hello"   → mouse_move(200,50) + keyboard_type("hello")
"点击保存按钮"               → mouse_click(element_id="save-btn")
"看一下当前界面有什么"       → screenshot() → 标注后的截图 + 元素列表
```

### 定位说明（v2 新增，诚实前提）

立项理由是「编程 LLM 看不见 GUI」。这个前提**正在软化**：Claude 已内置 computer use、GPT-4o/Operator 是多模态、本地多模态模型也在普及。这不是放弃项目的理由（本工具的价值在于**把 GUI 能力做成与具体 LLM/IDE 解耦的通用 MCP 层**，而不是绑死某家厂商的内置能力），但选型和宣传时要意识到这是个移动靶——别把卖点押在「只有我们能让 AI 看屏幕」上，而要押在「跨应用、跨平台、可本地、可审计的统一接口」上。

### 设计原则

| 原则 | 说明 |
|---|---|
| 分层解耦 | Action / Perception / Intelligence 三层独立演进 |
| 优先语义，兜底坐标 | 能用元素名（"保存按钮"）就不用像素坐标 |
| 通用优先 | 优先支持不依赖特定应用的方案（uinput + vision） |
| 分阶段交付 | 每个 Phase 都可独立使用 |
| 最小依赖 | 不给用户环境引入重量级依赖 |
| **先验证再承诺**（v2 新增） | 平台能力假设在动手前用 spike 实测，不假设 |

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────┐
│              AI 编程助手 (Cursor / Claude Code / …)        │
└───────────────────────────┬──────────────────────────────┘
                            │ MCP Protocol (JSON-RPC over stdio)
                            ▼
┌──────────────────────────────────────────────────────────┐
│                  GUI Perception MCP Server                 │
│  ┌────────────┐   ┌──────────────┐   ┌─────────────────┐  │
│  │  Action    │   │ Perception   │   │ Intelligence    │  │
│  │  鼠标/键盘  │   │ 截图/无障碍树 │   │ 视觉模型/SoM/语义│  │
│  └─────┬──────┘   └──────┬───────┘   └────────┬────────┘  │
│        └─────────────────┴────────────────────┘           │
│                          ▼                                 │
│  ┌────────────────────────────────────────────────────┐  │
│  │              Platform Abstraction                    │  │
│  │  Linux(v1)         Windows(v2)        macOS(v2)      │  │
│  │  uinput/XTest      Win32 SendInput    CGEvent        │  │
│  │  PipeWire/X11      DXGI/WGC           ScreenCaptureKit│  │
│  │  AT-SPI2           UIA                 AX API         │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**分层降级（项目核心架构决策）**：`screen_snapshot()` 调用时自动选择最佳表示——

```
1. 无障碍树 (AT-SPI2)   ~10-50ms   最快最精确   ──失败/不完整──┐
                                                              ▼
2. 视觉解析 (OmniParser) ~600-800ms 适用所有应用  ──需更准──────┐
                                                              ▼
3. 通用 VLM (Claude/GPT) ~1-2.5s    最通用最慢
```

> v2 提醒：这条降级链在 **Windows** 上「第 1 层兜住大部分」是合理的；在 **Linux** 上很可能**频繁掉到第 2 层**（见 §4.2）。架构不用改，但要预期 Linux 下视觉层不是「兜底」而是「主力」，资源投入要相应前移。

---

## 3. 分阶段路线图

### Phase 0: 环境验证 Spike（v2 新增）

**目标**：在写正式代码前，用 1-2 天把「会决定整个技术栈」的几个未知数实测掉。
**时间**：~1-2 天 ｜ **平台**：目标机器（Linux）

为什么必须先做：v1 把这些排到了 Phase 2-3，但它们的结果会**反向决定 Phase 1 怎么写**。如果实测发现 Wayland 下读不到光标位置，Phase 1 的 `mouse_position()` 就得换实现；如果 AT-SPI2 在目标应用上覆盖率只有 40%，整个感知层的优先级就要调。

验证清单：

- [ ] **会话类型**：目标机器是 X11 还是 Wayland？（`echo $XDG_SESSION_TYPE`）—— 这是最大的分叉点。
- [ ] **uinput 注入**：在目标会话下，python-evdev 写入虚拟设备能否被应用接收？（X11 几乎必成，Wayland 看 compositor）
- [ ] **截图可行性**：全屏截图走什么通路？X11 → 直接抓帧；Wayland → 必须走 xdg-desktop-portal，且首次可能弹授权窗。
- [ ] **光标位置读取**：Wayland 下默认**读不到**全局光标坐标（安全限制），需确认 compositor 是否提供接口，否则 `mouse_position()` 只能维护内部状态。
- [ ] **AT-SPI2 实际覆盖**：用 `accerciser` 或 `dasbus` 扫一遍**目标用户真实会操作的 5-10 个应用**，记录每个能拿到多完整的树。这一项的结果决定了视觉层该多早投入。

> **强烈建议**：第一个 demo 先在 **X11 会话**（或 XWayland）下做。X11 的输入注入（XTest）、截图、光标读取全部是成熟方案，能把 Phase 1 从「1 周」压到「一个周末」。把 Wayland 的全部麻烦留到 demo 跑通、概念验证完成之后再啃。

---

### Phase 1: Action Layer（模拟输入）

**目标**：AI 能执行基础鼠标键盘操作 ｜ **时间**：~1 周（X11 下约 2-3 天）｜ **状态**：准备开始

#### 1.1 核心能力

```
鼠标:   mouse_move_abs / mouse_move_rel / mouse_click / mouse_dbl_click
        mouse_right_click / mouse_down / mouse_up / mouse_scroll
        mouse_scroll_h / mouse_drag / mouse_position
键盘:   keyboard_type / keyboard_press([ctrl,shift,s]) / keyboard_down / keyboard_up
辅助:   screenshot / screen_size / wait(ms) / batch(actions[])
```

#### 1.2 技术选型（v2 微调）

| 决策 | 选择 | 原因 |
|---|---|---|
| 语言 | Python 3.10+ | MCP SDK 生态成熟 |
| 输入（X11，demo 推荐） | ~~python-xlib / XTest 或 pyautogui~~ | ⚠️ [V2假设] 已被实际实现覆盖：统一使用 uinput |
| 输入（Wayland，实际采用） | **python-evdev + uinput** | 内核级，对 compositor 透明（实际 P1 实现方案） |
| 截图（X11） | mss / Pillow.ImageGrab | 快，无依赖 |
| 截图（Wayland） | PipeWire + xdg-desktop-portal | Wayland 标准，但需授权 |
| MCP 框架 | mcp（官方 SDK） | 稳定 |
| MCP Transport | **stdio** | demo 阶段最简单；远程需求出现时再上 SSE |
| 打包 | uv + pyproject.toml | 现代工具链 |

> v1 默认上来就 uinput——对 Wayland 没错，但对 demo 是把难度拉满。v2 建议：**抽象一个 `InputBackend` 接口，先实现 X11 后端跑通，再补 uinput/Wayland 后端**。接口不变，后端可换，也为 Phase 5 跨平台铺好路。

权限：uinput 路径需 `sudo usermod -aG input $USER`；X11 路径通常无需特殊权限。

#### 1.3 Phase 1 交付物

- `src/backends/` — `InputBackend` 接口 + ~~X11 后端~~ uinput 后端 ⚠️ [V2假设] 实际仅实现 uinput，无 X11 后端
- ~~`src/screen/` — 截图模块~~ ⚠️ [V2假设] P1 实际不做截图（P2 引入）
- `src/server.py` — MCP server 入口
- `pyproject.toml` — 依赖与打包
- `tests/` — 每个工具的可用性验证脚本

→ **可直接落地的实现规格见附录 A**。

---

### Phase 2: Perception Layer（屏幕感知）

**目标**：AI 能「看见」屏幕、获取结构化信息 ｜ **时间**：~2 周 ｜ **依赖**：Phase 0+1

#### 核心能力

```
screen_snapshot()        截图 + 无障碍树 + 窗口列表
screen_observe(region?)  区域截图（可带坐标标尺）
screen_diff()            仅返回上次截图的变化区域
window_list / window_focus(title)
element_find(description) 在无障碍树中搜索元素
```

无障碍树输出示例（结构保留 v1 不变）：

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

#### v2 风险前置

- **AT-SPI2 库**：`pyatspi2` 封装全但依赖 GObject；`dasbus` 更轻。建议先用 dasbus 做 Phase 0 的覆盖率探测，确定主力库后再固化。
- **覆盖率现实**（关键）：见 §4.2。把「Electron / Canvas / 游戏 / 自定义工具包不暴露树」当作**常态**而非例外来设计——这意味着视觉路径（Phase 3）的优先级实际上要**和 Phase 2 并行**，而不是排在它后面。
- 差分截图算法、PipeWire 跨 compositor 兼容性仍是 [TODO]，但都不是 demo 阻塞项。

---

### Phase 3: Intelligence Layer（智能识别）

**目标**：纯视觉下也能识别 GUI 元素 ｜ **时间**：~3 周 ｜ **依赖**：Phase 2

```
screen_analyze()              视觉分析，返回结构化元素列表
screen_find(description)       语义搜索（"找到保存按钮"）
screen_click_element(desc)     语义点击（不需要坐标）
screen_read_text(x1,y1,x2,y2)  区域 OCR
```

OmniParser 集成思路（v1 正确，保留）：截图 → YOLOv8 检测可交互区域 → Florence-2 生成功能描述 → OCR 提文字 → 合成 SoM 标注截图（数字编号覆盖在元素上），LLM 输出 `click element 12` 而非 `click (225,115)`。

#### 3.1 视觉模型选型（v2 已核对数字）

> ⚠️ **这张表的数字 v1 有误，且这个领域 benchmark 月月在变。下表为 2025 年中可查的口径，选型时务必按当时 leaderboard 复核。**

| 方案 | 部署 | ScreenSpot-Pro（高难基准） | 说明 |
|---|---|---|---|
| OmniParser v2 + GPT-4o | 本地解析 + 云 VLM | **~39.6%**（已核实，MS 官方） | 注意：39.6% 是「解析器喂给 GPT-4o」的成绩，不是解析器单独的 |
| UI-TARS-72B | 本地 GPU（72B） | **~38%**（端到端，需复核） | v1 写的「7B = 61.6%」**错误**：7B 不可能高于 72B，且 61.6% 像是普通 ScreenSpot（更易）的数 |
| ScreenSeekeR（视觉搜索） | 训练-free 方法 | **~48%** | 当时 SOTA 量级，靠「缩小搜索区」提升 |
| Claude Computer Use / GPT-4V+SoM | API | 最高但最慢（~1-2.5s） | GPT-4o **裸图**在该基准仅 0.8%——说明解析层是刚需 |

> 背景：ScreenSpot-Pro 是专门为高分辨率专业软件设计的硬基准，**目标元素平均只占画面 0.07%**，原论文里最强模型也只有 18.9%。任何宣称在它上面破 60% 的 7B 模型，先去核源。

#### 3.2 Phase 3 交付物

`src/intelligence/`（视觉解析）、OmniParser 本地部署、SoM 标注工具、OCR、分层降级逻辑。
[TODO] 本地模型 vs API 谁做默认？｜ GPU 需求对目标用户是否可接受？

---

### Phase 4: Human-like（类人交互）

**目标**：操作更像人 ｜ **时间**：~2 周 ｜ **依赖**：Phase 1 即可开始，可与 2/3 并行

可配置 profile：`none / casual / deliberate / custom`，含鼠标速度、打字速度、点击抖动、操作后停顿。
具体增强：鼠标贝塞尔曲线（加速→减速）替代直线；逐字符输入带随机间隔（50-200ms，可选错误率）；点击在元素内随机偏移 3-8px + 按下到释放 50-100ms 间隔；滚轮带惯性分段。
交付物：`src/human/`（轨迹生成器、输入模拟器、行为配置、轨迹预览）。

> v2 提醒：除非明确瞄准「反自动化检测」场景，否则类人交互的优先级应低于「能稳定操作」。先把 Phase 1-3 的可靠性做扎实，类人是锦上添花。

---

### Phase 5: Multi-platform（跨平台）

**目标**：支持 Windows / macOS ｜ **时间**：~4 周 ｜ **依赖**：Phase 1-2 架构稳定后

```
src/platform/
├── linux/    mouse/keyboard(uinput,XTest)  screen(PipeWire/X11)  a11y(AT-SPI2)
├── windows/  mouse/keyboard(SendInput)      screen(DXGI/WGC)      a11y(UIA via FlaUI)
└── macos/    mouse/keyboard(CGEvent)         screen(ScreenCaptureKit) a11y(AX API)
```

平台要点（v1 正确，保留并补一条）：
- **Windows**：UIA 覆盖率远好于 Linux AT-SPI2；高 DPI 需特殊处理；WGC 需 Win10 1803+。
- **macOS**：ScreenCaptureKit 与 AX 都需权限弹窗手动授权；可能需 notarized 签名。**AX API 覆盖率也明显好于 Linux**——如果哪天想让某人在 Mac 上快速试，macOS 后端反而比 Linux 好做。
- 自动平台检测与路由 + 各平台测试套件。

---

### Phase 6: Polish（打磨）

| 功能 | 优先级 |
|---|---|
| 批量操作优化（减少往返） | 高 |
| 错误恢复（失败重试/回滚） | 高 |
| 操作录制与回放 | 中 |
| 安全沙箱（窗口/应用白名单） | 中 |
| 多显示器支持 | 中 |
| 日志与回放（审计） | 中 |
| 性能监控 | 低 |
| 插件系统（如 Chrome CDP 适配器） | 低 |

安全设计 [TODO 详议]：操作前确认弹窗？黑白名单？敏感区域屏蔽（密码框不截图）？操作频率限制？

---

## 4. 关键技术修正（v2 新增 · 集中列出，便于原作者核对）

### 4.1 错误的 benchmark 数字

v1 §3.3 表中「UI-TARS-7B / ScreenSpot Pro / 61.6%」是错的：

- ScreenSpot-Pro 上当时最强方法约 47-48%，UI-TARS-72B 本身都不到 40%；
- 一个 7B 模型不可能在同一基准上超过它的 72B 版本，更不可能破 60%；
- 61.6% 极可能是从**普通 ScreenSpot / ScreenSpot-V2**（容易得多，UI-TARS 在那上面能到 ~89%）串过来的。

教训：v1 这张表是「攒」出来的、未逐个核源（相邻的 OmniParser 39.6% 倒是对的）。**任何选型决策都别直接信这张表，到时按 leaderboard 现查。**

### 4.2 「无障碍树覆盖 80%」是 Windows 口径，不适用于 Linux-first

v1（及上游 overview）称「无障碍树覆盖约 80% 应用」。这个 80% 隐含的是 **Windows UIA** 的覆盖率。本项目 Phase 1-2 锁定 Linux，而 Linux 上 **AT-SPI2 的实际覆盖差得多**：

- GTK 应用通常 OK；
- Qt 时好时坏（取决于是否启用 a11y 桥接）；
- Electron 基本拿不到有用的树；
- Wayland 原生应用更糟。

后果：v1 把视觉路径（Phase 3）当「20% 场景的兜底」排在 3 周后，但 Linux 的现实更可能是**视觉路径要承担 40-60% 的活、且要和 Phase 2 并行起步**。这不需要改架构，但需要把资源/时间预期前移——否则 Phase 2 做完会发现「树拿不到、视觉还没好」的空窗。Phase 0 的覆盖率探测就是为了把这个数字从「猜」变成「测」。

### 4.3 被低估的 Wayland 限制

uinput 能**写**输入 ≠ 能**读**状态。Wayland 下读全局光标位置、做全屏截图都需 portal/compositor 配合，且各 compositor（GNOME/KDE/wlroots）行为不一。v1 把这列为「中优先级决策」，实际更接近 **Phase 1 阻塞项**。→ 故 v2 建议 demo 先走 X11。

### 4.4 一处假精度（来自上游 overview）

overview 里「差分区域 ~400 tokens → ~0.4s 推理，快约 3 倍」把 input token 数当成与推理 wall-clock 的线性关系。实际上 input token 影响 prefill、output token 主导 decode，不是 1:1 折算。差分截图省 token（进而省钱、略省 prefill）是真的，但「快 3 倍」这个具体倍数没有依据，建议表述为「显著减少输入开销」。

---

## 5. 待讨论事项（v2 重排优先级）

### 🔴 动手前（Phase 0 一并验证）

| # | 事项 | 选项 / 现状 |
|---|---|---|
| 1 | 会话类型 | X11（demo 推荐）vs Wayland——决定整个输入/截图栈 |
| 2 | 截图方案 | X11 直抓 vs PipeWire+portal（Wayland）vs grim+slurp（wlroots） |
| 3 | 光标读取 | X11 可读 vs Wayland 受限（可能只能维护内部状态） |
| 4 | AT-SPI2 实测覆盖 | 用真实目标应用集测，决定视觉层投入时机 |

### 🟡 Phase 2-3 前

| # | 事项 | 现状 |
|---|---|---|
| 5 | 无障碍树库 | pyatspi2（全，依赖 GObject）vs dasbus（轻） |
| 6 | 视觉模型 | OmniParser（本地）vs UI-TARS vs API——精度/延迟/部署三角，按当时 leaderboard 定 |
| 7 | GPU 需求 | 本地跑 OmniParser 是否要求用户有 GPU？ |
| 8 | 差分算法 | 像素 diff vs 感知哈希 vs SSIM |

### ❓ 待原作者确认

- A. 目标用户主要在哪个会话/平台？（这直接定 Phase 0-1 的实现）
- B. 是否要安全确认弹窗，还是信任「用户看着 AI 操作」？
- C. 使用场景：本地开发机 / 远程服务器 / 都要？
- D. 对 python-evdev 的 GPL 有顾虑吗？（X11 路径可绕开此问题）

---

## 6. 技术参考（v2 已修正数字）

**关键项目**：Anthropic Computer Use（跨平台，纯视觉，闭源）｜ OmniParser v2（MS，视觉→结构化，CC-BY-4.0）｜ Screenhand（macOS/Win，AX 优先，~50ms，AGPL）｜ FlaUI-MCP（Windows，元素引用，MIT）｜ kwin-mcp（Linux/KDE，AT-SPI2，MIT）｜ gui-user（Linux/X11，AT-SPI2 + 批量）｜ OS-Atlas（跨平台，1300 万元素训练数据）

**关键论文**：CogAgent (CVPR'24)｜ScreenAI (IJCAI'24)｜SeeClick (ACL'24)｜UI-TARS (2025, ByteDance)｜GUI-Actor (2025, MS，免坐标注意力定位，宣称在小模型上较 UI-TARS 有提升 [需复核具体分数])｜UGround/SeeAct-V (ICLR'25)

**关键数据**（已核对/标注口径）：
- 屏幕截图延迟：DXGI ~10-15ms ｜ PipeWire <2ms (DMA-BUF)——均 <5% 任务延迟，非瓶颈
- OmniParser 延迟：~600ms (A100) / ~800ms (4090)
- **LLM 推理占任务总延迟 75-94%**——真正的瓶颈在此（OSWorld-Human 口径）
- 无障碍树操作延迟 ~50ms（Screenhand 实测，注意是 macOS/Win 口径）
- 差分截图 token 节省：据 DeltaVision 称 40-77%（节省的是 token/成本，非 wall-clock）
- **ScreenSpot-Pro 难度参考**：原论文最强模型 18.9%，目标元素均占画面 0.07%

---

## 附录 A：Phase 1 Demo 实现规格（给 CC / Codex 直接执行）

> ⚠️ **此附录整体被实际 Wayland uinput 实现替代。仅接口设计思路（`InputBackend` 抽象、batch 设计、验收标准）可作参考。实际实现见 `src/` 源码和 `docs/PHASE1-IMPLEMENTATION.md`。**
>
> 原始内容：X11 后端为默认实现（最快跑通）；接口设计成可替换后端，以便后续补 uinput / macOS。

### 项目结构

```
ai-gui-mcp/
├── pyproject.toml
├── README.md
├── src/ai_gui_mcp/
│   ├── __init__.py
│   ├── server.py            # MCP server 入口，注册所有 tool
│   ├── backends/
│   │   ├── base.py          # InputBackend / ScreenBackend 抽象基类
│   │   └── x11.py           # X11 实现（默认）
│   └── models.py            # 入参/出参的 pydantic 模型
└── tests/
    └── test_smoke.py        # Xvfb 下的无头冒烟测试
```

### 抽象接口（backends/base.py）

```python
from abc import ABC, abstractmethod

class InputBackend(ABC):
    @abstractmethod
    def move_abs(self, x: int, y: int) -> None: ...
    @abstractmethod
    def move_rel(self, dx: int, dy: int) -> None: ...
    @abstractmethod
    def click(self, x: int, y: int, button: str = "left") -> None: ...
    @abstractmethod
    def scroll(self, dy: int) -> None: ...
    @abstractmethod
    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None: ...
    @abstractmethod
    def position(self) -> tuple[int, int]: ...   # X11 可实现；Wayland 后续返回内部状态
    @abstractmethod
    def type_text(self, text: str) -> None: ...
    @abstractmethod
    def press(self, keys: list[str]) -> None: ...  # 组合键，如 ["ctrl","shift","s"]

class ScreenBackend(ABC):
    @abstractmethod
    def screenshot(self) -> bytes: ...            # PNG bytes
    @abstractmethod
    def size(self) -> tuple[int, int]: ...
```

### 要暴露的 MCP Tools（Phase 1）

```
mouse_move_abs(x, y)            mouse_move_rel(dx, dy)
mouse_click(x, y, button)       mouse_dbl_click(x, y)
mouse_right_click(x, y)         mouse_scroll(dy)
mouse_drag(x1, y1, x2, y2)      mouse_position() -> {x, y}
keyboard_type(text)             keyboard_press(keys: list[str])
screenshot() -> PNG bytes       screen_size() -> {width, height}
wait(ms)                        batch(actions: list[dict])
```

### 实现要点 / 给 CC 的约束

- **MCP 框架**：官方 `mcp` Python SDK，transport 用 stdio。
- **X11 输入**：用 `pyautogui`（最省事，跨 X11/Win/mac，便于将来扩展）或 `python-xlib + XTest`（更底层、更可控）。二选一，建议 demo 先用 pyautogui 把流程跑通。
- **X11 截图**：`mss`（快）或 `PIL.ImageGrab`。
- **`batch`**：顺序执行 actions 列表，每个 action 形如 `{"tool":"mouse_click","args":{"x":100,"y":50}}`，遇错中止并返回已执行步数——这是减少 AI 往返的关键工具，要做对。
- **坐标安全**：所有坐标先 clamp 到屏幕范围内，越界返回错误而非乱点。
- **不要**在 Phase 1 碰 uinput / Wayland / 无障碍树 / 视觉模型——那是 Phase 2+。Demo 只证明「AI 能通过 MCP 可靠地动鼠标键盘 + 截图回看」。

### 验收标准（demo 成功的定义）

1. 在 Claude Code 里挂上这个 MCP server，能看到上述 tools。
2. 让 Claude 执行一个真实任务，例如：「打开文本编辑器，输入一句话，截图给我看」——它通过 `mouse_click → keyboard_type → screenshot` 完成，且截图里能看到输入的文字。
3. `batch` 能一次下发 3+ 个动作并正确顺序执行。
4. `tests/test_smoke.py` 在 Xvfb 无头环境下通过（CI 友好）。

---

*本文档为 v1 的优化版，随项目进展持续更新。*
