# 变更记录（CHANGELOG）

本文件记录 Deskworlds for Windows 的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [1.1.1] - 2026-11-23

### 修复（Fixed）

- **托盘点「❌ 退出」没反应**：`App.quit()` 运行在 pystray 托盘线程的菜单回调里，直接调用 `tray.stop()`（内部 `icon.stop()` 会 join 托盘线程）造成线程 self-join 死锁——表现是点击退出无响应、进程卡死无法关闭。
  - 修复：把停止托盘、退出 UI 消息循环、`os._exit()` 全部移到独立的 `_shutdown` 线程执行；托盘回调立即返回，不再自等待。
  - 验证：从工作线程触发 `quit()` 后进程 3 秒内自行结束（exit 0）；实测托盘点击退出正常关闭，日志出现 `quit` 记录。
  - 对应 Release：`v1.1.1`（安装包 `Deskworlds-Portable-v1.1.1.zip`）。

---

## [1.1.0] - 2026-11-19

### 新增（Added）

- **桌面右键菜单「喂鱼 🐟」**：桌面空白处右键 →「显示更多选项」→「喂鱼 🐟（桌面世界）」，直接投喂当前世界。
  - 实现：`host/shellmenu.py` 写入用户级注册表 `HKCU\Software\Classes\DesktopBackground\Shell\DeskworldsFeed`，无需管理员权限。
  - 触发：菜单执行 `Deskworlds.exe --feed` → 写信号文件 → 主程序轮询消费并投喂。
  - 注：Windows 11 的简化右键菜单会把传统项收进「显示更多选项」。
- **免安装打包**：`Deskworlds.spec` 用 PyInstaller 打包为独立可执行程序（`dist/Deskworlds/`），自带 Python 运行时，双击 `Deskworlds.exe` 即可运行，无需安装 Python。
- **随包使用说明**：`使用说明.txt`，面向非技术同事的操作指引。
- **应用图标**：`tools/make_icon.py` 生成 `app.ico`。

### 技术要点

- `--feed` 走快速路径：只写 `%APPDATA%\Deskworlds\.feed_request` 后立即退出，不加载 WebView2，启动极快。
- 打包使用 `console=True`（带控制台）：实测无控制台会导致 WebView2 GPU 子进程崩溃；控制台由程序启动后自动最小化。
- 场景路径解析兼容三种布局：打包后 `_MEIPASS/deskworlds`、仓库子目录 `./deskworlds`、开发同级 `../deskworlds`。

---

## [1.0.0] - 2026-11-19

首个正式发布版。实现 Windows 动态壁纸宿主，完整复用上游 `deskworlds` 的 7 个 3D 场景。

### 新增（Added）

#### 核心能力
- **桌面壁纸层渲染**：通过 `0x052C(0xD,0x1)` 分离出壁纸层 WorkerW，将 WebView2 窗口挂载到该层，实现「场景在图标之下、静态壁纸之上」，桌面图标正常显示且可点击。
- **WebView2 宿主**：用 Python + pythonnet 调用 WebView2（Edge Chromium），承载上游未改动的 `wallpaper.html`。
- **虚拟主机名映射**：`https://deskworlds.local/` 映射到本地场景目录，替代 macOS 的 `deskworlds://local` scheme，支持 ES Module 与 importmap。
- **文档脚本注入**：通过 `AddScriptToExecuteOnDocumentCreatedAsync` 注入兼容层，把 Mac 的 `window.webkit.messageHandlers` 协议映射到 WebView2，并注入 `scenePointer` 虚拟光标函数。**场景代码零改动**。
- **鼠标穿透**：`WS_EX_TRANSPARENT`，点击可穿透到桌面图标。
- **虚拟光标**：`GetCursorPos` 轮询 + `scenePointer` 注入，实现生物跟随鼠标。

#### 7 个世界
- 河床（riverscape）、珊瑚礁（reefscape）、斗鱼（bettascape）、等离子球（plasmascape）、锦鲤池（koiscape）、篝火（bonfirescape）、湖上风暴（lakescape）。

#### 交互
- **投喂食物**：河床/珊瑚礁/斗鱼/锦鲤，调用 `sceneFeed()`。
- **搅动篝火**：篝火世界。
- **节日彩灯**：湖上风暴世界开关小屋彩灯。
- **暂停/恢复**：`scenePause()`。

#### 系统集成
- **中文系统托盘菜单**：切换世界 / 投喂 / 暂停 / 重载 / 退出，带状态与 FPS 显示。
- **单实例保护**：PID 文件锁（`%APPDATA%\Deskworlds\instance.lock`）。
- **开机自启**：注册表 `HKCU\...\Run`，用 `pythonw` 无窗口启动。
- **配置持久化**：`%APPDATA%\Deskworlds\config.json`。
- **日志**：`%APPDATA%\Deskworlds\deskworlds.log`，含全局异常捕获。
- **托盘通知**：启动/切换世界/投喂均有中文气泡提示。

#### 性能与节能
- **画质档位**：eco / balanced / detail / native，默认 balanced（30fps / 180 万像素）。
- **电池节能**：`GetSystemPowerStatus` 检测，电池供电降帧至 30fps。
- **遮挡降帧**：16×10 网格采样检测桌面可见面积，被遮挡时降到 20fps（不停播）。
- **DPI 感知**：`SetProcessDpiAwareness(2)`，按物理分辨率全屏。

#### 安装与运维
- `install.bat`：安装依赖 + 注册自启。
- `run.bat`：启动（控制台自动最小化）。
- `stop.bat`：停止所有实例。
- `uninstall.bat`：移除自启项。
- `verify.py`：端到端验证脚本（渲染统计 + 截图）。

#### 文档与展示素材
- `PRD.md`：产品需求文档（功能清单、验收标准）。
- `CHANGELOG.md`：本变更记录。
- `docs/ARCHITECTURE.md`：架构设计、线程模型、关键技术。
- `docs/TROUBLESHOOTING.md`：11 类故障排查。
- `docs/images/worlds/`：7 个世界的展示截图（1280×800，用于 README 与 GitHub 展示）。
- `tools/capture_screenshots.py`：批量重新生成展示截图。

### 修复（Fixed）

开发过程中定位并修复的关键问题：

| # | 问题 | 根因 | 修复 |
| --- | --- | --- | --- |
| 1 | `pythonw` / 隐藏控制台导致 WebView2 崩溃 | 隐藏控制台子系统干扰 WebView2 GPU 子进程 | 改用普通 `python.exe`，启动后 `ShowWindow(SW_MINIMIZE)` 最小化控制台 |
| 2 | 桌面完全不显示场景 | `0x052C` 用了 `(0,0)` 参数，Win11 未分离 WorkerW；SetParent 到 Progman 导致画面黑屏 | 改用 `0xD/0x1` 参数分离壁纸层 WorkerW，加 `WS_CHILD` 后挂载 |
| 3 | 桌面图标被壁纸盖住 | 窗口未正确挂到图标层之下 | 挂到壁纸层 WorkerW（位于 DefView 之下），实测 Z 序正确 |
| 4 | 壁纸不是全屏 | 未开 DPI 感知，拿到 125% 缩放后的 1536×960 | `SetProcessDpiAwareness(2)` → 物理 1920×1200 |
| 5 | 看起来不动、频繁卡顿 | 遮挡检测每 30ms 全窗口枚举，且可见<15% 就完全暂停，反复横跳 | 检测降到每秒一次；遮挡时降帧 20fps 而非停播 |
| 6 | `run.bat` 中文乱码导致启动失败 | `chcp 65001` + 中文符号破坏命令行解析 | 批处理改为纯 ASCII |
| 7 | 重复启动产生多实例 | 命名互斥体判断不可靠 | 改用 PID 文件锁 |
| 8 | `native` 画质崩溃 | 1600 万像素 + 4096 阴影压垮集成显卡 WebGL2 进程 | 默认降为 `balanced` |
| 9 | WebMessage 回传不通 | 本机 WebView2 `WebMessageReceived` 异常 | 改为宿主主动轮询 `window.__dwReady/__dwErrors/sceneStats()` |
| 10 | 托盘菜单英文 | 初版沿用原项目英文文案 | 全面中文化（世界名、动作、状态、提示） |

### 技术方案演进（Changed）

1. **窗口层级方案**（三次迭代）：
   - v0：`SetParent` 到 Progman → WebView2 黑屏 ❌
   - v1：普通顶层窗口 `HWND_BOTTOM` 置底 → 场景正常但盖住图标 ❌
   - v2：`0x052C(0xD,0x1)` 分离壁纸层 WorkerW + `WS_CHILD` + `SetParent` → 场景与图标共存 ✅
2. **启动方式**：`python` 前台 → `pythonw`（崩溃）→ 普通 `python` + 控制台最小化 ✅
3. **页面状态通信**：`postMessage` 双向 → 宿主主动轮询 ✅

### 已知限制（Known Limitations）

- 多显示器共享同一世界选择（未实现独立设置）。
- 与部分桌面整理软件（如 360 桌面助手）可能层级冲突。
- 珊瑚礁场景首帧加载较慢（约 10 秒，含 9MB 烘焙资源）。
- 集成显卡建议使用 `eco` 或 `balanced` 档。

### 验证（Verified）

在 Windows 11 22631 + Python 3.13 + WebView2 138 上实测：
- ✅ 7 个世界均正常渲染
- ✅ 桌面图标显示在场景之上且可点击
- ✅ 场景全屏铺满
- ✅ 投喂调用链 `main.feed() → bridge.feed() → sceneFeed()` 生效
- ✅ 托盘中文菜单全部可用
- ✅ 单实例保护生效
- ✅ 连续运行稳定，无未捕获异常

---

## 版本命名说明

| 版本 | 含义 |
| --- | --- |
| MAJOR | 不兼容的架构变更（如更换渲染内核） |
| MINOR | 向后兼容的功能新增 |
| PATCH | 向后兼容的问题修复 |
