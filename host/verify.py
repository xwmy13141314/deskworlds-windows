"""端到端验证：启动壁纸视图，加载原场景，轮询 ready，截图并统计渲染状态。"""
import os, sys, time, traceback, base64
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)


def _resolve_scene_root():
    for p in (os.path.join(PROJECT, "..", "deskworlds"), os.path.join(PROJECT, "deskworlds")):
        if os.path.exists(os.path.join(p, "scenes")):
            return os.path.normpath(p).replace("\\", "/")
    return os.path.normpath(os.path.join(PROJECT, "..", "deskworlds")).replace("\\", "/")


SCENE_ROOT = _resolve_scene_root()
os.chdir(HERE)

try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")
import System
import System.Windows.Forms as WinForms
from System.Threading import Thread, ThreadStart, ApartmentState

import bridge, desktop

state = {"view": None}
SHOT = os.path.join(HERE, "verify_screenshot.png")


def save_snapshot(view, path):
    """用 WebView2 CapturePreviewAsync 截到内存流，再存 PNG（UI 线程同步等待）。"""
    try:
        from System.IO import MemoryStream
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
        core = view.webview.CoreWebView2
        ms = MemoryStream()
        task = core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, ms)
        task.GetAwaiter().GetResult()  # 同步等待截图完成
        with open(path, "wb") as f:
            f.write(bytes(ms.ToArray()))
        print("[verify] snapshot saved", flush=True)
    except Exception as e:
        print("[verify] snapshot err:", repr(e), flush=True)


def on_ready(view):
    print("[verify] on_ready callback", flush=True)


def on_msg(view, data):
    print("[verify] msg:", data, flush=True)


def ui_main():
    try:
        s = WinForms.Screen.PrimaryScreen.Bounds
        bounds = (s.X, s.Y, s.Width, s.Height)
        view = bridge.WallpaperView(None, 0, bounds, SCENE_ROOT, on_ready, on_msg)
        state["view"] = view
        view.show()
        print("[verify] shown hwnd:", view.hwnd, flush=True)
        view.ensure()
        view.load_world("riverscape", quality="balanced")
        WinForms.Application.Run()
    except Exception:
        print("[verify] UI error:\n", traceback.format_exc(), flush=True)


t = Thread(ThreadStart(ui_main)); t.SetApartmentState(ApartmentState.STA); t.Start()

# 轮询 ready
ready = False
deadline = time.time() + 40
last_log = 0
while time.time() < deadline and not ready:
    time.sleep(0.5)
    v = state["view"]
    if v is None:
        continue
    st = v.poll_state()
    if st and st.get("ready"):
        ready = True
        print("[verify] READY via poll. stats:", st.get("stats"), flush=True)
    if time.time() - last_log > 5:
        last_log = time.time()
        print("[verify] waiting... state:", st, flush=True)

print("[verify] ready:", ready, flush=True)
v = state.get("view")
if v:
    errs = v.drain_errors()
    print("[verify] page errors:", errs[:8], flush=True)
    # 启动动画（壁纸模式默认 fps=0）
    v.set_rate(60)
    # 挂到桌面层
    try:
        attached = desktop.attach_to_desktop(v.hwnd)
        print("[verify] attached:", attached, flush=True)
    except Exception as e:
        print("[verify] attach err:", repr(e), flush=True)
    time.sleep(4)
    st = v.poll_state()
    print("[verify] final stats:", st.get("stats") if st else None, flush=True)
    # 从主进程抓屏（壁纸窗口此时在桌面层可见）
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(SHOT)
        print("[verify] screen captured:", img.size, flush=True)
    except Exception as e:
        print("[verify] grab err:", repr(e), flush=True)

print("[verify] screenshot exists:", os.path.exists(SHOT), flush=True)
try: WinForms.Application.ExitThread()
except Exception: pass
os._exit(0)
