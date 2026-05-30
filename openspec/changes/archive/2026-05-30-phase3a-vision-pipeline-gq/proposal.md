## Why

`VisionProvider` 接口已在 P3A-1~3 中抽象完成，`PerceptionService` 已完整接线，但 `vision.backend` 仍为 `"dummy"`——`screen(action="analyze")` 返回空结果。Pipeline GQ（Grounding DINO-T + Qwen3-VL-4B）两阶段管道在 COSMIC 8 张截图集上完成 spike 验证，Go 结论明确：元素召回率显著优于单模型方案，无 repetition loop，VRAM 6 GB 在 11.47 GB GPU 上可行。现在是时候将 Dummy 替换为真实实现，打通 `analyze` 全链路。

## What Changes

- 新增 `PipelineGQVisionProvider(VisionProvider)`：两阶段管道（GDINO 检测 → Qwen 描述 → 类型映射 → 后处理）
- `config.yaml` 新增 `perception.providers.vision` 配置段：模型路径、量化参数、检测阈值、空闲卸载 TTL、双 effort 模式
- 新增 `src/providers/gdino/`：Grounding DINO-T 检测器封装（模型加载、开放词汇推理、bbox 输出）
- 新增 `src/providers/qwen_vl/`：Qwen3-VL-4B 描述器封装（模型加载、裁剪区域推理、类型/文本/置信度输出）
- 修改 `src/providers/__init__.py`：注册 `PipelineGQVisionProvider` 导出
- 修改 `src/config.py`：读取 `perception.providers.vision` 配置段
- 修改 `src/server.py`：根据配置选择 `VisionProvider` 后端（`dummy` / `pipeline_gq`）
- 修改 `pyproject.toml`：添加 Grounding DINO、transformers、torch 等 ML 依赖（标记为可选 extra `[vision]`）

## Capabilities

### New Capabilities

- `pipeline-gq-vision-provider`: 将 Pipeline GQ spike 验证通过的两阶段管道封装为正式 `VisionProvider` 实现，打通 `screen(action="analyze")` 全链路，产出含元素列表 + 置信度的 `AnalysisResult`

### Modified Capabilities

（无——现有 spec 的 requirement 级别行为不变，仅替换 provider 实现）

## Impact

- **受影响的代码**: `src/providers/vision.py`（新增实现类）、`src/providers/`（新增 gdino/ 和 qwen_vl/ 子模块）、`src/server.py`（provider 选择逻辑）、`src/config.py`（新配置段读取）、`config.yaml`（新配置段）、`pyproject.toml`（可选 ML 依赖）
- **不影响**: `PerceptionService`、`ObservationStore`、`ScreenshotProvider`、`AccessibilityProvider`、mouse/keyboard/batch 行为
- **依赖**: Grounding DINO-T（HuggingFace `IDEA-Research/grounding-dino-tiny`, Apache 2.0）、Qwen3-VL-4B-Instruct（HuggingFace, Apache 2.0）、transformers、torch、Pillow
- **风险**: GDINO/Qwen 模型需用户自行下载（~6 GB），首次实现仅支持已下载到本地路径的模式
