#!/usr/bin/env python3
"""Синтез киберпанк-звуков для уведомлений m2res (numpy, без внешних сэмплов).
Запуск: python3 gen.py  -> рядом появятся *.wav (48 кГц, стерео, 16 бит). Результат детерминирован (seed)."""
import os, wave
import numpy as np

SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(2077)


# ---------- примитивы ----------
def tt(d):
    return np.arange(int(SR * d)) / SR


def phase(f, n):
    f = np.broadcast_to(np.asarray(f, dtype=float), (n,))
    return np.cumsum(f) / SR


def saw(ph): return 2 * (ph % 1.0) - 1
def square(ph, pw=0.5): return np.where((ph % 1.0) < pw, 1.0, -1.0)
def sine(ph): return np.sin(2 * np.pi * ph)


def adsr_exp(n, attack=0.004, tau=0.12, release=0.01):
    x = np.arange(n) / SR
    e = np.exp(-x / tau)
    a = np.minimum(1.0, x / max(attack, 1e-4))
    r = np.minimum(1.0, (n / SR - x) / max(release, 1e-4))
    return e * a * np.clip(r, 0, 1)


def lowpass(x, fc):
    """однополюсный НЧ-фильтр, fc — число или массив (свип среза)"""
    fc = np.broadcast_to(np.asarray(fc, dtype=float), x.shape)
    a = 1 - np.exp(-2 * np.pi * np.clip(fc, 20, SR / 2 - 100) / SR)
    y = np.empty_like(x); s = 0.0
    for i in range(len(x)):
        s += a[i] * (x[i] - s); y[i] = s
    return y


def highpass(x, fc):
    return x - lowpass(x, fc)


def crush(x, bits=8, hold=2):
    y = np.repeat(x[::hold], hold)[:len(x)]
    q = 2 ** (bits - 1)
    return np.round(y * q) / q


def drive(x, g=3.0):
    return np.tanh(x * g) / np.tanh(g)


def place(buf, x, at, gain=1.0):
    i = int(at * SR)
    end = min(len(buf), i + len(x))
    if end > i:
        buf[i:end] += x[:end - i] * gain


def stereo_echo(m, delay, fb, mix, taps=4, tail=0.0):
    """пинг-понг эхо: моно -> стерео"""
    n = len(m) + int(SR * (delay * taps + tail))
    L = np.zeros(n); R = np.zeros(n)
    L[:len(m)] += m * (1 - mix * 0.3); R[:len(m)] += m * (1 - mix * 0.3)
    g = mix
    for k in range(1, taps + 1):
        d = int(SR * delay * k)
        tgt = L if k % 2 else R
        tgt[d:d + len(m)] += m * g
        g *= fb
    return L, R


def finish(L, R, name, peak=0.86, fade=0.03, maxd=None):
    if maxd:
        L, R = L[:int(SR * maxd)], R[:int(SR * maxd)]
        fade = max(fade, 0.12)
    n = max(len(L), len(R))
    L = np.pad(L, (0, n - len(L))); R = np.pad(R, (0, n - len(R)))
    m = max(np.abs(L).max(), np.abs(R).max(), 1e-9)
    L, R = L / m * peak, R / m * peak
    f = int(SR * fade)
    w = np.ones(n); w[-f:] = np.linspace(1, 0, f); w[:48] = np.linspace(0, 1, 48)
    L, R = L * w, R * w
    pcm = np.empty(n * 2, dtype="<i2")
    pcm[0::2] = np.round(L * 32767); pcm[1::2] = np.round(R * 32767)
    p = os.path.join(HERE, name + ".wav")
    with wave.open(p, "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(pcm.tobytes())
    print(f"{name}.wav  {n / SR:.2f}с  peak={max(np.abs(L).max(), np.abs(R).max()):.2f}")


def note_pluck(f, dur, tau=0.1, pw=0.35, cut0=7000, cut1=900, detune=0.004):
    n = int(SR * dur)
    x = square(phase(f, n), pw) + 0.7 * saw(phase(np.asarray(f) * (1 + detune), n))
    x = lowpass(x, np.linspace(cut0, cut1, n)) * adsr_exp(n, 0.003, tau)
    return x


def fm_bell(f, dur, ratio=3.5, idx=2.2, tau=0.18):
    n = int(SR * dur); x = np.arange(n) / SR
    mod = np.sin(2 * np.pi * f * ratio * x) * idx * np.exp(-x / (tau * 0.6))
    return np.sin(2 * np.pi * f * x + mod) * adsr_exp(n, 0.002, tau)


def click(dur=0.012, hp=3000):
    n = int(SR * dur)
    return highpass(rng.standard_normal(n), hp) * np.exp(-np.arange(n) / SR / 0.003)


# ---------- обычное уведомление: «net ping» ----------
def notify_cyber():
    buf = np.zeros(int(SR * 0.6))
    E5, G5, B5 = 659.25, 783.99, 987.77
    place(buf, note_pluck(E5, 0.16, 0.05), 0.00, 0.8)
    place(buf, note_pluck(G5, 0.16, 0.05), 0.07, 0.8)
    place(buf, note_pluck(B5, 0.45, 0.14), 0.14, 1.0)
    place(buf, fm_bell(B5 * 2, 0.45, tau=0.2), 0.14, 0.35)
    place(buf, click(), 0.0, 0.5)
    buf = crush(buf, 10, 2)
    L, R = stereo_echo(buf, 0.11, 0.5, 0.32, taps=3)
    finish(L, R, "notify-cyber")


# ---------- вариант: «data chirp» ----------
def notify_data():
    buf = np.zeros(int(SR * 0.5))
    fs = [1046.5, 1318.5, 1568.0, 2093.0, 1568.0]
    at = 0.0
    for i, f in enumerate(fs):
        last = i == len(fs) - 1
        d = 0.16 if last else 0.04
        n = int(SR * d)
        x = square(phase(f, n), 0.25) * adsr_exp(n, 0.001, 0.09 if last else 0.03, 0.004)
        place(buf, x, at, 1.0 if last else 0.75); at += 0.055
    buf = crush(buf, 8, 3)
    L, R = stereo_echo(buf, 0.09, 0.45, 0.28, taps=3)
    finish(L, R, "notify-data")


# ---------- вариант: «neon stab» ----------
def notify_neon():
    d = 0.6; n = int(SR * d)
    chord = [164.81, 246.94, 329.63, 392.0, 493.88]   # Em(add9)-ощущение
    x = np.zeros(n)
    for k, f in enumerate(chord):
        for dt in (-0.006, 0.0, 0.006):
            x += saw(phase(f * (1 + dt), n)) * (1.0 if k else 1.4)
    x = lowpass(x, 5200 * np.exp(-np.arange(n) / SR / 0.16) + 350) * adsr_exp(n, 0.004, 0.28)
    sub = sine(phase(82.41, n)) * adsr_exp(n, 0.004, 0.2) * 1.8
    x = drive(x / 6 + sub / 3, 1.6)
    L, R = stereo_echo(x, 0.16, 0.45, 0.35, taps=2)
    finish(L, R, "notify-neon")


# ---------- красное: «red alert» ----------
def critical_alarm():
    buf = np.zeros(int(SR * 1.0))
    # суб-удар вниз
    n = int(SR * 0.3); f = np.linspace(150, 45, n)
    place(buf, sine(phase(f, n)) * adsr_exp(n, 0.002, 0.14) * 1.4, 0.0)
    place(buf, click(0.02, 1500), 0.0, 0.8)
    # сирена: два тона с портаменто, 4 импульса
    at = 0.04
    for k in range(4):
        f0, f1 = (880, 660) if k % 2 == 0 else (660, 880)
        n = int(SR * 0.19); f = np.linspace(f0, f1, n)
        x = saw(phase(f, n)) + 0.8 * saw(phase(f * 1.007, n)) + 0.5 * square(phase(f * 0.5, n))
        x = drive(lowpass(x, 3800) * 0.6, 3.5) * adsr_exp(n, 0.004, 0.5, 0.012)
        place(buf, x, at, 0.9); at += 0.21
    buf = crush(buf, 8, 2)
    L, R = stereo_echo(buf, 0.1, 0.4, 0.25, taps=2)
    finish(L, R, "critical-alarm")


# ---------- вариант красного: «system failure» ----------
def critical_glitch():
    buf = np.zeros(int(SR * 0.8))
    n = int(SR * 0.55); f = 150 * np.exp(-np.arange(n) / SR / 0.12) + 32
    place(buf, drive(sine(phase(f, n)) * 1.6, 2.5) * adsr_exp(n, 0.002, 0.3), 0.0, 1.2)
    # стаккато квадрата со случайными скачками высоты
    at = 0.06
    for k in range(9):
        f = rng.choice([740, 554, 440, 987, 370])
        n = int(SR * 0.045)
        x = square(phase(f, n), 0.4) * adsr_exp(n, 0.001, 0.05, 0.004)
        place(buf, x, at, 0.55); at += rng.choice([0.05, 0.08, 0.05, 0.1])
    # шумовые «рваные» всплески
    for at in (0.0, 0.17, 0.33, 0.52):
        n = int(SR * rng.uniform(0.02, 0.05))
        place(buf, rng.standard_normal(n) * adsr_exp(n, 0.001, 0.04, 0.004), at, 0.35)
    buf = crush(buf, 6, 4)
    L, R = stereo_echo(buf, 0.07, 0.5, 0.2, taps=2)
    finish(L, R, "critical-glitch")


# ---------- тихое: «soft tick» ----------
def low_tick():
    buf = np.zeros(int(SR * 0.25))
    n = int(SR * 0.05); f = np.linspace(2200, 1500, n)
    place(buf, sine(phase(f, n)) * adsr_exp(n, 0.001, 0.02, 0.004), 0.0, 0.7)
    n = int(SR * 0.12)
    place(buf, sine(phase(1175, n)) * adsr_exp(n, 0.002, 0.05), 0.045, 0.6)
    buf = crush(buf, 11, 2)
    L, R = stereo_echo(buf, 0.08, 0.4, 0.22, taps=2)
    finish(L, R, "low-tick", peak=0.7)


# ================= красные, набор 2: чище и «кинематографичнее» =================
def reverb(m, rt=0.6, mix=0.3, seed=1):
    r = np.random.default_rng(seed); n_ir = int(SR * rt); x = np.arange(n_ir) / SR
    N = len(m) + n_ir; outs = []
    for _ in range(2):
        ir = lowpass(r.standard_normal(n_ir) * np.exp(-6.9 * x / rt), 5500)
        k = int(0.008 * SR); ir[:k] *= np.linspace(0, 1, k)
        ir /= np.sqrt((ir ** 2).sum())
        outs.append(np.fft.irfft(np.fft.rfft(m, N) * np.fft.rfft(ir, N), N))
    dry = np.pad(m, (0, n_ir)) * (1 - mix * 0.4)
    return dry + outs[0] * mix * 1.6, dry + outs[1] * mix * 1.6


def inharm_bell(f, dur, tau=0.25, ratios=(1, 2.32, 4.25, 6.63), amps=(1, 0.6, 0.35, 0.2)):
    n = int(SR * dur); x = np.arange(n) / SR; y = np.zeros(n)
    for r_, a_ in zip(ratios, amps):
        y += a_ * np.sin(2 * np.pi * f * r_ * x) * np.exp(-x / (tau / (0.6 + 0.4 * r_)))
    return y * np.minimum(1, x / 0.001)


def fm_tone(f, dur, ratio=2.0, idx=3.0, tau=0.08):
    n = int(SR * dur); x = np.arange(n) / SR
    mod = np.sin(2 * np.pi * f * ratio * x) * idx * np.exp(-x / (tau * 0.7))
    return np.sin(2 * np.pi * f * x + mod) * adsr_exp(n, 0.002, tau, 0.01)


def sub_hit(f0=130, f1=40, dur=0.3, tau=0.14, g=2.2):
    n = int(SR * dur); f = f1 + (f0 - f1) * np.exp(-np.arange(n) / SR / 0.06)
    return drive(sine(phase(f, n)) * 1.5, g) * adsr_exp(n, 0.002, tau, 0.02)


def crit_denied():
    """«ACCESS DENIED»: две металлические ноты вниз (тритон) + низкий стук"""
    buf = np.zeros(int(SR * 0.7))
    place(buf, fm_tone(987.77, 0.16, 2.0, 3.2, 0.07), 0.00, 0.9)
    place(buf, fm_tone(698.46, 0.16, 2.0, 3.2, 0.07), 0.17, 0.9)
    place(buf, fm_tone(329.63, 0.30, 1.0, 2.0, 0.15) + 0.4 * square(phase(164.8, int(SR * 0.3))) * adsr_exp(int(SR * 0.3), 0.003, 0.12), 0.34, 1.0)
    place(buf, sub_hit(110, 45, 0.25), 0.34, 0.9)
    L, R = reverb(drive(buf, 1.4), 0.45, 0.30, 11)
    finish(L, R, "crit-denied", maxd=1.0)


def crit_breach():
    """«BREACH»: шумовой нарастающий свист -> удар, суб, металлический звон, цифровая дробь"""
    buf = np.zeros(int(SR * 1.1)); r = np.random.default_rng(5)
    n = int(SR * 0.34); up = r.standard_normal(n)
    up = lowpass(up, np.geomspace(300, 9000, n)) * (np.linspace(0, 1, n) ** 2.2)
    place(buf, up, 0.0, 0.9)
    at = 0.34
    place(buf, sub_hit(140, 36, 0.6, 0.22, 2.8), at, 1.3)
    n = int(SR * 0.16); place(buf, lowpass(r.standard_normal(n), 3500) * adsr_exp(n, 0.001, 0.05), at, 0.9)
    place(buf, inharm_bell(220, 0.7, 0.45), at, 0.5)
    for k, f in enumerate((1568, 1318, 1568)):
        n = int(SR * 0.025); place(buf, square(phase(f, n), 0.3) * adsr_exp(n, 0.001, 0.03, 0.004), at + 0.12 + 0.05 * k, 0.4)
    L, R = reverb(buf, 0.7, 0.28, 12)
    finish(L, R, "crit-breach", maxd=1.35)


def crit_sonar():
    """«SONAR»: два сердечных удара и высокий пинг с длинным эхом"""
    buf = np.zeros(int(SR * 1.0))
    place(buf, sub_hit(95, 42, 0.22, 0.09, 2.5), 0.00, 1.2)
    place(buf, sub_hit(95, 42, 0.22, 0.09, 2.5), 0.16, 1.0)
    place(buf, fm_tone(1568, 0.5, 1.0, 0.8, 0.22), 0.34, 0.8)
    place(buf, sine(phase(3136, int(SR * 0.3))) * adsr_exp(int(SR * 0.3), 0.001, 0.08), 0.34, 0.25)
    L, R = stereo_echo(buf, 0.26, 0.5, 0.4, taps=2)
    L, R = reverb(L, 0.5, 0.2, 13)[0], reverb(R, 0.5, 0.2, 14)[1]
    finish(L, R, "crit-sonar", maxd=1.3)


def crit_triple():
    """«TRIPLE»: две тройки тревожных бипов вверх по полутонам (малая секунда)"""
    buf = np.zeros(int(SR * 1.0))
    for g, (at0, vol) in enumerate(((0.0, 0.8), (0.46, 1.0))):
        for k, f in enumerate((880.0, 932.33, 987.77)):
            last = k == 2
            n = int(SR * (0.2 if last else 0.075)); ph = phase(f, n)
            x = square(ph, 0.4) + 0.6 * saw(phase(f * 2.005, n))
            x = lowpass(x, 5200) * adsr_exp(n, 0.002, 0.12 if last else 0.04, 0.006)
            place(buf, drive(x * 0.6, 2.0), at0 + 0.1 * k, vol)
        place(buf, sub_hit(100, 50, 0.2, 0.08, 2.0), at0, 0.8 * vol)
    L, R = reverb(buf, 0.4, 0.25, 15)
    finish(L, R, "crit-triple", maxd=1.2)


def crit_glass():
    """«GLASS»: каскад неоднородных колокольчиков со строб-прерыванием, как разбитое стекло данных"""
    buf = np.zeros(int(SR * 1.0))
    for at, f in ((0.0, 1760), (0.055, 1320), (0.11, 2093), (0.19, 1480), (0.27, 2349)):
        place(buf, inharm_bell(f, 0.7, 0.3), at, 0.8)
    n = len(buf); gate = np.where((np.arange(n) / SR * 26) % 1.0 < 0.55, 1.0, 0.25)
    gate[int(0.4 * SR):] = 1.0
    buf = crush(buf * gate, 12, 2)
    place(buf, sub_hit(120, 50, 0.3, 0.1, 2.2), 0.0, 0.9)
    L, R = reverb(buf, 0.8, 0.4, 16)
    finish(L, R, "crit-glass", maxd=1.35)


def crit_klaxon():
    """«KLAXON»: мягкая, но тяжёлая сирена-гудок (тритон), без битcrush и без визга"""
    buf = np.zeros(int(SR * 1.1)); at = 0.0
    for f in (466.16, 329.63, 466.16, 329.63):
        n = int(SR * 0.25); x = np.zeros(n)
        for dt in (-0.007, 0.0, 0.007):
            x += saw(phase(f * (1 + dt), n))
        x += 0.5 * square(phase(f / 2, n))
        x = lowpass(x / 4, np.linspace(2600, 1500, n)) * adsr_exp(n, 0.02, 0.5, 0.05)
        place(buf, drive(x, 1.8), at, 1.0); at += 0.24
    place(buf, sub_hit(90, 45, 0.3, 0.12, 2.0), 0.0, 0.7)
    L, R = reverb(buf, 0.5, 0.25, 17)
    finish(L, R, "crit-klaxon", maxd=1.3)


if __name__ == "__main__":
    import sys
    only = sys.argv[1:]
    for fn in (notify_cyber, notify_data, notify_neon, critical_alarm, critical_glitch, low_tick,
               crit_denied, crit_breach, crit_sonar, crit_triple, crit_glass, crit_klaxon):
        if not only or any(o in fn.__name__ for o in only):
            fn()
