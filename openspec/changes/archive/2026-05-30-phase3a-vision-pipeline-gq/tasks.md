## 1. 依赖与配置

- [x] 1.1 修改 `pyproject.toml` — 添加 `[project.optional-dependencies]` 的 `vision` extra：torch>=2.0.0, transformers>=4.45.0, groundingdino-py>=0.4.0, accelerate>=0.26.0, bitsandbytes>=0.41.0, Pillow>=10.0.0
- [x] 1.2 修改 `src/config.py` — 新增 `VisionConfig` pydantic 模型，读取 `perception.providers.vision` 配置段，默认 `backend: "dummy"`
- [x] 1.3 修改 `config.yaml` — 新增 `perception.providers.vision` 完整配置段（pipeline_gq 各项参数含默认值，model_path 留空占位）
- [x] 1.4 验证配置读取：`config.yaml` 缺省 `vision` 段时 back to "dummy"，指定 "pipeline_gq" 时正确解析 `VisionConfig`

## 2. GDINO 检测器模块

- [x] 2.1 创建 `src/providers/gdino/__init__.py` — 导出 `GroundingDINODetector`
- [x] 2.2 创建 `src/providers/gdino/detector.py` — `GroundingDINODetector` 类：
  - `__init__(model_path, quantization=None)` — import guard（torch/transformers 缺失时抛 ImportError）
  - `initialize()` — 加载模型到 GPU，应用量化配置
  - `detect(image: PIL.Image, text_prompt: str, box_threshold: float) -> list[DetectedBox]` — 单次推理，返回 `(bbox: [x1,y1,x2,y2], label: str, confidence: float)` 列表
  - `shutdown()` — 卸载模型，释放显存
  - 分辨率缩放：输入 `img_scale` 参数，推理在缩放图上进行，bbox 坐标映射回原始分辨率
- [x] 2.3 添加 `DetectedBox` dataclass — 字段: `bbox: list[int]`, `label: str`, `confidence: float`
- [x] 2.4 添加 GDINO `text_prompt` 默认值（从 spike 验证的 prompt 导出）：`"button. input field. text label. checkbox. radio button. tab. menu item. link. window. dialog. sidebar. toolbar. panel. list. table. form field."`
- [x] 2.5 添加单元测试 `src/tests/test_gdino.py` — mock torch/transformers，验证 detect() 输入输出格式、坐标映射、import guard 错误信息

## 3. Qwen 描述器模块

- [x] 3.1 创建 `src/providers/qwen_vl/__init__.py` — 导出 `QwenVLDescriptor`
- [x] 3.2 创建 `src/providers/qwen_vl/descriptor.py` — `QwenVLDescriptor` 类：
  - `__init__(model_path, quantization="q4")` — import guard
  - `initialize()` — 加载 Qwen3-VL-4B 模型到 GPU，应用 Q4 量化
  - `describe(crop: PIL.Image, coarse_category: str) -> ElementDescription` — 单区域推理，返回 `(type: str, text: str | None, confidence: float)`
  - `shutdown()` — 卸载模型
  - 裁剪区域扩展：以 bbox 为中心扩展 1.2×
  - token 输出限制：`max_new_tokens` 可配置（默认 64），`repetition_penalty=1.1`
- [x] 3.3 设计 Qwen describe prompt：接收 `coarse_category` 参数，在对应候选集中约束 type 选择（interactive → 7 种，structural → 8 种，unknown → 全部 17 种）；要求输出 `{type, text, confidence}` JSON
- [x] 3.4 添加 `ElementDescription` dataclass — 字段: `type: str`, `text: str | None`, `confidence: float`
- [x] 3.5 添加单元测试 `src/tests/test_qwen_vl.py` — mock transformers，验证 describe() 输出解析、prompt 生成带粗分类约束、import guard

## 4. 类型映射器

- [x] 4.1 创建 `src/providers/gdino/label_mapper.py` — `GdinoLabelMapper` 类：
  - `map(label: str) -> str` — 返回粗分类 "interactive" / "structural" / "unknown"
  - 维护关键词映射表（基于 spike 中 GDINO 实际产出的 label 种类，约 15-20 条）
  - 未匹配 label 降级为 "unknown"
- [x] 4.2 添加 `QwenTypeMapper` 工具函数 — `constrain_by_category(coarse: str) -> list[str]` 返回对应候选类型列表
- [x] 4.3 添加单元测试 `src/tests/test_label_mapper.py` — 覆盖已知 label 映射、未知 label 降级、各粗分类候选集正确性

## 5. 后处理管道

- [x] 5.1 创建 `src/providers/vision_postprocess.py` — 后处理工具模块：
  - `filter_by_area(elements, screen_area, ratio=0.5)` — 过滤 >50% 屏幕面积的 bbox
  - `deduplicate_by_iou(elements, threshold=0.5)` — IoU 去重，保留高 confidence 者，添加 `duplicate_element` warning
  - `adaptive_min_crop_size(image_width, image_height)` — 返回 32 或 16
  - `should_skip_crop(bbox, min_size)` — 判断裁剪区域是否小于最小尺寸
- [x] 5.2 添加单元测试 `src/tests/test_vision_postprocess.py` — 覆盖面积过滤、IoU 去重（不同 confidence）、IoU 去重（相同 confidence）、小图/大图 min_crop 自适应、溢出 bbox 裁剪

## 6. PipelineGQVisionProvider 主类

- [x] 6.1 修改 `src/providers/vision.py` — 添加 `PipelineGQVisionProvider(VisionProvider)`：
  - `__init__(config: VisionConfig)` — 存储配置，不加载模型，检查依赖可用性
  - `initialize()` — 懒加载 GDINO + Qwen 模型
  - `shutdown()` — 卸载模型
  - `parse(image: RawImage, a11y_hints=None) -> AnalysisResult` — 完整两阶段管道：
    1. `PIL.Image.open(BytesIO(image.bytes))` → resize by `img_scale`
    2. GDINO detect → raw detections
    3. 面积过滤 → IoU 去重 → min_crop_size 过滤
    4. 对每个保留的 bbox：GDINO label → 粗分类 → crop 区域 → Qwen describe → 映射到 `ParsedElement`
    5. 组装 `AnalysisResult`：`overall_quality` 根据元素数量设定（>10 → "high", >0 → "medium", 0 → "low"），`elements` 按 id 排序
    6. 生成 `snapshot_id`（基于时间戳或 hash）
  - 首次 `parse()` 调用时隐式 `initialize()`
  - 解析 Qwen 输出的 JSON：异常时跳过该区域（best-effort），静默处理
  - `effort` → box_threshold 映射（low→0.17, high→0.13）
- [x] 6.2 更新 `src/providers/__init__.py` — 导出 `PipelineGQVisionProvider`
- [x] 6.3 添加单元测试 `src/tests/test_vision_pipeline_gq.py` — mock GDINO 和 Qwen 模块：
  - `parse()` 返回 AnalysisResult 含 elements
  - effort=low 使用 threshold 0.17
  - effort=high 使用 threshold 0.13
  - 零检测元素时返回空 elements，无 warning
  - `parse()` 首次调用触发隐式 `initialize()`
  - Qwen JSON 解析异常时跳过该区域而非崩溃
  - overall_quality 根据元素数量正确设定

## 7. Server 集成

- [x] 7.1 修改 `src/server.py` `main()`：
  - 读取 `VisionConfig` 从 `config.yaml`
  - 当 `vision.backend == "pipeline_gq"` 时，实例化 `PipelineGQVisionProvider(config)` 替换 `DummyVisionProvider`
  - 当 `vision.backend == "dummy"` 时保持原有行为
  - 注入到 `PerceptionService(vision_provider=...)`
- [x] 7.2 添加空闲卸载 timer 逻辑到 `server.py`（或在 `PerceptionService` 层）：
  - 每次 `analyze()` 调用重置 timer
  - timer 到期后调用 `VisionProvider.shutdown()`（如果 provider 支持）
  - timer 间隔读取 `idle_shutdown_sec` 配置项
- [x] 7.3 确保非 GPU 用户不受影响：未安装 `[vision]` extra 时，`backend: "dummy"`（默认）下 server 正常启动，`backend: "pipeline_gq"` 时 `PipelineGQVisionProvider.__init__` 在 import 阶段给出清晰的 `ImportError`
- [x] 7.4 更新 `list_tools()` 中 screen tool 的 schema——确保 `analyze` action 描述提及现在支持真实视觉解析

## 8. 测试与验证

- [x] 8.1 运行完整测试套件：`pytest src/tests/ -v` — 所有已有测试通过，新增测试通过，零回归
- [x] 8.2 运行 `lsp_diagnostics` 检查所有新增/修改文件：`src/providers/vision.py`, `src/providers/gdino/`, `src/providers/qwen_vl/`, `src/providers/vision_postprocess.py`, `src/config.py`, `src/server.py` — 零错误
- [x] 8.3 配置回退验证：`backend: "dummy"` 时 `screen(action="analyze")` 返回空的 `AnalysisResult`（保持现有行为）
- [x] 8.4 （暂跳过，需 GPU）真实环境端到端测试：`screen(action="analyze")` → 返回含元素的 `AnalysisResult`，将在实现完成后手动验证

## 9. 文档

- [x] 9.1 更新 `docs/PHASE3A-SPIKE-RESULTS.md` — 标记 Pipeline GQ 已从 spike 进入实现阶段，添加交联到本 change
- [x] 9.2 更新 `AGENTS.md` — 添加本 change 路径到项目规约表
- [x] 9.3 更新 `config.yaml` 注释 — 在 `perception.providers.vision` 段添加参数说明注释
