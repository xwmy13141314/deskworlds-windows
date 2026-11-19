"""单实例锁：用 PID 文件防止重复启动多个壁纸实例（比命名互斥体可靠）。

锁文件存到 %APPDATA%/Deskworlds/instance.lock，内容为当前进程 PID。
启动时若发现锁文件里的 PID 仍存活，则判定已有实例，拒绝启动。
"""
import os
import ctypes

LOCK_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Deskworlds")
LOCK_FILE = os.path.join(LOCK_DIR, "instance.lock")
_owned = False


def _process_alive(pid):
    """检查 PID 对应进程是否存活（Windows）。"""
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        exit_code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(h)
        # STILL_ACTIVE = 259
        return bool(ok) and exit_code.value == 259
    except Exception:
        return False


def acquire():
    """成功返回 True；若已有一个实例在运行返回 False。"""
    global _owned
    try:
        os.makedirs(LOCK_DIR, exist_ok=True)
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE, "r", encoding="utf-8") as f:
                old_pid = int((f.read() or "0").strip())
            if old_pid and old_pid != os.getpid() and _process_alive(old_pid):
                return False
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        _owned = True
        return True
    except Exception:
        return True


def release():
    global _owned
    if _owned:
        try:
            with open(LOCK_FILE, "r", encoding="utf-8") as f:
                pid = int((f.read() or "0").strip())
            if pid == os.getpid():
                os.remove(LOCK_FILE)
        except Exception:
            pass
        _owned = False
