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


def _exe_command():
    """返回用于右键菜单的命令行（含 --feed）。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后：直接用 exe 自身
        return '"%s" --feed' % sys.executable
    # 开发模式：python + main.py
    py = sys.executable
    main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return '"%s" "%s" --feed' % (py, main_py)


def _icon_path():
    if getattr(sys, "frozen", False):
        return sys.executable
    # 开发模式用 python 图标（或留空）
    return ""


def register():
    """注册桌面右键菜单项。已存在则覆盖。"""
    cmd = _exe_command()
    icon = _icon_path()
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, MENU_KEY) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, MENU_LABEL)
            if icon:
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
            # 让菜单项在 Win11 也尽量显示（不加 Extended 表示常规显示）
            winreg.SetValueEx(k, "Position", 0, winreg.REG_SZ, "Bottom")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, MENU_KEY + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
        return True
    except Exception:
        return False


def unregister():
    """删除桌面右键菜单项。"""
    try:
        _delete_tree(winreg.HKEY_CURRENT_USER, MENU_KEY)
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
