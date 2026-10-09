#!/usr/bin/env python3
"""m2res layout OSD — пилюля «RU / EN» по центру внизу при смене раскладки (SUPER+SPACE).
Фоновый процесс: слушает сокет событий Hyprland (activelayout), клавиатуру и мышь не трогает.
Запуск: m2res-layout daemon"""
import sys, os, socket, threading, time, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import ST  # noqa: E402
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

FONT = ST.font
ACC = (0.690, 0.835, 0.0)
W, H = 520, 190
HOLD = 1.25
NAMES = {"russian": ("RU", "РУССКАЯ"), "english (us)": ("EN", "ENGLISH · US"), "english": ("EN", "ENGLISH")}


def short(name):
    k = name.strip().lower()
    if k in NAMES: return NAMES[k]
    return (name.strip()[:2].upper() or "??", name.strip().upper()[:18])


def events():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    path = f"{os.environ.get('XDG_RUNTIME_DIR', '/run/user/1000')}/hypr/{sig}/.socket2.sock"
    while True:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.connect(path); buf = b""
            while True:
                d = s.recv(4096)
                if not d: break
                buf += d
                while b"\n" in buf:
                    ln, buf = buf.split(b"\n", 1); yield ln.decode("utf-8", "replace")
        except Exception:
            time.sleep(1.0)


class Osd(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY); LS.set_namespace(self, "m2res-layout")
        LS.set_anchor(self, LS.Edge.BOTTOM, True); LS.set_margin(self, LS.Edge.BOTTOM, 90)
        LS.set_exclusive_zone(self, -1); LS.set_keyboard_mode(self, LS.KeyboardMode.NONE)
        self.set_default_size(W, H)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.a = Gtk.DrawingArea(); self.a.set_draw_func(self.draw); self.set_child(self.a)
        self.code, self.cap = "EN", ""
        self.t_show = -10.0; self.pulse = 0.0
        self.last_name, self.last_t = None, 0.0
        self.connect("map", lambda *_: self.get_surface() and self.get_surface().set_input_region(cairo.Region()))
        self.a.add_tick_callback(self.tick)
        threading.Thread(target=self.listen, daemon=True).start()

    def listen(self):
        for ln in events():
            if not ln.startswith("activelayout>>"): continue
            name = ln.split(">>", 1)[1].split(",", 1)[-1]
            now = time.monotonic()
            if name == self.last_name and now - self.last_t < 0.3: continue      # дубль от второй клавиатуры
            self.last_name, self.last_t = name, now
            GLib.idle_add(self.show, name)

    def show(self, name):
        self.code, self.cap = short(name); self.t_show = time.monotonic(); return False

    def phase(self):
        t = time.monotonic() - self.t_show
        if t < 0: return 0.0, 0.0
        if t < 0.28:   # въезд: пружина
            k = t / 0.28; return min(1.0, k * 1.0), 1 + 0.11 * math.sin(k * math.pi) * (1 - k)
        if t < 0.28 + HOLD: return 1.0, 1.0
        k = (t - 0.28 - HOLD) / 0.22
        return max(0.0, 1.0 - k), 1.0

    def tick(self, *_):
        a, _s = self.phase()
        if a > 0 or self.pulse > 0: self.a.queue_draw()
        self.pulse = a
        return True

    def draw(self, _a, cr, w, h):
        al, sc = self.phase()
        if al <= 0.001: return
        t = time.monotonic() - self.t_show
        pw, ph = 330 * sc, 120 * sc
        cx, cy = w / 2, h / 2 + (1 - al) * 14
        x, y = cx - pw / 2, cy - ph / 2; r = ph / 2

        def pill(pad=0):
            cr.new_sub_path(); cr.arc(x + r, y + r, r + pad, math.pi / 2, math.pi * 1.5)
            cr.arc(x + pw - r, y + r, r + pad, -math.pi / 2, math.pi / 2); cr.close_path()
        for i, aa in ((14, 0.05), (9, 0.08), (5, 0.12)):          # свечение
            cr.set_source_rgba(*ACC, aa * al); pill(i); cr.fill()
        pill(); cr.set_source_rgba(*ST.bg[:3], 0.96 * al); cr.fill_preserve()
        cr.set_source_rgba(*ACC, 0.9 * al); cr.set_line_width(3); cr.stroke()
        # бегущий блик по рамке в момент переключения
        if t < 0.55:
            k = t / 0.55; cr.save(); pill(); cr.clip()
            g = cairo.LinearGradient(x + (pw + 120) * k - 120, 0, x + (pw + 120) * k, 0)
            g.add_color_stop_rgba(0, 1, 1, 1, 0); g.add_color_stop_rgba(0.5, 0.83, 1.0, 0.1, 0.45 * al); g.add_color_stop_rgba(1, 1, 1, 1, 0)
            cr.set_source(g); cr.rectangle(x, y, pw, ph); cr.fill(); cr.restore()
        # значок и код
        lay = PangoCairo.create_layout(cr); lay.set_font_description(Pango.FontDescription(f"{FONT} Bold {int(52 * sc)}"))
        lay.set_text(self.code, -1); tw, th = lay.get_pixel_size()
        cr.set_source_rgba(0.93, 0.93, 0.90, al); cr.move_to(x + 36 * sc, cy - th / 2 - 5); PangoCairo.show_layout(cr, lay)
        cap = PangoCairo.create_layout(cr); cap.set_font_description(Pango.FontDescription(f"{FONT} {int(15 * sc)}"))
        cap.set_text(self.cap, -1); cw, chh = cap.get_pixel_size()
        cr.set_source_rgba(*ACC, al); cr.move_to(x + pw - 30 * sc - cw, cy - chh / 2); PangoCairo.show_layout(cr, cap)
        # индикатор: две точки под подписью
        for i, c in enumerate(("RU", "EN")):
            on = c == self.code
            cr.set_source_rgba(*(ACC if on else ST.n(0.45, 0.45, 0.41)), (1 if on else 0.6) * al)
            cr.arc(x + pw - 30 * sc - cw + 5 + i * 14, cy + chh / 2 + 13 * sc, 4.0 * sc, 0, 6.3); cr.fill()


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.layoutosd")
    def do_activate(self):
        self.hold(); Osd(self).present()


if __name__ == "__main__":
    App().run()
