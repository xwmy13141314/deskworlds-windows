# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：Deskworlds for Windows 免安装版。

用法（在 deskworlds-win 目录下）：
    python -m PyInstaller --noconfirm --clean Deskworlds.spec

产物：dist/Deskworlds/  （整个文件夹即免安装包，双击 Deskworlds.exe 运行）
"""
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.getcwd())

datas = []
binaries = []
hiddenimports = []

# 收集第三方包的数据与二进制（WebView2 的 .NET 程序集、pythonnet 运行时等）
for pkg in ("webview", "pythonnet", "clr_loader", "pystray", "PIL"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# 场景文件（约 19MB）
datas.append((os.path.join(ROOT, "deskworlds"), "deskworlds"))

hiddenimports += [
    "clr",
    "webview.platforms.edgechromium",
    "pystray._win32",
    "System",
    "System.Windows.Forms",
    "System.Drawing",
    "System.Threading",
    "System.Threading.Tasks",
    "System.IO",
]

a = Analysis(
    [os.path.join(ROOT, "host", "main.py")],
    pathex=[os.path.join(ROOT, "host")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PySide2", "PySide6", "matplotlib", "numpy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Deskworlds",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # ★ 必须带控制台：无控制台会导致 WebView2 GPU 子进程崩溃
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Deskworlds",
)
