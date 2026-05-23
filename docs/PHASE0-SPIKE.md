# Phase 0: 环境验证 Spike

> **目标**：动手写代码前，把技术栈的每个环节都实测一遍，筛选确认
> **时间**：半天
> **平台**：当前机器（Linux Wayland COSMIC）

---

## 为什么必须先做

技术选型文档里的假设不等于实际环境的表现。Phase 0 的目标是把每个"应该可以"变成"实测可以"或"实测不行，换方案"。

## 验证清单

### 0.1 uinput 输入注入

**验证点**：python-evdev 写入 `/dev/uinput` 的鼠标/键盘事件能否被 COSMIC 上的应用接收？

```bash
# 确认 /dev/uinput 可读写
ls -la /dev/uinput
# 预期：crw------- 1 root root ...  → 需要 input 组权限

# 如果在 input 组中，运行快速验证脚本
python3 -c "
import evdev
from evdev import UInput, ecodes as e
ui = UInput({e.EV_REL: [e.REL_X, e.REL_Y], e.EV_KEY: [e.BTN_LEFT]},
            name='spike-test')
ui.write(e.EV_REL, e.REL_X, 100)
ui.write(e.EV_REL, e.REL_Y, 100)
ui.syn()
print('uinput 写入成功，检查鼠标是否移动了 100px')
"
```

**判定标准**：
- ✅ 鼠标实际移动 → uinput 方案可行
- ❌ 鼠标未移动 → 排查 input 组权限；若仍不行，考虑替代方案

### 0.2 键盘注入

**验证点**：uinput 键盘事件能否被应用接收？组合键（Shift + 字符）是否正确？

```python
# 快速验证：在文本编辑器里运行此脚本，看是否打出大写 A
python3 -c "
from evdev import UInput, ecodes as e
ui = UInput({e.EV_KEY: list(e.keys.keys())}, name='spike-kbd')
# 模拟 Shift + A
ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1); ui.syn()
ui.write(e.EV_KEY, e.KEY_A, 1); ui.syn()
ui.write(e.EV_KEY, e.KEY_A, 0); ui.syn()
ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0); ui.syn()
print('如果光标处出现了 A → 键盘方案可行')
"
```

### 0.3 屏幕分辨率获取

**验证点**：在 Wayland COSMIC 下如何获取屏幕分辨率？

```bash
# 方案 A: wlr-randr（wlroots 系可用，COSMIC 需实测）
which wlr-randr && wlr-randr 2>/dev/null

# 方案 B: cosmic-comp 的 DBus 接口
busctl --user introspect com.system76.CosmicComp /com/system76/CosmicComp 2>/dev/null | grep -i "output\|display\|screen" | head -20

# 方案 C: kms 直接读（需 drm 权限）
python3 -c "
import os
for f in sorted(os.listdir('/sys/class/drm/')):
    if f.startswith('card'):
        print(f)
" 2>/dev/null

# 方案 D: 硬编码 + 配置文件
# 如果以上都不可行，要求用户在 config.yaml 里手动配置分辨率
```

**判定标准**：找到至少一种**不需要交互授权**的方式获取分辨率。

### 0.4 内部坐标追踪精度

**验证点**：uinput 相对移动的累积误差有多大？

```python
# 跑 20 次 move_rel(100, 0)，看鼠标是否回到原点附近
python3 -c "
import evdev, time
from evdev import UInput, ecodes as e
ui = UInput({e.EV_REL: [e.REL_X, e.REL_Y]}, name='spike-track')
for i in range(20):
    ui.write(e.EV_REL, e.REL_X, 100); ui.syn()
    time.sleep(0.05)
for i in range(20):
    ui.write(e.EV_REL, e.REL_X, -100); ui.syn()
    time.sleep(0.05)
print('观察鼠标是否回到接近原位。若有明显偏移 → 追踪误差较大')
"
```

**判定标准**：
- ✅ 鼠标回到原位（误差 < 20px）→ 内部追踪可靠
- ⚠️ 偏移明显（> 50px）→ compositor 鼠标加速干扰，需考虑校准策略

### 0.5 AT-SPI2 覆盖率扫描（P2 决策用）

**验证点**：在当前环境上，用 5-10 个实际应用测 AT-SPI2 能拿到多少结构化信息。

```bash
# 安装探测工具
pip install dasbus  # 推荐，轻量无 GObject 依赖

# 对每个目标应用运行
python3 -c "
import dasbus.connection
bus = dasbus.connection.SessionMessageBus()
# 列出所有注册了 AT-SPI2 的应用
proxy = bus.get_proxy('org.a11y.Bus', '/org/a11y/bus')
print(proxy.Introspect())
" 2>/dev/null
```

**目标应用列表**（选你常用的）：
- 文本编辑器（如 COSMIC Edit）
- 终端（如 COSMIC Terminal / Alacritty）
- 浏览器（Edge）
- 文件管理器（COSMIC Files）
- 设置应用（COSMIC Settings）
- IDE（如 VS Code）
- 一个 Electron 应用（如 Discord/Slack）
- 其他你日常用的

**对每个应用记录**：
| 应用 | 可获取树的完整度 | 能读到按钮/输入框的 name/role/bbox？ |
|------|:---------------:|:-----------------------------------:|
| COSMIC Edit | ? | ? |
| Edge | ? | ? |
| VS Code | ? | ? |
| ... | | |

**判定标准**：统计有树 vs 无树的比例。这决定 P2 视觉层该多早投入、投入多大。

### 0.6 截图方案确认（P2 预备）

**验证点**：确认非交互式截图在 COSMIC 上的可行方案。P1 不需要截图，但 P2 会需要。

```bash
# 方案 A: xdg-desktop-portal Screenshot（通过 DBus）
gdbus call --session \
  --dest org.freedesktop.portal.Desktop \
  --object-path /org/freedesktop/portal/desktop \
  --method org.freedesktop.portal.Screenshot.Screenshot \
  '' '{ "handle_token": "spike0", "interactive": <false> }'

# 如果上面弹窗或报错，记录行为。
# 方案 B: grim（仅 wlroots，COSMIC 大概率不可用，跳过）
# 方案 C: PipeWire 截屏流（复杂但最通用，P2 再深入）
```

---

## Phase 0 产出物

完成后记录一份简短结论：

```
Phase 0 结论
═══════════

0.1 uinput 注入:  ✅ / ❌ — [备注]
0.2 键盘注入:    ✅ / ❌ — [备注]
0.3 屏幕分辨率:  方案 X 可用
0.4 坐标追踪:   误差约 Xpx
0.5 AT-SPI2:    X/Y 应用有树，视觉层预估承担 Z% 工作
0.6 截图方案:   方案 X 可行（P2 再实现）
```

这份结论直接决定 PHASE1-IMPLEMENTATION.md 的技术选型是否成立。有不可行的项目 → 换方案后再动手写代码。
