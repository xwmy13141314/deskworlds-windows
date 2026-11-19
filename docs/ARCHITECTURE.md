# 架构设计文档

本文面向开发者，说明 Deskworlds for Windows 的整体架构、线程模型、模块职责与关键技术实现。

---

## 一、总体架构

```
┌──────────────────────────────────────────────────────────────┐
│                      上游场景（零改动复用）                     │
│  deskworlds/scenes/{7 worlds}/wallpaper.html + Three.js/WebGL2 │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP(虚拟主机名映射)
┌───────────────────────────▼──────────────────────────────────┐
│                    Python 宿主（本复刻）                       │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  UI 线程    │  │  轮询线程    │  │  托盘线程    │          │
│  │  (STA)      │  │  (daemon)   │  │  (pystray)  │          │
│  │  WinForms   │  │  状态决策    │  │  菜单回调    │          │
│  │  + WebView2 │  │  光标注入    │  │             │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         │                │                │                 │
│  ┌──────▼────────────────▼────────────────▼──────┐          │
│  │              App (main.py) 状态中枢            │          │
│  └──────┬────────────────┬────────────────┬──────┘          │
│         │                │                │                 │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐          │
│  │  bridge.py  │  │ desktop.py  │  │  tray.py    │          │
│  │  WebView2   │  │  Win32 API  │  │  托盘菜单    │          │
│  └──────┬──────┘  └──────┬──────┘  └─────────────┘          │
└─────────┼────────────────┼───────────────────────────────────┘
          │                │
┌─────────▼──────┐  ┌──────▼─────────────────────────────────┐
│  WebView2      │  │  Windows 桌面窗口树                    │
│  (Edge Chromium)│  │  Progman / WorkerW / SHELLDLL_DefView │
└────────────────┘  └────────────────────────────────────────┘
```

---

## 二、线程模型

WebView2 有严格的线程约束：**必须在 STA 线程创建，且所有访问必须在创建它的 UI 线程**。因此采用三线程模型：

| 线程 | 职责 | 关键约束 |
| --- | --- | --- |
| **UI 线程**（STA） | 创建 WinForms 窗口 + WebView2，运行 `Application.Run()` 消息循环 | 所有 `CoreWebView2` 访问必须在此线程 |
| **轮询线程**（daemon） | 每 ~33ms 检查：电源、页面 ready、遮挡、光标位置 | 跨线程调用 UI 用 `form.Invoke` |
| **托盘线程**（pystray） | 托盘图标与菜单的消息循环 | 菜单回调中操作 UI 用 `_refresh_tray` 重建 |

### 跨线程调用约定

```python
# 轮询线程 → UI 线程（执行 JS）
def eval_sync(self, script):
    ev = threading.Event()
    def run():
        task = core.ExecuteScriptAsync(script)
        task.ContinueWith(Action[Task[String]](lambda t: cb(t)))
    self.form.Invoke(System.Action(run))   # 切到 UI 线程
    ev.wait(timeout=2.5)                    # 等结果
```

> ⚠️ 直接在非 UI 线程访问 `self.webview.CoreWebView2` 会抛
> `InvalidOperationException: CoreWebView2 can only be accessed from the UI thread`。

---

## 三、模块职责

### 3.1 `main.py` — 应用中枢

- `App` 类持有配置、视图列表、托盘、线程状态
- `_ui_main()`：UI 线程入口，创建每屏视图、加载场景、运行消息循环
- `_poll_loop()`：轮询线程，驱动状态机
- `_decide_rate()`：帧率决策（核心逻辑）
- 托盘动作：`select_world / feed / toggle_pause / reload / quit`

**帧率决策表**：

| 条件 | 帧率 |
| --- | --- |
| 用户暂停 | 0（停止） |
| 桌面被遮挡 | 20 |
| 电池供电 | 30 |
| 插电 + 可见 | 60 |

### 3.2 `bridge.py` — WebView2 桥接

`WallpaperView` 类：每个屏幕一个实例，持有 Form + WebView2。

关键能力：
- **虚拟主机名映射**：`SetVirtualHostNameToFolderMapping("deskworlds.local", scene_root, Allow)`，让 `https://deskworlds.local/scenes/...` 映射到本地目录，支持 ES Module。
- **文档脚本注入**（`BOOTSTRAP_JS`）：把 Mac 的 `window.webkit.messageHandlers` 协议映射到 WebView2，注入 `scenePointer`/`scenePointerOut` 虚拟光标，收集 `__dwReady`/`__dwErrors`。
- **状态轮询**：`poll_state()` 读取 `window.__dwReady`、`sceneStats()`、`__dwErrors`。
- **scene* 接口**：`set_rate/set_power/set_paused/feed/pointer/pointer_out`，通过 `ExecuteScriptAsync` 调用页面函数。

### 3.3 `desktop.py` — Win32 桌面层

纯 ctypes 封装，无第三方依赖。核心函数：

| 函数 | 作用 |
| --- | --- |
| `attach_to_desktop(hwnd)` | 挂载到壁纸层 WorkerW（核心） |
| `_get_wallpaper_workerw()` | `0x052C(0xD,0x1)` 分离并定位壁纸层 |
| `set_wallpaper_visible()` | 显示/隐藏（备用） |
| `get_cursor_pos()` | 全局光标轮询 |
| `is_on_battery()` | 电源状态 |
| `window_covers_screen()` | 16×10 网格遮挡采样 |

### 3.4 `tray.py` — 托盘

pystray + Pillow（图标用代码绘制，无外部资源依赖）。菜单动态重建，反映当前世界/状态/FPS。

### 3.5 `config.py` — 配置与世界注册表

`WORLDS` 是单一事实源（id / 英文名 / 中文名 / 动作类型）。配置文件读写到 `%APPDATA%\Deskworlds\config.json`。

### 3.6 `singleton.py` — 单实例锁

PID 文件锁：写入当前 PID，启动时检查旧 PID 是否存活（`OpenProcess` + `GetExitCodeProcess`）。

### 3.7 `autostart.py` — 开机自启

注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，用 `pythonw.exe` 启动。

---

## 四、关键技术详解

### 4.1 壁纸层挂载（最核心）

**问题**：Windows 上让窗口位于「桌面图标之下、静态壁纸之上」。

**桌面窗口树**（Win11）：
```
Progman (Program Manager)
├── WorkerW (图标层, 含 SHELLDLL_DefView → SysListView32)
└── WorkerW (壁纸层, 空)
```

**关键消息**：`0x052C`（未公开），用于分离 WorkerW。

```python
# 必须用 0xD / 0x1 参数（Win11），(0,0) 无效
user32.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, None)

# 枚举找含 SHELLDLL_DefView 的 WorkerW（图标层）
# 它之后的 WorkerW 就是壁纸层
def enum_proc(hwnd, _):
    if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
        wallpaper_workerw = user32.FindWindowExW(None, hwnd, "WorkerW", None)

# 加 WS_CHILD 后挂载
style = GetWindowLongW(hwnd, GWL_STYLE)
SetWindowLongW(hwnd, GWL_STYLE, style | WS_CHILD)   # 0x40000000
SetParent(hwnd, wallpaper_workerw)
```

**为什么不能直接 SetParent 到 Progman**：实测 WebView2 和 QtWebEngine 都会黑屏（跨进程父子 + D3D 合成失效）。必须挂到壁纸层 WorkerW。

**为什么不能只置底（HWND_BOTTOM）**：Progman 是最底层系统窗口，普通窗口永远在它之上，会盖住图标。

### 4.2 WebView2 渲染与 DPI

- **DPI 感知**：`SetProcessDpiAwareness(2)`（PER_MONITOR_AWARE_V2）必须在创建窗口前调用，否则 `Screen.Bounds` 返回缩放后的逻辑像素。
- **禁止 WS_EX_LAYERED**：分层窗口会让 WebView2 的 D3D 内容不合成，画面变黑。
- **控制台**：隐藏控制台（`pythonw` / `CREATE_NO_WINDOW`）会导致 WebView2 GPU 子进程崩溃。方案：普通 `python.exe` + 启动后 `ShowWindow(SW_MINIMIZE)`。

### 4.3 虚拟光标

壁纸窗口鼠标穿透，收不到真实鼠标事件。方案：
1. 轮询线程 `GetCursorPos()` 读取全局光标
2. 换算到对应屏幕坐标
3. `ExecuteScriptAsync("scenePointer(x,y)")`
4. 页面注入的 `scenePointer` 向 `#scene` canvas 派发合成 `PointerEvent('pointermove')`

### 4.4 状态通信（无 postMessage）

本机 WebView2 的 `WebMessageReceived` 收不到页面 `postMessage`。方案：
- **宿主 → 页面**：`ExecuteScriptAsync`（正常）
- **页面 → 宿主**：页面写入 `window.__dwReady` / `window.__dwErrors` / `sceneStats()`，宿主主动轮询

### 4.5 单实例

```
启动 → 读 instance.lock 的 PID
  ├─ PID 存活 → 退出（提示已在运行）
  └─ 不存在/已死 → 写入当前 PID，继续
退出 → 删除锁文件（仅当 PID 是自己）
```

---

## 五、数据流

### 启动流程

```
main()
 ├─ singleton.acquire()          # 单实例检查
 ├─ 启动 UI 线程 (STA)
 │   ├─ 枚举屏幕 → 创建 WallpaperView（每屏一个）
 │   ├─ form.Show() → 拿 HWND
 │   ├─ ensure() → WebView2 异步初始化
 │   └─ load_world() → 导航到 wallpaper.html
 ├─ 启动轮询线程
 │   └─ poll_state() 检测 ready → attach_to_desktop()
 └─ tray.run()                   # 阻塞，托盘消息循环
```

### 状态变更流程

```
用户点托盘「投喂」
  → App.feed()
    → 遍历 views → v.feed()
      → bridge._exec("sceneFeed()")
        → form.Invoke → ExecuteScriptAsync   # UI 线程
          → 页面 sceneFeed() → 鱼游向食物
    → tray.notify("已投喂食物 🐟")
```

---

## 六、扩展点

| 需求 | 扩展方式 |
| --- | --- |
| 新增世界 | 在 `config.WORLDS` 加条目；场景放入 `deskworlds/scenes/<id>/` |
| 新增托盘动作 | `tray.py` 加菜单项 → `main.py` 加对应方法 |
| 更换画质策略 | 改 `main._decide_rate()` |
| 多显示器独立世界 | 把 `config["world"]` 改为每屏配置 |

---

## 七、调试

| 手段 | 方法 |
| --- | --- |
| 查看日志 | `%APPDATA%\Deskworlds\deskworlds.log` |
| 渲染统计 | `verify.py` 输出 `sceneStats()`（帧数/三角面/draw calls） |
| 截图验证 | `verify.py` 抓屏到 `verify_screenshot.png` |
| 检查窗口层级 | 用 Spy++ 或自写 EnumWindows 脚本 |
