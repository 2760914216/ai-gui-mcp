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

### 感知抽象（P3A，2026-05-24 讨论结论）

- **不引入第二个“看”入口**：不要让 `screen` + `see` 并存。继续保持 `screen` 作为单一读侧入口。
- **统一点在 provider/result 层，不在 tool 命名层**：`screenshot` / `accessibility` / `vision` 都只是 perception provider。
- **顶层接口按语义分层**：
  - state query：`screen(size)` / `screen(cursor)`
  - perception query：`screen(snapshot)` / `screen(analyze)` / `screen(image)`
- **P3A 主目标**：先做 GUI parser（结构化元素 + 布局摘要），不是先做语义点击。
- **Observation 语义**：
  - `snapshot` 创建 observation handle
  - `analyze` 是 snapshot 的派生结果
  - `image` 按需返回 raw payload
- **缓存/历史策略**：session-scoped 语义；初版允许退化为当前 MCP 进程内默认 session；只保留短期内存历史，采用 `N + TTL + memory budget` 联合淘汰。
- **P3A 非目标**：diff、region 局部分析、analyze profile、semantic click、长期持久化、复杂 agent planning。
- 详见：[PHASE3A-DRAFT.md](PHASE3A-DRAFT.md)

### 无障碍树范围（Phase 2）

> ⚠️ **2026-05-23 实测修正**：COSMIC Wayland 上 AT-SPI2 覆盖率为 **0%**（PHASE2-SPIKE-RESULTS）。COSMIC compositor/settings/panel、GTK/Qt/Electron 应用均不注册 AT-SPI2。P0 曾发现 WebKit 沙箱进程有注册（~5%），P2 重新验证时也已消失。
>
> 以下为 AT-SPI2 在其他 Linux 桌面环境（GNOME/KDE）上的理论覆盖范围，非本项目 COSMIC 实测数据：

AT-SPI2 理论覆盖范围（GNOME/KDE 等传统桌面）：
- ✅ GTK 应用（GNOME 全家桶）
- ✅ Qt 应用（KDE 全家桶）
- ✅ Java Swing/AWT
- ✅ Firefox
- ⚠️ Electron 部分覆盖
- ❌ 游戏、Wine/Proton、FLTK、自定义工具包

> **对本项目的影响**：视觉路径是 Linux COSMIC 感知主力，P3 视觉模型优先级前移。AT-SPI2 仅作为 opportunistic 增强（不可用时静默降级）。

### 截图方案（Phase 2，已实现）

P2 实现方案：**xdg-desktop-portal + dbus-python**（非 PipeWire 直连）

- 调用 `org.freedesktop.portal.Desktop.Screenshot(interactive=false)`
- D-Bus 库选 `dbus-python`（dbus-next 存在 introspection bug，不可用）
- 线程桥接 GLib.MainLoop 监听异步 Response 信号
- 实测延迟：~56ms avg（2560×1600 PNG）
- 截图不含光标（COSMIC 硬件 overlay），坐标 1:1 映射

> P1 阶段未做截图（P1 仅有 mouse/keyboard/screen.size），P2 为截图实际实现阶段。

## 待讨论事项（按 Phase 分组）

### Phase 1 需确认

> 所有 P1 议题已在 PHASE1-IMPLEMENTATION.md 中决定：鼠标坐标用内部追踪、Transport 用 stdio、工具面采用 action 参数设计。

### Phase 2 已确认（✅ 2026-05-23 已完成）

> 📄 详见 [PHASE2-SPIKE-RESULTS.md](PHASE2-SPIKE-RESULTS.md) 和 [PHASE2-IMPLEMENTATION.md](PHASE2-IMPLEMENTATION.md)。
> P2 已于 2026-05-23 完成所有 Spike 验证并实现截图采集层。以下为最终决策：

| # | 事项 | P2 决策 |
|---|------|---------|
| 4 | 无障碍树库 | **放弃** — AT-SPI2 COSMIC 覆盖率 0%，不集成 |
| 5 | 差分截图 | **推迟** — 留给后续 P2-B |
| 6 | PipeWire 兼容性 | **转用 xdg-desktop-portal** — dbus-python + GLib 线程桥接 |
| 7 | `screen_snapshot()` 语义 | **screenshot-first** — elements 始终为空，accessible=false 为正常状态 |
| 8 | 光标校准 | **tracked cursor** — 硬件 overlay 截图不含光标，source="tracked" confidence="low" |
| 9 | D-Bus 异步模型 | **dbus-python** — dbus-next 存在 introspection bug 不可用 |
| 10 | 工具面设计 | **保持 4 tool** — screen 扩展 snapshot action，不引入新 tool |
| 11 | Backend 边界 | **ScreenBackend 独立于 InputBackend** — 新增 ScreenshotBackend 抽象 |
| 12 | 测试策略 | **分层测试** — 单元测试 mock D-Bus，集成测试需真实 Wayland 环境 |

### Phase 3 需确认

> P3A 核心议题已通过 [openspec/changes/archive/2026-05-24-phase3a-intelligence-layer/](../openspec/changes/archive/2026-05-24-phase3a-intelligence-layer/) 决议：
> - #7 默认策略 → 采用 provider 抽象，支持本地/云端模型切换（P3A-4 Spike 选型）
> - #8 本地模型选型 → 留待 P3A Spike 实测 OmniParser v2、UI-TARS、云 VLM 后确定
> - #9 `AnalysisResult` 兼容演进 → 采用三层公开模型（SnapshotResult / AnalysisResult / ScreenState），`ScreenSnapshot` 降级为内部模型
> - #10 受控枚举 → 第一版 element.type（17 值）、region.type（10 值）、warning.code（7 值）已冻结
> - #13 视觉 token 压缩 → 「Thinking with Visual Primities」(DeepSeek, 2026-04) 的 KV cache 4→1 压缩技术，未来处理 4K+ 高分辨率截图时的性能优化方向；Reference Gap 概念可作为 P3A 设计 bbox 输出的理论支撑

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
| c. 无障碍树范围多大？是否之外就得用模型？→ 上限 70-80%（Windows UIA 口径），Linux AT-SPI2 在 COSMIC 实测仅 ~5%（见 PHASE0-SPIKE-RESULTS.md）。视觉层需承担 ~95% 感知工作 | ✅ 已讨论 |
| d. Claude Computer Use 是否 macOS 专用？→ 否，Linux 可用（Docker+X11 参考实现） | ✅ 已讨论 |

## 技术参考

> 详见 [AI-GUI-MCP-ROADMAP-v3.md](AI-GUI-MCP-ROADMAP-v3.md) 第 5 节（关键参考项目、论文、数据）。
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
