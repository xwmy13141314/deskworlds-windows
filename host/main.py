"""
Deskworlds for Windows —— 动态壁纸宿主。

复用原项目（deskworlds/）的全部场景代码，仅重写原生外壳：
  WebView2 承载 wallpaper.html + WorkerW 桌面层 + 虚拟光标 + 系统托盘。

线程模型：
  - UI 线程：STA，运行 WinForms 消息循环 + WebView2（WebView2 必须在 STA + UI 线程访问）
  - 轮询线程：驱动 ready 检测、错误收集、电源/遮挡决策、虚拟光标注入
  - 托盘线程：pystray 自己的消息循环

说明：本机 WebView2 的 WebMessageReceived(postMessage) 通道不可用，
因此宿主 -> 页面用 ExecuteScriptAsync 推送，页面 -> 宿主用 window.__dwReady /
window.__dwErrors / sceneStats() 由宿主主动轮询读取。场景 JS 一行未改。
"""
import os
import sys
import time
import logging
import threading
import traceback

# ── 快速路径：桌面右键菜单「喂鱼」触发（<exe> --feed）──────────────────
# 只写一个信号文件就退出，不加载 WebView2 等重量级模块，启动极快。
if "--feed" in sys.argv:
    _appdata = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Deskworlds")
    try:
        os.makedirs(_appdata, exist_ok=True)
        with open(os.path.join(_appdata, ".feed_request"), "w", encoding="utf-8") as _f:
            _f.write("1")
    except Exception:
        pass
    sys.exit(0)

# ★ 必须在创建任何窗口之前开启 DPI 感知，否则 WinForms 返回的是 125%/150% 缩放后的
# 逻辑像素（如 1920x1200 屏幕只得到 1536x960），壁纸铺不满全屏。
try:
    import ctypes
    # PER_MONITOR_AWARE_V2 = -4，支持多显示器不同 DPI
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)  # deskworlds-win/


def _resolve_scene_root():
    """定位场景目录，兼容三种布局：
    1) 打包后：<exe同级>/deskworlds 或 <_MEIPASS>/deskworlds
    2) 仓库布局：<PROJECT>/deskworlds（子目录）
    3) 开发布局：<PROJECT>/../deskworlds（同级）
    """
    bases = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bases.append(meipass)
        bases.append(os.path.dirname(sys.executable))
    bases.append(PROJECT)
    candidates = [os.path.join(b, "deskworlds") for b in bases]
    candidates.append(os.path.join(PROJECT, "..", "deskworlds"))
    for p in candidates:
        if os.path.exists(os.path.join(p, "scenes")):
            return os.path.normpath(p).replace("\\", "/")
    return os.path.normpath(candidates[0]).replace("\\", "/")


SCENE_ROOT = _resolve_scene_root()

LOG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Deskworlds")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "deskworlds.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_PATH, encoding="utf-8")]
)
log = logging.getLogger("dw")


def _excepthook(exc_type, exc, tb):
    log.error("UNCAUGHT EXCEPTION:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))


sys.excepthook = _excepthook
_threading_excepthook = getattr(threading, "excepthook", None)


def _thread_excepthook(args):
    log.error("UNCAUGHT THREAD EXCEPTION in %s:\n%s",
              getattr(args, "thread", None),
              "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    if _threading_excepthook:
        _threading_excepthook(args)


threading.excepthook = _thread_excepthook

import clr
clr.AddReference("System.Windows.Forms")
import System.Windows.Forms as WinForms
from System.Threading import Thread, ThreadStart, ApartmentState

import config as cfgmod
import desktop
import bridge
import singleton
from tray import Tray


class App:
    def __init__(self):
        self.config = cfgmod.load()
        self.views = []
        self.screens = []
        self.tray = None
        self._stop = threading.Event()
        self._last_cursor = None
        self._last_battery = None
        self._last_covered = False
        self._current_rate = 0
        self._ui_ready = threading.Event()
        self._reported_errors = set()
        self._ready_handled = set()

    # ---------- 状态 ----------
    def current_rate(self):
        return self._current_rate

    def can_feed(self):
        return cfgmod.world_by_id(self.config["world"])["action"] != "none"

    def _decide_rate(self, battery, paused, covered):
        # 只有用户主动暂停才真正停止。被窗口遮挡时降帧而不停（保持"活着"的感觉，
        # 也避免反复 pause/resume 造成的卡顿）。电池 30，插电 60，遮挡 20。
        if paused:
            return 0
        if covered:
            return 20
        return 30 if battery else 60

    def _apply_state(self):
        rate = self._decide_rate(self._last_battery, self.config["paused"], self._last_covered)
        self._current_rate = rate
        for v in self.views:
            if v.ready:
                v.set_power(bool(self._last_battery))
                v.set_rate(rate)

    # ---------- UI 线程 ----------
    def _ui_main(self):
        try:
            for s in WinForms.Screen.AllScreens:
                b = s.Bounds
                self.screens.append((b.X, b.Y, b.Width, b.Height))

            for i, bounds in enumerate(self.screens):
                self.views.append(bridge.WallpaperView(
                    self, i, bounds, SCENE_ROOT,
                    on_ready=lambda v: None, on_message=lambda v, d: None))

            for v in self.views:
                v.show()

            # 先让 WebView2 初始化并加载场景，再挂桌面层（避免控件初始化受父级变更影响）
            for v in self.views:
                v.ensure()
                v.load_world(self.config["world"], quality=self.config["quality"],
                             holiday=self.config["holidayLights"], still=self.config["paused"])

            self._ui_ready.set()
            WinForms.Application.Run()
        except Exception:
            log.error("UI thread crashed:\n%s", traceback.format_exc())
            self._ui_ready.set()
            self._stop.set()

    def _attach_view(self, v):
        """页面就绪后再把窗口注入桌面层（顺序与验证脚本一致）。"""
        if getattr(v, "_attached", False):
            return
        v._attached = True
        try:
            ok = desktop.attach_to_desktop(v.hwnd)
            if not ok:
                log.warning("view %d: WorkerW 注入失败，回退置底方案", v.screen_index)
                desktop.set_bottom_fallback(v.hwnd)
            else:
                log.info("view %d attached to desktop layer (hwnd=%s)", v.screen_index, v.hwnd)
        except Exception as e:
            log.warning("view %d attach failed (%s) -> fallback", v.screen_index, e)
            desktop.set_bottom_fallback(v.hwnd)

    # ---------- 轮询线程 ----------
    def _poll_loop(self):
        self._ui_ready.wait(timeout=20)
        log.info("poll loop started")
        while not self._stop.is_set():
            try:
                # 桌面右键菜单「喂鱼」信号：检测到就投喂一次
                feed_flag = os.path.join(cfgmod.APP_DIR, ".feed_request")
                if os.path.exists(feed_flag):
                    try:
                        os.remove(feed_flag)
                    except Exception:
                        pass
                    self.feed()

                # 电源
                bat = desktop.is_on_battery()
                if bat != self._last_battery:
                    self._last_battery = bat
                    log.info("power: %s", "battery" if bat else "AC")

                # 页面状态轮询（ready / 错误）
                for v in self.views:
                    st = v.poll_state()
                    if st:
                        if st.get("ready") and v.screen_index not in self._ready_handled:
                            self._ready_handled.add(v.screen_index)
                            log.info("view %d ready", v.screen_index)
                            self._apply_state()
                            self._attach_view(v)
                            if v.screen_index == 0 and self.tray:
                                self.tray.notify(
                                    "桌面世界已启动 🐟",
                                    "按 Win+D 看桌面。点右下角托盘图标可投喂/切换世界/暂停。")
                        for err in (st.get("errors") or []):
                            key = (v.screen_index, err)
                            if key not in self._reported_errors:
                                self._reported_errors.add(key)
                                log.warning("page[%d]: %s", v.screen_index, str(err)[:300])

                # 遮挡检测（主屏）——每秒一次即可，避免每 30ms 全窗口枚举拖慢系统
                covered = False
                now = time.time()
                if now - getattr(self, "_last_cover_check", 0) >= 1.0:
                    self._last_cover_check = now
                    if self.screens and not self.config["paused"]:
                        sl, stt, sw, sh = self.screens[0]
                        covered = desktop.window_covers_screen((sl, stt, sl + sw, stt + sh))
                    if covered != self._last_covered:
                        self._last_covered = covered
                        self._apply_state()
                        log.info("coverage: %s", "covered -> 20fps" if covered else "visible -> full fps")

                # 虚拟光标（仅在动画运行时）
                if self._current_rate > 0:
                    pos = desktop.get_cursor_pos()
                    if pos != self._last_cursor:
                        self._last_cursor = pos
                        self._dispatch_pointer(pos)
            except Exception as e:
                self._poll_err_count = getattr(self, "_poll_err_count", 0) + 1
                if self._poll_err_count <= 3:
                    log.warning("poll error: %s", e)
            self._stop.wait(1.0 / 30.0)

    def _dispatch_pointer(self, pos):
        if not pos or not self.screens:
            return
        x, y = pos
        for idx, (sx, sy, sw, sh) in enumerate(self.screens):
            if sx <= x < sx + sw and sy <= y < sy + sh:
                if idx < len(self.views) and self.views[idx].ready:
                    self.views[idx].pointer(x - sx, y - sy)
                return
        for v in self.views:
            v.pointer_out()

    # ---------- 托盘动作 ----------
    def select_world(self, wid):
        self.config["world"] = wid
        cfgmod.save(self.config)
        log.info("select world: %s", wid)
        self._ready_handled.clear()
        for v in self.views:
            v.ready = False
            v.load_world(wid, quality=self.config["quality"],
                         holiday=self.config["holidayLights"], still=self.config["paused"])
        self._apply_state()
        self._refresh_tray()
        if self.tray:
            cw = cfgmod.world_by_id(wid)
            self.tray.notify("桌面世界", "已切换到：%s" % (cw.get("name_cn") or cw["name"]))

    def feed(self):
        w = cfgmod.world_by_id(self.config["world"])
        action = w["action"]
        for v in self.views:
            if action == "lights":
                self.config["holidayLights"] = not self.config["holidayLights"]
                cfgmod.save(self.config)
                v.feed("true" if self.config["holidayLights"] else "false")
            elif action != "none":
                v.feed()
        self._refresh_tray()
        # 视觉反馈：鱼食很小、彩灯切换也不显眼，给用户明确提示动作已触发
        if self.tray:
            if action == "lights":
                msg = "节日彩灯已%s" % ("打开" if self.config["holidayLights"] else "关闭")
            elif action == "stir":
                msg = "已搅动篝火 🔥"
            elif action == "none":
                msg = "这个世界没有可投喂的生物"
            else:
                msg = "已投喂食物 🐟 鱼会游过来吃"
            self.tray.notify("桌面世界", msg)

    def toggle_pause(self):
        self.config["paused"] = not self.config["paused"]
        cfgmod.save(self.config)
        self._apply_state()
        self._refresh_tray()

    def wallpaper_hidden(self):
        return getattr(self, "_wall_hidden", False)

    def toggle_visibility(self):
        """在"看壁纸"和"看桌面图标"之间切换（WebView2 无法两者同时显示）。"""
        new_hidden = not self.wallpaper_hidden()
        self._wall_hidden = new_hidden
        for v in self.views:
            try:
                desktop.set_wallpaper_visible(v.hwnd, not new_hidden)
            except Exception as e:
                log.warning("toggle visibility failed: %s", e)
        self._refresh_tray()
        if self.tray:
            self.tray.notify("桌面世界",
                             "壁纸已隐藏，桌面图标可见" if new_hidden else "壁纸已恢复显示 🐟")

    def reload(self):
        self._ready_handled.clear()
        for v in self.views:
            v.ready = False
            v.load_world(self.config["world"], quality=self.config["quality"],
                         holiday=self.config["holidayLights"], still=self.config["paused"])
        self._apply_state()

    def _refresh_tray(self):
        if self.tray:
            threading.Thread(target=self.tray.update, daemon=True).start()

    def quit(self):
        """从托盘菜单回调退出。

        ★ 关键：本方法运行在 pystray 托盘线程里。若直接调用 tray.stop()
        （内部 icon.stop() 会 join 托盘线程），等于线程等自己结束 → 死锁，
        表现就是"点退出没反应"。因此把所有清理放到独立线程，主回调立即返回，
        最后用 os._exit 强制结束进程。
        """
        log.info("quit")
        self._stop.set()

        def _shutdown():
            # 给托盘回调一点时间先返回，再停图标，避免 self-join 死锁
            time.sleep(0.3)
            if self.tray:
                try:
                    self.tray.stop()
                except Exception:
                    pass
            try:
                WinForms.Application.ExitThread()
            except Exception:
                pass
            time.sleep(0.2)
            os._exit(0)

        threading.Thread(target=_shutdown, daemon=True).start()

    def run(self):
        # 动态读取 pythonnet 需要的 System.Action（在 UI 模块加载后）
        global System
        if "System" not in globals():
            import System as _System
            System = _System
        t = Thread(ThreadStart(self._ui_main))
        t.SetApartmentState(ApartmentState.STA)
        t.Start()
        threading.Thread(target=self._poll_loop, daemon=True).start()
        self.tray = Tray(self)
        self.tray.run()


def _minimize_console():
    """把本进程的控制台窗口最小化，避免黑窗口挡住桌面壁纸（控制台子系统保留，WebView2 才稳定）。"""
    try:
        import ctypes
        SW_MINIMIZE = 6
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
    except Exception:
        pass


def main():
    if not singleton.acquire():
        log.warning("已有 Deskworlds 实例在运行，本次启动退出。")
        print("Deskworlds is already running. Check the system tray.")
        sys.exit(0)
    # 注册桌面右键菜单「喂鱼」（用户级注册表，失败不影响主功能）
    try:
        import shellmenu
        if shellmenu.register():
            log.info("desktop context menu registered")
    except Exception as e:
        log.debug("register context menu failed: %s", e)
    # 延迟一点再最小化，让用户先看到启动提示（若从 run.bat 直接启动）
    threading.Thread(target=lambda: (time.sleep(2), _minimize_console()), daemon=True).start()
    try:
        App().run()
    finally:
        singleton.release()


if __name__ == "__main__":
    main()
