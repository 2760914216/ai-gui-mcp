# P3A Spike — 视觉模型选型验证

> 目标：在 COSMIC 环境下实测候选视觉 GUI parser 模型，确定 P3A-4 的 `VisionProvider` 具体实现引擎。

## 背景

P3A 定义了 `VisionProvider` 抽象接口（`parse(image, a11y_hints) -> AnalysisResult`），当前使用 `DummyVisionProvider` 占位。P3A-4 需要选定具体模型并实现真实 `VisionProvider`。

## 候选模型

| 模型 | 类型 | 推理资源 | 参考延迟 | 特点 |
|------|------|----------|----------|------|
| **OmniParser v2** (Microsoft) | 本地 | RTX 4090 | ~800ms | 专为 GUI 理解优化，输出结构化元素 |
| **UI-TARS-7B** (ByteDance) | 本地 | 7B 参数，消费级 GPU | ~500ms | 轻量端侧模型，GUI grounding + action |
| **UI-TARS-72B** (ByteDance) | 本地/云端 | 72B 参数 | ~1.5s | 更强推理，复杂场景 |
| **Qwen-VL-Max** (云 API) | 云端 API | 无需本地 GPU | ~3s | 通用 VLM，需 prompt 工程适配 |
| **Claude 3.5 Sonnet** (云 API) | 云端 API | 无需本地 GPU | ~2-5s | 通用能力强，需 prompt 工程 |

> ⚠️ 基准数字仅供参考。选型时按当时 leaderboard 现查，不依赖历史数据。

## 评估指标

1. **元素召回率 (element recall)**: 人工标注的关键可交互元素中被模型正确识别的比例
2. **元素精度 (element precision)**: 模型输出的元素中正确的比例
3. **区域分类准确率 (region classification accuracy)**: `LayoutSummary.main_regions[].type` 分类是否正确
4. **屏幕类型准确率 (screen kind accuracy)**: `ScreenKind.kind` 分类是否正确
5. **延迟天花板 (latency ceiling)**: P95 延迟 ≤ 3s（本地）或 ≤ 10s（云端）
6. **bbox 交并比 (IoU)**: 识别元素的 bbox 与 ground truth 的交并比 ≥ 0.5

## 验收截图集

需要收集 10-15 张 COSMIC 真实截图，覆盖以下场景：

| # | 场景 | 应用 | 关键验证点 |
|---|------|------|------------|
| 1 | IDE 主界面 | VS Code / Lapce | editor 区域、sidebar、toolbar 识别 |
| 2 | IDE 右键菜单 | VS Code | menu 元素、menu item 识别 |
| 3 | 浏览器页面 | Firefox | content 区域、导航栏、tab 识别 |
| 4 | 浏览器弹窗 | Firefox 权限请求 | dialog 识别、按钮元素 |
| 5 | 系统设置 | COSMIC Settings | sidebar 导航、form 识别、toggle |
| 6 | 设置子页面 | COSMIC Settings → Display | 复杂 form 元素、下拉框 |
| 7 | 文件管理器 | COSMIC Files | list/table 视图、sidebar、toolbar |
| 8 | 文件管理器右键 | COSMIC Files context menu | 弹出菜单检测 |
| 9 | 终端 | COSMIC Terminal | terminal 区域、深色主题 |
| 10 | 对话框 | COSMIC Save File dialog | 文件选择器、输入框、按钮 |
| 11 | 混合窗口 | 多窗口重叠 | 前景/背景区分 |
| 12 | COSMIC 桌面 | 空桌面 + panel | 最小化界面，panel 检测 |
| 13 | 应用启动器 | COSMIC App Launcher | 搜索框、list 识别 |
| 14 | 通知弹窗 | COSMIC notification | 小型弹窗检测 |
| 15 | Flatpak 权限对话框 | Flatpak portal | portal 对话框识别 |

## Go/No-Go 标准

### 要求

- 候选模型必须满足 `parse(image, a11y_hints) -> AnalysisResult` 接口契约
- 延迟在可接受范围内（本地 ≤ 3s P95，云端 ≤ 10s P95）
- 至少一种模型满足以下最低质量指标：

### 最低质量阈值

| 指标 | Go 阈值 |
|------|---------|
| 可交互元素召回率 (button/input/checkbox 等) | ≥ 60% |
| 屏幕类型分类准确率 | ≥ 70% |
| 主区域检测率 (sidebar/toolbar/content) | ≥ 50% |

### 优先策略

1. 同一资源量级选当时 leaderboard 最优
2. 本地模型优先于云 API（延迟可控、隐私友好）
3. 必须保留云 API 降级路径（无 GPU 用户可用）

## 实施步骤

1. **收集验收截图集**（10-15 张 COSMIC 截图，上述场景）
2. **人工标注 ground truth**：元素 bbox、类型、屏幕类别、主区域
3. **搭建评估框架**：调用每个候选模型 parse 截图，计算上述指标
4. **分析结果**：对比延迟、召回率、精度、边界情况
5. **决策 + 实现**：选定模型，实现真实 `VisionProvider`

## 输出

- `docs/PHASE3A-SPIKE-RESULTS.md` — 详细测试结果与决策依据
- `src/providers/vision.py` — 替换 `DummyVisionProvider` 为真实实现
