#!/usr/bin/env python3
"""m2res calendar — календарь + таймер по клику на часы (Waybar). Стиль райса.
Календарь: ←/→ или PgUp/PgDn или колесо — месяц · T/Home — сегодня · клик по заголовку — сегодня.
Таймер (живёт отдельно от окна — см. m2res-timer): плитки 5/10/15/25/50 мин · набрать время и Enter
  (25 = минуты, 1:30 = мин:сек, 45s, 1h30m) · Пробел — пауза/продолжить · Delete — сброс · клик по кнопкам.
Esc или потеря фокуса — закрыть. Запуск: m2res-calendar toggle (файл не называть calendar.py — затеняет stdlib)"""
import sys, os, json, math, time, calendar, subprocess, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TIMER = os.path.expanduser("~/.config/m2res/scripts/m2res-timer"); TJSON = os.path.expanduser("~/.cache/m2res/timer.json")
FONT = "CaskaydiaMono Nerd Font Mono"
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
WDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
PRESETS = [(5, "5"), (10, "10"), (15, "15"), (25, "25"), (50, "50")]
PW, PAD, RIGHT, TOP = 500, 28, 28, 52
CW = (PW - 2 * PAD) / 7; CH = 42
Y_HDR, Y_WD, Y_GRID = 0, 74, 104
Y_TIMER = Y_GRID + 6 * CH + 20
PH = Y_TIMER + 296
RED, YEL = (1.0, 0.36, 0.48), (1.0, 0.82, 0.40)
DIM, TXT = (0.55, 0.56, 0.52), (0.92, 0.92, 0.88)
T_OPEN, T_CLOSE = 0.30, 0.16


def ease_out_quart(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 4


def accent():
    try:
        c = json.load(open(os.path.join(HERE, "colors.json")))["accent"].lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return (0.69, 0.84, 0.0)


def ease_out_back(t, s=1.5):
    t = max(0.0, min(1.0, t)) - 1
    return 1 + t * t * ((s + 1) * t + s)


def timer_state():
    """('idle'|'running'|'paused'|'done', осталось_сек, всего_сек, подпись)"""
    try: d = json.load(open(TJSON))
    except Exception: return ("idle", 0, 0, "")
    st = d.get("state")
    if st == "running": return ("running", max(0.0, d["end"] - time.time()), d.get("total", 0), d.get("label", ""))
    if st == "paused": return ("paused", d.get("left", 0), d.get("total", 0), d.get("label", ""))
    if st == "done": return ("done", 0, d.get("total", 0), d.get("label", ""))
    return ("idle", 0, 0, "")


def tcmd(*a): subprocess.Popen([TIMER, *a], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def fmt(sec):
    s = int(math.ceil(sec))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


class Cal(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        today = datetime.date.today()
        self.acc = accent(); self.today = today; self.y, self.m = today.year, today.month
        self.t0 = None; self.close_at = None; self.typed = ""; self.err_t = 0.0; self.active_once = False
        self.press = {}; self.mshift = 0.0; self.mdir = 0
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY); LS.set_namespace(self, "m2res-calendar")
        MG = 48                                                   # поле под свечение и «выезд» вокруг панели
        for e in (LS.Edge.TOP, LS.Edge.RIGHT): LS.set_anchor(self, e, True)
        LS.set_margin(self, LS.Edge.TOP, TOP - MG); LS.set_margin(self, LS.Edge.RIGHT, RIGHT - MG)
        self.set_default_size(PW + 2 * MG, PH + 2 * MG)
        LS.set_exclusive_zone(self, -1); LS.set_keyboard_mode(self, LS.KeyboardMode.ON_DEMAND)
        mon = os.environ.get("M2_MON")
        if mon:
            for mo in Gdk.Display.get_default().get_monitors():
                if mo.get_connector() == mon: LS.set_monitor(self, mo)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.area = Gtk.DrawingArea(); self.set_child(self.area); self.area.set_draw_func(self.draw)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); self.add_controller(kc)
        g = Gtk.GestureClick(); g.connect("pressed", self.on_click); self.area.add_controller(g)
        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL); sc.connect("scroll", self.on_scroll); self.area.add_controller(sc)
        self.connect("map", lambda *_: setattr(self, "t0", time.monotonic()))
        self.connect("notify::is-active", self.on_active)
        self.area.add_tick_callback(self.tick)

    # ---------- геометрия ----------
    def origin(self):
        return 48, 48

    def chip_rect(self, i):
        ox, oy = self.origin(); n = len(PRESETS); gap = 10; w = (PW - 2 * PAD - gap * (n - 1)) / n
        return ox + PAD + i * (w + gap), oy + Y_TIMER + 132, w, 40

    def btn_rect(self, k):          # 0 — основная, 1 — сброс
        ox, oy = self.origin(); y = oy + Y_TIMER + 188
        return (ox + PAD + 250, y, PW - 2 * PAD - 250 - 66, 46) if k == 0 else (ox + PW - PAD - 56, y, 56, 46)

    def field_rect(self):
        ox, oy = self.origin(); return ox + PAD, oy + Y_TIMER + 188, 238, 46

    def nav_rect(self, k):
        ox, oy = self.origin(); return (ox + PW - PAD - 100, oy + 18, 46, 40) if k == 0 else (ox + PW - PAD - 46, oy + 18, 46, 40)

    def inr(self, r, x, y): return r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]

    # ---------- действия ----------
    def shift(self, d):
        self.m += d
        while self.m < 1: self.m += 12; self.y -= 1
        while self.m > 12: self.m -= 12; self.y += 1
        self.mdir = d; self.mshift = 1.0

    def go_today(self):
        d = (self.today.year * 12 + self.today.month) - (self.y * 12 + self.m)
        self.y, self.m = self.today.year, self.today.month
        if d: self.mdir = 1 if d > 0 else -1; self.mshift = 1.0

    def parse_typed(self):
        s = self.typed.strip().lower().replace(" ", "")
        if not s: return None
        if s.isdigit(): s += "m"
        return s

    def main_action(self):
        st = timer_state()[0]
        if st == "running": tcmd("pause")
        elif st == "paused": tcmd("resume")
        elif st == "done": tcmd("stop")
        else:
            a = self.parse_typed()
            if a: tcmd("start", a); self.typed = ""
            else: self.err_t = time.monotonic()
        self.press["main"] = time.monotonic()

    def begin_close(self):
        if not self.close_at: self.close_at = time.monotonic()

    def on_active(self, *_):
        if self.is_active(): self.active_once = True
        elif self.active_once and self.t0 and time.monotonic() - self.t0 > 0.5: self.begin_close()

    def on_key(self, _c, keyval, keycode, state):
        K = Gdk; ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if keyval == K.KEY_Escape: self.begin_close(); return True
        if keyval in (K.KEY_Return, K.KEY_KP_Enter): self.main_action(); return True
        if keyval == K.KEY_space and not self.typed: self.main_action(); return True
        if keyval == K.KEY_Delete: tcmd("stop"); self.press["reset"] = time.monotonic(); return True
        if keyval == K.KEY_BackSpace: self.typed = "" if ctrl else self.typed[:-1]; return True
        if keyval in (K.KEY_Left, K.KEY_Page_Up): self.shift(-1); return True
        if keyval in (K.KEY_Right, K.KEY_Page_Down): self.shift(1); return True
        if keyval in (K.KEY_Home, K.KEY_t, K.KEY_T) and not self.typed: self.go_today(); return True
        if keyval in (K.KEY_Up,): self.shift(-12); return True
        if keyval in (K.KEY_Down,): self.shift(12); return True
        ch = chr(keyval) if 32 <= keyval < 127 else ""
        if ch and (ch.isdigit() or ch in ":hmsHMS ") and len(self.typed) < 10: self.typed += ch
        return True

    def on_click(self, g, n, x, y):
        ox, oy = self.origin()
        if not (ox <= x <= ox + PW and oy <= y <= oy + PH): self.begin_close(); return
        if self.inr(self.nav_rect(0), x, y): self.shift(-1); return
        if self.inr(self.nav_rect(1), x, y): self.shift(1); return
        if oy <= y <= oy + 70 and x < ox + PW - 160: self.go_today(); return
        for i, (mins, _) in enumerate(PRESETS):
            if self.inr(self.chip_rect(i), x, y): tcmd("start", f"{mins}m"); self.press[f"c{i}"] = time.monotonic(); return
        if self.inr(self.btn_rect(0), x, y): self.main_action(); return
        if self.inr(self.btn_rect(1), x, y): tcmd("stop"); self.press["reset"] = time.monotonic(); return

    def on_scroll(self, c, dx, dy): self.shift(1 if dy > 0 else -1); return True

    def tick(self, _w, clock):
        if self.t0 is None: return True
        now = time.monotonic()
        if self.close_at and now - self.close_at > T_CLOSE: self.get_application().quit(); return False
        self.mshift *= 0.78
        if self.mshift < 0.01: self.mshift = 0.0
        self.area.queue_draw(); return True

    # ---------- рисование ----------
    def rr(self, cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2); cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi); cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi); cr.close_path()

    def text(self, cr, s, size, color, x, y, bold=False, anchor="l", alpha=1.0):
        lay = PangoCairo.create_layout(cr); lay.set_font_description(Pango.FontDescription(f"{FONT} {'Bold ' if bold else ''}{size}"))
        lay.set_text(s, -1); w, h = lay.get_pixel_size(); ox = x - (w / 2 if anchor == "c" else (w if anchor == "r" else 0))
        cr.set_source_rgba(*color, alpha); cr.move_to(ox, y - h / 2); PangoCairo.show_layout(cr, lay); return w

    def draw(self, _a, cr, w, h):
        if self.t0 is None: return
        now = time.monotonic(); t = now - self.t0
        if self.close_at:
            k = max(0.0, min(1.0, (now - self.close_at) / T_CLOSE)); sc = 1 - 0.03 * k; al = 1 - k; dy = -10 * k
        else:
            k = ease_out_quart(t / T_OPEN); sc = 0.96 + 0.04 * k; al = max(0.0, min(1.0, t / (T_OPEN * 0.6))); dy = (1 - min(1.0, t / T_OPEN)) * -14
        ox, oy = self.origin()
        cr.translate(ox + PW, oy); cr.scale(sc, sc); cr.translate(-(ox + PW), -oy + dy)
        self.paint_cached(cr, w, h, now, t, al, bool(self.close_at) or t < T_OPEN + 0.05)

    def paint_cached(self, cr, w, h, now, t, al, animating):
        """Во время анимации панель не меняется — рисуем её один раз в буфер и только двигаем (иначе кадр > 8 мс и анимация рваная)."""
        if not animating:
            self._pc = None; cr.push_group(); self.panel(cr, now, t); cr.pop_group_to_source(); cr.paint_with_alpha(al); return
        key = "close" if self.close_at else "open"
        if getattr(self, "_pc", None) is None or self._pc[0] != key or self._pc[1].get_width() != w:
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w), int(h)); self.panel(cairo.Context(surf), now, t); self._pc = (key, surf)
        cr.set_source_surface(self._pc[1], 0, 0); cr.paint_with_alpha(al)

    def panel(self, cr, now, t):
        A = self.acc; ox, oy = self.origin()
        for i, a in ((16, 0.04), (10, 0.06), (5, 0.09)):
            cr.set_source_rgba(*A, a); self.rr(cr, ox - i, oy - i, PW + 2 * i, PH + 2 * i, 28 + i); cr.fill()
        self.rr(cr, ox, oy, PW, PH, 28); cr.set_source_rgba(0.039, 0.039, 0.039, 0.97); cr.fill_preserve()
        cr.set_source_rgba(*A, 0.55); cr.set_line_width(2.5); cr.stroke()
        self.calendar(cr, now, ox, oy); self.timer(cr, now, ox, oy)

    def calendar(self, cr, now, ox, oy):
        A = self.acc
        wm = self.text(cr, MONTHS[self.m - 1].upper(), 24, A, ox + PAD + 2, oy + 38, bold=True)
        self.text(cr, str(self.y), 24, DIM, ox + PAD + 2 + wm + 14, oy + 38)
        for k, ch in enumerate(("‹", "›")):
            r = self.nav_rect(k); self.rr(cr, *r, 12); cr.set_source_rgba(1, 1, 1, 0.06); cr.fill()
            self.text(cr, ch, 26, A, r[0] + r[2] / 2, r[1] + r[3] / 2 - 2, bold=True, anchor="c")
        cr.set_source_rgba(*A, 0.28); cr.rectangle(ox + PAD, oy + 66, PW - 2 * PAD, 2); cr.fill()
        for i, d in enumerate(WDAYS):
            self.text(cr, d, 14, RED if i >= 5 else DIM, ox + PAD + CW * (i + .5), oy + Y_WD + 8, bold=True, anchor="c", alpha=0.85 if i >= 5 else 1)
        weeks = calendar.Calendar(0).monthdatescalendar(self.y, self.m)
        while len(weeks) < 6: weeks.append([weeks[-1][-1] + datetime.timedelta(days=1 + j) for j in range(7)])
        slide = self.mshift * self.mdir * 40; fade = 1 - self.mshift * 0.7
        cr.save(); cr.rectangle(ox + PAD - 4, oy + Y_GRID - 2, PW - 2 * PAD + 8, 6 * CH + 4); cr.clip()
        for r, wk in enumerate(weeks):
            for c, d in enumerate(wk):
                x = ox + PAD + CW * c + slide; y = oy + Y_GRID + CH * r
                inm = d.month == self.m; is_today = d == self.today
                if is_today:
                    for j, aa in ((6, 0.06), (3, 0.1)): cr.set_source_rgba(*A, aa * fade); self.rr(cr, x + 3 - j, y + 3 - j, CW - 6 + 2 * j, CH - 6 + 2 * j, 14 + j); cr.fill()
                    self.rr(cr, x + 3, y + 3, CW - 6, CH - 6, 14); cr.set_source_rgba(*A, fade); cr.fill()
                    col = (0.08, 0.10, 0.0)
                else:
                    col = (RED if c >= 5 else TXT) if inm else (0.32, 0.33, 0.30)
                self.text(cr, str(d.day), 17, col, x + CW / 2, y + CH / 2, bold=is_today, anchor="c", alpha=fade * (0.88 if (c >= 5 and inm and not is_today) else 1))
        cr.restore()

    def timer(self, cr, now, ox, oy):
        A = self.acc; y0 = oy + Y_TIMER
        cr.set_source_rgba(*A, 0.28); cr.rectangle(ox + PAD, y0 - 10, PW - 2 * PAD, 2); cr.fill()
        st, left, total, label = timer_state()
        col = {"running": A, "paused": YEL, "done": RED}.get(st, A)
        self.text(cr, "TIMER", 15, A, ox + PAD + 2, y0 + 14, bold=True)
        sub = {"idle": "не запущен", "running": "идёт", "paused": "пауза", "done": "ВРЕМЯ ВЫШЛО"}[st]
        if label and st != "idle": sub += f" · {label}"
        self.text(cr, sub, 14, col if st != "idle" else DIM, ox + PW - PAD - 2, y0 + 14, anchor="r", bold=(st == "done"))
        # кольцо + время
        cx, cy, R = ox + PAD + 52, y0 + 76, 40
        cr.set_line_width(8); cr.set_source_rgba(1, 1, 1, 0.08); cr.new_sub_path(); cr.arc(cx, cy, R, 0, 2 * math.pi); cr.stroke()
        frac = (left / total) if total else 0
        if st == "done": frac = 1.0; col = (RED[0], RED[1], RED[2])
        if st != "idle" and frac > 0:
            a = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(now * 6)) if st == "done" else 1.0
            cr.set_source_rgba(*col, a); cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.new_sub_path(); cr.arc(cx, cy, R, -math.pi / 2, -math.pi / 2 + 2 * math.pi * min(1.0, frac)); cr.stroke()
        cr.set_line_cap(cairo.LINE_CAP_BUTT)
        shown = fmt(left) if st in ("running", "paused") else ("00:00" if st == "done" else "--:--")
        if st == "idle" and self.typed:
            pt = self.parse_typed()
            shown = self.typed; col = A
        self.text(cr, shown, 46 if len(shown) < 7 else 38, TXT if st in ("running", "paused") else (col if st == "done" else DIM), ox + PAD + 118, cy - 2, bold=True)
        if st in ("running", "paused"): self.text(cr, f"из {int(total // 60)} мин" if total >= 60 else f"из {int(total)} с", 14, DIM, ox + PAD + 120, cy + 34)
        # плитки
        for i, (mins, lab) in enumerate(PRESETS):
            r = self.chip_rect(i); pr = self.press.get(f"c{i}"); k = 1.0
            if pr is not None and (now - pr) < 0.3: k = 1 - 0.07 * math.sin((now - pr) / 0.3 * math.pi)
            cr.save(); cr.translate(r[0] + r[2] / 2, r[1] + r[3] / 2); cr.scale(k, k); cr.translate(-r[2] / 2, -r[3] / 2)
            self.rr(cr, 0, 0, r[2], r[3], 14); cr.set_source_rgba(1, 1, 1, 0.06); cr.fill_preserve(); cr.set_source_rgba(*A, 0.3); cr.set_line_width(1.5); cr.stroke()
            self.text(cr, f"{lab} мин", 15, TXT, r[2] / 2, r[3] / 2, bold=True, anchor="c"); cr.restore()
        # поле ввода
        fx, fy, fw, fh = self.field_rect()
        self.rr(cr, fx, fy, fw, fh, 16); cr.set_source_rgba(1, 1, 1, 0.05); cr.fill_preserve()
        bad = (now - self.err_t) < 0.5
        cr.set_source_rgba(*(RED if bad else A), 0.7 if bad else 0.3); cr.set_line_width(1.5); cr.stroke()
        if self.typed: wq = self.text(cr, self.typed, 20, TXT, fx + 16, fy + fh / 2, bold=True)
        else: wq = 0; self.text(cr, "25 · 1:30 · 45s", 14, DIM, fx + 16, fy + fh / 2)
        if int(now * 2) % 2 == 0: cr.set_source_rgba(*A, 0.9); cr.rectangle(fx + 18 + wq, fy + 12, 2.5, fh - 24); cr.fill()
        # кнопки
        r = self.btn_rect(0); lab = {"idle": "СТАРТ", "running": "ПАУЗА", "paused": "ПРОДОЛЖИТЬ", "done": "ЗАКРЫТЬ"}[st]
        pr = self.press.get("main"); k = 1 - 0.05 * math.sin(min(1, (now - pr) / 0.25) * math.pi) if pr else 1.0
        cr.save(); cr.translate(r[0] + r[2] / 2, r[1] + r[3] / 2); cr.scale(k, k); cr.translate(-r[2] / 2, -r[3] / 2)
        self.rr(cr, 0, 0, r[2], r[3], 16); cr.set_source_rgba(*(col if st != "idle" else A), 0.95); cr.fill()
        self.text(cr, lab, 16, (0.08, 0.10, 0.0), r[2] / 2, r[3] / 2, bold=True, anchor="c"); cr.restore()
        r = self.btn_rect(1)
        self.rr(cr, *r, 16); cr.set_source_rgba(1, 1, 1, 0.06); cr.fill_preserve(); cr.set_source_rgba(RED[0], RED[1], RED[2], 0.5); cr.set_line_width(1.5); cr.stroke()
        self.text(cr, "\U000f0156", 20, RED, r[0] + r[2] / 2, r[1] + r[3] / 2, anchor="c")
        self.text(cr, "←/→ месяц · T сегодня · Enter · Пробел · Del", 12, (0.45, 0.46, 0.42), ox + PW / 2, oy + PH - 20, anchor="c")


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.calendar")
    def do_activate(self): Cal(self).present()


if __name__ == "__main__":
    App().run()
