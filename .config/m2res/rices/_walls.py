#!/usr/bin/env python3
"""Процедурные обои для встроенных райсов (5120x1440, без внешних картинок): paper, brutal, cyber, glass, tty, zen. Детерминированно."""
import os, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

R = os.path.dirname(os.path.abspath(__file__)); W, H = 5120, 1440
rng = np.random.default_rng(7)


def grad(c0, c1, vertical=True):
    t = np.linspace(0, 1, H if vertical else W)[:, None, None] if vertical else np.linspace(0, 1, W)[None, :, None]
    a = np.array(c0, float); b = np.array(c1, float)
    g = a + (b - a) * t
    return np.broadcast_to(g, (H, W, 3)).copy()


def save(name, arr):
    im = Image.fromarray(np.clip(arr, 0, 255).astype("uint8")); im.save(f"{R}/{name}/wall.jpg", quality=90); print("wall", name)


def mono(sz):
    for p in ("/usr/share/fonts/noto/NotoSansMono-Bold.ttf", "/usr/share/fonts/TTF/NotoSansMono-Bold.ttf"):
        if os.path.isfile(p): return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


# paper — тёплая бумага, зерно, большие мягкие дуги
a = grad((246, 240, 227), (232, 222, 203))
a += rng.normal(0, 2.2, (H, W, 1))
im = Image.fromarray(np.clip(a, 0, 255).astype("uint8")); d = ImageDraw.Draw(im, "RGBA")
d.ellipse((3300, -420, 4700, 980), fill=(194, 65, 12, 235))
d.ellipse((3480, -240, 4520, 800), fill=(231, 120, 52, 120))
for i, y in enumerate(range(900, 1500, 46)):
    d.arc((-600 + i * 40, y - 500, 4200 + i * 40, y + 500), 190, 350, fill=(60, 40, 20, 38), width=3)
for i in range(6): d.rounded_rectangle((300 + i * 22, 220 + i * 22, 1500 + i * 22, 760 + i * 22), 30, outline=(60, 40, 20, 30), width=2)
im = im.filter(ImageFilter.GaussianBlur(0.6)); im.save(f"{R}/paper/wall.jpg", quality=90); print("wall paper")

# brutal — крупные геометрические фигуры с чёрным контуром и жёсткими тенями
im = Image.new("RGB", (W, H), (253, 245, 217)); d = ImageDraw.Draw(im)
for x in range(0, W, 80): d.line((x, 0, x, H), fill=(240, 230, 190), width=2)
for y in range(0, H, 80): d.line((0, y, W, y), fill=(240, 230, 190), width=2)
def sh(box, fill, kind="rect"):
    o = 22
    bx = (box[0] + o, box[1] + o, box[2] + o, box[3] + o)
    if kind == "rect": d.rectangle(bx, fill=(13, 13, 13)); d.rectangle(box, fill=fill, outline=(13, 13, 13), width=8)
    elif kind == "ell": d.ellipse(bx, fill=(13, 13, 13)); d.ellipse(box, fill=fill, outline=(13, 13, 13), width=8)
sh((300, 240, 960, 900), (255, 61, 113), "ell"); sh((1250, 420, 2150, 1060), (255, 226, 122)); sh((2500, 180, 3200, 880), (96, 165, 250), "ell")
sh((3550, 520, 4350, 1120), (110, 231, 160)); sh((4500, 200, 4900, 600), (255, 61, 113))
tri = [(1500, 1250), (1900, 700), (2300, 1250)]
d.polygon([(x + 22, y + 22) for x, y in tri], fill=(13, 13, 13)); d.polygon(tri, fill=(255, 140, 66), outline=(13, 13, 13))
d.line(tri + [tri[0]], fill=(13, 13, 13), width=8)
d.text((300, 1120), "M2RES / BRUTAL", font=mono(150), fill=(13, 13, 13))
im.save(f"{R}/brutal/wall.jpg", quality=92); print("wall brutal")

# cyber — синтвейв: солнце с полосами, сетка в перспективе
a = grad((14, 6, 40), (54, 12, 84)); im = Image.fromarray(a.astype("uint8")); d = ImageDraw.Draw(im, "RGBA")
cx, cy, rad = W // 2, 700, 420
for k in range(60, 0, -1):
    d.ellipse((cx - rad - k * 5, cy - rad - k * 5, cx + rad + k * 5, cy + rad + k * 5), fill=(255, 40, 160, 2))
sun = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(sun)
for i in range(rad * 2):
    t = i / (rad * 2); col = (int(255), int(60 + 170 * (1 - t)), int(120 + 60 * t))
    y = cy - rad + i
    half = math.sqrt(max(rad * rad - (y - cy) ** 2, 0)); sd.line((cx - half, y, cx + half, y), fill=col + (255,))
for j in range(10):
    y = cy + 40 + j * 38; sd.rectangle((0, y, W, y + 4 + j * 3), fill=(0, 0, 0, 0)) if False else None
mask = Image.new("L", (W, H), 255); md = ImageDraw.Draw(mask)
for j in range(9): y = cy + 30 + j * 42; md.rectangle((0, y, W, y + 6 + j * 4), fill=0)
sun.putalpha(Image.composite(sun.split()[3], Image.new("L", (W, H), 0), mask)); im.paste(sun, (0, 0), sun)
d = ImageDraw.Draw(im, "RGBA"); hor = cy + 330
d.rectangle((0, hor, W, H), fill=(8, 4, 24, 255))
d.line((0, hor, W, hor), fill=(0, 240, 255, 255), width=5)
for i in range(-60, 61): d.line((cx + i * 80, hor, cx + i * 560, H), fill=(0, 240, 255, 150), width=2)
y, st = hor, 14
while y < H: y += st; st *= 1.28; d.line((0, y, W, y), fill=(0, 240, 255, 150), width=2)
im = im.filter(ImageFilter.GaussianBlur(0.8)); im.save(f"{R}/cyber/wall.jpg", quality=90); print("wall cyber")

# glass — размытые цветные пятна
base = np.zeros((H, W, 3)); base[:] = (14, 20, 36)
im = Image.fromarray(base.astype("uint8")); d = ImageDraw.Draw(im)
for (x, y, r, c) in [(900, 500, 700, (60, 120, 255)), (2300, 1100, 800, (120, 80, 240)), (3500, 400, 760, (40, 200, 240)), (4500, 1050, 700, (230, 90, 200)), (200, 1300, 600, (50, 90, 200))]:
    d.ellipse((x - r, y - r, x + r, y + r), fill=c)
im = im.filter(ImageFilter.GaussianBlur(230))
arr = np.asarray(im).astype(float) * 0.85 + rng.normal(0, 1.6, (H, W, 1)); save("glass", arr)

# tty — зелёный фосфор: сетка, сканлайны, колонка «кода»
im = Image.new("RGB", (W, H), (0, 8, 3)); d = ImageDraw.Draw(im, "RGBA"); f = mono(26)
chars = "01abcdef$#>_/\\|{}[]=+-*"
for col in range(0, W, 30):
    ln = int(rng.integers(6, 46)); y0 = int(rng.integers(-300, H))
    for i in range(ln):
        al = int(20 + 110 * (i / ln) ** 2)
        d.text((col, y0 + i * 32), chars[int(rng.integers(len(chars)))], font=f, fill=(57, 255, 122, al))
a = np.asarray(im).astype(float); a[::3] *= 0.78
vg = np.linspace(-1, 1, W)[None, :, None] ** 2 + np.linspace(-1, 1, H)[:, None, None] ** 2
a *= np.clip(1.15 - 0.45 * vg, 0, 1); save("tty", a)

# zen — спокойный тёмный градиент и концентрические линии
a = grad((22, 22, 25), (10, 10, 12)); im = Image.fromarray(a.astype("uint8")); d = ImageDraw.Draw(im, "RGBA")
for i in range(1, 26):
    r = 80 + i * 62; d.ellipse((W * 0.72 - r, H * 0.5 - r * 0.62, W * 0.72 + r, H * 0.5 + r * 0.62), outline=(228, 228, 231, max(6, 46 - i * 2)), width=2)
d.ellipse((W * 0.72 - 36, H * 0.5 - 36, W * 0.72 + 36, H * 0.5 + 36), fill=(228, 228, 231, 200))
im = im.filter(ImageFilter.GaussianBlur(0.7)); im.save(f"{R}/zen/wall.jpg", quality=92); print("wall zen")
