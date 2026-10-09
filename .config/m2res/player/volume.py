#!/usr/bin/env python3
"""m2res volume — ползунок громкости у ПРАВОГО края экрана (стиль индикатора из райса).

Работает как фоновый процесс:
  * невидимая полоска в 2 px у правого края ловит курсор: упёрся в край — ползунок выезжает;
  * пока курсор на ползунке он остаётся; ушёл — через 0.5 с сужается в риску и уезжает;
  * интерактивность: тянуть пилюлю мышью, колесо = ±5%, клик по значку = mute;
  * SIGUSR1 (из m2res-volume up/down/mute/show) показывает его на ~1.6 с.
Запуск: m2res-volume daemon"""
import sys, os, signal, subprocess, time, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import ST  # noqa: E402
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

FONT = ST.font
SINK = "@DEFAULT_AUDIO_SINK@"
HOLD, LEAVE_DELAY = 1.6, 0.5
EDGE = 2                      # ширина горячей полосы, px
W = 150                       # ширина окна (запас под перелёт пружины)
HW = 104                      # видимая ширина подставки
PH = 380                      # высота подставки
PILL_W, PILL_H = 40, 250
REST_X = W - HW


def read_volume():
    try:
        o = subprocess.run(["wpctl", "get-volume", SINK], capture_output=True, text=True, timeout=1).stdout
        return float(o.split()[1]), "MUTED" in o
    except Exception:
        return 0.0, False


def wpctl(*a):
    subprocess.Popen(["wpctl", *a], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Vol(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY)
        for e in (LS.Edge.RIGHT, LS.Edge.TOP, LS.Edge.BOTTOM): LS.set_anchor(self, e, True)
        LS.set_exclusive_zone(self, -1)
        LS.set_namespace(self, "m2res-volume"); LS.set_keyboard_mode(self, LS.KeyboardMode.NONE)
        self.set_default_size(W, 100)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw); self.set_child(self.area)

        self.vol, self.muted = read_volume(); self.shown_v = self.vol
        self.p, self.pv = 0.0, 0.0          # положение выезда (0 спрятан … 1 на месте) и скорость
        self.wf = 1.0                       # ширина пилюли (сужение при уходе)
        self.want = False                   # хотим показывать
        self.hover = False; self.drag = False
        self.hide_at = 0.0; self.last = time.monotonic()
        self.region_mode = None; self.size = (W, 1)
        self.hot = False

        mo = Gtk.EventControllerMotion()
        mo.connect("enter", self.on_enter); mo.connect("leave", self.on_leave)
        self.area.add_controller(mo)
        dr = Gtk.GestureDrag(); dr.set_button(1)
        dr.connect("drag-begin", self.on_drag_begin); dr.connect("drag-update", self.on_drag_update)
        dr.connect("drag-end", lambda *_: setattr(self, "drag", False))
        self.area.add_controller(dr)
        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        sc.connect("scroll", self.on_scroll); self.area.add_controller(sc)

        self.area.add_tick_callback(self.tick)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.on_ping)
        GLib.timeout_add(150, self.poll)

    # ---------- геометрия ----------
    def oy(self): return (self.size[1] - PH) / 2
    def pill_box(self):
        oy = self.oy(); return REST_X + 32, oy + 60, PILL_W, PILL_H     # x, y, w, h
    def icon_c(self): return REST_X + 32 + PILL_W / 2, self.oy() + 345

    # ---------- ввод ----------
    def on_enter(self, *_):
        self.hover = True; self.want = True; self.hide_at = 0

    def on_leave(self, *_):
        self.hover = False; self.hide_at = time.monotonic() + LEAVE_DELAY

    def set_vol(self, v):
        v = max(0.0, min(1.0, v)); self.vol = v; self.muted = False
        wpctl("set-mute", SINK, "0"); wpctl("set-volume", "-l", "1.0", SINK, f"{v:.3f}")

    def set_from_y(self, y):
        _, py, _, ph = self.pill_box(); self.set_vol((py + ph - y) / ph)

    def on_drag_begin(self, g, x, y):
        ix, iy = self.icon_c()
        if abs(x - ix) < 24 and abs(y - iy) < 24:           # клик по значку = mute
            self.muted = not self.muted; wpctl("set-mute", SINK, "toggle"); return
        if x < REST_X: return
        self.drag = True; self.drag_y0 = y; self.set_from_y(y)

    def on_drag_update(self, g, dx, dy):
        if self.drag: self.set_from_y(self.drag_y0 + dy)

    def on_scroll(self, c, dx, dy):
        self.set_vol(self.vol + (-0.05 if dy > 0 else 0.05)); self.hide_at = 0 if self.hover else time.monotonic() + HOLD
        return True

    def on_ping(self):
        self.vol, self.muted = read_volume()
        self.want = True; self.hide_at = time.monotonic() + HOLD
        return True

    def poll(self):
        if not self.drag: self.vol, self.muted = read_volume()
        return True

    # ---------- анимация ----------
    def tick(self, *_):
        now = time.monotonic(); dt = min(0.05, now - self.last); self.last = now
        if self.want and not self.hover and not self.drag and self.hide_at and now > self.hide_at:
            self.want = False
        tv = 0.0 if self.muted else self.vol
        self.shown_v += (tv - self.shown_v) * min(1.0, dt * 14)
        if self.want:
            self.wf += (1.0 - self.wf) * min(1.0, dt * 18)
            k, c = 420.0, 20.0                              # недодемпфированная пружина → «перелёт»
            self.pv += (k * (1.0 - self.p) - c * self.pv) * dt; self.p += self.pv * dt
        else:
            if self.wf > 0.17:
                self.wf = max(0.15, self.wf - dt * 5.0)      # сначала сужаемся
            else:
                self.pv = min(self.pv, 0.0) - dt * 14.0      # потом уезжаем с ускорением
                self.p = max(0.0, self.p + self.pv * dt)
                if self.p <= 0.0: self.pv = 0.0
        self.set_region(self.p > 0.02 and self.want or self.hover)
        self.area.queue_draw()
        return True

    def set_region(self, panel):
        mode = "panel" if panel else "edge"
        if mode == self.region_mode: return
        w, h = self.size
        surf = self.get_surface()
        if surf is None or h < 100: return
        if mode == "panel":
            r = cairo.RectangleInt(int(REST_X - 12), int(self.oy()), int(W - REST_X + 12), PH)
        else:
            r = cairo.RectangleInt(w - EDGE, 0, EDGE, h)
        try:
            surf.set_input_region(cairo.Region(r)); self.region_mode = mode
        except Exception as e:
            print("input region:", e, file=sys.stderr)

    # ---------- рисование ----------
    def rrect(self, cr, x, y, w, h, r):
        ST.path(cr, x, y, w, h, r)

    def glyph(self, cr, s, cx, cy, size, color):
        lay = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription(FONT); fd.set_absolute_size(size * Pango.SCALE)
        lay.set_font_description(fd); lay.set_text(s, -1); w, h = lay.get_pixel_size()
        cr.move_to(cx - w / 2, cy - h / 2); cr.set_source_rgb(*color); PangoCairo.show_layout(cr, lay)

    def draw(self, _a, cr, w, h):
        self.size = (w, h)
        if self.p <= 0.001: return
        oy = self.oy(); off = (1 - self.p) * (HW + 40)
        cr.translate(off, 0)
        self.rrect(cr, REST_X, oy, HW + 80, PH, 28); cr.set_source_rgb(*ST.bg[:3]); cr.fill()
        px, py, pw0, ph = self.pill_box(); pw = pw0 * self.wf; px += (pw0 - pw) / 2
        self.rrect(cr, px, py, pw, ph, pw / 2); cr.set_source_rgb(*ST.n(0.20, 0.20, 0.22)); cr.fill()
        fh = ph * max(0.0, min(1.0, self.shown_v))
        if fh > 0 and pw > 3:
            cr.save(); self.rrect(cr, px, py, pw, ph, pw / 2); cr.clip()
            cr.rectangle(px, py + ph - fh, pw, fh); cr.set_source_rgb(*ST.n(1, 1, 1)); cr.fill(); cr.restore()
        if self.wf > 0.6:
            cx = px + pw / 2
            red = (1, 0.36, 0.48)
            self.glyph(cr, "mute" if self.muted else f"{round(self.vol * 100)}", cx, oy + 32, 15, red if self.muted else ST.n(1, 1, 1))
            icon = "󰖁" if self.muted else ("󰕿" if self.vol < 0.34 else ("󰖀" if self.vol < 0.67 else "󰕾"))
            self.glyph(cr, icon, cx, oy + 345, 26, red if self.muted else ST.n(0.92, 0.92, 0.92))


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.volume")
    def do_activate(self): Vol(self).present()


if __name__ == "__main__":
    App().run()
