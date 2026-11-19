"""生成应用图标 app.ico（多尺寸）。"""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "app.ico")


def make(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64.0
    def P(x, y):
        return (x * s, y * s)
    # 顶视菱形地块
    d.polygon([P(32, 8), P(56, 20), P(32, 32), P(8, 20)], fill=(90, 200, 160, 255))
    d.polygon([P(8, 20), P(32, 32), P(32, 56), P(8, 44)], fill=(60, 160, 130, 255))
    d.polygon([P(56, 20), P(32, 32), P(32, 56), P(56, 44)], fill=(45, 130, 105, 255))
    # 水波纹
    for off, color in [(0, (220, 245, 235, 230)), (6, (180, 225, 205, 190))]:
        d.arc([P(14, 22 + off)[0], P(14, 22 + off)[1], P(50, 38 + off)[0], P(50, 38 + off)[1]],
              200, 340, fill=color, width=max(2, int(2 * s)))
    return img


base = make(256)
base.save(OUT, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("saved:", OUT, os.path.getsize(OUT), "bytes")
