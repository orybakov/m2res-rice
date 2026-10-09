#!/usr/bin/env python3
"""m2res clipboard — история буфера обмена (список слева, предпросмотр справа), стиль райса.
Клавиши: ↑/↓ PgUp/PgDn — выбор · Enter — скопировать и закрыть · Ctrl+P — закрепить · Delete — удалить ·
Ctrl+Shift+Delete — очистить всё неприкреплённое · печать — поиск · Esc — закрыть.
Данные пишет m2res-clip-store (wl-paste --watch). Запуск: m2res-clip toggle"""
import threading, sys, os, json, math, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0"); gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from style import ST  # noqa: E402
D = os.path.expanduser("~/.local/share/m2res/clipboard"); IDX = f"{D}/index.json"
FONT = ST.font
LW, RW, PAD, MARG = 520, 640, 24, 40
PW = PAD * 3 + LW + RW; ROW, ROWS = 62, 9
HDR = 112; PH = HDR + ROWS * ROW + 54
T_OPEN, T_CLOSE = 0.28, 0.14
RU = dict(zip("йцукенгшщзхъфывапролджэячсмитьбю.ё", "qwertyuiop[]asdfghjkl;'zxcvbnm,./`"))
DIM, TXT = ST.n(0.55, 0.56, 0.52), ST.n(0.92, 0.92, 0.88)


def accent():
    try:
        c = json.load(open(os.path.join(HERE, "colors.json")))["accent"].lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return (0.69, 0.84, 0.0)


def ease_out_quart(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 4


def ease_out_back(t, s=1.4):
    t = max(0.0, min(1.0, t)) - 1
    return 1 + t * t * ((s + 1) * t + s)


def load():
    try: return json.load(open(IDX))
    except Exception: return []


def save(items):
    os.makedirs(D, mode=0o700, exist_ok=True)
    tmp = IDX + ".tmp"; json.dump(items, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, IDX)


def ago(ts):
    d = time.time() - ts
    if d < 60: return "сейчас"
    if d < 3600: return f"{int(d // 60)} мин"
    if d < 86400: return f"{int(d // 3600)} ч"
    return f"{int(d // 86400)} дн"


class Clip(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.acc = accent(); self.items = load(); self.query = ""; self.sel = 0; self.scroll = 0.0; self.scroll_t = 0.0
        self.view = []; self.thumbs = {}; self.t0 = None; self.close_at = None; self.pending = None; self.hlf = None
        self.flash = None; self.win_w, self.win_h = PW + 2 * MARG, PH + 2 * MARG
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY); LS.set_namespace(self, "m2res-clip")
        LS.set_exclusive_zone(self, -1); LS.set_keyboard_mode(self, LS.KeyboardMode.EXCLUSIVE)
        mon = os.environ.get("M2_MON")
        if mon:
            for m in Gdk.Display.get_default().get_monitors():
                if m.get_connector() == mon: LS.set_monitor(self, m)
        self.set_default_size(self.win_w, self.win_h)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw); self.set_child(self.area)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); self.add_controller(kc)
        g = Gtk.GestureClick(); g.connect("pressed", self.on_click); self.area.add_controller(g)
        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL); sc.connect("scroll", self.on_scroll); self.area.add_controller(sc)
        self.connect("map", lambda *_: setattr(self, "t0", time.monotonic()))
        self.area.add_tick_callback(self.tick); self.refilter()

    # ---------- данные ----------
    def refilter(self):
        q = self.query.lower().strip()
        def hit(i): return not q or (i["kind"] == "text" and q in i["text"].lower()) or (i["kind"] == "image" and q in ("image", "картинка", "img"))
        self.view = sorted([i for i in self.items if hit(i)], key=lambda i: (not i.get("pinned"), -i["ts"]))
        self.sel = min(self.sel, max(0, len(self.view) - 1)); self.ensure_visible()

    def ensure_visible(self):
        if self.sel < self.scroll_t: self.scroll_t = float(self.sel)
        elif self.sel > self.scroll_t + ROWS - 1: self.scroll_t = float(self.sel - ROWS + 1)
        self.scroll_t = max(0.0, min(self.scroll_t, max(0, len(self.view) - ROWS)))

    def thumb(self, path, size):
        """превью грузятся в потоке — раньше первый кадр висел 180 мс; пока грузится, возвращаем None"""
        k = (path, size)
        if k not in self.thumbs:
            self.thumbs[k] = None; threading.Thread(target=self._load_thumb, args=(k, path, size), daemon=True).start()
        return self.thumbs[k]

    def _load_thumb(self, k, path, size):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file(path); w, h = pb.get_width(), pb.get_height()
            s = min(size[0] / w, size[1] / h, 1.0 if size[0] > 200 else 9)
            pb = pb.scale_simple(max(1, int(w * s)), max(1, int(h * s)), GdkPixbuf.InterpType.BILINEAR)
            self.thumbs[k] = (pb, w, h); GLib.idle_add(self.area.queue_draw)
        except Exception: pass

    # ---------- действия ----------
    def begin_close(self, then=None):
        if self.close_at: return
        self.close_at = time.monotonic(); self.pending = then

    def choose(self):
        if not self.view: return
        it = self.view[self.sel]
        def go():
            if it["kind"] == "text": subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE).communicate(it["text"].encode())
            else:
                mime = "image/png" if it["file"].endswith("png") else "image/jpeg"
                subprocess.Popen(["wl-copy", "--type", mime], stdin=open(it["file"], "rb"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.flash = time.monotonic(); self.begin_close(go)

    def delete(self):
        if not self.view: return
        it = self.view[self.sel]; self.items = [i for i in self.items if i["id"] != it["id"]]
        if it["kind"] == "image":
            try: os.remove(it["file"])
            except OSError: pass
        save(self.items); self.refilter()

    def pin(self):
        if not self.view: return
        it = self.view[self.sel]; it["pinned"] = not it.get("pinned"); save(self.items); self.refilter()
        self.sel = next((n for n, i in enumerate(self.view) if i["id"] == it["id"]), 0); self.ensure_visible()

    def clear(self):
        for i in self.items:
            if i["kind"] == "image" and not i.get("pinned"):
                try: os.remove(i["file"])
                except OSError: pass
        self.items = [i for i in self.items if i.get("pinned")]; save(self.items); self.refilter()

    def on_key(self, _c, keyval, keycode, state):
        if self.close_at: return True
        K = Gdk; ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK); shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        n = len(self.view)
        if keyval == K.KEY_Escape: self.begin_close(); return True
        if keyval in (K.KEY_Return, K.KEY_KP_Enter): self.choose(); return True
        if keyval == K.KEY_Delete:
            self.clear() if (ctrl and shift) else self.delete(); return True
        if ctrl and keyval in (K.KEY_p, K.KEY_P, K.KEY_Cyrillic_ze, K.KEY_Cyrillic_ZE): self.pin(); return True
        if ctrl and keyval in (K.KEY_u, K.KEY_U): self.query = ""; self.refilter(); return True
        step = {K.KEY_Up: -1, K.KEY_Down: 1, K.KEY_Page_Up: -ROWS, K.KEY_Page_Down: ROWS, K.KEY_Home: -10**6, K.KEY_End: 10**6}.get(keyval)
        if step is not None and n: self.sel = max(0, min(n - 1, self.sel + step)); self.ensure_visible(); return True
        if keyval == K.KEY_BackSpace: self.query = self.query[:-1]; self.refilter(); return True
        if not ctrl and 32 <= keyval < 0x110000:
            try: ch = chr(Gdk.keyval_to_unicode(keyval)) or ""
            except Exception: ch = ""
            if ch.isprintable() and ch: self.query += ch; self.sel = 0; self.refilter()
        return True

    def row_at(self, x, y):
        x -= MARG + PAD; y -= MARG + HDR
        if 0 <= x <= LW and y >= 0:
            r = int((y + self.scroll * ROW) // ROW)
            if 0 <= r < len(self.view) and y < ROWS * ROW: return r
        return -1

    def on_click(self, g, n, x, y):
        r = self.row_at(x, y)
        if r >= 0:
            self.sel = r
            if n >= 2: self.choose()
        elif not (MARG <= x <= MARG + PW and MARG <= y <= MARG + PH): self.begin_close()

    def on_scroll(self, c, dx, dy):
        self.scroll_t = max(0.0, min(self.scroll_t + dy * 2, max(0, len(self.view) - ROWS))); return True

    def tick(self, _w, clock):
        if self.t0 is None: return True
        now = time.monotonic()
        if self.close_at and now - self.close_at > (T_CLOSE if not self.flash else 0.22):
            if self.pending: self.pending()
            self.get_application().quit(); return False
        self.scroll += (self.scroll_t - self.scroll) * 0.3
        ty = self.sel * ROW; self.hlf = ty if self.hlf is None else self.hlf + (ty - self.hlf) * 0.35
        self.area.queue_draw(); return True

    # ---------- рисование ----------
    def rr(self, cr, x, y, w, h, r):
        ST.path(cr, x, y, w, h, r)

    def text(self, cr, s, size, color, x, y, bold=False, anchor="l", alpha=1.0, width=None, lines=1, line_h=None):
        lay = PangoCairo.create_layout(cr); lay.set_font_description(Pango.FontDescription(f"{FONT} {'Bold ' if bold else ''}{size}"))
        lay.set_text(s, -1)
        if width: lay.set_width(width * Pango.SCALE); lay.set_ellipsize(Pango.EllipsizeMode.END if lines == 1 else Pango.EllipsizeMode.END); lay.set_height(-lines if lines > 1 else 0)
        if lines > 1: lay.set_wrap(Pango.WrapMode.WORD_CHAR)
        w, h = lay.get_pixel_size(); ox = x - (w / 2 if anchor == "c" else (w if anchor == "r" else 0))
        cr.set_source_rgba(*color, alpha); cr.move_to(ox, y if lines > 1 else y - h / 2); PangoCairo.show_layout(cr, lay); return w

    def draw(self, _a, cr, w, h):
        if self.t0 is None: return
        now = time.monotonic(); t = now - self.t0
        if self.close_at:
            k = max(0.0, min(1.0, (now - self.close_at) / (T_CLOSE if not self.flash else 0.2))); sc = 1 - 0.03 * k; al = 1 - k
        else:
            k = ease_out_quart(t / T_OPEN); sc = 0.96 + 0.04 * k; al = max(0.0, min(1.0, t / (T_OPEN * 0.6)))
        cr.translate(self.win_w / 2, self.win_h / 2); cr.scale(sc, sc); cr.translate(-self.win_w / 2, -self.win_h / 2)
        cr.push_group(); self.panel(cr, now); cr.pop_group_to_source(); cr.paint_with_alpha(al)

    def panel(self, cr, now):
        A = self.acc; x0, y0 = MARG, MARG
        ST.frame(cr, x0, y0, PW, PH, A, 30)
        # поиск
        sx, sy, sw, sh = x0 + PAD, y0 + 26, PW - 2 * PAD, 56
        self.rr(cr, sx, sy, sw, sh, 28); cr.set_source_rgba(*ST.n(1, 1, 1, 0.05)); cr.fill_preserve(); cr.set_source_rgba(*A, 0.35); cr.set_line_width(1.5); cr.stroke()
        cr.set_source_rgba(*A, 1); self.rr(cr, sx + 14, sy + 14, 62, 28, 14); cr.fill()
        self.text(cr, "CLIP", 14, ST.on_acc, sx + 45, sy + sh / 2, bold=True, anchor="c")
        q = self.query
        if q: wq = self.text(cr, q, 22, TXT, sx + 96, sy + sh / 2, width=sw - 330)
        else: wq = 0; self.text(cr, "поиск по истории…", 20, DIM, sx + 96, sy + sh / 2)
        if int(now * 2) % 2 == 0: cr.set_source_rgba(*A, 0.9); cr.rectangle(sx + 98 + min(wq, sw - 330), sy + 15, 2.5, 26); cr.fill()
        self.text(cr, f"{len(self.view)} / {len(self.items)}", 15, DIM, sx + sw - 26, sy + sh / 2, anchor="r")
        # список
        lx, ly = x0 + PAD, y0 + HDR
        cr.save(); cr.rectangle(lx - 6, ly, LW + 12, ROWS * ROW); cr.clip()
        if self.view and self.hlf is not None:
            hy = ly + self.hlf - self.scroll * ROW
            self.rr(cr, lx, hy + 3, LW, ROW - 6, 16); cr.set_source_rgba(*A, 0.14); cr.fill_preserve()
            cr.set_source_rgba(*A, 0.9); cr.set_line_width(2); cr.stroke()
        for n, it in enumerate(self.view):
            ry = ly + (n - self.scroll) * ROW
            if ry < ly - ROW or ry > ly + ROWS * ROW: continue
            self.row(cr, it, lx, ry, n == self.sel)
        cr.restore()
        if not self.view:
            self.text(cr, "ничего не найдено" if self.items else "история пока пуста — скопируйте что-нибудь", 18, DIM, lx + LW / 2, ly + 130, anchor="c")
        if len(self.view) > ROWS:                                           # полоса прокрутки
            th = ROWS * ROW * ROWS / len(self.view); ty = ly + (ROWS * ROW - th) * (self.scroll / max(1, len(self.view) - ROWS))
            cr.set_source_rgba(*A, 0.45); self.rr(cr, lx + LW + 8, ty, 4, th, 2); cr.fill()
        # предпросмотр
        rx, ry2, rw, rh = x0 + PAD * 2 + LW, y0 + HDR, RW, ROWS * ROW
        self.rr(cr, rx, ry2, rw, rh, 20); cr.set_source_rgba(*ST.n(1, 1, 1, 0.035)); cr.fill_preserve(); cr.set_source_rgba(*A, 0.22); cr.set_line_width(1.5); cr.stroke()
        if self.view: self.preview(cr, self.view[self.sel], rx, ry2, rw, rh)
        # подвал
        self.text(cr, "↑↓ выбор   Enter копировать   Ctrl+P закрепить   Del удалить   Ctrl+Shift+Del очистить   Esc закрыть", 13, ST.n(0.5, 0.51, 0.47), x0 + PW / 2, y0 + PH - 27, anchor="c")
        if self.flash and self.close_at:
            f = max(0.0, 1 - (now - self.flash) / 0.2); cr.set_source_rgba(*A, 0.22 * f); self.rr(cr, x0, y0, PW, PH, 30); cr.fill()

    def row(self, cr, it, x, y, sel):
        A = self.acc; cy = y + ROW / 2; tx = x + 18
        if it.get("pinned"): self.text(cr, "\U000f0403", 15, A, x + 14, cy); tx = x + 40
        if it["kind"] == "image":
            th = self.thumb(it["file"], (64, 44))
            if th:
                pb = th[0]; Gdk.cairo_set_source_pixbuf(cr, pb, tx, cy - pb.get_height() / 2); cr.paint()
                self.text(cr, f"картинка  {th[1]}×{th[2]}", 17, TXT if sel else ST.n(0.78, 0.79, 0.74), tx + 80, cy)
            else: self.text(cr, "картинка", 17, TXT, tx, cy)
        else:
            one = " ".join(it["text"].split()); self.text(cr, one, 17, TXT if sel else ST.n(0.78, 0.79, 0.74), tx, cy, width=LW - (tx - x) - 86)
        self.text(cr, ago(it["ts"]), 13, DIM, x + LW - 14, cy, anchor="r")

    def preview(self, cr, it, x, y, w, h):
        A = self.acc
        if it["kind"] == "image":
            th = self.thumb(it["file"], (w - 40, h - 80))
            if th:
                pb = th[0]; px = x + (w - pb.get_width()) / 2; py = y + 20 + (h - 80 - pb.get_height()) / 2
                Gdk.cairo_set_source_pixbuf(cr, pb, px, py); cr.paint()
                self.text(cr, f"{th[1]}×{th[2]} px   {it.get('size', 0) // 1024} КБ", 14, DIM, x + w / 2, y + h - 28, anchor="c")
        else:
            t = it["text"]; n = t.count("\n") + 1
            self.text(cr, t[:3000], 18, TXT, x + 24, y + 22, width=w - 48, lines=14)
            self.text(cr, f"{len(t)} симв.   {n} стр.", 14, DIM, x + w / 2, y + h - 28, anchor="c")


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.clip")
    def do_activate(self): Clip(self).present()


if __name__ == "__main__":
    App().run()
