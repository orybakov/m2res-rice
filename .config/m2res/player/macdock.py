#!/usr/bin/env python3
"""m2res macdock — нижний док в стиле macOS: стеклянная капсула по центру, иконки закреплённых приложений,
точка под запущенными. Список берётся из ~/.config/m2res/macdock.json (его пишет m2res-rice из ключа "macdock" райса).
Запуск и остановку делает m2res-rice; вручную: python3 macdock.py."""
import os, sys, json, subprocess, warnings
warnings.filterwarnings("ignore")
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, GLib, Gio, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
CFG = os.path.join(M2, "macdock.json")
CSS = """
window.macdock-win { background: transparent; }
box.macdock { background: rgba(255,255,255,0.58); border: 1px solid rgba(255,255,255,0.75);
  border-radius: 22px; padding: 6px 12px 3px 12px; box-shadow: 0 10px 28px rgba(0,0,0,0.20); }
button.mac-app { background: transparent; border: none; box-shadow: none; padding: 3px 5px; min-height: 0; border-radius: 14px; }
button.mac-app:hover { background: rgba(0,0,0,0.07); }
button.mac-app:active { background: rgba(0,0,0,0.12); }
label.mac-dot { color: #3a3a3c; font-size: 8px; margin-top: 1px; }
"""


def load_cfg():
    c = {"apps": [], "icon": 52, "bottom": 10}
    try: c.update(json.load(open(CFG)))
    except Exception: pass
    return c


def running():
    try:
        out = subprocess.run(["hyprctl", "-j", "clients"], capture_output=True, text=True, timeout=2).stdout
        return {x.get("class", "").lower() for x in json.loads(out)}
    except Exception:
        return set()


def spawn(cmd):
    subprocess.Popen(["setsid", "-f", "bash", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def gicon(desktop_id):
    info = Gio.DesktopAppInfo.new(desktop_id + ".desktop") if desktop_id else None
    return info.get_icon() if info else None


OFF = 120          # на сколько px панель уходит вниз, когда скрыта (высота капсулы + запас)
ANIM_MS = 16       # шаг анимации выезда


class Dock(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="m2res.macdock")
        self.dots = []
        self.p = 0.0; self.target = 0.0; self.in_dock = False; self.in_edge = False
        self.hide_id = None; self.anim_id = None; self.bottom = 10; self.win = None; self.edge = None

    def do_activate(self):
        c = load_cfg()
        win = Gtk.ApplicationWindow(application=self)
        win.add_css_class("macdock-win"); win.set_decorated(False); win.set_focusable(False)
        LS.init_for_window(win)
        LS.set_layer(win, LS.Layer.TOP)
        LS.set_anchor(win, LS.Edge.BOTTOM, True)
        self.bottom = int(c.get("bottom", 10)); self.cfg = c
        LS.set_margin(win, LS.Edge.BOTTOM, self.bottom)
        LS.set_exclusive_zone(win, 0)
        LS.set_keyboard_mode(win, LS.KeyboardMode.NONE)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6); box.add_css_class("macdock")
        box.set_halign(Gtk.Align.CENTER)
        size = int(c.get("icon", 52))
        self.dots = []
        for a in c.get("apps", []):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            btn = Gtk.Button(); btn.add_css_class("mac-app"); btn.set_tooltip_text(a.get("name", ""))
            ic = gicon(a.get("id", ""))
            img = Gtk.Image.new_from_gicon(ic) if ic else Gtk.Image.new_from_icon_name("application-x-executable")
            img.set_pixel_size(size)
            btn.set_child(img)
            cmd = a.get("cmd", "")
            btn.connect("clicked", lambda _b, cmd=cmd: spawn(cmd) if cmd else None)
            dot = Gtk.Label(label="•"); dot.add_css_class("mac-dot")
            dot.set_opacity(0)
            col.append(btn); col.append(dot)
            box.append(col)
            self.dots.append((a.get("cls", "").lower(), dot))
        if not self.dots:
            box.append(Gtk.Label(label="нет закреплённых приложений"))
        win.set_child(box)
        prov = Gtk.CssProvider(); prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(win.get_display(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.win = win
        mo = Gtk.EventControllerMotion()
        mo.connect("enter", lambda *_: self.hover_dock(True)); mo.connect("leave", lambda *_: self.hover_dock(False))
        box.add_controller(mo)
        if c.get("autohide", True):
            self.setup_edge(c)
            LS.set_margin(win, LS.Edge.BOTTOM, self.bottom - OFF)
            win.present(); win.set_visible(False)
        else:
            win.present(); self.p = self.target = 1.0
        self.refresh()
        GLib.timeout_add(1500, self.refresh)

    def setup_edge(self, c):
        """Невидимая полоска у нижнего края: наведение на неё выдвигает док."""
        edge = int(c.get("edge", 4))
        ew = Gtk.Window(application=self); ew.set_decorated(False); ew.set_focusable(False)
        ew.set_default_size(1, edge)
        LS.init_for_window(ew); LS.set_layer(ew, LS.Layer.TOP)
        for e in (LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT): LS.set_anchor(ew, e, True)
        LS.set_exclusive_zone(ew, 0); LS.set_keyboard_mode(ew, LS.KeyboardMode.NONE)
        da = Gtk.DrawingArea(); da.set_content_height(edge)
        ew.set_child(da)
        em = Gtk.EventControllerMotion()
        em.connect("enter", lambda *_: self.hover_edge(True)); em.connect("leave", lambda *_: self.hover_edge(False))
        da.add_controller(em)
        ew.present()
        self.edge = ew

    def hover_edge(self, on):
        self.in_edge = on
        if on: self.show()
        else: self.schedule_hide()

    def hover_dock(self, on):
        self.in_dock = on
        if on:
            if self.hide_id: GLib.source_remove(self.hide_id); self.hide_id = None
        else: self.schedule_hide()

    def schedule_hide(self):
        if self.in_edge or self.in_dock or self.hide_id: return
        self.hide_id = GLib.timeout_add(int(self.cfg.get("hide_ms", 450)), self.do_hide)

    def do_hide(self):
        self.hide_id = None
        if not (self.in_edge or self.in_dock): self.animate(0.0)
        return False

    def show(self):
        if self.hide_id: GLib.source_remove(self.hide_id); self.hide_id = None
        if not self.win.get_visible(): self.win.set_visible(True); self.win.present()
        self.animate(1.0)

    def animate(self, tgt):
        self.target = tgt
        if self.anim_id is None: self.anim_id = GLib.timeout_add(ANIM_MS, self.tick)

    def tick(self):
        step = 0.18
        if self.p < self.target: self.p = min(self.target, self.p + step)
        elif self.p > self.target: self.p = max(self.target, self.p - step)
        LS.set_margin(self.win, LS.Edge.BOTTOM, int(round(self.bottom - OFF * (1 - self.p))))
        if self.p == self.target:
            self.anim_id = None
            if self.target == 0.0: self.win.set_visible(False)
            return False
        return True

    def refresh(self):
        run = running()
        for cls, dot in self.dots:
            dot.set_opacity(1.0 if cls and cls in run else 0.0)
        return True


if __name__ == "__main__":
    sys.exit(Dock().run(None))
