"""Give every short a narrator from a rotation of six Kokoro voices, in feed order (the unit order of course.json,
then id), so two shorts next to each other in the feed never share a voice. The voice also picks the short's look.

python -I shorts/assign_voices.py [--root <course folder>] [ids...]   # rewrites "voice" only in the listed ids (all if none)
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import speech

ROTATION = ["af_heart", "am_michael", "bf_emma", "am_fenrir", "af_bella", "am_puck"]

argv = sys.argv[1:]
root = speech.course_root(argv); only = set(argv)
units = [u["id"] for u in speech.load_course(root).get("units", [])]
d = os.path.join(root, "course", "shorts", "scripts")
scripts = []
for f in os.listdir(d):
    if f.endswith(".json"):
        with open(os.path.join(d, f), encoding="utf-8") as fh:
            s = json.load(fh)
        scripts.append((units.index(s["unit"]) if s["unit"] in units else len(units), s["id"], f))
scripts.sort()
for k, (_, sid, f) in enumerate(scripts):
    v = ROTATION[k % len(ROTATION)]
    if only and sid not in only:
        continue
    p = os.path.join(d, f)
    with open(p, encoding="utf-8") as fh:
        s = json.load(fh)
    if s.get("voice") != v:
        s["voice"] = v
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(s, fh, indent=1, ensure_ascii=False)
    print(f"{k + 1:2} {sid:26} {v}")
