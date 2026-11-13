"""Energy layer for the study shorts: sound effects, a beat, an animated circuit background,
confetti, segmented progress and kinetic (word-by-word) captions."""
import math, random, re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ---------------- audio ----------------
def _env(n, attack, release, sr):
    a = max(1, int(attack * sr)); r = max(1, int(release * sr))
    e = np.ones(n, np.float32)
    e[:a] = np.linspace(0, 1, a)
    e[-r:] *= np.exp(-np.linspace(0, 6, r))
    return e

def sfx(kind, sr):
    rng = np.random.default_rng({"whoosh": 1, "pop": 2, "tick": 3, "ding": 4, "stinger": 5}.get(kind, 0))
    if kind == "whoosh":
        n = int(0.30 * sr); x = rng.standard_normal(n).astype(np.float32)
        out = np.zeros(n, np.float32); acc = 0.0
        for i in range(n):                       # one-pole low-pass whose cutoff sweeps up and down
            k = 0.02 + 0.35 * math.sin(math.pi * i / n) ** 2
            acc += k * (x[i] - acc); out[i] = acc
        return 0.55 * out * np.sin(np.linspace(0, math.pi, n)) ** 2
    if kind == "pop":
        n = int(0.09 * sr); t = np.arange(n) / sr
        f = 1300 * np.exp(-t * 28) + 380
        return 0.32 * np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 38)
    if kind == "tick":
        n = int(0.035 * sr); t = np.arange(n) / sr
        return 0.22 * np.sin(2 * np.pi * 2600 * t) * np.exp(-t * 140)
    if kind == "ding":
        n = int(0.9 * sr); t = np.arange(n) / sr; y = np.zeros(n, np.float32)
        for k, (f, d0) in enumerate([(1046.5, 0.0), (1318.5, 0.07), (1568.0, 0.14)]):
            s = int(d0 * sr); tt = t[: n - s]
            y[s:] += (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)) * np.exp(-tt * 5.5)
        return 0.16 * y
    if kind == "stinger":
        n = int(0.55 * sr); t = np.arange(n) / sr
        boom = np.sin(2 * np.pi * (48 + 60 * np.exp(-t * 18)) * t) * np.exp(-t * 6)
        hit = rng.standard_normal(n) * np.exp(-t * 40) * 0.25
        return 0.5 * (boom + hit).astype(np.float32)
    return np.zeros(1, np.float32)

def beat(total, sr, bpm=118, seed=0):
    """A light four-on-the-floor loop (kick, offbeat hats, claps on 2 and 4, bass on Am-F-C-G)."""
    n = int(total * sr); y = np.zeros(n, np.float32)
    spb = 60.0 / bpm; rng = np.random.default_rng(seed)
    def add(sig, at):
        s = int(at * sr)
        if s >= n: return
        e = min(n, s + len(sig)); y[s:e] += sig[: e - s]
    tk = np.arange(int(0.28 * sr)) / sr
    kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-tk * 30)) * tk) * np.exp(-tk * 11) * 0.9
    th = np.arange(int(0.05 * sr)) / sr
    hat = rng.standard_normal(len(th)) * np.exp(-th * 90) * 0.18
    hat = hat - np.convolve(hat, np.ones(4) / 4, "same")      # crude high-pass
    tc = np.arange(int(0.16 * sr)) / sr
    clap = rng.standard_normal(len(tc)) * np.exp(-tc * 28) * 0.35
    roots = [110.0, 87.31, 130.81, 98.0]                        # A2 F2 C3 G2
    beats = int(total / spb) + 1
    for b in range(beats):
        t0 = b * spb
        add(kick, t0); add(hat, t0 + spb / 2)
        if b % 4 in (1, 3): add(clap, t0)
        f = roots[(b // 4) % 4]
        tb = np.arange(int(spb * 0.45 * sr)) / sr
        bass = (np.sin(2 * np.pi * f * tb) + 0.35 * np.sin(2 * np.pi * 2 * f * tb)) * np.exp(-tb * 4) * 0.35
        add(bass, t0 + spb / 2)
    return y

SFX_GAIN = {"whoosh": 0.3, "pop": 0.6, "tick": 0.6, "ding": 0.8, "stinger": 0.45}

def _smooth(x, k):
    """Centred moving average of length k, same length as x (cumulative sums, so it stays fast)."""
    k = max(1, min(int(k), len(x)))
    c = np.cumsum(np.insert(x.astype(np.float64), 0, 0.0))
    y = (c[k:] - c[:-k]) / k
    left = (k - 1) // 2
    return np.concatenate([np.full(left, y[0]), y, np.full(k - 1 - left, y[-1])]).astype(np.float32)

VOICE_RMS = 0.185    # loudness target for the narration while someone is talking (about -16.5 LUFS once encoded)

def mix(voice_segments, events, total, sr, style="techno", seed=0, bed_music=None):
    """voice_segments: [(start_s, float32 array)], events: [(time_s, kind)].
    Returns two int16 tracks at one shared gain: (narration + sound effects, music). The page plays the music
    file in sync with the video, so viewers can mute the music and keep the narration."""
    n = int(total * sr) + 1
    v = np.zeros(n, np.float32)
    for st, a in voice_segments:
        s = int(st * sr); e = min(n, s + len(a)); v[s:e] += a[: e - s]
    pk = float(np.abs(v).max())
    if pk > 0: v *= 0.9 / pk                     # voice first: peak at 0.9, effects sit under it
    fx_bus = np.zeros(n, np.float32)
    cache = {}
    for t, kind in events:
        if kind not in cache: cache[kind] = sfx(kind, sr) * SFX_GAIN.get(kind, 0.5)
        a = cache[kind]; s = max(0, int(t * sr)); e = min(n, s + len(a))
        if e > s: fx_bus[s:e] += a[: e - s]
    # duck the music under the voice: smoothed level follower, 35 % while someone is talking
    m = np.pad(bed_music if bed_music is not None else music(style, total, sr, seed), (0, n))[:n]   # a music file, else synthesized
    env = _smooth(np.abs(v), 0.02 * sr)
    talking = env > 0.01
    duck = _smooth(np.where(talking, 0.35, 1.0), 0.25 * sr)
    fade = np.minimum(1.0, np.minimum(np.arange(n) / (0.4 * sr), (n - np.arange(n)) / (0.6 * sr)))
    bed = m * duck * fade * 0.16
    # the voice is levelled to VOICE_RMS; effects and music keep fixed levels (tuned against a voice at 0.13 RMS),
    # so a quiet narrator never drags the effects up with it. Soft-clip each track so neither can clip.
    voiced = v[talking] if talking.any() else v
    g = VOICE_RMS / max(float(np.sqrt(np.mean(voiced ** 2))), 1e-4)
    k = VOICE_RMS / 0.13
    fg = np.tanh((v * g + fx_bus * k) * 1.05) * 0.95
    bed = np.tanh(bed * k * 1.05) * 0.95
    return (fg * 32767).astype(np.int16), (bed * 32767).astype(np.int16)

# ---------------- music: one style per narrator, varied per short ----------------
# Every style is synthesized here (no samples). A seed picks the key, the chord progression, the tempo inside
# the style's range and the pattern variations, so two shorts in the same style still sound different.
PROGRESSIONS = {
    "minor": [[0, 8, 3, 10], [0, 5, 8, 7], [0, 10, 8, 10], [0, 3, 8, 7], [0, 8, 5, 7]],
    "major": [[0, 7, 9, 5], [0, 9, 5, 7], [5, 0, 7, 9], [0, 5, 9, 7], [0, 4, 9, 5]],
}

def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)

def _chord(root, quality, seventh=False):
    """MIDI notes of the triad (and seventh) on a scale degree, quality 'minor' key or 'major' key."""
    tones = [0, 3, 7] if quality == "m" else [0, 4, 7]
    if seventh:
        tones.append(10 if quality == "m" else 11)
    return [root + t for t in tones]

def _degree_quality(step, key):
    """Chord quality on a scale step (semitones from the tonic) in a natural minor or major key."""
    if key == "minor":
        return "m" if step in (0, 5, 7) else "M"
    return "m" if step in (2, 4, 9) else "M"

class _Track:
    def __init__(self, total, sr):
        self.sr = sr; self.n = int(total * sr) + 1; self.y = np.zeros(self.n, np.float32)
    def add(self, sig, at, gain=1.0):
        s = int(at * self.sr)
        if s >= self.n or s + len(sig) <= 0: return
        if s < 0: sig = sig[-s:]; s = 0
        e = min(self.n, s + len(sig)); self.y[s:e] += gain * sig[: e - s]

def _t(dur, sr):
    return np.arange(int(dur * sr)) / sr

def _adsr(n, sr, a=0.005, d=0.1, s=0.6, r=0.1):
    e = np.ones(n, np.float32) * s
    na, nd, nr = max(1, int(a * sr)), max(1, int(d * sr)), max(1, int(r * sr))
    e[:na] = np.linspace(0, 1, na)
    e[na:na + nd] = np.linspace(1, s, len(e[na:na + nd]))
    e[-nr:] *= np.linspace(1, 0, nr)
    return e

def _osc(kind, f, t, harmonics=12, sr=24000):
    if kind == "sine": return np.sin(2 * np.pi * f * t)
    out = np.zeros_like(t)
    for k in range(1, harmonics + 1):
        if f * k > sr * 0.45: break
        if kind == "saw": out += np.sin(2 * np.pi * f * k * t) / k
        elif kind == "square" and k % 2: out += np.sin(2 * np.pi * f * k * t) / k
        elif kind == "tri" and k % 2: out += ((-1) ** ((k - 1) // 2)) * np.sin(2 * np.pi * f * k * t) / (k * k)
    return out

def _kick(sr, punch=1.0, dur=0.3):
    t = _t(dur, sr)
    return (np.sin(2 * np.pi * (48 + 95 * punch * np.exp(-t * 32)) * t) * np.exp(-t * 10)).astype(np.float32)

def _noise(dur, sr, rng):
    return rng.standard_normal(int(dur * sr)).astype(np.float32)

def _hat(sr, rng, dur=0.05, decay=90):
    x = _noise(dur, sr, rng); x = x - _smooth(x, 3)
    return x * np.exp(-_t(dur, sr) * decay)

def _snare(sr, rng, dur=0.22, tone=190, decay=22):
    t = _t(dur, sr)
    body = np.sin(2 * np.pi * tone * t) * np.exp(-t * 30) * 0.6
    sn = _noise(dur, sr, rng); sn = sn - 0.6 * _smooth(sn, 4)
    return (body + sn * np.exp(-t * decay) * 0.7).astype(np.float32)

def _pluck(f, dur, sr, bright=1.0):
    t = _t(dur, sr); y = np.zeros_like(t)
    for k in range(1, 9):
        if f * k > sr * 0.45: break
        y += np.sin(2 * np.pi * f * k * t) * np.exp(-t * (3 + 2.2 * k / bright)) / k
    return y * _adsr(len(t), sr, 0.002, 0.05, 1.0, 0.05)

def _bell(f, dur, sr):
    t = _t(dur, sr)
    y = sum(a * np.sin(2 * np.pi * f * m * t) * np.exp(-t * dcy) for m, a, dcy in ((1, 1, 1.8), (2.76, .4, 3.2), (5.4, .2, 5)))
    return y * _adsr(len(t), sr, 0.004, 0.05, 1.0, 0.1)

def _pad(notes, dur, sr, attack=0.8):
    t = _t(dur, sr); y = np.zeros_like(t)
    for m in notes:
        for det in (-0.12, 0.0, 0.12):
            y += _osc("tri", _hz(m + det), t, 6, sr) * 0.33
    return y * _adsr(len(t), sr, attack, 0.2, 1.0, min(0.8, dur * 0.4))

def _music_plan(seed, style):
    rng = random.Random(seed * 7919 + len(style))
    key = "minor" if style in ("techno", "synthwave", "minimal", "lofi") else rng.choice(["major", "major", "minor"])
    if style == "lofi" and rng.random() < 0.4: key = "major"
    prog = rng.choice(PROGRESSIONS[key])
    root = rng.choice([45, 46, 47, 48, 50, 52, 43])       # tonic of the bass, A2 .. E3 (or G2)
    return rng, key, prog, root

def _bars(total, spb):
    return int(total / (4 * spb)) + 2

def style_techno(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "techno"); bpm = rng.randint(118, 126); spb = 60 / bpm
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    kick, clap, hat = _kick(sr), _snare(sr, nr, 0.16, 0, 26), _hat(sr, nr)
    stab_on = rng.random() < 0.7
    for b in range(_bars(total, spb) * 4):
        t0 = b * spb; bar = b // 4; step = prog[bar % 4]
        T.add(kick, t0, .9); T.add(hat, t0 + spb / 2, .5)
        for k in (1, 3): T.add(hat, t0 + k * spb / 4, .18)
        if b % 4 in (1, 3): T.add(clap, t0, .45)
        f = _hz(root + step); tb = _t(spb * 0.42, sr)
        T.add((_osc("saw", f, tb, 8, sr) * _adsr(len(tb), sr, .003, .1, .5, .05)).astype(np.float32), t0 + spb / 2, .3)
        if stab_on and b % 4 == 2:
            notes = _chord(root + 12 + step, _degree_quality(step, key)); ts = _t(spb * 0.3, sr)
            st = sum(_osc("saw", _hz(m), ts, 6, sr) for m in notes) * _adsr(len(ts), sr, .003, .08, .3, .05)
            T.add(st.astype(np.float32), t0 + spb * 0.75, .12)
    return T.y

def style_lofi(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "lofi"); bpm = rng.randint(78, 88); spb = 60 / bpm; swing = 0.58
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    kick, snare, hat = _kick(sr, .6, .35), _snare(sr, nr, .25, 180, 18), _hat(sr, nr, .04, 120)
    kpat = rng.choice([(0, 2.5), (0, 1.75, 2.5), (0, 2.25, 2.75)])
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[bar % 4]
        for k in kpat: T.add(kick, t0 + k * spb, .7)
        for k in (1, 3): T.add(snare, t0 + k * spb + 0.01, .32)
        for e in range(8):
            off = (e // 2) * spb + (swing * spb if e % 2 else 0)
            T.add(hat, t0 + off, .14 if e % 2 else .2)
        notes = _chord(root + 12 + step, _degree_quality(step, key), seventh=True); dur = 4 * spb
        tp = _t(dur, sr); trem = 1 + 0.15 * np.sin(2 * np.pi * 4.5 * tp)
        ep = sum(_osc("sine", _hz(m), tp) + 0.25 * _osc("sine", _hz(m) * 2, tp) for m in notes) * trem * _adsr(len(tp), sr, .02, .6, .45, .4)
        T.add(ep.astype(np.float32), t0, .12)
        tb = _t(spb * 1.6, sr); T.add((_osc("sine", _hz(root + step), tb) * _adsr(len(tb), sr, .01, .3, .6, .2)).astype(np.float32), t0, .35)
        tb = _t(spb * 1.2, sr); T.add((_osc("sine", _hz(root + step + 7), tb) * _adsr(len(tb), sr, .01, .3, .5, .2)).astype(np.float32), t0 + 2.5 * spb, .22)
    crackle = (nr.random(T.n) < 0.0009).astype(np.float32) * nr.uniform(-1, 1, T.n).astype(np.float32)
    return T.y + 0.25 * _smooth(crackle, 2) + 0.01 * _smooth(nr.standard_normal(T.n).astype(np.float32), 30)

def style_pluck(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "pluck"); bpm = rng.randint(92, 102); spb = 60 / bpm
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    kick, shaker = _kick(sr, .5, .25), _hat(sr, nr, .06, 60)
    pattern = rng.choice([[0, 1, 2, 1, 3, 1, 2, 1], [0, 2, 1, 2, 3, 2, 1, 2], [0, 1, 2, 3, 2, 1, 2, 3]])
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[bar % 4]
        notes = _chord(root + 12 + step, _degree_quality(step, key)) + [root + 24 + step]
        for e, idx in enumerate(pattern):
            T.add(_pluck(_hz(notes[idx]), spb * 1.4, sr, 1.2).astype(np.float32), t0 + e * spb / 2, .2)
        for k in (0, 2): T.add(kick, t0 + k * spb, .55)
        for s16 in range(16): T.add(shaker, t0 + s16 * spb / 4, .09 if s16 % 2 else .05)
        tb = _t(spb * 1.8, sr)
        T.add((_osc("tri", _hz(root + step), tb, 6, sr) * _adsr(len(tb), sr, .01, .3, .6, .3)).astype(np.float32), t0, .4)
    return T.y

def style_synthwave(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "synthwave"); bpm = rng.randint(98, 108); spb = 60 / bpm
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    kick, snare = _kick(sr, .9, .3), _snare(sr, nr, .4, 160, 14)
    arp = rng.choice([[0, 1, 2, 3], [0, 2, 1, 3], [0, 1, 2, 1], [3, 2, 1, 0]])
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[bar % 4]; q = _degree_quality(step, key)
        for k in (0, 2): T.add(kick, t0 + k * spb, .85)
        for k in (1, 3): T.add(snare, t0 + k * spb, .3)
        for s8 in range(8):
            tb = _t(spb * 0.45, sr)
            T.add((_osc("saw", _hz(root + step), tb, 10, sr) * _adsr(len(tb), sr, .002, .08, .4, .04)).astype(np.float32), t0 + s8 * spb / 2, .22)
        notes = _chord(root + 24 + step, q) + [root + 36 + step]
        for s16 in range(16):
            ta = _t(spb * 0.22, sr); m = notes[arp[s16 % 4]]
            T.add((_osc("square", _hz(m), ta, 9, sr) * _adsr(len(ta), sr, .002, .06, .3, .04)).astype(np.float32), t0 + s16 * spb / 4, .06)
        T.add(_pad(_chord(root + 12 + step, q), 4 * spb, sr, .3).astype(np.float32), t0, .07)
    return T.y

def style_ambient(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "ambient"); bpm = rng.randint(70, 80); spb = 60 / bpm
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    sub = _kick(sr, .25, .5)
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[bar % 4]; q = _degree_quality(step, key)
        T.add(_pad(_chord(root + 12 + step, q, seventh=True), 4.6 * spb, sr, 1.2).astype(np.float32), t0, .16)
        for k in (0, 2): T.add(sub, t0 + k * spb, .45)
        for k in range(rng.randint(2, 4)):
            m = rng.choice(_chord(root + 24 + step, q) + [root + 36 + step])
            T.add(_bell(_hz(m), 2.5, sr).astype(np.float32), t0 + rng.choice([0, 1, 1.5, 2, 3, 3.5]) * spb, .12)
    swell = _smooth(nr.standard_normal(T.n).astype(np.float32), 60) * (0.5 + 0.5 * np.sin(2 * np.pi * np.arange(T.n) / (sr * 8)))
    return T.y + 0.5 * swell

def style_minimal(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "minimal"); bpm = rng.randint(108, 116); spb = 60 / bpm
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    kick, hat, rim = _kick(sr, .8, .25), _hat(sr, nr, .03, 160), _snare(sr, nr, .05, 900, 80)
    seq = rng.choice([[0, 0, 12, 0, 7, 0, 12, 7], [0, 12, 0, 7, 0, 12, 10, 7], [0, 0, 7, 12, 0, 3, 7, 12]])
    blips = [rng.random() < 0.18 for _ in range(16)]
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[bar % 4]
        for k in range(4): T.add(kick, t0 + k * spb, .55)
        for s16 in range(16): T.add(hat, t0 + s16 * spb / 4, .22 if s16 % 4 == 2 else .08)
        for k in (1, 3): T.add(rim, t0 + k * spb + spb / 2, .25)
        for s8 in range(8):
            tb = _t(spb * 0.4, sr); m = root + step + seq[s8]
            T.add((_osc("square", _hz(m), tb, 7, sr) * _adsr(len(tb), sr, .002, .07, .35, .04)).astype(np.float32), t0 + s8 * spb / 2, .24)
        for s16, on in enumerate(blips):
            if on:
                tb = _t(0.07, sr)
                T.add((_osc("sine", _hz(root + 36 + step + rng.choice([0, 7, 12])), tb) * np.exp(-tb * 40)).astype(np.float32), t0 + s16 * spb / 4, .12)
    return T.y

MUSIC = {"techno": style_techno, "lofi": style_lofi, "pluck": style_pluck, "synthwave": style_synthwave,
         "ambient": style_ambient, "minimal": style_minimal}

# ---- second set of music styles ----
def _ride(sr, rng, dur=0.5):
    t = _t(dur, sr)
    y = sum(np.sin(2 * np.pi * f * t) for f in (3150, 4870, 6230, 7410)) * 0.15 + _noise(dur, sr, rng) * 0.3
    return (y * np.exp(-t * 9)).astype(np.float32)

def _tom(sr, f0=110, dur=0.45):
    t = _t(dur, sr)
    return (np.sin(2 * np.pi * (f0 + f0 * 0.8 * np.exp(-t * 14)) * t) * np.exp(-t * 6)).astype(np.float32)

def _808(f, dur, sr):
    t = _t(dur, sr)
    y = np.sin(2 * np.pi * np.cumsum(f * (1 + 1.4 * np.exp(-t * 30))) / sr)
    return (np.tanh(1.6 * y) * _adsr(len(t), sr, 0.003, 0.2, 0.8, 0.15)).astype(np.float32)

def _rhodes(notes, dur, sr):
    t = _t(dur, sr); trem = 1 + 0.18 * np.sin(2 * np.pi * 5 * t)
    y = sum(np.sin(2 * np.pi * _hz(m) * t) + 0.35 * np.sin(2 * np.pi * 2 * _hz(m) * t) * np.exp(-t * 3) for m in notes)
    return (y * trem * _adsr(len(t), sr, 0.01, 0.5, 0.5, 0.3)).astype(np.float32)

def style_chiptune(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "chiptune"); bpm = rng.randint(132, 146); spb = 60 / bpm
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    tk = _t(0.12, sr)
    kick = (np.sign(np.sin(2 * np.pi * np.cumsum(140 * np.exp(-tk * 30) + 40) / sr)) * np.exp(-tk * 30) * 0.6).astype(np.float32)
    snare = (_noise(0.09, sr, nr) * np.exp(-_t(0.09, sr) * 40)).astype(np.float32)
    arp = rng.choice([[0, 1, 2, 3, 2, 1], [0, 2, 1, 3], [0, 1, 2, 1, 3, 1, 2, 1]])
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[bar % 4]; q = _degree_quality(step, key)
        for k in range(4): T.add(kick if k % 2 == 0 else snare, t0 + k * spb, .5 if k % 2 == 0 else .35)
        notes = _chord(root + 24 + step, q) + [root + 36 + step]
        for s16 in range(16):
            ta = _t(spb * 0.24, sr); m = notes[arp[s16 % len(arp)] % len(notes)]
            T.add((np.sign(np.sin(2 * np.pi * _hz(m) * ta)) * _adsr(len(ta), sr, .001, .05, .5, .02) * 0.5).astype(np.float32), t0 + s16 * spb / 4, .08)
        for s8 in range(8):
            tb = _t(spb * 0.45, sr); m = root + 12 + step + (12 if s8 % 2 else 0)
            T.add((np.sign(np.sin(2 * np.pi * _hz(m) * tb)) * _adsr(len(tb), sr, .001, .05, .6, .03) * 0.5).astype(np.float32), t0 + s8 * spb / 2, .1)
    return T.y

def style_house(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "house"); bpm = rng.randint(120, 126); spb = 60 / bpm
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    kick, clap, hat, ohat = _kick(sr, .9, .3), _snare(sr, nr, .2, 0, 20), _hat(sr, nr, .04, 120), _hat(sr, nr, .18, 18)
    stab = rng.choice([[0.5, 1.5, 2.5, 3.5], [0.5, 1.75, 2.5, 3.25], [0.75, 1.5, 2.75, 3.5]])
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[bar % 4]; q = _degree_quality(step, key)
        for k in range(4):
            T.add(kick, t0 + k * spb, .85); T.add(ohat, t0 + k * spb + spb / 2, .22)
            for e in (0.25, 0.75): T.add(hat, t0 + (k + e) * spb, .1)
        for k in (1, 3): T.add(clap, t0 + k * spb, .4)
        notes = _chord(root + 24 + step, q, seventh=True)
        for st in stab:
            tp = _t(spb * 0.3, sr)
            pn = sum(_osc("sine", _hz(m), tp) + 0.5 * _osc("sine", 2 * _hz(m), tp) * np.exp(-tp * 12) for m in notes)
            T.add((pn * _adsr(len(tp), sr, .002, .12, .25, .05)).astype(np.float32), t0 + st * spb, .09)
        for k in range(4):
            tb = _t(spb * 0.4, sr)
            T.add((_osc("saw", _hz(root + step), tb, 6, sr) * _adsr(len(tb), sr, .003, .1, .5, .05)).astype(np.float32), t0 + k * spb + spb / 2, .25)
    return T.y

def style_jazzhop(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "jazzhop"); bpm = rng.randint(84, 92); spb = 60 / bpm; sw = 0.62
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    kick, brush, ride = _kick(sr, .5, .3), _snare(sr, nr, .3, 220, 12), _ride(sr, nr)
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[bar % 4]; q = _degree_quality(step, key)
        for k in (0, 2.5): T.add(kick, t0 + k * spb, .55)
        for k in (1, 3): T.add(brush, t0 + k * spb, .22)
        for k in range(4):
            T.add(ride, t0 + k * spb, .16)
            if k % 2: T.add(ride, t0 + (k + sw) * spb, .1)
        T.add(_rhodes(_chord(root + 12 + step, q, seventh=True), 3.6 * spb, sr), t0, .1)
        walk = [root + step, root + step + (3 if q == "m" else 4), root + step + 7, root + step + rng.choice([9, 10, 5])]
        for k, m in enumerate(walk):
            tb = _t(spb * 0.9, sr)
            T.add((_osc("tri", _hz(m), tb, 5, sr) * _adsr(len(tb), sr, .005, .2, .4, .1)).astype(np.float32), t0 + k * spb, .4)
    return T.y

def style_cinematic(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "cinematic"); bpm = rng.randint(88, 100); spb = 60 / bpm
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    tom, tom2 = _tom(sr, 90), _tom(sr, 130)
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[bar % 4]; q = _degree_quality(step, key)
        for k, tt in ((0, tom), (1.5, tom2), (2.5, tom), (3.5, tom2)): T.add(tt, t0 + k * spb, .5)
        for s8 in range(8):
            tb = _t(spb * 0.45, sr)
            T.add((_osc("saw", _hz(root + step), tb, 5, sr) * _adsr(len(tb), sr, .004, .1, .5, .05)).astype(np.float32), t0 + s8 * spb / 2, .2)
        T.add(_pad(_chord(root + 12 + step, q), 4.2 * spb, sr, 1.0).astype(np.float32), t0, .14)
        if bar % 4 == 3:                            # a riser into the next phrase
            n = int(4 * spb * sr); x = nr.standard_normal(n).astype(np.float32)
            T.add((x - _smooth(x, 4)) * np.linspace(0, 1, n) ** 2 * 0.25, t0)
    return T.y

def style_dnb(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "dnb"); bpm = rng.randint(168, 176); spb = 60 / bpm
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    kick, snare, hat = _kick(sr, .9, .22), _snare(sr, nr, .2, 210, 22), _hat(sr, nr, .03, 150)
    kpat = rng.choice([(0, 2.5), (0, 0.75, 2.5), (0, 2.25, 2.75)])
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[(bar // 2) % 4]; q = _degree_quality(step, key)
        for k in kpat: T.add(kick, t0 + k * spb, .8)
        for k in (1, 3): T.add(snare, t0 + k * spb, .5)
        for e in range(8): T.add(hat, t0 + e * spb / 2, .14 if e % 2 else .2)
        if bar % 2 == 0:
            tb = _t(8 * spb, sr)
            reese = sum(_osc("saw", _hz(root + step) * dt, tb, 4, sr) for dt in (0.995, 1.005))
            T.add((reese * _adsr(len(tb), sr, .02, .3, .7, .3)).astype(np.float32), t0, .14)
            T.add(_pad(_chord(root + 24 + step, q), 8 * spb, sr, .6).astype(np.float32), t0, .07)
    return T.y

def style_trap(total, sr, seed):
    rng, key, prog, root = _music_plan(seed, "trap"); bpm = rng.randint(136, 146); spb = 60 / bpm
    T = _Track(total, sr); nr = np.random.default_rng(seed)
    clap, hat = _snare(sr, nr, .22, 0, 18), _hat(sr, nr, .035, 140)
    bell_notes = [rng.choice([0, 3, 7, 10, 12]) for _ in range(8)]
    for bar in range(_bars(total, spb)):
        t0 = bar * 4 * spb; step = prog[(bar // 2) % 4]
        T.add(_808(_hz(root - 12 + step), 2.2 * spb, sr), t0, .55)
        T.add(_808(_hz(root - 12 + step), 1.2 * spb, sr), t0 + 2.75 * spb, .45)
        T.add(clap, t0 + 2 * spb, .5)
        for e in range(8):
            T.add(hat, t0 + e * spb / 2, .14)
            if rng.random() < 0.25:                 # hi-hat rolls
                for r in range(1, 3): T.add(hat, t0 + e * spb / 2 + r * spb / 6, .08)
        for e in (0, 1.5, 3):
            m = root + 24 + step + bell_notes[(bar * 3 + int(e * 2)) % 8]
            T.add(_bell(_hz(m), 0.8, sr).astype(np.float32), t0 + e * spb, .07)
    return T.y

MUSIC.update({"chiptune": style_chiptune, "house": style_house, "jazzhop": style_jazzhop,
              "cinematic": style_cinematic, "dnb": style_dnb, "trap": style_trap})

def music(style, total, sr, seed=0):
    """A music bed in the given style, the length of the short, at a fixed loudness (RMS)."""
    y = MUSIC[style](total, sr, seed)[: int(total * sr) + 1]
    # level from half the full-range energy and half the part a phone speaker plays (above ~150 Hz),
    # so bass-heavy styles do not end up faint on phones
    hp = y - _smooth(y, sr / 150)
    level = float(np.sqrt(0.5 * np.mean(y ** 2) + 0.5 * np.mean(hp ** 2) * 4)) or 1.0
    return (y * (0.22 / level)).astype(np.float32)

# ---------------- visuals ----------------
W, H = 720, 1280
_bg = None
def _traces(seed=7):
    rng = random.Random(seed); paths = []
    for _ in range(16):
        x = rng.randrange(0, W // 40) * 40 + 20; y = rng.randrange(0, H // 40) * 40 + 20
        pts = [(x, y)]
        for _ in range(rng.randint(4, 8)):
            if rng.random() < 0.5: x = min(W - 20, max(20, x + rng.choice([-1, 1]) * rng.randint(2, 7) * 40))
            else: y = min(H - 20, max(20, y + rng.choice([-1, 1]) * rng.randint(2, 7) * 40))
            pts.append((x, y))
        segs = list(zip(pts, pts[1:])); L = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in segs)
        if L > 200: paths.append((pts, L, rng.uniform(0, 1), rng.uniform(140, 260)))
    return paths

PATHS = _traces()
_bases = {}
def background_base(bg, dot, trace):
    key = ("circuit", bg, dot, trace)
    if key not in _bases:
        im = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(im)
        for x in range(0, W, 40):
            for y in range(0, H, 40):
                d.point((x + 20, y + 20), fill=dot)
        for pts, L, ph, sp in PATHS:
            d.line(pts, fill=trace, width=2)
            for p in (pts[0], pts[-1]): d.ellipse((p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4), outline=trace, width=2)
        _bases[key] = im
    return _bases[key]

def _point_on(pts, dist):
    for a, b in zip(pts, pts[1:]):
        seg = abs(a[0] - b[0]) + abs(a[1] - b[1])
        if dist <= seg:
            f = dist / max(seg, 1); return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        dist -= seg
    return pts[-1]

def draw_pulses(d, t, color, glow):
    for pts, L, ph, sp in PATHS:
        dist = (ph * L + t * sp) % (L + 300)
        if dist > L: continue
        for k, (r, c) in enumerate(((9, glow), (5, color))):
            x, y = _point_on(pts, dist)
            d.ellipse((x - r, y - r, x + r, y + r), fill=c)
        for back in (18, 36):                       # short fading tail
            if dist - back > 0:
                x, y = _point_on(pts, dist - back); r = 3 if back == 18 else 2
                d.ellipse((x - r, y - r, x + r, y + r), fill=glow)

def confetti(d, t, t0, colors, seed=0):
    """Two confetti cannons firing up from the bottom corners; lasts ~1.7 s."""
    dt = t - t0
    if dt < 0 or dt > 1.7: return
    rng = random.Random(seed)
    for i in range(130):
        side = 1 if i % 2 else -1                     # left cannon fires up-right, right cannon up-left
        ang = -math.pi / 2 + side * rng.uniform(0.05, 0.8); sp = rng.uniform(650, 2100)
        drag = (1 - math.exp(-2.2 * dt)) / 2.2        # air drag slows them down
        x0 = W / 2 - side * (W / 2 - 30)
        x = x0 + math.cos(ang) * sp * drag; y = H - 120 + math.sin(ang) * sp * drag + 520 * dt * dt
        if y > H or y < -20: continue
        s = rng.uniform(7, 14); rot = rng.uniform(0, 6.28) + dt * rng.uniform(-11, 11)
        c = colors[i % len(colors)]
        pts = [(x + s * math.cos(rot + k * math.pi / 2) * (1 if k % 2 == 0 else 0.5),
                y + s * math.sin(rot + k * math.pi / 2) * (1 if k % 2 == 0 else 0.5)) for k in range(4)]
        d.polygon(pts, fill=c)

def ease_out_back(x, s=1.9):
    x = max(0.0, min(1.0, x)); x -= 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2

def stage_transform(t, scene_start, scene_end, punches):
    """Returns (scale, dx, dy, alpha) for the scene layer at time t."""
    k = (t - scene_start) / 0.28
    scale = 1.0; dy = 0.0; dx = 0.0; alpha = 1.0
    if k < 1:
        e = ease_out_back(k); scale = 1.12 - 0.12 * e; dy = 60 * (1 - e)
    for pt, strength in punches:
        dt = t - pt
        if 0 <= dt < 0.22:
            scale *= 1 + strength * (1 - dt / 0.22) ** 2
        if strength >= 0.05 and 0 <= dt < 0.18:     # big hits also shake
            r = random.Random(int(pt * 1000) + int(dt * 60))
            dx += r.uniform(-7, 7) * (1 - dt / 0.18); dy += r.uniform(-7, 7) * (1 - dt / 0.18)
    if scene_end - t < 0.12:
        alpha = max(0.0, (scene_end - t) / 0.12)
    return scale, dx, dy, alpha

# ---------------- themed backgrounds (one per narrator) ----------------
def _mix(c1, c2, a):
    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * a)) for i in range(3))

def _vgrad(stops):
    """Vertical gradient through [(y_fraction, color), ...]."""
    col = Image.new("RGB", (1, H)); px = col.load()
    for y in range(H):
        f = y / (H - 1)
        for (f0, c0), (f1, c1) in zip(stops, stops[1:]):
            if f0 <= f <= f1:
                px[0, y] = _mix(c0, c1, (f - f0) / max(f1 - f0, 1e-6)); break
    return col.resize((W, H))

def _base(style, p, build):
    key = (style, tuple(sorted((k, v) for k, v in p.items() if isinstance(v, tuple))))
    if key not in _bases:
        _bases[key] = build()
    return _bases[key]

def _circuit(t, p, font):
    im = background_base(p["BG"], p["dot"], p["trace"]).copy()
    draw_pulses(ImageDraw.Draw(im), t, p["pulse"], p["glow"])
    return im

def _bokeh(t, p, font):
    """Soft out-of-focus lights drifting upward, with a few twinkles."""
    def build():
        rng = random.Random(11)
        tex = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(tex)
        for i in range(30):
            r = rng.uniform(34, 120); x = rng.uniform(-40, W + 40); y = rng.uniform(0, H)
            c = p["glows"][i % len(p["glows"])]; a = int(rng.uniform(28, 64))
            for dy in (-H, 0, H):                     # drawn three times so the texture wraps without a seam
                d.ellipse((x - r, y + dy - r, x + r, y + dy + r), fill=c + (a,))
        tex = tex.filter(ImageFilter.GaussianBlur(16))
        flat = Image.new("RGBA", (W, H), p["BG"] + (255,)); flat.alpha_composite(tex)
        flat = flat.convert("RGB")
        canvas = Image.new("RGB", (W, 2 * H)); canvas.paste(flat, (0, 0)); canvas.paste(flat, (0, H))
        return canvas
    canvas = _base("bokeh", p, build)
    y0 = int(t * 22) % H
    im = canvas.crop((0, y0, W, y0 + H)); d = ImageDraw.Draw(im)
    rng = random.Random(5)
    for k in range(16):
        x, y = rng.uniform(20, W - 20), rng.uniform(20, H - 20)
        a = max(0.0, math.sin(t * rng.uniform(1.2, 2.4) + k)) ** 3
        if a > 0.05:
            r = 1.5 + 2.5 * a
            d.ellipse((x - r, y - r, x + r, y + r), fill=_mix(p["BG"], p["spark"], a))
    return im

GLYPHS = ["{ }", "x²", "π", "0", "1", "i", "j", "N", "+", "Δ", "[ ]", "√", "( )", "42", "∑", "x", "%", "=", "≈", "y"]
def _paper(t, p, font):
    """Graph paper with math and code glyphs floating up like pencil notes."""
    def build():
        im = Image.new("RGB", (W, H), p["BG"]); d = ImageDraw.Draw(im)
        for x in range(0, W, 24): d.line((x, 0, x, H), fill=p["grid"], width=1)
        for y in range(0, H, 24): d.line((0, y, W, y), fill=p["grid"], width=1)
        for x in range(0, W, 120): d.line((x, 0, x, H), fill=p["grid2"], width=1)
        for y in range(0, H, 120): d.line((0, y, W, y), fill=p["grid2"], width=1)
        d.line((22, 0, 22, H), fill=p["margin"], width=2)
        return im
    im = _base("paper", p, build).copy(); d = ImageDraw.Draw(im)
    rng = random.Random(3)
    for k in range(22):
        g = GLYPHS[k % len(GLYPHS)]; size = rng.choice([22, 26, 30, 36])
        sp = rng.uniform(16, 34); ph = rng.uniform(0, 1); x0 = rng.uniform(30, W - 90)
        y = H + 40 - ((t * sp + ph * (H + 80)) % (H + 80))
        x = x0 + 10 * math.sin(t * 0.7 + ph * 6.28)
        d.text((x, y), g, font=font("mono", size), fill=p["glyph"])
    return im

def _neon(t, p, font):
    """Synthwave: stars above, a glowing grid floor rolling toward you below."""
    hz = 830
    def build():
        im = _vgrad([(0, p["sky_top"]), (hz / H, p["sky_low"]), (hz / H + 0.002, p["floor"]), (1, p["BG"])])
        d = ImageDraw.Draw(im); rng = random.Random(9)
        for _ in range(90):
            x, y = rng.uniform(0, W), rng.uniform(0, hz - 30)
            d.point((x, y), fill=_mix(p["sky_top"], (255, 255, 255), rng.uniform(.25, .7)))
        d.line((0, hz, W, hz), fill=_mix(p["floor"], p["grid_hi"], .8), width=2)
        for k in range(-14, 15):
            d.line((W / 2 + k * 10, hz, W / 2 + k * 150, H), fill=_mix(p["floor"], p["grid_lo"], .55), width=2)
        return im
    im = _base("neon", p, build).copy(); d = ImageDraw.Draw(im)
    N = 11; phase = (t * 0.55) % 1
    for k in range(N):
        f = (k + phase) / N; y = hz + (H - hz) * f * f
        d.line((0, y, W, y), fill=_mix(p["floor"], p["grid_hi"], 0.25 + 0.55 * f), width=2 if f > .4 else 1)
    rng = random.Random(4)
    for k in range(14):
        x, y = rng.uniform(10, W - 10), rng.uniform(10, hz - 40)
        a = max(0.0, math.sin(t * rng.uniform(1.0, 2.2) + k * 1.7)) ** 2
        if a > .05:
            r = 1 + 2.5 * a
            d.ellipse((x - r, y - r, x + r, y + r), fill=_mix(p["sky_top"], (255, 255, 255), .4 + .6 * a))
    return im

def _ocean(t, p, font):
    """Slow waves rolling across, bubbles rising."""
    def build():
        return _vgrad([(0, p["top"]), (1, p["BG"])])
    im = _base("ocean", p, build).copy(); d = ImageDraw.Draw(im)
    for k in range(7):
        y0 = 150 + k * 165; amp = 12 + 8 * (k % 3); wl = 280 + 55 * k; sp = 0.5 + 0.12 * k
        col = _mix(p["BG"], p["wave"], 0.16 + 0.05 * (k % 3))
        pts = [(x, y0 + amp * math.sin(2 * math.pi * (x / wl) + t * sp + k)) for x in range(-20, W + 24, 24)]
        d.line(pts, fill=col, width=2, joint="curve")
    rng = random.Random(8)
    for k in range(24):
        x0 = rng.uniform(20, W - 20); sp = rng.uniform(30, 70); ph = rng.uniform(0, 1); r = rng.uniform(2.5, 7)
        y = H + 20 - ((t * sp + ph * (H + 40)) % (H + 40)); x = x0 + 7 * math.sin(t * 1.3 + ph * 6.28)
        d.ellipse((x - r, y - r, x + r, y + r), outline=_mix(p["BG"], p["bubble"], .55), width=1)
    return im

def _blueprint(t, p, font):
    """Drafting grid with rotating gauges and a scan line."""
    gauges = [((585, 300), 120), ((130, 1000), 105), ((600, 1120), 70)]
    def build():
        im = Image.new("RGB", (W, H), p["BG"]); d = ImageDraw.Draw(im)
        for x in range(0, W, 20): d.line((x, 0, x, H), fill=p["grid"], width=1)
        for y in range(0, H, 20): d.line((0, y, W, y), fill=p["grid"], width=1)
        for x in range(0, W, 100): d.line((x, 0, x, H), fill=p["grid2"], width=1)
        for y in range(0, H, 100): d.line((0, y, W, y), fill=p["grid2"], width=1)
        for (cx, cy), r in gauges:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=p["ink"], width=2)
            d.ellipse((cx - r * .62, cy - r * .62, cx + r * .62, cy + r * .62), outline=p["grid2"], width=1)
            d.line((cx - r - 14, cy, cx + r + 14, cy), fill=p["grid2"], width=1)
            d.line((cx, cy - r - 14, cx, cy + r + 14), fill=p["grid2"], width=1)
        d.line((60, 640, 300, 640), fill=p["ink"], width=1)
        for x in (60, 300): d.line((x, 630, x, 650), fill=p["ink"], width=1)
        return im
    im = _base("blueprint", p, build).copy(); d = ImageDraw.Draw(im)
    for i, ((cx, cy), r) in enumerate(gauges):
        a = math.radians(t * (40 + 15 * i) * (1 if i % 2 == 0 else -1))
        d.line((cx, cy, cx + r * math.cos(a), cy + r * math.sin(a)), fill=p["sweep"], width=2)
        for k in range(12):
            b = a + k * math.pi / 6
            d.line((cx + r * .86 * math.cos(b), cy + r * .86 * math.sin(b), cx + r * math.cos(b), cy + r * math.sin(b)), fill=p["ink"], width=2)
    y = (t * 80) % (H + 60) - 30
    for k, w in ((0, 2), (8, 1), (18, 1)):
        d.line((0, y - k, W, y - k), fill=_mix(p["BG"], p["sweep"], .45 - k * .018), width=w)
    return im

STYLES = {"circuit": _circuit, "bokeh": _bokeh, "paper": _paper, "neon": _neon, "ocean": _ocean, "blueprint": _blueprint}
def backdrop(style, t, p, font):
    """A fresh RGB background frame for time t in the given style; p holds the theme's colors."""
    return STYLES[style](t, p, font)

# ---- second set of backgrounds ----
RAIN_CHARS = "01{}<>[]();=+*%&|^~abcdefghijklmnopqrstuvwxyz0123456789"
def _terminal(t, p, font):
    """Green code rain behind faint scanlines, like an old terminal."""
    def build():
        im = Image.new("RGB", (W, H), p["BG"]); d = ImageDraw.Draw(im)
        for y in range(0, H, 3):
            d.line((0, y, W, y), fill=_mix(p["BG"], p["scan"], 0.5), width=1)
        return im
    im = _base("terminal", p, build).copy(); d = ImageDraw.Draw(im)
    f = font("mono", 22); rng = random.Random(21)
    for c in range(15):
        x = 18 + c * 48 + rng.randint(-6, 6); sp = rng.uniform(70, 160); ph = rng.uniform(0, H + 300)
        head = (t * sp + ph) % (H + 300) - 150
        for k in range(9):
            y = head - k * 26
            if y < -30 or y > H: continue
            ch = RAIN_CHARS[(c * 7 + int((head - k * 26) // 26) * 13) % len(RAIN_CHARS)]
            col = p["head"] if k == 0 else _mix(p["BG"], p["rain"], max(0.15, 1 - k / 9))
            d.text((x, y), ch, font=f, fill=col)
    return im

def _sunset(t, p, font):
    """Vaporwave dusk: striped sun sinking behind the hills, shimmer on the water. Kept low, under the captions."""
    hz, cx, cy, r = 1040, W // 2, 1000, 170
    def build():
        im = _vgrad([(0, p["sky_top"]), (0.5, p["sky_mid"]), (hz / H, p["horizon"]), (hz / H + 0.001, p["water"]), (1, p["water"])])
        d = ImageDraw.Draw(im)
        for y in range(cy - r, min(cy + r, hz)):
            half = (r * r - (y - cy) ** 2) ** 0.5
            d.line((cx - half, y, cx + half, y), fill=_mix(p["sun_top"], p["sun_bot"], (y - (cy - r)) / (2 * r)))
        for pts, col in (([(0, hz), (0, 960), (110, 900), (220, 975), (330, 920), (420, 990), (420, hz)], p["hill"]),
                         ([(380, hz), (380, 985), (500, 925), (610, 970), (720, 905), (720, hz)], p["hill2"])):
            d.polygon(pts, fill=col)
        d.line((0, hz, W, hz), fill=p["horizon"], width=2)
        return im
    base = _base("sunset", p, build)
    im = base.copy(); d = ImageDraw.Draw(im)
    for k in range(6):                           # stripes drift up through the lower half of the sun
        y = cy + 8 + ((k * 26 + t * 14) % 156)
        if y > hz - 4: continue
        h = 3 + (y - cy) // 30
        half = max(0.0, (r * r - (y - cy) ** 2)) ** 0.5
        d.rectangle((cx - half - 2, y, cx + half + 2, y + h), fill=base.getpixel((5, int(y))))
    rng = random.Random(6)
    for k in range(26):
        y = hz + 8 + rng.uniform(0, H - hz - 20); w = rng.uniform(20, 90)
        x = cx + rng.uniform(-160, 160) + 14 * math.sin(t * 1.1 + k)
        d.line((x - w / 2, y, x + w / 2, y), fill=_mix(p["water"], p["sun_bot"], 0.35 + 0.25 * math.sin(t * 2 + k)), width=2)
    return im

CHALK_NOTES = ["i = b * d + t", "<<< N, M >>>", "C[i] = A[i] + B[i]", "warp = 32", "row * W + col", "if (i < N)"]
def _chalk(t, p, font):
    """A green chalkboard: speckled texture, smudges, faint notes that come and go, falling dust."""
    def build():
        rng = random.Random(4)
        im = Image.new("RGB", (W, H), p["BG"]); d = ImageDraw.Draw(im)
        for _ in range(7000):
            x, y = rng.uniform(0, W), rng.uniform(0, H); d.point((x, y), fill=p["speck"])
        sm = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ds = ImageDraw.Draw(sm)
        for _ in range(9):
            x, y = rng.uniform(-100, W), rng.uniform(0, H); w, h = rng.uniform(160, 420), rng.uniform(40, 110)
            ds.ellipse((x, y, x + w, y + h), fill=p["smudge"] + (90,))
        sm = sm.filter(ImageFilter.GaussianBlur(22))
        im = im.convert("RGBA"); im.alpha_composite(sm); im = im.convert("RGB")
        d = ImageDraw.Draw(im)
        d.rectangle((0, H - 18, W, H), fill=p["frame"])
        return im
    im = _base("chalk", p, build).copy(); d = ImageDraw.Draw(im)
    f = font("display", 30)
    spots = [(60, 230), (380, 360), (90, 560), (400, 700), (70, 880), (360, 1180)]
    for k, (x, y) in enumerate(spots):
        a = 0.5 + 0.5 * math.sin(t * 0.35 + k * 1.3)
        d.text((x, y), CHALK_NOTES[k], font=f, fill=_mix(p["BG"], p["chalk"], 0.35 + 0.45 * a))
    rng = random.Random(12)
    for k in range(40):
        x0 = rng.uniform(0, W); sp = rng.uniform(12, 30); ph = rng.uniform(0, H)
        y = (ph + t * sp) % H; x = x0 + 6 * math.sin(t * 0.8 + k)
        d.point((x, y), fill=p["dust"]); d.point((x + 1, y), fill=_mix(p["BG"], p["dust"], 0.5))
    return im

def _space(t, p, font):
    """Deep space: a soft nebula, stars drifting past in three layers, a ringed planet low in the corner."""
    def build():
        rng = random.Random(17)
        tex = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(tex)
        for i in range(14):
            r = rng.uniform(90, 220); x = rng.uniform(-60, W + 60); y = rng.uniform(80, 900)
            d.ellipse((x - r, y - r, x + r, y + r), fill=p["nebula"][i % 3] + (int(rng.uniform(20, 46)),))
        tex = tex.filter(ImageFilter.GaussianBlur(40))
        im = Image.new("RGBA", (W, H), p["BG"] + (255,)); im.alpha_composite(tex); im = im.convert("RGB")
        d = ImageDraw.Draw(im); cx, cy, r = 640, 1150, 150
        for y in range(cy - r, cy + r):
            half = max(0.0, r * r - (y - cy) ** 2) ** 0.5
            d.line((cx - half, y, cx + half, y), fill=_mix(p["planet"], p["BG"], 0.15 + 0.6 * (y - (cy - r)) / (2 * r)))
        d.ellipse((cx - 250, cy - 40, cx + 250, cy + 40), outline=p["ring"], width=3)
        return im
    im = _base("space", p, build).copy(); d = ImageDraw.Draw(im)
    rng = random.Random(29)
    for layer, (n, sp, size, br) in enumerate(((70, 8, 1, .35), (45, 22, 1.5, .6), (22, 48, 2.2, .95))):
        for _ in range(n):
            x, y0 = rng.uniform(0, W), rng.uniform(0, H)
            y = (y0 + t * sp) % H; s = size
            c = _mix(p["BG"], p["star"], br * (0.7 + 0.3 * math.sin(t * 2 + x)))
            d.ellipse((x - s, y - s, x + s, y + s), fill=c)
    k = int(t // 6); ph = t - k * 6
    if ph < 0.6:                                  # a shooting star every six seconds
        r2 = random.Random(k); x0, y0 = r2.uniform(100, W), r2.uniform(60, 500)
        x1, y1 = x0 - 500 * ph, y0 + 260 * ph
        d.line((x1, y1, x1 + 70, y1 - 36), fill=_mix(p["BG"], p["star"], 1 - ph / 0.6), width=2)
    return im

def _aurora(t, p, font):
    """Northern lights: three soft curtains waving over a starry sky and dark hills."""
    def build():
        im = _vgrad([(0, p["sky_top"]), (1, p["sky_bot"])]); d = ImageDraw.Draw(im); rng = random.Random(3)
        for _ in range(120):
            x, y = rng.uniform(0, W), rng.uniform(0, 1000); d.point((x, y), fill=_mix(p["sky_top"], p["star"], rng.uniform(.3, .8)))
        d.polygon([(0, H), (0, 1120), (140, 1050), (260, 1110), (400, 1030), (560, 1100), (720, 1040), (720, H)], fill=p["hill"])
        return im
    im = _base("aurora", p, build).copy()
    w2, h2 = W // 2, H // 2
    lay = Image.new("RGBA", (w2, h2), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for k, col in enumerate(p["bands"]):
        base_y = 60 + k * 70
        for x in range(0, w2, 3):
            y1 = base_y + 24 * math.sin(x / 40 + t * 0.55 + k * 1.7) + 10 * math.sin(x / 15 - t * 0.9 + k)
            h = 70 + 34 * math.sin(x / 31 + t * 0.4 + 2 * k)
            a = 0.55 + 0.45 * math.sin(x / 23 + t * 0.8 + k * 2)
            d.line((x, y1, x, y1 + h * 0.35), fill=col + (int(70 * a),), width=3)
            d.line((x, y1 + h * 0.35, x, y1 + h), fill=col + (int(28 * a),), width=3)
    lay = lay.resize((W, H), Image.BILINEAR)
    im.paste(lay.convert("RGB"), (0, 0), lay)
    return im

def _pop(t, p, font):
    """Pop art: halftone dots sliding by, a striped band, big shapes turning slowly in the corners."""
    def build():
        tex = Image.new("RGB", (W + 80, H + 80), p["BG"]); d = ImageDraw.Draw(tex)
        for gy in range(0, H + 80, 20):
            for gx in range(0, W + 80, 20):
                r = 1.5 + 5.5 * ((gx + gy) / (W + H + 160))
                d.ellipse((gx - r, gy - r, gx + r, gy + r), fill=p["dots"])
        return tex
    tex = _base("pop", p, build)
    off = int((t * 16) % 20)
    im = tex.crop((off, off, off + W, off + H)); d = ImageDraw.Draw(im)
    s0 = (t * 40) % 60
    for k in range(-2, 16):                      # striped band across the top right
        x = 360 + k * 60 + s0
        d.polygon([(x, 0), (x + 30, 0), (x - 90, 120), (x - 120, 120)], fill=p["stripe"])
    for (cx, cy, r, n, col, sp) in ((712, 150, 58, 3, p["shape2"], 0.5), (70, 1180, 90, 4, p["shape"], -0.35), (660, 1210, 46, 0, p["shape"], 0)):
        if n == 0:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=7); continue
        a = t * sp
        pts = [(cx + r * math.cos(a + i * 2 * math.pi / n), cy + r * math.sin(a + i * 2 * math.pi / n)) for i in range(n)]
        d.polygon(pts, outline=col, width=7)
    return im

STYLES.update({"terminal": _terminal, "sunset": _sunset, "chalk": _chalk, "space": _space, "aurora": _aurora, "pop": _pop})


# ---------------- kinetic captions ----------------
def caption_words(text):
    """Words to show (markers removed) and which are keywords (inside **...**)."""
    keys = set()
    for m in re.finditer(r"\*\*([^*]+)\*\*", text):
        for w in m.group(1).split(): keys.add(re.sub(r"\W", "", w.lower()))
    words = re.sub(r"[`*]", "", text).split()
    return [(w, re.sub(r"\W", "", w.lower()) in keys) for w in words]

NUMBER_WORDS = set("""zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen
sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand""".split())
def _is_number(w):
    parts = re.sub(r"[^a-z-]", "", w.lower()).split("-")
    return bool(parts[0]) and all(p in NUMBER_WORDS for p in parts)

def caption_groups(words, maxw=3, maxc=20):
    groups, cur = [], []
    for i, (w, k) in enumerate(words):
        spoken_number = cur and _is_number(words[cur[-1]][0]) and _is_number(w) and words[cur[-1]][0][-1:].isalnum()
        if cur and not spoken_number and (len(cur) >= maxw or len(" ".join(words[j][0] for j in cur + [i])) > maxc):
            groups.append(cur); cur = []
        cur.append(i)
        if w[-1:] in ".?!,:" and len(cur) >= 1:
            groups.append(cur); cur = []
    if cur: groups.append(cur)
    return groups
