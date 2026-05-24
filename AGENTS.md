# AGENTS.md — AI GUI MCP

## 以前 Agent 犯过的错

- **假设 X11 环境** — 本项目目标是 Linux Wayland（COSMIC）。X11 方案（pyautogui/XTest）不可用，技术选型必须基于 Wayland 实测。
- **P1 加入截图模块** — AI 在 P1 阶段无视觉能力，截图 base64 对 AI 无意义。截图在 P2（引入无障碍树后）作为 `screen_snapshot()` 的一部分加入。
- **盲信网上基准数字** — 聚合来源的 benchmark（如 UI-TARS-7B 在 ScreenSpot Pro 上）可能串表。选型时按当时 leaderboard 现查。
- **跨平台乐观估计** — AT-SPI2 覆盖率 70-80% 是 Windows UIA 口径，Linux 实际差得多。未经实测不写覆盖率数字。
- **工具粒度过多** — 15+ 细粒度 tool 会造成 AI 选择困难。本项目采用 3-4 个大 tool + action 参数的设计。
- **跳过技术验证直接编码** — 动手前必须跑 Phase 0 Spike，实测 uinput/键盘/分辨率/AT-SPI2 在真实环境中的表现。
- **sudo 盲用** — 遇到需要 sudo 的操作时，先考虑有无替代方案（如用户级权限、非 root 路径），将 sudo 需求与替代方案告知用户，由用户决断是否使用 sudo。
- **Question 被 TODO hook 拦截** — 在 TODO 项未完成时直接向用户提问会被 hook 阻止。如需在任务中途向用户提问，使用 `question` 工具而非直接文字提问。
- **跳过视觉验证直接推进计划** — Spike 验证中部分测试项需要用户人工视觉确认（如"观察鼠标是否移动"、"确认截图中光标是否可见"）。Agent 在未等待用户确认的情况下直接标记验证通过并推进到下一阶段。人工视觉验证项必须在 TODO 中保留 pending 状态，等待用户在 TODO 中标记完成后再推进。

## 项目规约

| 项目 | 位置 |
|------|------|
| 总体规划 | [docs/ROADMAP.md](docs/ROADMAP.md) |
| P0 技术验证 | [docs/PHASE0-SPIKE.md](docs/PHASE0-SPIKE.md) |
| P1 实现计划 | [docs/PHASE1-IMPLEMENTATION.md](docs/PHASE1-IMPLEMENTATION.md) |
| P0 验证结果 | [docs/PHASE0-SPIKE-RESULTS.md](docs/PHASE0-SPIKE-RESULTS.md) |
| 跨 session 参考 | [docs/FUTURE-REFERENCE.md](docs/FUTURE-REFERENCE.md) |
| P1 实测问题 | [docs/P1-potential-issue.md](docs/P1-potential-issue.md) |
| P2 潜在问题分析 | [docs/P2-potential-issue.md](docs/P2-potential-issue.md) |
| P2 技术验证 | [docs/PHASE2-SPIKE.md](docs/PHASE2-SPIKE.md) |
| P2 验证结果 | [docs/PHASE2-SPIKE-RESULTS.md](docs/PHASE2-SPIKE-RESULTS.md) |
| P2 实现计划 | [docs/PHASE2-IMPLEMENTATION.md](docs/PHASE2-IMPLEMENTATION.md) |
| V3 路线图（设计参考） | [docs/AI-GUI-MCP-ROADMAP-v3.md](docs/AI-GUI-MCP-ROADMAP-v3.md) |
| 开发环境及规约 | [openspec/config.yaml](openspec/config.yaml) |

### 技术栈（当前阶段）

- **语言**: Python 3.10+
- **MCP SDK**: `mcp>=1.0.0`，transport 用 stdio
- **输入**: `evdev` + uinput（内核级，Wayland 透明）
- **数据模型**: pydantic >= 2.0
- **配置**: pyyaml
- **测试**: pytest
- **打包**: uv + pyproject.toml

### 架构约定

- **后端可替换** — P1 即建 `InputBackend` 抽象接口（`src/backends/base.py`），当前仅 uinput 实现。
- **最小工具面** — 4 个 tool：mouse / keyboard / screen / batch，通过 action 参数区分操作。
- **分层解耦** — Action → Perception → Intelligence 三层独立演进，当前 P1 只做 Action。
- **先验证再编码** — Phase 0 Spike 先过，再写代码。

### 目录树

```
ai-gui-mcp/
├── AGENTS.md                         ← 本文件
├── oh-my-opencode.json               ← OpenCode agent 配置
├── opencode.jsonc                    ← OpenCode 项目配置
├── pyproject.toml                    ← Python 项目元数据
├── config.yaml                       ← 运行时配置
├── openspec/                         ← OpenSpec 规约驱动
│   ├── config.yaml
│   ├── changes/
│   └── specs/
├── docs/                             ← 项目文档
│   ├── ROADMAP.md
│   ├── PHASE0-SPIKE.md
│   ├── PHASE0-SPIKE-RESULTS.md
│   ├── PHASE1-IMPLEMENTATION.md
│   ├── PHASE2-SPIKE.md
│   ├── PHASE2-SPIKE-RESULTS.md
│   ├── PHASE2-IMPLEMENTATION.md
│   ├── FUTURE-REFERENCE.md
│   ├── P1-potential-issue.md
│   ├── P2-potential-issue.md
│   └── AI-GUI-MCP-ROADMAP-v3.md
├── src/                              ← 源代码
│   ├── __init__.py
│   ├── server.py
│   ├── config.py
│   ├── models.py
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── uinput.py
│   │   ├── portal.py
│   │   └── screen.py
│   └── tests/
│       ├── test_mouse.py
│       ├── test_keyboard.py
│       └── test_batch.py
├── ignore_draft/                     ← 忽略，草稿和临时笔记
│   ├── overview.md
│   ├── Suggestions-For-ROADMAP.md
│   └── NextToDo
└── .sisyphus/                        ← Sisyphus agent 内部
```

### 禁止

- 跳过 Phase 0 Spike 直接写代码
- 在 P1 引入截图/视觉/无障碍树
- 使用 X11 专用方案（pyautogui, python-xlib, XTest）
- 不加实测引用覆盖率数字

### 输出语言

- Agent 输出的文档及回答使用中文
