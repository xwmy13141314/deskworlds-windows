"""批量截取 7 个世界的展示图（用 WebView2 CapturePreviewAsync，纯净场景，不受遮挡影响）。

用法（在 deskworlds-win 目录下）：
    python tools/capture_screenshots.py
输出：docs/images/worlds/<世界id>.png（1280x800）
"""
import os, sys, time, traceback, ctypes
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
HOST_DIR = os.path.join(PROJECT, "host")


def _resolve_scene_root():
    for p in (os.path.join(PROJECT, "..", "deskworlds"), os.path.join(PROJECT, "deskworlds")):
        if os.path.exists(os.path.join(p, "scenes")):
            return os.path.normpath(p).replace("\\", "/")
    return os.path.normpath(os.path.join(PROJECT, "..", "deskworlds")).replace("\\", "/")


SCENE_ROOT = _resolve_scene_root()
OUT_DIR = os.path.join(PROJECT, "docs", "images", "worlds")
os.makedirs(OUT_DIR, exist_ok=True)
sys.path.insert(0, HOST_DIR)   # 让 bridge / config 可导入
os.chdir(HOST_DIR)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")
import System
import System.Windows.Forms as WinForms
from System.Threading import Thread, ThreadStart, ApartmentState
from System.IO import MemoryStream
from System.Threading.Tasks import Task
from PIL import Image

import bridge  # 先导入 bridge（它会加载 WebView2 程序集）
import config as cfgmod

from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat

SETTLE_SECONDS = 5.0
OUT_W, OUT_H = 1280, 800

state = {"view": None}

def ui_main():
    try:
        s = WinForms.Screen.PrimaryScreen.Bounds
        v = bridge.WallpaperView(None, 0, (s.X, s.Y, s.Width, s.Height),
                                 SCENE_ROOT, lambda v: None, lambda v, d: None)
        state["view"] = v
        v.show()
        v.ensure()
        v.load_world("riverscape", quality="detail")
        WinForms.Application.Run()
    except Exception:
        print(traceback.format_exc(), flush=True)

t = Thread(ThreadStart(ui_main))
t.SetApartmentState(ApartmentState.STA)
t.Start()

deadline = time.time() + 40
while time.time() < deadline and state["view"] is None:
    time.sleep(0.3)
while time.time() < deadline:
    v = state["view"]
    st = v.poll_state() if v else None
    if st and st.get("ready"):
        break
    time.sleep(0.4)
v = state["view"]
print("initial ready:", bool(v and v.poll_state() and v.poll_state().get("ready")))


def capture_png(path):
    """在 UI 线程发起 CapturePreviewAsync，主线程等回调写文件。"""
    from threading import Event
    ev = Event()
    res = {"ok": False, "err": None}

    def run():
        try:
            core = v.webview.CoreWebView2
            ms = MemoryStream()

            def cb(task):
                try:
                    if task.IsFaulted:
                        res["err"] = "faulted: %s" % (task.Exception,)
                    else:
                        data = ms.ToArray()
                        with open(path, "wb") as f:
                            f.write(bytes(data))
                        res["ok"] = True
                except Exception as e:
                    res["err"] = repr(e)
                finally:
                    ev.set()

            core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, ms) \
                .ContinueWith(System.Action[Task](cb))
        except Exception as e:
            res["err"] = repr(e)
            ev.set()

    v.form.Invoke(System.Action(run))
    ev.wait(timeout=25)
    return res


ok_count = 0
for w in cfgmod.WORLDS:
    wid = w["id"]
    print("=== capturing", wid, "===", flush=True)
    v.ready = False
    v._pending.clear()
    v.load_world(wid, quality="detail")
    dl = time.time() + 45
    while time.time() < dl:
        st = v.poll_state()
        if st and st.get("ready"):
            break
        time.sleep(0.4)
    time.sleep(SETTLE_SECONDS)
    raw_path = os.path.join(OUT_DIR, wid + "_raw.png")
    r = capture_png(raw_path)
    if r["ok"]:
        # 缩放到统一尺寸，控制体积
        img = Image.open(raw_path)
        img = img.convert("RGB")
        img = img.resize((OUT_W, OUT_H), Image.LANCZOS)
        final = os.path.join(OUT_DIR, wid + ".png")
        img.save(final, optimize=True)
        try:
            os.remove(raw_path)
        except Exception:
            pass
        print("  saved:", final, img.size, flush=True)
        ok_count += 1
    else:
        print("  FAILED:", r["err"], flush=True)

print("DONE, captured %d/7" % ok_count, flush=True)
try:
    WinForms.Application.ExitThread()
except Exception:
    pass
os._exit(0)
