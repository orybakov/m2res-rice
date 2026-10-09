#!/usr/bin/env python3
"""m2res overview — обзор рабочих столов (SUPER+Tab). Карточки столов с мини-картой окон (из hyprctl clients).
Клик по карточке — перейти на стол, клик по окну — сфокусировать его · 1–9, 0 — стол N · ←/→/↑/↓ — выбор · Enter — перейти · Esc — закрыть."""
import sys, os, json, math, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "CaskaydiaMono Nerd Font Mono"
MARG, PAD, GAP, PER_ROW = 40, 28, 22, 5
T_OPEN, T_CLOSE = 0.26, 0.13
DIM, TXT = (0.55, 0.56, 0.52), (0.92, 0.92, 0.88)


def ease_out_quart(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 4


def accent():
    try:
        c = json.load(open(os.path.join(HERE, "colors.json")))["accent"].lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return (0.69, 0.84, 0.0)


def hj(what):
    try: return json.loads(subprocess.run(["hyprctl", "-j", what], capture_output=True, text=True, timeout=3).stdout)
    except Exception: return []


def bg(*a): subprocess.Popen(list(a), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


class Over(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.acc = accent(); self.t0 = None; self.close_at = None; self._pc = None; self.hover = None
        mons = hj("monitors"); name = os.environ.get("M2_MON")
        mon = next((m for m in mons if m["name"] == name), next((m for m in mons if m.get("focused")), mons[0] if mons else None))
        self.mon = mon; self.mx, self.my = mon["x"], mon["y"]
        sc = mon.get("scale", 1) or 1; self.mw, self.mh = mon["width"] / sc, mon["height"] / sc
        self.active = (mon.get("activeWorkspace") or {}).get("id", 1)
        clients = [c for c in hj("clients") if c.get("mapped") and c["workspace"]["id"] > 0 and c.get("monitor") == mon["id"]]
        ids = set(range(1, 6)) | {c["workspace"]["id"] for c in clients} | {self.active}
        self.ws = sorted(ids)
        self.wins = {i: [c for c in clients if c["workspace"]["id"] == i] for i in self.ws}
        fa = (hj("activewindow") or {}).get("address") if isinstance(hj("activewindow"), dict) else None
        self.focus_addr = fa
        n = len(self.ws); self.cols = min(PER_ROW, n); self.rows = math.ceil(n / self.cols)
        self.CW = min(430.0, (self.mw * 0.9 - 2 * PAD - (self.cols - 1) * GAP) / self.cols); self.CH = self.CW * self.mh / self.mw
        self.LBL = 34
        self.PW = int(2 * PAD + self.cols * self.CW + (self.cols - 1) * GAP)
        self.PH = int(2 * PAD + 44 + self.rows * (self.CH + self.LBL) + (self.rows - 1) * GAP + 26)
        self.win_w, self.win_h = self.PW + 2 * MARG, self.PH + 2 * MARG
        self.sel = self.ws.index(self.active)
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY); LS.set_namespace(self, "m2res-overview")
        LS.set_exclusive_zone(self, -1); LS.set_keyboard_mode(self, LS.KeyboardMode.EXCLUSIVE)
        for m in Gdk.Display.get_default().get_monitors():
            if m.get_connector() == mon["name"]: LS.set_monitor(self, m)
        self.set_default_size(self.win_w, self.win_h)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw); self.set_child(self.area)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); self.add_controller(kc)
        mo = Gtk.EventControllerMotion(); mo.connect("motion", self.on_motion); self.area.add_controller(mo)
        g = Gtk.GestureClick(); g.connect("pressed", self.on_click); self.area.add_controller(g)
        self.connect("map", lambda *_: setattr(self, "t0", time.monotonic()))
        self.area.add_tick_callback(self.tick)

    # ---- геометрия ----
    def card(self, i):
        r, c = divmod(i, self.cols)
        return MARG + PAD + c * (self.CW + GAP), MARG + PAD + 44 + r * (self.CH + self.LBL + GAP)

    def hit(self, x, y):
        for i, w in enumerate(self.ws):
            cx, cy = self.card(i)
            if cx <= x <= cx + self.CW and cy <= y <= cy + self.CH + self.LBL:
                k = self.CW / self.mw
                for c in reversed(self.wins[w]):
                    rx, ry = cx + (c["at"][0] - self.mx) * k, cy + (c["at"][1] - self.my) * k
                    if rx <= x <= rx + c["size"][0] * k and ry <= y <= ry + c["size"][1] * k: return i, c
                return i, None
        return None, None

    # ---- действия ----
    def go(self, i, c=None):
        w = self.ws[i]
        code = "hl.dispatch(hl.dsp.focus({ workspace = '%d' }))" % w
        if c: code += "; hl.dispatch(hl.dsp.focus({ window = 'address:%s' }))" % c["address"]
        bg("hyprctl", "eval", code); self.begin_close()

    def begin_close(self):
        if not self.close_at: self.close_at = time.monotonic()

    def on_key(self, _c, keyval, keycode, state):
        n = len(self.ws)
        if keyval == Gdk.KEY_Escape: self.begin_close(); return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter): self.go(self.sel); return True
        if keyval == Gdk.KEY_Right: self.sel = (self.sel + 1) % n; return True
        if keyval == Gdk.KEY_Left: self.sel = (self.sel - 1) % n; return True
        if keyval == Gdk.KEY_Down: self.sel = min(n - 1, self.sel + self.cols); return True
        if keyval == Gdk.KEY_Up: self.sel = max(0, self.sel - self.cols); return True
        ch = chr(keyval) if 32 < keyval < 127 else ""
        if ch.isdigit():
            want = 10 if ch == "0" else int(ch)
            if want in self.ws: self.go(self.ws.index(want))
        return True

    def on_motion(self, _c, x, y):
        i, c = self.hit(x, y); self.hover = (i, c["address"] if c else None) if i is not None else None
        if i is not None: self.sel = i

    def on_click(self, g, n, x, y):
        i, c = self.hit(x, y)
        if i is None:
            if not (MARG <= x <= MARG + self.PW and MARG <= y <= MARG + self.PH): self.begin_close()
        else: self.go(i, c)

    def tick(self, _w, clock):
        if self.t0 is None: return True
        now = time.monotonic()
        if self.close_at and now - self.close_at > T_CLOSE: self.get_application().quit(); return False
        self.area.queue_draw(); return True

    # ---- рисование ----
    def rr(self, cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2); cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi); cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi); cr.close_path()

    def text(self, cr, s, size, color, x, y, bold=False, anchor="l", width=None, alpha=1.0):
        lay = PangoCairo.create_layout(cr)
        lay.set_font_description(Pango.FontDescription(f"{FONT} {'Bold ' if bold else ''}{size}"))
        if width: lay.set_width(int(width * Pango.SCALE)); lay.set_ellipsize(Pango.EllipsizeMode.END)
        lay.set_text(s, -1); w, h = lay.get_pixel_size()
        ox = x - w if anchor == "r" else (x - w / 2 if anchor == "c" else x)
        cr.move_to(ox, y - h / 2); cr.set_source_rgba(*color, alpha); PangoCairo.show_layout(cr, lay); return w

    def draw(self, _a, cr, w, h):
        if self.t0 is None: return
        now = time.monotonic(); t = now - self.t0
        if self.close_at:
            k = max(0.0, min(1.0, (now - self.close_at) / T_CLOSE)); sc = 1 - 0.03 * k; al = 1 - k
        else:
            k = ease_out_quart(t / T_OPEN); sc = 0.96 + 0.04 * k; al = max(0.0, min(1.0, t / (T_OPEN * 0.6)))
        cr.translate(self.win_w / 2, self.win_h / 2); cr.scale(sc, sc); cr.translate(-self.win_w / 2, -self.win_h / 2)
        if self.close_at or t < T_OPEN + 0.05:
            if self._pc is None:
                surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w), int(h)); self.panel(cairo.Context(surf)); self._pc = surf
            cr.set_source_surface(self._pc, 0, 0); cr.paint_with_alpha(al)
        else:
            cr.push_group(); self.panel(cr); cr.pop_group_to_source(); cr.paint_with_alpha(al)

    def panel(self, cr):
        A = self.acc; x0 = y0 = MARG
        for i, a in ((18, 0.04), (12, 0.06), (6, 0.09)):
            cr.set_source_rgba(*A, a); self.rr(cr, x0 - i, y0 - i, self.PW + 2 * i, self.PH + 2 * i, 30 + i); cr.fill()
        self.rr(cr, x0, y0, self.PW, self.PH, 30); cr.set_source_rgba(0.039, 0.039, 0.039, 0.97); cr.fill_preserve()
        cr.set_source_rgba(*A, 0.55); cr.set_line_width(2.5); cr.stroke()
        self.text(cr, "WORKSPACES", 22, A, x0 + PAD, y0 + PAD + 8, bold=True)
        self.text(cr, "клик · 1–9, 0 · ←→↑↓ · Enter · Esc", 13, DIM, x0 + self.PW - PAD, y0 + PAD + 10, anchor="r")
        k = self.CW / self.mw
        for i, wid in enumerate(self.ws):
            cx, cy = self.card(i); cur = wid == self.active; sel = i == self.sel; n = len(self.wins[wid])
            if sel:
                self.rr(cr, cx - 8, cy - 8, self.CW + 16, self.CH + self.LBL + 14, 14); cr.set_source_rgba(*A, 0.10); cr.fill_preserve()
                cr.set_source_rgba(*A, 0.9); cr.set_line_width(2); cr.stroke()
            self.rr(cr, cx, cy, self.CW, self.CH, 8); cr.set_source_rgba(1, 1, 1, 0.045 if n else 0.02); cr.fill_preserve()
            cr.set_source_rgba(*A, 0.55 if cur else 0.18); cr.set_line_width(2 if cur else 1); cr.stroke()
            if not n: self.text(cr, "пусто", 13, DIM, cx + self.CW / 2, cy + self.CH / 2, anchor="c", alpha=0.7)
            for c in self.wins[wid]:
                rx, ry = cx + (c["at"][0] - self.mx) * k, cy + (c["at"][1] - self.my) * k
                rw, rh = max(6, c["size"][0] * k), max(6, c["size"][1] * k)
                foc = c["address"] == self.focus_addr; hov = self.hover and self.hover[1] == c["address"]
                self.rr(cr, rx + 1, ry + 1, rw - 2, rh - 2, 4); cr.set_source_rgba(*A, 0.30 if hov else (0.20 if foc else 0.10)); cr.fill_preserve()
                cr.set_source_rgba(*A, 0.95 if foc else 0.5); cr.set_line_width(1.6 if foc else 1); cr.stroke()
                if rw > 60 and rh > 24:
                    cls = (c.get("class") or "?").split(".")[-1]
                    self.text(cr, cls, 11, TXT, rx + 8, ry + 14, bold=True, width=rw - 14)
                    if rh > 44 and c.get("title"): self.text(cr, c["title"], 9, DIM, rx + 8, ry + 29, width=rw - 14)
            self.text(cr, str(wid), 15, A if cur else TXT, cx + 4, cy + self.CH + 18, bold=True)
            sub = ("активный · " if cur else "") + (f"{n} окон" if n else "пусто") if n != 1 else ("активный · " if cur else "") + "1 окно"
            self.text(cr, sub, 12, DIM, cx + 30, cy + self.CH + 19)


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.overview")
    def do_activate(self): Over(self).present()


if __name__ == "__main__":
    App().run()
