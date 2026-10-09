#!/usr/bin/env python3
"""m2res powermenu — меню сессии: блокировка, сон, выход, перезагрузка, выключение.
Опасные действия (выход/перезагрузка/выключение) срабатывают только при УДЕРЖАНИИ Enter / кнопки мыши 0.8 с —
кольцо заполняется; отпустили раньше — отмена. Блокировка и сон — сразу.
Клавиши: ←/→ Tab — выбор · 1-5 или L S O R P — выбор буквой · Enter — действие · Esc — закрыть.
Запуск: m2res-power toggle"""
import sys, os, json, math, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "CaskaydiaMono Nerd Font Mono"
RED, YEL = (1.0, 0.36, 0.48), (1.0, 0.82, 0.40)
TW, TH, GAP, PAD, MARG = 200, 236, 16, 30, 40
N = 5
PW = PAD * 2 + N * TW + (N - 1) * GAP
HDR, FTR = 104, 70
PH = HDR + TH + FTR
T_OPEN, T_CLOSE, HOLD = 0.30, 0.16, 0.8

# ключ, подпись, значок, команда, нужно удержание, цвет (None = акцент), буква
ACTIONS = [
    ("lock", "LOCK", "\uf023", "pidof hyprlock || hyprlock", False, None, "L"),
    ("sleep", "SLEEP", "\U000f0904", "systemctl suspend", False, None, "S"),
    ("logout", "LOG OUT", "\U000f0343", "uwsm stop || loginctl terminate-session \"$XDG_SESSION_ID\"", True, YEL, "O"),
    ("reboot", "RESTART", "\U000f0709", "systemctl reboot", True, RED, "R"),
    ("poweroff", "SHUT DOWN", "\U000f0425", "systemctl poweroff", True, RED, "P"),
]


def accent():
    try:
        c = json.load(open(os.path.join(HERE, "colors.json")))["accent"].lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return (0.69, 0.84, 0.0)


def ease_out_quart(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 4


def ease_out_back(t, s=1.6):
    t = max(0.0, min(1.0, t)) - 1
    return 1 + t * t * ((s + 1) * t + s)


class Power(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.acc = accent(); self.sel = 0; self.hlx = None; self.hover = -1
        self.t0 = None; self.close_at = None; self.pending = None
        self.hold_i = None; self.hold_t = 0.0; self.fire_t = None; self.cancel_t = {}
        self.win_w, self.win_h = PW + 2 * MARG, PH + 2 * MARG
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY); LS.set_namespace(self, "m2res-power")
        LS.set_exclusive_zone(self, -1); LS.set_keyboard_mode(self, LS.KeyboardMode.EXCLUSIVE)
        mon = os.environ.get("M2_MON")
        if mon:
            for m in Gdk.Display.get_default().get_monitors():
                if m.get_connector() == mon: LS.set_monitor(self, m)
        self.set_default_size(self.win_w, self.win_h)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw); self.set_child(self.area)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); kc.connect("key-released", self.on_key_up); self.add_controller(kc)
        mo = Gtk.EventControllerMotion(); mo.connect("motion", self.on_motion); self.area.add_controller(mo)
        g = Gtk.GestureClick(); g.set_button(1); g.connect("pressed", self.on_press); g.connect("released", self.on_release); self.area.add_controller(g)
        self.connect("map", lambda *_: setattr(self, "t0", time.monotonic()))
        self.area.add_tick_callback(self.tick)

    # ---------- логика ----------
    def tile_rect(self, i):
        return MARG + PAD + i * (TW + GAP), MARG + HDR, TW, TH

    def tile_at(self, x, y):
        for i in range(N):
            tx, ty, w, h = self.tile_rect(i)
            if tx <= x <= tx + w and ty <= y <= ty + h: return i
        return -1

    def begin_close(self, then=None):
        if self.close_at: return
        self.close_at = time.monotonic(); self.pending = then

    def start_hold(self, i):
        a = ACTIONS[i]
        if self.fire_t or self.close_at: return
        if not a[4]: self.fire(i); return
        if self.hold_i is None: self.hold_i = i; self.hold_t = time.monotonic()

    def stop_hold(self):
        if self.hold_i is not None and not self.fire_t: self.cancel_t[self.hold_i] = (time.monotonic(), self.hold_frac())
        if not self.fire_t: self.hold_i = None

    def hold_frac(self):
        return 0.0 if self.hold_i is None else min(1.0, (time.monotonic() - self.hold_t) / HOLD)

    def fire(self, i):
        self.fire_t = time.monotonic(); self.hold_i = i if ACTIONS[i][4] else None; self.sel = i
        cmd = ACTIONS[i][3]
        dry = os.environ.get("M2_POWER_DRY")        # для тестов: вместо запуска только записать команду в файл
        if dry: self.begin_close(lambda: open(dry, "a").write(ACTIONS[i][0] + "\n")); return
        self.begin_close(lambda: subprocess.Popen(["sh", "-c", cmd], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

    def on_key(self, _c, keyval, keycode, state):
        if self.close_at: return True
        K = Gdk
        if keyval == K.KEY_Escape: self.begin_close(); return True
        if keyval in (K.KEY_Return, K.KEY_KP_Enter, K.KEY_space): self.start_hold(self.sel); return True
        if keyval in (K.KEY_Left, K.KEY_h): self.sel = (self.sel - 1) % N; self.stop_hold(); return True
        if keyval in (K.KEY_Right, K.KEY_Tab): self.sel = (self.sel + 1) % N; self.stop_hold(); return True
        if keyval == K.KEY_ISO_Left_Tab: self.sel = (self.sel - 1) % N; self.stop_hold(); return True
        ch = chr(keyval).upper() if 32 < keyval < 127 else ""
        if ch.isdigit() and 1 <= int(ch) <= N: self.sel = int(ch) - 1; self.stop_hold(); return True
        for i, a in enumerate(ACTIONS):
            if ch == a[6]: self.sel = i; self.stop_hold(); return True
        return True

    def on_key_up(self, _c, keyval, keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space): self.stop_hold()

    def on_motion(self, _c, x, y):
        i = self.tile_at(x, y); self.hover = i
        if i >= 0 and i != self.sel and self.hold_i is None: self.sel = i

    def on_press(self, g, n, x, y):
        i = self.tile_at(x, y)
        if i < 0:                                   # клик мимо панели закрывает
            if not (MARG <= x <= MARG + PW and MARG <= y <= MARG + PH): self.begin_close()
            return
        self.sel = i; self.start_hold(i)

    def on_release(self, g, n, x, y): self.stop_hold()

    # ---------- анимация ----------
    def tick(self, _w, clock):
        if self.t0 is None: return True
        now = time.monotonic()
        if self.close_at and now - self.close_at > (T_CLOSE if not self.fire_t else 0.34):
            if self.pending: self.pending()
            self.get_application().quit(); return False
        if self.hold_i is not None and not self.fire_t and self.hold_frac() >= 1.0: self.fire(self.hold_i)
        tx = self.tile_rect(self.sel)[0]
        self.hlx = tx if self.hlx is None else self.hlx + (tx - self.hlx) * 0.32
        self.area.queue_draw(); return True

    # ---------- рисование ----------
    def rr(self, cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2); cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi); cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi); cr.close_path()

    def text(self, cr, s, size, color, x, y, bold=False, anchor="l", alpha=1.0):
        lay = PangoCairo.create_layout(cr); lay.set_font_description(Pango.FontDescription(f"{FONT} {'Bold ' if bold else ''}{size}"))
        lay.set_text(s, -1); w, h = lay.get_pixel_size()
        ox = x - (w / 2 if anchor == "c" else (w if anchor == "r" else 0))
        cr.set_source_rgba(*color, alpha); cr.move_to(ox, y - h / 2); PangoCairo.show_layout(cr, lay); return w

    def draw(self, _a, cr, w, h):
        if self.t0 is None: return
        now = time.monotonic(); t = now - self.t0
        if self.close_at:
            k = max(0.0, min(1.0, (now - self.close_at) / (T_CLOSE if not self.fire_t else 0.3))); sc = 1 - 0.04 * k; al = 1 - k
        else:
            k = ease_out_quart(t / T_OPEN); sc = 0.95 + 0.05 * k; al = max(0.0, min(1.0, t / (T_OPEN * 0.6)))
        cr.translate(self.win_w / 2, self.win_h / 2); cr.scale(sc, sc); cr.translate(-self.win_w / 2, -self.win_h / 2)
        cr.push_group(); self.panel(cr, now, t); cr.pop_group_to_source(); cr.paint_with_alpha(al)

    def panel(self, cr, now, t):
        A = self.acc
        x0, y0 = MARG, MARG
        for i, a in ((18, 0.04), (12, 0.06), (6, 0.09)):
            cr.set_source_rgba(*A, a); self.rr(cr, x0 - i, y0 - i, PW + 2 * i, PH + 2 * i, 30 + i); cr.fill()
        self.rr(cr, x0, y0, PW, PH, 30); cr.set_source_rgba(0.039, 0.039, 0.039, 0.97); cr.fill_preserve()
        cr.set_source_rgba(*A, 0.55); cr.set_line_width(2.5); cr.stroke()
        # шапка
        self.text(cr, "SESSION", 26, A, x0 + PAD + 4, y0 + 44, bold=True)
        self.text(cr, "выберите действие", 14, (0.55, 0.56, 0.52), x0 + PAD + 4, y0 + 74)
        user = os.environ.get("USER", "")
        self.text(cr, f"{user} @ {os.uname().nodename}", 14, (0.55, 0.56, 0.52), x0 + PW - PAD - 4, y0 + 44, anchor="r")
        cr.set_source_rgba(*A, 0.30); cr.rectangle(x0 + PAD, y0 + 94, PW - 2 * PAD, 2); cr.fill()
        # рамка выбора (скользит)
        if self.hlx is not None:
            a = ACTIONS[self.sel]; c = a[5] or A; hy = y0 + HDR
            pulse = 0.5 + 0.5 * math.sin(now * 4)
            for i, aa in ((10, 0.05), (6, 0.08)):
                cr.set_source_rgba(*c, aa + 0.03 * pulse); self.rr(cr, self.hlx - i, hy - i, TW + 2 * i, TH + 2 * i, 24 + i); cr.fill()
            self.rr(cr, self.hlx, hy, TW, TH, 24); cr.set_source_rgba(*c, 0.13); cr.fill_preserve()
            cr.set_source_rgba(*c, 0.95); cr.set_line_width(2.5); cr.stroke()
        for i, a in enumerate(ACTIONS):
            self.tile(cr, i, a, now, t)
        # подвал
        sel = ACTIONS[self.sel]
        hint = "удерживайте Enter 0.8 с" if sel[4] else "Enter — сразу"
        self.text(cr, f"←  →  выбор      {hint}      Esc — закрыть", 14, (0.50, 0.51, 0.47), x0 + PW / 2, y0 + PH - 30, anchor="c")

    def tile(self, cr, i, a, now, t):
        tx, ty, w, h = self.tile_rect(i)
        d = max(0.0, min(1.0, (t - 0.05 * i) / 0.34))                    # появление плиток по очереди
        pop = ease_out_back(d, 1.8); off = (1 - pop) * 26
        c = a[5] or self.acc; selected = i == self.sel
        cx, cy = tx + w / 2, ty + h / 2 + off
        cr.save(); cr.translate(cx, cy)
        frac = self.hold_frac() if self.hold_i == i else 0.0
        if self.fire_t and self.hold_i == i: frac = 1.0
        k = 1.0 + (0.04 if selected else 0) + 0.03 * frac
        shake = 0.0
        if frac > 0.6 and not self.fire_t: shake = math.sin(now * 70) * 2.2 * (frac - 0.6)
        if i in self.cancel_t and not self.fire_t:                       # отпустили: кольцо плавно откатывается
            t0, f0 = self.cancel_t[i]; r = max(0.0, f0 * (1 - (now - t0) / 0.25))
            if r <= 0: del self.cancel_t[i]
            else: frac = r
        cr.translate(shake, 0); cr.scale(k, k)
        al = d
        # значок
        ic = (0.93, 0.93, 0.90) if not selected else tuple(min(1, v * 0.4 + 0.6) for v in c)
        self.text(cr, a[2], 76, ic if selected else (0.82, 0.83, 0.78), 0, -34, anchor="c", alpha=al)
        # кольцо удержания вокруг значка
        if frac > 0:
            cr.set_line_width(7); cr.set_source_rgba(*c, 0.18 * al); cr.arc(0, -34, 60, 0, 2 * math.pi); cr.stroke()
            cr.set_source_rgba(*c, al); cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.arc(0, -34, 60, -math.pi / 2, -math.pi / 2 + 2 * math.pi * frac); cr.stroke()
        self.text(cr, a[1], 20, c if selected else (0.78, 0.79, 0.74), 0, 62, bold=True, anchor="c", alpha=al)
        self.text(cr, f"{i + 1}  ·  {a[6]}", 13, (0.45, 0.46, 0.42), 0, 92, anchor="c", alpha=al * 0.9)
        if a[4]: self.text(cr, "HOLD", 11, c, 0, 108, bold=True, anchor="c", alpha=al * (0.9 if selected else 0.45))
        cr.restore()
        if self.fire_t and self.hold_i == i:                             # вспышка при срабатывании
            f = max(0.0, 1 - (now - self.fire_t) / 0.3)
            cr.set_source_rgba(*c, 0.35 * f); self.rr(cr, tx, ty, w, h, 24); cr.fill()


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.power")
    def do_activate(self): Power(self).present()


if __name__ == "__main__":
    App().run()
