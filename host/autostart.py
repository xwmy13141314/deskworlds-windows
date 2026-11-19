"""开机自启管理：写/删 HKCU Run 项，用 pythonw 无控制台启动。"""
import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Deskworlds"


def _command():
    here = os.path.dirname(os.path.abspath(__file__))
    project = os.path.dirname(here)
    main_py = os.path.join(here, "main.py")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    return '"%s" "%s"' % (pythonw, main_py)


def enable():
    import winreg
    cmd = _command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
    return cmd


def disable():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
    except FileNotFoundError:
        pass


def is_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except FileNotFoundError:
        return False


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "enable"
    if action == "enable":
        print("Autostart enabled:", enable())
    elif action == "disable":
        disable()
        print("Autostart disabled")
    elif action == "status":
        print("Autostart:", "enabled" if is_enabled() else "disabled")
