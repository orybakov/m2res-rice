#!/usr/bin/env python3
"""m2res player: виджет «пластинка» на GTK4 + layer-shell. Данные через playerctl (MPRIS).
Запуск: LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so python3 player.py  (см. m2res-player)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))  # локальный pycairo
import cairo  # noqa: E402  (до gi — нужен для cairo-контекста в GTK4)
import gi, json, math, subprocess, hashlib, threading, time, urllib.request, urllib.parse

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Gtk4LayerShell as LS
import cairo

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.expanduser("~/.cache/m2res"); os.makedirs(CACHE, exist_ok=True)


def colors():
    try:
        c = json.load(open(os.path.join(HERE, "colors.json")))
    except Exception:
        c = {"accent": "#ff2d4a", "on_accent": "#000000"}
    return c


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def pctl(*args):
    try:
        return subprocess.run(["playerctl", *args], capture_output=True, text=True, timeout=2).stdout.strip()
    except Exception:
        return ""


def fetch_cover(url):
    if not url:
        return None
    p = urllib.parse.urlparse(url)
    if p.scheme == "file":
        return urllib.parse.unquote(p.path)
    path = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest())
    if not os.path.exists(path):
        try:
            urllib.request.urlretrieve(url, path)
        except Exception:
            return None
    return path


class Disc(Gtk.DrawingArea):
    def __init__(self, acc):
        super().__init__()
        self.set_content_width(210); self.set_content_height(210)
        self.acc = acc; self.angle = 0.0; self.playing = False; self.pix = None; self.last = None
        self.set_draw_func(self.draw)
        self.add_tick_callback(self.tick)

    def set_cover(self, path):
        self.pix = None
        if path:
            try:
                self.pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 220, 220, False)
            except Exception:
                pass
        self.queue_draw()

    def tick(self, _w, clock):
        now = clock.get_frame_time() / 1e6                     # время кадра, синхронно с vsync
        dt = 0.0 if self.last is None else min(0.1, now - self.last); self.last = now
        if self.playing:
            self.angle = (self.angle + 0.6 * dt) % (2 * math.pi)  # 0.6 рад/с, как раньше, но не зависит от частоты кадров
            self.queue_draw()
        return True

    def draw(self, _a, cr, w, h):
        cx, cy, R = w / 2, h / 2, min(w, h) / 2 - 4
        cr.translate(cx, cy); cr.rotate(self.angle)
        cr.arc(0, 0, R, 0, 2 * math.pi); cr.set_source_rgb(0.03, 0.03, 0.04); cr.fill()
        for r in range(int(R * .5), int(R), 4):                      # канавки
            cr.arc(0, 0, r, 0, 2 * math.pi); cr.set_source_rgba(1, 1, 1, 0.05); cr.set_line_width(1); cr.stroke()
        lr = R * .62                                                  # этикетка
        cr.arc(0, 0, lr, 0, 2 * math.pi); cr.set_source_rgb(*self.acc); cr.fill()
        ir = lr - 7
        if self.pix:
            cr.save(); cr.arc(0, 0, ir, 0, 2 * math.pi); cr.clip()
            sc = (ir * 2) / min(self.pix.get_width(), self.pix.get_height())
            cr.scale(sc, sc)
            Gdk.cairo_set_source_pixbuf(cr, self.pix, -self.pix.get_width() / 2, -self.pix.get_height() / 2)
            cr.paint(); cr.restore()
        else:
            cr.arc(0, 0, ir, 0, 2 * math.pi); cr.set_source_rgb(0.1, 0.1, 0.12); cr.fill()
        cr.arc(0, 0, 7, 0, 2 * math.pi); cr.set_source_rgb(0.02, 0.02, 0.03); cr.fill()   # отверстие


class Wave(Gtk.DrawingArea):
    def __init__(self, acc):
        super().__init__()
        self.set_content_height(34); self.set_hexpand(True)
        self.acc = acc; self.frac = 0.0; self.phase = 0.0; self.playing = False; self.last = None
        self.length = 0.0; self.base_t = time.monotonic(); self.shown = -1.0
        self.set_draw_func(self.draw)
        self.add_tick_callback(self.tick)
        g = Gtk.GestureClick(); g.connect("pressed", self.on_click); self.add_controller(g)

    def on_click(self, _g, _n, x, _y):
        f = max(0, min(1, x / max(1, self.get_width())))
        ln = pctl("metadata", "mpris:length")
        if ln.isdigit():
            pctl("position", str(int(ln) / 1e6 * f))

    def set_pos(self, frac, length):
        self.frac, self.length, self.base_t = frac, length, time.monotonic()

    def cur(self):
        if self.playing and self.length > 0:
            return max(0.0, min(1.0, self.frac + (time.monotonic() - self.base_t) / self.length))
        return self.frac

    def tick(self, _w, clock):
        now = clock.get_frame_time() / 1e6
        dt = 0.0 if self.last is None else min(0.1, now - self.last); self.last = now
        if self.playing:
            self.phase += 6.0 * dt                             # 6 рад/с
        c = self.cur()
        if self.playing or abs(c - self.shown) > 1e-4:         # на паузе не перерисовываем зря
            self.shown = c; self.queue_draw()
        return True

    def draw(self, _a, cr, w, h):
        mid = h / 2; px = w * self.cur()
        cr.set_line_width(3); cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(px, mid); cr.line_to(w - 4, mid)
        cr.set_source_rgba(*self.acc, 0.35); cr.stroke()
        cr.move_to(4, mid)
        x = 4
        while x <= px:
            amp = 7 if self.playing else 0
            cr.line_to(x, mid + math.sin(x / 9 + self.phase) * amp); x += 2
        cr.set_source_rgb(*self.acc); cr.stroke()
        cr.arc(px, mid, 6, 0, 2 * math.pi); cr.fill()


class Player(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.col = colors(); acc = hex_rgb(self.col["accent"])
        LS.init_for_window(self)
        LS.set_layer(self, LS.Layer.TOP)
        LS.set_anchor(self, LS.Edge.BOTTOM, True); LS.set_anchor(self, LS.Edge.RIGHT, True)
        LS.set_margin(self, LS.Edge.BOTTOM, 24); LS.set_margin(self, LS.Edge.RIGHT, 24)
        LS.set_namespace(self, "m2res-player")
        LS.set_keyboard_mode(self, LS.KeyboardMode.ON_DEMAND)

        css = Gtk.CssProvider()
        css.load_from_data(f"""
        window {{ background: transparent; }}
        .card {{ background: rgba(6,6,8,0.94); border-radius: 26px; padding: 22px; border: 2px solid {self.col['accent']}; }}
        .pill {{ background: rgba(0,0,0,0.85); color: {self.col['accent']}; border: 2px solid {self.col['accent']};
                 border-radius: 8px; padding: 2px 10px; font-family: 'CaskaydiaMono Nerd Font Mono'; font-weight: 800; font-size: 13px; }}
        .title {{ font-size: 15px; }}
        .btn {{ background: transparent; color: {self.col['accent']}; border: none; box-shadow: none; font-size: 30px; padding: 0 10px; min-width: 0; }}
        .btn:hover {{ color: #ffffff; }}
        .play {{ font-size: 42px; }}
        """.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.disc = Disc(acc); self.wave = Wave(acc)
        self.title = Gtk.Label(label="—", xalign=0, ellipsize=3, max_width_chars=26); self.title.add_css_class("pill"); self.title.add_css_class("title")
        self.artist = Gtk.Label(label="", xalign=0, ellipsize=3, max_width_chars=26); self.artist.add_css_class("pill")
        self.play_btn = self.btn("▶", lambda *_: pctl("play-pause"), "play")

        controls = Gtk.Box(spacing=18, halign=Gtk.Align.CENTER)
        controls.append(self.btn("⏮", lambda *_: pctl("previous"))); controls.append(self.play_btn); controls.append(self.btn("⏭", lambda *_: pctl("next")))
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, valign=Gtk.Align.CENTER)
        right.set_size_request(330, -1)
        for wdg in (self.title, self.artist, self.wave, controls):
            right.append(wdg)
        for wdg in (self.title, self.artist):
            wdg.set_halign(Gtk.Align.START)
        card = Gtk.Box(spacing=22); card.add_css_class("card"); card.append(self.disc); card.append(right)
        self.set_child(card)

        k = Gtk.EventControllerKey(); k.connect("key-pressed", lambda _c, kv, *_: app.quit() if kv == Gdk.KEY_Escape else None)
        self.add_controller(k)
        self.last_art = None; self.polling = False
        GLib.timeout_add(500, self.refresh); self.refresh()

    def btn(self, glyph, cb, extra=None):
        b = Gtk.Button(label=glyph); b.add_css_class("btn")
        if extra: b.add_css_class(extra)
        b.connect("clicked", cb); return b

    FMT = "{{status}}\t{{xesam:title}}\t{{xesam:artist}}\t{{mpris:artUrl}}\t{{mpris:length}}\t{{position}}"

    def refresh(self):
        if not self.polling:
            self.polling = True; threading.Thread(target=self.poll, daemon=True).start()
        return True

    def poll(self):
        """всё медленное (playerctl, скачивание обложки) — вне главного потока, чтобы не рвать анимацию"""
        try:
            out = subprocess.run(["playerctl", "metadata", "--format", self.FMT], capture_output=True, text=True, timeout=2).stdout.rstrip("\n")
            if not out:
                st = pctl("status")
                data = (st, "", "", "", "", "") if st else None
            else:
                data = tuple((out.split("\t") + [""] * 6)[:6])
            cover = None
            if data and data[3] != self.last_art:
                cover = fetch_cover(data[3])
            GLib.idle_add(self.apply, data, cover)
        except Exception:
            GLib.idle_add(self.apply, None, None)

    def apply(self, data, cover):
        self.polling = False
        if not data:
            self.disc.playing = self.wave.playing = False
            self.title.set_label("Nothing playing"); self.artist.set_label(""); self.wave.set_pos(0.0, 0.0)
            self.play_btn.set_label("▶"); return False
        status, title, artist, art, ln, pos = data
        playing = status == "Playing"
        self.disc.playing = playing; self.wave.playing = playing
        self.play_btn.set_label("⏸" if playing else "▶")
        if self.title.get_label() != (title or "—"): self.title.set_label(title or "—")
        if self.artist.get_label() != artist: self.artist.set_label(artist)
        self.artist.set_visible(bool(artist))
        if art != self.last_art:
            self.last_art = art; self.disc.set_cover(cover)
        try:
            length = int(ln) / 1e6; self.wave.set_pos(max(0.0, min(1.0, int(pos) / 1e6 / length)), length)
        except Exception:
            self.wave.set_pos(0.0, 0.0)
        return False


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.m2res.player")
    def do_activate(self):
        Player(self).present()


if __name__ == "__main__":
    App().run()
