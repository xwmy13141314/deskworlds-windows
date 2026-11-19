"""系统托盘菜单：对齐 Mac 版菜单栏（世界切换 / 投喂 / 暂停 / 退出）。"""
import os
import logging

import pystray
from PIL import Image, ImageDraw

from config import WORLDS, world_by_id

log = logging.getLogger("dw.tray")


def _make_icon():
    """用 Pillow 画一个简单的 'Deskworlds' 图标（分层地块 + 波纹），避免外部资源依赖。"""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 顶视菱形地块
    d.polygon([(32, 8), (56, 20), (32, 32), (8, 20)], fill=(90, 200, 160, 255))
    d.polygon([(8, 20), (32, 32), (32, 56), (8, 44)], fill=(60, 160, 130, 255))
    d.polygon([(56, 20), (32, 32), (32, 56), (56, 44)], fill=(45, 130, 105, 255))
    # 水波纹
    for off, color in [(0, (220, 245, 235, 220)), (6, (180, 225, 205, 180))]:
        d.arc([14, 22 + off, 50, 38 + off], 200, 340, fill=color, width=2)
    return img


class Tray:
    def __init__(self, app):
        self.app = app
        w = world_by_id(self.app.config["world"])
        self.icon = pystray.Icon(
            "Deskworlds", _make_icon(),
            "桌面世界 · %s（点此投喂/切换/暂停）" % (w.get("name_cn") or w["name"]),
            menu=self._build_menu())

    def _build_menu(self):
        a = self.app
        cfg = a.config

        # 世界切换子菜单
        def make_world_handlers(wid):
            # pystray 要求 action 恰好是 (icon, item)，用闭包捕获 wid
            def on_select(icon, item):
                a.select_world(wid)
            def is_checked(item):
                return cfg["world"] == wid
            return on_select, is_checked

        world_items = []
        for w in WORLDS:
            on_select, is_checked = make_world_handlers(w["id"])
            label = "%s · %s" % (w.get("name_cn") or w["name"], w["name"])
            world_items.append(pystray.MenuItem(
                label, on_select, checked=is_checked, radio=True))
        world_submenu = pystray.Menu(*world_items)

        world = world_by_id(cfg["world"])
        feed_label = {
            "feed": "投喂食物 🐟",
            "stir": "搅动篝火 🔥",
            "lights": "节日彩灯 💡 (开/关)",
            "none": "（此世界无需投喂）",
        }[world["action"]]

        def pause_label(item):
            return "▶ 继续播放" if cfg["paused"] else "⏸ 暂停"

        def status_label(item):
            if cfg["paused"]:
                return "状态：已暂停"
            return "状态：运行中 · %d FPS" % a.current_rate()

        def visibility_label(item):
            return "🐟 恢复壁纸" if a.wallpaper_hidden() else "🖥 临时看桌面图标"

        return pystray.Menu(
            pystray.MenuItem(status_label, lambda *args: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🌍 切换世界", world_submenu),
            pystray.MenuItem(feed_label, lambda *args: a.feed(),
                             enabled=lambda item: a.can_feed()),
            pystray.MenuItem(pause_label, lambda *args: a.toggle_pause()),
            pystray.MenuItem(visibility_label, lambda *args: a.toggle_visibility()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔄 重新加载", lambda *args: a.reload()),
            pystray.MenuItem("❌ 退出", lambda *args: a.quit()),
        )

    def run(self):
        self.icon.run()

    def update(self):
        """配置变化后重建菜单。"""
        try:
            self.icon.menu = self._build_menu()
            w = world_by_id(self.app.config["world"])
            self.icon.title = "桌面世界 · %s（左键菜单：投喂/切换/暂停）" % (
                w.get("name_cn") or w["name"])
        except Exception as e:
            log.debug("tray update failed: %s", e)

    def notify(self, title, message):
        try:
            self.icon.notify(message, title)
        except Exception:
            pass

    def stop(self):
        try:
            self.icon.stop()
        except Exception:
            pass
