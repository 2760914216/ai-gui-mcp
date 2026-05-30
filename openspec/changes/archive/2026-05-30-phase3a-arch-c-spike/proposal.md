## Why

Phase 3A 需要选定 `VisionProvider` 的实现引擎。根据 PHASE3A-SPIKE.md 的决策路径，架构 C（通用 VLM Qwen3-VL-8B + prompt 工程）是最快上线、零额外依赖、许可最宽松（Apache 2.0）的方案。但 COSMIC 环境下的实际 Grounding 精度、VRAM 约束下的量化策略、prompt 稳定性均未经实测验证。上一个 agent 的 spike 尝试因**未充分明确细节就写计划**而失败（已 git 还原）。本次 spike 必须在明确所有已知约束和未确定变数后，用真实 COSMIC 截图跑通验证闭环。

## What Changes

- **修改 `AnalysisResult` / `ParsedElement` / `LayoutRegion` 的 bbox 格式**：从 `[x, y, w, h]` 改为 `[x1, y1, x2, y2]`（像素坐标，闭区间）。同步修改 `UIElement` 和 `ScreenSnapshot` 内部模型。**BREAKING** — 所有消费 bbox 的代码和测试需同步更新。
- **新增 spike 验证脚本** `scripts/spike_arch_c.py`：加载 Qwen3-VL-8B-Instruct（支持 INT8/INT4 量化），用结构化 prompt 解析 COSMIC 截图，输出 AnalysisResult JSON。
- **新增可视化验证脚本** `scripts/visualize_bboxes.py`：将 VLM 输出的 bbox 画在测试集原图上，在框边标注序号，同时输出对应序号识别内容的文本文件，方便人工核实。
- **更新 `AnalysisWarning.code` 枚举**：新增 `duplicate_element`（模型重复输出元素）、`hallucinated_element`（幻觉元素）等 spike 中可能出现的质量信号码。
- **不纳入本轮 change**：正式 `VisionProvider` 实现（spike 通过后才写）、OmniParser / KV-Ground 验证（后续架构）、Zoom-In 叠加（spike 中可选测试但不作为主目标）。

## Capabilities

### New Capabilities

- `arch-c-spike-validation`: Qwen3-VL-8B 在 COSMIC 截图上的 Grounding 验证闭环——包括模型加载与量化、结构化 prompt 设计、输出解析为 AnalysisResult、可视化 bbox 覆盖图、人工验收流程。
- `bbox-format-v2`: 将项目中所有 bbox 字段统一从 `[x, y, w, h]` 改为 `[x1, y1, x2, y2]` 像素坐标格式。覆盖 ParsedElement、LayoutRegion、UIElement 及消费方。

### Modified Capabilities

- `gui-parser-result`: ParsedElement.bbox 和 LayoutRegion.bbox 格式变更（BREAKING）。AnalysisWarning.code 枚举新增 `duplicate_element`、`hallucinated_element`、`model_parse_error`。
- `screen-perception-models`: UIElement.bbox 格式变更（BREAKING）。ScreenSnapshot.elements 中的 bbox 格式同步变更。

## Impact

- **Affected code**: `src/models.py`（ParsedElement, LayoutRegion, UIElement bbox 格式）、`src/providers/vision.py`（DummyVisionProvider 需适配新格式）、`src/tests/test_models_p3a.py`（测试需更新）、消费 AnalysisResult 的 `src/services/perception.py` 和 `src/server.py`
- **New files**: `scripts/spike_arch_c.py`、`scripts/visualize_bboxes.py`、`docs/PHASE3A-SPIKE-RESULTS.md`（spike 验证结果记录）
- **Dependencies**: 需安装 `transformers`、`torch`（已有 CUDA）、`Pillow`、`bitsandbytes`（INT8 量化）或 `auto-gptq`（INT4 量化）
- **No API surface change**: `screen()` 的 MCP tool 接口不变，仅内部数据格式调整
