#!/usr/bin/env python3
"""m2res control — центр управления (SUPER+X): плитки-переключатели и ползунки.
Плитки: DND (уведомления) · CAFFEINE (не блокировать/не гасить) · NIGHT (ночной свет) · MIC (микрофон) · POWER (профиль питания) · ANIM (анимации Hyprland)
· GAME (игровой режим: m2res-game — без анимаций/блюра, DND, performance, освобождает VRAM; широкая плитка).
Ползунки: громкость выхода и микрофона (перетаскивание или колесо); клик по имени устройства — следующий выход.
Нижний ряд: BLUETOOTH · WI-FI · VPN (Happ, только статус) · SOUND (следующий выход). Клавиши: Esc — закрыть · 1–9 — плитки · ←/→ громкость выхода. Запуск: m2res-control toggle"""
import sys, os, json, math, time, subprocess, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from style import ST  # noqa: E402
FONT = ST.font
SINK, SRC = "@DEFAULT_AUDIO_SINK@", "@DEFAULT_AUDIO_SOURCE@"
NIGHT = os.path.expanduser("~/.config/m2res/nightlight.frag")      # старый статичный шейдер (больше не используется)
NIGHTCMD = os.path.expanduser("~/.config/m2res/scripts/m2res-night")
PW, PAD, TW, TH, GAP = 540, 24, 156, 104, 12
GH = 84
H2 = 88; NEWTILES = 4                                   # нижний ряд: BT · WIFI · VPN · SOUND
HDR = 78; GRID_Y = HDR; SL_Y = GRID_Y + 2 * TH + GAP + GAP + GH + GAP + H2 + 30; PH = SL_Y + 2 * 84 + 62
RIGHT, TOP = 28, 52
DIM, TXT = ST.n(0.55, 0.56, 0.52), ST.n(0.92, 0.92, 0.88)
T_OPEN, T_CLOSE = 0.30, 0.16
GAME_ST = os.path.expanduser("~/.cache/m2res/game.json")
GAME = os.path.expanduser("~/.config/m2res/scripts/m2res-game")
POWERS = ["balanced", "performance", "power-saver"]
SHADER = """#version 300 es
precision highp float;
in vec2 v_texcoord;
uniform sampler2D tex;
out vec4 fragColor;
void main() { vec4 c = texture(tex, v_texcoord); fragColor = vec4(c.r, c.g * 0.88, c.b * 0.68, c.a); }
"""


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


def run(*a, t=2.0):
    try: return subprocess.run(a, capture_output=True, text=True, timeout=t).stdout
    except Exception: return ""


def bg(*a):
    subprocess.Popen(list(a), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def hl_eval(code): bg("hyprctl", "eval", code)


def notify(t, b=""): bg("notify-send", "-a", "Control", t, b, "-t", "3500")


def net_state():
    """(bt_hw, bt_on, wifi_hw, wifi_on, vpn_on) без root"""
    bt_hw = os.path.isdir("/sys/class/bluetooth") and bool(os.listdir("/sys/class/bluetooth"))
    bt = bt_hw and "Powered: yes" in run("bluetoothctl", "show", t=2)
    wifi_hw = any(os.path.isdir(f"/sys/class/net/{n}/wireless") for n in os.listdir("/sys/class/net"))
    wifi = wifi_hw and run("nmcli", "radio", "wifi", t=2).strip() == "enabled"
    return bt_hw, bt, wifi_hw, wifi, os.path.exists("/sys/class/net/happ-xray")


def vol(dev):
    o = run("wpctl", "get-volume", dev)
    try: return float(o.split()[1]), "MUTED" in o
    except Exception: return 0.0, False


def sinks():
    """[(id, имя, по умолчанию)] из wpctl status"""
    out, on = [], False
    for ln in run("wpctl", "status").splitlines():
        if "Sinks:" in ln: on = True; continue
        if on and ("Sources:" in ln or "Filters:" in ln or "Streams:" in ln): on = False
        if on:
            s = ln.replace("│", " ").replace("├─", " ").replace("└─", " ").strip()
            if not s: continue
            star = s.startswith("*"); s = s.lstrip("* ").strip()
            if "." in s and s.split(".")[0].isdigit():
                i, rest = s.split(".", 1); nm = rest.split("[vol")[0].strip()
                out.append((int(i), nm, star))
    return out


class State:
    def __init__(self):
        self.bt_hw = self.bt = self.wifi_hw = self.wifi = self.vpn = False
        self.dnd = self.caf = self.night = self.mic_mute = self.anim = self.game = False; self.freed = 0
        self.power = "balanced"; self.v = 0.0; self.vm = False; self.mv = 0.0; self.sink = ""; self.sinks = []
        self.lock = threading.Lock(); self.freeze = 0.0     # после переключения не затираем состояние опросом

    def refresh(self):
        dnd = "do-not-disturb" in run("makoctl", "mode")
        caf = run("systemctl", "--user", "is-active", "hypridle").strip() != "active"
        nst = run(NIGHTCMD, "status", t=4).split()
        night = bool(nst) and nst[0] == "on"; nsub = ("%s → %s" % (nst[2], nst[3])) if night and len(nst) >= 4 else "обычные цвета"
        anim = "true" in run("hyprctl", "getoption", "animations:enabled").splitlines()[0]
        power = run("powerprofilesctl", "get", t=3).strip() or "balanced"
        v, vm = vol(SINK); mv, mm = vol(SRC); sk = sinks(); nets = net_state()
        game, freed = os.path.exists(GAME_ST), 0
        if game:
            try: freed = int(json.load(open(GAME_ST)).get("freed", 0))
            except Exception: pass
        with self.lock:
            if time.monotonic() < self.freeze: return
            self.dnd, self.caf, self.night, self.anim, self.power = dnd, caf, night, anim, power; self.nsub = nsub
            self.game, self.freed = game, freed
            self.bt_hw, self.bt, self.wifi_hw, self.wifi, self.vpn = nets
            self.v, self.vm, self.mv, self.mic_mute = v, vm, mv, mm; self.sinks = sk
            self.sink = next((n for _, n, s in sk if s), "")


class Control(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.acc = accent(); self.st = State(); self.t0 = None; self.close_at = None
        self.sh = {"v": 0.0, "mv": 0.0}; self.press = {}; self.drag = None; self.hover = -1; self.active_once = False
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY); LS.set_namespace(self, "m2res-control")
        MG = 48                                                   # поле под свечение и «выезд» вокруг панели
        for e in (LS.Edge.TOP, LS.Edge.RIGHT): LS.set_anchor(self, e, True)
        LS.set_margin(self, LS.Edge.TOP, TOP - MG); LS.set_margin(self, LS.Edge.RIGHT, RIGHT - MG)
        self.set_default_size(PW + 2 * MG, PH + 2 * MG)
        LS.set_exclusive_zone(self, -1); LS.set_keyboard_mode(self, LS.KeyboardMode.ON_DEMAND)
        mon = os.environ.get("M2_MON")
        if mon:
            for m in Gdk.Display.get_default().get_monitors():
                if m.get_connector() == mon: LS.set_monitor(self, m)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.area = Gtk.DrawingArea(); self.set_child(self.area); self.area.set_draw_func(self.draw)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); self.add_controller(kc)
        mo = Gtk.EventControllerMotion(); mo.connect("motion", self.on_motion); self.area.add_controller(mo)
        g = Gtk.GestureDrag(); g.connect("drag-begin", self.on_begin); g.connect("drag-update", self.on_update); g.connect("drag-end", self.on_end); self.area.add_controller(g)
        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL); sc.connect("scroll", self.on_scroll); self.area.add_controller(sc)
        self.connect("map", lambda *_: setattr(self, "t0", time.monotonic()))
        self.connect("notify::is-active", self.on_active)
        self.area.add_tick_callback(self.tick)
        self.st.refresh(); self.sh["v"], self.sh["mv"] = self.st.v, self.st.mv
        GLib.timeout_add(1500, self.poll)

    # ---------- геометрия ----------
    def origin(self):
        return 48, 48

    def tile_rect(self, i):
        ox, oy = self.origin()
        if i >= 7:
            w2 = (PW - 2 * PAD - (NEWTILES - 1) * GAP) / NEWTILES
            return ox + PAD + (i - 7) * (w2 + GAP), oy + GRID_Y + 2 * (TH + GAP) + GH + GAP, w2, H2
        if i == 6: return ox + PAD, oy + GRID_Y + 2 * (TH + GAP), 3 * TW + 2 * GAP, GH     # GAME — широкая плитка
        c, r = i % 3, i // 3
        return ox + PAD + c * (TW + GAP), oy + GRID_Y + r * (TH + GAP), TW, TH

    def slider_rect(self, k):
        ox, oy = self.origin(); return ox + PAD, oy + SL_Y + k * 84, PW - 2 * PAD, 84

    def hit(self, x, y):
        for i in range(7 + NEWTILES):
            tx, ty, w, h = self.tile_rect(i)
            if tx <= x <= tx + w and ty <= y <= ty + h: return ("tile", i)
        for k in (0, 1):
            sx, sy, w, h = self.slider_rect(k)
            if sx <= x <= sx + w and sy <= y <= sy + h:
                if k == 0 and y < sy + 30 and x > sx + 140: return ("dev", 0)
                return ("slider", k)
        ox, oy = self.origin()
        if not (ox <= x <= ox + PW and oy <= y <= oy + PH): return ("out", 0)
        return ("none", 0)

    # ---------- действия ----------
    def poll(self):
        if self.close_at: return False
        threading.Thread(target=self.st.refresh, daemon=True).start(); return True

    def toggle(self, i):
        s = self.st
        self.press[i] = time.monotonic(); s.freeze = time.monotonic() + 2.5
        if i == 0: s.dnd = not s.dnd; bg("makoctl", "mode", "-s" if False else ("-a" if s.dnd else "-r"), "do-not-disturb")
        elif i == 1:
            s.caf = not s.caf; bg("systemctl", "--user", "stop" if s.caf else "start", "hypridle")
        elif i == 2:
            s.night = not s.night; s.nsub = "включается…" if s.night else "обычные цвета"
            bg(NIGHTCMD, "on" if s.night else "off")        # sunsetr: авто по закату/восходу, плавный переход
        elif i == 3: s.mic_mute = not s.mic_mute; bg("wpctl", "set-mute", SRC, "toggle")
        elif i == 4:
            n = POWERS[(POWERS.index(s.power) + 1) % 3] if s.power in POWERS else "balanced"; s.power = n; bg("powerprofilesctl", "set", n)
        elif i == 6:
            s.freeze = time.monotonic() + 4.5; s.game = not s.game
            if s.game: s.dnd = s.caf = True; s.anim = False; s.freed = 0
            bg(GAME, "on" if s.game else "off")
        elif i == 7:
            if not s.bt_hw: notify("Bluetooth", "адаптер не найден"); return
            s.bt = not s.bt; bg("bluetoothctl", "power", "on" if s.bt else "off")
        elif i == 8:
            if not s.wifi_hw: notify("Wi-Fi", "адаптер не найден"); return
            s.wifi = not s.wifi; bg("nmcli", "radio", "wifi", "on" if s.wifi else "off")
        elif i == 9:
            notify("VPN (Happ)", ("активен: интерфейс happ-xray" if s.vpn else "выключен") + "\nпереключается в самом Happ (окно/трей)")
        elif i == 10: self.cycle_sink(); s.freeze = time.monotonic() + 1.0
        elif i == 5: s.anim = not s.anim; hl_eval("hl.config({ animations = { enabled = %s } })" % ("true" if s.anim else "false"))

    def set_vol(self, k, v):
        v = max(0.0, min(1.0, v)); dev = SINK if k == 0 else SRC
        if k == 0: self.st.v = v
        else: self.st.mv = v
        bg("wpctl", "set-volume", "-l", "1.0", dev, f"{v:.3f}")

    def cycle_sink(self):
        sk = self.st.sinks
        if len(sk) < 2: return
        n = next((i for i, s in enumerate(sk) if s[2]), 0); nxt = sk[(n + 1) % len(sk)]
        self.st.sink = nxt[1]; bg("wpctl", "set-default", str(nxt[0]))
        self.st.sinks = [(i, nm, i == nxt[0]) for i, nm, _ in sk]

    def begin_close(self):
        if not self.close_at: self.close_at = time.monotonic()

    def on_active(self, *_):
        if self.is_active(): self.active_once = True
        elif self.active_once and self.t0 and time.monotonic() - self.t0 > 0.5: self.begin_close()

    def on_key(self, _c, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape: self.begin_close(); return True
        ch = chr(keyval) if 32 < keyval < 127 else ""
        if ch.isdigit() and 1 <= int(ch) <= 9: self.toggle(int(ch) - 1); return True
        if keyval == Gdk.KEY_Left: self.set_vol(0, self.st.v - 0.05); return True
        if keyval == Gdk.KEY_Right: self.set_vol(0, self.st.v + 0.05); return True
        return True

    def on_motion(self, _c, x, y):
        self.ptr = (x, y)
        h = self.hit(x, y); self.hover = h[1] if h[0] == "tile" else -1

    def on_begin(self, g, x, y):
        h = self.hit(x, y); self.drag = None
        if h[0] == "out": self.begin_close()
        elif h[0] == "tile": self.toggle(h[1])
        elif h[0] == "dev": self.cycle_sink()
        elif h[0] == "slider":
            self.drag = h[1]; self.slide(h[1], x)
        self.dx0 = x

    def slide(self, k, x):
        sx, _, w, _ = self.slider_rect(k); self.set_vol(k, (x - sx - 4) / (w - 8))

    def on_update(self, g, ox, oy):
        if self.drag is not None: self.slide(self.drag, self.dx0 + ox)

    def on_end(self, *_): self.drag = None

    def on_scroll(self, c, dx, dy):
        w = getattr(self, "ptr", None)
        k = 1 if w and self.slider_rect(1)[1] <= w[1] else 0
        self.set_vol(k, (self.st.v if k == 0 else self.st.mv) - dy * 0.04); return True

    def get_pointer_pos(self):
        try:
            d = json.loads(run("hyprctl", "-j", "cursorpos", t=0.5)); return d["x"], d["y"]
        except Exception: return None

    def tick(self, _w, clock):
        if self.t0 is None: return True
        now = time.monotonic()
        if self.close_at and now - self.close_at > T_CLOSE: self.get_application().quit(); return False
        for k, tgt in (("v", self.st.v), ("mv", self.st.mv)): self.sh[k] += (tgt - self.sh[k]) * 0.35
        self.area.queue_draw(); return True

    # ---------- рисование ----------
    def rr(self, cr, x, y, w, h, r):
        ST.path(cr, x, y, w, h, r)

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
        cr.translate(ox + PW, oy); cr.scale(sc, sc); cr.translate(-(ox + PW), -oy + dy)       # якорь — верхний правый угол
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
        A = self.acc; ox, oy = self.origin(); s = self.st
        ST.frame(cr, ox, oy, PW, PH, A, 28)
        up = 0
        try: up = float(open("/proc/uptime").read().split()[0])
        except Exception: pass
        self.text(cr, "CONTROL", 24, A, ox + PAD + 2, oy + 38, bold=True)
        self.text(cr, f"{os.environ.get("M2_HOST") or os.uname().nodename}  ·  up {int(up // 3600)}ч {int(up % 3600 // 60)}м", 14, DIM, ox + PW - PAD - 2, oy + 38, anchor="r")
        cr.set_source_rgba(*A, 0.28); cr.rectangle(ox + PAD, oy + 60, PW - 2 * PAD, 2); cr.fill()
        names = [("DND", "\U000f009b", s.dnd, "не беспокоить" if s.dnd else "уведомления"),
                 ("CAFFEINE", "\U000f0176", s.caf, "не гасить экран" if s.caf else "автоблокировка"),
                 ("NIGHT", "\U000f0594", s.night, getattr(s, "nsub", "обычные цвета")),
                 ("MIC", "\U000f036d" if s.mic_mute else "\U000f036c", not s.mic_mute, "включён" if not s.mic_mute else "выключен"),
                 ("POWER", "\U000f0e7c", s.power != "power-saver", s.power),
                 ("ANIM", "\U000f0e1f", s.anim, "включены" if s.anim else "выключены"),
                 ("GAME", "\U000f0297", s.game, ("VRAM −%d МБ · DND · без анимаций" % s.freed if s.freed else "включается…  DND · без анимаций") if s.game else "освободить VRAM · без анимаций · DND")]
        short = lambda x, n=12: x if len(x) <= n else x[:n - 1] + "…"
        names += [("BLUETOOTH", "\U000f00af" if s.bt else "\U000f00b2", s.bt, ("включён" if s.bt else "выключен") if s.bt_hw else "нет адаптера"),
                  ("WI-FI", "\U000f05a9" if s.wifi else "\U000f05aa", s.wifi, ("включён" if s.wifi else "выключен") if s.wifi_hw else "нет адаптера"),
                  ("VPN", "\U000f0582", s.vpn, "Happ · вкл" if s.vpn else "выключен"),
                  ("SOUND", "\U000f057e", False, short(s.sink or "нет выхода") if len(s.sinks) > 1 else short(s.sink or "нет выхода") + "")]
        for i, (nm, ic, on, sub) in enumerate(names): self.tile(cr, i, nm, ic, on, sub, now, t)
        # ползунки
        for k, (lab, key, muted) in enumerate((("OUTPUT", "v", s.vm), ("INPUT", "mv", s.mic_mute))):
            sx, sy, sw, sh = self.slider_rect(k); d = max(0.0, min(1.0, (t - 0.25 - 0.06 * k) / 0.3)); a = d
            self.text(cr, lab, 14, A, sx + 2, sy + 18, bold=True, alpha=a)
            if k == 0 and s.sink: self.text(cr, ("⇄  " + s.sink)[:46], 13, DIM, sx + sw - 2, sy + 18, anchor="r", alpha=a)
            val = self.sh[key]; bx, by, bw, bh = sx, sy + 38, sw - 70, 20
            self.rr(cr, bx, by, bw, bh, 10); cr.set_source_rgba(1, 1, 1, 0.08 * a); cr.fill()
            fw = max(bh, bw * val)
            col = ST.n(0.45, 0.46, 0.42) if muted else A
            self.rr(cr, bx, by, fw, bh, 10); cr.set_source_rgba(*col, a); cr.fill()
            cr.set_source_rgba(0.95, 0.95, 0.9, a); cr.arc(bx + fw - 10, by + 10, 6, 0, 7); cr.fill()
            self.text(cr, f"{int(round(val * 100))}%", 18, TXT if not muted else DIM, sx + sw, by + 10, bold=True, anchor="r", alpha=a)
        self.text(cr, "клик · 1–9 · колесо по ползунку · Esc", 13, ST.n(0.45, 0.46, 0.42), ox + PW / 2, oy + PH - 24, anchor="c")

    def tile(self, cr, i, nm, ic, on, sub, now, t):
        A = self.acc; x, y, w, h = self.tile_rect(i)
        d = max(0.0, min(1.0, (t - 0.04 * i) / 0.3)); pop = ease_out_back(d, 1.8); a = d
        pr = self.press.get(i); k = 1.0
        if pr is not None:
            q = (now - pr) / 0.35
            if q < 1: k = 1 + 0.08 * math.sin(q * math.pi) * (1 - q * 0.4)
        k *= (0.9 + 0.1 * pop) * (1.025 if self.hover == i else 1.0)
        cx, cy = x + w / 2, y + h / 2
        cr.save(); cr.translate(cx, cy); cr.scale(k, k); cr.translate(-w / 2, -h / 2)
        if on:
            for j, aa in ((8, 0.05), (4, 0.09)): cr.set_source_rgba(*A, aa * a); self.rr(cr, -j, -j, w + 2 * j, h + 2 * j, 22 + j); cr.fill()
            self.rr(cr, 0, 0, w, h, 22); cr.set_source_rgba(*A, 0.95 * a); cr.fill(); fg = (0.10, 0.13, 0.0); sub_c = (0.20, 0.26, 0.0)
        else:
            self.rr(cr, 0, 0, w, h, 22); cr.set_source_rgba(1, 1, 1, 0.055 * a); cr.fill_preserve(); cr.set_source_rgba(*A, 0.22 * a); cr.set_line_width(1.5); cr.stroke()
            fg = ST.n(0.85, 0.86, 0.80); sub_c = DIM
        if w > TW * 2:                                   # широкая плитка: иконка слева, текст справа
            self.text(cr, ic, 38, fg, 24, h / 2, alpha=a)
            self.text(cr, nm, 17, fg, 84, h / 2 - 13, bold=True, alpha=a)
            self.text(cr, sub, 13, sub_c, 84, h / 2 + 14, alpha=a)
        elif i >= 7:
            self.text(cr, ic, 28, fg, 16, 28, alpha=a)
            self.text(cr, nm, 12, fg, 16, h - 34, bold=True, alpha=a)
            self.text(cr, sub, 10, sub_c, 16, h - 16, alpha=a)
        else:
            self.text(cr, ic, 34, fg, 20, 36, alpha=a)
            self.text(cr, nm, 15, fg, 20, h - 38, bold=True, alpha=a)
            self.text(cr, sub, 12, sub_c, 20, h - 18, alpha=a)
        if i < 9: self.text(cr, str(i + 1), 12, sub_c, w - 16, 16, anchor="r", alpha=0.7 * a)
        cr.restore()


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.control")
    def do_activate(self): Control(self).present()


if __name__ == "__main__":
    App().run()
