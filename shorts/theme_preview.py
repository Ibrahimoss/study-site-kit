"""Side-by-side preview of the color schemes: a few moments of each listed short.

python -I shorts/theme_preview.py [--root <course folder>] <out.jpg> id [id@scheme ...]

"id@scheme" previews a short in another scheme. For each short: the hook, the middle of the second scene, and the
last scene (or the quiz answer when there is one). The shorts must be narrated first (render.py tts).
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R
import speech

argv = sys.argv[1:]
root = speech.course_root(argv)
dst, ids = argv[0], argv[1:]
forced = {a.split("@")[0]: a.split("@")[1] for a in ids if "@" in a}
ids = [a.split("@")[0] for a in ids]
R.setup(root)

TW, TH = 240, 427
cols = []
for s in sorted(R.load_scripts(ids), key=lambda s: ids.index(s["id"])):
    if s["id"] in forced: s["theme"] = forced[s["id"]]
    R.apply_theme(R.theme_of(s))
    tl, total = R.timeline(s)
    R.use_gameplay(s, total)
    cue = R.cues(tl)
    mid = tl[min(1, len(tl) - 1)]
    times = [min(1.2, tl[0]["ve"] - 0.2), (mid["vs"] + mid["ve"]) / 2]
    times.append(cue[2][0] + 0.35 if cue[2] else (tl[-1]["vs"] + tl[-1]["ve"]) / 2)
    frames = [R.frame_at(s, tl, total, t, R.unit_code(s), cue).resize((TW, TH)) for t in times]
    cols.append((s["id"], R.voice_of(s), R.THEME, frames))

sheet = Image.new("RGB", (len(cols) * (TW + 10) + 10, 3 * (TH + 10) + 44), (60, 60, 60))
d = ImageDraw.Draw(sheet)
for i, (sid, voice, theme, frames) in enumerate(cols):
    x = 10 + i * (TW + 10)
    d.text((x, 8), f"{theme} ({voice})", font=R.font("bodyb", 16), fill=(255, 255, 255))
    d.text((x, 26), sid, font=R.font("body", 12), fill=(200, 200, 200))
    for j, f in enumerate(frames):
        sheet.paste(f, (x, 44 + j * (TH + 10)))
sheet.save(dst, quality=86)
if R.GP: R.GP.close()
print("preview:", dst, [(c[0], c[2]) for c in cols])
