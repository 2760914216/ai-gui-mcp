## 1. Bbox 格式变更 — 数据模型

- [x] 1.1 `src/models.py`: 将 `ParsedElement.bbox` 注释从 `[x, y, w, h]` 改为 `[x1, y1, x2, y2]`，确保 `list[int]` 类型不变
- [x] 1.2 `src/models.py`: 将 `LayoutRegion.bbox` 注释从 `[x, y, w, h]` 改为 `[x1, y1, x2, y2]`
- [x] 1.3 `src/models.py`: 将 `UIElement.bbox` 注释从 `[x, y, w, h]` 改为 `[x1, y1, x2, y2]`
- [x] 1.4 `src/models.py`: 在 `AnalysisWarning.code` 枚举中新增 `duplicate_element`、`hallucinated_element`、`model_parse_error`
- [x] 1.5 运行 `lsp_diagnostics src/models.py` 确认无类型错误

## 2. Bbox 格式变更 — 现有代码适配

- [x] 2.1 搜索项目中所有使用 `UIElement(bbox=` 或 `ParsedElement(bbox=` 的代码，将 `[x,y,w,h]` 构造转为 `[x1,y1,x2,y2]`
- [x] 2.2 搜索项目中所有读取 `.bbox[2]` 作 width、`.bbox[3]` 作 height 的代码，改为 `x2-x1` 和 `y2-y1` 计算
- [x] 2.3 更新 `src/tests/test_models_p3a.py` 中所有 bbox 测试数据
- [x] 2.4 更新 `src/tests/test_perception_service.py` 中涉及 bbox 的测试
- [x] 2.5 更新 `src/tests/test_providers.py` 中涉及 bbox 的测试
- [x] 2.6 更新 `src/providers/a11y.py` 中 AT-SPI2 bbox 构造逻辑（如有）
- [x] 2.7 运行 `pytest src/tests/ -x --tb=short` 确认所有现有测试通过

## 3. Spike 环境准备 — 依赖安装

- [x] 3.1 检查 PyTorch CUDA 版本：`python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
- [x] 3.2 安装 transformers：`pip install transformers>=4.45.0`
- [x] 3.3 安装 bitsandbytes（INT8/INT4 量化）：`pip install bitsandbytes`
- [x] 3.4 验证模型路径可访问：确认 `/home/ruruka/Documents/Models/Qwen3-VL-8B-Instruct/` 下 safetensors 文件完整（4 个分片 + index）
- [x] 3.5 创建 `scripts/` 目录（如不存在）

## 4. Spike 验证脚本 — `scripts/spike_arch_c.py`

- [x] 4.1 实现模型加载函数 `load_model(model_path, quantize="int8")`，支持 int8/fp16/int4 三种模式，失败时打印清晰错误信息
- [x] 4.2 实现两阶段推理主流程：`coarse_parse(image)` → 输出 screen_kind + layout_regions；`fine_parse(cropped_image)` → 输出 elements[]
- [x] 4.3 实现第一阶段 prompt（coarse）：要求模型输出 JSON 含 `screen_kind` 和 `layout_regions[]`（每个 region 含 type/id/bbox）
- [x] 4.4 实现第二阶段 prompt（fine）：要求模型输出 JSON 含 `elements[]`（每个 element 含 id/type/bbox/text/confidence）
- [x] 4.5 实现鲁棒 JSON 解析器：正则提取 ```json 代码块，容错处理 trailing comma、缺失括号；失败时记录 raw output
- [x] 4.6 实现输出映射：将 VLM 输出的原始 JSON 映射为 `AnalysisResult`（含 elements、layout_summary、warnings）
- [x] 4.7 实现 IoU 去重逻辑：两个 element bbox IoU > 0.5 时移除低置信度者，添加 `duplicate_element` warning
- [x] 4.8 实现 CLI 参数：`--model-path`, `--image`, `--quantize`, `--max-tokens`, `--scale`, `--output`
- [x] 4.9 实现耗时统计：打印模型加载时间和单张图片推理时间

## 5. 可视化验证脚本 — `scripts/visualize_bboxes.py`

- [x] 5.1 实现 `draw_bboxes(image_path, analysis_json_path, output_dir)` 主函数
- [x] 5.2 在原图上用 Pillow 绘制每个 element 的 bbox 矩形框（不同 type 用不同颜色）
- [x] 5.3 在每个矩形框的左上角标注序号（1, 2, 3...）
- [x] 5.4 输出带标注的 PNG 图片到 `output_dir/{image_name}_annotated.png`
- [x] 5.5 输出文本映射文件到 `output_dir/{image_name}_elements.txt`，格式：`[N] type=button text="Save" bbox=[x1,y1,x2,y2] confidence=0.92`
- [x] 5.6 实现 CLI：`python scripts/visualize_bboxes.py <analysis.json> <original.png> -o <out_dir>`

## 6. 首轮验证 — 单图测试

- [x] 6.1 从 `docs/spike-screenshots/` 选一张代表性截图（建议 `vscode.png` — IDE 场景元素丰富）
- [x] 6.2 以 INT8 量化 + 2560×1600 原始分辨率运行推理，记录耗时
- [x] 6.3 将 VLM 输出的 AnalysisResult JSON 保存到 `docs/spike-results/round-1/`
- [x] 6.4 运行可视化脚本生成 bbox 叠加图 + 文本清单
- [x] 6.5 **停下来，展示叠加图和耗时数据给用户，等待人工验收反馈后再进入下一轮**

## 7. 迭代调参 — 基于用户反馈

- [x] 7.1 根据用户反馈调整量化精度（INT4 或 FP16 offload）、缩放比例、max_tokens、prompt 措辞
- [x] 7.2 每轮只改一个参数，对比前后结果
- [x] 7.3 **每轮结束后停下来，展示结果等待用户反馈**

## 8. 扩展验证 — 多图测试

- [x] 8.1 在用户确认单图质量可接受后，对 `docs/spike-screenshots/` 下其余 7 张截图批量运行
- [x] 8.2 所有结果保存到 `docs/spike-results/round-N/`，每张图独立子目录
- [x] 8.3 汇总统计各场景的元素召回情况（粗略人工计数）

## 9. 收尾 — 文档与清理

- [x] 9.1 将最终验证的量化方案、分辨率、prompt 模板、耗时、精度评估写入 `docs/PHASE3A-SPIKE-RESULTS.md`
- [x] 9.2 在 `docs/PHASE3A-SPIKE-RESULTS.md` 中明确给出架构 C 的 Go/No-Go 结论
- [x] 9.3 运行 `pytest src/tests/ -x --tb=short` 确认 bbox 格式变更未引入回归
