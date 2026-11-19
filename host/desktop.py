"""
Win32 桌面层操作。

重要结论（实测）：WebView2 **不能** SetParent 到 Progman/WorkerW——
那样它的 D3D 内容不会合成，窗口存在、页面在跑，但屏幕上是静态壁纸/纯黑。
正确方案：保持壁纸窗口为普通顶层窗口，用 HWND_BOTTOM 置到 Z 序最底 + 鼠标穿透。
这样它位于所有应用窗口之下、桌面图标之上，画面正常显示，点击穿透给桌面。
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
HWND_BOTTOM = 1
HWND_NOTOPMOST = -2


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_byte),
        ("BatteryFlag", ctypes.c_byte),
        ("BatteryLifePercent", ctypes.c_byte),
        ("Reserved1", ctypes.c_byte),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


ULONG_PTR = ctypes.c_size_t
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowLongW.restype = wintypes.LONG
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
kernel32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(SYSTEM_POWER_STATUS)]
kernel32.GetSystemPowerStatus.restype = wintypes.BOOL
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
ULONG_PTR = ctypes.c_size_t
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                       ctypes.POINTER(ULONG_PTR)]
user32.SendMessageTimeoutW.restype = wintypes.LPARAM
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetParent.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL


def _get_wallpaper_workerw():
    """
    找到"壁纸层" WorkerW（位于桌面图标层之下、静态壁纸之上）。

    ★ 关键：向 Progman 发 0x052C 时必须用 wParam=0xD, lParam=0x1，
      才会在 Windows 11 上分离出两个 WorkerW（图标层 + 壁纸层）。
      用 (0,0) 参数无效——这是之前一直找不到 WorkerW、SetParent 到 Progman 后
      画面变黑的根因。
    返回 (progman, defview_parent_workerw, wallpaper_workerw)。
    """
    progman = user32.FindWindowW("Progman", None)
    if not progman:
        return None, None, None
    # 分离 WorkerW（0xD/0x1 为 Win11 有效参数）
    user32.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, None)

    found = {"defview_parent": None, "wallpaper": None}

    @WNDENUMPROC
    def enum_proc(hwnd, lparam):
        defview = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
        if defview:
            found["defview_parent"] = hwnd
            # 图标层 WorkerW 之后的那个 WorkerW 就是壁纸层
            found["wallpaper"] = user32.FindWindowExW(None, hwnd, "WorkerW", None)
        return True

    user32.EnumWindows(enum_proc, 0)
    return progman, found["defview_parent"], found["wallpaper"]


def attach_to_desktop(hwnd):
    """
    把壁纸窗口挂到桌面壁纸层（WorkerW），使其位于桌面图标之下、静态壁纸之上。
    这样场景正常渲染，桌面图标也正常显示在场景之上（与 Mac 原版一致）。
    """
    hwnd = int(hwnd)
    progman, defview_parent, workerw = _get_wallpaper_workerw()

    # 扩展样式：鼠标穿透 + 工具窗口 + 不激活。绝不加 WS_EX_LAYERED（会让 WebView2 变黑）。
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ex &= ~WS_EX_LAYERED
    ex |= WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)

    if workerw:
        # 加 WS_CHILD 再 SetParent 到壁纸层 WorkerW
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_CHILD)
        user32.SetParent(hwnd, workerw)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        return True

    # 回退：找不到 WorkerW 时，作为置底顶层窗口（图标会被盖）
    user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    return False


def set_wallpaper_visible(hwnd, visible):
    """显示/隐藏壁纸窗口（作为极端情况的备用）。"""
    hwnd = int(hwnd)
    user32.ShowWindow(hwnd, 5 if visible else 0)


def set_bottom_fallback(hwnd):
    """与 attach_to_desktop 现在等价（保留接口兼容）。"""
    return attach_to_desktop(hwnd)


def make_clickthrough(hwnd, enabled=True):
    """动态开关鼠标穿透。"""
    hwnd = int(hwnd)
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if enabled:
        ex |= WS_EX_TRANSPARENT
    else:
        ex &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)


def get_cursor_pos():
    p = POINT()
    if user32.GetCursorPos(ctypes.byref(p)):
        return p.x, p.y
    return None


def is_on_battery():
    s = SYSTEM_POWER_STATUS()
    if kernel32.GetSystemPowerStatus(ctypes.byref(s)):
        return s.ACLineStatus == 0
    return False


def foreground_window():
    return user32.GetForegroundWindow()


def window_covers_screen(screen_rect):
    """粗粒度遮挡检测：16x10 网格采样，桌面可见面积 <15% 视为被遮挡。"""
    sl, st, sr, sb = screen_rect
    sw, sh = sr - sl, sb - st
    if sw <= 0 or sh <= 0:
        return False
    me = kernel32.GetCurrentProcessId()
    blockers = []

    @WNDENUMPROC
    def enum_proc(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == me:
            return True
        r = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        if r.right <= r.left or r.bottom <= r.top:
            return True
        blockers.append((r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumWindows(enum_proc, 0)
    if not blockers:
        return False
    cols, rows = 16, 10
    free = 0
    for c in range(cols):
        for rw in range(rows):
            px = sl + sw * (c + 0.5) / cols
            py = st + sh * (rw + 0.5) / rows
            covered = any(l <= px < rr and t <= py < b for (l, t, rr, b) in blockers)
            if not covered:
                free += 1
    return free / float(cols * rows) < 0.15


def find_window_by_title_contains(substr):
    result = []
    buf = ctypes.create_unicode_buffer(512)

    @WNDENUMPROC
    def enum_proc(hwnd, lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            user32.GetWindowTextW(hwnd, buf, 512)
            if substr.lower() in buf.value.lower():
                result.append((hwnd, buf.value))
        return True

    user32.EnumWindows(enum_proc, 0)
    return result
