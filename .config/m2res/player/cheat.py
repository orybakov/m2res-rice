#!/usr/bin/env python3
"""m2res cheat — шпаргалка по горячим клавишам (SUPER+F1). Список строит m2res-binds из binds.lua / hypr-m2res.lua,
дубликаты подсвечиваются красным. Печатай — поиск по клавишам и действию; ↑/↓/колесо — прокрутка; Esc — очистить поиск / закрыть."""
import sys, os, json, math, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from style import ST  # noqa: E402
FONT = ST.font
PW, PAD, MARG = 1360, 28, 40
COLW, KEYW, ROW, ROWS = 630, 232, 30, 16
HDR, SRCH = 78, 52
PH = HDR + SRCH + ROWS * ROW + 58
T_OPEN, T_CLOSE = 0.28, 0.14
DIM, TXT, RED = ST.n(0.55, 0.56, 0.52), ST.n(0.92, 0.92, 0.88), (1.0, 0.36, 0.48)
PRETTY = {"SUPER": "Super", "CTRL": "Ctrl", "ALT": "Alt", "SHIFT": "Shift", "return": "Enter", "Escape": "Esc", "Print": "PrtSc", "Tab": "Tab",
          "left": "←", "right": "→", "up": "↑", "down": "↓"}


def ease_out_quart(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 4


def accent():
    try:
        c = json.load(open(os.path.join(HERE, "colors.json")))["accent"].lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return (0.69, 0.84, 0.0)


def load_binds():
    try:
        out = subprocess.run([os.path.expanduser("~/.config/m2res/scripts/m2res-binds"), "json"], capture_output=True, text=True, timeout=5).stdout
        items = json.loads(out)
    except Exception:
        items = []
    for it in items:
        it["pk"] = " + ".join(PRETTY.get(p, p) for p in it["keys"].split("+"))
        it["hay"] = (it["pk"] + " " + it["keys"] + " " + it["action"]).lower()
    return items


class Cheat(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.acc = accent(); self.items = load_binds(); self.view = list(self.items); self.query = ""; self.scroll = 0
        self.t0 = None; self.close_at = None; self.win_w, self.win_h = PW + 2 * MARG, PH + 2 * MARG; self._pc = None
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY); LS.set_namespace(self, "m2res-cheat")
        LS.set_exclusive_zone(self, -1); LS.set_keyboard_mode(self, LS.KeyboardMode.EXCLUSIVE)
        mon = os.environ.get("M2_MON")
        if mon:
            for m in Gdk.Display.get_default().get_monitors():
                if m.get_connector() == mon: LS.set_monitor(self, m)
        self.set_default_size(self.win_w, self.win_h)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw); self.set_child(self.area)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); self.add_controller(kc)
        g = Gtk.GestureClick(); g.connect("pressed", self.on_click); self.area.add_controller(g)
        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        sc.connect("scroll", self.on_scroll); self.area.add_controller(sc)
        self.connect("map", lambda *_: setattr(self, "t0", time.monotonic()))
        self.area.add_tick_callback(self.tick)

    # ---- данные ----
    def refilter(self):
        q = self.query.lower().strip()
        self.view = [i for i in self.items if all(w in i["hay"] for w in q.split())] if q else list(self.items)
        self.scroll = 0; self._pc = None

    def maxscroll(self): return max(0, math.ceil(len(self.view) / 2) - ROWS)

    # ---- ввод ----
    def begin_close(self):
        if not self.close_at: self.close_at = time.monotonic()

    def on_key(self, _c, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            if self.query: self.query = ""; self.refilter()
            else: self.begin_close()
            return True
        if keyval == Gdk.KEY_BackSpace: self.query = self.query[:-1]; self.refilter(); return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Page_Down): self.scroll = min(self.maxscroll(), self.scroll + (1 if keyval == Gdk.KEY_Down else ROWS)); return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Page_Up): self.scroll = max(0, self.scroll - (1 if keyval == Gdk.KEY_Up else ROWS)); return True
        u = Gdk.keyval_to_unicode(keyval)
        if u >= 32 and not (state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK)):
            self.query += chr(u); self.refilter()
        return True

    def on_scroll(self, c, dx, dy):
        self.scroll = max(0, min(self.maxscroll(), self.scroll + int(dy) * 2)); return True

    def on_click(self, g, n, x, y):
        if not (MARG <= x <= MARG + PW and MARG <= y <= MARG + PH): self.begin_close()

    def tick(self, _w, clock):
        if self.t0 is None: return True
        now = time.monotonic()
        if self.close_at and now - self.close_at > T_CLOSE: self.get_application().quit(); return False
        self.area.queue_draw(); return True

    # ---- рисование ----
    def rr(self, cr, x, y, w, h, r):
        ST.path(cr, x, y, w, h, r)

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
                surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w), int(h)); self.panel(cairo.Context(surf), now); self._pc = surf
            cr.set_source_surface(self._pc, 0, 0); cr.paint_with_alpha(al)
        else:
            cr.push_group(); self.panel(cr, now); cr.pop_group_to_source(); cr.paint_with_alpha(al)

    def panel(self, cr, now):
        A = self.acc; x0 = y0 = MARG
        ST.frame(cr, x0, y0, PW, PH, A, 30)
        dups = sum(1 for i in self.items if i.get("dup"))
        self.text(cr, "BINDS", 30, A, x0 + PAD, y0 + 42, bold=True)
        info = f"{len(self.items)} биндов" + (f" · дублей: {dups}" if dups else " · дублей нет")
        self.text(cr, info, 14, RED if dups else DIM, x0 + PW - PAD, y0 + 44, anchor="r")
        cr.set_source_rgba(*A, 0.35); cr.set_line_width(1.5); cr.move_to(x0 + PAD, y0 + HDR - 6); cr.line_to(x0 + PW - PAD, y0 + HDR - 6); cr.stroke()
        # поиск
        sy = y0 + HDR + 2
        self.rr(cr, x0 + PAD, sy, PW - 2 * PAD, 40, 14); cr.set_source_rgba(*ST.n(1, 1, 1, 0.04)); cr.fill_preserve()
        cr.set_source_rgba(*A, 0.35); cr.set_line_width(1.5); cr.stroke()
        if self.query:
            wq = self.text(cr, self.query, 17, TXT, x0 + PAD + 16, sy + 21)
        else:
            wq = 0; self.text(cr, "печатай для поиска…", 16, DIM, x0 + PAD + 16, sy + 21)
        if int(now * 2) % 2 == 0: cr.set_source_rgba(*A, 0.9); cr.rectangle(x0 + PAD + 18 + wq, sy + 9, 2.5, 22); cr.fill()
        # список: два столбца, заполняются сверху вниз
        ly = y0 + HDR + SRCH + 6; half = math.ceil(len(self.view) / 2)
        if not self.view: self.text(cr, "ничего не найдено", 18, DIM, x0 + PW / 2, ly + 120, anchor="c")
        for n, it in enumerate(self.view):
            col, r = divmod(n, half) if half > ROWS or True else (0, n)
            r -= self.scroll
            if r < 0 or r >= ROWS: continue
            cx = x0 + PAD + col * (COLW + 2 * PAD - 8); cy = ly + r * ROW + ROW / 2
            if it.get("dup"):
                self.rr(cr, cx - 6, cy - ROW / 2 + 2, COLW, ROW - 4, 8); cr.set_source_rgba(*RED, 0.12); cr.fill()
            self.text(cr, it["pk"], 14, RED if it.get("dup") else A, cx, cy, bold=True, width=KEYW)
            self.text(cr, it["action"], 14, TXT, cx + KEYW + 14, cy, width=COLW - KEYW - 24)
        # разделитель столбцов и полоса прокрутки
        cr.set_source_rgba(*A, 0.15); cr.set_line_width(1); mx = x0 + PW / 2; cr.move_to(mx, ly + 4); cr.line_to(mx, ly + ROWS * ROW - 4); cr.stroke()
        if self.maxscroll() > 0:
            th = ROWS * ROW; bh = max(30, th * ROWS / half); by = ly + (th - bh) * self.scroll / self.maxscroll()
            self.rr(cr, x0 + PW - 14, by, 4, bh, 2); cr.set_source_rgba(*A, 0.5); cr.fill()
        self.text(cr, "печатай — поиск · ↑/↓/колесо — прокрутка · Esc — назад / закрыть", 13, DIM, x0 + PW / 2, y0 + PH - 26, anchor="c")


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.cheat")
    def do_activate(self): Cheat(self).present()


if __name__ == "__main__":
    App().run()
