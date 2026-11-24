"""桌面右键菜单：注册/注销「喂鱼」菜单项（用户级注册表，无需管理员）。

原理：写入 HKCU\\Software\\Classes\\DesktopBackground\\Shell\\DeskworldsFeed，
点击时执行 `<exe> --feed`，主程序据此写信号文件并投喂。

注意：Windows 11 的简化右键菜单会把传统 shell 项收进「显示更多选项」。
"""
import os
import sys
import winreg

MENU_KEY = r"Software\Classes\DesktopBackground\Shell\DeskworldsFeed"
MENU_LABEL = "喂鱼 🐟（桌面世界）"
QUIT_KEY = r"Software\Classes\DesktopBackground\Shell\DeskworldsQuit"
QUIT_LABEL = "退出壁纸 ❌（桌面世界）"


def _exe_command(flag="--feed"):
    """返回用于右键菜单的命令行。"""
    if getattr(sys, "frozen", False):
        return '"%s" %s' % (sys.executable, flag)
    py = sys.executable
    main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return '"%s" "%s" %s' % (py, main_py, flag)


def _icon_path():
    if getattr(sys, "frozen", False):
        return sys.executable
    # 开发模式用 python 图标（或留空）
    return ""


def register():
    """注册桌面右键菜单项（喂鱼 + 退出）。已存在则覆盖。"""
    icon = _icon_path()
    try:
        # 喂鱼项
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, MENU_KEY) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, MENU_LABEL)
            if icon:
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
            winreg.SetValueEx(k, "Position", 0, winreg.REG_SZ, "Bottom")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, MENU_KEY + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, _exe_command("--feed"))

        # 退出项
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, QUIT_KEY) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, QUIT_LABEL)
            if icon:
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
            winreg.SetValueEx(k, "Position", 0, winreg.REG_SZ, "Bottom")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, QUIT_KEY + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, _exe_command("--quit"))
        return True
    except Exception:
        return False


def unregister():
    """删除桌面右键菜单项（喂鱼 + 退出）。"""
    try:
        _delete_tree(winreg.HKEY_CURRENT_USER, MENU_KEY)
        _delete_tree(winreg.HKEY_CURRENT_USER, QUIT_KEY)
        return True
    except Exception:
        return False


def _delete_tree(root, path):
    """递归删除注册表键。"""
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root, path + "\\" + sub)
    except FileNotFoundError:
        return
    try:
        winreg.DeleteKey(root, path)
    except Exception:
        pass


def is_registered():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_KEY + r"\command") as k:
            winreg.QueryValueEx(k, "")
        return True
    except FileNotFoundError:
        return False
