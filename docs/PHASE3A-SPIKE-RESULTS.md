# Phase 3A Spike Results — Architecture C (Qwen3-VL-8B)

**Date**: 2026-05-30  
**Status**: COMPLETE  
**Model**: Qwen3-VL-8B-Instruct (Apache 2.0, safetensors, ~17 GB)  
**GPU**: 11.47 GB VRAM (NVIDIA, CUDA 13.0)  
**Test Set**: 8 COSMIC screenshots (2560×1600), `docs/spike-screenshots/`

---

## 1. 最终验证配置

| Parameter | Value |
|-----------|-------|
| Quantization | INT4 (bitsandbytes) |
| GPU Memory (INT4) | ~5.5 GB |
| Image Resolution | 1280×800 (scale=0.5, LANCZOS) |
| max_new_tokens | 1024 |
| Generation | do_sample=False |
| Repetition Penalty | 1.1 |
| Post-processing | IoU dedup (>0.5) + text-based dedup + button spam filter |

**为什么选 INT4 而非 INT8**：INT8 在 11.47 GB GPU 上失败（`Some modules are dispatched on the CPU`），bitsandbytes 无法将全量 INT8 模型装入可用显存。FP16 加载后推理阶段 OOM。INT4 是唯一可用的量化方案。

**为什么选 scale=0.5**：2560×1600 原始分辨率在 INT4 下仍可跑动，但视觉 token 数过大导致推理极慢且易触发 repetition loop。1280×800 在精度与速度间取得可接受的平衡。

---

## 2. 批量测试结果

| Screenshot | Screen Kind | Elements | Regions | Quality | Time |
|-----------|------------|----------|---------|---------|------|
| COMIC-setting | settings ✓ | 15 | 2 | high | 26.9s |
| Desktop | unknown ✗ | 15 | 3 | high | 27.7s |
| FileManager | file_manager ✓ | 9 | 2 | high | 27.2s |
| edge-bilibili-streaming | browser ✓ | 9 | 3 | low | 27.9s |
| edge-bing-searching | browser ✓ | 0 | 2 | medium | 27.1s |
| edge-opencode-zen | browser ✓ | 15 | 2 | high | 27.6s |
| MessageBox-confirmation | ide ✗ | 0 | 3 | medium | 28.2s |
| vscode | ide ✓ | 7 | 3 | medium | 28.5s |

**总计**: 70 elements, 221.1s (3.7 min), 平均 27.6s/张  
**屏幕分类准确率**: 5/8 (63%) — Desktop 被误判为 unknown, MessageBox 被误判为 ide  
**Quality 分布**: high=4, medium=3, low=1

---

## 3. 已知问题

### 3.1 Repetition Loop（严重）

模型在列出元素时倾向于进入重复循环。INT4 + Qwen3-VL-8B 在 `do_sample=False` 模式下，生成 10-15 个有效元素后陷入窗口控制按钮的无限重复。缓解措施：
- `max_new_tokens=1024` 限制输出长度（约 15-20 个元素后截断）
- 后处理 heuristic：当 >50% 元素为无文本 button 时截断至前 5 个 button
- `repetition_penalty=1.1` 轻度缓解

**根因**：Qwen3-VL 的 greedy decoding 缺乏 diversity 机制；INT4 量化可能加剧了 token 分布坍缩。

### 3.2 元素漏检

- `edge-bing-searching`: 仅检测到 4 个元素，经去重/过滤后归零
- `MessageBox-confirmation`: 检测到 0 个元素
- 所有场景的检测偏向于顶部标题栏区域，对内容区域（编辑器、网页正文）召回极低

### 3.3 屏幕分类不准确

- Desktop 被分类为 `unknown` 而非 `desktop`/`file_manager`
- MessageBox-confirmation 被分类为 `ide` 而非 `dialog`

---

## 4. Prompt 设计

### Stage 1 (Coarse)
```
You are a GUI screen analyzer. Classify screen type and identify main layout regions.
Output: { "screen_kind": "...", "layout_regions": [{"id", "type", "bbox": [x1,y1,x2,y2]}] }
```
效果：屏幕分类 63% 准确；区域划分基本合理。

### Stage 2 (Fine)
```
You are a GUI element detector. Identify ALL visible UI elements.
Output: { "elements": [{"id", "type", "bbox": [x1,y1,x2,y2], "text", "confidence"}] }
CRITICAL: List each element only ONCE. After the last element, close with ]} and STOP.
```
效果：前 5-10 个元素有效，之后进入重复循环。

---

## 5. 架构 C Go/No-Go 结论

### No-Go（不建议直接用于生产）

| 维度 | 评估 |
|------|------|
| Grounding 精度 | ❌ 元素召回极低，仅检测到标题栏附近元素 |
| 输出稳定性 | ❌ 严重的 repetition loop，需大量后处理 |
| 量化要求 | ⚠️ 仅 INT4 可用，精度损失显著 |
| 推理速度 | ⚠️ 27.6s/张（1280×800），2560×1600 无法跑通 |
| 许可 | ✓ Apache 2.0，无商业限制 |
| 部署复杂度 | ✓ 单文件脚本，无额外依赖 |

### 建议

1. **不推荐在当前 GPU (11.47 GB) 上直接使用 Qwen3-VL-8B + INT4 作为 VisionProvider**。元素召回率和输出稳定性不足。
2. **如果升级 GPU（≥24 GB）**：可尝试 INT8 量化 + 1920×1200 分辨率。预计精度有显著提升。
3. **备选方案**：考虑架构 A（KV-Ground / 小模型微调）或架构 B（OmniParser + 微调小模型），前者可能更适合单 GPU 场景。
4. **短期可用**：Stage 1（layout 分类）质量可接受，可作为 `LayoutSummary` 的 fallback。

### bbox 格式变更

`[x,y,w,h]` → `[x1,y1,x2,y2]` 变更已完成。所有 185 个测试通过，无回归。

---

## 6. 产出文件

- `scripts/spike_arch_c.py` — spike 验证脚本（模型加载、两阶段推理、JSON 解析、去重、CLI）
- `scripts/visualize_bboxes.py` — bbox 可视化脚本（Pillow 叠加 + 文本映射）
- `docs/spike-results/round-2/` — 8 张截图的分析结果 + 叠加图 + 元素清单
- `src/models.py` — bbox 格式变更 + 新增 AnalysisWarning 枚举值
