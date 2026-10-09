#!/usr/bin/env python3
"""m2res idle-dim — плавное затемнение экрана перед блокировкой (запускает hypridle).
Окно не принимает ввод и клавиатуру; гасится, когда hypridle убивает процесс (on-resume).
Аргумент: длительность затемнения в секундах (по умолчанию 45), финальная непрозрачность 0.78."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gtk4LayerShell as LS  # noqa: E402

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
MAXA = 0.78


class Dim(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY); LS.set_namespace(self, "m2res-idledim")
        LS.set_exclusive_zone(self, -1); LS.set_keyboard_mode(self, LS.KeyboardMode.NONE)
        for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT): LS.set_anchor(self, e, True)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.a = Gtk.DrawingArea(); self.a.set_draw_func(self.draw); self.set_child(self.a)
        self.t0 = time.monotonic(); self.last = -1.0
        self.connect("map", self.on_map)
        self.a.add_tick_callback(self.tick)

    def on_map(self, *_):
        s = self.get_surface()
        if s: s.set_input_region(cairo.Region())          # пустая область ввода: клики и курсор проходят насквозь

    def alpha(self):
        k = min(1.0, (time.monotonic() - self.t0) / DUR)
        return MAXA * k * k

    def tick(self, *_):
        a = self.alpha()
        if abs(a - self.last) > 0.004: self.last = a; self.a.queue_draw()      # ~не чаще, чем меняется картинка
        return True

    def draw(self, _a, cr, w, h):
        cr.set_source_rgba(0.02, 0.025, 0.01, self.alpha()); cr.paint()


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.idledim")
    def do_activate(self): Dim(self).present()


if __name__ == "__main__":
    App().run()
