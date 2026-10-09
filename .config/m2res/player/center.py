#!/usr/bin/env python3
"""m2res center — центр уведомлений: панель справа во всю высоту (как в Windows).
Журнал: ~/.local/share/m2res/notifications.jsonl (его пишет m2res-notify-log по хуку mako).
Управление: × на карточке — удалить, CLEAR — очистить всё, DND — режим «не беспокоить»,
колесо — прокрутка, клик вне панели или Esc — закрыть. Запуск: m2res-center toggle"""
import sys, os, json, math, time, re, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from style import ST  # noqa: E402
DATA = os.path.expanduser("~/.local/share/m2res")
LOG, SEEN = f"{DATA}/notifications.jsonl", f"{DATA}/notif_seen"
FONT = ST.font
T_ENTER, T_EXIT = 0.40, 0.24
CARD_W, PAD, GAP, HEAD = 450, 16, 10, 76
RED, YEL, GREEN = (1.0, 0.36, 0.48), (1.0, 0.82, 0.40), (0.49, 1.0, 0.63)


def ease_out_back(t, s=1.4):
    t = max(0.0, min(1.0, t)) - 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2

def ease_out_quart(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 4


def ease_in_cubic(t):
    t = max(0.0, min(1.0, t)); return t ** 3

TAG = re.compile(r"<[^>]+>")

def load():
    out = []
    try:
        for line in open(LOG, encoding="utf-8"):
            try: out.append(json.loads(line))
            except Exception: pass
    except FileNotFoundError:
        pass
    return out[::-1]                      # новые сверху

def save(items_newest_first):
    os.makedirs(DATA, exist_ok=True)
    tmp = LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for n in reversed(items_newest_first): f.write(json.dumps(n, ensure_ascii=False) + "\n")
    os.replace(tmp, LOG)

def ping_bar():
    subprocess.Popen(["pkill", "-RTMIN+9", "-x", "waybar"])

def dnd_on():
    try: return "do-not-disturb" in subprocess.run(["makoctl", "mode"], capture_output=True, text=True, timeout=2).stdout
    except Exception: return False

def ago(ts):
    d = max(0, int(time.time() - ts))
    if d < 45: return "now"
    if d < 3600: return f"{d // 60}m"
    if d < 86400: return f"{d // 3600}h"
    return f"{d // 86400}d"


class Center(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        try:
            c = json.load(open(os.path.join(HERE, "colors.json")))["accent"].lstrip("#")
            self.accent = tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
        except Exception:
            self.accent = (0.69, 0.84, 0.0)
        env = os.environ
        self.top = int(float(env.get("M2_TOP", 42)))
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY)
        for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.RIGHT): LS.set_anchor(self, e, True)
        self.set_default_size(CARD_W + 10 + 60, -1)
        LS.set_exclusive_zone(self, -1); LS.set_namespace(self, "m2res-center")
        LS.set_keyboard_mode(self, LS.KeyboardMode.ON_DEMAND)
        mon = env.get("M2_MON")
        if mon:
            for m in Gdk.Display.get_default().get_monitors():
                if m.get_connector() == mon: LS.set_monitor(self, m)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw); self.set_child(self.area)

        self.items = load(); self.dnd = dnd_on(); self.mtime = self.log_mtime()
        self.scroll = 0.0; self.scroll_t = 0.0; self.content_h = 0
        self.t0 = None; self.closing_at = None; self.hits = []; self.hover = None
        self.card = (0, 0, CARD_W, 0)
        self.removing = {}                       # key -> время начала анимации удаления

        mo = Gtk.EventControllerMotion(); mo.connect("motion", self.on_motion); self.area.add_controller(mo)
        ck = Gtk.GestureClick(); ck.set_button(1); ck.connect("pressed", self.on_click); self.area.add_controller(ck)
        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        sc.connect("scroll", self.on_scroll); self.area.add_controller(sc)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); self.add_controller(kc)
        self.connect("map", lambda *_: setattr(self, "t0", time.monotonic()))
        self.active_once = False; self.connect("notify::is-active", self.on_active)
        self.area.add_tick_callback(self.tick)
        GLib.timeout_add(1000, self.refresh)
        os.makedirs(DATA, exist_ok=True); open(SEEN, "w").write(str(int(time.time()))); ping_bar()

    def log_mtime(self):
        try: return os.stat(LOG).st_mtime_ns
        except OSError: return 0

    def refresh(self):
        m = self.log_mtime()
        if m != self.mtime: self.mtime = m; self.items = load(); open(SEEN, "w").write(str(int(time.time()))); ping_bar()
        self.dnd = dnd_on(); return True

    # ---------- ввод ----------
    def on_motion(self, _c, x, y):
        self.hover = None
        for kind, r, pl in self.hits:
            if r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]: self.hover = (kind, pl)

    def on_scroll(self, _c, dx, dy):
        self.scroll_t += dy * 70; self.clamp(); return True

    def clamp(self):
        vis = self.card[3] - HEAD - PAD
        self.scroll_t = max(0.0, min(self.scroll_t, max(0.0, self.content_h - vis)))

    def on_key(self, _c, keyval, *_):
        if keyval == Gdk.KEY_Escape: self.begin_close()
        return True

    def begin_close(self):
        if not self.closing_at: self.closing_at = time.monotonic()

    def on_active(self, *_):
        if self.is_active(): self.active_once = True
        elif self.active_once and self.t0 and time.monotonic() - self.t0 > 0.5: self.begin_close()

    def on_click(self, _g, _n, x, y):
        if self.closing_at: return
        cx, cy, cw, ch = self.card
        if not (cx <= x <= cx + cw and cy <= y <= cy + ch):
            self.begin_close(); return
        for kind, r, pl in self.hits:
            if r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]:
                if kind == "clear":
                    for n in self.items: self.removing[(n["ts"], n["id"])] = time.monotonic()
                elif kind == "dnd":
                    subprocess.run(["makoctl", "mode", "-t", "do-not-disturb"]); self.dnd = dnd_on()
                    ping_bar()
                elif kind == "del":
                    self.removing[pl] = time.monotonic()
                return

    # ---------- цикл ----------
    def tick(self, *_):
        if self.t0 is None: return True
        now = time.monotonic()
        self.scroll += (self.scroll_t - self.scroll) * 0.25
        done = [k for k, t in self.removing.items() if now - t > 0.28]
        if done:
            keep = [n for n in self.items if (n["ts"], n["id"]) not in done]
            for k in done: self.removing.pop(k, None)
            if len(keep) != len(self.items): self.items = keep; save(keep); self.mtime = self.log_mtime(); ping_bar()
        if self.closing_at and now - self.closing_at > T_EXIT:
            self.get_application().quit(); return False
        self.area.queue_draw(); return True

    # ---------- рисование ----------
    def rrect(self, cr, x, y, w, h, r):
        ST.path(cr, x, y, w, h, r)

    def lay(self, cr, s, size, bold=True, width=None):
        l = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription(f"{FONT} {'Bold' if bold else ''}"); fd.set_absolute_size(size * Pango.SCALE)
        l.set_font_description(fd)
        if width: l.set_width(int(width * Pango.SCALE)); l.set_wrap(Pango.WrapMode.WORD_CHAR)
        l.set_text(s, -1); return l

    def txt(self, cr, s, x, y, size, color, bold=True, align="l"):
        l = self.lay(cr, s, size, bold); w, h = l.get_pixel_size()
        ox = x if align == "l" else (x - w / 2 if align == "c" else x - w)
        cr.move_to(ox, y - h / 2); cr.set_source_rgba(*color); PangoCairo.show_layout(cr, l); return w

    def chip(self, cr, rx, cy, s, size, fg, bg, kind=None, payload=None, active=False):
        l = self.lay(cr, s, size); w, h = l.get_pixel_size()
        x0, y0, bw, bh = rx - w - 22, cy - h / 2 - 6, w + 22, h + 12
        hov = self.hover and self.hover[0] == kind and kind
        self.rrect(cr, x0 - 3, y0 - 3, bw + 6, bh + 6, (bh + 6) / 2); cr.set_source_rgb(0, 0, 0); cr.fill()
        self.rrect(cr, x0, y0, bw, bh, bh / 2)
        if active: cr.set_source_rgb(*fg)
        else: cr.set_source_rgb(*(tuple(min(1, c + 0.08) for c in bg) if hov else bg))
        cr.fill()
        cr.move_to(x0 + 11, cy - h / 2); cr.set_source_rgb(*(ST.on_acc if active else fg)); PangoCairo.show_layout(cr, l)
        if kind: self.hits.append((kind, (x0, y0, bw, bh), payload))
        return x0 - 10

    def draw_item(self, cr, n, x, y, w, now):
        key = (n["ts"], n["id"])
        urg = n.get("urgency", "normal")
        col = RED if urg == "critical" else (ST.n(0.45, 0.45, 0.48) if urg == "low" else self.accent)
        tw = w - 2 * 16 - 8
        summ = self.lay(cr, TAG.sub("", n.get("summary", "")), 14, True, tw - 70)
        body = self.lay(cr, TAG.sub("", n.get("body", "")), 12, False, tw)
        sh, bh = summ.get_pixel_size()[1], body.get_pixel_size()[1] if n.get("body") else 0
        h = 16 + 16 + 6 + sh + (6 + bh if bh else 0) + 16
        k = self.removing.get(key)
        p = 0.0 if k is None else min(1.0, (now - k) / 0.28)
        return h, col, summ, body, sh, bh, p, tw

    def draw(self, _a, cr, W, H):
        if self.t0 is None: return
        now = time.monotonic(); t = now - self.t0
        cw, ch = CARD_W, H - self.top - 12
        cx = W - cw - 10
        full = cw + 40; off = 0.0
        if self.closing_at: off = full * ease_in_cubic((now - self.closing_at) / T_EXIT)
        elif t < T_ENTER: off = full * (1 - ease_out_quart(t / T_ENTER))
        self.card = (cx, self.top, cw, ch); self.hits = []
        cr.save(); cr.translate(off, 0)
        # корпус
        ST.frame(cr, cx, self.top, cw, ch, self.accent, 24, glow=False)
        hy = self.top + 36
        self.txt(cr, "󰂚", cx + PAD + 6, hy, 22, self.accent)
        self.txt(cr, "NOTIFICATIONS", cx + PAD + 40, hy - 1, 13, ST.n(0.95, 0.95, 0.95))
        self.txt(cr, f"{len(self.items)} в журнале" if self.items else "пусто", cx + PAD + 40, hy + 17, 10, ST.n(0.55, 0.55, 0.58), False)
        rx = cx + cw - PAD
        rx = self.chip(cr, rx, hy, "CLEAR", 12, RED, ST.n(0.12, 0.12, 0.14), "clear")
        self.chip(cr, rx, hy, "󰂛 DND" if self.dnd else "󰂚 DND", 12, self.accent, ST.n(0.12, 0.12, 0.14), "dnd", None, self.dnd)
        # список
        ly0 = self.top + HEAD; lh = ch - HEAD - PAD
        cr.save(); cr.rectangle(cx, ly0, cw, lh); cr.clip()
        y = ly0 - self.scroll; total = 0
        if not self.items:
            self.txt(cr, "󰂜", cx + cw / 2, ly0 + 120, 54, ST.n(0.28, 0.28, 0.3), True, "c")
            self.txt(cr, "Нет новых уведомлений", cx + cw / 2, ly0 + 180, 14, ST.n(0.6, 0.6, 0.62), True, "c")
        for i, n in enumerate(self.items):
            h, col, summ, body, sh, bh, p, tw = self.draw_item(cr, n, cx + PAD, y, cw - 2 * PAD, now)
            slide_in = ease_out_back((t - 0.1 - 0.04 * min(i, 8)) / 0.35, 1.2) if t < 1.0 else 1.0
            visible_h = h * (1 - p) ; ix = cx + PAD + p * 60 + (1 - max(0, min(1, slide_in))) * 40
            alpha = max(0.0, min(1.0, slide_in)) * (1 - p)
            if y + h > ly0 - 4 and y < ly0 + lh + 4 and alpha > 0.01:
                cr.push_group()
                self.rrect(cr, ix - 3, y - 3, cw - 2 * PAD + 6, h + 6, 20); cr.set_source_rgb(0, 0, 0); cr.fill()
                self.rrect(cr, ix, y, cw - 2 * PAD, h, 17); cr.set_source_rgb(*ST.n(0.15, 0.15, 0.17)); cr.fill()
                cr.save(); self.rrect(cr, ix, y, cw - 2 * PAD, h, 17); cr.clip()
                cr.rectangle(ix, y, 6, h); cr.set_source_rgb(*col); cr.fill(); cr.restore()
                self.txt(cr, n.get("app", "?").upper(), ix + 20, y + 22, 10, (*col, 1))
                self.txt(cr, ago(n["ts"]), ix + cw - 2 * PAD - 52, y + 22, 10, ST.n(0.55, 0.55, 0.58), False, "r")
                dx = ix + cw - 2 * PAD - 34
                hov = self.hover == ("del", (n["ts"], n["id"]))
                self.rrect(cr, dx, y + 8, 22, 22, 11); cr.set_source_rgb(*((0.35, 0.12, 0.17) if hov else ST.n(0.1, 0.1, 0.11))); cr.fill()
                self.txt(cr, "×", dx + 11, y + 18, 15, (*RED, 1) if hov else ST.n(0.7, 0.7, 0.72), True, "c")
                cr.move_to(ix + 20, y + 38); cr.set_source_rgb(*ST.n(0.97, 0.97, 0.97)); PangoCairo.show_layout(cr, summ)
                if bh:
                    cr.move_to(ix + 20, y + 38 + sh + 6); cr.set_source_rgb(*ST.n(0.72, 0.73, 0.7)); PangoCairo.show_layout(cr, body)
                cr.pop_group_to_source(); cr.paint_with_alpha(alpha)
                if p == 0.0 and not self.closing_at:
                    self.hits.append(("del", (dx, y + 8, 22, 22), (n["ts"], n["id"])))
            adv = (h + GAP) * (1 - p * 0.0)
            y += adv; total += adv
        self.content_h = total; self.clamp()
        cr.restore()
        # полоска прокрутки
        if self.content_h > lh:
            th = max(40, lh * lh / self.content_h); ty = ly0 + (lh - th) * (self.scroll / max(1, self.content_h - lh))
            self.rrect(cr, cx + cw - 7, ty, 4, th, 2); cr.set_source_rgba(*self.accent, 0.6); cr.fill()
        cr.restore()


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.center")
    def do_activate(self): Center(self).present()


if __name__ == "__main__":
    App().run()
