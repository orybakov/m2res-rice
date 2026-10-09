#!/usr/bin/env python3
"""m2res launcher — меню приложений в стиле райса (GTK4 + layer-shell + cairo).
Сетка плиток с иконками, нечёткий поиск (в т.ч. на русской раскладке), частота запуска, категории,
`>команда` — shell, `=2+2*3` — калькулятор (+ единицы и валюты через qalc: `= 5 km to mi`, `= 100 usd to eur`),
`:smile` — эмодзи (Enter копирует), `w ` — открытые окна (Enter — фокус), `f ` — файлы и папки в ~ (Enter — открыть, Ctrl+Enter — копировать путь),
`g `/`? ` Google · `y ` Яндекс · `ddg ` DuckDuckGo · `yt ` YouTube · `gh ` GitHub — поиск в вебе, у приложений — быстрые действия (New Window…).
Клавиши: стрелки — выбор · Enter — запуск · Tab/Shift+Tab — категория · Esc — закрыть · Ctrl+U — очистить.
Запуск: m2res-launcher toggle"""
import sys, os, json, math, time, re, ast, subprocess, operator, threading, unicodedata, urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import cairo  # noqa: E402
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gdk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf, Pango, PangoCairo, Gtk4LayerShell as LS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
USAGE = os.path.expanduser("~/.local/share/m2res/launcher-usage.json")
FONT = "CaskaydiaMono Nerd Font Mono"
COLS, ROWS = 6, 3
TILE_W, TILE_H, GAP = 180, 150, 12
PAD = 22
PW = PAD * 2 + COLS * TILE_W + (COLS - 1) * GAP            # 1174
GRID_Y = 172
PH = GRID_Y + ROWS * TILE_H + (ROWS - 1) * GAP + 66        # 712
MARG = 36                                                   # поле под свечение вокруг панели
T_OPEN, T_CLOSE = 0.30, 0.16
ICON = 64

CATS = [("ALL", None), ("RECENT", "recent"), ("DEV", ("Development", "IDE", "TextEditor", "Debugger")),
        ("WEB", ("Network", "WebBrowser", "Email", "Chat", "InstantMessaging")),
        ("MEDIA", ("AudioVideo", "Audio", "Video", "Graphics", "Player", "Photography")),
        ("GAMES", ("Game",)), ("SYSTEM", ("System", "Settings", "Utility", "FileManager", "TerminalEmulator", "Monitor"))]

RU = dict(zip("йцукенгшщзхъфывапролджэячсмитьбю.ё", "qwertyuiop[]asdfghjkl;'zxcvbnm,./`"))


def ease_out_quart(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 4


def ease_out_back(t, s=1.6):
    t = max(0.0, min(1.0, t)) - 1
    return 1 + t * t * ((s + 1) * t + s)


def ease_out_cubic(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 3


def accent():
    try:
        c = json.load(open(os.path.join(HERE, "colors.json")))["accent"].lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return (0.69, 0.84, 0.0)


# ---------------- данные ----------------
class AppRec:
    __slots__ = ("id", "name", "generic", "kw", "exe", "desc", "cats", "icon", "path", "info", "lname", "lgen", "lkw", "bucket", "stem", "ini", "actions")


def load_usage():
    try: return json.load(open(USAGE))
    except Exception: return {}


def save_usage(u):
    try:
        os.makedirs(os.path.dirname(USAGE), exist_ok=True)
        json.dump(u, open(USAGE, "w"))
    except Exception: pass


def load_apps():
    out, seen = [], set()
    for ai in Gio.AppInfo.get_all():
        if not ai.should_show(): continue
        name = ai.get_display_name() or ai.get_name() or ""
        if not name or (ai.get_id() or name) in seen: continue
        seen.add(ai.get_id() or name)
        r = AppRec(); r.id = ai.get_id() or name; r.name = name; r.info = ai
        di = ai if isinstance(ai, Gio.DesktopAppInfo) else None
        r.generic = (di.get_generic_name() if di else "") or ""
        r.kw = " ".join(di.get_keywords() or []) if di else ""
        r.cats = set((di.get_categories() or "").split(";")) if di else set()
        r.path = di.get_filename() if di else None
        r.desc = ai.get_description() or r.generic or ""
        cl = ai.get_commandline() or ""
        r.exe = os.path.basename(cl.split()[0]) if cl.split() else ""
        ic = ai.get_icon()
        r.icon = None
        if isinstance(ic, Gio.ThemedIcon): r.icon = ic.get_names()[0] if ic.get_names() else None
        elif isinstance(ic, Gio.FileIcon): r.icon = ic.get_file().get_path()
        r.lname, r.lgen, r.lkw = name.lower(), r.generic.lower(), r.kw.lower()
        r.ini = "".join(w[0] for w in re.split(r"[\s\-_.]+", r.lname) if w)
        r.stem = re.sub(r"\.desktop$", "", r.id).lower()
        r.actions = []
        if di:
            try: r.actions = [(a, di.get_action_name(a)) for a in (di.list_actions() or [])][:4]
            except Exception: r.actions = []
        r.bucket = set()
        for label, cs in CATS:
            if isinstance(cs, tuple) and r.cats & set(cs): r.bucket.add(label)
        out.append(r)
    out.sort(key=lambda a: a.lname)
    return out


def fuzzy(q, s):
    """0 — нет совпадения; чем больше, тем лучше"""
    if not s: return 0
    if s == q: return 120
    if s.startswith(q): return 100
    for w in re.split(r"[\s\-_./]+", s):
        if w.startswith(q): return 82
    i = s.find(q)
    if i >= 0: return 66 - min(i, 20)
    if len(q) < 3: return 0                         # подпоследовательность: только компактная ("ffx" → firefox)
    first, last = -1, -1
    for ch in q:
        j = s.find(ch, last + 1)
        if j < 0: return 0
        if first < 0: first = j
        last = j
    span = last - first + 1
    if span > len(q) + 2: return 0
    return max(8, 36 - (span - len(q)) * 4)


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}
_FN = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log, "ln": math.log, "abs": abs, "round": round}
_CONST = {"pi": math.pi, "e": math.e}


def calc(expr):
    def ev(n):
        if isinstance(n, ast.Expression): return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 1000: raise ValueError
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)): return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        if isinstance(n, ast.Name) and n.id in _CONST: return _CONST[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FN and not n.keywords:
            return _FN[n.func.id](*[ev(a) for a in n.args])
        raise ValueError
    try:
        v = ev(ast.parse(expr.replace("^", "**").replace(",", ".").replace("×", "*").replace("÷", "/"), mode="eval"))
        return ("%.10g" % v) if isinstance(v, float) else str(v)
    except Exception:
        return None


# ---------------- расширения: эмодзи / окна / файлы / веб ----------------
SEARCH = {"g": ("Google", "https://www.google.com/search?q="), "?": ("Google", "https://www.google.com/search?q="),
          "y": ("Яндекс", "https://yandex.ru/search/?text="), "ddg": ("DuckDuckGo", "https://duckduckgo.com/?q="),
          "yt": ("YouTube", "https://www.youtube.com/results?search_query="), "gh": ("GitHub", "https://github.com/search?q=")}
RU_EMOJI = {"😀": "улыбка радость", "😂": "смех ржу лол", "🤣": "ржу смех", "😊": "улыбка", "😍": "влюблен любовь", "😘": "поцелуй",
            "😎": "круто очки", "😭": "плачу слезы", "😢": "грусть слеза", "😡": "злой гнев", "😱": "ужас крик", "🤔": "думаю мысль",
            "😴": "сон спать", "🥳": "праздник вечеринка", "😅": "неловко пот", "🙃": "ирония", "😉": "подмигивание", "🤯": "взрыв мозг",
            "👍": "палец вверх класс ок лайк", "👎": "палец вниз дизлайк", "👋": "привет пока рука", "🙏": "спасибо молитва пожалуйста",
            "👏": "аплодисменты браво", "💪": "сила мышца", "🤝": "рукопожатие договор", "👀": "глаза смотрю", "✌️": "мир победа",
            "❤️": "сердце любовь красное", "💔": "разбитое сердце", "🔥": "огонь жара круто", "⭐": "звезда", "✨": "блеск искры",
            "🎉": "праздник ура", "🚀": "ракета запуск", "💀": "череп смерть", "💩": "кака", "🐛": "баг жук", "🐍": "змея питон",
            "☕": "кофе чай", "🍺": "пиво", "🍕": "пицца", "🎮": "игра геймпад", "💻": "ноутбук компьютер", "📱": "телефон",
            "✅": "галочка готово", "❌": "крестик нет", "⚠️": "предупреждение внимание", "💡": "идея лампочка", "🔒": "замок закрыто",
            "🔑": "ключ", "📌": "кнопка закрепить", "📎": "скрепка", "📝": "заметка запись", "💰": "деньги", "📈": "рост график",
            "📉": "падение график", "🌙": "луна ночь", "☀️": "солнце", "🌧️": "дождь", "❄️": "снег холод", "🏠": "дом", "🚗": "машина"}
COMMON_EMOJI = list(RU_EMOJI)[:36]
_EMOJI = None


def load_emoji():
    global _EMOJI
    if _EMOJI is not None: return _EMOJI
    out = []
    for lo, hi in ((0x1F300, 0x1F64F), (0x1F680, 0x1F6FF), (0x1F900, 0x1F9FF), (0x1FA70, 0x1FAFF), (0x2600, 0x27BF)):
        for cp in range(lo, hi + 1):
            if 0x1F3FB <= cp <= 0x1F3FF: continue
            ch = chr(cp); nm = unicodedata.name(ch, "")
            if not nm or nm.startswith(("VARIATION", "CIRCLED", "BLACK ", "WHITE ", "DINGBAT")): continue
            if cp < 0x2800: ch += "\ufe0f"
            out.append((ch, nm.lower()))
    have = {c for c, _ in out}
    for c in RU_EMOJI:
        if c not in have and c.rstrip("\ufe0f") not in {h.rstrip("\ufe0f") for h in have}: out.append((c, ""))
    _EMOJI = out; return out


def emoji_search(q, usage):
    toks = q.lower().split()
    base = load_emoji(); names = {c: n for c, n in base}
    if not toks:
        rec = sorted([k[6:] for k in usage if k.startswith("emoji:")], key=lambda c: -usage["emoji:" + c][1])[:24]
        order = rec + [c for c in COMMON_EMOJI if c not in rec]
        return [(c, names.get(c) or RU_EMOJI.get(c, "")) for c in order]
    sc = []
    for ch, nm in base:
        hay = nm + " " + RU_EMOJI.get(ch, "")
        if all(t in hay for t in toks):
            s = 50 + (30 if any(w.startswith(toks[0]) for w in hay.split()) else 0) - len(nm) * 0.1
            u = usage.get("emoji:" + ch)
            if u: s += min(15, math.log1p(u[0]) * 5)
            sc.append((s, ch, nm or RU_EMOJI.get(ch, "")))
    sc.sort(key=lambda x: -x[0])
    return [(c, n) for _, c, n in sc[:120]]


def list_windows():
    try:
        cl = json.loads(subprocess.run(["hyprctl", "-j", "clients"], capture_output=True, text=True, timeout=2).stdout)
    except Exception: return []
    cl = [c for c in cl if c.get("mapped") and c.get("class")]
    cl.sort(key=lambda c: c.get("focusHistoryID", 99))
    return [dict(address=c["address"], title=c.get("title") or c["class"], cls=c["class"], ws=(c.get("workspace") or {}).get("name", "?")) for c in cl]


def find_files(pat):
    if not pat: return []
    try:
        o = subprocess.run(["fd", "-i", "--max-results", "60", "--max-depth", "7", "--color", "never", pat, os.path.expanduser("~")],
                           capture_output=True, text=True, timeout=3).stdout
    except Exception: return []
    return [l for l in o.splitlines() if l][:60]


def qalc(expr):
    try:
        r = subprocess.run(["qalc", "-t", expr], capture_output=True, text=True, timeout=4)
        o = r.stdout.strip().splitlines()
        o = [l for l in o if l.strip() and not l.lower().startswith(("warning", "error"))]
        res = o[-1].strip() if o and r.returncode == 0 else None
        m = re.match(r"^(.+?)\s+(?:to|в|→)\s+([A-Za-z°µ/²³]+)$", expr.strip())
        if res and m and " + " in res:           # qalc сам дробит «3 mi + 188 yd + …» — просим одно число в нужной единице
            r2 = subprocess.run(["qalc", "-t", f"({m.group(1)}) / (1 {m.group(2)})"], capture_output=True, text=True, timeout=4)
            n = r2.stdout.strip().splitlines()[-1].strip() if r2.stdout.strip() else ""
            if re.match(r"^-?[0-9.,eE+−-]+$", n): res = f"{n} {m.group(2)}"
        return res
    except Exception: return None


def short_path(p):
    h = os.path.expanduser("~"); return "~" + p[len(h):] if p.startswith(h) else p


# ---------------- окно ----------------
class Launcher(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.acc = accent()
        self.apps = load_apps(); self.usage = load_usage()
        self.icons = {}; self.query = ""; self.cat = 0
        self.results = []; self.sel = 0; self.scroll = 0.0; self.scroll_t = 0.0
        self.hl = None                          # анимированная рамка выделения (x, y)
        self.t0 = None; self.close_at = None; self.pending = None
        self.result_t = 0.0; self.hover = -1; self.last_mouse = (-1, -1)
        self.caret_t = time.monotonic(); self.busy_until = 0.0
        self.token = 0; self.ctrl_enter = False

        self.win_w, self.win_h = PW + 2 * MARG, PH + 2 * MARG
        LS.init_for_window(self); LS.set_layer(self, LS.Layer.OVERLAY)
        LS.set_namespace(self, "m2res-launcher"); LS.set_exclusive_zone(self, -1)
        LS.set_keyboard_mode(self, LS.KeyboardMode.EXCLUSIVE)
        mon = os.environ.get("M2_MON")
        if mon:
            for m in Gdk.Display.get_default().get_monitors():
                if m.get_connector() == mon: LS.set_monitor(self, m)
        self.set_default_size(self.win_w, self.win_h)
        css = Gtk.CssProvider(); css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw); self.set_child(self.area)

        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self.on_key); self.add_controller(kc)
        mo = Gtk.EventControllerMotion(); mo.connect("motion", self.on_motion); self.area.add_controller(mo)
        ck = Gtk.GestureClick(); ck.set_button(1); ck.connect("pressed", self.on_click); self.area.add_controller(ck)
        sc = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        sc.connect("scroll", self.on_scroll); self.area.add_controller(sc)
        self.connect("map", lambda *_: self.on_map())
        self.theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        self.refilter(reset=True)
        for k, a in self.results[:COLS * ROWS]:                    # видимые иконки грузим до показа, остальные — в простое
            if k == "app": self.icon(a)
        self.warm = iter([a for a in self.apps]); GLib.idle_add(self.warm_icons)
        self.area.add_tick_callback(self.tick)

    # ---------- иконки ----------
    def icon(self, r):
        key = r.icon or r.id
        if key in self.icons: return self.icons[key]
        pb = None
        try:
            path = None
            if r.icon and r.icon.startswith("/"): path = r.icon
            elif r.icon:
                p = self.theme.lookup_icon(r.icon, None, ICON, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags.NONE)
                f = p.get_file() if p else None
                path = f.get_path() if f else None
            if path: pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, ICON + 8, ICON + 8)
        except Exception:
            pb = None
        self.icons[key] = pb
        return pb

    def warm_icons(self):
        for _ in range(3):
            a = next(self.warm, None)
            if a is None: return False
            self.icon(a)
        return True

    # ---------- поиск ----------
    def score_usage(self, r):
        u = self.usage.get(r.id)
        if not u: return 0.0
        days = (time.time() - u[1]) / 86400
        return min(12.0, math.log1p(u[0]) * 4) * (0.5 + 0.5 / (1 + days))

    def refilter(self, reset=False):
        q = self.query.strip()
        alt = "".join(RU.get(c, c) for c in q.lower())       # запрос, набранный на русской раскладке → латиница
        special = None
        self.token += 1
        m_pref = re.match(r"^(\?|g|y|ddg|yt|gh|w|f)\s", alt)
        if q.startswith(">"): special = ("cmd", q[1:].strip())
        elif q.startswith("="): special = ("calc", q[1:].strip())
        elif q.startswith(":"): special = ("emoji", q[1:].strip())
        elif m_pref: special = ("pref", m_pref.group(1), q[m_pref.end():].strip())
        lab, cs = CATS[self.cat]
        items = []
        if special and special[0] == "emoji":
            items = [("emoji", e) for e in emoji_search(special[1], self.usage)]
        elif special and special[0] == "pref":
            pf, rest = special[1], special[2]
            if pf == "w":
                ws = list_windows(); rl = rest.lower(); ral = "".join(RU.get(c, c) for c in rl)
                items = [("win", w) for w in ws if not rest or max(fuzzy(rl, w["title"].lower()), fuzzy(rl, w["cls"].lower()), fuzzy(ral, w["title"].lower()), fuzzy(ral, w["cls"].lower())) > 0]
            elif pf == "f":
                items = [("info", ("Поиск файлов…" if rest else "Введите часть имени файла", "f имя · ищет в ~, до 60 результатов"))]
                if rest: threading.Thread(target=self.run_async, args=(self.token, "file", rest), daemon=True).start()
            else:
                eng, url = SEARCH[pf]
                items = [("web", (eng, rest, url + urllib.parse.quote(rest)))] if rest else [("info", (eng, "введите запрос и Enter"))]
        elif special:
            if special[0] == "cmd":
                items.append(("cmd", special[1]))
            else:
                v = calc(special[1]) if special[1] else None
                items.append(("calc", (special[1], v)))
                if special[1] and v is None:
                    threading.Thread(target=self.run_async, args=(self.token, "qalc", special[1]), daemon=True).start()
        elif not q:
            pool = self.apps
            if cs == "recent":
                pool = sorted([a for a in self.apps if a.id in self.usage], key=lambda a: -self.usage[a.id][1])[:ROWS * COLS * 2]
            elif cs:
                pool = [a for a in self.apps if lab in a.bucket]
            if cs != "recent":
                pool = sorted(pool, key=lambda a: (-self.score_usage(a), a.lname))
            items = [("app", a) for a in pool]
        else:
            ql, scored = q.lower(), []
            for a in self.apps:
                if cs and cs != "recent" and lab not in a.bucket: continue
                s = 0
                for qq in {ql, alt}:
                    s = max(s, fuzzy(qq, a.lname), fuzzy(qq, a.lgen) * .5, fuzzy(qq, a.lkw) * .4, fuzzy(qq, a.exe.lower()) * .45, fuzzy(qq, a.id.lower()) * .3)
                    if len(qq) >= 2 and a.ini.startswith(qq): s = max(s, 90 - (len(a.ini) - len(qq)) * 3)   # инициалы: vsc → Visual Studio Code
                    if qq == a.exe.lower() or qq == a.stem: s = max(s, 140)          # точное системное имя команды / .desktop — выше всего
                if s > 0: scored.append((s + self.score_usage(a), a))
            scored.sort(key=lambda x: (-x[0], x[1].lname))
            for n, (sc_, a) in enumerate(scored):
                items.append(("app", a))
                if n < 3 and sc_ >= 82 and a.actions:
                    items += [("act", (a, aid, nm)) for aid, nm in a.actions]
        self.results = items; self.result_t = time.monotonic()
        if reset or True: self.sel = 0; self.scroll = self.scroll_t = 0.0
        self.poke()

    def run_async(self, token, kind, arg):
        res = find_files(arg) if kind == "file" else qalc(arg)
        GLib.idle_add(self.apply_async, token, kind, arg, res)

    def apply_async(self, token, kind, arg, res):
        if token != self.token: return False
        if kind == "file":
            self.results = [("file", f) for f in res] or [("info", ("Ничего не найдено", "по запросу «%s»" % arg))]
        else:
            self.results = [("calc", (arg, res))]
        self.result_t = time.monotonic(); self.sel = 0; self.scroll = self.scroll_t = 0.0; self.poke(); return False

    def poke(self, dur=0.6):
        self.busy_until = max(self.busy_until, time.monotonic() + dur); self.caret_t = time.monotonic()

    # ---------- ввод ----------
    def on_map(self):
        self.t0 = time.monotonic(); self.poke(1.0)

    def tile_at(self, x, y):
        x -= MARG + PAD; y -= MARG + GRID_Y
        if x < 0 or y < 0: return -1
        c, r = int(x // (TILE_W + GAP)), int(y // (TILE_H + GAP))
        if c >= COLS or r >= ROWS: return -1
        if x - c * (TILE_W + GAP) > TILE_W or y - r * (TILE_H + GAP) > TILE_H: return -1
        i = (r + int(round(self.scroll_t))) * COLS + c
        return i if i < len(self.results) else -1

    def chip_at(self, x, y):
        if not (MARG + 96 <= y <= MARG + 136): return -1
        cx = MARG + PAD
        for i, (lab, _) in enumerate(CATS):
            w = len(lab) * 9 + 30
            if cx <= x <= cx + w: return i
            cx += w + 8
        return -1

    def on_motion(self, _c, x, y):
        if abs(x - self.last_mouse[0]) + abs(y - self.last_mouse[1]) < 3: return
        self.last_mouse = (x, y)
        i = self.tile_at(x, y)
        if i >= 0 and i != self.sel: self.sel = i; self.poke()

    def on_click(self, _g, _n, x, y):
        if self.close_at: return
        ci = self.chip_at(x, y)
        if ci >= 0: self.cat = ci; self.refilter(); return
        i = self.tile_at(x, y)
        if i >= 0: self.sel = i; self.launch()

    def on_scroll(self, _c, _dx, dy):
        self.move(0, 1 if dy > 0 else -1); return True

    def move(self, dc, dr):
        n = len(self.results)
        if not n: return
        i = self.sel + dc + dr * COLS
        if dc and not dr: i = max(0, min(n - 1, i))
        elif dr: i = max(0, min(n - 1, i)) if 0 <= i < n or (dr > 0 and self.sel // COLS < (n - 1) // COLS) else self.sel
        self.sel = max(0, min(n - 1, i)); self.ensure_visible(); self.poke()

    def ensure_visible(self):
        r = self.sel // COLS
        if r < self.scroll_t: self.scroll_t = float(r)
        elif r > self.scroll_t + ROWS - 1: self.scroll_t = float(r - ROWS + 1)

    def on_key(self, _c, keyval, keycode, state):
        if self.close_at: return True
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        K = Gdk
        if keyval == K.KEY_Escape: self.begin_close(); return True
        if keyval in (K.KEY_Return, K.KEY_KP_Enter): self.ctrl_enter = ctrl; self.launch(); return True
        if keyval in (K.KEY_Left,): self.move(-1, 0); return True
        if keyval in (K.KEY_Right,): self.move(1, 0); return True
        if keyval in (K.KEY_Up,): self.move(0, -1); return True
        if keyval in (K.KEY_Down,): self.move(0, 1); return True
        if keyval in (K.KEY_Page_Down,): self.move(0, ROWS); return True
        if keyval in (K.KEY_Page_Up,): self.move(0, -ROWS); return True
        if keyval == K.KEY_Home: self.sel = 0; self.ensure_visible(); self.poke(); return True
        if keyval == K.KEY_End: self.sel = max(0, len(self.results) - 1); self.ensure_visible(); self.poke(); return True
        if keyval in (K.KEY_Tab, K.KEY_ISO_Left_Tab):
            back = keyval == K.KEY_ISO_Left_Tab or bool(state & Gdk.ModifierType.SHIFT_MASK)
            self.cat = (self.cat + (-1 if back else 1)) % len(CATS); self.refilter(); return True
        if keyval == K.KEY_BackSpace:
            if ctrl: self.query = re.sub(r"\S*\s*$", "", self.query)
            else: self.query = self.query[:-1]
            self.refilter(); return True
        if ctrl and keyval in (K.KEY_u, K.KEY_U, 0x6d7):                # Ctrl+U (и Ctrl+Г на русской)
            self.query = ""; self.refilter(); return True
        if ctrl or (state & Gdk.ModifierType.ALT_MASK): return True
        ch = Gdk.keyval_to_unicode(keyval)
        if ch >= 32 and ch != 127:
            self.query += chr(ch); self.refilter()
        return True

    # ---------- запуск ----------
    def begin_close(self, then=None):
        if self.close_at is None: self.close_at = time.monotonic(); self.pending = then; self.poke(0.5)

    def launch(self):
        if not self.results: return
        kind, v = self.results[self.sel]
        if kind == "app":
            self.usage[v.id] = [(self.usage.get(v.id) or [0, 0])[0] + 1, time.time()]; save_usage(self.usage)
            def go():
                try:
                    if v.path: subprocess.Popen(["gio", "launch", v.path], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else: v.info.launch([], None)
                except Exception as e: print("launch:", e, file=sys.stderr)
            self.begin_close(go)
        elif kind == "cmd" and v:
            self.begin_close(lambda: subprocess.Popen(["sh", "-c", v], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        elif kind == "emoji":
            self.usage["emoji:" + v[0]] = [(self.usage.get("emoji:" + v[0]) or [0, 0])[0] + 1, time.time()]; save_usage(self.usage)
            self.begin_close(lambda: subprocess.Popen(["wl-copy", v[0]], start_new_session=True))
        elif kind == "win":
            # с задержкой: при закрытии слоя композитор возвращает фокус прежнему окну — перебиваем его после этого
            self.begin_close(lambda: subprocess.Popen(["sh", "-c", "sleep 0.3; hyprctl eval \"hl.dispatch(hl.dsp.focus({ window = 'address:$1' }))\"", "_", v["address"]],
                                                      start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        elif kind == "file":
            if self.ctrl_enter: self.begin_close(lambda: subprocess.Popen(["wl-copy", v], start_new_session=True))
            else: self.begin_close(lambda: subprocess.Popen(["xdg-open", v], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        elif kind == "web":
            self.begin_close(lambda: subprocess.Popen(["xdg-open", v[2]], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        elif kind == "act":
            app, aid, _nm = v
            def go():
                try: app.info.launch_action(aid, None)
                except Exception as e: print("action:", e, file=sys.stderr)
            self.begin_close(go)
        elif kind == "calc" and v[1] is not None:
            self.begin_close(lambda: subprocess.Popen(["wl-copy", v[1]], start_new_session=True))

    # ---------- цикл ----------
    def tick(self, _w, clock):
        if self.t0 is None: return True
        now = time.monotonic()
        if self.close_at and now - self.close_at > T_CLOSE:
            if self.pending: self.pending()
            self.get_application().quit(); return False
        d = self.scroll_t - self.scroll
        if abs(d) > 0.002: self.scroll += d * 0.28; self.busy_until = max(self.busy_until, now + 0.1)
        else: self.scroll = self.scroll_t
        if now < self.busy_until or int((now - self.caret_t) * 2) != getattr(self, "_blink", -1):
            self._blink = int((now - self.caret_t) * 2); self.area.queue_draw()
        return True

    # ---------- рисование ----------
    def rrect(self, cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2); cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi); cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi); cr.close_path()

    def lay(self, cr, s, size, bold=True, width=None, align=Pango.Alignment.LEFT):
        l = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription(f"{FONT} {'Bold' if bold else ''}"); fd.set_absolute_size(size * Pango.SCALE)
        l.set_font_description(fd); l.set_text(s, -1)
        if width: l.set_width(int(width * Pango.SCALE)); l.set_ellipsize(Pango.EllipsizeMode.END); l.set_alignment(align)
        return l

    def txt(self, cr, s, x, y, size, color, bold=True, align="l", width=None):
        l = self.lay(cr, s, size, bold, width, Pango.Alignment.CENTER if align == "c" and width else Pango.Alignment.LEFT)
        w, h = l.get_pixel_size()
        ox = x if align == "l" else (x - (width or w) / 2 if align == "c" else x - w)
        cr.move_to(ox, y - h / 2); cr.set_source_rgba(*color); PangoCairo.show_layout(cr, l); return w

    def chip(self, cr, x, cy, s, size, fg, bg, h=24, padx=10):
        l = self.lay(cr, s, size); w, th = l.get_pixel_size()
        cw = w + padx * 2
        cr.new_path(); c = 6                                        # скошенные углы, как у плашек режимов
        cr.move_to(x + c, cy - h / 2); cr.line_to(x + cw, cy - h / 2); cr.line_to(x + cw, cy + h / 2 - c)
        cr.line_to(x + cw - c, cy + h / 2); cr.line_to(x, cy + h / 2); cr.line_to(x, cy - h / 2 + c); cr.close_path()
        cr.set_source_rgba(*bg); cr.fill()
        cr.move_to(x + padx, cy - th / 2); cr.set_source_rgba(*fg); PangoCairo.show_layout(cr, l)
        return cw

    def tile_geom(self, i):
        r, c = divmod(i, COLS)
        return (PAD + c * (TILE_W + GAP), GRID_Y + (r - self.scroll) * (TILE_H + GAP))

    def draw_tile(self, cr, i, item, now, selected):
        x, y = self.tile_geom(i)
        if y < GRID_Y - TILE_H - 4 or y > GRID_Y + ROWS * (TILE_H + GAP): return
        ap = ease_out_back((now - self.result_t - 0.012 * min(i, 24)) / 0.28, 1.4)
        ap = max(0.0, min(1.2, ap))
        if ap <= 0: return
        cx, cy = x + TILE_W / 2, y + TILE_H / 2
        cr.save()
        cr.translate(cx, cy + (1 - min(ap, 1.0)) * 16); cr.scale(0.86 + 0.14 * min(ap, 1.0), 0.86 + 0.14 * min(ap, 1.0)); cr.translate(-cx, -cy)
        # плитка
        self.rrect(cr, x, y, TILE_W, TILE_H, 18)
        cr.set_source_rgba(0.075, 0.078, 0.07, 1) if not selected else cr.set_source_rgba(0.11, 0.12, 0.085, 1)
        cr.fill()
        kind, v = item
        a_ = min(1.0, ap)
        if kind == "app":
            pb = self.icon(v); sc = 1.0 + (0.1 if selected else 0) 
            ix, iy = cx, y + 14 + ICON / 2 + 6
            if pb:
                cr.save(); cr.translate(ix, iy); cr.scale(sc, sc)
                Gdk.cairo_set_source_pixbuf(cr, pb, -pb.get_width() / 2, -pb.get_height() / 2); cr.paint_with_alpha(a_); cr.restore()
            else:
                cr.save(); cr.translate(ix, iy); cr.scale(sc, sc); self.rrect(cr, -30, -30, 60, 60, 16)
                cr.set_source_rgba(*self.acc, 0.18 * a_); cr.fill()
                self.txt(cr, v.name[:1].upper(), 0, 0, 30, (*self.acc, a_), True, "c", 60); cr.restore()
            nm = (0.97, 0.97, 0.95, a_) if selected else (0.85, 0.85, 0.82, a_)
            self.txt(cr, v.name, cx, y + TILE_H - 40, 14, nm, True, "c", TILE_W - 20)
            sub = v.generic or v.exe
            if sub: self.txt(cr, sub, cx, y + TILE_H - 20, 11, (0.5, 0.52, 0.47, a_ * (1 if selected else 0.8)), False, "c", TILE_W - 20)
            if v.id in self.usage and selected:                       # метка частоты
                n = self.usage[v.id][0]
                self.txt(cr, f"×{n}", x + TILE_W - 12, y + 16, 10, (*self.acc, a_), True, "r")
        else:
            big = 40
            if kind == "cmd": glyph, title, sub = "", "Выполнить", v
            elif kind == "calc": glyph, title, sub = "󰃬", ("= " + (v[1] if v[1] is not None else "…")), v[0]
            elif kind == "emoji": glyph, title, sub, big = v[0], v[1].title()[:24], "Enter — копировать", 46
            elif kind == "win": glyph, title, sub = "󰖲", v["title"], f"{v['cls']} · ws {v['ws']}"
            elif kind == "file": glyph, title, sub = ("󰉋" if os.path.isdir(v) else "󰈔"), os.path.basename(v.rstrip("/")) or v, short_path(os.path.dirname(v.rstrip("/")))
            elif kind == "web": glyph, title, sub = "󰖟", v[0], v[1]
            elif kind == "act": glyph, title, sub = "󰜎", v[2], v[0].name
            else: glyph, title, sub = "󰍉", v[0], v[1]
            self.txt(cr, glyph, cx, y + 56, big, (*self.acc, a_) if kind != "emoji" else (1, 1, 1, a_), True, "c", 80)
            self.txt(cr, title, cx, y + TILE_H - 40, 15 if kind == "calc" else 14, (0.97, 0.97, 0.95, a_), True, "c", TILE_W - 16)
            self.txt(cr, sub or ("shell" if kind == "cmd" else "введите выражение"), cx, y + TILE_H - 20, 11, (0.55, 0.57, 0.5, a_), False, "c", TILE_W - 16)
        cr.restore()

    def draw_panel(self, cr, now, t):
        acc = self.acc
        # корпус
        self.rrect(cr, 0, 0, PW, PH, 28)
        cr.set_source_rgba(0.035, 0.036, 0.034, 1.0); cr.fill_preserve()
        cr.set_source_rgba(*acc, 0.55); cr.set_line_width(2); cr.stroke()
        # уголки-скобки
        cr.set_source_rgba(*acc, 0.9); cr.set_line_width(3)
        for sx, sy in ((14, 14), (PW - 14, 14), (14, PH - 14), (PW - 14, PH - 14)):
            dx, dy = (1 if sx < PW / 2 else -1), (1 if sy < PH / 2 else -1)
            cr.move_to(sx, sy + dy * 14); cr.line_to(sx, sy); cr.line_to(sx + dx * 14, sy); cr.stroke()
        # строка поиска
        sx, sy, sw, sh = PAD, 24, PW - 2 * PAD, 62
        self.rrect(cr, sx - 3, sy - 3, sw + 6, sh + 6, 24); cr.set_source_rgb(0, 0, 0); cr.fill()
        self.rrect(cr, sx, sy, sw, sh, 21); cr.set_source_rgba(0.115, 0.118, 0.11, 1); cr.fill()
        cr.save(); self.rrect(cr, sx, sy, sw, sh, 21); cr.clip()                 # линия-«сканер» при открытии
        p = ease_out_cubic(t / 0.55); cr.rectangle(sx, sy + sh - 3, sw * p, 3); cr.set_source_rgba(*acc, 0.9 * (1 - p * 0.55)); cr.fill()
        cr.restore()
        self.txt(cr, "󰍉", sx + 30, sy + sh / 2, 26, (*acc, 1), True, "c", 40)
        qy = sy + sh / 2
        if self.query:
            w = self.txt(cr, self.query, sx + 62, qy, 26, (0.96, 0.96, 0.94, 1), True)
        else:
            w = 0; self.txt(cr, "Поиск…  > команда  = счёт  : эмодзи  w окна  f файлы  g веб", sx + 62, qy, 21, (0.42, 0.43, 0.4, 1), False)
        if int((now - self.caret_t) * 2) % 2 == 0:
            cr.rectangle(sx + 62 + w + 3, qy - 15, 3, 30); cr.set_source_rgba(*acc, 1); cr.fill()
        cnt = sum(1 for k, _ in self.results if k == "app")
        self.chip(cr, sx + sw - 20 - (len(f"{cnt}/{len(self.apps)}") * 9 + 26), qy, f"{cnt}/{len(self.apps)}", 13, (0.7, 0.72, 0.66, 1), (0.05, 0.05, 0.05, 1), 28)
        # категории
        cx = PAD
        for i, (lab, _) in enumerate(CATS):
            on = i == self.cat
            cw = self.chip(cr, cx, 116, lab, 13, (0.05, 0.06, 0.0, 1) if on else (0.62, 0.64, 0.58, 1),
                           (*acc, 1) if on else (0.11, 0.115, 0.105, 1), 28, 14)
            cx += cw + 8
        # сетка (клип по области, чтобы прокрутка не вылезала)
        cr.save(); cr.rectangle(PAD - 6, GRID_Y - 6, PW - 2 * PAD + 12, ROWS * TILE_H + (ROWS - 1) * GAP + 12); cr.clip()
        if not self.results:
            self.txt(cr, "Ничего не найдено", PW / 2, GRID_Y + 110, 22, (0.5, 0.52, 0.47, 1), True, "c", 600)
            self.txt(cr, "Esc — закрыть · Ctrl+U — очистить запрос", PW / 2, GRID_Y + 150, 13, (0.4, 0.42, 0.38, 1), False, "c", 600)
        else:
            # скользящая рамка выделения
            tx, ty = self.tile_geom(self.sel)
            if self.hl is None: self.hl = [tx, ty]
            self.hl[0] += (tx - self.hl[0]) * 0.35; self.hl[1] += (ty - self.hl[1]) * 0.35
            if abs(tx - self.hl[0]) + abs(ty - self.hl[1]) > 0.4: self.busy_until = max(self.busy_until, now + 0.1)
            for g, al in ((7, 0.05), (4, 0.09), (2, 0.16)):
                self.rrect(cr, self.hl[0] - g, self.hl[1] - g, TILE_W + 2 * g, TILE_H + 2 * g, 18 + g); cr.set_source_rgba(*acc, al); cr.fill()
            first = max(0, int(self.scroll) * COLS - COLS); last = min(len(self.results), (int(self.scroll) + ROWS + 2) * COLS)
            for i in range(first, last): self.draw_tile(cr, i, self.results[i], now, i == self.sel)
            self.rrect(cr, self.hl[0], self.hl[1], TILE_W, TILE_H, 18); cr.set_source_rgba(*acc, 0.95); cr.set_line_width(2); cr.stroke()
        cr.restore()
        # полоса прокрутки
        rows_total = (len(self.results) + COLS - 1) // COLS
        if rows_total > ROWS:
            th = ROWS * TILE_H + (ROWS - 1) * GAP; bh = max(40, th * ROWS / rows_total)
            by = GRID_Y + (th - bh) * (self.scroll / max(1, rows_total - ROWS))
            self.rrect(cr, PW - 12, by, 4, bh, 2); cr.set_source_rgba(*acc, 0.6); cr.fill()
        # подвал: описание выбранного + подсказки
        fy = PH - 30
        if self.results:
            k0, v0 = self.results[self.sel]
            d = (v0.desc if k0 == "app" else short_path(v0) if k0 == "file" else v0["title"] if k0 == "win" else v0[2] if k0 == "web" else "")
            if d: self.txt(cr, d, PAD + 4, fy, 13, (0.6, 0.62, 0.56, 1), False, "l", 560)
        hx = PW - PAD
        for lab, key in reversed((("↑↓←→", "выбор"), ("↵", "запуск"), ("⇥", "категория"), ("esc", "закрыть"))):
            lw = self.lay(cr, lab, 12).get_pixel_size()[0] + 16; kw = self.lay(cr, key, 12, False).get_pixel_size()[0]
            hx -= kw; self.txt(cr, key, hx, fy, 12, (0.5, 0.52, 0.47, 1), False); hx -= lw + 6
            self.chip(cr, hx, fy, lab, 12, (*acc, 1), (0.05, 0.05, 0.05, 1), 22, 8); hx -= 20

    def draw(self, _a, cr, w, h):
        if self.t0 is None: return
        now = time.monotonic(); t = now - self.t0
        if self.close_at:
            k = max(0.0, min(1.0, (now - self.close_at) / T_CLOSE)); sc = 1 - 0.04 * k; al = 1 - k
        else:
            k = ease_out_quart(t / T_OPEN); sc = 0.95 + 0.05 * k; al = max(0.0, min(1.0, t / (T_OPEN * 0.6)))
        cx, cy = self.win_w / 2, self.win_h / 2
        cr.translate(cx, cy); cr.scale(sc, sc); cr.translate(-PW / 2, -PH / 2)
        cr.push_group(); self.draw_panel(cr, now, t); cr.pop_group_to_source(); cr.paint_with_alpha(al)


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="dev.m2res.launcher")
    def do_activate(self): Launcher(self).present()


if __name__ == "__main__":
    App().run()
