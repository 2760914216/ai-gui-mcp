## Context

架构 C（Qwen3-VL-8B INT4 单模型 GUI parsing）在 COSMIC 实测中失败。根因分析：单模型同时承担 detection + description + classification，在 INT4 量化下 token 分布坍缩导致 repetition loop，注意力分散导致仅检测到标题栏区域元素。

管道方案将 GUI parsing 拆解为两阶段：
- **Stage 1（检测）**：开放词汇检测器定位所有 UI 元素 bbox——CNN 单次前向，零 token 生成风险
- **Stage 2（描述）**：小 VLM 在裁剪区域做精细元素识别——小区域推理，token 输出短，坍缩概率低

Grounding DINO-T 选为检测器因为开放词汇特性对未见过的 COSMIC/iced UI toolkit 泛化能力更强；Qwen3-VL-4B Q4_K_M 选为描述器因为 ScreenSpot 90%+ 且 Q4 量化后仅 ~4 GB，与检测器合计 ~6 GB，在 11.94 GB GPU 上可行。

验证采用与架构 C 相同的可视化方法：bbox 叠加标注序号 → 人工核实召回率和类型准确率。

## Goals / Non-Goals

**Goals:**
- 部署 Grounding DINO-T 开放词汇检测，验证在 COSMIC 截图上的元素召回率
- 部署 Qwen3-VL-4B Q4_K_M，验证在 bbox 裁剪区域上的元素类型和文本识别准确率
- 两阶段管道串联运行，产出 AnalysisResult 兼容的结构化 JSON
- 在 8 张 COSMIC 测试截图上产出可视化叠加图 + 元素清单，人工评估
- 单轮内完成 1-2 张截图的调参（prompt、检测阈值、分辨率），确定最佳参数组合
- 全量 8 张批量运行，产出对比矩阵

**Non-Goals:**
- 不实现正式 VisionProvider（spike 通过后才做 P3A-4 实现）
- 不集成到 MCP server 的 `screen(action="analyze")` 路径
- 不验证管道 Q（Qwen3-VL-4B 单模型 Zoom-In）和管道 F（Florence-2）
- 不修改 `src/` 任何生产代码
- 不新增 Python 依赖到 `pyproject.toml`
- 不创建测试集 ground truth JSON（纯人工可视化评估）

## Decisions

### D1: 检测器选型 — Grounding DINO-T（开放词汇）而非 YOLOv8（固定类别）

**选择**：Grounding DINO-T（`IDEA-Research/grounding-dino-tiny`），通过自然语言 prompt 指定检测目标。

**理由**：
- COSMIC/iced UI toolkit 不在任何固定类别检测器的训练分布中——YOLOv8 的 "icon" 类别（OmniParser 训练）对 COSMIC 元素可能完全无效
- 开放词汇检测接受自然语言描述（`"button. input field. checkbox. tab. menu item."`），显式告诉模型"找什么"，不依赖训练时的类别分布
- Grounding DINO-T 仅 ~2 GB VRAM，在 11.94 GB 预算内

**备选方案（已否决）**：
- YOLOv8n 微调：需要收集 COSMIC 标注数据，spike 阶段不可行
- OWLv2：VRAM 更大（~5 GB），且对 UI 元素的开放词汇检测未见 ScreenSpot 级验证
- 跳过独立检测直接用 VLM 做 detection + description：架构 C 已证明单模型全责不可靠

### D2: 描述器选型 — Qwen3-VL-4B Q4_K_M（而非 Florence-2 或 Moondream2）

**选择**：Qwen3-VL-4B-Instruct，Q4_K_M 量化，输入为裁剪的 bbox 区域图像。

**理由**：
- ScreenSpot 90-94%——在 4B 规模中 grounding 能力最强
- Q4_K_M 量化后 ~4 GB，与 Grounding DINO-T 合计 ~6 GB，余量充足
- 仅需对裁剪小区域做推理（token 输出极短，15-30 tokens），重复循环风险远低于全图推理
- Apache 2.0 许可

**备选方案（保留为后续轮次备选）**：
- Florence-2-large：MIT 许可，encoder-decoder 无重复循环风险，但 0.77B 参数理解能力有限，不适合精细描述
- Moondream2 INT4：~1.6 GB，ScreenSpot 80.4%，可在 VRAM 紧张时降级

**待验证变数**：
- Qwen3-VL-4B 是否也像 8B 版本一样有 repetition 倾向（小模型可能 token 分布更紧凑）
- Q4_K_M 量化在裁剪小图上的精度是否足够

### D3: 验证脚本架构 — 单文件 CLI，继承 spike_arch_c.py 模式

**选择**：独立 CLI 脚本 `scripts/spike_pipeline_gq.py`，使用 argparse，不耦合 MCP server。

**理由**：
- 与架构 C spike 脚本保持同模式——CLI 迭代快，不与生产路径耦合
- 管道涉及两个模型加载，需要灵活的参数调优（检测阈值、text_prompt、分辨率缩放）
- 复用现有 `scripts/visualize_bboxes.py`，不改动

**脚本参数设计**：
```
--image-dir       测试截图目录（默认 docs/spike-screenshots/）
--output-dir      结果输出目录（默认 docs/spike-results/pipeline-round1/）
--gdino-model     Grounding DINO 模型路径
--qwen-model      Qwen3-VL-4B 模型路径
--text-prompt     检测文本 prompt
--box-threshold   检测置信度阈值（默认 0.25）
--text-threshold  文本-图像匹配阈值（默认 0.25）
--img-scale       截图缩放比例（默认 0.5，即 1280×800）
--qwen-quantize   Qwen 量化方式（默认 q4）
--max-tokens      Qwen 单区域最大 token 数（默认 64）
--single          单张模式：只跑一张图用于调参
--image           单张模式下的图片文件名
--skip-describe   跳过描述阶段，仅产出检测 bbox
```

### D4: 管道流程 — 顺序两阶段（检测 → 逐区域描述）

**选择**：
```
Step 1: Grounding DINO-T 全图推理 → bbox[] + label[] + confidence[]
Step 2: 对每个 bbox 区域裁剪 → Qwen3-VL-4B 推理 → type + text + confidence
Step 3: 合并结果 → AnalysisResult 兼容 JSON
Step 4: 可视化叠加图 + 元素清单文本
```

**理由**：
- 顺序管道简单可调试——每阶段结果可独立检查
- Step 2 的 N 个区域裁剪可批量推理，减少 Qwen 推理次数
- 管道设计允许 `--skip-describe` 单独验证检测阶段质量

**后处理规则**：
- bbox 裁剪时扩展到原 bbox 的 1.2×（避免裁掉元素边缘）
- 裁剪区域最小尺寸 32×32（小于此尺寸跳过描述）
- IoU > 0.5 的元素去重（保留置信度更高的）
- bbox 坐标从缩放图映射回原始 2560×1600

### D5: 输出格式 — 与架构 C 对齐

**选择**：输出格式与 `spike_arch_c.py` 完全一致，便于横向对比。

每个截图产出三文件：
```
{name}_analysis.json   — AnalysisResult 兼容 JSON（elements[] + layout_summary）
{name}_annotated.png   — bbox 叠加图（颜色按 type，左上角标注序号）
{name}_elements.txt    — 序号→元素详情映射文本
```

**AnalysisResult 兼容 JSON 结构**：
```json
{
  "snapshot_id": "pipeline_gq_r1_{image_name}",
  "overall_quality": "medium",
  "warnings": [],
  "layout_summary": {
    "screen_kind": {"kind": "unknown", "detail": null},
    "main_regions": [],
    "active_dialog": {"present": false},
    "notes": null
  },
  "elements": [
    {
      "id": "el_001",
      "type": "button",
      "bbox": [x1, y1, x2, y2],
      "text": "Save",
      "description": null,
      "confidence": 0.92,
      "parent_id": null,
      "children_ids": [],
      "region_ref": null
    }
  ]
}
```

注意：Round 1 聚焦元素检测和描述，**不做 layout_summary / screen_kind 分类**——该能力留到管道验证确认可行后再叠加。

### D6: 验证节奏 — 调参轮 + 批量轮

**选择**：
```
Phase 1: 调参轮（1-2 张截图）
  ├─ 跑 COMIC-setting.png（设置界面，元素丰富）
  ├─ 调整 text_prompt / box_threshold / img_scale / qwen prompt
  ├─ 产出可视化图 → 人工评估 → 用户反馈 → 调整参数
  └─ 迭代到参数稳定

Phase 2: 批量轮（全部 8 张）
  ├─ 用稳定参数跑全部 8 张截图
  ├─ 产出 8×3 文件到 pipeline-round1/
  └─ 汇总对比表 → 人工评估 → Go/No-Go 判定
```

**暂停点**：每轮结束（调参轮每次迭代后、批量轮完成后），简短告知用户结果并等待反馈，不自动推进。

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Grounding DINO-T 在 COSMIC 上检测率极低 | 中 | 高 | `--skip-describe` 先独立验证检测阶段；如果 <30% 召回则本轮 No-Go，考虑降级到管道 Q |
| Qwen3-VL-4B Q4 仍有 repetition 倾向 | 低 | 中 | 小裁剪区域 token 极短（15-30），概率低；如出现则加 `repetition_penalty=1.1` |
| 两个模型同时加载 OOM | 低 | 致命 | 改为顺序加载（检测完卸载 G-DINO 再加载 Qwen），延迟增加但可跑通 |
| 开放词汇 prompt 设计不佳导致检测遗漏 | 中 | 中 | 调参轮迭代 prompt；参考 SeeClick 和 OS-Atlas 的元素类别词汇 |
| G-DINO bbox 精度不够（裁剪区域偏移） | 低 | 中 | 裁剪区域扩展 1.2× 边界；Qwen 描述时也可做 bbox 微调 |

## Open Questions

1. **Grounding DINO-T text prompt 的最佳措辞**：用简单名词（`"button"`）还是描述性短语（`"a clickable button on a desktop application"`）？需在调参轮对比
2. **检测阈值**：`box_threshold` 和 `text_threshold` 的初始值 0.25 是否合适？COSMIC 高分辨率截图可能需要更低的阈值
3. **Qwen 描述 prompt**：单区域描述需要多详细？`"Identify this UI element: type and text"` vs `"Describe this UI element in JSON: {type, text, confidence}"`
4. **Qwen3-VL-4B 的 Q4_K_M vs Q5_K_M**：Q5 精度更好但 VRAM 更大。如果 ~6 GB 总预算有压力，先试 Q4；有余量可试 Q5
5. **元素类型映射**：Grounding DINO 输出的 label 是自然语言（如 "a blue button"），需要映射到 `ParsedElement.type` 枚举值。映射规则需在实现中定义
