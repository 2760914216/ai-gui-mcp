# AI GUI MCP — 项目架构设计 (v3)

> **V3 说明**：基于 V2 的技术修正重写。V2 中已被实际实现覆盖的假设（X11 demo、附录 A 代码骨架等）不再保留。本文档为项目权威架构参考，随实际进展更新。
>
> 与活跃文档的关系：阶段状态见 [ROADMAP.md](ROADMAP.md)；跨 session 决策记录见 [FUTURE-REFERENCE.md](FUTURE-REFERENCE.md)。

---

## 1. 项目愿景

为 AI 编程助手提供 **与具体 LLM/IDE 解耦的通用 GUI 交互层**，通过 MCP 协议暴露跨平台、可审计的 GUI 操作与感知能力。

### 设计原则

| 原则 | 说明 |
|------|------|
| **分层解耦** | Action / Perception / Intelligence 三层独立演进 |
| **图像优先，语义兜底** | Linux 上 AT-SPI2 覆盖率极低（实测 ~5%），视觉路径是主力而非兜底 |
| **最小工具面** | 4 个 MCP tool（mouse/keyboard/screen/batch），通过 action 参数区分操作 |
| **后端可替换** | InputBackend / ScreenBackend 抽象接口，当前仅 Linux Wayland 实现 |
| **分阶段交付** | 每个 Phase 独立可用 |
| **先验证再编码** | 平台能力假设必须用 spike 实测，不写未经验证的数字 |

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────┐
│              AI 编程助手 (Cursor / Claude Code / OpenCode)  │
└───────────────────────────┬──────────────────────────────┘
                            │ MCP Protocol (JSON-RPC over stdio)
                            ▼
┌──────────────────────────────────────────────────────────┐
│                GUI Perception MCP Server                   │
│  ┌────────────┐   ┌──────────────┐   ┌─────────────────┐  │
│  │  Action    │   │ Perception   │   │ Intelligence    │  │
│  │  鼠标/键盘  │   │ 截图/无障碍树 │   │ 视觉模型/SoM    │  │
│  └─────┬──────┘   └──────┬───────┘   └────────┬────────┘  │
│        └─────────────────┴────────────────────┘           │
│                          ▼                                 │
│  ┌────────────────────────────────────────────────────┐  │
│  │              Platform Abstraction                    │  │
│  │  Linux(current)      Windows(future)   macOS(future) │  │
│  │  uinput               SendInput         CGEvent      │  │
│  │  xdg-desktop-portal   DXGI/WGC          SCKit        │  │
│  │  AT-SPI2 (opportunistic) UIA           AX API        │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 分层降级链（Linux 现实修正）

原 V2 设计认为 AT-SPI2 无障碍树是主力（~80%），视觉是兜底（~20%）。Phase 0/2 Spike 实测推翻了这一前提：

```
P2（当前）: 截图采集 → 仅截图（AT-SPI2 覆盖率 0%，COSMIC 无树可用）
P3（规划）: 截图 → 视觉模型 (OmniParser/SoM) → 结构化元素
           ──特定应用有树──┐
                           ▼
                   AT-SPI2 增强（opportunistic，不可用时静默降级）
```

**关键事实**：Linux Wayland COSMIC 上 AT-SPI2 覆盖率实测 0%（P0 为 ~5% 仅 WebKit，P2 重新验证为 0%）。视觉路径在整个 Linux target 上是**感知主力**，而非兜底。

---

## 3. 分阶段路线图

| Phase | 内容 | 状态 | 产出 |
|-------|------|:---:|------|
| **0. Spike** | uinput/键盘/坐标/AT-SPI2/截图 可行性验证 | ✅ | [PHASE0-SPIKE.md](PHASE0-SPIKE.md) → [PHASE0-SPIKE-RESULTS.md](PHASE0-SPIKE-RESULTS.md) |
| **1. Action** | MCP server + 鼠标键盘模拟 (uinput) | ✅ | [PHASE1-IMPLEMENTATION.md](PHASE1-IMPLEMENTATION.md) |
| **2. Perception** | 截图采集 (xdg-desktop-portal) + 坐标置信度 | ✅ | [PHASE2-SPIKE.md](PHASE2-SPIKE.md) → [PHASE2-SPIKE-RESULTS.md](PHASE2-SPIKE-RESULTS.md) → [PHASE2-IMPLEMENTATION.md](PHASE2-IMPLEMENTATION.md) |
| **3. Intelligence** | 视觉识别 + SoM 标注 + 语义点击 | 规划中 | — |
| **4. Human-like** | 类人交互（贝塞尔轨迹、打字间隔等） | 规划中 | — |
| **5. Multi-platform** | Windows + macOS 后端 | 远期 | — |
| **6. Polish** | 安全、性能、录制回放 | 远期 | — |

### Phase 1: Action Layer ✅

- **实现**：uinput 后端（evdev），内核级输入注入，对 compositor 透明
- **工具面**：mouse / keyboard / screen / batch，4 tool + action 参数
- **关键决策**：坐标用内部追踪（Wayland 下无法读取全局光标），Transport 用 stdio
- **已知限制**：光标位置仅内部推算，外部干扰后会漂移；P2 引入截图后可做视觉校准

### Phase 2: Perception Layer ✅

- **实现**：xdg-desktop-portal Screenshot（dbus-python + GLib 线程桥接），截图延迟 ~56ms
- **核心语义**：`screen(action="snapshot")` 返回截图 + 坐标/光标置信度 + 可选无障碍树
- **关键决策**：
  - D-Bus 库选 `dbus-python`（dbus-next 存在 introspection bug，不可用）
  - AT-SPI2 放弃集成（0% 覆盖率），`accessible=false` 为正常状态
  - 光标标注 `source="tracked" confidence="low"`（硬件 overlay，截图不含光标）
  - 截图坐标与 uinput 坐标 1:1（KMS 2560×1600 = 截图尺寸）

### Phase 3: Intelligence Layer（规划中）

- **P3A 目标**：先做 GUI parser，而不是先做 agent。主目标是把整屏 observation 转成结构化元素与布局摘要。
- **顶层抽象**：继续保持 `screen` 作为单一读侧入口；`screenshot` / `accessibility` / `vision` 统一视为 perception provider，而不是拆成多个“看”的 tool。
- **接口方向**：在 `screen` 下区分 state query（如 `size` / `cursor`）与 perception query（如 `snapshot` / `analyze` / `image`）。
- **视觉识别**：OmniParser / GUI grounding / OCR / SoM 作为 vision provider 能力候选，服务于 `analyze` 的结构化输出，而不是直接决定顶层 API。
- **语义交互**：`find` / `click_element` 留在 P3B 或后续阶段，建立在 P3A parser 结果之上。
- **模型选型原则**：按当时 leaderboard 现查，不依赖历史数字。同一资源量级选最优，用户通过配置切换。
- **讨论草案**：详见 [PHASE3A-DRAFT.md](PHASE3A-DRAFT.md)。

---

## 4. 关键技术决策与修正

### 4.1 Benchmark 数字核验

V1/V2 中部分 benchmark 数字有误。以下为已核实或标注口径的数据：

| 数据 | 数值 | 来源/口径 |
|------|------|-----------|
| uinput 鼠标延迟 | <1ms | 内核级，实测 |
| xdg-desktop-portal 截图延迟 | ~56ms avg | Phase 2 Spike 实测（5 次） |
| OmniParser v2 (4090) | ~800ms | MS 官方 |
| OmniParser v2 + GPT-4o (ScreenSpot-Pro) | ~39.6% | MS 官方，已核实 |
| ScreenSeekeR (ScreenSpot-Pro) | ~48% | 当时 SOTA 量级 |
| LLM 推理占任务延迟 | 75-94% | OSWorld-Human 口径 |

> ⚠️ **选型时务必按当时 leaderboard 现查**。ScreenSpot-Pro 上任何宣称破 60% 的 7B 模型请先核源——该基准目标元素平均只占画面 0.07%。

### 4.2 AT-SPI2 覆盖率：Linux ≠ Windows

V1 称「无障碍树覆盖约 80% 应用」——这是 **Windows UIA 口径**。Linux AT-SPI2 实测：

- COSMIC compositor/settings/panel：**0%**（不注册 AT-SPI2）
- GTK/Qt/Electron 应用：**0%**（当前 COSMIC 环境下无注册）
- 仅 WebKit 沙箱进程曾有注册（P0 发现，P2 时也消失）

**后果**：视觉路径是 Linux 感知主力，P3 视觉模型的优先级应前移。架构的降级链设计（树→视觉→VLM）在 Linux 上实际从第二级起步。

### 4.3 Wayland 限制

- uinput 能**写**输入 ≠ 能**读**状态。光标位置、全屏截图均需 portal/compositor 配合
- COSMIC 使用硬件光标 overlay，截图不含光标 → 无法做视觉光标校准
- COSMIC compositor 不暴露 D-Bus 输出/窗口管理接口 → 窗口感知推迟

### 4.4 差分截图的 Token 节省 ≠ Wall-Clock 加速

V1 称差分区域「快约 3 倍」——这是把 input token 数与推理 wall-clock 当线性关系。实际 input token 影响 prefill、output token 主导 decode，不是 1:1。差分截图省 token（进而省钱、略省 prefill）是真的，但具体加速倍数无依据。

---

## 5. 技术参考

**关键项目**：Anthropic Computer Use（跨平台纯视觉，闭源）｜ OmniParser v2（MS, CC-BY-4.0）｜ FlaUI-MCP（Windows, MIT）｜ kwin-mcp（Linux/KDE, MIT）｜ gui-user（Linux/X11 AT-SPI2 + 批量）

**关键论文**：CogAgent (CVPR'24)｜ScreenAI (IJCAI'24)｜SeeClick (ACL'24)｜UI-TARS (2025, ByteDance)｜GUI-Actor (2025, MS)｜UGround/SeeAct-V (ICLR'25)

---

## 6. 当前活跃文档索引

| 用途 | 文档 |
|------|------|
| 阶段状态追踪 | [ROADMAP.md](ROADMAP.md) |
| P0 Spike 计划 | [PHASE0-SPIKE.md](PHASE0-SPIKE.md) |
| P0 Spike 结果 | [PHASE0-SPIKE-RESULTS.md](PHASE0-SPIKE-RESULTS.md) |
| P1 实现计划 | [PHASE1-IMPLEMENTATION.md](PHASE1-IMPLEMENTATION.md) |
| P1 实测问题 | [P1-potential-issue.md](P1-potential-issue.md) |
| P2 Spike 计划 | [PHASE2-SPIKE.md](PHASE2-SPIKE.md) |
| P2 Spike 结果 | [PHASE2-SPIKE-RESULTS.md](PHASE2-SPIKE-RESULTS.md) |
| P2 实现计划 | [PHASE2-IMPLEMENTATION.md](PHASE2-IMPLEMENTATION.md) |
| P3A 讨论草案 | [PHASE3A-DRAFT.md](PHASE3A-DRAFT.md) |
| P2 潜在问题 | [P2-potential-issue.md](P2-potential-issue.md) |
| 跨 session 决策 | [FUTURE-REFERENCE.md](FUTURE-REFERENCE.md) |
| Agent 行为规约 | [../AGENTS.md](../AGENTS.md) |

---

*本文档随项目实际进展持续更新。架构决策以当前实测数据为准，不依赖历史文档中的未验证数字。*
