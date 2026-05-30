## Context

本项目处于 P3A spike 阶段，当前 `VisionProvider` 为 dummy stub，`AnalysisResult` / `ParsedElement` 模型已定义但未经实际模型验证。PHASE3A-SPIKE.md 决策路径要求先验证架构 C（通用 VLM + prompt 工程），模型选 Qwen3-VL-8B-Instruct（Apache 2.0 许可，已下载至本地 safetensors 格式）。

上一个 agent 的 spike 尝试因在变数未确定时就写计划而失败，已 git 还原。本轮必须在充分明确所有已知约束和未知变数的前提下设计验证流程。

**关键约束**：
- 测试集：`docs/spike-screenshots/` 下 8 张 2560×1600 COSMIC 全屏截图
- 模型：Qwen3-VL-8B-Instruct，safetensors 格式，~17GB，FP16 全精度会超出显存
- 输出格式：bbox 必须为 `[x1, y1, x2, y2]`（像素坐标），非 `[x, y, w, h]`
- 验证方式：VLM 输出的 bbox 画在测试集原图上 + 序号标注 + 文本清单，人工核实
- 验证节奏：先跑一张图评估时间→调参→每轮验收后暂停等待用户反馈

## Goals / Non-Goals

**Goals:**
1. 跑通 Qwen3-VL-8B-Instruct 在 COSMIC 截图上的结构化 Grounding，输出可映射到 `AnalysisResult` 的 JSON
2. 验证 bbox 精度（绘制叠加图人工评估）、元素类型识别准确率、重复输出问题
3. 确定最佳量化策略（INT8 vs INT4）、分辨率（原始 2560×1600 vs 缩放后）、content 长度参数组合
4. 产出可复用的 spike 验证脚本和可视化脚本
5. 确认 `AnalysisResult` 最终数据契约格式（特别是 bbox=[x1,y1,x2,y2]）

**Non-Goals:**
- 不实现正式的 `VisionProvider`（spike 通过后才做）
- 不集成到 MCP server 的 `screen(action="analyze")` 路径
- 不验证架构 A（KV-Ground）和架构 B（OmniParser）
- 不实现 Zoom-In 等推理时增强（spike 中可选测试但不作为硬性目标）
- 不写完整测试套件（spike 是探索性验证）

## Decisions

### D1: 验证脚本架构 — 单文件 CLI 脚本，非 MCP 集成

**选择**：独立 CLI 脚本 `scripts/spike_arch_c.py`，不耦合 MCP server。

**理由**：
- Spike 阶段需要快速迭代参数（量化精度、分辨率、prompt），CLI 脚本改动成本远低于 MCP 服务重启
- 避免把不稳定的实验代码混入生产路径
- 脚本输出可直接供给可视化脚本，不需要走 MCP 协议层

**备选方案**（已否决）：直接在 `DummyVisionProvider` 里替换为真实模型。问题：每次改 prompt 都要重启 server，调试效率极低。

### D2: 模型加载 — transformers + bitsandbytes INT8 量化优先

**选择**：使用 HuggingFace `transformers` 加载模型，优先尝试 `bitsandbytes` INT8（`load_in_8bit=True`），失败则降级到 device_map="auto" + torch.float16 + CPU offload。

**理由**：
- 用户已确认 FP16 全精度会超出显存，量化是必须的
- INT8 精度损失通常 <1%，在 Grounding 任务上影响可控
- `bitsandbytes` 是 transformers 生态的一等公民，集成成本最低
- 备选 INT4（`auto-gptq` / `bitsandbytes 4bit`）作为进一步降级路径

**备选方案**（保留但不首轮采用）：
- vLLM：部署复杂度高，spike 阶段不需要吞吐量优化
- llama.cpp GGUF：需额外格式转换，增加不确定因素

### D3: 推理策略 — 粗分区 + 细提取（两阶段）

**选择**：
1. 第一阶段（coarse）：全图推理，要求模型输出 `screen_kind`、`layout_summary`、主要区域 bbox
2. 第二阶段（fine）：将每个识别出的区域裁剪放大后二次推理，要求输出该区域内的 `elements[]` 详情

**理由**：
- 用户已知经验："先粗分区再细提取是对的"
- 2560×1600 高分辨率下，直接要求全图细粒度元素列表会导致模型遗漏小元素（VLM 注意力分散问题）
- 两阶段方案与 Zoom-In 思想一致，但要显式分区而非隐式推理

**待验证变数**：
- 裁剪放大比例（1.5x? 2x? 保持原始分辨率？）
- 第二阶段是否需要独立运行还是可以从第一阶段上下文延续

### D4: Prompt 设计 — 结构化 JSON 输出 + 强格式约束

**选择**：使用 system prompt 指定输出 JSON schema，user prompt 描述任务。要求模型输出严格的 JSON 数组，每个元素含 `id`、`type`、`bbox`(4 ints)、`text`、`confidence`。

**关键细节**：
- bbox 格式明确指定为 `[x1, y1, x2, y2]`（左上角和右下角像素坐标）
- 坐标原点为图片左上角 (0,0)
- 要求模型输出完整的 JSON 块（用 ```json 包裹），方便解析
- 第一阶段 prompt 要求输出 `screen_kind`、`layout_regions`（每个区域含 bbox 和 type）
- 第二阶段 prompt 要求输出该裁剪区域内的 `elements[]`（含 bbox、type、text、confidence）

**防止重复输出**：在 prompt 中明确要求 "Do not duplicate elements. Each UI element should appear exactly once."

### D5: 可视化验证 — Pillow 绘制 bbox 叠加图

**选择**：用 Pillow 加载原图，在图上绘制每个 bbox 的矩形框 + 左上角标注序号，另存为 PNG。同时输出一个文本文件列出序号→识别内容映射。

**理由**：
- 纯 Pillow 无额外依赖（项目已有 Pillow）
- 矩形框 + 序号标注直观可读，人工评估效率高
- 文本映射文件可与叠加图对照，不会混淆

### D6: AnalysisResult bbox 格式 — [x1, y1, x2, y2]

**选择**：将所有 bbox 字段从 `[x, y, w, h]` 改为 `[x1, y1, x2, y2]`。

**理由**：
- 用户明确要求此格式
- `[x1,y1,x2,y2]` 对 VLM 更自然（输出两个坐标点比输出点+宽高更直观）
- 与主流 VLM 坐标输出格式（Qwen-VL 的 [0-1000] 归一化坐标、多数 Grounding benchmark）对齐
- 避免 w/h 计算中的 off-by-one 歧义

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| INT8 量化后 Grounding 精度显著下降 | 中 | 高 | 对比 INT8 vs FP16（用 CPU offload 跑少数样本），量化不可接受则评估 INT4 或升级 GPU |
| 1920×1200 缩放后小元素丢失 | 中 | 中 | 先跑原始分辨率+FP16 offload（慢但作为精度 baseline），再对比缩放后 |
| 模型重复输出元素 | 高（已知问题） | 中 | Prompt 中加防重复指令；后处理去重（IoU > 0.5 的元素视为重复）|
| JSON 解析失败（模型输出格式不规范） | 中 | 高 | 实现鲁棒的 JSON 提取（正则匹配 JSON 块），解析失败时记录 raw output 到日志 |
| 两阶段推理总时长超过可接受范围 | 中 | 中 | 先测单阶段全图推理，如精度可接受则跳过第二阶段 |

## Open Questions

1. **量化方案最终选择**：INT8 是否可用？是否需要回退到 INT4？FP16 + CPU offload 作为精度 baseline 的耗时是否可接受（哪怕很慢）？
2. **分辨率策略**：2560×1600 原始分辨率在 INT8 下是否跑得动？1920×1200 缩放是否保留足够细节？
3. **两阶段 vs 单阶段**：单阶段全图推理的精度是否已经足够（可能不需要第二阶段）？
4. **Content 长度参数**：`max_new_tokens` 设置多少合适？第一阶段（layout summary）和第二阶段（elements detail）是否需要不同的 token 上限？
5. **`AnalysisResult` 最终确认**：当前 `LayoutRegion.type` 枚举和 `ScreenKind.kind` 枚举是否需要从 spike 中新增/调整？
