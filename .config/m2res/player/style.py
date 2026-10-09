"""m2res style — единые токены оформления для всех виджетов (читает player/style.json, его пишет m2res-rice).

Что здесь:
  ST.bg / fg / dim / ink / on_acc  — цвета панели (rgba/rgb 0..1), ST.font — шрифт
  ST.path(cr, x, y, w, h, r)       — контур панели по форме (round | chamfer | square | pill)
  ST.frame(cr, x, y, w, h, A, r)   — рамка панели по виду (glow | flat | neon | brutal | glass | double | soft)
  ST.n(*rgb[a])                    — «нейтральный» цвет из старого кода → цвет текущей палитры (для светлых/цветных тем)
Без style.json всё выглядит как прежний m2res (токены по умолчанию), так что виджеты работают и без райсов.
"""
import json, math, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "style.json")

DEFAULT = {
    "name": "m2res",
    "frame": "glow",            # вид рамки панели
    "shape": "round",           # round | chamfer | square | pill
    "rk": 1.0,                  # множитель радиусов скругления
    "border_w": 2.5, "border_a": 0.55,
    "glow_k": 1.0,              # сила/размер свечения
    "shadow": [0, 0],           # смещение жёсткой тени (brutal), px
    "bg": [0.039, 0.039, 0.039, 0.97],
    "fg": [0.92, 0.92, 0.88],
    "dim": [0.55, 0.56, 0.52],
    "ink": [1, 1, 1],           # цвет «подсветки поверх»: белый на тёмном, чёрный на светлом
    "on_acc": [0.04, 0.04, 0.04],   # текст на акцентной заливке
    "font": "CaskaydiaMono Nerd Font Mono",
    "tint": False,              # перекрашивать «серые» литералы кода в палитру темы
    "anim": 1.0,                # множитель скорости анимаций открытия (1 = как раньше)
    "caps": False,              # заголовки заглавными
}


def _lerp(a, b, t): return a + (b - a) * t


class Style:
    def __init__(self):
        self._mt = 0.0; self._chk = 0.0
        self.load()

    def load(self):
        d = dict(DEFAULT)
        try:
            d.update(json.load(open(PATH)))
            self._mt = os.stat(PATH).st_mtime
        except Exception:
            self._mt = 0.0
        self.d = d
        for k, v in d.items():
            setattr(self, "fkind" if k == "frame" else k, tuple(v) if isinstance(v, list) else v)

    def maybe_reload(self):
        """долгоживущие демоны подхватывают смену райса без перезапуска (проверка не чаще раза в секунду)"""
        now = time.monotonic()
        if now - self._chk < 1.0: return
        self._chk = now
        try: mt = os.stat(PATH).st_mtime
        except Exception: mt = 0.0
        if mt != self._mt: self.load()

    # ---------- цвета ----------
    def n(self, *c):
        """нейтральный серый/белый из старого кода → палитра темы. Без tint — как есть."""
        if not self.tint: return tuple(c)
        lum = sum(c[:3]) / 3.0
        bg, fg = self.bg, self.fg
        out = tuple(_lerp(bg[i], fg[i], lum) for i in range(3))
        return out + tuple(c[3:])

    # ---------- форма ----------
    def path(self, cr, x, y, w, h, r):
        shape = self.shape
        if shape == "square": r = 0
        elif shape == "pill": r = min(w, h) / 2
        else: r = r * self.rk
        r = min(r, w / 2, h / 2)
        if shape == "chamfer":
            c = max(0.0, min(r * 0.9, w / 2, h / 2))
            cr.new_sub_path(); cr.move_to(x + c, y); cr.line_to(x + w - c, y); cr.line_to(x + w, y + c); cr.line_to(x + w, y + h - c)
            cr.line_to(x + w - c, y + h); cr.line_to(x + c, y + h); cr.line_to(x, y + h - c); cr.line_to(x, y + c); cr.close_path(); return
        if r <= 0.01:
            cr.rectangle(x, y, w, h); return
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi); cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi); cr.close_path()

    # ---------- рамка панели ----------
    def frame(self, cr, x, y, w, h, A, r=30, glow=True):
        """glow=False — без выступающих за рамку частей (свечение/тень): для окон, где снаружи нет прозрачного поля"""
        self.maybe_reload()
        k, kind = self.glow_k, self.fkind
        if not glow:
            if kind in ("glow", "soft", "glass"): kind = "flat"
            elif kind == "neon": kind = "flatneon"
            elif kind == "brutal": kind = "brutalflat"
        bg = self.bg
        if kind in ("glow", "neon"):
            lay = ((26, 0.03), (18, 0.05), (12, 0.08), (6, 0.12)) if kind == "neon" else ((18, 0.04), (12, 0.06), (6, 0.09))
            for i, a in lay:
                i *= k; cr.set_source_rgba(*A, min(1.0, a)); self.path(cr, x - i, y - i, w + 2 * i, h + 2 * i, r + i); cr.fill()
            self.path(cr, x, y, w, h, r); cr.set_source_rgba(*bg); cr.fill_preserve()
            cr.set_source_rgba(*A, 0.95 if kind == "neon" else self.border_a); cr.set_line_width(1.8 if kind == "neon" else self.border_w); cr.stroke()
        elif kind == "flatneon":
            self.path(cr, x, y, w, h, r); cr.set_source_rgba(*bg); cr.fill_preserve()
            cr.set_source_rgba(*A, 0.95); cr.set_line_width(2.0); cr.stroke()
        elif kind == "brutalflat":
            self.path(cr, x, y, w, h, r); cr.set_source_rgba(*bg); cr.fill_preserve()
            cr.set_source_rgba(*self.fg, 1); cr.set_line_width(max(3.0, self.border_w)); cr.stroke()
        elif kind == "flat":
            self.path(cr, x, y, w, h, r); cr.set_source_rgba(*bg); cr.fill_preserve()
            cr.set_source_rgba(*A, self.border_a); cr.set_line_width(self.border_w); cr.stroke()
        elif kind == "brutal":
            dx, dy = self.shadow if any(self.shadow) else (8, 8)
            self.path(cr, x + dx, y + dy, w, h, r); cr.set_source_rgba(*A, 1); cr.fill()
            self.path(cr, x, y, w, h, r); cr.set_source_rgba(*bg); cr.fill_preserve()
            cr.set_source_rgba(*self.fg, 1); cr.set_line_width(max(3.0, self.border_w)); cr.stroke()
        elif kind == "glass":
            for i, a in ((22, 0.02), (16, 0.03), (10, 0.04), (5, 0.05)):
                cr.set_source_rgba(0, 0, 0, a); self.path(cr, x - i * 0.6, y - i * 0.3 + 8, w + 1.2 * i * 0.6, h + 0.6 * i * 0.3, r + i); cr.fill()
            self.path(cr, x, y, w, h, r); cr.set_source_rgba(*bg); cr.fill_preserve()
            cr.set_source_rgba(*self.ink, 0.22); cr.set_line_width(max(1.0, self.border_w)); cr.stroke()
            self.path(cr, x + 1.5, y + 1.5, w - 3, h - 3, max(0, r - 1.5)); cr.set_source_rgba(*A, 0.22); cr.set_line_width(1.0); cr.stroke()
        elif kind == "double":
            self.path(cr, x, y, w, h, r); cr.set_source_rgba(*bg); cr.fill_preserve()
            cr.set_source_rgba(*A, 0.95); cr.set_line_width(max(1.5, self.border_w)); cr.stroke()
            g = 7; self.path(cr, x + g, y + g, w - 2 * g, h - 2 * g, max(0, r - g)); cr.set_source_rgba(*A, 0.38); cr.set_line_width(1.0); cr.stroke()
        elif kind == "soft":      # светлая тема: мягкая тень + тонкая линия
            for i, a in ((20, 0.02), (14, 0.03), (9, 0.04), (5, 0.05), (2, 0.06)):
                cr.set_source_rgba(0, 0, 0, a); self.path(cr, x - i * 0.5, y - i * 0.2 + 5, w + i, h + 0.4 * i, r + i * 0.7); cr.fill()
            self.path(cr, x, y, w, h, r); cr.set_source_rgba(*bg); cr.fill_preserve()
            cr.set_source_rgba(*A, self.border_a); cr.set_line_width(self.border_w); cr.stroke()
        else:
            self.path(cr, x, y, w, h, r); cr.set_source_rgba(*bg); cr.fill()


ST = Style()
