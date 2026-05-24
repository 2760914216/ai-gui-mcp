# AI GUI MCP — 项目总体规划

> 为 AI 编程助手提供 GUI 感知与操作能力的 MCP 工具。

## 阶段总览

| Phase | 内容 | 状态 |
|-------|------|------|
| **0. Spike** | 技术栈验证（uinput/键盘/坐标/AT-SPI2/截图） | ✅ 已完成 |
| **1. Action Layer** | MCP server + 鼠标键盘模拟 | ✅ 已完成 |
| **2. Perception** | 截图 + 无障碍树 | ✅ 已完成 |
| **3A. Intelligence Layer** | PerceptionService + provider 抽象 + GUI parser | 进行中 |
| **4. Human-like** | 类人交互（贝塞尔轨迹等） | 规划中 |
| **5. Multi-platform** | Windows + macOS | 远期 |
| **6. Polish** | 安全、性能、录制回放 | 远期 |

## 架构原则

- **策略可配置**：schema 配置文件控制行为
- **最小工具面**：减少 AI 选择负担
- **语义优先，坐标兜底**：能用元素引用就不用像素坐标
- **后端可替换**：P1 即建 `InputBackend` 抽象接口

## 当前阶段

→ [docs/PHASE0-SPIKE-RESULTS.md](PHASE0-SPIKE-RESULTS.md) — P0 验证结论
→ [docs/PHASE1-IMPLEMENTATION.md](PHASE1-IMPLEMENTATION.md) — P1 开发参考
→ [docs/P1-potential-issue.md](P1-potential-issue.md) — P1 实测问题与修复状态

## 后续阶段参考

→ [docs/PHASE3A-SPIKE.md](PHASE3A-SPIKE.md) — P3A 模型选型 Spike 计划
→ [openspec/changes/archive/2026-05-24-phase3a-intelligence-layer/](../openspec/changes/archive/2026-05-24-phase3a-intelligence-layer/) — P3A 变更 artifacts
→ [docs/P2-potential-issue.md](P2-potential-issue.md) — P2 潜在问题分析（P2 已完成，分析留存）
→ [docs/FUTURE-REFERENCE.md](FUTURE-REFERENCE.md)（跨 session 讨论记录）
