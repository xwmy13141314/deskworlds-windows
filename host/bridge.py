"""
WebView2 桥接：每个屏幕一个无边框窗口 + WebView2，加载原项目未改动的 wallpaper.html。
通过"文档创建时注入脚本"把 Mac WKWebView 的协议映射到 WebView2，
并把宿主状态（帧率/电源/投喂/虚拟光标）以 scene* 调用发给页面。

对应 Mac 版：
  - SceneHandler (deskworlds://local)  -> WebView2 虚拟主机名映射
  - WKUserScript scenePointer          -> AddScriptToExecuteOnDocumentCreatedAsync
  - ready message                      -> window.chrome.webview.postMessage
  - evaluateJavaScript("sceneRate...") -> ExecuteScriptAsync
"""
import os
import json
import logging

import clr
import webview.util as wutil

clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")
import System
import System.Windows.Forms as WinForms
from System.Drawing import Size, Point

clr.AddReference(wutil.interop_dll_path("Microsoft.Web.WebView2.Core.dll"))
clr.AddReference(wutil.interop_dll_path("Microsoft.Web.WebView2.WinForms.dll"))
for _p in ("win-x64", "win-x86", "win-arm64"):
    os.environ["PATH"] = wutil.interop_dll_path(_p) + os.pathsep + os.environ["PATH"]

from Microsoft.Web.WebView2.WinForms import WebView2, CoreWebView2CreationProperties
from Microsoft.Web.WebView2.Core import CoreWebView2HostResourceAccessKind

log = logging.getLogger("dw.bridge")

VIRTUAL_HOST = "deskworlds.local"
# 注入到每个文档最前面的兼容层：把 Mac 协议映射到 WebView2，并提供虚拟光标函数。
# 这样原场景的 start.js / main.js 一行都不用改。
BOOTSTRAP_JS = r"""
(() => {
  // 页面错误收集到数组，宿主用 evalSync 主动拉取（该环境 postMessage 通道不可用）。
  window.__dwErrors = [];
  window.__dwReadyFlag = false;
  const record = (text) => { try { window.__dwErrors.push(String(text)); } catch(e) {} };
  // --- 让原页面的 window.webkit.messageHandlers.ready / report 可用 ---
  if (!window.webkit) window.webkit = {};
  window.webkit.messageHandlers = {
    ready: { postMessage: () => { window.__dwReadyFlag = true; } },
    report: { postMessage: (v) => record(v) },
  };
  // --- 收集页面 error/warn（等价 Mac 的 Reporter） ---
  for (const level of ['error', 'warn']) {
    const orig = console[level];
    console[level] = (...parts) => {
      record(parts.map(p => (p && p.stack) ? p.stack : String(p)).join(' '));
      orig.apply(console, parts);
    };
  }
  addEventListener('error', e => record(e.message + ' at ' + e.filename + ':' + e.lineno));
  addEventListener('unhandledrejection', e => record(String(e.reason)));

  // --- 宿主注入的虚拟光标（等价 Mac WKUserScript 的 scenePointer） ---
  window.scenePointerCount = 0;
  window.scenePointer = (x, y) => {
    const canvas = document.querySelector('#scene');
    window.scenePointerCount++;
    if (canvas) canvas.dispatchEvent(new PointerEvent('pointermove', { clientX: x, clientY: y, bubbles: true }));
  };
  window.scenePointerOut = () => {
    const canvas = document.querySelector('#scene');
    if (canvas) canvas.dispatchEvent(new PointerEvent('pointerleave', { bubbles: true }));
  };
  // ready 标志：场景装好 sceneRate 后置位，宿主轮询读取。
  const probe = () => {
    if (typeof window.sceneRate === 'function' || window.__dwReadyFlag) window.__dwReady = true;
    else setTimeout(probe, 100);
  };
  probe();
})();
"""


class WallpaperView:
    """单个屏幕的壁纸视图：持有一个 WinForms Form + WebView2。"""

    def __init__(self, app, screen_index, bounds, scene_root, on_ready, on_message):
        self.app = app
        self.screen_index = screen_index
        self.bounds = bounds  # (x, y, w, h) 物理像素，由 WinForms Screen 提供
        self.scene_root = scene_root
        self.on_ready = on_ready
        self.on_message = on_message
        self.form = None
        self.webview = None
        self.hwnd = None
        self.ready = False
        self._initialized = False  # CoreWebView2 是否就绪（UI 线程写，其它线程只读）
        self._pending = []       # 页面尚未就绪时缓存的 JS 状态脚本
        self._desired_url = None  # 期望加载的页面（CoreWebView2 就绪后导航）
        self._build()

    def _build(self):
        x, y, w, h = self.bounds
        form = WinForms.Form()
        form.Text = "Deskworlds"
        form.StartPosition = WinForms.FormStartPosition.Manual
        form.Location = Point(x, y)
        form.Size = Size(w, h)
        form.FormBorderStyle = getattr(WinForms.FormBorderStyle, "None")
        form.ShowInTaskbar = False
        form.ControlBox = False
        form.BackColor = System.Drawing.Color.Black

        wv = WebView2()
        wv.Dock = WinForms.DockStyle.Fill
        form.Controls.Add(wv)

        self.form = form
        self.webview = wv

        def on_init(sender, args):
            if not args.IsSuccess:
                log.error("WebView2 init failed: %s", args.InitializationException)
                return
            core = sender.CoreWebView2
            core.Settings.IsWebMessageEnabled = True
            core.Settings.AreDefaultContextMenusEnabled = False
            core.Settings.AreBrowserAcceleratorKeysEnabled = False
            core.Settings.IsZoomControlEnabled = False
            core.Settings.UserAgent = core.Settings.UserAgent + " DeskworldsWin/1.0"
            core.SetVirtualHostNameToFolderMapping(
                VIRTUAL_HOST, self.scene_root, CoreWebView2HostResourceAccessKind.Allow)
            core.AddScriptToExecuteOnDocumentCreatedAsync(BOOTSTRAP_JS)
            self._initialized = True
            # CoreWebView2 就绪后，导航到期望页面
            if self._desired_url:
                log.info("navigate to deferred url: %s", self._desired_url)
                core.Navigate(self._desired_url)
                self._desired_url = None

        def on_nav_complete(sender, args):
            try:
                log.info("nav complete: %s isSuccess=%s http=%s",
                         str(sender.Source), args.get_IsSuccess(), args.get_HttpStatusCode())
            except Exception as e:
                log.info("nav complete: %s (status read err %s)", str(sender.Source), e)
            # 诊断通过 verify.py 的 eval_sync 完成，这里只记录导航状态

        def on_nav_error(sender, args):
            try:
                log.error("nav error: %s -> %s", str(args.get_Uri()), args.get_WebView2().StatusText if args.get_WebView2() else "?")
            except Exception:
                log.error("nav error occurred")

        wv.NavigationCompleted += on_nav_complete
        wv.NavigationStarting += lambda s, a: log.info("nav starting: %s", str(a.get_Uri()))

        def on_msg(sender, args):
            raw = str(args.get_WebMessageAsJson())
            try:
                data = json.loads(raw)
            except Exception:
                data = {"type": "raw", "value": raw}
            # 消息回调在 UI 线程，直接分发
            if data.get("type") == "ready":
                self.ready = True
                self.on_ready(self)
                # 回放就绪前缓存的状态脚本
                pending = list(self._pending)
                self._pending.clear()
                for script in pending:
                    try:
                        self.webview.ExecuteScriptAsync(script)
                    except Exception:
                        pass
            self.on_message(self, data)

        wv.CoreWebView2InitializationCompleted += on_init
        wv.WebMessageReceived += on_msg

        props = CoreWebView2CreationProperties()
        props.UserDataFolder = os.path.join(
            os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", ".")),
            "Deskworlds", "webview_profile_s%d" % screen_index_safe(self.screen_index))
        props.set_IsInPrivateModeEnabled(True)
        wv.CreationProperties = props

    def show(self):
        self.form.Show()
        # 窗口显示后原生句柄即已创建，无需等 WebView2 初始化
        self.hwnd = int(self.form.Handle.ToInt64())

    def ensure(self):
        self.webview.EnsureCoreWebView2Async(None)

    def _run_on_ui(self, fn):
        """在 UI 线程执行 fn（若当前已在 UI 线程则直接执行）。"""
        try:
            if self.form.InvokeRequired:
                self.form.Invoke(System.Action(fn))
            else:
                fn()
        except Exception as e:
            log.debug("run_on_ui: %s", e)

    def eval_sync(self, script):
        """在 UI 线程同步执行 JS 并返回字符串结果。"""
        from threading import Event
        if not self._initialized:
            return None
        out = {"v": None}
        ev = Event()

        def cb(task):
            try:
                out["v"] = task.Result
            except Exception as e:
                out["v"] = "ERR:" + repr(e)
            ev.set()

        def run():
            try:
                from System import Action, String
                from System.Threading.Tasks import Task
                core = self.webview.CoreWebView2
                task = core.ExecuteScriptAsync(script)
                task.ContinueWith(Action[Task[String]](lambda t: cb(t)))
            except Exception as e:
                out["v"] = "ERR:" + repr(e)
                ev.set()

        try:
            self.form.Invoke(System.Action(run))
        except Exception:
            return None
        ev.wait(timeout=2.5)
        return out["v"]

    def _exec(self, script):
        """在 UI 线程执行 JS；未就绪时缓存。"""
        if not self.ready or not self._initialized:
            if script not in self._pending:
                self._pending.append(script)
            return
        self._run_on_ui(lambda: self.webview.ExecuteScriptAsync(script))

    # ---- 宿主 -> 页面 接口（对齐原项目的 window.scene* 契约） ----
    def load_world(self, world_id, quality="native", holiday=False, still=False):
        url = "https://%s/scenes/%s/wallpaper.html?quality=%s" % (
            VIRTUAL_HOST, world_id, quality)
        if holiday:
            url += "&holiday=1"
        if still:
            url += "&still=1"
        self.ready = False
        self._pending.clear()
        if self._initialized:
            self._run_on_ui(lambda: self.webview.CoreWebView2.Navigate(url))
        else:
            self._desired_url = url

    def set_rate(self, fps):
        self._exec("typeof sceneRate==='function'&&sceneRate(%d);" % int(fps))

    def set_power(self, on_battery):
        self._exec("typeof scenePower==='function'&&scenePower(%s);" % (
            "true" if on_battery else "false"))

    def set_paused(self, paused):
        self._exec("typeof scenePause==='function'&&scenePause(%s);" % (
            "true" if paused else "false"))

    def feed(self, setting=""):
        if setting:
            self._exec("typeof sceneFeed==='function'&&sceneFeed(%s);" % json.dumps(setting))
        else:
            self._exec("typeof sceneFeed==='function'&&sceneFeed();")

    def pointer(self, x, y):
        self._exec("typeof scenePointer==='function'&&scenePointer(%.1f,%.1f);" % (x, y))

    def pointer_out(self):
        self._exec("typeof scenePointerOut==='function'&&scenePointerOut();")

    def mark_ready(self):
        """页面就绪后调用：设置 ready 标志并回放缓存的状态脚本。"""
        if self.ready:
            return
        self.ready = True
        pending = list(self._pending)
        self._pending.clear()
        for script in pending:
            self._run_on_ui(lambda s=script: self.webview.ExecuteScriptAsync(s))

    def poll_state(self):
        """主动轮询页面状态：ready / 首帧 / 错误。"""
        if not self._initialized:
            return None
        js = ("JSON.stringify({ready:!!window.__dwReady,"
              "stats:(typeof sceneStats==='function'?sceneStats():null),"
              "errors:window.__dwErrors||[]})")
        raw = self.eval_sync(js)
        state = self._parse_json_result(raw)
        if raw is None:
            log.debug("view %d eval_sync timeout (busy)", self.screen_index)
        if state and state.get("ready") and not self.ready:
            self.mark_ready()
        return state

    def drain_errors(self):
        """取走并清空页面错误数组。"""
        if not self._initialized:
            return []
        raw = self.eval_sync("(()=>{const e=JSON.stringify(window.__dwErrors||[]);window.__dwErrors=[];return e})()")
        result = self._parse_json_result(raw)
        return result if isinstance(result, list) else []

    def _parse_json_result(self, raw):
        if not raw:
            return None
        try:
            # ExecuteScriptAsync 返回的是 JSON 编码的字符串，可能多包一层引号
            if isinstance(raw, str) and raw.startswith('"'):
                raw = json.loads(raw)
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return None

    def stats(self):
        self._exec("typeof sceneStats==='function'?JSON.stringify(sceneStats()):'{}'")


def screen_index_safe(i):
    try:
        return int(i)
    except Exception:
        return 0
