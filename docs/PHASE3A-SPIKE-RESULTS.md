# Phase 3A Spike Results

> **Architecture C**: Qwen3-VL-8B single-model GUI parsing ([sections 1-6](#phase-3a-spike-results--architecture-c-qwen3-vl-8b))  
> **Pipeline GQ Round 1**: Grounding DINO-T + Qwen3-VL-4B two-stage pipeline ([sections 7-14](#phase-3a-spike-results--pipeline-gq-round-1-grounding-dino-t--qwen3-vl-4b))

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

---

# Phase 3A Spike Results — Pipeline GQ Round 1 (Grounding DINO-T + Qwen3-VL-4B)

**Date**: 2026-05-30  
**Status**: COMPLETE  
**Detector**: Grounding DINO-T (`IDEA-Research/grounding-dino-tiny`, ~2 GB)  
**Descriptor**: Qwen3-VL-4B-Instruct Q4 (~4 GB, Apache 2.0)  
**GPU**: 11.47 GB VRAM (NVIDIA, CUDA 13.0)  
**Test Set**: 8 COSMIC screenshots (2560×1600) + 5 Zoom-In crops (1024×768 / 711×247), `docs/spike-screenshots/`  
**Script**: `scripts/spike_pipeline_gq.py`

---

## 7. 方案设计

管道将 GUI parsing 拆解为两阶段，规避架构 C 单模型全责导致的 attention 分散和 repetition loop：

```
Stage 1 (检测): Grounding DINO-T 开放词汇检测 → bbox[] + label[] + confidence[]
Stage 2 (描述): Qwen3-VL-4B Q4 裁剪区域推理 → type + text + confidence
Stage 3 (合并): IoU 去重 + AnalysisResult JSON + 可视化
```

**选型理由**：GDINO 的开放词汇特性对 COSMIC/iced 未见 toolkit 泛化更强；Qwen3-VL-4B Q4 仅 ~4 GB，与检测器合计 ~6 GB，在 11.47 GB GPU 上可行。

---

## 8. 阈值扫描 — COMIC-setting.png (2560×1600, scale=0.5)

| Threshold | 原始检测 | IoU 去重后 | 增量 | 噪声水平 |
|:--:|:--:|:--:|:--:|:--:|
| 0.25 | 4 | 4 | — | 太少 |
| 0.20 | 18 | 16 | +12 | 保守 |
| 0.175 | 29 | 24 | +8 | 稳定 |
| **0.17** | 31 | **26** | +2 | **★ 高精度** |
| 0.16 | 35 | 30 | +4 | 稳定 |
| 0.15 | 45 | 39 | +9 | 拐点 |
| **0.13** | 66 | **57** | +18 | **★ 高覆盖** |
| 0.125 | 77 | 66 | +9 | 噪声入侵 |
| 0.10 | 133 | 103 | +37 | 噪声淹没 |

**拐点位于 0.15→0.13**，检测量从 39 跃升至 57（+46%），之后进入噪声爆炸区。

**双参数模式**：

| 模式 | Threshold | 元素 | 特点 |
|------|:--:|:--:|------|
| 高精度 | 0.17 | 26 | 窗口/sidebar/content/dock 等主要区域精准识别，漏桌面图标 |
| 高覆盖 | 0.13 | 57 | 桌面图标 + 主要区域全覆盖，~9 个背景无意义区域 |

---

## 9. 批量测试结果 — 全屏 8 张 (threshold=0.1, 初始探索)

| Screenshot | Elements | Texts | Quality | Warnings |
|-----------|:--:|:--:|:--:|:--:|
| COMIC-setting | 103 | 52 | medium | 30 |
| Desktop | 80 | 37 | medium | 25 |
| FileManager | 89 | 44 | medium | 34 |
| MessageBox-confirmation | 34 | 22 | medium | 5 |
| edge-bilibili-streaming | 44 | 25 | medium | 12 |
| edge-bing-searching | 25 | 10 | medium | 11 |
| edge-opencode-zen | 24 | 12 | medium | 8 |
| vscode | 24 | 14 | medium | 8 |
| **TOTAL** | **423** | **216** | — | **133** |

**全局类型分布**: button(200, 47%), text(55), link(46), window(27), checkbox(23), sidebar(16), 其余 10 类(56)

**注意**: 0.1 是初始探索阈值，元素量高但噪声大。最终推荐 0.17（高精度）和 0.13（高覆盖）。

---

## 10. 与架构 C 对比 — COMIC-setting.png

| 指标 | Arch C r2 (INT4) | GQ 0.17 | GQ 0.13 |
|------|:--:|:--:|:--:|
| 元素数 | 15 | 26 (+73%) | 57 (+280%) |
| 文本覆盖 | 13 | 13 | 26 |
| 类型分布 | text(9), button(4) | button(13), radio(3), text(3) | button(26), text(8), window(7) |
| Repetition Loop | ❌ 严重 | ✅ 无（CNN 检测器无 token 生成） | ✅ 无 |
| 检测范围 | 仅标题栏区域 | 全屏主要区域 | 全屏 + 桌面图标 |
| 推理速度 | 27.6s | ~20s (检测 0.5s + 描述 15-18s) | ~35s (检测 0.5s + 描述 33s) |

管道 GQ 在元素召回和输出稳定性上显著优于架构 C。唯一弱势是 Qwen 类型分类精度（button 49% vs Arch C 的 27%），可通过 prompt 优化改善。

---

## 11. Zoom-In 区域截图验证 (threshold=0.17/0.13, scale=1.0)

| Screenshot | 尺寸 | GQ 0.17 | GQ 0.13 |
|------------|:--:|:--:|:--:|
| COMIC-filemanager-1 | 1024×768 | 14 | 18 |
| COMIC-filemanager-3 | 1024×768 | 12 | 15 |
| COMIC-setting-accessible | 1024×768 | 15 | 18 |
| MessageBox-confirmation | 711×230 | 8 | 8 |
| MessageBox-error | 711×247 | 10 | 14 |

**发现**：管道在非全屏区域截图上同样可用，检测行为与全屏阈值扫描趋势一致。但小尺寸图像有独特问题：

- **高去重率**: MessageBox 类小图上 60% 检测因 IoU>0.5 被去重（小图 bbox 密集重叠）
- **小元素被跳过**: 30-50% 元素 < 32px 被裁剪阶段丢弃（711×230 图像上按钮仅 20×15px）
- **建议**: 区域识别模式下降低 `min_crop_size` 至 16px，IoU 去重阈值降至 0.3

---

## 12. 已知问题

### 12.1 Qwen 置信度无区分度（严重）

Qwen3-VL-4B 对所有裁剪区域返回 confidence=0.98，无法用于元素质量排序。需在 P3A-4 实现时优化 describe prompt，要求模型输出区分化的 0.0-1.0 置信度。

### 12.2 button 过度分类 (47-49%)

近半数元素被 Qwen 分类为 button——文本标签、图标、菜单项被误判。需在 prompt 中增加更多元素类型示例（text/label/toggle/slider/pick_list），特别针对 COSMIC/iced toolkit 术语。

### 12.3 超大 bbox 误检

GDINO 倾向于检测全屏/半屏窗口作为单一元素（如 `[14,6,2546,1588]`）。P3A-4 实现时加面积过滤：>50% 屏幕面积的忽略。

### 12.4 小图参数不适配

当前 IoU=0.5、min_crop_size=32 配置针对 2560×1600 全屏优化，在 Zoom-In 小区域上导致过高去重率和元素跳过率。需按图像尺寸自适应。

---

## 13. 管道 GQ Round 1 Go/No-Go 结论

### GO — 建议进入 P3A-4 VisionProvider 实现

| 维度 | 评估 |
|------|------|
| Grounding 召回 | ✅ 显著优于架构 C，0.17 下主要区域全覆盖 |
| 输出稳定性 | ✅ 无 repetition loop（检测器为 CNN，零 token 风险） |
| VRAM 可行性 | ✅ 两模型合计 ~6 GB，11.47 GB GPU 余量充足 |
| 推理速度 | ✅ 检测 0.5s + 描述 15-35s（取决于元素数） |
| 类型精度 | ⚠️ button 误分类 47-49%，需 prompt 优化 |
| 置信度 | ❌ 全 0.98，需 prompt 优化 |
| Zoom-In 兼容 | ⚠️ 参数需按尺寸自适应 |
| 许可 | ✓ Grounding DINO-T (Apache 2.0) + Qwen3-VL-4B (Apache 2.0) |

### P3A-4 实现建议

1. 采用 **threshold=0.17**（高精度模式）作为默认配置
2. **Qwen prompt 优化**：增加 COSMIC/iced 元素类型术语（slider, toggle, pick_list），要求输出区分化置信度
3. **后处理增强**：面积过滤（>50% 屏幕忽略）、min_crop_size 自适应（全屏 32px / 区域 16px）
4. **保留 0.13 模式**作为可选 `analysis_mode="thorough"` 参数

---

## 14. 产出文件

- `scripts/spike_pipeline_gq.py` — 管道 spike 脚本（576 行，GDINO 检测 + Qwen 描述 + CLI + 可视化）
- `scripts/visualize_bboxes.py` — bbox 可视化脚本（复用，未修改）
- `docs/spike-results/pipeline-round1/` — 输出目录：
  - 全屏 8 张 × threshold=0.1 (24 files)
  - COMIC-setting 阈值扫描 7 组 × 3 (21 files)
  - Zoom-In 5 张 × 2 阈值 × 3 (30 files)
  - 总计 75 个输出文件
