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


class Dock(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="m2res.macdock")
        self.dots = []

    def do_activate(self):
        c = load_cfg()
        win = Gtk.ApplicationWindow(application=self)
        win.add_css_class("macdock-win"); win.set_decorated(False); win.set_focusable(False)
        LS.init_for_window(win)
        LS.set_layer(win, LS.Layer.TOP)
        LS.set_anchor(win, LS.Edge.BOTTOM, True)
        LS.set_margin(win, LS.Edge.BOTTOM, int(c.get("bottom", 10)))
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
        win.present()
        self.refresh()
        GLib.timeout_add(1500, self.refresh)

    def refresh(self):
        run = running()
        for cls, dot in self.dots:
            dot.set_opacity(1.0 if cls and cls in run else 0.0)
        return True


if __name__ == "__main__":
    sys.exit(Dock().run(None))
