#!/usr/bin/env python3
"""m2res wallpick — револьвер выбора обоев из райса.
Шесть круглых превью по кругу, в центре название, внизу чипы режима перехода
(FADE / WIPE / GROW / OUTER / CLOCK / RANDOM). Enter — применить с переходом.
Колесо / стрелки — крутить, Tab — режим перехода, C — моно/цвет, Esc или клик мимо — закрыть.
Обои ставятся через hyprpaper; переход рисует отдельное окно на слое BACKGROUND.
Запуск: m2res-wallpick toggle   (или: wallpick.py --warm — только прогреть кэш превью)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import ST  # noqa: E402
import cairo  # noqa: E402
import gi, json, math, random, re, shutil, subprocess, threading, time  # noqa: E402
from PIL import Image, ImageFilter, ImageOps  # noqa: E402

HOME = os.path.expanduser("~")
M2 = HOME + "/.config/m2res"
WALL_DIRS = [os.path.expanduser(d) for d in os.environ.get("M2_WALL_DIR", HOME + "/Pictures/anime-wallpapers:" + HOME + "/Pictures/dotfiles-wallpapers").split(":") if d]
CACHE = HOME + "/.cache/m2res/wallpick"
STATE = M2 + "/wallpick-state.json"
FONT = ST.font
MODES = ["fade", "wipe", "grow", "outer", "clock", "random"]
FITS = ["auto", "fill", "fit"]     # fill — на весь экран с обрезкой; fit — целиком + размытые края; auto — fit для узких, fill для ультрашироких
AUTO_FIT_BELOW = 2.0               # соотношение сторон картинки, ниже которого auto вписывает целиком
MONO_DARK = "#070900"

ORB, R_N, R_S, PAD = 190, 56, 74, 15      # орбита, радиусы слотов, поля корпуса
CENTER_R = 118
CH_W, CH_H, CH_GAP = 132, 44, 12
T_OPEN, T_CLOSE, T_TRANS = 0.45, 0.25, 1.1


def ease_out_back(t, s=1.6):
    t = max(0.0, min(1.0, t)) - 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def accent_hex():
    try:
        m = re.search(r"@define-color\s+accent\s+(#[0-9a-fA-F]{6})", open(M2 + "/waybar/colors.css").read())
        return m.group(1)
    except Exception:
        return "#b0d500"


ACC_HEX = accent_hex()
ACC = tuple(int(ACC_HEX[i:i + 2], 16) / 255 for i in (1, 3, 5))


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(**kw):
    s = load_state(); s.update(kw)
    try:
        json.dump(s, open(STATE, "w"))
    except Exception:
        pass


# ---------------- картинки ----------------
def list_walls():
    exts = (".jpg", ".jpeg", ".png", ".webp")
    out = []
    files = []
    for d in WALL_DIRS:                       # папки идут в заданном порядке, внутри — по имени
        try:
            files += [os.path.join(d, f) for f in sorted(os.listdir(d), key=str.lower) if f.lower().endswith(exts)]
        except Exception:
            pass
    for p in files:
        f = os.path.basename(p)
        if not os.path.isfile(p):
            continue
        try:
            with Image.open(p) as im:
                sz = im.size
        except Exception:
            continue
        out.append(dict(path=p, stem=os.path.splitext(f)[0], ext=os.path.splitext(f)[1][1:].upper(),
                        size=sz, mtime=int(os.path.getmtime(p))))
    return out


def open_fast(path, target):
    im = Image.open(path)
    if path.lower().endswith((".jpg", ".jpeg")):
        im.draft("RGB", target)
    return im.convert("RGB")


def eff_fit(fit, size):
    if fit == "auto":
        return "fit" if size[0] / size[1] < AUTO_FIT_BELOW else "fill"
    return fit


def compose(im, W, H, how):
    """fill — обрезка по центру; fit — картинка целиком по высоте, по бокам её же размытое продолжение"""
    if how == "fill":
        return ImageOps.fit(im, (W, H), Image.LANCZOS)
    small = ImageOps.fit(im, (W // 8, H // 8), Image.BILINEAR).filter(ImageFilter.GaussianBlur(9))
    bg = small.resize((W, H), Image.BICUBIC).point(lambda v: int(v * 0.6))
    fg = ImageOps.contain(im, (W, H), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    return bg


def recolor(im, mono):
    if not mono:
        return im
    g = ImageOps.autocontrast(im.convert("L"), cutoff=2)
    return ImageOps.colorize(g, black=MONO_DARK, white=ACC_HEX)


def thumb_file(it, mono):
    return f"{CACHE}/{'m' if mono else 'c'}-{it['stem']}-{it['mtime']}-{ACC_HEX[1:] if mono else 'x'}.png"


def make_thumb(it, mono):
    p = thumb_file(it, mono)
    if os.path.exists(p):
        return p
    os.makedirs(CACHE, exist_ok=True)
    im = ImageOps.fit(open_fast(it["path"], (640, 640)), (320, 320), Image.LANCZOS)
    tmp = p + ".tmp.png"
    recolor(im, mono).save(tmp, compress_level=1)
    os.replace(tmp, p)
    return p


def to_surface(im):
    w, h = im.size
    buf = bytearray(im.tobytes("raw", "BGRX"))
    return cairo.ImageSurface.create_for_data(buf, cairo.FORMAT_RGB24, w, h, w * 4), buf


def active_wallpaper(mon):
    try:
        for line in subprocess.run(["hyprctl", "hyprpaper", "listactive"], capture_output=True, text=True).stdout.splitlines():
            m = re.match(r"\s*([^:]+):\s*(.+)$", line)
            if m and (not mon or m.group(1).strip() == mon):
                return m.group(2).strip()
    except Exception:
        pass
    return None


if "--warm" in sys.argv:
    its = list_walls(); t0 = time.time()
    for mono in (True, False):
        for it in its:
            make_thumb(it, mono)
    print(f"warm: {len(its)} шт × 2 за {time.time() - t0:.1f}с -> {CACHE}")
    sys.exit(0)

gi.require_version("Gtk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402


class _Keys:
    def __getattr__(self, n):
        return getattr(Gdk, "KEY_" + n)


KEYS = _Keys()


def monitor_by_name(name):
    for m in Gdk.Display.get_default().get_monitors():
        if not name or m.get_connector() == name:
            return m
    return Gdk.Display.get_default().get_monitors().get_item(0)


def ease_out_quart(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 4


def setup_layer(win, layer, ns, kb, mon):
    LS.init_for_window(win); LS.set_layer(win, layer)
    for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
        LS.set_anchor(win, e, True)
    LS.set_exclusive_zone(win, -1); LS.set_namespace(win, ns); LS.set_keyboard_mode(win, kb)
    if mon:
        LS.set_monitor(win, mon)
    css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; } window.m2dim { background: rgba(0,0,0,0.42); }")
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def draw_text(cr, s, x, y, size, color=ST.n(1, 1, 1), bold=True, align="c"):
    lay = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription(f"{FONT} {'Bold' if bold else ''}"); fd.set_absolute_size(size * Pango.SCALE)
    lay.set_font_description(fd); lay.set_text(s, -1)
    w, h = lay.get_pixel_size()
    ox = x - w / 2 if align == "c" else (x if align == "l" else x - w)
    cr.move_to(ox, y - h / 2); cr.set_source_rgb(*color); PangoCairo.show_layout(cr, lay)
    return w


def draw_block(cr, s, cx, cy, maxw, size, color):
    """до трёх строк по центру, с переносом по словам; шрифт уменьшается, пока название не влезет целиком"""
    lay = PangoCairo.create_layout(cr)
    lay.set_width(int(maxw * Pango.SCALE)); lay.set_alignment(Pango.Alignment.CENTER)
    lay.set_wrap(Pango.WrapMode.WORD_CHAR); lay.set_ellipsize(Pango.EllipsizeMode.END); lay.set_height(-3)
    lay.set_text(s, -1)
    while True:
        fd = Pango.FontDescription(f"{FONT} Bold"); fd.set_absolute_size(size * Pango.SCALE)
        lay.set_font_description(fd)
        if not lay.is_ellipsized() or size <= 13:
            break
        size -= 1
    w, h = lay.get_pixel_size()
    cr.move_to(cx - maxw / 2, cy - h / 2); cr.set_source_rgb(*color); PangoCairo.show_layout(cr, lay)


class Picker(Gtk.ApplicationWindow):
    def __init__(self, app, mon_name):
        super().__init__(application=app)
        self.mon_name = mon_name
        self.mon = monitor_by_name(mon_name)
        g = self.mon.get_geometry(); sc = self.mon.get_scale_factor() or 1
        self.mon_px = (g.width * sc, g.height * sc)
        self.items = list_walls()
        st = load_state()
        self.mono = st.get("mono", True)
        self.mode = st.get("mode", "clock") if st.get("mode") in MODES else "clock"
        self.fit = st.get("fit", "auto") if st.get("fit") in FITS else "auto"
        self.target = 0
        for i, it in enumerate(self.items):
            if it["stem"] == st.get("last"):
                self.target = i
        self.pos = self.target - 2.0          # при открытии револьвер докручивается до места
        self.last_t = None
        self.surf, self.ready = {}, set()
        self.old = None; self.old_done = False; self.new = None
        self.hover = -1
        self.chips, self.slots = [], []
        self.W, self.H = 5120, 1440
        self.state = "pick"; self.close_at = None; self.t0 = None; self.trans_started = False

        setup_layer(self, LS.Layer.OVERLAY, "m2res-wallpick", LS.KeyboardMode.EXCLUSIVE, self.mon)
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw); self.set_child(self.area)
        # окно остаётся полноэкранным только ради затемнения (CSS, рисует GPU); cairo-поверхность — лишь под револьвер (было 29 МБ за кадр)
        self.add_css_class("m2dim"); self.area.set_halign(Gtk.Align.CENTER); self.area.set_valign(Gtk.Align.CENTER)
        self.area.set_size_request(1160, 1040); self.set_opacity(0.0)
        wck = Gtk.GestureClick(); wck.set_button(1); wck.connect("pressed", self.on_click_outside); self.add_controller(wck)
        ck = Gtk.GestureClick(); ck.set_button(1); ck.connect("pressed", self.on_click); self.area.add_controller(ck)
        mc = Gtk.EventControllerMotion(); mc.connect("motion", self.on_motion); self.area.add_controller(mc)
        sc_ = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        sc_.connect("scroll", self.on_scroll); self.area.add_controller(sc_)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); self.add_controller(kc)
        self.connect("map", lambda *_: setattr(self, "t0", time.monotonic()))
        self.area.add_tick_callback(self.tick)
        threading.Thread(target=self.gen_thumbs, daemon=True).start()
        threading.Thread(target=self.load_old, daemon=True).start()

    # ---- фоновые задачи ----
    def gen_thumbs(self):
        order = sorted(range(len(self.items)), key=lambda i: min((i - self.target) % len(self.items), (self.target - i) % len(self.items)))
        for mono in (self.mono, not self.mono):
            for i in order:
                try:
                    make_thumb(self.items[i], mono)
                    GLib.idle_add(self.mark_ready, i, mono)
                except Exception as e:
                    print("thumb:", self.items[i]["path"], e, file=sys.stderr)

    def mark_ready(self, i, mono):
        self.ready.add((i, mono)); self.area.queue_draw(); return False

    def load_old(self):
        try:
            p = active_wallpaper(self.mon_name)
            if p and os.path.exists(p):
                W, H = self.mon_px
                im = ImageOps.fit(open_fast(p, (W, H)), (W, H), Image.LANCZOS)
                self.old = to_surface(im)
        except Exception as e:
            print("old:", e, file=sys.stderr)
        self.old_done = True

    def prepare_new(self, it, mono, fit):
        try:
            W, H = self.mon_px
            how = eff_fit(fit, it["size"])
            im = recolor(compose(open_fast(it["path"], (W, H)), W, H, how), mono)
            os.makedirs(CACHE + "/applied", exist_ok=True)
            out = f"{CACHE}/applied/{it['stem']}-{'m' if mono else 'c'}-{how}-{ACC_HEX[1:]}-{W}x{H}.png"
            im.save(out, compress_level=1)
            self.new = (to_surface(im), out)
        except Exception as e:
            print("new:", e, file=sys.stderr)
            self.new = False

    # ---- ввод ----
    def idx(self):
        return round(self.pos) % max(1, len(self.items))

    def step(self, n):
        if self.state == "pick":
            self.target += n

    def cycle_mode(self, n):
        self.mode = MODES[(MODES.index(self.mode) + n) % len(MODES)]; save_state(mode=self.mode); self.area.queue_draw()

    def cycle_fit(self):
        self.fit = FITS[(FITS.index(self.fit) + 1) % len(FITS)]; save_state(fit=self.fit); self.area.queue_draw()

    def toggle_mono(self):
        self.mono = not self.mono; save_state(mono=self.mono)
        threading.Thread(target=self.gen_thumbs, daemon=True).start(); self.area.queue_draw()

    def on_key(self, _c, keyval, code, state):
        if self.state != "pick":
            return True
        K = KEYS
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if keyval == K.Escape: self.begin_close()
        elif keyval in (K.Left, K.Up, K.h, K.k) or code in (43, 45): self.step(-1)      # h / k
        elif keyval in (K.Right, K.Down, K.l, K.j) or code in (46, 44): self.step(1)     # l / j
        elif keyval == K.ISO_Left_Tab or (keyval == K.Tab and shift): self.cycle_mode(-1)
        elif keyval == K.Tab: self.cycle_mode(1)
        elif keyval in (K.Return, K.KP_Enter, K.space): self.apply()
        elif keyval in (K.c, K.C) or code == 54: self.toggle_mono()
        elif keyval in (K.f, K.F) or code == 41: self.cycle_fit()
        elif keyval in (K.Page_Down,): self.step(6)
        elif keyval in (K.Page_Up,): self.step(-6)
        return True

    def on_scroll(self, _c, dx, dy):
        if dy:
            self.step(1 if dy > 0 else -1)
        return True

    def on_motion(self, _c, x, y):
        h = -1
        for i, (cx, cy, w, hh, _m) in enumerate(self.chips):
            if cx <= x <= cx + w and cy <= y <= cy + hh:
                h = i
        if h != self.hover:
            self.hover = h; self.area.queue_draw()

    def on_click(self, _g, _n, x, y):
        if self.state != "pick":
            return
        for (cx, cy, w, hh, m) in self.chips:
            if cx <= x <= cx + w and cy <= y <= cy + hh:
                self.mode = m; save_state(mode=m); self.area.queue_draw(); return
        for (sx, sy, r, rel) in self.slots:
            if math.hypot(x - sx, y - sy) <= r:
                if abs(rel) < 0.5: self.apply()
                else: self.step(round(rel))
                return
        cx, cy = self.W / 2, self.H / 2 - 30
        d = math.hypot(x - cx, y - cy)
        if d <= CENTER_R:
            self.apply(); return
        if d <= ORB + R_S + 24:
            return
        if abs(x - cx) < 480 and cy + 300 < y < cy + 450:
            return
        self.begin_close()

    def on_click_outside(self, _g, _n, x, y):
        b = self.area.compute_bounds(self)
        if b[0] and not (b[1].get_x() <= x <= b[1].get_x() + b[1].get_width() and b[1].get_y() <= y <= b[1].get_y() + b[1].get_height()) and self.state == "pick":
            self.begin_close()

    def update_opacity(self, now):
        if self.close_at is not None: a = 1 - min(1.0, (now - self.close_at) / T_CLOSE)
        else: a = min(1.0, ((now - self.t0) if self.t0 else 0) / 0.22)
        self.set_opacity(max(0.0, min(1.0, a)))

    def begin_close(self):
        if self.close_at is None and self.t0 is not None:
            self.close_at = time.monotonic()

    def apply(self):
        if self.state != "pick" or not self.items:
            return
        it = self.items[self.idx()]
        self.state = "applying"; self.begin_close()
        save_state(last=it["stem"])
        self.chosen = random.choice(MODES[:-1]) if self.mode == "random" else self.mode
        threading.Thread(target=self.prepare_new, args=(it, self.mono, self.fit), daemon=True).start()

    # ---- кадр ----
    def tick(self, *_):
        if self.t0 is None:
            return True
        now = time.monotonic(); self.update_opacity(now)
        dt = 0.016 if self.last_t is None else min(0.05, now - self.last_t); self.last_t = now
        if self.pos != self.target:
            self.pos += (self.target - self.pos) * (1 - math.exp(-dt * 15))
            if abs(self.target - self.pos) < 0.002: self.pos = self.target
        gone = self.close_at is not None and now - self.close_at > T_CLOSE
        if gone and self.state == "pick":
            self.get_application().quit(); return False
        if gone and self.state == "applying" and not self.trans_started and self.new is not None and self.old_done:
            self.trans_started = True
            if self.new is False:
                self.get_application().quit(); return False
            self.get_application().start_transition(self.mon, self.mon_name, self.old, self.new, self.chosen)
            self.set_visible(False)
            GLib.idle_add(self.destroy); return False
        busy = (self.pos != self.target) or now - self.t0 < T_OPEN + 0.1 or self.close_at is not None
        if busy:
            self.area.queue_draw()
        return True

    def surface(self, i):
        key = (i, self.mono)
        s = self.surf.get(key)
        if s is None and key in self.ready:
            try:
                s = self.surf[key] = cairo.ImageSurface.create_from_png(thumb_file(self.items[i], self.mono))
            except Exception:
                return None
        return s

    # ---- рисование ----
    def poly(self, cr, x, y, w, h, c=10):
        cr.new_path()
        for k, (px, py) in enumerate([(x + c, y), (x + w, y), (x + w, y + h - c), (x + w - c, y + h), (x, y + h), (x, y + c)]):
            (cr.move_to if k == 0 else cr.line_to)(px, py)
        cr.close_path()

    def draw(self, _a, cr, w, h):
        self.W, self.H = w, h
        now = time.monotonic(); t = (now - self.t0) if self.t0 else 0
        if self.close_at is not None:
            u = min(1.0, (now - self.close_at) / T_CLOSE); a = 1 - u; sc = 1 - 0.12 * u
        else:
            a = 1.0; sc = 0.78 + 0.22 * ease_out_quart(t / T_OPEN)
        if self.close_at is not None: a = 1.0                      # затухание — через прозрачность окна (update_opacity)
        cx, cy = w / 2, h / 2 - 30
        bx, by, bw, bh = cx - 540, cy - 330, 1080, 840
        cr.save(); cr.rectangle(bx, by, bw, bh); cr.clip()
        cr.push_group()
        cr.translate(cx, cy); cr.scale(sc, sc); cr.translate(-cx, -cy)
        self.draw_wheel(cr, cx, cy)
        self.draw_chips(cr, cx, cy + 372)
        cr.pop_group_to_source(); cr.paint(); cr.restore()

    def draw_wheel(self, cr, cx, cy):
        # корпус: объединение шести «лепестков» + центральный диск
        def body():
            cr.new_path()
            cr.new_sub_path(); cr.arc(cx, cy, ORB - 30, 0, 2 * math.pi)
            for k in range(6):
                ang = math.radians(-90 + 60 * k); rr = R_S + PAD if k == 0 else R_N + PAD
                cr.new_sub_path(); cr.arc(cx + ORB * math.cos(ang), cy + ORB * math.sin(ang), rr, 0, 2 * math.pi)
        for lw, al in ((46, 0.06), (32, 0.08), (20, 0.1)):
            body(); cr.set_source_rgba(0, 0, 0, al); cr.set_line_width(lw); cr.stroke()
        body(); cr.set_source_rgb(*ST.n(0.2, 0.2, 0.21)); cr.set_line_width(9); cr.stroke_preserve()
        cr.set_source_rgb(*ST.n(0.085, 0.085, 0.09)); cr.fill()
        # центр
        cr.arc(cx, cy, CENTER_R + 6, 0, 2 * math.pi); cr.set_source_rgb(*ST.n(0.2, 0.2, 0.21)); cr.fill()
        cr.arc(cx, cy, CENTER_R, 0, 2 * math.pi); cr.set_source_rgb(*ST.n(0.045, 0.045, 0.04)); cr.fill()
        cr.arc(cx, cy, CENTER_R - 7, 0, 2 * math.pi); cr.set_source_rgba(*ACC, 0.85); cr.set_line_width(2); cr.stroke()
        N = len(self.items)
        if not N:
            draw_text(cr, "НЕТ ОБОЕВ", cx, cy, 16, ST.n(0.8, 0.8, 0.8)); return
        it = self.items[self.idx()]
        draw_text(cr, f"{self.idx() + 1:02d} / {N:02d}", cx, cy - 62, 12, ACC)
        draw_block(cr, re.sub(r"[-_]+", " ", it["stem"]).upper(), cx, cy - 10, CENTER_R * 1.55, 24, ST.n(1, 1, 1))
        draw_text(cr, f"{it['size'][0]}×{it['size'][1]} · {it['ext']}", cx, cy + 42, 11, ST.n(0.6, 0.6, 0.62), False)
        how = eff_fit(self.fit, it["size"])
        draw_text(cr, ("MONO" if self.mono else "COLOR") + " · " + (how.upper() if self.fit != "auto" else "AUTO:" + how.upper()),
                  cx, cy + 68, 11, ACC if self.mono else ST.n(0.9, 0.9, 0.9), True)
        # слоты
        vis = []
        for i in range(N):
            rel = (i - self.pos + 2.5) % N - 2.5
            if rel < 3.5:
                vis.append((abs(rel) if abs(rel) < 1 else 9, i, rel))
        vis.sort(key=lambda v: -v[0])
        self.slots = []
        for _s, i, rel in vis:
            al = max(0.0, min(1.0, min(rel + 2.5, 3.5 - rel) / 0.7))
            if al <= 0.01:
                continue
            ang = math.radians(-90 + 60 * rel)
            sx, sy = cx + ORB * math.cos(ang), cy + ORB * math.sin(ang)
            sel = max(0.0, 1 - abs(rel)); r = R_N + (R_S - R_N) * sel
            self.slots.append((sx, sy, r, rel))
            if al < 0.99: cr.push_group()
            cr.arc(sx, sy, r + 5, 0, 2 * math.pi); cr.set_source_rgb(*ST.n(0.03, 0.03, 0.035)); cr.fill()
            th = self.surface(i)
            cr.save(); cr.arc(sx, sy, r, 0, 2 * math.pi); cr.clip()
            if th is not None:
                cr.translate(sx - r, sy - r); k = 2 * r / th.get_width(); cr.scale(k, k)
                cr.set_source_surface(th, 0, 0); cr.get_source().set_filter(cairo.FILTER_GOOD); cr.paint()
            else:
                cr.set_source_rgb(*ST.n(0.12, 0.12, 0.13)); cr.paint()
            cr.restore()
            if sel > 0.02:
                cr.arc(sx, sy, r + 3, 0, 2 * math.pi); cr.set_source_rgba(1, 1, 1, sel); cr.set_line_width(5); cr.stroke()
                cr.arc(sx, sy, r - 4, 0, 2 * math.pi); cr.set_source_rgba(*ACC, sel * 0.9); cr.set_line_width(2); cr.stroke()
            else:
                cr.arc(sx, sy, r + 2, 0, 2 * math.pi); cr.set_source_rgb(*ST.n(0.1, 0.1, 0.11)); cr.set_line_width(4); cr.stroke()
            if sel < 0.5:
                for ox, oy in ((-1.5, 0), (1.5, 0), (0, -1.5), (0, 1.5)):
                    draw_text(cr, str(i + 1), sx + ox, sy + r * 0.55 + oy, 20, (0, 0, 0))
                draw_text(cr, str(i + 1), sx, sy + r * 0.55, 20, ST.n(1, 1, 1))
            if al < 0.99:
                cr.pop_group_to_source(); cr.paint_with_alpha(al)

    def draw_chips(self, cr, cx, y):
        total = len(MODES) * CH_W + (len(MODES) - 1) * CH_GAP; x0 = cx - total / 2
        for sx in (-1, 1):
            cr.move_to(cx + sx * 90, y - 30); cr.line_to(cx + sx * (total / 2 - 20), y - 30)
            cr.set_source_rgba(*ST.n(1, 1, 1, 0.12)); cr.set_line_width(1); cr.stroke()
        draw_text(cr, "TRANSITION MODE", cx, y - 30, 10, ST.n(0.65, 0.65, 0.68), True)
        self.chips = []
        for i, m in enumerate(MODES):
            x = x0 + i * (CH_W + CH_GAP); sel = m == self.mode; yy = y - 4 if sel else y
            self.poly(cr, x, yy + 3, CH_W, CH_H, 11); cr.set_source_rgba(0, 0, 0, 0.6); cr.fill()
            self.poly(cr, x, yy, CH_W, CH_H, 11)
            if sel: cr.set_source_rgb(*ACC)
            else: cr.set_source_rgb(*ST.n(0.15, 0.15, 0.16)) if i == self.hover else cr.set_source_rgb(*ST.n(0.085, 0.085, 0.09))
            cr.fill_preserve(); cr.set_source_rgb(*ST.n(0.22, 0.22, 0.23)) if not sel else cr.set_source_rgb(*ST.n(1, 1, 1))
            cr.set_line_width(2); cr.stroke()
            draw_text(cr, m.upper(), x + CH_W / 2, yy + CH_H / 2, 16, ST.n(0.07, 0.08, 0.02) if sel else ST.n(1, 1, 1), True)
            self.chips.append((x, y - 4, CH_W, CH_H + 4, m))


class Trans(Gtk.ApplicationWindow):
    """смена обоев с переходом: рисуем на BACKGROUND (над hyprpaper), в конце ставим обои через hyprpaper"""
    def __init__(self, app, mon, mon_name, old, new, mode, on_done):
        super().__init__(application=app)
        self.old, self.new, self.mode, self.on_done = old, new, mode, on_done
        layer = LS.Layer.OVERLAY if os.environ.get("M2_WP_LAYER") == "overlay" else LS.Layer.BACKGROUND
        setup_layer(self, layer, "m2res-wallpaper", LS.KeyboardMode.NONE, mon)
        self.dur = float(os.environ.get("M2_WP_DUR", T_TRANS))
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw); self.set_child(self.area)
        self.t0 = None; self.finished = False
        self.connect("map", self.on_map)
        self.area.add_tick_callback(self.tick)

    def on_map(self, *_):
        try:
            self.get_surface().set_input_region(cairo.Region())
        except Exception:
            pass
        self.t0 = time.monotonic()

    def tick(self, *_):
        if self.t0 is None: return True
        self.area.queue_draw()
        if not self.finished and time.monotonic() - self.t0 > self.dur:
            self.finished = True; self.on_done()
        return not self.finished

    def draw(self, _a, cr, w, h):
        p = ease_in_out(((time.monotonic() - self.t0) if self.t0 else 0) / self.dur)
        (ns, _nb), (os_, _ob) = self.new[0], (self.old if self.old else (None, None))
        W, H = ns.get_width(), ns.get_height(); cr.scale(w / W, h / H); w, h = W, H
        if os_ is not None: cr.set_source_surface(os_, 0, 0)
        else: cr.set_source_rgb(*ST.n(0.03, 0.03, 0.03))
        cr.paint()
        cx, cy = w / 2, h / 2; R = math.hypot(w, h) / 2 + 4
        cr.save()
        m = self.mode
        if m == "fade":
            cr.set_source_surface(ns, 0, 0); cr.paint_with_alpha(p); cr.restore(); return
        if m == "wipe": cr.rectangle(0, 0, w * p, h)
        elif m == "grow": cr.arc(cx, cy, R * p, 0, 2 * math.pi)
        elif m == "outer":
            cr.rectangle(0, 0, w, h); cr.arc(cx, cy, R * (1 - p), 0, 2 * math.pi); cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        else:  # clock
            cr.move_to(cx, cy); cr.arc(cx, cy, R, -math.pi / 2, -math.pi / 2 + 2 * math.pi * max(p, 1e-4)); cr.close_path()
        cr.clip(); cr.set_source_surface(ns, 0, 0); cr.paint(); cr.restore()
        if m == "wipe" and 0 < p < 1:
            cr.rectangle(w * p - 2, 0, 4, h); cr.set_source_rgba(*ACC, 0.9); cr.fill()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.m2res.wallpick")
        self.connect("activate", lambda a: Picker(a, os.environ.get("M2_MON")).present())

    def start_transition(self, mon, mon_name, old, new, mode):
        (_s, _b), out = new[0], new[1]

        def done():
            subprocess.run(["hyprctl", "hyprpaper", "wallpaper", f"{mon_name or ''},{out}"], capture_output=True)
            try:                         # lock/m2res-theme берут «текущие» обои отсюда
                tmp = M2 + "/wallpapers/.current.tmp.png"; shutil.copyfile(out, tmp)
                os.replace(tmp, M2 + "/wallpapers/current.png")
            except Exception as e:
                print("current.png:", e, file=sys.stderr)
            try:                         # акцент райса следует за обоями (waybar, меню, lock, mako)
                subprocess.Popen(["bash", "-c", "sleep 0.8; exec " + M2 + "/scripts/m2res-accent auto"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            except Exception as e:
                print("accent:", e, file=sys.stderr)
            GLib.timeout_add(450, lambda: (self.quit(), False)[1])
        Trans(self, mon, mon_name, old, new, mode, done).present()


if __name__ == "__main__":
    sys.exit(App().run([sys.argv[0]]))
