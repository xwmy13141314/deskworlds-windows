# 故障排查指南

本指南覆盖实际使用中最常见的问题。每条都给出「现象 → 原因 → 解决」。

---

## 快速自检

先确认程序到底有没有在运行：

1. **看托盘**：右下角有没有"桌面世界"图标
2. **看日志**：`%APPDATA%\Deskworlds\deskworlds.log`
   - 正常应有：`view 0 ready` + `attached to desktop layer`
3. **看进程**：任务管理器里有没有 `python.exe`（命令行含 `host\main.py`）

---

## 一、看不到壁纸

### 现象
双击 `run.bat` 后，桌面没有变化，看不到动态场景。

### 原因与解决

| 子问题 | 说明 | 解决 |
| --- | --- | --- |
| **这是正常的** | 动态壁纸没有自己的窗口，铺在桌面最底层 | 按 **Win + D** 最小化所有窗口 |
| 控制台窗口挡着 | `run.bat` 的控制台会遮住桌面 | 等 2 秒它会自动最小化；或手动最小化 |
| 场景还在加载 | 首次加载需 5–15 秒 | 等待，看日志是否出现 `view 0 ready` |
| 程序没启动 | 依赖缺失或报错 | 看下一节"启动失败" |

### 验证
按 Win+D 后，如果能看到水下场景 + 桌面图标，说明一切正常。

---

## 二、桌面图标被壁纸盖住 / 看不到图标

### 现象
按 Win+D 看到全屏场景，但"此电脑""回收站"等图标不见了。

### 原因
窗口没有正确挂到「壁纸层」，而是变成了置底顶层窗口（盖住了图标层）。常见于：
- Windows 版本桌面结构与预期不同
- 桌面整理软件（360 桌面助手等）改动了窗口层级
- 之前有异常退出留下脏状态

### 解决

1. **托盘 → 🔄 重新加载**（重建窗口层级）
2. 若仍不行：**托盘 → 🖥 临时看桌面图标**（临时隐藏壁纸，图标完全可用）
3. 彻底重启：`stop.bat` → `run.bat`

### 深层修复（进阶）
如果长期存在，可检查日志里 `attach to desktop layer` 是否成功：
```
INFO [dw] view 0 attached to desktop layer (hwnd=...)
```
若看到 `WorkerW 注入失败，回退置底方案`，说明系统未分离出壁纸层 WorkerW。此时可尝试重启 explorer：
- 任务管理器 → 找到"Windows 资源管理器" → 重新启动
- 再重启壁纸程序

---

## 三、壁纸不是全屏 / 右下角留白

### 现象
场景只铺了屏幕的一部分，右下角露出静态壁纸。

### 原因
DPI 缩放。程序未开 DPI 感知时，`Screen.Bounds` 返回的是 125%/150% 缩放后的逻辑像素（如 1920×1200 屏幕得到 1536×960）。

### 解决
已在 v1.0.0 修复（`SetProcessDpiAwareness(2)`）。若仍有问题：
1. 确认使用的是最新版本
2. 检查系统缩放设置（设置 → 显示 → 缩放）
3. 反馈你的分辨率与缩放比例

---

## 四、卡顿 / 掉帧 / 反应慢

### 原因与解决

| 原因 | 解决 |
| --- | --- |
| 世界太重（珊瑚礁 9MB 资源） | 切换到河床/斗鱼等轻量世界 |
| 画质过高 | 改 `config.json` 的 `quality` 为 `eco` |
| 集成显卡性能不足 | 关闭其他 GPU 密集程序；用 `eco` 档 |
| 遮挡检测触发降帧 | 这是正常的节能行为（20fps），移开遮挡窗口即恢复 |
| 电池供电 | 电池模式自动降到 30fps，插电恢复 60fps |

### 各世界性能参考

| 世界 | 复杂度 | 首帧加载 |
| --- | --- | --- |
| 河床 riverscape | 中（284 万三角面） | ~8 秒 |
| 珊瑚礁 reefscape | 高（含 9MB 烘焙） | ~10 秒 |
| 斗鱼 bettascape | 中 | ~5 秒 |
| 等离子球 plasmascape | 低 | ~3 秒 |
| 锦鲤池 koiscape | 中 | ~6 秒 |
| 篝火 bonfirescape | 低 | ~4 秒 |
| 湖上风暴 lakescape | 中 | ~6 秒 |

---

## 五、启动失败 / 报错缺少依赖

### 现象
双击 `run.bat` 弹出错误或闪退。

### 解决

**1. 检查 Python**
```bash
python --version
```
需要 3.10+。

**2. 手动安装依赖**
```bash
python -m pip install pywin32 pywebview pystray pillow
```

**3. 检查 WebView2 Runtime**
- Win11 通常预装
- 若缺失，从微软官网下载 "Microsoft Edge WebView2 Runtime"

**4. 检查场景目录**
确保 `deskworlds/` 与本目录同级，且存在：
```
deskworlds/scenes/riverscape/wallpaper.html
```

**5. 直接前台运行看报错**
```bash
cd host
python main.py
```
错误会直接打印在控制台。

---

## 六、重复启动 / 提示"已在运行"

### 现象
点了两次 `run.bat`，提示 `already running` 或出现多个实例。

### 说明
这是**单实例保护**，正常行为。第二次启动会被拦截。

### 彻底重启
```bash
stop.bat     # 停止所有实例
run.bat      # 重新启动
```

若 `stop.bat` 无效，任务管理器结束 `python.exe`（命令行含 `host\main.py`）后重试。

---

## 七、画面黑屏

### 现象
壁纸区域是纯黑，不是场景。

### 可能原因

| 原因 | 排查 |
| --- | --- |
| 显卡驱动问题 | 更新显卡驱动 |
| WebGL2 不可用 | 浏览器打开 `about:gpu` 检查；或在 `config.json` 改 `eco` 档 |
| 窗口层级错误 | 托盘 → 重新加载 |
| WebView2 渲染异常 | 删除 `%LOCALAPPDATA%\Deskworlds\webview_profile_*` 后重启 |

---

## 八、投喂了但看不到效果

### 说明
这是**正常的**。鱼食是毫米级小颗粒、缓慢下沉，视觉上非常细微。

### 确认投喂已触发
- 托盘会弹出"已投喂食物 🐟 鱼会游过来吃"
- 仔细看水面，能看到小鱼游向食物颗粒
- 鱼群会朝食物聚集

### 哪些世界可以投喂
河床、珊瑚礁、斗鱼、锦鲤池。等离子球不可投喂（菜单会显示"此世界无需投喂"）。

---

## 九、查看日志与诊断

### 日志位置
```
%APPDATA%\Deskworlds\deskworlds.log
```
（在文件管理器地址栏输入 `%APPDATA%\Deskworlds` 可直接打开）

### 关键日志含义

| 日志 | 含义 |
| --- | --- |
| `poll loop started` | 轮询线程启动 |
| `nav complete ... isSuccess=True http=200` | 页面加载成功 |
| `view 0 ready` | 场景就绪 |
| `attached to desktop layer (hwnd=...)` | 成功挂到桌面层 ✅ |
| `WorkerW 注入失败，回退置底方案` | 挂载失败，图标可能被盖 ⚠️ |
| `coverage: covered -> 20fps` | 检测到遮挡，降帧 |
| `UNCAUGHT EXCEPTION` | 有崩溃，需看堆栈 |

### 端到端验证脚本
```bash
cd host
python verify.py
```
会输出渲染统计（帧数、三角面、draw calls）并抓一张截图到 `verify_screenshot.png`。

---

## 十、彻底重置

如果一切都乱套了，按顺序执行：

```bash
# 1. 停止所有实例
stop.bat

# 2. 删除运行时数据（配置 + 缓存 + 锁）
#    在文件管理器打开 %APPDATA%\Deskworlds，删除整个文件夹
#    以及 %LOCALAPPDATA%\Deskworlds（WebView2 缓存）

# 3. 重新启动
run.bat
```

---

## 十一、已知兼容性问题

| 软件/环境 | 问题 | 建议 |
| --- | --- | --- |
| 360 桌面助手 / 腾讯桌面整理 | 窗口层级冲突，图标可能异常 | 暂时关闭整理软件，或使用"临时看桌面图标" |
| 多显示器不同 DPI | 部分屏幕可能尺寸不准 | 已用 PER_MONITOR_AWARE_V2，多数场景正常 |
| 远程桌面会话 | GPU 渲染可能不可用 | 本地使用 |
| 虚拟机 | WebGL2 可能不支持 | 需开启 3D 加速 |

---

## 反馈问题时请提供

1. Windows 版本（`winver`）
2. 日志文件 `%APPDATA%\Deskworlds\deskworlds.log`
3. 具体现象（截图更好）
4. 是否多显示器、缩放比例
