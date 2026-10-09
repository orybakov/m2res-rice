#!/usr/bin/env python3
"""m2res dock — узкая боковая панель для 32:9: ярлыки, мини-плеер, загрузка CPU/GPU/VRAM/RAM.
Живёт у левого края монитора, не берёт фокус клавиатуры. Запуск: m2res-dock toggle (SUPER+SHIFT+B).
Настройки: ~/.config/m2res/dock.conf (SIDE=left|right, AUTOHIDE=1 — выезжает при наведении на край экрана, EDGE — толщина зоны у края в px, HIDE_MS — задержка скрытия, EXCLUSIVE=1 — резервировать место, AUTOSTART=1 — запуск при входе)."""
import sys, os, json, time, subprocess, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402,F401
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from style import ST  # noqa: E402
M2 = os.path.dirname(HERE)
FONT = ST.font
W, PAD, BH, BG = 84, 12, 46, 6          # ширина панели, поля, высота кнопки, зазор
MARGIN = 8


def conf():
    d = {"SIDE": "left", "EXCLUSIVE": "0", "AUTOHIDE": "1", "EDGE": "4", "HIDE_MS": "450"}
    try:
        for line in open(M2 + "/dock.conf"):
            line = line.split("#")[0].strip()
            if "=" in line:
                k, v = line.split("=", 1); d[k.strip()] = v.strip().strip('"')
    except Exception:
        pass
    return d


def accent():
    try:
        c = json.load(open(os.path.join(HERE, "colors.json")))["accent"].lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return (0.69, 0.84, 0.0)


def sh(*a, t=2.0):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=t).stdout
    except Exception:
        return ""


SECONDARY = {"SHOT": "@hide sleep 0.45; " + M2 + "/scripts/m2res-shot screen"}


def spawn(cmd):
    subprocess.Popen(["setsid", "-f", "bash", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# (глиф, подпись, команда)
BUTTONS = [
    ("\uf120", "TERM", "uwsm app -- ghostty"),
    ("\uf0ac", "WEB", "uwsm app -- google-chrome-stable"),
    ("\uf07b", "FILES", "uwsm app -- nautilus --new-window"),
    ("\uf0ea", "CLIP", M2 + "/scripts/m2res-clip toggle"),
    ("\uf030", "SHOT", "@hide sleep 0.45; " + M2 + "/scripts/m2res-shot area"),     # ЛКМ — область, ПКМ — весь экран
    ("\uf013", "CTRL", M2 + "/scripts/m2res-control toggle"),
    ("\uf1fc", "PROF", M2 + "/scripts/m2res-profile cycle"),
]


class Stats:
    def __init__(self):
        self.cpu = self.gpu = self.vram = self.ram = 0.0
        self.title = ""; self.playing = False; self.prof = ""; self._c = None
        self.lock = threading.Lock()
        threading.Thread(target=self.loop, daemon=True).start()

    def read_cpu(self):
        p = [int(x) for x in open("/proc/stat").readline().split()[1:8]]
        idle, tot = p[3] + p[4], sum(p)
        if self._c:
            di, dt = idle - self._c[0], tot - self._c[1]
            v = 1 - di / dt if dt > 0 else 0.0
        else:
            v = 0.0
        self._c = (idle, tot); return max(0.0, min(1.0, v))

    def loop(self):
        n = 0
        while True:
            cpu = self.read_cpu()
            mi = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo") if l.split(":")[0] in ("MemTotal", "MemAvailable")}
            ram = 1 - mi["MemAvailable"] / mi["MemTotal"]
            with self.lock:
                self.cpu, self.ram = cpu, ram
            if n % 2 == 0:
                g = sh("nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits", t=3).strip().split(",")
                try:
                    with self.lock:
                        self.gpu = float(g[0]) / 100; self.vram = float(g[1]) / float(g[2])
                except Exception:
                    pass
                st = sh("playerctl", "status").strip()
                ti = sh("playerctl", "metadata", "title").strip() if st else ""
                try:
                    prof = open(os.path.expanduser("~/.cache/m2res/profile")).read().strip()
                except Exception:
                    prof = ""
                with self.lock:
                    self.playing, self.title, self.prof = st == "Playing", ti, prof
            n += 1; time.sleep(1.0)


class Dock(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.cf = conf(); self.acc = accent(); self.stats = Stats(); self.hover = None
        self.nb = len(BUTTONS)
        self.PH = PAD + self.nb * (BH + BG) + 14 + 78 + 14 + 4 * 34 + PAD
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.TOP); LS.set_namespace(self, "m2res-dock")
        side = LS.Edge.RIGHT if self.cf["SIDE"] == "right" else LS.Edge.LEFT
        LS.set_anchor(self, side, True); LS.set_margin(self, side, MARGIN)
        self.set_default_size(W, self.PH)
        LS.set_exclusive_zone(self, W + 2 * MARGIN if self.cf["EXCLUSIVE"] == "1" else 0)
        LS.set_keyboard_mode(self, LS.KeyboardMode.NONE)
        mon = os.environ.get("M2_MON")
        if mon:
            for m in Gdk.Display.get_default().get_monitors():
                if m.get_connector() == mon: LS.set_monitor(self, m)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.area = Gtk.DrawingArea(); self.set_child(self.area); self.area.set_draw_func(self.draw)
        mo = Gtk.EventControllerMotion(); mo.connect("motion", self.on_motion); mo.connect("leave", lambda *_: self.set_hover(None)); self.area.add_controller(mo)
        gc = Gtk.GestureClick(); gc.set_button(0); gc.connect("pressed", self.on_click); self.area.add_controller(gc)
        GLib.timeout_add(1000, lambda: (self.area.queue_draw(), True)[1])
        # ---- автоскрытие: узкая невидимая полоса у края + плавный выезд панели ----
        self.auto = self.cf.get("AUTOHIDE", "1") == "1"; self.side = side
        self.p = 1.0; self.target = 1.0; self.in_dock = self.in_edge = False; self.hide_id = None; self.anim_id = None
        if self.auto:
            LS.set_exclusive_zone(self, 0)
            self.p = 0.0; self.target = 0.0; self.apply_margin(); self.set_visible(False)
            self.edge = Gtk.Window(application=app); LS.init_for_window(self.edge); LS.set_layer(self.edge, LS.Layer.TOP)
            LS.set_namespace(self.edge, "m2res-dock-edge")
            for e in (side, LS.Edge.TOP, LS.Edge.BOTTOM): LS.set_anchor(self.edge, e, True)
            LS.set_exclusive_zone(self.edge, 0); LS.set_keyboard_mode(self.edge, LS.KeyboardMode.NONE)
            self.edge.set_default_size(max(1, int(self.cf.get("EDGE", "4"))), 100)
            ea = Gtk.DrawingArea(); ea.set_size_request(max(1, int(self.cf.get("EDGE", "4"))), -1)
            if mon:
                for m in Gdk.Display.get_default().get_monitors():
                    if m.get_connector() == mon: LS.set_monitor(self.edge, m)
            ea.set_draw_func(lambda _a, cr, w, h: (cr.set_source_rgba(0, 0, 0, 0.004), cr.paint()))   # почти прозрачный буфер: поверхность должна смапиться
            css2 = Gtk.CssProvider(); css2.load_from_data(b"window.m2edge { background: transparent; }"); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css2, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.edge.add_css_class("m2edge")
            self.edge.set_child(ea)
            em = Gtk.EventControllerMotion(); em.connect("enter", lambda *_: self.hover_edge(True)); em.connect("leave", lambda *_: self.hover_edge(False))
            ea.add_controller(em)
            dm = Gtk.EventControllerMotion(); dm.connect("enter", lambda *_: self.hover_dock(True)); dm.connect("leave", lambda *_: self.hover_dock(False))
            self.add_controller(dm)
            self.edge.present()

    def apply_margin(self):
        full = W + MARGIN
        LS.set_margin(self, self.side, int(round(MARGIN - full * (1 - self.p))))

    def hover_edge(self, v): self.in_edge = v; self.update_want()

    def hover_dock(self, v): self.in_dock = v; self.update_want()

    def update_want(self):
        if self.in_edge or self.in_dock:
            if self.hide_id: GLib.source_remove(self.hide_id); self.hide_id = None
            self.go(1.0)
        elif not self.hide_id:
            self.hide_id = GLib.timeout_add(int(self.cf.get("HIDE_MS", "450")), self.do_hide)

    def do_hide(self):
        self.hide_id = None
        if not (self.in_edge or self.in_dock): self.go(0.0)
        return False

    def go(self, tgt):
        self.target = tgt
        if tgt > 0 and not self.get_visible(): self.set_visible(True); self.present()
        if not self.anim_id: self.t_last = time.monotonic(); self.anim_id = GLib.timeout_add(8, self.step)

    def step(self):
        now = time.monotonic(); dt = now - self.t_last; self.t_last = now
        d = dt / 0.18; self.p = min(self.target, self.p + d) if self.target > self.p else max(self.target, self.p - d)
        self.apply_margin(); self.area.queue_draw()
        if self.p == self.target:
            self.anim_id = None
            if self.target == 0.0: self.set_visible(False)
            return False
        return True

    # ---------- геометрия ----------
    def btn_rect(self, i): return PAD, PAD + i * (BH + BG), W - 2 * PAD, BH

    def player_y(self): return PAD + self.nb * (BH + BG) + 14

    def ctl_rect(self, k):          # 0 prev, 1 play/pause, 2 next
        y = self.player_y() + 46; w = (W - 2 * PAD) / 3
        return PAD + k * w, y, w, 28

    def hit(self, x, y):
        for i in range(self.nb):
            bx, by, bw, bh = self.btn_rect(i)
            if bx <= x <= bx + bw and by <= y <= by + bh: return ("b", i)
        for k in range(3):
            bx, by, bw, bh = self.ctl_rect(k)
            if bx <= x <= bx + bw and by <= y <= by + bh: return ("p", k)
        return None

    def set_hover(self, h):
        if h != self.hover: self.hover = h; self.area.queue_draw()

    def on_motion(self, _c, x, y): self.set_hover(self.hit(x, y))

    def run(self, cmd):
        if cmd.startswith("@hide "):         # спрятать панель, чтобы она не попала в кадр
            cmd = cmd[6:]; self.in_dock = self.in_edge = False
            if self.auto:
                if self.hide_id: GLib.source_remove(self.hide_id); self.hide_id = None
                self.go(0.0)
        spawn(cmd)

    def on_click(self, g, _n, x, y):
        h = self.hit(x, y)
        if not h: return
        if h[0] == "b":
            nm = BUTTONS[h[1]][1]
            self.run(SECONDARY[nm] if g.get_current_button() == 3 and nm in SECONDARY else BUTTONS[h[1]][2])
        else: spawn("playerctl " + ("previous", "play-pause", "next")[h[1]])
        GLib.timeout_add(600, lambda: (self.area.queue_draw(), False)[1])

    # ---------- рисование ----------
    def text(self, cr, s, size, color, x, y, bold=False, anchor="l", alpha=1.0, maxw=None):
        lay = PangoCairo.create_layout(cr); lay.set_font_description(Pango.FontDescription(f"{FONT} {'Bold ' if bold else ''}{size}"))
        if maxw: lay.set_width(int(maxw * Pango.SCALE)); lay.set_ellipsize(Pango.EllipsizeMode.END)
        lay.set_text(s, -1); w, h = lay.get_pixel_size(); ox = x - (w / 2 if anchor == "c" else (w if anchor == "r" else 0))
        cr.set_source_rgba(*color, alpha); cr.move_to(ox, y - h / 2); PangoCairo.show_layout(cr, lay); return w

    def rr(self, cr, x, y, w, h, r):
        ST.path(cr, x, y, w, h, r)

    def draw(self, _a, cr, w, h):
        A = self.acc; TXT = ST.n(0.93, 0.93, 0.9); DIM = ST.n(0.54, 0.55, 0.5)
        self.rr(cr, 0.5, 0.5, w - 1, h - 1, 18); cr.set_source_rgba(*ST.bg[:3], 0.94); cr.fill_preserve()
        cr.set_source_rgba(*A, 0.35); cr.set_line_width(1); cr.stroke()
        for i, (ic, nm, _c) in enumerate(BUTTONS):
            bx, by, bw, bh = self.btn_rect(i); hv = self.hover == ("b", i)
            if nm == "PROF" and self.stats.prof: ic_col = A
            else: ic_col = ST.on_acc if hv else TXT
            self.rr(cr, bx, by, bw, bh, 10)
            if hv: cr.set_source_rgba(*A, 1.0)
            else: cr.set_source_rgba(*ST.n(1, 1, 1, 0.05))
            cr.fill()
            self.text(cr, ic, 15, ic_col if not hv else ST.on_acc, bx + bw / 2, by + 17, anchor="c")
            self.text(cr, nm if not (nm == "PROF" and self.stats.prof) else self.stats.prof[:5].upper(), 8, ST.on_acc if hv else DIM, bx + bw / 2, by + 36, anchor="c", bold=True)
        py = self.player_y()
        cr.set_source_rgba(*A, 0.25); cr.rectangle(PAD, py - 8, W - 2 * PAD, 1); cr.fill()
        st = self.stats
        self.text(cr, "▶ PLAY" if st.playing else "❚❚", 8, A if st.playing else DIM, PAD, py + 8, bold=True)
        self.text(cr, st.title or "—", 8, TXT, PAD, py + 28, maxw=W - 2 * PAD)
        for k, g in enumerate(("\uf048", "\uf04c" if st.playing else "\uf04b", "\uf051")):
            bx, by, bw, bh = self.ctl_rect(k); hv = self.hover == ("p", k)
            if hv: self.rr(cr, bx + 2, by, bw - 4, bh, 8); cr.set_source_rgba(*A, 1.0); cr.fill()
            self.text(cr, g, 12, ST.on_acc if hv else TXT, bx + bw / 2, by + bh / 2, anchor="c")
        ly = py + 78 + 6
        cr.set_source_rgba(*A, 0.25); cr.rectangle(PAD, ly - 8, W - 2 * PAD, 1); cr.fill()
        for k, (nm, v) in enumerate((("CPU", st.cpu), ("GPU", st.gpu), ("VRAM", st.vram), ("RAM", st.ram))):
            y = ly + 4 + k * 34; col = (1.0, 0.36, 0.48) if v > 0.9 else A
            self.text(cr, nm, 8, DIM, PAD, y + 6, bold=True); self.text(cr, "%d%%" % round(v * 100), 8, TXT, W - PAD, y + 6, anchor="r", bold=True)
            bw = W - 2 * PAD
            self.rr(cr, PAD, y + 16, bw, 6, 3); cr.set_source_rgba(*ST.n(1, 1, 1, 0.08)); cr.fill()
            if v > 0.01: self.rr(cr, PAD, y + 16, max(6, bw * v), 6, 3); cr.set_source_rgba(*col, 1.0); cr.fill()


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="m2res.dock")

    def do_activate(self):
        d = Dock(self)
        if not d.auto: d.present()


if __name__ == "__main__":
    App().run([])
