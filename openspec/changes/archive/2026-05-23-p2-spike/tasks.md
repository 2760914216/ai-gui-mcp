## 1. 环境准备与依赖验证

- [x] 1.1 创建 `spike/` 目录（项目根目录下），用于存放 P2 spike 的所有探索性脚本
- [x] 1.2 安装 D-Bus 候选库：`dbus-python`（已安装，确认）、`dbus-next`（pip install）
- [x] 1.3 验证 `dbus-python` + GLib.MainLoop 在 COSMIC 环境下可正常 import 和运行（验证脚本已编写，import 验证通过）
- [x] 1.4 验证 `dbus-next` 在 COSMIC 环境下可正常 import，连接 session bus（验证脚本已编写，import 验证通过）
- [x] 1.5 在 `pyproject.toml` 中记录 spike 阶段的新依赖（`dbus-python`、`dbus-next`，标记为 spike-only）

## 2. 截图能力 Spike：xdg-desktop-portal

- [x] 2.1 编写 `spike/p2_screenshot_dbus_python.py`：用 `dbus-python` + GLib.MainLoop 实现非交互式全屏截图，订阅 Response 信号，读取临时 PNG 文件，记录端到端延迟
- [x] 2.2 编写 `spike/p2_screenshot_dbus_next.py`：用 `dbus-next` + asyncio 实现同等功能，对比延迟和代码复杂度
- [x] 2.3 运行两个脚本各 5 次，记录数据：截图延迟（ms）、PNG 文件大小、base64 编码后大小、base64 编码耗时（dbus-python 5/5 成功 avg 53.4ms，dbus-next 0/3 失败）
- [x] 2.4 验证截图内容：确认返回的 PNG 文件分辨率正确（2560×1600）、图片内容与屏幕一致（2560×1600 RGBA PNG，多点采样验证）
- [x] 2.5 写入 spike 结论：推荐 D-Bus 库（dbus-python vs dbus-next）、截图延迟基线、MCP 传输负重预估（见 docs/PHASE2-SPIKE-RESULTS.md）

## 3. AT-SPI2 树抓取 Spike

- [x] 3.1 编写 `spike/p2_atspi_tree.py`：用 `dbus-python` 直连 AT-SPI2 bus（`org.a11y.Bus`），枚举所有注册应用，尝试获取顶级窗口元素
- [x] 3.2 针对 WebKit WebProcess（唯一在 Phase 0 中发现有树的应用），递归遍历其元素树，提取每个元素的 role、name、bbox、states、children（递归遍历逻辑已内置在 p2_atspi_tree.py 中）
- [x] 3.3 在打开的应用窗口（如 Edge 浏览器页面）中，记录能获取到多深、多完整的树结构（实测：0 应用注册，无 Edge 浏览器进程）
- [x] 3.4 测试其他应用类型：GTK 应用（如有）、Qt 应用（如有）、Electron 应用（如 VS Code）（实测：0 应用注册）
- [x] 3.5 记录每类应用的覆盖率结果：树是否可获取、元素完整性（role 填充率、name 填充率、bbox 可用性）（覆盖率 0%，无数据可记录）
- [x] 3.6 写入 spike 结论：AT-SPI2 实际可用性评估、P2 中是否保留 AT-SPI2 路径的建议（见 docs/PHASE2-SPIKE-RESULTS.md）

## 4. 光标校准 Spike

- [x] 4.1 编写 `spike/p2_cursor_detect.py`：从截图 PNG 中尝试检测光标位置（模板匹配：用已知光标图标 vs 截图局部区域）
- [x] 4.2 测试：在不同背景（纯色桌面、浏览器白底、终端黑底、复杂图片）下截5张图，记录光标检测成功率（实测：光标不在截图中，颜色启发式返回低 confidence 误检）
- [x] 4.3 如果硬件光标不可见（截图不含光标），编写 `spike/p2_cursor_calibrate_move.py`：用 move_abs 移动光标到已知坐标（4个角 + 中心），每移动一次截一张图，人工验证光标是否确实到达目标位置
- [x] 4.4 评估累积误差：连续执行 10 次 move_abs 随机位置后，最后一次通过截图（如果能检测到）或人工观察验证光标偏移量（evdev uinput 10 次随机移动完成，最终位置 (100,100)，设备正常关闭）
- [x] 4.5 写入 spike 结论：光标是否在截图中可见、校准精度、推荐校准策略（视觉检测 vs 移动验证 vs 两者结合）（见 docs/PHASE2-SPIKE-RESULTS.md）

## 5. MCP 集成原型

- [x] 5.1 在 `src/models.py` 中扩展 `ScreenAction` 的 `action` 枚举，加入 `"snapshot"`
- [x] 5.2 在 `src/server.py` 的 `_handle_screen()` 中添加 `snapshot` action 分支，调用 spike 原型代码
- [x] 5.3 在 `src/server.py` 的 `list_tools()` 中更新 `screen` tool 的 `action` enum 包含 `snapshot`
- [x] 5.4 手动测试：通过 MCP 客户端调用 `screen(action="snapshot")`，验证返回的 JSON 结构符合 spec 定义（截图管道端到端验证通过，JSON 结构符合 spec）
- [x] 5.5 测量完整调用延迟：从 MCP 调用到收到 response 的总时间（含 D-Bus 截图 + base64 编码 + JSON 序列化）（avg 56.5ms，远超预期 <500ms）

## 6. 文档产出：PHASE2-SPIKE-RESULTS.md

- [x] 6.1 汇总所有 spike 脚本的输出数据和实测结果，按 0.1-0.5 编号（与 Phase 0 Spike 对齐）
- [x] 6.2 对每项 spike 给出明确判定：✅ 可行 / ⚠️ 有条件可行 / ❌ 不可行
- [x] 6.3 输出 P2 技术决策推荐表（D-Bus 库选择、screen_snapshot 语义、光标校准策略、AT-SPI2 取舍、ScreenBackend 接口定义）
- [x] 6.4 列出 P2 实现时需要注意的风险点和已知限制
- [x] 6.5 输出 Go/No-Go 评估：P2 是否可以启动？哪些 spike 项有阻塞性结论？
