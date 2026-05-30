## Context

当前状态：`VisionProvider` 抽象接口（`src/providers/vision.py`）已定义，`PerceptionService` 已完整接线，但实际实现为 `DummyVisionProvider`——`screen(action="analyze")` 返回空元素列表和 `image_unavailable` warning。

Pipeline GQ（Grounding DINO-T + Qwen3-VL-4B）两阶段管道在 8 张 COSMIC 2560×1600 截图上完成 spike 验证（`docs/PHASE3A-SPIKE-RESULTS.md` §7-14），Go 结论明确。平台约束：NVIDIA GPU 11.47 GB VRAM，CUDA 13.0，Wayland/COSMIC 环境。

云端降级（Qwen3-VL API）作为未来 fallback 本次不实现，但架构上通过 `FallbackVisionProvider` Composite 模式预留扩展点（本次仅实现 `PipelineGQVisionProvider`）。

## Goals / Non-Goals

**Goals:**
- 实现 `PipelineGQVisionProvider(VisionProvider)`：GDINO 检测 + Qwen 描述 + 类型映射 + 后处理，打通 `screen(action="analyze")` 全链路
- 模型懒加载 + 空闲 N 分钟后卸载（N 可配置，默认 10 分钟）
- 双 effort 模式：`effort="low"`（threshold 0.17，高精度）和 `effort="high"`（threshold 0.13，高覆盖）
- GDINO 粗分类约束 Qwen 细分类的两阶段类型映射
- 置信度初版使用 GDINO detection score
- bbox 后处理：面积过滤（>50% 屏幕忽略）、IoU 去重、min_crop_size 自适应
- `config.yaml` 中所有参数可配置（模型路径、阈值、TTL 等）
- ML 依赖标记为可选 extra `[vision]`，不破坏非 GPU 用户的安装

**Non-Goals:**
- 不实现云端 `CloudVisionProvider`
- 不实现 `FallbackVisionProvider` Composite（仅接口预留）
- 不利用 `a11y_hints` 参数（未来实现）
- 不实现 layout_summary / screen_kind 分类（管道聚焦元素检测）
- 不做 prompt 自动优化（首版 prompt 由 spike 验证的版本导出）
- 不做 Qwen 置信度区分化（等待 prompt 优化作为后续迭代）

## Decisions

### D1: 模块拆分 — gdino/ 和 qwen_vl/ 独立子模块

**选择**：检测器和描述器各自独立子模块，`PipelineGQVisionProvider` 组合二者。

```
src/providers/
├── vision.py           # VisionProvider ABC + PipelineGQVisionProvider（组合器）
├── gdino/
│   ├── __init__.py
│   └── detector.py     # GroundingDINODetector 类
├── qwen_vl/
│   ├── __init__.py
│   └── descriptor.py   # QwenVLDescriptor 类
└── ...
```

**理由**：
- 检测器和描述器可独立测试（mock 其中一个）
- 未来管道变体（如替换描述器为 Florence-2）只需换 `qwen_vl/` 模块
- 避免 `vision.py` 文件膨胀（`PipelineGQVisionProvider._parse()` 预期 100+ 行逻辑，再内联两个模型的管理会更长）

**备选方案**：全部塞进 `vision.py`。否决——单文件超过 300 行，测试和替换都困难。

### D2: 模型生命周期 — 懒加载 + 空闲卸载

**选择**：`initialize()` 和 `shutdown()` 显式方法控制模型加载/卸载，不放入 `__init__`。

```python
class PipelineGQVisionProvider(VisionProvider):
    def __init__(self, config):          # 仅存储配置，不加载模型
    def initialize(self):                # 加载 GDINO + Qwen 到 GPU
    def shutdown(self):                  # 卸载模型，释放显存
    def parse(self, image, a11y_hints):  # 调用时确保 initialized
```

**空闲卸载策略**：在 `PerceptionService` 或 `server.py` 层实现一个 idle timer，`analyze()` 调用时重置 timer，超时后调用 `shutdown()`。Provider 层不感知 timer——它只提供 load/unload 原语。

**理由**：
- `__init__` 中加载意味着 `import src.providers.vision` 就触发 GPU 分配——破坏非 GPU 用户的 import 体验
- 显式生命周期让 server 可以精确控制加载时机（收到第一个 `analyze` 请求时懒加载）
- 空闲卸载避免长期不用的模型占用显存

**备选方案**：模型常驻显存。否决——用户可能在 session 间数小时不使用 `analyze`，6 GB 显存浪费不可接受。

### D3: 类型映射 — 两阶段约束映射

**选择**：GDINO 的开放词汇 label 做粗分类（约束 Qwen 的枚举选择空间），Qwen 在受限集合内做细分类。

```
GDINO label → 粗分类               Qwen type（约束在该集合内选）
─────────────────────────────────────────────────────────────
含 "button"     → interactive    → {button, input, checkbox, radio, tab, menuitem, link}
含 "text/input" → interactive
含 "check/radio"→ interactive
含 "window/menu/→ structural     → {window, dialog, sidebar, toolbar, panel, list, table, form}
  sidebar/toolbar/
  panel/list/table"
其他            → unknown        → 全部 17 值
```

**Qwen describe prompt** 接收粗分类约束作为输入参数，要求输出在对应候选集中选择一个枚举值。这从根本上限制了 47% button 泛滥——遇到 structural 类元素时 Qwen 根本不能选 `button`。

**映射实现**：`GdinoLabelMapper` 内部工具类，维护关键词 → 粗分类的映射表。初始映射表基于 spike 中 GDINO 实际产出的 label 构建（约 15-20 种）。

**理由**：
- GDINO 的开放词汇在区分 interactive vs structural 上可靠（"button" 和 "window" 不会混淆）
- Qwen 的 47% button 误分类是因为在全部 17 值中自由选择——缩小候选集直接降低误分类率
- 无需额外模型，纯规则映射零延迟
- 映射表可增量维护（遇到新 GDINO label 时加到映射表）

**备选方案**：纯 Qwen prompt 约束（不依赖 GDINO 粗分类）。否决——spike 已证明 Qwen 在无约束下的类型分布严重偏向 button。

### D4: 置信度 — 初版用 GDINO detection score

**选择**：`ParsedElement.confidence` 填入 GDINO 的 detection score（box_threshold 过滤后保留的原始分数）。Qwen 输出暂不影响 confidence（全 0.98，无区分度）。不使用分层 confidence 字段。

**理由**：
- GDINO score 反映"这里确实有个物体"，在 0.17 threshold 下可靠性经过 spike 验证
- Qwen score 全 0.98 是已知问题（见 spike §12.1），但解决它需要 prompt 优化——属于后续迭代
- 不分层：`ParsedElement` 保持单字段 `confidence`，Provider 内部透明决定来源
- 当 prompt 优化使 Qwen 产出区分化分数后，可内部切换到 `max(GDINO, QWEN)` 或加权——不改变 `AnalysisResult` 消费者

### D5: 后处理管道 — 顺序三阶段

**选择**：检测后立即执行三阶段后处理，不暴露中间状态。

```
raw elements (GDINO) → Stage 1: 面积过滤 → Stage 2: IoU 去重 → Stage 3: min_size 裁剪 → final elements
```

| 阶段 | 规则 | 参数 |
|------|------|------|
| 面积过滤 | bbox 面积 > 50% 屏幕面积 → 忽略 | `area_filter_ratio: 0.5` |
| IoU 去重 | IoU > 阈值 → 保留高 confidence 者 | `iou_dedup_threshold: 0.5` |
| min_size 裁剪 | 最短边 < min_crop → 跳过描述阶段 | `min_crop_size_full: 32`, `min_crop_size_zoom: 16` |

**min_crop_size 自适应规则**：当原始截图分辨率 ≤ 1024×768 时使用 `min_crop_size_zoom`，否则使用 `min_crop_size_full`。不依赖 `effort` 参数——纯尺寸自适应。

**理由**：spike §12.3-12.4 分别验证了大 bbox 误检和小图参数不适配问题。面积过滤和尺寸自适应成本极低（O(n) 遍历）。

### D6: effort 参数 — Provider 构造函数配置，不进 ABC

**选择**：`effort` 作为 `PipelineGQVisionProvider` 的构造函数参数，不在 `VisionProvider.parse()` 接口中暴露。

```python
class PipelineGQVisionProvider(VisionProvider):
    def __init__(self, config: VisionConfig):
        self._effort = config.effort  # "low" | "high"

    def parse(self, image, a11y_hints):
        threshold = 0.13 if self._effort == "high" else 0.17
        # ...
```

**`effort` 语义**：
| effort | GDINO threshold | 预期元素数 | 延迟 | 适用场景 |
|--------|:---:|------|------|---------|
| `"low"` | 0.17 | ~26（高精度） | ~20s | 常规任务 |
| `"high"` | 0.13 | ~57（高覆盖） | ~35s | 复杂 UI 需要全部元素 |

**理由**：`effort` 是 Pipeline GQ 特有的 tradeoff（threshold → 精度 vs 覆盖），不适合作为通用 `VisionProvider` 接口参数——云端 provider 的 `effort` 可能映射到完全不同的概念（如模型选型 plus vs flash）。不进 ABC 是讨论中明确的决策。

### D7: 配置结构 — vision 配置段

**选择**：在 `config.yaml` 现有 `perception.providers.vision` 下扩展参数。

```yaml
perception:
  providers:
    vision:
      backend: "pipeline_gq"           # dummy | pipeline_gq
      pipeline_gq:
        gdino_model_path: ""           # 必填：本地模型路径
        qwen_model_path: ""            # 必填：本地模型路径
        gdino_quantization: null       # null=FP16, "int8", "int4"
        qwen_quantization: "q4"        # Qwen3-VL-4B 的量化方式
        effort: "low"                  # low | high
        idle_shutdown_sec: 600         # 空闲 10 分钟后卸载
        text_prompt: "button. input field. checkbox..."  # GDINO 检测 prompt
        box_threshold_low: 0.17
        box_threshold_high: 0.13
        area_filter_ratio: 0.5
        iou_dedup_threshold: 0.5
        min_crop_size_full: 32
        min_crop_size_zoom: 16
        img_scale: 0.5                 # 输入缩放比例
        max_tokens_per_region: 64      # Qwen 单区域最大 token 数
```

**理由**：
- `backend: "pipeline_gq"` 触发 `PipelineGQVisionProvider` 初始化，保持与现有 `dummy` 的切换方式一致
- 所有 spike 调参产物固化为可配置参数，避免硬编码
- `gdino_model_path` / `qwen_model_path` 必填——因为模型需用户自行下载，不给默认路径

### D8: ML 依赖管理 — 可选 extra

**选择**：`pyproject.toml` 中 ML 依赖放在 `[project.optional-dependencies]` 的 `vision` extra 下。

```toml
[project.optional-dependencies]
vision = [
    "torch>=2.0.0",
    "transformers>=4.45.0",
    "groundingdino-py>=0.4.0",
    "accelerate>=0.26.0",
    "bitsandbytes>=0.41.0",
    "Pillow>=10.0.0",
]
```

**import 守卫**：`PipelineGQVisionProvider.__init__` 中检查依赖可用性，缺失时给出清晰错误信息，而非 import 即崩溃。

```python
try:
    import torch
except ImportError:
    raise ImportError(
        "PipelineGQVisionProvider requires PyTorch. "
        "Install with: pip install ai-gui-mcp[vision]"
    )
```

**理由**：项目 70%+ 用户可能在无 GPU 环境下使用（仅需 mouse/keyboard/screenshot），强制安装 torch（~2 GB）不合理。

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| GDINO 模型路径下找不到模型文件 | 高 | blocker | `initialize()` 中明确检查路径存在性，给出下载指引 |
| Qwen3-VL-4B Q4 在裁剪小图上仍有 repetition 倾向 | 低 | 中 | `max_tokens_per_region=64` 硬截断；`repetition_penalty=1.1` |
| 两个模型顺序加载 OOM（6 GB 理论可行但量化开销可能超预算） | 低 | 高 | `initialize()` 先加载 GDINO → 检查 VRAM → 加载 Qwen → 如 OOM 则 `shutdown()` GDINO 降级为纯 Qwen 模式（future），当前报错 |
| GDINO 在特定 COSMIC 主题/缩放比例下检测率骤降 | 中 | 中 | `text_prompt` 可配置，用户可定制检测词汇；`effort="high"` 降低 threshold |
| `pyproject.toml` 可选 extra 安装复杂度让用户困惑 | 中 | 低 | README 和 `initialize()` 错误信息中明确指引 |
| 初始类型映射表覆盖不全（GDINO label 词汇超出映射表） | 中 | 低 | 未匹配 label 降级为 `unknown` 粗分类 → Qwen 在全部 17 值中选择；映射表后续增量更新 |

## Open Questions

（全部分析中已决策，无遗留）
