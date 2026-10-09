#!/usr/bin/env python3
"""Рисует сцену «комната с ретро-ТВ» для hyprlock.
usage: make_scene.py <wallpaper> <out.png> <W> <H>
Печатает JSON с координатами экрана ТВ (центр) для hyprlock."""
import sys, random, json
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageOps

wall, out, W, H = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
random.seed(7)
B = 1080                       # базовая высота сцены
S = H / B
BW = 1920
canvas = Image.new("RGB", (W, H), (9, 14, 26))

def room(w, h):
    im = Image.new("RGB", (w, h), (10, 17, 30))
    d = ImageDraw.Draw(im)
    for x in range(0, w, 34):                 # перфорированная стена (сетка)
        d.line([(x, 0), (x, h)], fill=(18, 28, 46), width=2)
    for y in range(0, h, 34):
        d.line([(0, y), (w, y)], fill=(18, 28, 46), width=2)
    return im

# --- сцена 1920x1080 ---
sc = room(BW, B); d = ImageDraw.Draw(sc)

# полки слева + VHS
for sy in (228, 650):
    d.rectangle([0, sy, 500, sy + 38], fill=(16, 20, 28))
tapes = [(210, 40, 70), (230, 150, 30), (40, 200, 130), (60, 90, 200), (230, 230, 225), (40, 40, 44), (220, 120, 40), (180, 40, 180)]
for sy, x0 in ((228, 20), (650, 20), (1010, 30)):
    x = x0
    while x < 470:
        w = random.randint(26, 46); h = random.randint(150, 205)
        c = random.choice(tapes)
        d.rectangle([x, sy - h, x + w, sy], fill=c)
        d.rectangle([x + 4, sy - h + 14, x + w - 4, sy - h + 38], fill=(235, 235, 230))
        d.rectangle([x, sy - h, x + w, sy], outline=(0, 0, 0), width=2)
        x += w + 4

# постеры
d.rectangle([600, -10, 1310, 170], fill=(222, 214, 200)); d.rectangle([614, -10, 1296, 156], fill=(196, 120, 40))
d.polygon([(700, 40), (1200, 40), (1150, 130), (760, 130)], fill=(140, 40, 30))
d.rectangle([1545, -10, 1920, 445], fill=(200, 205, 205)); d.rectangle([1562, -10, 1920, 430], fill=(52, 76, 86))
d.ellipse([1640, 20, 1860, 220], fill=(230, 235, 235))
d.rectangle([1750, 190, 1780, 330], fill=(15, 20, 25))

# колонка справа
d.rectangle([1615, 560, 1865, 1000], fill=(142, 82, 38), outline=(60, 30, 14), width=4)
for cy, r in ((635, 40), (735, 40), (860, 85)):
    d.ellipse([1740 - r, cy - r, 1740 + r, cy + r], fill=(40, 40, 42), outline=(15, 15, 16), width=5)
    d.ellipse([1740 - r // 2, cy - r // 2, 1740 + r // 2, cy + r // 2], fill=(90, 90, 92))

# видеомагнитофон
d.rectangle([145, 860, 1790, 1090], fill=(17, 18, 22), outline=(40, 42, 48), width=3)
d.rectangle([650, 895, 1410, 1010], fill=(10, 10, 12), outline=(55, 57, 62), width=3)
d.rectangle([830, 925, 1395, 990], fill=(12, 12, 14), outline=(40, 40, 44), width=2)
d.rectangle([688, 925, 750, 975], outline=(60, 60, 64), width=2); d.ellipse([706, 936, 732, 962], outline=(130, 220, 60), width=3)
d.rectangle([1440, 925, 1520, 1000], outline=(70, 70, 74), width=2)
d.rectangle([1545, 925, 1690, 985], fill=(8, 8, 9))
for cx in (265, 470):
    d.ellipse([cx - 62, 960 - 0, cx + 62, 1084], fill=(30, 30, 32), outline=(8, 8, 8), width=5)
    d.ellipse([cx - 28, 995, cx + 28, 1051], fill=(60, 60, 62))

# корпус ТВ
tv = (500, 175, 1572, 858)
d.rounded_rectangle(tv, 14, fill=(34, 24, 22), outline=(86, 70, 64), width=6)
d.rounded_rectangle((528, 200, 1378, 835), 8, fill=(18, 14, 14), outline=(110, 86, 78), width=5)
scr = (566, 228, 1344, 805)                    # стекло
d.rounded_rectangle((1385, 205, 1540, 830), 6, fill=(28, 22, 22), outline=(70, 56, 52), width=3)
for ky in (312, 424):
    d.ellipse([1418, ky - 38, 1496, ky + 38], fill=(60, 56, 60), outline=(10, 10, 10), width=4)
    d.ellipse([1434, ky - 22, 1480, ky + 22], fill=(34, 32, 36), outline=(120, 120, 124), width=3)
d.rectangle([1405, 486, 1520, 566], fill=(10, 10, 10))
for vy in range(492, 562, 12): d.line([(1405, vy), (1520, vy)], fill=(36, 36, 36), width=3)
d.rectangle([1464, 600, 1480, 800], fill=(10, 10, 10)); d.rectangle([1458, 622, 1488, 664], fill=(210, 190, 170))
d.rectangle([1498, 616, 1508, 662], fill=(190, 40, 40)); d.rectangle([1498, 680, 1508, 726], fill=(40, 120, 60))
# антенна
d.line([(880, 175), (940, 0)], fill=(6, 6, 6), width=7); d.line([(1140, 175), (1085, 0)], fill=(6, 6, 6), width=7)

# --- экран: обои + CRT ---
sx0, sy0, sx1, sy1 = scr
sw, sh = sx1 - sx0, sy1 - sy0
im = Image.open(wall).convert("L")
im = ImageOps.fit(im, (sw, sh), Image.LANCZOS)
tint = Image.open(wall).convert("RGB").resize((1, 1), Image.BOX).getpixel((0, 0))
im = ImageOps.colorize(im, (4, 4, 4), (235, 235, 235)).convert("RGB")
glass = Image.new("RGB", (sw, sh), (0, 0, 0))
glass.paste(im, (0, 0))
g = ImageDraw.Draw(glass)
for y in range(0, sh, 4):                      # строки развёртки
    g.line([(0, y), (sw, y)], fill=(0, 0, 0), width=1)
vig = Image.new("L", (sw, sh), 0)
ImageDraw.Draw(vig).ellipse([-sw * .15, -sh * .2, sw * 1.15, sh * 1.2], fill=255)
vig = vig.filter(ImageFilter.GaussianBlur(70))
glass = Image.composite(glass, Image.new("RGB", (sw, sh), (0, 0, 0)), vig)
mask = Image.new("L", (sw, sh), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, sw - 1, sh - 1], 70, fill=255)
sc.paste(glass, (sx0, sy0), mask)
# блик
gl = Image.new("RGBA", (BW, B), (0, 0, 0, 0))
ImageDraw.Draw(gl).polygon([(600, 240), (900, 240), (700, 440), (600, 440)], fill=(255, 255, 255, 18))
sc = Image.alpha_composite(sc.convert("RGBA"), gl).convert("RGB")

# виньетка комнаты
rv = Image.new("L", (BW, B), 0)
ImageDraw.Draw(rv).ellipse([-300, -200, BW + 300, B + 250], fill=255)
rv = rv.filter(ImageFilter.GaussianBlur(160))
sc = Image.composite(sc, Image.new("RGB", (BW, B), (3, 5, 9)), rv)

sc = sc.resize((int(BW * S), H), Image.LANCZOS)
ox = (W - sc.width) // 2
bg = room(W, H).resize((W, H))
fade = Image.new("L", sc.size, 255)
fd = ImageDraw.Draw(fade)
for i in range(120):
    a = int(255 * i / 120)
    fd.line([(i, 0), (i, H)], fill=a); fd.line([(sc.width - 1 - i, 0), (sc.width - 1 - i, H)], fill=a)
canvas = bg.filter(ImageFilter.GaussianBlur(1))
canvas = Image.composite(canvas, canvas, Image.new("L", (W, H), 255))
canvas.paste(sc, (ox, 0), fade)
canvas = ImageChops.multiply(canvas, Image.new("RGB", (W, H), (255, 255, 255)))
canvas.save(out)
cx = ox + int(((sx0 + sx1) / 2) * S); cy = int(((sy0 + sy1) / 2) * S)
print(json.dumps({"cx": cx, "cy": cy, "sw": int(sw * S), "sh": int(sh * S)}))
