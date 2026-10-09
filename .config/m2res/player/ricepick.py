#!/usr/bin/env python3
"""m2res ricepick — переключатель райсов: карусель карточек с превью.
← → / колесо — выбрать · Enter — примерить на 10 с (потом «оставить?») · A — применить сразу · Esc — закрыть.
Во время примерки: Enter — оставить, Esc — вернуть прежний райс; не ответили — вернётся само.
Запуск: m2res-rice pick (SUPER+ALT+R)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import ST  # noqa: E402
import cairo  # noqa: E402
import gi, json, math, subprocess, threading, time  # noqa: E402
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0"); gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402
from PIL import Image  # noqa: E402

HOME = os.path.expanduser("~"); M2 = HOME + "/.config/m2res"; RICES = M2 + "/rices"
RICE = M2 + "/scripts/m2res-rice"
CW, CH = 1000, 282            # карточка выбранного райса: превью 32:9
TRIAL = 10


def hexrgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def lerp(a, b, t): return a + (b - a) * t


def acc_now():
    try: return hexrgb(json.load(open(M2 + "/player/colors.json"))["accent"])
    except Exception: return (0.69, 0.84, 0.0)


def load_rices():
    try: return json.loads(subprocess.run([RICE, "dump"], capture_output=True, text=True, timeout=10).stdout)
    except Exception: return []


def surf_from(path, w, h):
    try:
        im = Image.open(path).convert("RGBA"); sc = max(w / im.width, h / im.height)
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
        l, t = (im.width - w) // 2, (im.height - h) // 2; im = im.crop((l, t, l + w, t + h))
        b, g, r, a = (x for x in (im.split()[2], im.split()[1], im.split()[0], im.split()[3]))
        data = bytearray(Image.merge("RGBA", (b, g, r, a)).tobytes())
        return cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32, w, h, w * 4), data
    except Exception: return None, None


def text(cr, s, x, y, size, col, bold=True, align="l", maxw=None):
    lay = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription(f"{ST.font} {'Bold' if bold else ''}"); fd.set_absolute_size(size * Pango.SCALE)
    lay.set_font_description(fd); lay.set_text(s, -1)
    if maxw: lay.set_width(int(maxw * Pango.SCALE)); lay.set_ellipsize(Pango.EllipsizeMode.END)
    w, h = lay.get_pixel_size()
    ox = x if align == "l" else (x - w / 2 if align == "c" else x - w)
    cr.move_to(ox, y - h / 2); cr.set_source_rgba(*col); PangoCairo.show_layout(cr, lay); return w


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.m2res.ricepick")
        self.connect("activate", lambda a: Pick(a).present())


class Pick(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.items = load_rices(); self.imgs = {}
        self.target = next((i for i, r in enumerate(self.items) if r["cur"]), 0); self.pos = self.target - 1.5
        self.mode = "pick"; self.t0 = None; self.trial_end = 0; self.busy = False; self.msg = ""; self.closing = None
        self.acc = acc_now(); self.acc_t = 0
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY); LS.set_namespace(self, "m2res-ricepick")
        for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT): LS.set_anchor(self, e, True)
        LS.set_exclusive_zone(self, -1); LS.set_keyboard_mode(self, LS.KeyboardMode.EXCLUSIVE)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; } window.m2dim { background: rgba(0,0,0,0.5); }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.add_css_class("m2dim")
        self.area = Gtk.DrawingArea(); self.area.set_halign(Gtk.Align.CENTER); self.area.set_valign(Gtk.Align.CENTER)
        self.area.set_size_request(4600, 640); self.area.set_draw_func(self.draw); self.set_child(self.area)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); self.add_controller(kc)
        ck = Gtk.GestureClick(); ck.set_button(1); ck.connect("pressed", self.on_click); self.area.add_controller(ck)
        wck = Gtk.GestureClick(); wck.set_button(1); wck.connect("pressed", lambda *_: self.mode == "pick" and self.quit()); self.add_controller(wck)
        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        sc.connect("scroll", lambda _c, _dx, dy: (self.move(1 if dy > 0 else -1), True)[1]); self.area.add_controller(sc)
        self.connect("map", lambda *_: setattr(self, "t0", time.monotonic()))
        self.area.add_tick_callback(self.tick); self.last = None
        threading.Thread(target=self.load_imgs, daemon=True).start()

    def load_imgs(self):
        for r in self.items:
            n = r["name"]; p = f"{RICES}/{n}/preview.jpg"
            if not os.path.isfile(p):
                p = next((q for q in (f"{RICES}/{n}/wall.jpg", f"{RICES}/{r.get('ext') or n}/preview.jpg") if os.path.isfile(q)), "")
            s = surf_from(p, CW, CH) if p else (None, None)
            self.imgs[n] = s
        GLib.idle_add(self.area.queue_draw)

    # ── управление ──
    def move(self, d):
        if self.mode == "pick": self.target = max(0, min(len(self.items) - 1, self.target + d))

    def quit(self):
        if self.closing: return
        self.closing = time.monotonic()
        GLib.timeout_add(220, lambda: (self.get_application().quit(), False)[1])

    def run(self, *a, then=None):
        def w():
            subprocess.run([RICE, *a], capture_output=True)
            if then: GLib.idle_add(then)
        threading.Thread(target=w, daemon=True).start()

    def on_key(self, _c, kv, _kc, st):
        if self.mode == "trial":
            if kv in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
                self.run("keep"); self.msg = "оставлено"; self.quit()
            elif kv == Gdk.KEY_Escape:
                self.run("revert"); self.msg = "возвращаю…"; self.quit()
            return True
        if self.busy: return True
        if kv == Gdk.KEY_Escape: self.quit()
        elif kv in (Gdk.KEY_Left, Gdk.KEY_h, Gdk.KEY_Up): self.move(-1)
        elif kv in (Gdk.KEY_Right, Gdk.KEY_l, Gdk.KEY_Down, Gdk.KEY_Tab): self.move(1)
        elif kv == Gdk.KEY_Home: self.target = 0
        elif kv == Gdk.KEY_End: self.target = len(self.items) - 1
        elif kv in (Gdk.KEY_Return, Gdk.KEY_KP_Enter): self.start_trial()
        elif kv in (Gdk.KEY_a, Gdk.KEY_A): self.apply_now()
        return True

    def on_click(self, _g, _n, x, y):
        if self.mode != "pick" or self.busy: return
        for i, (x0, y0, x1, y1) in getattr(self, "hits", []):
            if x0 <= x <= x1 and y0 <= y <= y1:
                if i == self.target: self.start_trial()
                else: self.target = i
                return

    def start_trial(self):
        r = self.items[self.target]
        if r["cur"]: self.msg = "этот райс уже включён"; return
        self.busy = True; self.msg = f"применяю «{r['title']}»…"
        def after():
            self.busy = False; self.mode = "trial"; self.trial_end = time.monotonic() + TRIAL
            # окно остаётся на весь экран (иначе слой теряет клавиатурный фокус); просто прозрачное, панель — внизу по центру
            self.remove_css_class("m2dim"); self.area.set_valign(Gtk.Align.END); self.area.set_margin_bottom(90)
            self.area.set_size_request(900, 150); self.area.queue_resize(); self.grab_focus()
        self.run("preview", r["name"], str(TRIAL + 2), then=after)

    def apply_now(self):
        r = self.items[self.target]
        if r["cur"]: self.msg = "этот райс уже включён"; return
        self.busy = True; self.msg = f"применяю «{r['title']}»…"
        self.run("apply", r["name"], then=self.quit)

    # ── кадр ──
    def tick(self, _w, _clk):
        now = time.monotonic()
        dt = 0.016 if self.last is None else min(0.05, now - self.last); self.last = now
        self.pos += (self.target - self.pos) * min(1.0, dt * 11)
        if abs(self.target - self.pos) < 0.001: self.pos = self.target
        if now - self.acc_t > 0.5: self.acc = acc_now(); self.acc_t = now
        if self.mode == "trial" and now > self.trial_end + 0.3 and not self.closing: self.quit()
        self.area.queue_draw(); return GLib.SOURCE_CONTINUE

    def alpha(self):
        now = time.monotonic()
        a = 1.0
        if self.t0: a = min(1.0, (now - self.t0) / 0.28)
        if self.closing: a = max(0.0, 1 - (now - self.closing) / 0.2)
        return a

    def draw(self, _a, cr, w, h):
        ST.maybe_reload(); al = self.alpha(); self.set_opacity(al)
        if self.mode == "trial": return self.draw_trial(cr, w, h)
        A = self.acc; cx, cy = w / 2, h / 2 - 20; self.hits = []
        order = sorted(range(len(self.items)), key=lambda i: -abs(i - self.pos))
        for i in order:
            r = self.items[i]; d = i - self.pos; ad = abs(d)
            if ad > 2.6: continue
            sc = lerp(1.0, 0.62, min(ad, 1.0)) * (0.92 if ad > 1 else 1.0)
            off = (min(ad, 1) * 860 + max(ad - 1, 0) * 640) * (1 if d >= 0 else -1)
            cw, ch = CW * sc, CH * sc; x, y = cx + off - cw / 2, cy - ch / 2 - 30 * sc
            a = max(0.0, 1.0 - max(0.0, ad - 0.6) * 0.45)
            self.card(cr, r, x, y, cw, ch, sc, a, ad < 0.5, i == self.target)
            self.hits.append((i, (x, y, x + cw, y + ch + 120 * sc)))
        self.hits = [(i, b) for i, b in self.hits]
        r = self.items[self.target]
        text(cr, "RICE", cx - 2290, 56, 26, (*A, 0.9), True, "l"); text(cr, f"{self.target + 1} / {len(self.items)}", cx + 2290, 56, 22, (0.8, 0.8, 0.8, 0.6), False, "r")
        hint = "←  →  выбрать     Enter — примерить на 10 с     A — применить сразу     Esc — закрыть"
        text(cr, self.msg or hint, cx, h - 40, 20, (0.92, 0.92, 0.9, 0.75 if not self.msg else 1), False, "c")

    def card(self, cr, r, x, y, cw, ch, sc, a, front, selected):
        pal = r["pal"]; A = hexrgb(pal.get("accent", "#b0d500")); wd = r["wd"]
        cr.push_group()
        pad = 14 * sc; tot_h = ch + 150 * sc
        # корпус карточки рисуем в стиле самого райса: форма и рамка из его widgets
        bgc = wd.get("bg", [0.04, 0.04, 0.04, 0.97]); fgc = wd.get("fg", [0.92, 0.92, 0.88]); dimc = wd.get("dim", [0.55, 0.56, 0.52])
        shape = wd.get("shape", "round"); rr = {"square": 0, "chamfer": 12, "pill": 40}.get(shape, 26 * wd.get("rk", 1.0) * sc)
        saved = (ST.shape, ST.fkind, ST.bg, ST.border_w, ST.border_a, ST.glow_k, ST.shadow)
        ST.shape, ST.fkind, ST.bg = shape, wd.get("frame", "glow"), tuple(bgc) if len(bgc) == 4 else (*bgc, 1)
        ST.border_w, ST.border_a, ST.glow_k = wd.get("border_w", 2.5), wd.get("border_a", 0.55), wd.get("glow_k", 1.0)
        ST.shadow = tuple(wd.get("shadow", (0, 0)))
        ST.frame(cr, x - pad, y - pad, cw + 2 * pad, tot_h + 2 * pad - 20 * sc, A, rr + 4)
        ST.shape, ST.fkind, ST.bg, ST.border_w, ST.border_a, ST.glow_k, ST.shadow = saved
        s = self.imgs.get(r["name"], (None, None))[0]
        cr.save(); ST.path(cr, x, y, cw, ch, max(0, rr * 0.5)); cr.clip()
        if s:
            cr.translate(x, y); cr.scale(cw / CW, ch / CH); cr.set_source_surface(s, 0, 0); cr.paint()
        else:
            cr.set_source_rgba(*A, 0.25); cr.paint()
        cr.restore()
        ty = y + ch + 40 * sc
        text(cr, f"{r['icon']}  {r['title']}", x + 6, ty, 40 * sc, (*A, 1), True, "l", cw - 12)
        if r["cur"]: text(cr, "● ВКЛЮЧЁН", x + cw - 6, ty, 20 * sc, (*A, 1), True, "r")
        text(cr, r["desc"], x + 6, ty + 44 * sc, 21 * sc, (*fgc, 0.85), False, "l", cw - 12)
        # палитра + теги
        sx = x + 6; sy = ty + 82 * sc
        for c in (A, hexrgb(pal["pill_fg"]) if str(pal.get("pill_fg", "")).startswith("#") else fgc, tuple(dimc)):
            ST.path(cr, sx, sy - 11 * sc, 38 * sc, 22 * sc, 11 * sc); cr.set_source_rgba(*c, 1); cr.fill(); sx += 46 * sc
        tags = f"{wd.get('shape', 'round')} · {wd.get('frame', 'glow')} · bar {r['bar'].get('position', 'top')}"
        text(cr, tags, x + cw - 6, sy, 18 * sc, (*dimc, 0.95), False, "r")
        cr.pop_group_to_source(); cr.paint_with_alpha(a)

    def draw_trial(self, cr, w, h):
        left = max(0.0, self.trial_end - time.monotonic()); A = self.acc
        ST.frame(cr, 6, 6, w - 12, h - 12, A, 30)
        r = self.items[self.target]
        text(cr, f"Райс «{r['title']}» — оставить?", 36, 44, 30, (*A, 1), True, "l")
        text(cr, f"Enter — оставить       Esc — вернуть прежний       авто-возврат через {left:0.0f} с", 36, 90, 19, ST.n(0.9, 0.9, 0.86, 0.9), False, "l")
        bw = w - 72; cr.set_source_rgba(*A, 0.18); ST.path(cr, 36, 118, bw, 10, 5); cr.fill()
        cr.set_source_rgba(*A, 1); ST.path(cr, 36, 118, max(10, bw * left / TRIAL), 10, 5); cr.fill()


if __name__ == "__main__":
    App().run()
