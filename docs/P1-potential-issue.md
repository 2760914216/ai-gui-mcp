# P1 实测问题与改进建议

> **实测日期**: 2026-05-23
> **测试方式**: 通过 OpenCode MCP 客户端直接调用 mouse/keyboard/screen/batch 四个 tool
> **测试环境**: Linux Wayland COSMIC, 2560×1600

---

## 1. ✅ 已验证正常的功能

| 功能 | 测试操作 | 结果 |
|------|----------|------|
| `screen.size` | KMS 检测 | 2560×1600（正确覆盖 config 的 1920×1080） |
| `mouse.move_abs` | 移到 (500,300) | 正常 |
| `mouse.move_rel` | 相对位移 | 正常 |
| `mouse.scroll` | 滚轮 dy=-3 | 正常 |
| `mouse.down / up` | 按下/释放 | 正常 |
| `keyboard.type` | 打字含大写 | 正常（Shift 映射正确） |
| `keyboard.press` | 组合键 ctrl+s | 正常 |
| `batch` 顺序执行 | 3 个 move 全部成功 | 正常，返回 completed=3 |
| `batch` 遇错中止 | 第 2 步出错后停止 | 正确返回 completed=1 |
| 坐标超界保护 | x=99999 | 拒绝，返回 "0 <= x < 2560" |

---

## 2. ❌ 用户报告的已知问题（已确认）

### 2.1 click 必须给坐标 → 确认是严重 UX 问题 → ✅ 已修复

```
mouse(action="click")  →  Error: mouse action 'click' requires x and y parameters
```

**实测验证**：
- 单次调用 `click` 不传 x,y → 报错
- batch 中 `move_rel` 后跟 `click` → 在第 2 步报错中止

**唯一变通方案（修复前）**：用 `down()` + `up()` 代替 `click()`。修复后 `click()` 无参数直接可用。

```
# ❌ AI 通常会这样写（失败）
batch([move_rel(dx=100, dy=0), click()])

# ✅ 可行的写法（但 AI 不会自然想到）
batch([move_rel(dx=100, dy=0), down(), up()])
```

**影响**：AI agent 无法用 "先相对移动到目标位置，再点击" 的工作流。大多数 AI 看到 `click` action 会直接用，不会想到 down/up 组合。

### 2.2 移到中心 (1280, 800) 位置不对

最可能的原因不是 `move_abs` 实现有 bug，而是**内部坐标跟踪与实际光标位置漂移**：

```
内部跟踪        实际光标           状态
────────────────────────────────────────
(0, 0)         (0, 0)           ✓ 初始同步
move_abs(500,300) → 光标到 (500,300)
(500,300)      (500,300)        ✓ 同步

用户碰了一下触摸板...
(500,300)      (700,200)        ✗ 漂移！

move_abs(1280,800)
dx = 1280-500 = 780
实际位移: 从 (700,200) → (1480,1000)  ✗ 已偏到屏幕右下
```

**一次外部干扰 → 此后所有绝对移动全错。**

---

## 3. 🆕 额外发现的设计缺陷

### D1：初始位置假设 (0,0) 几乎必错 → ⚠️ 仍待解决（`screen cursor` 可查询但无自动校准）

```python
# uinput.py 第 142 行
self._x: int = 0
self._y: int = 0
```

MCP 启动时假设光标在 (0,0)。但实际情况几乎永远是——MCP 重启后光标在屏幕某处，位置未知。没有任何校准机制。

### D2：无位置查询能力 → ✅ 已修复（添加 `screen(action="cursor")`）

没有 `mouse(action="position")` 或 `screen(action="cursor")` 可查询当前光标位置。AI session 是 stateless 的，无法靠记忆追踪位置。

### D3：batch 丢失中间结果 → ✅ 已修复（batch 返回 `results` 数组）

```
batch([screen.size, mouse.move, ...]) → {"completed": 3, "total": 3}
```

只返回完成计数，`screen.size` 的返回值 (2560×1600) 被丢弃。AI 无法在一个 batch 里 "取屏幕尺寸 → 计算坐标 → 移动"。

### D4：config 与实际分辨率不一致时的静默差异 → ✅ 已修复（启动时打印 warning）

```yaml
# config.yaml 写的是
screen:
  width: 1920
  height: 1080
```

但 KMS 检测返回 2560×1600，且 `_validate_coords` 用的是 KMS 值而非 config 值。启动时没有日志告知 AI 实际使用的分辨率。如果 AI 按 config 计算坐标（如中心 = 960,540），实际位置会偏，但没有警告。

---

## 4. 🛠 改进建议

### 优先级：🔴 P0 （阻塞 AI 可用性）

| 问题 | 建议 | 状态 |
|------|------|:--:|
| click 必须传坐标 | `MouseAction` 中 `x,y` 改为真正 optional。click/dbl_click/right_click 缺 x,y 时直接在当前光标位置点击。 | ✅ 已修复 |
| 内部跟踪漂移 | 增加 `screen(action="cursor")` 返回当前跟踪位置。后续 P2 引入截图后可做视觉定位校准。 | ✅ cursor 已加；自动校准仍待 P2 |

### 优先级：🟡 P1 （影响开发体验）

| 问题 | 建议 | 状态 |
|------|------|:--:|
| batch 丢失中间结果 | batch 返回数组 `[result1, result2, ...]` 而非仅计数。 | ✅ 已修复 |
| 启动无校准 | 启动时检测到光标位置未知，打印警告。 | ✅ 已修复（resolution logging） |

### 优先级：🟢 P2 （改善类）

| 问题 | 建议 | 状态 |
|------|------|:--:|
| config 与实际分辨率不一致 | 启动时打印 "detected: 2560×1600, config: 1920×1080, using detected"。 | ✅ 已修复 |
| drag 接口不够直观 | drag 改为 `(x1, y1, x2, y2)`。 | ✅ 已修复 |

### 优先级：🔵 P3 （未来考虑）

| 问题 | 建议 |
|------|------|
| click 的语义分裂 | 当前 click=move+click。如果改成 x,y 可选，则 click 有两种语义：有 coord 时 = move+click，无 coord 时 = 原地 click。考虑拆分为 `click_at(x,y)` + `click()` 更清晰。但不急，先让 AI 能用起来。 |
| 相对移动累积误差 | `move_rel` 使用单次大位移（spike 实测 ≤20px 误差），但如果 AI 大量使用小步 `move_rel`，误差可能累积。需长期观察。

---

## 5. 最小可操作修复 → ✅ 已实现

> **让 `click` / `dbl_click` / `right_click` 在 x,y 缺失时直接用当前光标位置点击。**

改动范围（已完成）：
- `src/models.py`: MouseAction 的 x,y 均为 Optional
- `src/server.py` `_handle_mouse()`: 当 action 是 click/dbl_click/right_click 且 x,y 缺失时，跳过 move，直接调用 backend 的 mouse_down/mouse_up
- `src/backends/base.py` + `uinput.py`: 无改动（backend 的 click 接口不变，只是 server 层的路由逻辑调整）

预估改动量：~15 行。**实际已实现。**
