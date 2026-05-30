## 1. 环境准备

- [x] 1.1 确认 Grounding DINO-T 模型可用（检查 `IDEA-Research/grounding-dino-tiny` 或下载）
- [x] 1.2 确认 Qwen3-VL-4B-Instruct 模型已下载到本地
- [x] 1.3 安装 spike 脚本所需依赖（transformers, torch, grounding-dino, pillow, accelerate, bitsandbytes）
- [x] 1.4 创建输出目录 `docs/spike-results/pipeline-round1/`

## 2. Grounding DINO-T 检测模块

- [x] 2.1 实现 `load_gdino_model()` — 加载 Grounding DINO-T 模型和 processor
- [x] 2.2 实现 `detect_elements(image, text_prompt, box_threshold, text_threshold)` — 单张图检测，返回 bbox[] + label[] + confidence[]
- [x] 2.3 实现 bbox 坐标映射：缩放图坐标 → 原始 2560×1600 坐标
- [x] 2.4 实现 `--skip-describe` 模式，仅输出检测 bbox 用于单独验证

## 3. Qwen3-VL-4B 描述模块

- [x] 3.1 实现 `load_qwen_model(model_path, quantize)` — 加载 Qwen3-VL-4B Q4_K_M
- [x] 3.2 实现 `describe_region(cropped_image, prompt)` — 对单个裁剪区域推理，返回 type + text + confidence
- [x] 3.3 实现裁剪区域生成：从原图按 bbox（1.2× 扩展）裁剪，最小尺寸 32×32 的跳过
- [x] 3.4 实现 JSON 解析与容错：从 Qwen 输出中提取 JSON（正则匹配），解析失败则返回 type="unknown"
- [x] 3.5 实现 type 映射：Qwen 输出的自然语言 type → `ParsedElement.type` 枚举值

## 4. 管道编排与后处理

- [x] 4.1 实现 `run_pipeline(image_path, ...)` — 编排 detect → crop → describe → merge 全流程
- [x] 4.2 实现 IoU 去重（阈值 0.5），保留置信度更高的元素
- [x] 4.3 实现 AnalysisResult 兼容 JSON 构建：snapshot_id, elements[], layout_summary(screen_kind="unknown"), warnings[]
- [x] 4.4 实现置信度 clamp [0.0, 1.0]
- [x] 4.5 实现顺序模型加载（如 VRAM 不足则检测完卸载 G-DINO 再加载 Qwen）

## 5. CLI 与输出生成

- [x] 5.1 实现 argparse CLI：--image-dir, --output-dir, --gdino-model, --qwen-model, --text-prompt, --box-threshold, --text-threshold, --img-scale, --qwen-quantize, --max-tokens, --single, --image, --skip-describe
- [x] 5.2 实现单张模式（--single --image X）：仅处理一张图，打印结果摘要并等待
- [x] 5.3 实现批量模式：遍历 --image-dir 所有 PNG，逐张处理
- [x] 5.4 调用现有 `scripts/visualize_bboxes.py` 生成 _annotated.png 和 _elements.txt
- [x] 5.5 实现批量模式结束后的汇总对比表输出（Screenshot / Elements / Quality / Warnings）

## 6. 调参轮验证

- [x] 6.1 用 `--single --image COMIC-setting.png` 跑首次调参，默认参数
- [x] 6.2 产出可视化叠加图，人工评估检测召回率和描述准确率
- [x] 6.3 根据反馈调整 text_prompt / box_threshold / text_threshold / img_scale
- [x] 6.4 重复 1-2 个调参迭代，确定稳定参数组合
- [x] 6.5 用稳定参数跑第二张截图（如 vscode.png）验证参数泛化性

## 7. 批量验证与决策

- [x] 7.1 用稳定参数跑全部 8 张 COSMIC 截图
- [x] 7.2 产出 8×3 文件到 pipeline-round1/
- [x] 7.3 人工评估全部 8 张的标注图，记录每张的元素数、漏检、误检
  - 用户已观察 0.125/0.175 标注图：
    - 0.125: 桌面图标大量识别，但也将桌面背景识别出 ~9 个无意义区域
    - 0.175: 主要区域(窗口/sidebar/content/dock/图标集中区)基本识别到，但漏掉大部分桌面图标
  - 确定两个代表参数：0.13（高覆盖）和 0.17（高精度）
- [x] 7.4 汇总对比表：与架构 C round-2 结果横向对比
  - COMIC-setting: Arch_C_r2=15 vs GQ_0.17=26 (+73%) vs GQ_0.13=57 (+280%)
  - 管道 GQ 在元素召回上显著优于架构 C 单模型方案
- [x] 7.5 基于 Go/No-Go 标准判定：
  - 可交互元素召回率：0.13 覆盖桌面图标+窗口+sidebar+content，0.17 覆盖主要区域但漏图标
  - bbox 精度：坐标正确（已修复初始 COCO 格式 bug），裁剪区域扩展 1.2× 可用
  - 致命问题：Qwen 置信度全 0.98（无区分度），button 误分类 47-49%
- [x] 7.6 产出 Round 1 结论：Go（进入 P3A-4 VisionProvider 实现）/ No-Go（降级到管道 Q 或 F）/ Retry（特定参数调整后重跑）

**结论: GO — 管道 GQ 方案可行，建议进入 P3A-4 VisionProvider 实现。**
- 两阶段管道（GDINO→Qwen）在 COSMIC 8 张截图上成功运行
- 检测召回显著优于架构 C 单模型（+73%~280%）
- 参数空间已充分探索（0.10-0.25，7 个数据点），拐点在 0.15
- 建议 P3A-4 实现时采用 threshold=0.17（高精度模式），优化 Qwen prompt 解决 button 误分类和置信度问题
