# Future Reference — 后续阶段参考

> 跨 session 共享。包含已确认的决策、待讨论事项、用户建议。

## 用户的核心反馈 (2026-05-20)

1. **文档分阶段**：按 Phase 顺序写，当前只写到 P1，其余信息放本文档供后续参考。
2. **一次只讨论少量问题**：不要一次性抛出太多信息。
3. **跨 session 注意**：文档需要考虑跨对话的连续性。
4. **Schema 配置**：各策略可配置（如优先无障碍树 → 降级到键鼠模拟），需设计配置文件。
5. **最小工具面**：暴露给 AI 的工具过多会导致选择困难。
6. **类人目的不是仿真**：是让 AI 感受交互并判断 UI 质量（按钮位置是否合理、操作是否繁琐）。
7. **触控手势**：整个项目不做。
8. **录制真实操作学习**：不做，没有训练能力。
9. **多显示器**：不需要。
10. **部署**：仅本地。
11. **许可证**：质量优先，GPL 无顾虑。
12. **安全**：此项目的开发者习惯看着 AI 操作，但不代表所有用户都习惯，需思考是否有更好方案（AI 占用屏幕，用户无法做其他事）。

## 已确认的架构决策

### 模型选型（Phase 3）

- 采用 **provider + API + API key 模式**，不区分本地/云端
- 同一资源量级选最优，用户通过配置切换
- GPU 需求可接受，但必须保留云端选项（无 GPU 用户可用 API）
- 本地模型（如 UI-TARS-7B）可处理常见 GUI 场景
- 云端 VLM 作为复杂场景的降级
- ⚠️ v2 审阅指出：原「UI-TARS-7B, ScreenSpot Pro 61.6%」数字有误，7B 模型不可能超 72B 版本，且该基准当时最强方法 ~48%。选型时按当时 leaderboard 现查，不依赖本文档数字。

### 无障碍树范围（Phase 2）

AT-SPI2 覆盖范围：
- ✅ GTK 应用（GNOME 全家桶）
- ✅ Qt 应用（KDE 全家桶）
- ✅ Java Swing/AWT
- ✅ Firefox
- ⚠️ Electron 部分覆盖
- ❌ 游戏、Wine/Proton、FLTK、自定义工具包

⚠️ v2 审阅指出：原「覆盖率 70-80%」是 Windows UIA 口径。Linux AT-SPI2 实际覆盖可能显著更低，Qt 时好时坏、Electron 基本无树、Wayland 原生应用更糟。视觉层可能需要承担 40-60% 的实际工作。**Phase 0 需用目标应用实测确认。**

### 截图方案（Phase 1-2）

PipeWire：
- 优点：Wayland 标准，通过 xdg-desktop-portal 跨 compositor，<17ms 延迟
- 缺点：需 portal 集成（有时不稳定），不兼容无 portal 的极简 compositor

grim+slurp / wlr-screencopy：
- 优点：极简，wlroots compositor 直接支持
- 缺点：仅 wlroots 系（Sway, Hyprland, river），不通用

→ Phase 1 先用 PipeWire + portal（最通用），后续按需加 wlr 方案。

## 待讨论事项（按 Phase 分组）

### Phase 1 需确认

> 所有 P1 议题已在 PHASE1-IMPLEMENTATION.md 中决定：鼠标坐标用内部追踪、Transport 用 stdio、工具面采用 action 参数设计。

### Phase 2 需确认

> 📄 详见 [P2-potential-issue.md](P2-potential-issue.md) — Phase 2 潜在问题完整分析（7 个问题 + 优先级 + 建议）

| # | 事项 |
|---|------|
| 4 | 无障碍树库：`pyatspi2` vs `dasbus` |
| 5 | 差分截图实现方案 |
| 6 | PipeWire 跨 compositor 兼容性 |
| 7 | `screen_snapshot()` 语义重定义（AT-SPI2 覆盖率 ~5% 现实下） |
| 8 | 光标校准协议（解决 P1 内部坐标与屏幕坐标脱节） |
| 9 | D-Bus 异步模型选型（dbus-python + GLib vs dbus-next asyncio） |
| 10 | 工具面设计：perception 能力如何融入现有 4-tool 结构 |
| 11 | ScreenBackend 与 InputBackend 的职责边界 |
| 12 | P2 测试策略（D-Bus mock、AT-SPI2 mock、差分算法测试） |

### Phase 3 需确认

| # | 事项 |
|---|------|
| 7 | 默认策略：本地模型优先 vs API 优先 |
| 8 | 本地模型具体选型与部署方式 |

### Phase 4+ 需确认

| # | 事项 |
|---|------|
| 9 | 多语言支持（中文无障碍树/OCR） |
| 10 | Headless 模式（虚拟显示） |
| 11 | 安全机制设计 |
| 12 | Windows/macOS 具体方案 |

## 疑问记录

| 疑问 | 状态 |
|------|------|
| a. 本地模型能力够吗？→ 够处理 80% 常见 GUI，复杂场景需云端降级 | ✅ 已讨论 |
| b. PipeWire vs grim 各有什么优缺点？→ 见上方截图方案 | ✅ 已讨论 |
| c. 无障碍树范围多大？是否之外就得用模型？→ 上限 70-80%（Windows UIA 口径），Linux AT-SPI2 在 COSMIC 实测仅 ~5%（见 SPIKE-RESULTS.md）。视觉层需承担 ~95% 感知工作 | ✅ 已讨论 |
| d. Claude Computer Use 是否 macOS 专用？→ 否，Linux 可用（Docker+X11 参考实现） | ✅ 已讨论 |

## 技术参考

> 详见原始 ROADMAP.md 第 5 节（关键参考项目、论文、数据）。
> 此处仅保留摘要。

### 关键数据

| 指标 | 数值 |
|------|------|
| uinput 鼠标延迟 | <1ms（内核级） |
| PipeWire 截图 | <17ms p50 @ 60fps |
| OmniParser (4090) | ~800ms |
| LLM 推理占任务延迟 | 75-94% |

### 参考项目

- OmniParser (MS, CC-BY-4.0): 视觉→结构化元素 + SoM
- FlaUI-MCP (MIT): Playwright 风格元素引用
- kwin-mcp (MIT): Linux/KDE Wayland + AT-SPI2
- gui-user: Linux/X11 AT-SPI2 + 批量操作
