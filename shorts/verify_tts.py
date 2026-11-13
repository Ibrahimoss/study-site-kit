"""Check narrated shorts: real length, and every line Whisper heard differently from the script.

python -I shorts/verify_tts.py [--root <course folder>] [ids...]      (all scripts when no ids)

Needs Whisper where the narration ran (optional; without it only the lengths are listed). Lines are listed when
the similarity is below 0.9 after spelling out digits Whisper writes as numerals.
"""
import difflib, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R
import speech

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
def say_num(n):
    if n < 20: return ONES[n]
    if n < 100: return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000: return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + say_num(n % 100))
    return str(n)
def norm(s):
    s = s.lower().replace("-", " ")
    s = re.sub(r"\d+", lambda m: say_num(int(m.group())) if int(m.group()) < 1000 else m.group(), s)
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", s)).strip()

argv = sys.argv[1:]
R.setup(speech.course_root(argv))
low, totals, missing, unchecked = [], [], [], 0
for sc in R.load_scripts(argv or None):
    v = R.voice_of(sc)
    try:
        tl, total = R.timeline(sc)
    except FileNotFoundError:
        missing.append(sc["id"]); continue
    totals.append((sc["id"], v, total))
    for scene in sc["scenes"]:
        for line in R.says(scene):
            sp = R.speakable(line, v); p = R.clip_path(v, sp)
            with open(p[:-4] + ".json", encoding="utf-8") as f:
                heard = json.load(f).get("heard")
            if heard is None: unchecked += 1; continue
            sp = speech.plain_spoken(sp)            # compare what was heard with the word, not its phonemes
            r = difflib.SequenceMatcher(None, norm(sp), norm(heard)).ratio()
            if r < 0.9: low.append((sc["id"], round(r, 2), sp, heard))
for sid, v, t in totals: print(f"{sid:26} {v:11} {t:5.1f} s")
print("missing narration:", missing or "none")
if unchecked: print(f"{unchecked} lines not checked (Whisper is not installed where the narration ran)")
print(f"{len(low)} lines heard differently:")
for x in low: print("  ", x)
