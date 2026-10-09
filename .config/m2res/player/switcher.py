#!/usr/bin/env python3
"""m2res switcher — Alt+Tab с превью окон (стиль райса). Фоновый демон.

  * Alt+Tab / Alt+Shift+Tab → m2res-switch next|prev → сигнал демону (SIGUSR1 / SIGUSR2);
  * порядок — по недавности использования (MRU, из событий Hyprland), первое нажатие выбирает предыдущее окно;
  * отпустили Alt — переключились; Esc или клик мимо — отмена; клик по карточке — переключиться;
  * превью — снимок окна через grim в момент открытия; для окон на других рабочих столах показывается последний
    снятый кадр (если был) или значок.
Если Alt отпущен до появления окна (быстрый тап), просто происходит переключение на предыдущее окно без показа."""
import sys, os, json, math, time, signal, socket, threading, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0"); gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "CaskaydiaMono Nerd Font Mono"
TW, TH, GAP, PAD = 340, 190, 18, 26
CARD_H = TH + 70
MAXWIN = 16
DIM, TXT = (0.55, 0.56, 0.52), (0.92, 0.92, 0.88)
T_IN, T_OUT = 0.16, 0.10
WATCHDOG = 20.0


def accent():
    try:
        c = json.load(open(os.path.join(HERE, "colors.json")))["accent"].lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return (0.69, 0.84, 0.0)


def hyprctl_json(*a):
    try: return json.loads(subprocess.run(["hyprctl", "-j", *a], capture_output=True, text=True, timeout=2).stdout)
    except Exception: return None


def focus(addr):
    subprocess.Popen(["hyprctl", "eval", "hl.dispatch(hl.dsp.focus({ window = 'address:%s' }))" % addr],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------- MRU ----------------
MRU = []


def mru_touch(addr):
    if addr in MRU: MRU.remove(addr)
    MRU.insert(0, addr)


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


def mru_thread():
    for ln in events():
        if ln.startswith("activewindowv2>>"):
            a = ln.split(">>", 1)[1].strip()
            if a: mru_touch("0x" + a if not a.startswith("0x") else a)
        elif ln.startswith("closewindow>>"):
            a = "0x" + ln.split(">>", 1)[1].strip()
            if a in MRU: MRU.remove(a)


# ---------------- окна ----------------
THUMBS = {}          # addr -> (pixbuf, w, h, ts)
ICONS = {}


def list_windows():
    cl = hyprctl_json("clients") or []
    aw = hyprctl_json("activewindow") or {}
    mons = hyprctl_json("monitors") or []
    shown = {m["activeWorkspace"]["id"] for m in mons}
    out = []
    for c in cl:
        if not c.get("mapped") or c.get("hidden") or c["workspace"]["id"] <= 0: continue
        c["_vis"] = c["workspace"]["id"] in shown
        out.append(c)
    cur = aw.get("address", "")
    if cur: mru_touch(cur) if (not MRU or MRU[0] != cur) else None
    out.sort(key=lambda c: MRU.index(c["address"]) if c["address"] in MRU else 10_000 + c.get("focusHistoryID", 0))
    return out[:MAXWIN]


def grab(c):
    x, y = c["at"]; w, h = c["size"]
    if w < 8 or h < 8: return
    s = min(1.0, 520 / w, 300 / h)
    try:
        p = subprocess.run(["grim", "-t", "png", "-s", f"{s:.4f}", "-g", f"{x},{y} {w}x{h}", "-"], capture_output=True, timeout=3)
        if p.returncode != 0 or not p.stdout: return
        ld = GdkPixbuf.PixbufLoader.new_with_type("png"); ld.write(p.stdout); ld.close()
        THUMBS[c["address"]] = (ld.get_pixbuf(), w, h, time.time())
    except Exception:
        pass


def icon_for(cls, size=40):
    k = (cls, size)
    if k in ICONS: return ICONS[k]
    th = Gtk.IconTheme.get_for_display(Gdk.Display.get_default()); pb = None
    names = [cls, cls.lower(), cls.lower().split(".")[-1], cls.lower().replace("-stable", "").replace("-bin", "")]
    for n in names:
        if not th.has_icon(n): continue
        try:
            f = th.lookup_icon(n, None, size, 1, Gtk.TextDirection.NONE, 0).get_file()
            if f and f.get_path():
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(f.get_path(), size, size); break
        except Exception: pass
    ICONS[k] = pb; return pb


# ---------------- интерфейс ----------------
MG = 40                                                   # поле под свечение вокруг панели


class Switch(Gtk.ApplicationWindow):
    def __init__(self, app, wins, sel, daemon):
        super().__init__(application=app)
        self.d = daemon; self.wins = wins; self.sel = sel; self.acc = accent()
        self.ready_t = None; self.opened = time.monotonic(); self.close_at = None; self.commit_addr = None; self.hlx = None
        self.hover = -1; self.seen_active = False
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY); LS.set_namespace(self, "m2res-switch")
        for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT): LS.set_anchor(self, e, True)
        LS.set_exclusive_zone(self, -1); LS.set_keyboard_mode(self, LS.KeyboardMode.EXCLUSIVE)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; } window.m2dim { background: rgba(0,0,0,0.35); }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        mons = Gdk.Display.get_default().get_monitors(); self.mw = mons.get_item(0).get_geometry().width if mons.get_n_items() else 5120
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw); self.set_child(self.area)
        # окно — полный экран только ради затемнения (CSS + прозрачность окна); cairo рисует лишь прямоугольник панели
        _k, _cw, _ch, _g, _px, _py, _pw, _ph = self.layout()
        self.add_css_class("m2dim"); self.area.set_halign(Gtk.Align.CENTER); self.area.set_valign(Gtk.Align.CENTER)
        self.area.set_size_request(int(_pw + 2 * MG), int(_ph + 2 * MG)); self.set_opacity(0.02)
        oc = Gtk.GestureClick(); oc.connect("pressed", self.on_click_outside); self.add_controller(oc)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); kc.connect("key-released", self.on_key_up); kc.connect("modifiers", self.on_mods); self.add_controller(kc)
        mo = Gtk.EventControllerMotion(); mo.connect("motion", self.on_motion); self.area.add_controller(mo)
        g = Gtk.GestureClick(); g.connect("pressed", self.on_click); self.area.add_controller(g)
        self.connect("notify::is-active", self.on_active)
        self.area.add_tick_callback(self.tick)
        GLib.timeout_add(500, self.fallback_ready)

    def fallback_ready(self):
        if self.ready_t is None: self.ready_t = time.monotonic()
        return False

    def on_active(self, *_):
        if self.is_active() and not self.seen_active:
            self.seen_active = True; GLib.timeout_add(90, self.mark_ready)

    def mark_ready(self):
        if self.ready_t is None: self.ready_t = time.monotonic()
        return False

    # ----- геометрия -----
    def layout(self):
        n = len(self.wins); w = self.mw
        k = min(1.0, (w * 0.92 - PAD * 2 + GAP) / (n * (TW + GAP)))
        cw, ch, gap = TW * k, CARD_H * k, GAP * k
        pw = n * cw + (n - 1) * gap + PAD * 2; ph = ch + PAD * 2 + 56
        px, py = MG, MG
        return k, cw, ch, gap, px, py, pw, ph

    def card_rect(self, i):
        k, cw, ch, gap, px, py, pw, ph = self.layout(); return px + PAD + i * (cw + gap), py + PAD, cw, ch

    def hit(self, x, y):
        k, cw, ch, gap, px, py, pw, ph = self.layout()
        for i in range(len(self.wins)):
            cx, cy, w, h = self.card_rect(i)
            if cx <= x <= cx + w and cy <= y <= cy + h: return i
        return -1 if (px <= x <= px + pw and py <= y <= py + ph) else -2

    # ----- ввод -----
    def step(self, d):
        if os.environ.get("M2_SWITCH_DEBUG"): print("step", d, "sel", self.sel, "close", self.close_at, flush=True)
        if self.close_at: return
        self.sel = (self.sel + d) % len(self.wins)

    def commit(self):
        if os.environ.get("M2_SWITCH_DEBUG"): print("commit sel", self.sel, self.wins[self.sel]["class"], "alt", self.alt_down(), flush=True)
        if self.close_at: return
        self.commit_addr = self.wins[self.sel]["address"]; self.close_at = time.monotonic()

    def cancel(self):
        if not self.close_at: self.close_at = time.monotonic()

    def on_key(self, _c, keyval, keycode, state):
        if os.environ.get("M2_SWITCH_DEBUG"): print("key", Gdk.keyval_name(keyval), "state", int(state), "seat", int(Gdk.Display.get_default().get_default_seat().get_keyboard().get_modifier_state()), flush=True)
        K = Gdk
        if keyval == K.KEY_Escape: self.cancel(); return True
        if keyval in (K.KEY_Return, K.KEY_KP_Enter): self.commit(); return True
        if keyval in (K.KEY_Right, K.KEY_Down): self.step(1); return True
        if keyval in (K.KEY_Left, K.KEY_Up): self.step(-1); return True
        return True

    def on_key_up(self, _c, keyval, keycode, state):
        if os.environ.get("M2_SWITCH_DEBUG"): print("keyup", Gdk.keyval_name(keyval), int(state), flush=True)
        if keyval in (Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Meta_L, Gdk.KEY_Meta_R): self.commit()

    def on_mods(self, _c, state):
        if os.environ.get("M2_SWITCH_DEBUG"): print("mods", int(state), flush=True)
        return False

    def on_motion(self, _c, x, y):
        i = self.hit(x, y); self.hover = i
        if i >= 0: self.sel = i

    def update_opacity(self, now):
        if self.ready_t is None: self.set_opacity(0.02); return
        t = now - self.ready_t
        if self.close_at and self.close_at > self.ready_t: al = max(0.0, 1 - (now - self.close_at) / T_OUT)
        else: al = max(0.0, min(1.0, t / T_IN))
        self.set_opacity(max(0.02, al))

    def on_click_outside(self, g, n, x, y):
        b = self.area.compute_bounds(self)
        if b[0]:
            r = b[1]
            if not (r.get_x() <= x <= r.get_x() + r.get_width() and r.get_y() <= y <= r.get_y() + r.get_height()): self.cancel()

    def on_click(self, g, n, x, y):
        i = self.hit(x, y)
        if i >= 0: self.sel = i; self.commit()
        elif i == -2: self.cancel()

    def alt_down(self):
        try:
            kb = Gdk.Display.get_default().get_default_seat().get_keyboard()
            return bool(kb.get_modifier_state() & Gdk.ModifierType.ALT_MASK)
        except Exception: return True

    def tick(self, _w, clock):
        now = time.monotonic(); self.update_opacity(now)          # прозрачность окна — отсюда: у невидимого окна GTK не вызывает draw
        if self.close_at is None:
            if self.ready_t is not None and not self.alt_down(): self.commit()
            if now - self.opened > WATCHDOG: self.cancel()
        done = (self.close_at is not None and (now - self.close_at > (T_OUT if self.ready_t and self.ready_t < self.close_at else 0.0)))
        if done:
            addr = self.commit_addr; self.d.closed(self, addr); return False
        tx = self.card_rect(self.sel)[0]
        self.hlx = tx if self.hlx is None else self.hlx + (tx - self.hlx) * 0.38
        self.area.queue_draw(); return True

    # ----- рисование -----
    def rr(self, cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2); cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi); cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi); cr.close_path()

    def text(self, cr, s, size, color, x, y, bold=False, anchor="l", alpha=1.0, width=None):
        lay = PangoCairo.create_layout(cr); lay.set_font_description(Pango.FontDescription(f"{FONT} {'Bold ' if bold else ''}{size}"))
        lay.set_text(s, -1)
        if width: lay.set_width(int(width * Pango.SCALE)); lay.set_ellipsize(Pango.EllipsizeMode.END)
        w, h = lay.get_pixel_size(); ox = x - (w / 2 if anchor == "c" else (w if anchor == "r" else 0))
        cr.set_source_rgba(*color, alpha); cr.move_to(ox, y - h / 2); PangoCairo.show_layout(cr, lay); return w

    def draw(self, _a, cr, w, h):
        if self.ready_t is None: return
        now = time.monotonic(); t = now - self.ready_t
        if self.close_at and self.close_at > self.ready_t: al = max(0.0, 1 - (now - self.close_at) / T_OUT)
        else: al = max(0.0, min(1.0, t / T_IN))
        sc = 0.97 + 0.03 * al
        k, cw, ch, gap, px, py, pw, ph = self.layout()
        cr.translate(w / 2, h / 2); cr.scale(sc, sc); cr.translate(-w / 2, -h / 2)
        self.panel(cr, now, k, cw, ch, gap, px, py, pw, ph)

    def panel(self, cr, now, k, cw, ch, gap, px, py, pw, ph):
        A = self.acc
        for i, a in ((16, 0.04), (10, 0.06), (5, 0.09)):
            cr.set_source_rgba(*A, a); self.rr(cr, px - i, py - i, pw + 2 * i, ph + 2 * i, 28 + i); cr.fill()
        self.rr(cr, px, py, pw, ph, 28); cr.set_source_rgba(0.039, 0.039, 0.039, 0.96); cr.fill_preserve()
        cr.set_source_rgba(*A, 0.5); cr.set_line_width(2.5); cr.stroke()
        # рамка выбора
        if self.hlx is not None:
            cy = py + PAD; pulse = 0.5 + 0.5 * math.sin(now * 4)
            for i, aa in ((9, 0.05), (5, 0.08)):
                cr.set_source_rgba(*A, aa + 0.03 * pulse); self.rr(cr, self.hlx - 6 - i, cy - 6 - i, cw + 12 + 2 * i, ch + 12 + 2 * i, 20 + i); cr.fill()
            self.rr(cr, self.hlx - 6, cy - 6, cw + 12, ch + 12, 20); cr.set_source_rgba(*A, 0.14); cr.fill_preserve()
            cr.set_source_rgba(*A, 0.95); cr.set_line_width(2.5); cr.stroke()
        for i, c in enumerate(self.wins): self.card(cr, i, c, k, cw, ch)
        cur = self.wins[self.sel]
        self.text(cr, (cur.get("title") or cur["class"])[:90], 18, TXT, px + pw / 2, py + ph - 30, bold=True, anchor="c", width=pw - 80)

    def card(self, cr, i, c, k, cw, ch):
        A = self.acc; x, y, w, h = self.card_rect(i); sel = i == self.sel
        th = int(TH * k)
        self.rr(cr, x, y, w, th, 14 * k); cr.set_source_rgba(1, 1, 1, 0.05); cr.fill()
        t = THUMBS.get(c["address"])
        if t:
            pb = t[0]; s = min((w - 8 * k) / pb.get_width(), (th - 8 * k) / pb.get_height())
            cr.save(); self.rr(cr, x, y, w, th, 14 * k); cr.clip()
            cr.translate(x + (w - pb.get_width() * s) / 2, y + (th - pb.get_height() * s) / 2); cr.scale(s, s)
            Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0); cr.paint_with_alpha(1.0 if c["_vis"] else 0.55); cr.restore()
        else:
            ic = icon_for(c["class"], 64)
            if ic: Gdk.cairo_set_source_pixbuf(cr, ic, x + w / 2 - 32, y + th / 2 - 32); cr.paint()
            else: self.text(cr, (c["class"][:1] or "?").upper(), 56, A, x + w / 2, y + th / 2, bold=True, anchor="c")
        cr.set_source_rgba(*A, 0.9 if sel else 0.2); cr.set_line_width(1.5 if not sel else 2); self.rr(cr, x, y, w, th, 14 * k); cr.stroke()
        # значок + заголовок под превью
        ic = icon_for(c["class"], 36); ty = y + th + 30 * k
        tx = x + 6
        if ic: Gdk.cairo_set_source_pixbuf(cr, ic, tx, ty - 18); cr.paint(); tx += 46
        title = c.get("title") or c["class"]
        self.text(cr, title, 15, TXT if sel else (0.72, 0.73, 0.68), tx, ty - 8 * k, bold=sel, width=x + w - tx - 6)
        self.text(cr, c["class"].split(".")[-1], 12, DIM, tx, ty + 10 * k, width=x + w - tx - 6)
        if not c["_vis"]:
            wsid = c["workspace"]["id"]; self.rr(cr, x + w - 48, y + 8, 40, 24, 12); cr.set_source_rgba(0, 0, 0, 0.75); cr.fill()
            self.text(cr, f"ws{wsid}", 13, A, x + w - 28, y + 20, bold=True, anchor="c")


# ---------------- демон ----------------
class Daemon(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.m2res.switcher")
        self.win = None; self.busy = False; self.pending = 0; self.wins = []

    def do_activate(self):
        self.hold()
        threading.Thread(target=mru_thread, daemon=True).start()
        a = (hyprctl_json("activewindow") or {}).get("address")
        if a: mru_touch(a)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, lambda: self.signal(+1) or True)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, lambda: self.signal(-1) or True)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: self.quit() or True)

    def signal(self, d):
        if self.win is not None: self.win.step(d); return
        self.pending += d
        if self.busy: return
        self.busy = True
        threading.Thread(target=self.prepare, daemon=True).start()

    def prepare(self):
        wins = list_windows()
        if len(wins) >= 2:
            ts = [threading.Thread(target=grab, args=(c,)) for c in wins if c["_vis"]]
            [t.start() for t in ts]; [t.join(4) for t in ts]
        GLib.idle_add(self.open, wins)

    def open(self, wins):
        self.busy = False; p, self.pending = self.pending, 0
        if os.environ.get("M2_SWITCH_DEBUG"): print("open", p, [w["class"][:8] for w in wins], MRU[:5], flush=True)
        if len(wins) < 2: return False
        sel = (p if p > 0 else p) % len(wins) if abs(p) <= 1 else p % len(wins)
        self.win = Switch(self, wins, sel, self); self.win.present(); return False

    def closed(self, win, addr):
        self.win = None; win.destroy()
        if addr: GLib.timeout_add(40, lambda: focus(addr) or False)


if __name__ == "__main__":
    Daemon().run()
