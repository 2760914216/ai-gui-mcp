## Why

架构 C（Qwen3-VL-8B INT4 单模型 GUI parsing）在 COSMIC 实测中失败：元素召回集中于标题栏区域，严重 repetition loop，整体不可用。单模型承担 detection + description + classification 全部职责导致注意力分散和 token 坍缩。管道方案将"看"拆解为独立优化的检测→描述两阶段，用开放词汇检测器（Grounding DINO-T）解决 COSMIC 未见 toolkit 的泛化问题，用小 VLM（Qwen3-VL-4B Q4）在裁剪区域做精细元素识别——各组件在 11.94 GB GPU 约束下均可运行。

## What Changes

- 新增独立 spike 验证脚本 `scripts/spike_pipeline_gq.py`，部署 Grounding DINO-T（检测）+ Qwen3-VL-4B Q4_K_M（描述）两阶段管道
- 复用现有 8 张 COSMIC 2560×1600 测试截图（`docs/spike-screenshots/`），不新增测试集
- 复用现有可视化脚本 `scripts/visualize_bboxes.py`，不做修改
- 产出 Round 1 验证结果到 `docs/spike-results/pipeline-round1/`（`_analysis.json` + `_annotated.png` + `_elements.txt` 格式与架构 C 对齐）
- **不修改** `src/providers/vision.py`、`src/services/perception.py`、`src/server.py` 或任何生产代码路径
- **不引入** 新 Python 依赖到 `pyproject.toml`（spike 脚本自含依赖声明）

## Capabilities

### New Capabilities

- `pipeline-vision-spike`: Round 1 管道验证——Grounding DINO-T 开放词汇 UI 元素检测 + Qwen3-VL-4B Q4 区域裁剪描述，在 COSMIC 8 张截图集上产出结构化元素列表与可视化叠加图，人工评估召回率和精度

### Modified Capabilities

（无——spike 验证不修改现有 spec）

## Impact

- 受影响的代码: `scripts/spike_pipeline_gq.py`（新建）、`docs/spike-results/pipeline-round1/`（新建目录）
- 不影响的代码: `src/` 全部生产代码、`pyproject.toml`、`config.yaml`
- 依赖: Grounding DINO-T（HuggingFace `IDEA-Research/grounding-dino-tiny`）、Qwen3-VL-4B-Instruct（已下载至本地）、`visualize_bboxes.py`（已存在）
- 风险: Grounding DINO-T 的 COSMIC UI 检测质量未知（开放词汇理论上比固定类别泛化好，未经实测）；Qwen3-VL-4B Q4 在小裁剪区域上的描述质量待验证
