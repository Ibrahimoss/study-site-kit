"""Check the short scripts (course/shorts/scripts/*.json) and the rendered files. Prints "no problems" when clean.

python -I shorts/checks/check.py [--root <course folder>] [ids...] [--lines]

Checks: the JSON reads; the format (specs/SHORTS_SPEC.md: scene types and their fields, a hook first and a card
last, 4 quiz options, list lengths matching the narration lines); the writing rules (line and text lengths, no
digits or symbols in narration, no filler openers, no hints about where a question came from); the length (an
estimate from the text, and the real length once narrated, against the short's size); and the files (every
rendered short in site/shorts/manifest.json has its video, poster and music, and its script still exists).
Facts are not checked here: the AI checks them against course/content/ (specs/VERIFY_SPEC.md).
--lines also prints every narration line with its word count.
"""
import json, os, re, sys, wave

SHORTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SHORTS)
import speech

argv = [a for a in sys.argv[1:] if a != "--lines"]
SHOW_LINES = "--lines" in sys.argv
ROOT = speech.course_root(argv)
COURSE = speech.load_course(ROOT)
SAY = speech.Speech(ROOT)
SCRIPTS = os.path.join(ROOT, "course", "shorts", "scripts")
UNITS = {u["id"] for u in COURSE.get("units", [])}

problems, notes = [], []
def bad(sid, msg): problems.append(f"{sid}: {msg}")

def plain(t): return re.sub(r"[`*]", "", t or "")
def words(t): return plain(t).split()
def says(scene):
    s = scene.get("say", [])
    return [s] if isinstance(s, str) else list(s)

VOICE = re.compile(r"^[abejfhipz][fm]_[a-z]+$")          # Kokoro voice names: af_heart, bm_george, ...
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FORBIDDEN = re.compile(r"[0-9()\[\]{};/\\%=+<>_^&#|~`→×·:]")
FILLER = re.compile(r"^(So|Now|Basically|Let's take a look|As we can see)\b", re.I)
EXAMHINT = re.compile(r"\b(past paper|previous|was asked|grader|last year|20\d\d)\b", re.I)
SYNTAX = re.compile(r"\b(comma|commas|brackets?|parens?|parenthes[ie]s|semicolon|underscore|ampersand|asterisk|equals sign)\b", re.I)
# a short's "size" sets how many scenes it has and how long it runs (seconds); default "standard"
SIZES = {"micro": ((2, 4), (7, 17)), "standard": ((3, 6), (16, 34)), "deep": ((4, 8), (32, 58))}
TYPES = {"hook": ["text"], "bullets": ["items"], "formula": ["lines"], "code": ["code"], "cells": ["cells"], "tree": ["tree"],
         "quiz": ["q", "options", "answer"], "compare": ["heads", "rows"], "card": ["text"]}


def check_line(sid, where, line):
    n = len(words(line))
    if n > 14: bad(sid, f"{where}: narration line has {n} words (at most 14): {line!r}")
    stars = line.count("**")
    if stars % 2: bad(sid, f"{where}: odd number of ** in {line!r}")
    if stars // 2 > 2: bad(sid, f"{where}: more than 2 highlights in {line!r}")
    body = line.replace("**", "")
    if FORBIDDEN.search(body): bad(sid, f"{where}: write numbers and symbols as words in narration: {line!r} {FORBIDDEN.findall(body)}")
    if "*" in body: bad(sid, f"{where}: stray * in {line!r}")
    if FILLER.search(body): bad(sid, f"{where}: filler opener: {line!r}")
    if EXAMHINT.search(body): bad(sid, f"{where}: do not say where a question comes from: {line!r}")
    if SYNTAX.search(body): bad(sid, f"{where}: reads code symbols aloud: {line!r}")
    if re.search(r"\bi\.e\.|\be\.g\.", body): bad(sid, f"{where}: write 'that is' or 'for example': {line!r}")
    return n


def check_scene(sid, i, x, kind):
    t = x.get("type"); L = says(x); n = len(L); where = f"scene {i + 1} ({t})"
    if t not in TYPES: bad(sid, f"{where}: unknown scene type"); return
    for f in TYPES[t]:
        if f not in x: bad(sid, f"{where}: missing \"{f}\""); return
    if n == 0: bad(sid, f"{where}: no \"say\"")
    off = int(x.get("offset", 0))
    if t == "hook":
        if len(words(x["text"])) > 10: bad(sid, f"{where}: hook text has more than 10 words")
    elif t == "card":
        if len(words(x["text"])) > 14: bad(sid, f"{where}: card text has more than 14 words")
    elif t == "bullets":
        if not 2 <= len(x["items"]) <= 5: bad(sid, f"{where}: {len(x['items'])} items (2 to 5)")
        for it in x["items"]:
            if len(words(it)) > 6: bad(sid, f"{where}: item longer than 6 words: {it!r}")
        if len(x["items"]) + off > n: bad(sid, f"{where}: more items than narration lines")
    elif t == "formula":
        if len(x["lines"]) + off > n: bad(sid, f"{where}: more lines than narration lines")
    elif t == "compare":
        if len(x["heads"]) != 2: bad(sid, f"{where}: needs 2 heads")
        if len(x["rows"]) + off > n: bad(sid, f"{where}: more rows than narration lines")
    elif t == "code":
        cl = x["code"].split("\n")
        if len(cl) > 14: bad(sid, f"{where}: code has {len(cl)} lines (at most 14)")
        for c in cl:
            if len(c) > 46: bad(sid, f"{where}: code line of {len(c)} characters (at most 46): {c!r}")
        for key in ("hl", "show", "notes"):
            if key in x and len(x[key]) != n: bad(sid, f"{where}: \"{key}\" has {len(x[key])} entries for {n} narration lines")
        for h in x.get("hl", []):
            for ln in h:
                if not 1 <= ln <= len(cl): bad(sid, f"{where}: highlighted line {ln} does not exist")
    elif t == "cells":
        for key in ("hl", "notes"):
            if key in x and len(x[key]) != n: bad(sid, f"{where}: \"{key}\" has {len(x[key])} entries for {n} narration lines")
        allc = set()
        for b in x["cells"].get("blocks", []):
            for r in b.get("rows", []):
                if len(r) > 8: bad(sid, f"{where}: a row of {len(r)} cells (at most 8)")
                allc.update(map(str, r))
        for h in x.get("hl", []):
            miss = set(map(str, h or [])) - allc
            if miss: bad(sid, f"{where}: highlights cells not in the grid: {sorted(miss)}")
    elif t == "tree":
        for key in ("steps", "notes"):
            if key in x and len(x[key]) != n: bad(sid, f"{where}: \"{key}\" has {len(x[key])} entries for {n} narration lines")
    elif t == "quiz":
        if len(x["options"]) != 4: bad(sid, f"{where}: needs 4 options")
        if x["answer"] not in range(4): bad(sid, f"{where}: answer must be 0 to 3"); return
        if n < 2: bad(sid, f"{where}: needs a question line and a reveal line"); return
        if "pick one" not in L[0].lower(): bad(sid, f"{where}: the question line should end with 'Pause and pick one.'")
        letter = "ABCD"[x["answer"]]
        if not L[1].replace("**", "").startswith((letter + ".", "Answer " + letter + ".")):
            bad(sid, f"{where}: the reveal line should start with '{letter}.'")
        if "notes" in x and len(x["notes"]) != n - 1: bad(sid, f"{where}: \"notes\" has {len(x['notes'])} entries for {n - 1} reveal lines")


CPS = 15.0     # narrated characters per second (measured)
def estimate(s):
    """Seconds: speech at CPS + 0.12 s between lines + 0.12 s per scene + 0.65 s lead and tail + quiz think time."""
    nl = nc = 0; think = 0.0
    for x in s["scenes"]:
        for line in says(x):
            nl += 1; nc += len(plain(line))
        if x.get("type") == "quiz": think += float(x.get("think", 2))
    return nc / CPS + 0.12 * nl + 0.12 * len(s["scenes"]) + 0.65 + think


def real_length(s):
    """The rendered length from the narration clips, or None until the short is narrated."""
    try:
        import render
        render.setup(ROOT)
        return render.timeline(s)[1]
    except (FileNotFoundError, wave.Error):
        return None


def check_short(sid, path):
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
    except Exception as e:
        bad(sid, f"the JSON does not read: {e}"); return None
    if s.get("id") != sid: bad(sid, "\"id\" does not match the file name")
    if not ID.match(sid): bad(sid, "id: lowercase letters, digits and dashes only")
    if s.get("unit") not in UNITS: bad(sid, f"unit {s.get('unit')!r} is not a unit in course.json")
    if s.get("kind") not in ("question", "explain"): bad(sid, "\"kind\" must be \"question\" or \"explain\"")
    if "voice" in s and not VOICE.match(str(s["voice"])): bad(sid, f"unknown voice {s['voice']!r} (a Kokoro voice such as af_heart)")
    if s.get("bg") not in (None, "gameplay", "drawn"): bad(sid, "\"bg\" must be \"gameplay\" or \"drawn\"")
    if len(s.get("title", "")) > 40 or not s.get("title"): bad(sid, f"title must be 1 to 40 characters")
    if len(s.get("caption", "")) > 120: bad(sid, f"caption has {len(s['caption'])} characters (at most 120)")
    cp = os.path.join(ROOT, "course", "content", str(s.get("unit")) + ".json")
    if os.path.exists(cp) and "sections" in s:
        with open(cp, encoding="utf-8") as f:
            titles = [x.get("title") for x in json.load(f).get("sections", [])]
        for t in s["sections"]:
            if t not in titles: bad(sid, f"section {t!r} is not a section title of {s['unit']}")
    sc = s.get("scenes") or []
    if not sc: bad(sid, "no scenes"); return s
    size = s.get("size", "standard")
    if size not in SIZES: bad(sid, f"unknown size {size!r} (micro, standard, deep)"); size = "standard"
    lo, hi = SIZES[size][0]
    if not lo <= len(sc) <= hi: bad(sid, f"{len(sc)} scenes for a {size} short ({lo} to {hi})")
    if sc[0].get("type") != "hook" and not (size == "micro" and sc[0].get("type") == "quiz"): bad(sid, "the first scene must be a hook")
    if sc[-1].get("type") != "card": bad(sid, "the last scene must be a card")
    if (s.get("kind") == "question") != any(x.get("type") == "quiz" for x in sc):
        bad(sid, "a \"question\" short has a quiz scene, an \"explain\" short has none")
    for i, x in enumerate(sc):
        check_scene(sid, i, x, s.get("kind"))
        for line in says(x):
            check_line(sid, f"scene {i + 1}", line)
            for w in SAY.spelled_out(line):
                notes.append(f"{sid}: {w} will be read letter by letter (add it to course/pronunciations.json if it is said as a word)")
    est = estimate(s)
    lo, hi = SIZES[size][1]
    real = real_length(s)
    if real is not None:
        if not lo - 1 <= real <= hi + 1: bad(sid, f"narrated length {real:.1f} s is outside {lo} to {hi} s for a {size} short")
    elif not lo <= est <= hi:
        bad(sid, f"estimated length {est:.1f} s is outside {lo} to {hi} s for a {size} short")
    s["_len"] = (est, real)
    return s


def check_files(ids):
    mp = os.path.join(ROOT, "site", "shorts", "manifest.json")
    if not os.path.exists(mp): return
    with open(mp, encoding="utf-8") as f:
        man = json.load(f)
    for m in man:
        for k in ("video", "poster", "music"):
            if not m.get(k) or not os.path.exists(os.path.join(ROOT, "site", "shorts", m[k])):
                bad(m.get("id", "?"), f"rendered short has no {k} file in site/shorts/ (render it again)")
        if m.get("id") not in ids: bad(m.get("id", "?"), "is in site/shorts/manifest.json but has no script any more")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(errors="replace")
    files = sorted(f[:-5] for f in os.listdir(SCRIPTS) if f.endswith(".json")) if os.path.isdir(SCRIPTS) else []
    ids = argv or files
    rows = []
    for sid in ids:
        p = os.path.join(SCRIPTS, sid + ".json")
        if not os.path.exists(p): bad(sid, "no script course/shorts/scripts/" + sid + ".json"); continue
        s = check_short(sid, p)
        if s: rows.append(s)
    if not argv: check_files(set(files))
    if rows:
        print(f"{'id':28} scenes  est.s  real.s")
        for s in rows:
            est, real = s["_len"]
            print(f"{s['id']:28} {len(s['scenes']):6} {est:6.1f}  {'' if real is None else f'{real:6.1f}'}")
        print()
    else:
        print("no shorts yet")
    for n in sorted(set(notes)): print("note:", n)
    if SHOW_LINES:
        for s in rows:
            print("\n==", s["id"])
            for i, x in enumerate(s["scenes"]):
                for line in says(x):
                    print(f"  [{i + 1} {x.get('type', '?'):8}] ({len(words(line)):2}) {line}")
    print("PROBLEMS:" if problems else "no problems")
    for p in problems: print(" -", p)
    sys.exit(1 if problems else 0)
