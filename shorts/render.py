"""Render study shorts (vertical 720x1280 MP4 with narration and burned-in captions) from JSON scripts.

Usage (from the course folder; --root <folder> picks another course):
  python -I shorts/render.py tts    [ids...]   # narrate the lines (cached by voice, speed and text)
  python -I shorts/render.py sheet  <id>       # one still per narration line, to check the layout
  python -I shorts/render.py video  [ids...]   # narrate what is missing, then render the videos
  python -I shorts/render.py audio  [ids...]   # new sound for rendered videos (keeps the frames)
  python -I shorts/render.py frames <id> <t1> <t2> ...   # still frames at these seconds

Needs Python with pillow and numpy, ffmpeg on the PATH, and Kokoro (audio/requirements.txt) or a voice PC.
Settings come from course.json:
  "shorts":  {"engine": "kokoro-local" | "kokoro-ssh", "voice": "af_heart", "speed": 1.12,
              "background": "gameplay" | "drawn", "backgroundFile": "shorts/backgrounds/minecraft-parkour.mp4"}
  "voicePC": {"host": ..., "key": ..., "dir": ...}   (only for kokoro-ssh; see shorts/homepc/README.md)

course/shorts/scripts/<id>.json   one short per file (specs/SHORTS_SPEC.md); "bg": "gameplay" or "drawn" overrides
                                  the course's background for one short
.cache/tts/<key>.wav              narration clips; .cache/shorts/ holds frames, sheets and work files
site/shorts/<id>-<hash>.mp4 (narration + effects), <id>-<hash>.music.m4a (music bed, played in sync by the page),
<id>-<hash>.jpg, manifest.json. File names change with their content (see publish()), so the site can cache them.

Background: gameplay footage from backgroundFile (a video, or a folder of videos), dimmed under the text. Without
that file the short gets a drawn, animated background instead. Music: synthesized per short, or picked from audio
files you put in shorts/music/ (see the README files there). The kit ships no video or music.
"""
import hashlib, json, math, os, re, subprocess, sys, wave
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 720, 1280, 24
ROOT = None                                      # the course folder
TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import fx
import speech

COURSE, SAY = {}, None
ENGINE, KOKORO_SPEED, DEFAULT_VOICE = "kokoro-local", 1.12, "af_heart"
UNIT_CODES, BRAND, LANGUAGE = {}, "", "none"
DEFAULT_BG, GAMEPLAY_PATH = "gameplay", None
MUSIC_FILES = []


def setup(root):
    """Reads the course once per process (the render workers call it again)."""
    global ROOT, COURSE, SAY, ENGINE, KOKORO_SPEED, DEFAULT_VOICE, UNIT_CODES, BRAND, LANGUAGE, DEFAULT_BG, GAMEPLAY_PATH, MUSIC_FILES
    if ROOT == root and SAY is not None: return
    ROOT = root
    COURSE = speech.load_course(root)
    SAY = speech.Speech(root)
    cfg = COURSE.get("shorts") or {}
    ENGINE = cfg.get("engine") or (COURSE.get("audio") or {}).get("engine") or "kokoro-local"
    KOKORO_SPEED = float(cfg.get("speed", 1.12))
    DEFAULT_VOICE = cfg.get("voice") or (COURSE.get("audio") or {}).get("voice") or "af_heart"
    UNIT_CODES = {u["id"]: u.get("code") or u["id"].upper() for u in COURSE.get("units", [])}
    BRAND = ((COURSE.get("site") or {}).get("title") or "").upper()
    LANGUAGE = (COURSE.get("code") or {}).get("language", "none")
    DEFAULT_BG = cfg.get("background", "gameplay")
    GAMEPLAY_PATH = speech.resolve(root, cfg.get("backgroundFile") or "shorts/backgrounds/minecraft-parkour.mp4")
    md = os.path.join(root, "shorts", "music")
    MUSIC_FILES = sorted(os.path.join(md, f) for f in os.listdir(md) if f.lower().endswith(MUSIC_EXT)) if os.path.isdir(md) else []

# ---------- color schemes: one per narrator, so neighbouring shorts in the feed look different ----------
# PCB is each scheme's primary color (titles, chips), COPPER its accent (keywords, highlights, progress).
# Code boxes stay dark in every scheme so the syntax colors read the same everywhere.
THEMES = {
    "circuit": dict(music="techno", style="circuit",
        BG=(11, 19, 16), PANEL=(20, 32, 27), PANEL2=(28, 44, 37), INK=(230, 238, 233), INK2=(165, 181, 173), INK3=(104, 122, 113),
        LINE=(44, 64, 55), PCB=(150, 214, 184), COPPER=(234, 142, 84), COPPER_SOFT=(74, 46, 28), OK=(88, 204, 148), OK_SOFT=(22, 62, 42),
        BAD=(240, 120, 120), CODEBG=(7, 14, 11), CODEINK=(150, 214, 184), CODE_HL=(74, 46, 28), CODE_PLAIN=(230, 238, 233), TRACK=(36, 52, 45), GOLD=(242, 193, 78),
        bg=dict(dot=(24, 38, 32), trace=(25, 44, 37), pulse=(150, 214, 184), glow=(38, 74, 58))),
    "ember": dict(music="lofi", style="bokeh",
        BG=(26, 12, 20), PANEL=(44, 21, 33), PANEL2=(60, 29, 45), INK=(250, 236, 232), INK2=(208, 178, 180), INK3=(150, 114, 122),
        LINE=(80, 43, 60), PCB=(255, 190, 120), COPPER=(255, 96, 128), COPPER_SOFT=(88, 26, 45), OK=(120, 224, 160), OK_SOFT=(26, 68, 48),
        BAD=(255, 128, 128), CODEBG=(14, 6, 11), CODEINK=(255, 190, 120), CODE_HL=(88, 26, 45), CODE_PLAIN=(250, 236, 232), TRACK=(66, 35, 50), GOLD=(255, 214, 102),
        bg=dict(glows=[(255, 96, 128), (255, 170, 90), (190, 80, 200), (255, 120, 80)], spark=(255, 222, 186))),
    "paper": dict(music="pluck", style="paper",
        BG=(247, 242, 231), PANEL=(238, 231, 215), PANEL2=(227, 218, 198), INK=(32, 36, 50), INK2=(78, 84, 102), INK3=(134, 132, 138),
        LINE=(210, 200, 180), PCB=(28, 92, 150), COPPER=(214, 80, 44), COPPER_SOFT=(248, 214, 196), OK=(28, 138, 86), OK_SOFT=(206, 236, 218),
        BAD=(196, 56, 56), CODEBG=(36, 40, 54), CODEINK=(150, 214, 255), CODE_HL=(96, 44, 32), CODE_PLAIN=(232, 236, 244), TRACK=(222, 212, 192), GOLD=(232, 170, 40),
        bg=dict(grid=(234, 228, 214), grid2=(219, 210, 193), margin=(238, 176, 166), glyph=(212, 203, 186))),
    "neon": dict(music="synthwave", style="neon",
        BG=(8, 6, 22), PANEL=(20, 16, 44), PANEL2=(30, 24, 62), INK=(238, 236, 255), INK2=(174, 170, 216), INK3=(114, 108, 156),
        LINE=(54, 46, 100), PCB=(70, 228, 255), COPPER=(255, 70, 190), COPPER_SOFT=(74, 16, 58), OK=(90, 242, 170), OK_SOFT=(16, 62, 48),
        BAD=(255, 96, 120), CODEBG=(5, 4, 14), CODEINK=(70, 228, 255), CODE_HL=(74, 16, 58), CODE_PLAIN=(238, 236, 255), TRACK=(46, 38, 86), GOLD=(255, 226, 90),
        bg=dict(sky_top=(10, 6, 30), sky_low=(58, 16, 74), floor=(16, 8, 34), grid_hi=(255, 70, 190), grid_lo=(70, 228, 255))),
    "ocean": dict(music="ambient", style="ocean",
        BG=(4, 18, 30), PANEL=(10, 34, 50), PANEL2=(16, 46, 66), INK=(226, 242, 248), INK2=(156, 190, 204), INK3=(98, 130, 146),
        LINE=(28, 62, 84), PCB=(110, 222, 232), COPPER=(255, 198, 84), COPPER_SOFT=(72, 54, 18), OK=(100, 230, 160), OK_SOFT=(14, 60, 46),
        BAD=(255, 128, 118), CODEBG=(2, 10, 18), CODEINK=(110, 222, 232), CODE_HL=(72, 54, 18), CODE_PLAIN=(226, 242, 248), TRACK=(24, 56, 76), GOLD=(255, 232, 120),
        bg=dict(top=(12, 54, 76), wave=(110, 222, 232), bubble=(160, 230, 240))),
    "blueprint": dict(music="minimal", style="blueprint",
        BG=(16, 44, 80), PANEL=(24, 58, 100), PANEL2=(32, 72, 118), INK=(240, 246, 255), INK2=(186, 208, 234), INK3=(130, 158, 192),
        LINE=(58, 96, 142), PCB=(150, 214, 255), COPPER=(255, 196, 64), COPPER_SOFT=(80, 64, 24), OK=(110, 232, 160), OK_SOFT=(22, 76, 66),
        BAD=(255, 128, 118), CODEBG=(8, 24, 46), CODEINK=(150, 214, 255), CODE_HL=(80, 64, 24), CODE_PLAIN=(240, 246, 255), TRACK=(44, 82, 126), GOLD=(255, 226, 120),
        bg=dict(grid=(22, 52, 90), grid2=(34, 68, 110), ink=(72, 112, 162), sweep=(150, 214, 255))),
    # ---- second schemes: each narrator alternates between two looks ----
    "terminal": dict(music="chiptune", style="terminal",
        BG=(2, 10, 4), PANEL=(6, 24, 11), PANEL2=(10, 34, 17), INK=(190, 255, 200), INK2=(118, 204, 138), INK3=(66, 136, 86),
        LINE=(22, 64, 34), PCB=(120, 255, 150), COPPER=(255, 200, 60), COPPER_SOFT=(62, 48, 10), OK=(110, 236, 255), OK_SOFT=(10, 48, 58),
        BAD=(255, 96, 96), CODEBG=(0, 6, 2), CODEINK=(120, 255, 150), CODE_HL=(52, 52, 8), CODE_PLAIN=(196, 255, 206), TRACK=(16, 48, 24), GOLD=(255, 226, 96),
        bg=dict(rain=(30, 120, 60), head=(170, 255, 190), scan=(0, 0, 0)),
        fonts=dict(display=("consolab.ttf", None), display2=("consolab.ttf", None), body=("consola.ttf", None),
                   bodyb=("consolab.ttf", None), heavy=("consolab.ttf", None))),
    "sunset": dict(music="house", style="sunset",
        BG=(26, 10, 40), PANEL=(46, 18, 64), PANEL2=(62, 26, 84), INK=(255, 238, 246), INK2=(232, 184, 216), INK3=(164, 124, 174),
        LINE=(92, 46, 112), PCB=(255, 214, 102), COPPER=(255, 92, 160), COPPER_SOFT=(92, 20, 62), OK=(110, 240, 200), OK_SOFT=(20, 72, 66),
        BAD=(255, 112, 122), CODEBG=(14, 4, 24), CODEINK=(255, 214, 102), CODE_HL=(92, 24, 66), CODE_PLAIN=(255, 238, 246), TRACK=(72, 32, 92), GOLD=(255, 232, 120),
        bg=dict(sky_top=(22, 8, 44), sky_mid=(120, 30, 110), horizon=(255, 120, 90), sun_top=(255, 222, 120), sun_bot=(255, 70, 140),
                hill=(40, 12, 58), hill2=(64, 18, 80), water=(30, 10, 50)),
        fonts=dict(display=("ariblk.ttf", None), display2=("trebucbd.ttf", None), body=("trebuc.ttf", None),
                   bodyb=("trebucbd.ttf", None), heavy=("impact.ttf", None))),
    "chalkboard": dict(music="jazzhop", style="chalk",
        BG=(30, 54, 42), PANEL=(38, 66, 52), PANEL2=(46, 78, 62), INK=(242, 242, 234), INK2=(204, 214, 204), INK3=(146, 164, 154),
        LINE=(72, 102, 86), PCB=(255, 236, 150), COPPER=(255, 156, 176), COPPER_SOFT=(84, 62, 68), OK=(170, 236, 170), OK_SOFT=(42, 84, 58),
        BAD=(255, 144, 144), CODEBG=(14, 26, 20), CODEINK=(255, 236, 150), CODE_HL=(72, 72, 40), CODE_PLAIN=(236, 242, 232), TRACK=(52, 82, 66), GOLD=(255, 236, 150),
        bg=dict(speck=(44, 72, 58), smudge=(52, 80, 66), chalk=(86, 116, 100), dust=(170, 190, 178), frame=(92, 62, 38)),
        fonts=dict(display=("segoeprb.ttf", None), display2=("segoeprb.ttf", None), body=("Candara.ttf", None),
                   bodyb=("Candarab.ttf", None), heavy=("segoeprb.ttf", None))),
    "space": dict(music="cinematic", style="space",
        BG=(4, 4, 14), PANEL=(14, 14, 34), PANEL2=(22, 22, 48), INK=(236, 240, 255), INK2=(172, 182, 222), INK3=(112, 120, 162),
        LINE=(42, 46, 84), PCB=(150, 200, 255), COPPER=(255, 170, 80), COPPER_SOFT=(72, 46, 20), OK=(120, 240, 190), OK_SOFT=(16, 60, 48),
        BAD=(255, 112, 122), CODEBG=(2, 2, 8), CODEINK=(150, 200, 255), CODE_HL=(62, 44, 20), CODE_PLAIN=(236, 240, 255), TRACK=(30, 32, 66), GOLD=(255, 220, 120),
        bg=dict(nebula=[(90, 40, 160), (30, 90, 180), (180, 50, 120)], star=(220, 228, 255), planet=(70, 90, 150), ring=(150, 170, 220)),
        fonts=dict(display=("bahnschrift.ttf", [350, 100]), display2=("bahnschrift.ttf", [450, 100]), heavy=("bahnschrift.ttf", [700, 100]))),
    "aurora": dict(music="dnb", style="aurora",
        BG=(6, 14, 28), PANEL=(12, 26, 44), PANEL2=(18, 36, 58), INK=(232, 246, 250), INK2=(162, 198, 212), INK3=(102, 136, 152),
        LINE=(30, 60, 82), PCB=(120, 255, 200), COPPER=(222, 142, 255), COPPER_SOFT=(56, 30, 74), OK=(120, 255, 180), OK_SOFT=(16, 64, 48),
        BAD=(255, 122, 132), CODEBG=(2, 8, 16), CODEINK=(120, 255, 200), CODE_HL=(52, 30, 72), CODE_PLAIN=(232, 246, 250), TRACK=(24, 48, 68), GOLD=(255, 230, 130),
        bg=dict(sky_top=(4, 8, 22), sky_bot=(10, 26, 44), bands=[(80, 255, 170), (120, 200, 255), (200, 120, 255)], hill=(4, 10, 18), star=(210, 230, 255)),
        fonts=dict(display=("georgiab.ttf", None), display2=("georgiab.ttf", None), body=("corbel.ttf", None),
                   bodyb=("corbelb.ttf", None), heavy=("georgiab.ttf", None))),
    "pop": dict(music="trap", style="pop",
        BG=(252, 226, 64), PANEL=(255, 242, 150), PANEL2=(242, 214, 70), INK=(22, 22, 22), INK2=(58, 58, 50), INK3=(110, 104, 70),
        LINE=(40, 36, 20), PCB=(30, 30, 30), COPPER=(226, 34, 92), COPPER_SOFT=(255, 200, 214), OK=(0, 136, 88), OK_SOFT=(198, 240, 206),
        BAD=(196, 26, 26), CODEBG=(24, 24, 24), CODEINK=(255, 228, 80), CODE_HL=(112, 20, 52), CODE_PLAIN=(242, 242, 242), TRACK=(226, 200, 56), GOLD=(255, 255, 255),
        bg=dict(dots=(236, 204, 40), stripe=(242, 196, 30), shape=(30, 30, 30), shape2=(226, 34, 92)),
        fonts=dict(display=("impact.ttf", None), display2=("FRADM.TTF", None), body=("calibri.ttf", None),
                   bodyb=("calibrib.ttf", None), heavy=("impact.ttf", None))),
}
# each narrator has two looks; a script picks the second with "theme", otherwise it gets the first
VOICE_SCHEMES = {"am_michael": ("circuit", "terminal"), "af_heart": ("ember", "sunset"), "bf_emma": ("paper", "chalkboard"),
                 "am_fenrir": ("neon", "space"), "af_bella": ("ocean", "aurora"), "am_puck": ("blueprint", "pop")}
THEME_BY_VOICE = {v: pair[0] for v, pair in VOICE_SCHEMES.items()}
LIGHT_THEMES = ("paper", "pop")
PALETTE_KEYS = ("BG", "PANEL", "PANEL2", "INK", "INK2", "INK3", "LINE", "PCB", "COPPER", "COPPER_SOFT", "OK", "OK_SOFT",
                "BAD", "CODEBG", "CODEINK", "CODE_HL", "CODE_PLAIN", "TRACK", "GOLD")
CAP_INK = (255, 255, 255)                       # captions stay white with a black outline in every scheme
THEME = None
BG_STYLE, BG_PARAMS = "circuit", {}
MUSIC_STYLE = "techno"


def music_seed(short):
    """Each short gets its own key, chords and patterns inside its scheme's music style."""
    return int(hashlib.sha1(short["id"].encode("utf-8")).hexdigest()[:8], 16)


def apply_theme(name):
    """Switch every palette color (and the background style) to the named scheme."""
    global THEME, BG_STYLE, BG_PARAMS, CONFETTI
    th = THEMES[name]; THEME = name
    g = globals()
    for k in PALETTE_KEYS:
        g[k] = th[k]
    BG_STYLE = th["style"]
    g["MUSIC_STYLE"] = th["music"]
    BG_PARAMS = dict(th["bg"], BG=th["BG"])
    g["FONT_SET"] = dict(FONT_DEFAULT, **th.get("fonts", {}))
    CONFETTI = [th["COPPER"], th["PCB"], th["OK"], th["GOLD"], th["INK"] if name != "paper" else (255, 255, 255)]


def theme_of(short):
    """A script may name its scheme; otherwise the narrator decides. Over gameplay footage only dark schemes are used."""
    v = voice_of(short)
    name = short.get("theme") or THEME_BY_VOICE.get(v, "circuit")
    if is_gameplay(short) and name in LIGHT_THEMES:
        pair = VOICE_SCHEMES.get(v, ())
        name = next((x for x in pair if x not in LIGHT_THEMES), "circuit")
    return name


CODE = dict(kw=(240, 164, 110), cu=(242, 193, 78), bi=(143, 211, 176), api=(156, 196, 240), nm=(231, 154, 154), st=(198, 217, 138), c=(127, 154, 140), pp=(240, 164, 110))

# The schemes use Windows fonts. On a Mac or Linux the closest common font is used instead (FONT_FALLBACK).
FONT_DIRS = [os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"), os.path.expanduser("~/Library/Fonts"),
             "/Library/Fonts", "/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "/usr/share/fonts",
             "/usr/local/share/fonts", os.path.expanduser("~/.local/share/fonts"), os.path.expanduser("~/.fonts")]
# kind -> (file, variation): a list sets variable-font axes (Bahnschrift: weight, width), a string names an instance
FONT_DEFAULT = {"display": ("bahnschrift.ttf", [700, 75]), "display2": ("bahnschrift.ttf", [600, 100]),
                "body": ("segoeui.ttf", None), "bodyb": ("seguisb.ttf", None), "heavy": ("seguibl.ttf", None),
                "mono": ("CascadiaMono.ttf", "Regular"), "monob": ("CascadiaMono.ttf", "Bold")}
FONT_FALLBACK = {"display": ["Arial Bold.ttf", "DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
                 "display2": ["Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
                 "body": ["Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"],
                 "bodyb": ["Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
                 "heavy": ["Arial Black.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
                 "mono": ["consola.ttf", "Menlo.ttc", "Courier New.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"],
                 "monob": ["consolab.ttf", "Menlo.ttc", "Courier New Bold.ttf", "DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf"]}
FONT_SET = dict(FONT_DEFAULT)                   # the current scheme's fonts (apply_theme)
_fc, _found = {}, {}


def find_font(name):
    """Full path of a font file in the usual font folders (searched once per name), or None."""
    if name not in _found:
        _found[name] = None
        low = name.lower()
        for d in FONT_DIRS:
            if not os.path.isdir(d): continue
            p = os.path.join(d, name)
            if os.path.exists(p): _found[name] = p; break
            for dp, _, files in os.walk(d):
                hit = next((f for f in files if f.lower() == low), None)
                if hit: _found[name] = os.path.join(dp, hit); break
            if _found[name]: break
    return _found[name]


def font(kind, size):
    if kind not in FONT_DEFAULT: raise ValueError(kind)
    spec = FONT_SET.get(kind, FONT_DEFAULT[kind])
    key = (spec[0], str(spec[1]), size)
    if key in _fc: return _fc[key]
    path = find_font(spec[0])
    if path:
        f = ImageFont.truetype(path, size)
        try:
            if isinstance(spec[1], list): f.set_variation_by_axes(spec[1])
            elif isinstance(spec[1], str): f.set_variation_by_name(spec[1])
        except Exception:
            pass
    else:
        alt = next((p for p in map(find_font, FONT_FALLBACK[kind]) if p), None)
        f = ImageFont.truetype(alt, size) if alt else ImageFont.load_default(size)
    _fc[key] = f
    return f

def ease(x):
    x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3
def lerp(c1, c2, a):
    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * a)) for i in range(3))
def fade(c, a, base=None):
    return lerp(BG if base is None else base, c, max(0.0, min(1.0, a)))

# ---------- speech (rules and engines live in speech.py) ----------
spoken_words = speech.spoken_words
MARKUP = speech.MARKUP


def speakable(s, voice=None):
    """The text the narrator reads, with the course's pronunciations (see speech.py)."""
    return SAY.speakable(s, voice or DEFAULT_VOICE)


def clip_path(voice, spoken):
    return os.path.join(ROOT, ".cache", "tts", speech.clip_key(voice, KOKORO_SPEED, spoken) + ".wav")


# ---------- scripts ----------
def scripts_dir():
    return os.path.join(ROOT, "course", "shorts", "scripts")


def load_scripts(ids=None):
    d = scripts_dir()
    if not os.path.isdir(d): raise SystemExit("no shorts yet: course/shorts/scripts/ does not exist")
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"): continue
        with open(os.path.join(d, f), encoding="utf-8") as fh:
            s = json.load(fh)
        if ids and s["id"] not in ids: continue
        out.append(s)
    if ids:
        missing = set(ids) - {s["id"] for s in out}
        if missing: raise SystemExit("no script for: " + ", ".join(sorted(missing)))
    return out

def says(scene):
    s = scene.get("say", [])
    return [s] if isinstance(s, str) else list(s)

def voice_of(script):
    return script.get("voice") or DEFAULT_VOICE

def run_tts(scripts):
    jobs, seen, spelled = [], set(), set()
    for sc in scripts:
        v = voice_of(sc)
        for scene in sc["scenes"]:
            for line in says(scene):
                spelled.update(SAY.spelled_out(line))
                spoken = speakable(line, v)
                key = os.path.splitext(os.path.basename(clip_path(v, spoken)))[0]
                if key in seen: continue
                seen.add(key); jobs.append({"key": key, "text": spoken, "voice": v, "speed": KOKORO_SPEED})
    if spelled:
        print("read letter by letter:", ", ".join(sorted(spelled)), "(add any said as a word to course/pronunciations.json)")
    speech.synthesize(ROOT, jobs, ENGINE, COURSE.get("voicePC"))

def wav_len(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / w.getframerate()

# ---------- timeline ----------
GAP = 0.12        # silence between lines
LEAD = 0.14       # a scene appears this long before its first line
def timeline(script):
    """Returns scenes with absolute timings: each scene gets start, end, its segments [(start,end,text,clip)]
    and its visible window vs..ve."""
    v = voice_of(script)
    t = 0.15
    out = []
    for scene in script["scenes"]:
        segs = []
        s0 = t
        for line in says(scene):
            p = clip_path(v, speakable(line, v))
            full = wav_len(p); a, b = 0.0, full
            words = []
            mj = p[:-4] + ".json"
            if os.path.exists(mj):
                words = json.load(open(mj, encoding="utf-8")).get("words") or []
            if words:      # cut the silence the voice leaves before the first and after the last word
                a = max(0.0, words[0]["s"] - 0.04); b = min(full, words[-1]["e"] + 0.1)
            d = b - a
            sg = {"start": t, "end": t + d, "text": line, "clip": p, "trim": (a, b), "words": words, "voice": v}
            segs.append(sg)
            t += d + GAP
        if scene.get("type") == "quiz":
            think = float(scene.get("think", 2))
            # the think pause sits after the first line (the question), before the reveal line(s)
            if segs:
                shift = think
                for sg in segs[1:]:
                    sg["start"] += shift; sg["end"] += shift
                scene = dict(scene, _think=(segs[0]["end"] + 0.15, segs[0]["end"] + 0.15 + think))
                t += think
        t += float(scene.get("hold", 0.12))
        out.append({"scene": scene, "start": s0, "end": t, "segs": segs})
    total = t + 0.5
    for sc in out:
        sc["vs"] = max(0.0, sc["start"] - LEAD)
    for i, sc in enumerate(out):
        sc["ve"] = out[i + 1]["vs"] if i + 1 < len(out) else total
    return out, total

REVEALS = {"bullets": "items", "formula": "lines", "compare": "rows"}
def cues(tl):
    """Sound effects, zoom punches and confetti bursts, all derived from the timeline."""
    snd, punch, burst = [], [], []
    for i, sc in enumerate(tl):
        s = sc["scene"]; typ = s["type"]
        if i == 0:
            snd.append((0.0, "stinger")); punch.append((sc["vs"] + 0.08, 0.06))
        else:
            snd.append((max(0.0, sc["vs"] - 0.1), "whoosh"))
        for j, sg in enumerate(sc["segs"]):
            if j == 0: continue
            at = sg["start"] - 0.05
            if typ == "quiz":
                if j == 1:
                    snd.append((at, "ding")); punch.append((at, 0.08)); burst.append(at)
                else:
                    snd.append((at, "pop")); punch.append((at, 0.03))
            elif typ in REVEALS:
                off = int(s.get("offset", 0)); n = len(s.get(REVEALS[typ], []))
                if off <= j < off + n:
                    snd.append((at, "pop")); punch.append((at, 0.035))
            elif typ in ("code", "cells", "tree"):
                snd.append((at, "pop")); punch.append((at, 0.03))
            else:                                   # hooks and cards: a softer beat on each new line
                snd.append((at, "tick")); punch.append((at, 0.02))
        th = s.get("_think")
        if th:
            for k in range(int(round(th[1] - th[0]))):
                snd.append((th[0] + k, "tick"))
    return snd, punch, burst

def build_audio(tl, total, dst, dst_music, events, seed=0):
    """Two wav files at one shared gain: narration + sound effects (dst) and the music bed (dst_music)."""
    rate, voice = None, []
    for sc in tl:
        for sg in sc["segs"]:
            with wave.open(sg["clip"], "rb") as w:
                assert w.getsampwidth() == 2 and w.getnchannels() == 1
                rate = rate or w.getframerate()
                assert w.getframerate() == rate
                a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
            lo, hi = sg.get("trim", (0, len(a) / rate))
            a = a[int(lo * rate):int(hi * rate)].copy()
            r = min(len(a) // 2, int(0.006 * rate))          # tiny fades so the cuts never click
            if r: a[:r] *= np.linspace(0, 1, r); a[-r:] *= np.linspace(1, 0, r)
            voice.append((sg["start"], a))
    rate = rate or 24000
    fg, bed = fx.mix(voice, events, total, rate, MUSIC_STYLE, seed, music_from_file(total, rate, seed))
    for path, pcm in ((dst, fg), (dst_music, bed)):
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())


MUSIC_EXT = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".opus", ".flac")


def music_from_file(total, rate, seed):
    """A stretch of one of the tracks in shorts/music/ (picked per short), at the synthesized music's loudness.
    None when the folder is empty, so the scheme's synthesized music plays instead."""
    if not MUSIC_FILES: return None
    path = MUSIC_FILES[seed % len(MUSIC_FILES)]
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"], capture_output=True)
    y = np.frombuffer(r.stdout, np.float32)
    if r.returncode != 0 or len(y) < rate:
        print("could not read music file", os.path.basename(path), "- using synthesized music", flush=True); return None
    n = int(total * rate) + 1
    start = (seed // 7) % (len(y) - n) if len(y) > n else 0
    y = np.tile(y, n // len(y) + 2)[start:start + n].copy()
    level = float(np.sqrt(np.mean(y ** 2))) or 1.0
    return (y * (0.22 / level)).astype(np.float32)


AUDIO_ARGS = ["-af", "alimiter=limit=0.7:level=false", "-c:a", "aac", "-b:a", "64k", "-ar", "44100"]


def encode_music(wav, dst):
    """The music bed as a small AAC file the page plays in sync with the video (so it can be muted on its own)."""
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af", "alimiter=limit=0.89:level=false",
                        "-c:a", "aac", "-b:a", "48k", "-ar", "44100", "-ac", "1", "-movflags", "+faststart", dst])
    if r.returncode != 0: raise RuntimeError("ffmpeg failed for " + dst)

# ---------- rich text ----------
def tokens(text):
    """`code`, **bold** -> list of (word, style, glue); glue = no space before the word."""
    out = []
    prev_ws = True
    for m in re.finditer(r"`([^`]+)`|\*\*([^*]+)\*\*|([^`*]+)|(\*)", text):
        if m.group(1) is not None or m.group(2) is not None:
            st = "code" if m.group(1) is not None else "bold"
            words = [w for w in (m.group(1) if st == "code" else m.group(2)).split(" ") if w]
            for i, w in enumerate(words):
                out.append((w, st, i == 0 and not prev_ws and bool(out)))
            prev_ws = False
        else:
            seg = m.group(3) or m.group(4) or ""
            words = seg.split()
            for i, w in enumerate(words):
                out.append((w, "n", i == 0 and not seg[:1].isspace() and not prev_ws and bool(out)))
            prev_ws = seg[-1:].isspace() if seg else prev_ws
    return out

def style_font(style, size, base="body"):
    if style == "code": return font("mono", int(size * 0.92))
    if style == "bold": return font(base if base.startswith("display") else "bodyb", size)
    return font(base, size)

def layout(text, size, maxw, base="body", lh=1.32):
    toks = tokens(text)
    lines, cur, x = [], [], 0
    space = font(base, size).getlength(" ")
    for w, st, glue in toks:
        f = style_font(st, size, base)
        wl = f.getlength(w) + (10 if st == "code" else 0)
        if glue and cur:
            x -= space
        if cur and x + wl > maxw and not glue:
            lines.append(cur); cur, x = [], 0
        cur.append((x, w, st, wl)); x += wl + space
    if cur: lines.append(cur)
    return lines, int(size * lh)

def text_h(text, size, maxw, base="body", lh=1.32):
    lines, step = layout(text, size, maxw, base, lh)
    return len(lines) * step

def draw_rich(d, text, x0, y0, size, maxw, color=None, alpha=1.0, base="body", align="left", lh=1.32, panel=None, anim=None):
    """anim=(t, t0, step): words drop in one after another, word j starting at t0 + j*step."""
    color = INK if color is None else color; panel = BG if panel is None else panel
    lines, step = layout(text, size, maxw, base, lh)
    y = y0; j = 0
    def word_anim():
        if not anim: return alpha, 0
        t, t0, st = anim; k = (t - t0 - j * st)
        return alpha * max(0.0, min(1.0, k / 0.1)), int(-34 * (1 - fx.ease_out_back(k / 0.26)))
    for ln in lines:
        width = (ln[-1][0] + ln[-1][3]) if ln else 0
        dx = x0 + (maxw - width) / 2 if align == "center" else x0
        j0 = j
        # one background pill per run of consecutive code words on this line
        run = None
        for (x, w, st, wl) in ln + [(None, None, None, None)]:
            if st == "code":
                if not run:
                    a, oy = word_anim()
                run = (run[0], x + wl, run[2], run[3]) if run else (x, x + wl, a, oy)
            elif run:
                d.rounded_rectangle((dx + run[0], y + run[3] + size * 0.08, dx + run[1], y + run[3] + size * 1.22), radius=6, fill=fade(CODEBG, run[2], panel))
                run = None
            if w is not None: j += 1
        j = j0
        for (x, w, st, wl) in ln:
            f = style_font(st, size, base)
            a, oy = word_anim(); j += 1
            if a <= 0: continue
            if st == "code":
                d.text((dx + x + 5, y + oy + size * 0.16), w, font=f, fill=fade(CODEINK, a, panel))
            else:
                d.text((dx + x, y + oy), w, font=f, fill=fade(COPPER if st == "bold" else color, a, panel))
        y += step
    return y

def fit_size(text, maxw, maxh, start, minimum=22, base="body", lh=1.32):
    s = start
    while s > minimum and text_h(text, s, maxw, base, lh) > maxh:
        s -= 2
    return s

# ---------- code highlighting (course.json "code.language") ----------
KW = set(("int float double char void unsigned long short const return if else for while do break continue struct sizeof "
          "bool true false size_t typedef static switch case default class public private protected new delete this "
          "def import from as in is not and or None True False lambda with try except finally raise pass yield elif "
          "function var let const null undefined boolean String final extends implements interface throws "
          "SELECT FROM WHERE JOIN ON GROUP BY ORDER HAVING INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE AS AND OR NOT NULL").split())
EXTRA = {"cuda": (set("__global__ __device__ __host__ __shared__ __constant__ __syncthreads".split()),
                  set("threadIdx blockIdx blockDim gridDim warpSize dim3".split()), "cuda")}
COMMENT = {"python": r"#.*$", "sql": r"--.*$"}
def code_spans(line):
    qual, builtin, api = EXTRA.get(LANGUAGE, (set(), set(), None))
    cm = COMMENT.get(LANGUAGE, r"//.*$")
    out, last = [], 0
    for m in re.finditer(r"(" + cm + r")|(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|(^\s*#\s*\w+)|(<<<|>>>)|(\b\d+(?:\.\d+)?[fFuUlL]*\b)|([A-Za-z_]\w*)", line):
        if m.start() > last: out.append((line[last:m.start()], CODE_PLAIN))
        t = m.group(0)
        if m.group(1): c = CODE["c"]
        elif m.group(2): c = CODE["st"]
        elif m.group(3): c = CODE["pp"]
        elif m.group(4): c = CODE["cu"]
        elif m.group(5): c = CODE["nm"]
        else:
            c = (CODE["cu"] if t in qual else CODE["bi"] if t in builtin else CODE["kw"] if t in KW
                 else CODE["api"] if api and t.startswith(api) else CODE_PLAIN)
        out.append((t, c)); last = m.end()
    if last < len(line): out.append((line[last:], CODE_PLAIN))
    return out

# ---------- scene renderers ----------
STAGE = (40, 150, 640, 975)
WARN = []
def overflow(where, y):
    if y > STAGE[3] + 4: WARN.append(f"{where} content reaches y={int(y)} (stage ends at {STAGE[3]})")   # x0, y0, x1, y1 (right 80 px kept clear for the feed's buttons)
def stage_w(): return STAGE[2] - STAGE[0]

def seg_index(sc, t):
    """Index of the segment that has started most recently (-1 before the first)."""
    k = -1
    for i, sg in enumerate(sc["segs"]):
        if t >= sg["start"] - 0.05: k = i
    return k

def appear(t, t0, dur=0.35):
    return ease((t - t0) / dur)

def fit_font(kind, text, size, maxw, minimum=22):
    """The largest size (up to `size`) at which one line of text fits in maxw; wide fonts shrink, narrow ones don't."""
    while size > minimum and font(kind, size).getlength(text) > maxw:
        size -= 2
    if font(kind, size).getlength(text) > maxw + 2: WARN.append(f"'{text}' is wider than {int(maxw)} px")
    return font(kind, size)

def scene_title(d, scene, a, y):
    if scene.get("title"):
        txt = scene["title"].upper()
        d.text((STAGE[0], y), txt, font=fit_font("display", txt, 46, stage_w()), fill=fade(PCB, a))
        return y + 64
    return y

def r_hook(d, sc, t, short):
    s = sc["scene"]; a = appear(t, sc["start"] - 0.2, 0.3)
    size = fit_size(s["text"], stage_w(), 470, 96, 44, base="display", lh=1.05)
    block = (80 if s.get("kicker") else 0) + text_h(s["text"], size, stage_w(), "display", 1.05) + (30 + text_h(s["sub"], 34, stage_w()) if s.get("sub") else 0)
    y = max(STAGE[1] + 40, (STAGE[1] + STAGE[3]) // 2 - 40 - block // 2)       # centred, a little above the middle
    if s.get("kicker"):
        f = font("monob", 26)
        txt = s["kicker"].upper()
        wl = f.getlength(txt) + 28
        d.rounded_rectangle((STAGE[0], y, STAGE[0] + wl, y + 46), radius=23, fill=fade(COPPER, a))
        d.text((STAGE[0] + 14, y + 8), txt, font=f, fill=fade(BG, a, COPPER))
        y += 80
    y = draw_rich(d, s["text"], STAGE[0], y, size, stage_w(), INK, 1.0, base="display", lh=1.05, anim=(t, sc["vs"] + 0.04, 0.07))
    if s.get("sub"):
        a2 = appear(t, sc["start"] + 0.5, 0.3)
        draw_rich(d, s["sub"], STAGE[0], y + 30, 34, stage_w(), INK2, a2)

def r_bullets(d, sc, t, short):
    s = sc["scene"]; k = seg_index(sc, t)
    y = scene_title(d, s, appear(t, sc["start"] - 0.2), STAGE[1] + 10)
    items = s["items"]; offset = int(s.get("offset", 0))  # first `offset` segments narrate without revealing items
    size = 46
    while size > 24 and sum(text_h(it, size, stage_w() - 50) + 26 for it in items) > STAGE[3] - y:
        size -= 2
    for i, it in enumerate(items):
        seg = i + offset
        if seg > k: break
        t0 = sc["segs"][seg]["start"] if seg < len(sc["segs"]) else sc["start"]
        a = appear(t, t0 - 0.1)
        cur = (seg == k)
        dy = int(18 * (1 - a))
        d.ellipse((STAGE[0], y + size * 0.4 + dy, STAGE[0] + 16, y + size * 0.4 + 16 + dy), fill=fade(COPPER if cur else PCB, a))
        y = draw_rich(d, it, STAGE[0] + 34, y + dy, size, stage_w() - 50, INK if cur else INK2, a) + 26
    overflow('bullets', y - 26)

def r_formula(d, sc, t, short):
    s = sc["scene"]; k = seg_index(sc, t)
    y = scene_title(d, s, appear(t, sc["start"] - 0.2), STAGE[1] + 10)
    if s.get("given"):
        a = appear(t, sc["start"] - 0.2)
        gh = text_h(s["given"], 34, stage_w() - 40) + 30
        d.rounded_rectangle((STAGE[0], y, STAGE[2], y + gh), radius=14, fill=fade(PANEL, a))
        draw_rich(d, s["given"], STAGE[0] + 20, y + 14, 34, stage_w() - 40, INK2, a, panel=PANEL)
        y += gh + 30
    lines = s["lines"]; offset = int(s.get("offset", 0))
    for i, ln in enumerate(lines):
        seg = i + offset
        if seg > k: break
        t0 = sc["segs"][seg]["start"] if seg < len(sc["segs"]) else sc["start"]
        a = appear(t, t0 - 0.1)
        last = (i == len(lines) - 1) and s.get("box", True)
        size = fit_size(ln, stage_w() - 40, 200, 56, 26, base="display2", lh=1.15)
        while size > 32 and len(layout(ln, size, stage_w() - 40, "display2", 1.15)[0]) > 2: size -= 2     # long code: two lines at most
        h = text_h(ln, size, stage_w() - 40, base="display2", lh=1.15)
        if last:
            d.rounded_rectangle((STAGE[0], y - 8, STAGE[2], y + h + 18), radius=14, fill=fade(COPPER_SOFT, a), outline=fade(COPPER, a), width=3)
            draw_rich(d, ln, STAGE[0] + 20, y + 4, size, stage_w() - 40, INK, a, base="display2", lh=1.15, panel=COPPER_SOFT)
        else:
            draw_rich(d, ln, STAGE[0] + 20, y + int(14 * (1 - a)), size, stage_w() - 40, INK if seg == k else INK2, a, base="display2", lh=1.15)
        y += h + 34
    overflow('formula', y - 34)

def r_code(d, sc, t, short):
    s = sc["scene"]; k = max(0, seg_index(sc, t))
    y = scene_title(d, s, appear(t, sc["start"] - 0.2), STAGE[1] + 10)
    lines = s["code"].replace("\t", "    ").split("\n")
    maxc = max(len(l) for l in lines) or 1
    size = int(min(30, (stage_w() - 40) / (maxc * 0.6)))
    size = max(size, 16)
    lh = int(size * 1.5)
    show = s.get("show"); hl = s.get("hl")
    n_show = len(lines) if not show else show[min(k, len(show) - 1)]
    hls = set(hl[min(k, len(hl) - 1)]) if hl else set()
    box_h = lh * len(lines) + 36
    a0 = appear(t, sc["start"] - 0.2)
    d.rounded_rectangle((STAGE[0], y, STAGE[2], y + box_h), radius=16, fill=fade(CODEBG, a0))
    f = font("mono", size)
    for i, ln in enumerate(lines):
        if i >= n_show: break
        yy = y + 18 + i * lh
        if (i + 1) in hls:
            d.rectangle((STAGE[0] + 6, yy - 4, STAGE[2] - 6, yy + lh - 6), fill=CODE_HL)
            d.rectangle((STAGE[0] + 6, yy - 4, STAGE[0] + 11, yy + lh - 6), fill=COPPER)
        x = STAGE[0] + 22
        for txt, col in code_spans(ln):
            d.text((x, yy), txt, font=f, fill=col)
            x += f.getlength(txt)
    y += box_h + 26
    overflow('code box', y - 26)
    notes = s.get("notes")
    if notes:
        nt = notes[min(k, len(notes) - 1)]
        if nt:
            a = appear(t, sc["segs"][k]["start"] - 0.1 if sc["segs"] else sc["start"])
            overflow('code notes', draw_rich(d, nt, STAGE[0], y, fit_size(nt, stage_w(), STAGE[3] - y, 40, 26), stage_w(), INK, a))

def r_cells(d, sc, t, short):
    s = sc["scene"]; k = max(0, seg_index(sc, t))
    y = scene_title(d, s, appear(t, sc["start"] - 0.2), STAGE[1] + 10)
    c = s["cells"]; cols = int(c.get("cols", 1)); blocks = c["blocks"]
    hl_seq = s.get("hl") or [c.get("hl", [])]
    hls = set(map(str, hl_seq[min(k, len(hl_seq) - 1)] or []))
    gap = 14
    ncol = max(len(r) for b in blocks for r in b["rows"])
    nrow_blocks = math.ceil(len(blocks) / cols)
    bw = (stage_w() - gap * (cols - 1)) / cols
    cw = (bw - 12) / ncol
    rows_per = max(len(b["rows"]) for b in blocks)
    ch = min(58, cw * 0.8 if cw < 70 else 52)
    labels = [str(v) for b in blocks for r in b["rows"] for v in r]
    longest = max((len(v) for v in labels), default=1)
    fs = int(max(12, min(28, cw / max(2.2, longest * 0.62))))
    fcell = font("mono", fs); flab = font("monob", 20)
    bh = 34 + rows_per * ch + 10
    a = appear(t, sc["start"] - 0.2)
    for bi, b in enumerate(blocks):
        bx = STAGE[0] + (bi % cols) * (bw + gap)
        by = y + (bi // cols) * (bh + gap)
        d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=10, outline=fade(INK3, a), width=2, fill=fade(PANEL, a))
        d.text((bx + 8, by + 6), b.get("label", ""), font=flab, fill=fade(INK2, a, PANEL))
        for ri, r in enumerate(b["rows"]):
            for ci, v in enumerate(r):
                x0 = bx + 6 + ci * cw; y0 = by + 34 + ri * ch
                on = str(v) in hls and str(v) != ""
                d.rectangle((x0, y0, x0 + cw - 3, y0 + ch - 3), fill=fade(COPPER if on else BG, a, PANEL), outline=fade(LINE, a, PANEL))
                if str(v):
                    tw = fcell.getlength(str(v))
                    d.text((x0 + (cw - 3 - tw) / 2, y0 + (ch - 3 - fs * 1.25) / 2), str(v), font=fcell, fill=fade(BG if on else INK, a, PANEL))
    y += nrow_blocks * (bh + gap) + 14
    overflow('cells grid', y)
    if c.get("caption"):
        y = draw_rich(d, c["caption"], STAGE[0], y, 26, stage_w(), INK3, a) + 10
    notes = s.get("notes")
    if notes:
        nt = notes[min(k, len(notes) - 1)]
        if nt:
            a2 = appear(t, sc["segs"][k]["start"] - 0.1 if sc["segs"] else sc["start"])
            size = fit_size(nt, stage_w(), STAGE[3] - y, 42, 22, base="display2", lh=1.2)
            overflow('cells notes', draw_rich(d, nt, STAGE[0], y + 6, size, stage_w(), INK, a2, base="display2", lh=1.2))

def tree_layout(node, depth=0, pos=None, acc=None):
    if acc is None: acc = []
    if pos is None: pos = [0]
    if isinstance(node, list):
        op, l, r = node
        L = tree_layout(l, depth + 1, pos, acc)
        R = tree_layout(r, depth + 1, pos, acc)
        me = {"label": op, "x": (L["x"] + R["x"]) / 2, "depth": depth, "kids": [L, R]}
    else:
        me = {"label": node, "x": pos[0], "depth": depth, "kids": []}
        pos[0] += 1
    acc.append(me)
    return me

def r_tree(d, sc, t, short):
    s = sc["scene"]; k = seg_index(sc, t)
    y = scene_title(d, s, appear(t, sc["start"] - 0.2), STAGE[1] + 10)
    nodes = []
    root = tree_layout(s["tree"], acc=nodes)
    maxd = max(n["depth"] for n in nodes); nleaf = max(n["x"] for n in nodes) + 1
    r = 34
    xs = lambda x: STAGE[0] + r + 6 + x * (stage_w() - 2 * r - 12) / max(1, nleaf - 1)
    ys = lambda dd: y + 40 + dd * min(130, (STAGE[3] - y - 200) / max(1, maxd))
    steps = s.get("steps")  # per segment: depth being evaluated, or null
    active = None
    if steps and k >= 0:
        active = steps[min(k, len(steps) - 1)]
    a = appear(t, sc["start"] - 0.2)
    for n in nodes:
        for kid in n["kids"]:
            d.line((xs(n["x"]), ys(n["depth"]), xs(kid["x"]), ys(kid["depth"])), fill=fade(INK3, a), width=4)
    done_depth = None
    if active is not None: done_depth = active
    for n in nodes:
        is_op = bool(n["kids"])
        cx, cy = xs(n["x"]), ys(n["depth"])
        fill, ink = PANEL2, INK
        if is_op and done_depth is not None and n["depth"] > done_depth: fill, ink = OK_SOFT, OK
        if is_op and done_depth is not None and n["depth"] == done_depth: fill, ink = COPPER, BG
        if not is_op: fill, ink = PANEL, PCB
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fade(fill, a), outline=fade(ink if is_op else LINE, a), width=3)
        f = font("heavy", 44) if is_op else font("display", 36)
        tw = f.getlength(n["label"])
        bb = f.getbbox(n["label"])
        d.text((cx - tw / 2, cy - (bb[1] + bb[3]) / 2), n["label"], font=f, fill=fade(ink, a))
    notes = s.get("notes")
    if notes and k >= 0:
        nt = notes[min(k, len(notes) - 1)]
        if nt:
            a2 = appear(t, sc["segs"][k]["start"] - 0.1)
            yy = ys(maxd) + r + 40
            overflow('tree notes', draw_rich(d, nt, STAGE[0], yy, 40, stage_w(), INK, a2, base="display2", lh=1.2))

def r_quiz(d, sc, t, short):
    s = sc["scene"]; k = seg_index(sc, t)
    a = appear(t, sc["start"] - 0.2)
    y = STAGE[1] + 10
    f = font("monob", 24); kick = "QUICK QUESTION"
    d.rounded_rectangle((STAGE[0], y, STAGE[0] + f.getlength(kick) + 28, y + 42), radius=21, fill=fade(COPPER, a))
    d.text((STAGE[0] + 14, y + 7), kick, font=f, fill=fade(BG, a, COPPER))
    y += 66
    size = fit_size(s["q"], stage_w(), 260, 48, 26, base="bodyb", lh=1.25)
    y = draw_rich(d, s["q"], STAGE[0], y, size, stage_w(), INK, a, base="bodyb", lh=1.25) + 10
    if s.get("code"):
        lines = s["code"].split("\n"); maxc = max(len(l) for l in lines)
        cs = int(max(16, min(26, (stage_w() - 40) / (maxc * 0.6)))); lh = int(cs * 1.45)
        bh = lh * len(lines) + 28
        d.rounded_rectangle((STAGE[0], y, STAGE[2], y + bh), radius=14, fill=fade(CODEBG, a))
        fm = font("mono", cs)
        for i, ln in enumerate(lines):
            x = STAGE[0] + 18
            for txt, col in code_spans(ln):
                d.text((x, y + 14 + i * lh), txt, font=fm, fill=fade(col, a, CODEBG)); x += fm.getlength(txt)
        y += bh + 16
    revealed = k >= 1
    th = s.get("_think")
    for i, op in enumerate(s["options"]):
        osz = 36 if text_h(op, 36, stage_w() - 90) <= 50 else 30
        oh = text_h(op, osz, stage_w() - 90) + 28
        ok = revealed and i == s["answer"]
        dim = revealed and not ok
        fill = OK_SOFT if ok else PANEL
        d.rounded_rectangle((STAGE[0], y, STAGE[2], y + oh), radius=14, fill=fade(fill, a), outline=fade(OK if ok else LINE, a), width=3 if ok else 2)
        d.rounded_rectangle((STAGE[0] + 12, y + 12, STAGE[0] + 56, y + 56), radius=10, fill=fade(OK if ok else PANEL2, a, fill))
        lf = font("display", 34); L = "ABCD"[i]
        d.text((STAGE[0] + 34, y + 34), L, font=lf, fill=fade(BG if ok else INK2, a, OK if ok else PANEL2), anchor="mm")
        draw_rich(d, op, STAGE[0] + 72, y + 12, osz, stage_w() - 92, INK3 if dim else INK, a, panel=fill)
        y += oh + 14
    overflow('quiz options', y - 12)
    if th and th[0] <= t < th[1]:
        left = math.ceil(th[1] - t)
        beat = max(0.0, 1 - ((t - th[0]) % 1) / 0.25)          # swells on every tick
        cx, cy, rr = STAGE[2] - 50, STAGE[1] + 34, int(38 + 8 * beat)
        frac = (th[1] - t) / (th[1] - th[0])
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=PANEL, outline=LINE, width=7)
        d.arc((cx - rr, cy - rr, cx + rr, cy + rr), -90, -90 + 360 * frac, fill=COPPER, width=7)
        fn = font("display", int(44 + 10 * beat))
        d.text((cx, cy), str(left), font=fn, fill=INK, anchor="mm")
    notes = s.get("notes")
    if notes and k >= 1:
        nt = notes[min(k - 1, len(notes) - 1)]
        if nt:
            a2 = appear(t, sc["segs"][k]["start"] - 0.1)
            overflow('quiz notes', draw_rich(d, nt, STAGE[0], y + 10, fit_size(nt, stage_w(), STAGE[3] - y - 10, 36, 24), stage_w(), INK, a2))

def r_compare(d, sc, t, short):
    s = sc["scene"]; k = seg_index(sc, t)
    y = scene_title(d, s, appear(t, sc["start"] - 0.2), STAGE[1] + 10)
    heads = s["heads"]; rows = s["rows"]; offset = int(s.get("offset", 0))
    colw = (stage_w() - 16) / 2
    a = appear(t, sc["start"] - 0.2)
    for i, h in enumerate(heads):
        x = STAGE[0] + i * (colw + 16)
        d.rounded_rectangle((x, y, x + colw, y + 60), radius=12, fill=fade(COPPER if i == 0 else PCB, a))
        f = fit_font("display", h.upper(), 36, colw - 28); d.text((x + 16, y + 10), h.upper(), font=f, fill=fade(BG, a, COPPER if i == 0 else PCB))
    y += 76
    size = 34
    for ri, row in enumerate(rows):
        seg = ri + offset
        if seg > k: break
        t0 = sc["segs"][seg]["start"] if seg < len(sc["segs"]) else sc["start"]
        a2 = appear(t, t0 - 0.1)
        hgt = max(text_h(c, size, colw - 28) for c in row) + 26
        for i, ctext in enumerate(row):
            x = STAGE[0] + i * (colw + 16)
            d.rounded_rectangle((x, y, x + colw, y + hgt), radius=12, fill=fade(PANEL, a2))
            draw_rich(d, ctext, x + 14, y + 12, size, colw - 28, INK if seg == k else INK2, a2, panel=PANEL)
        y += hgt + 12
    overflow('compare rows', y - 12)

def r_card(d, sc, t, short):
    s = sc["scene"]; a = appear(t, sc["start"] - 0.2, 0.3)
    size = fit_size(s["text"], stage_w(), 420, 70, 32, base="display2", lh=1.12)
    block = 74 + text_h(s["text"], size, stage_w(), "display2", 1.12) + (30 + text_h(s["sub"], 32, stage_w()) if s.get("sub") else 0)
    y = max(STAGE[1] + 40, (STAGE[1] + STAGE[3]) // 2 - 40 - block // 2)
    kick = s.get("kicker", "ANSWER").upper()
    f = font("monob", 24)
    col = OK if s.get("tone", "ok") == "ok" else COPPER
    d.rounded_rectangle((STAGE[0], y, STAGE[0] + f.getlength(kick) + 28, y + 42), radius=21, fill=fade(col, a))
    d.text((STAGE[0] + 14, y + 7), kick, font=f, fill=fade(BG, a, col))
    y += 74
    y = draw_rich(d, s["text"], STAGE[0], y, size, stage_w(), INK, 1.0, base="display2", lh=1.12, anim=(t, sc["vs"] + 0.1, 0.05))
    if s.get("sub"):
        a2 = appear(t, sc["start"] + 0.4, 0.3)
        draw_rich(d, s["sub"], STAGE[0], y + 30, 32, stage_w(), INK2, a2)

RENDER = {"hook": r_hook, "bullets": r_bullets, "formula": r_formula, "code": r_code, "cells": r_cells,
          "tree": r_tree, "quiz": r_quiz, "compare": r_compare, "card": r_card, "outro": r_card, "answer": r_card}

# ---------- frame ----------
STAGE_BOX = (0, 120, W, 1000)      # the part of the frame that zooms, punches and shakes
# --- gameplay footage as the background ---
# course.json "shorts.background" ("gameplay" or "drawn") sets it for every short; a script's "bg" overrides it.
# The footage is "shorts.backgroundFile": one video, or a folder of videos (each short gets one, picked from its id).
# Each short plays its own stretch of the clip, scaled to fill the frame and dimmed toward the scheme's background so
# text stays readable. Without footage the short gets the scheme's drawn background (see gameplay_missing()).
GAMEPLAY_DIM = 0.5                               # share of the scheme's background color mixed over the footage
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".m4v")
GP = None                                        # the current short's Gameplay, or None for a drawn background


def gameplay_clips():
    p = GAMEPLAY_PATH
    if p and os.path.isdir(p):
        return sorted(os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(VIDEO_EXT))
    return [p] if p and os.path.isfile(p) else []


def wants_gameplay(short): return str(short.get("bg") or DEFAULT_BG).startswith("gameplay")
def is_gameplay(short): return wants_gameplay(short) and bool(gameplay_clips())


def gameplay_missing(scripts):
    """One line for the person when a short wants gameplay footage that is not there."""
    if any(wants_gameplay(s) for s in scripts) and not gameplay_clips():
        rel = (os.path.relpath(GAMEPLAY_PATH, ROOT) if GAMEPLAY_PATH.startswith(ROOT) else GAMEPLAY_PATH).replace(os.sep, "/")
        print(f"no background video at {rel}: using a drawn background. For the gameplay look, drop a free-to-use "
              "Minecraft parkour gameplay clip there (see shorts/backgrounds/README.md).", flush=True)


class Gameplay:
    def __init__(self, sid, total):
        clips = gameplay_clips()
        pick = int(hashlib.sha256(("clip:" + sid).encode()).hexdigest()[:8], 16)
        self.path = clips[pick % len(clips)]
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", self.path], capture_output=True, text=True)
        span = max(0.0, float(r.stdout.strip() or 0) - total - 2)
        self.offset = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16) % 100000 / 100000 * span
        self.p, self.next, self.last = None, 0, None
    def _open(self, i):
        self.close()
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS}"
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{self.offset + i / FPS:.3f}", "-i", self.path, "-an", "-vf", vf,
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.next = i
    def frame(self, t):
        i = int(round(t * FPS))
        if self.p is None or i != self.next: self._open(i)       # frames in order read on; a jump seeks again
        b = self.p.stdout.read(W * H * 3); self.next = i + 1
        if len(b) == W * H * 3:
            # bright footage (snow, sky) gets dimmed harder so light text keeps its contrast
            lum = float(np.frombuffer(b, np.uint8)[::97].mean()) / 255
            dim = min(0.8, max(GAMEPLAY_DIM, GAMEPLAY_DIM + (lum - 0.35) * 1.1))
            self.last = Image.blend(Image.frombytes("RGB", (W, H), b), Image.new("RGB", (W, H), BG), dim)
        return (self.last or Image.new("RGB", (W, H), BG)).copy()
    def close(self):
        if self.p:
            try: self.p.kill()
            except Exception: pass
            self.p = None

def use_gameplay(short, total):
    global GP
    if GP: GP.close()
    GP = Gameplay(short["id"], total) if is_gameplay(short) else None

def background(t):
    """The scheme's drawn background, or the short's gameplay footage."""
    if GP: return GP.frame(t)
    im = fx.backdrop(BG_STYLE, t, BG_PARAMS, font)
    return im

def word_starts(seg):
    """Absolute start time of every caption word, from the narrator's own word timing when available."""
    if "_ws" in seg: return seg["_ws"]
    orig = re.sub(r"[`*]", "", seg["text"]).split()
    words = seg.get("words") or []
    out = None
    if words and orig:
        counts = [len(spoken_words(speakable(w, seg.get("voice")))) for w in orig]
        N, M = sum(counts), len(words)
        out, k, cum = [], 0, 0
        for c in counts:
            if N == M:
                idx = k if c else max(0, k - 1)
                k += c
            else:
                idx = min(M - 1, int((cum + c / 2) / max(N, 1) * M)); cum += c
            out.append(seg["start"] - seg.get("trim", (0, 0))[0] + words[min(idx, M - 1)]["s"])
    seg["_ws"] = out
    return out

def active_seg(tl, t):
    seg = None
    for sc in tl:
        for sg in sc["segs"]:
            if sg["start"] - 0.05 <= t <= sg["end"] + 0.12: seg = sg
    return seg

CAP_SIZE, CAP_Y, CAP_MAXW = 66, 1076, W - 150
def cap_word(w):
    w = w.upper()
    return w.rstrip(",.;:") or w

def draw_caption(d, tl, t):
    """Kinetic captions: a few words at a time, each popping in as it is spoken; keywords (**...**) in copper."""
    seg = active_seg(tl, t)
    if not seg: return
    words = fx.caption_words(seg["text"])
    if not words: return
    ws = word_starts(seg)
    if not ws or len(ws) != len(words):          # no narrator timing: spread the words by length
        dur = seg["end"] - seg["start"]; L = sum(len(w) + 1 for w, _ in words); acc = 0; ws = []
        for w, _ in words:
            ws.append(seg["start"] + acc / L * dur); acc += len(w) + 1
    cur = 0
    for i, s0 in enumerate(ws):
        if t >= s0 - 0.03: cur = i
    group = next(g for g in fx.caption_groups(words) if cur in g)
    # lay the whole group out first so words never move while the rest appear
    wsize = lambda i: CAP_SIZE * (1.12 if words[i][1] else 1.0)
    space = font("heavy", CAP_SIZE).getlength(" ") * 0.8 + max(4, CAP_SIZE // 10) * 1.6   # room for both outlines
    widths = {i: font("heavy", int(wsize(i))).getlength(cap_word(words[i][0])) for i in group}
    k = min(1.0, CAP_MAXW / max(widths.values()))
    lines, ln, x = [], [], 0
    for i in group:
        wl = widths[i] * k
        if ln and x + space + wl > CAP_MAXW:
            lines.append(ln); ln, x = [], 0
        x += (space if ln else 0) + wl; ln.append(i)
    if ln: lines.append(ln)
    lh = CAP_SIZE * k * 1.1
    slam = min(1.0, fx.ease_out_back((t - ws[group[0]] + 0.03) / 0.16))
    y0 = CAP_Y - (len(lines) - 1) * lh / 2 + 22 * (1 - slam)
    for li, ln in enumerate(lines):
        tw = sum(widths[i] * k for i in ln) + space * (len(ln) - 1)
        x = (W - 70 - tw) / 2 + 5            # centred, nudged left of the feed's button column
        cy = y0 + li * lh
        for i in ln:
            wl = widths[i] * k
            if i <= cur:
                p = (t - ws[i] + 0.03) / 0.14
                pop = 1 + 0.22 * (1 - ease(p)) if p < 1 else 1.0
                pop = min(pop, (wl + space * 0.85) / max(wl, 1))   # the pop stays inside the word's own gap
                size = int(wsize(i) * k * pop)
                d.text((x + wl / 2, cy), cap_word(words[i][0]), font=font("heavy", size), anchor="mm",
                       fill=COPPER if words[i][1] else CAP_INK, stroke_width=max(4, size // 10), stroke_fill=(0, 0, 0))
            x += wl + space

def draw_progress(d, tl, t):
    """One segment per scene, so you can feel the short moving."""
    x0, x1, y0, y1, gap = 32, W - 32, 24, 31, 6
    durs = [sc["ve"] - sc["vs"] for sc in tl]; T = sum(durs) or 1
    span = x1 - x0 - gap * (len(tl) - 1); x = x0
    for sc, du in zip(tl, durs):
        w = span * du / T
        d.rounded_rectangle((x, y0, x + w, y1), radius=3, fill=TRACK)
        f = min(1.0, max(0.0, (t - sc["vs"]) / max(du, 0.01)))
        if f > 0: d.rounded_rectangle((x, y0, x + max(7, w * f), y1), radius=3, fill=COPPER)
        x += w + gap

def draw_chrome(d, short, tl, t, unit_code):
    draw_progress(d, tl, t)
    # unit chip + title
    f = font("display", 30)
    wl = f.getlength(unit_code) + 26
    d.rounded_rectangle((32, 52, 32 + wl, 96), radius=10, fill=PANEL2)
    d.text((45, 56), unit_code, font=f, fill=PCB)
    ft = font("bodyb", 24)
    title = short["title"]
    while ft.getlength(title) > W - 64 - wl - 20 and len(title) > 8:
        title = title[:-2]
    if title != short["title"]: title = title.rstrip() + "…"
    d.text((32 + wl + 14, 60), title, font=ft, fill=INK2)
    if BRAND:
        fb = fit_font("display", BRAND, 22, W - 64)
        d.text((W - 32 - fb.getlength(BRAND), 106), BRAND, font=fb, fill=INK3)

CONFETTI = []
def frame_at(short, tl, total, t, unit_code, cue=None):
    snd, punches, bursts = cue or cues(tl)
    im = background(t); d = ImageDraw.Draw(im)
    cur = tl[0]
    for sc in tl:
        if sc["vs"] <= t: cur = sc
    # the scene is drawn on its own transparent layer so it can zoom in, punch on reveals, shake and fade out
    layer = Image.new("RGBA", (W, H), BG + (0,))
    RENDER[cur["scene"]["type"]](ImageDraw.Draw(layer), cur, t, short)
    scale, dx, dy, alpha = fx.stage_transform(t, cur["vs"], cur["ve"], [p for p in punches if cur["vs"] <= p[0] < cur["ve"]])
    region = layer.crop(STAGE_BOX)
    if abs(scale - 1) > 1e-3:
        region = region.resize((round(region.width * scale), round(region.height * scale)), Image.BILINEAR)
    if alpha < 1:
        region.putalpha(region.getchannel("A").point(lambda v: int(v * alpha)))
    cx, cy = (STAGE_BOX[0] + STAGE_BOX[2]) / 2, (STAGE_BOX[1] + STAGE_BOX[3]) / 2
    im.paste(region, (round(cx - region.width / 2 + dx), round(cy - region.height / 2 + dy)), region)
    for b in bursts:                                  # right answer: confetti and a green flash
        fx.confetti(d, t, b, CONFETTI, seed=int(b * 100))
        if 0 <= t - b < 0.35:
            d.rectangle((0, 0, W - 1, H - 1), outline=OK, width=max(1, int(18 * (1 - (t - b) / 0.35))))
    draw_chrome(d, short, tl, t, unit_code)
    draw_caption(d, tl, t)
    return im

def unit_code(short):
    return UNIT_CODES.get(short["unit"], short["unit"].upper())


def work_dir():
    return speech.cache_dir(ROOT, "shorts", "work")


def render_one(args):
    root, short = args
    setup(root)
    apply_theme(theme_of(short))
    tl, total = timeline(short)
    use_gameplay(short, total)
    out = out_dir(); os.makedirs(out, exist_ok=True)
    wav = os.path.join(work_dir(), short["id"] + ".wav"); mwav = os.path.join(work_dir(), short["id"] + ".music.wav")
    cue = cues(tl)
    build_audio(tl, total, wav, mwav, cue[0], music_seed(short))
    encode_music(mwav, os.path.join(out, short["id"] + ".music.m4a")); os.remove(mwav)
    mp4 = os.path.join(out, short["id"] + ".mp4")
    code = unit_code(short)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", wav, "-c:v", "libx264", "-preset", "medium", "-tune", "animation", "-crf", "30", "-pix_fmt", "yuv420p", "-g", str(FPS * 2),
           *AUDIO_ARGS, "-movflags", "+faststart", "-shortest", mp4]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(math.ceil(total * FPS))
    poster_t = min(1.2, total / 2)
    for i in range(n):
        t = i / FPS
        im = frame_at(short, tl, total, t, code, cue)
        p.stdin.write(im.tobytes())
        if abs(t - poster_t) < 0.5 / FPS:
            im.save(os.path.join(out, short["id"] + ".jpg"), "JPEG", quality=80)
    p.stdin.close(); rc = p.wait()
    if GP: GP.close()
    os.remove(wav)
    if rc != 0: raise RuntimeError("ffmpeg failed for " + short["id"])
    return entry(short, total, publish(out, short["id"]))


# The site caches these files, so a changed file must get a new name: <id>-<first 10 hex of its sha256>.
# Unchanged files keep their name.
KINDS = (("video", ".mp4"), ("poster", ".jpg"), ("music", ".music.m4a"))

def published(out, sid, ext):
    """The current file of one kind for a short: its content-named copy, else the plain <id><ext>."""
    rx = re.compile(re.escape(sid) + r"-[0-9a-f]{10}" + re.escape(ext) + "$")
    named = [f for f in os.listdir(out) if rx.match(f)]
    if named: return max(named, key=lambda f: os.path.getmtime(os.path.join(out, f)))
    return sid + ext if os.path.exists(os.path.join(out, sid + ext)) else None

def publish(out, sid):
    """Move the freshly written <id><ext> files to content names and delete the older copies of this short."""
    names = {}
    for kind, ext in KINDS:
        src = os.path.join(out, sid + ext)
        with open(src, "rb") as f: h = hashlib.sha256(f.read()).hexdigest()[:10]
        name = f"{sid}-{h}{ext}"
        rx = re.compile(re.escape(sid) + r"-[0-9a-f]{10}" + re.escape(ext) + "$")
        for old in os.listdir(out):
            if rx.match(old) and old != name: os.remove(os.path.join(out, old))
        os.replace(src, os.path.join(out, name))
        names[kind] = name
    return names


def entry(short, total, names):
    return {"id": short["id"], "unit": short["unit"], "title": short["title"], "kind": short.get("kind", "explain"),
            "duration": round(total, 2), "bytes": os.path.getsize(os.path.join(out_dir(), names["video"])),
            "caption": short.get("caption", ""), "video": names["video"], "poster": names["poster"], "music": names["music"]}


def remux_one(args):
    """New audio for an already rendered short, keeping its video stream as it is (no frames are redrawn)."""
    root, short = args
    setup(root)
    apply_theme(theme_of(short))
    tl, total = timeline(short)
    out = out_dir(); sid = short["id"]
    cur = {kind: published(out, sid, ext) for kind, ext in KINDS}
    if not cur["video"] or not cur["poster"]: raise RuntimeError("render the video first: " + sid)
    mp4 = os.path.join(out, sid + ".mp4"); tmp = os.path.join(work_dir(), sid + ".remux.mp4")
    wav = os.path.join(work_dir(), sid + ".wav"); mwav = os.path.join(work_dir(), sid + ".music.wav")
    build_audio(tl, total, wav, mwav, cues(tl)[0], music_seed(short))
    encode_music(mwav, os.path.join(out, sid + ".music.m4a"))
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(out, cur["video"]), "-i", wav, "-map", "0:v",
                        "-map", "1:a", "-c:v", "copy", *AUDIO_ARGS, "-movflags", "+faststart", tmp])
    os.remove(wav); os.remove(mwav)
    if r.returncode != 0: raise RuntimeError("ffmpeg remux failed for " + sid)
    os.replace(tmp, mp4)
    if cur["poster"] != sid + ".jpg":                  # the poster is unchanged; publish() expects it under the plain name
        os.replace(os.path.join(out, cur["poster"]), os.path.join(out, sid + ".jpg"))
    return entry(short, total, publish(out, sid))

def out_dir():
    """Where videos, posters, music and the manifest go."""
    return os.path.join(ROOT, "site", "shorts")

def frames_dir():
    return speech.cache_dir(ROOT, "shorts", "frames")

def update_manifest(results):
    mp = os.path.join(out_dir(), "manifest.json")
    man = {}
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            man = {m["id"]: m for m in json.load(f)}
    for r in results: man[r["id"]] = r
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(sorted(man.values(), key=lambda m: m["id"]), f, indent=1, ensure_ascii=False)

def need_clips(scripts):
    """Narrates any line that has no clip yet (nothing to do when every clip is cached)."""
    for sc in scripts:
        v = voice_of(sc)
        for scene in sc["scenes"]:
            for line in says(scene):
                p = clip_path(v, speakable(line, v))
                if not (os.path.exists(p) and os.path.exists(p[:-4] + ".json")):
                    run_tts(scripts); return

COMMANDS = ("tts", "sheet", "frames", "video", "all", "audio")

def main(argv):
    root = speech.course_root(argv)
    if not argv or argv[0] not in COMMANDS:
        raise SystemExit("usage: python -I shorts/render.py [--root <course folder>] " + "|".join(COMMANDS) + " [ids...]")
    setup(root)
    cmd, rest = argv[0], argv[1:]
    if cmd in ("frames", "sheet"):
        if not rest: raise SystemExit(f"usage: python -I shorts/render.py {cmd} <id>" + (" <seconds> ..." if cmd == "frames" else ""))
        sid = rest[0]
        short = load_scripts([sid])[0]
        need_clips([short])
        gameplay_missing([short])
        apply_theme(theme_of(short))
        tl, total = timeline(short)
        use_gameplay(short, total)
        code = unit_code(short); cue = cues(tl)
        if cmd == "frames":
            for tt in [float(x) for x in rest[1:]]:
                dst = os.path.join(frames_dir(), f"{sid}_{tt:05.1f}.jpg")
                frame_at(short, tl, total, tt, code, cue).save(dst, "JPEG", quality=85)
                print("frame:", dst)
            print("total", round(total, 2), "scenes", [(sc["scene"]["type"], round(sc["start"], 1), round(sc["end"], 1)) for sc in tl])
        else:
            times = []
            for sc in tl:
                for sg in sc["segs"]:
                    times.append(min(sg["end"] - 0.05, sc["end"] - 0.05))
                th = sc["scene"].get("_think")
                if th: times.append((th[0] + th[1]) / 2)
            times = sorted(set(round(x, 2) for x in times))
            ims = []
            for tt in times:
                WARN.clear()
                ims.append(frame_at(short, tl, total, tt, code, cue).resize((288, 512)))
                for w in sorted(set(WARN)): print(f"WARNING t={tt:.1f}s: {w}")
            cols = 5; rows = math.ceil(len(ims) / cols)
            sheet = Image.new("RGB", (cols * 296, rows * 520), (70, 70, 70))
            for i, im in enumerate(ims): sheet.paste(im, ((i % cols) * 296, (i // cols) * 520))
            dst = os.path.join(frames_dir(), sid + "_sheet.jpg")
            sheet.save(dst, "JPEG", quality=82)
            print("duration", round(total, 1), "s;", len(times), "frames;", "sheet:", dst)
        if GP: GP.close()
        return
    scripts = load_scripts(rest or None)
    if cmd == "tts":
        run_tts(scripts)
    if cmd in ("video", "all"):
        run_tts(scripts)
        gameplay_missing(scripts)
        jobs = [(ROOT, s) for s in scripts]
        workers = max(1, min(4, os.cpu_count() or 2))
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = []
            for r in ex.map(render_one, jobs):
                print("rendered", r["id"], r["duration"], "s", r["bytes"] // 1024, "KB", flush=True)
                results.append(r)
        update_manifest(results)
        print("wrote", len(results), "shorts to site/shorts/")
    if cmd == "audio":                                # rebuild only the sound of rendered shorts
        need_clips(scripts)
        jobs = [(ROOT, s) for s in scripts]
        with ProcessPoolExecutor(max_workers=max(1, min(4, os.cpu_count() or 2))) as ex:
            results = []
            for r in ex.map(remux_one, jobs):
                print("audio", r["id"], r["duration"], "s", r["bytes"] // 1024, "KB", flush=True)
                results.append(r)
        update_manifest(results)

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(errors="replace")
    main(sys.argv[1:])
