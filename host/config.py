"""配置持久化：世界选择、暂停、开机自启状态。存到 %APPDATA%/Deskworlds。"""
import json
import os

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Deskworlds")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

# 与原项目 ui/worlds.js 顺序严格一致；name_cn 仅用于中文托盘菜单
WORLDS = [
    {"id": "riverscape", "name": "Riverbed", "name_cn": "河床", "action": "feed"},
    {"id": "reefscape", "name": "Coral reef", "name_cn": "珊瑚礁", "action": "feed"},
    {"id": "bettascape", "name": "Betta", "name_cn": "斗鱼", "action": "feed"},
    {"id": "plasmascape", "name": "Plasma globe", "name_cn": "等离子球", "action": "none"},
    {"id": "koiscape", "name": "Koi pond", "name_cn": "锦鲤池", "action": "feed"},
    {"id": "bonfirescape", "name": "Bonfire", "name_cn": "篝火", "action": "stir"},
    {"id": "lakescape", "name": "Lake storm", "name_cn": "湖上风暴", "action": "lights"},
]

DEFAULTS = {
    "world": "riverscape",
    "paused": False,
    "holidayLights": False,
    "startWithWindows": False,
    # 用 balanced（30fps/180万像素）：native 档（1600万像素+4096阴影）
    # 在集成显卡上会压垮 WebGL2 GPU 进程导致崩溃。
    "quality": "balanced",
}


def load():
    data = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            for k in DEFAULTS:
                if k in saved:
                    data[k] = saved[k]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    if data["world"] not in {w["id"] for w in WORLDS}:
        data["world"] = DEFAULTS["world"]
    return data


def save(data):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


def world_by_id(wid):
    for w in WORLDS:
        if w["id"] == wid:
            return w
    return WORLDS[0]
