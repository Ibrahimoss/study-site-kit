"""Shared narration helpers for the audio lessons (audio/narrate.py) and the shorts (shorts/render.py).

- Finds the course (course.json) and reads it.
- Turns written text into what the voice should say: the kit's word list (shorts/pronunciations.json) merged
  with the course's own (course/pronunciations.json), plus a few generic spoken rules (units, symbols).
- Runs Kokoro, either here ("kokoro-local") or on the voice PC over SSH ("kokoro-ssh", see shorts/homepc/README.md).
  Clips are cached in .cache/tts/ under the course folder, named by voice, speed and text, so a changed line is
  the only thing narrated again.

course/pronunciations.json (optional) has the same shape as shorts/pronunciations.json:
  "words": {"WORD": {"us": "<phonemes>", "gb": "<phonemes>"}}   exact sounds (Kokoro notation)
  "spell": {"text": "how to say it"}                           plain respelling, e.g. {"NaCl": "sodium chloride"}
See shorts/pronunciations.example.json.
"""
import hashlib, json, os, re, subprocess, sys, tarfile, time

SHORTS = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(SHORTS)                       # the repository root when the kit is used as it is


# ---------- the course ----------
def course_root(argv):
    """Pops "--root DIR" from argv (a list, changed in place). Default: the repository this kit lives in."""
    root = KIT
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv): raise SystemExit("--root needs a folder")
        root = argv[i + 1]; del argv[i:i + 2]
    root = os.path.abspath(root)
    if not os.path.exists(os.path.join(root, "course.json")):
        raise SystemExit(f"no course.json in {root} (run from the course folder, or pass --root <folder>)")
    return root


def load_course(root):
    with open(os.path.join(root, "course.json"), encoding="utf-8") as f:
        return json.load(f)


def cache_dir(root, *parts):
    d = os.path.join(root, ".cache", *parts)
    os.makedirs(d, exist_ok=True)
    return d


def resolve(root, path):
    """A path from course.json: absolute as it is, otherwise relative to the course folder."""
    path = os.path.expanduser(path)
    return path if os.path.isabs(path) else os.path.join(root, path)


# ---------- what the voice says ----------
# Generic spoken rules, applied after the course's own words. Keep this list small and subject-free.
SPEAK = [
    (r"(\d+)\s*\^\s*(\d+)", r"\1 to the power \2"),
    (r"\bms\b", "milliseconds"), (r"\bKB\b", "kilobytes"), (r"\bMB\b", "megabytes"), (r"\bGB\b", "gigabytes"),
    (r"\bTB\b", "terabytes"), (r"\bkm\b", "kilometres"), (r"\bkg\b", "kilograms"),
    (r"\bi\.e\.", "that is"), (r"\be\.g\.", "for example"), (r"\betc\.", "and so on"), (r"\bvs\.?(?=\s)", "versus"),
    (r"×", " times "), (r"÷", " divided by "), (r"\s/\s", " divided by "), (r"\s\*\s", " times "), (r"\s\+\s", " plus "),
    (r"\s=\s", " equals "), (r"→", " to "), (r"≤", " at most "), (r"≥", " at least "), (r"≈", " about "),
    (r"%", " percent "), (r"&", " and "), (r"[`*_]", ""),
]
MARKUP = re.compile(r"\[([^\]]+)\]\(/[^)]*/\)")      # [word](/phonemes/): Kokoro says exactly these sounds


def _read_json(path):
    if not os.path.exists(path): return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Speech:
    """The pronunciation rules of one course."""

    def __init__(self, root):
        kit, course = _read_json(os.path.join(SHORTS, "pronunciations.json")), _read_json(os.path.join(root, "course", "pronunciations.json"))
        self.words = dict(kit.get("words", {})); self.words.update(course.get("words", {}))
        self.spell = dict(kit.get("spell", {})); self.spell.update(course.get("spell", {}))
        alt = lambda keys: "|".join(sorted(map(re.escape, keys), key=len, reverse=True))
        self._lex = re.compile(r"\b(" + alt(self.words) + r")\b", re.I) if self.words else None
        self._lex_key = {k.lower(): k for k in self.words}
        # a key that starts or ends with a letter or digit only matches as a whole word ("ln" not inside "kiln");
        # one that starts or ends with a symbol ("°C", "²") also matches right after a number
        guard = lambda k: ("(?<!\\w)" if re.match(r"[A-Za-z0-9]", k) else "") + re.escape(k) + ("(?!\\w)" if re.search(r"[A-Za-z0-9]$", k) else "")
        self._spell = re.compile("|".join(guard(k) for k in sorted(self.spell, key=len, reverse=True))) if self.spell else None

    def speakable(self, s, voice="af_heart"):
        """The text sent to Kokoro. Words in the lists are sent with their exact sounds, so every voice says them
        the same way; 'us' sounds for American voices (a...), 'gb' for British ones (b...)."""
        marks = []
        acc = "gb" if voice[:1] == "b" else "us"

        def hold(m):
            ph = self.words[self._lex_key[m.group(1).lower()]]
            marks.append("[%s](/%s/)" % (m.group(1), ph.get(acc) or ph.get("us")))
            return "\x00%d\x00" % (len(marks) - 1)
        if self._spell: s = self._spell.sub(lambda m: self.spell[m.group(0)], s)
        if self._lex: s = self._lex.sub(hold, s)
        for a, b in SPEAK:
            s = re.sub(a, b, s)
        if self._lex: s = self._lex.sub(hold, s)     # and words the rules produced
        # any other all-capital word is read letter by letter (DNA: "dee en ay"), so the voice never guesses
        s = re.sub(r"\b([A-Z]{2,})(s?)\b", lambda m: "[%s](/%s/)" % (m.group(0), letters(m.group(1), acc) + ("z" if m.group(2) else "")), s)
        s = re.sub(r"\s+", " ", s).strip()
        return re.sub("\x00(\\d+)\x00", lambda m: marks[int(m.group(1))], s)

    def spelled_out(self, text):
        """All-capital words in a written line that are in neither list (they will be read letter by letter)."""
        if self._spell: text = self._spell.sub(" ", text)
        if self._lex: text = self._lex.sub(" ", text)
        return sorted(set(m.group(1) for m in re.finditer(r"\b([A-Z]{2,})s?\b", text)))


# letter names in Kokoro's phonemes (us, gb), for acronyms read letter by letter
LETTERS = dict(A=("ˈA",), B=("bˈi", "bˈiː"), C=("sˈi", "sˈiː"), D=("dˈi", "dˈiː"), E=("ˈi", "ˈiː"), F=("ˈɛf",), G=("ʤˈi", "ʤˈiː"),
               H=("ˈAʧ",), I=("ˈI",), J=("ʤˈA",), K=("kˈA",), L=("ˈɛl",), M=("ˈɛm",), N=("ˈɛn",), O=("ˈO", "ˈQ"), P=("pˈi", "pˈiː"),
               Q=("kjˈu", "kjˈuː"), R=("ˈɑɹ", "ˈɑː"), S=("ˈɛs",), T=("tˈi", "tˈiː"), U=("jˈu", "jˈuː"), V=("vˈi", "vˈiː"),
               W=("dˈʌbᵊljˌu", "dˈʌbᵊljˌuː"), X=("ˈɛks",), Y=("wˈI",), Z=("zˈi", "zˈɛd"))


def letters(word, acc="us"):
    return " ".join(LETTERS[c][-1 if acc == "gb" else 0] for c in word)


def spoken_words(s):
    """Words the narrator's timing reports for a spoken text (a [word](/phonemes/) counts as one)."""
    return MARKUP.sub(lambda m: m.group(1).replace(" ", ""), s).split()


def plain_spoken(s):
    return MARKUP.sub(r"\1", s)


def clip_key(voice, speed, spoken):
    return hashlib.sha1(f"kokoro:{voice}@{speed}|{spoken}".encode("utf-8")).hexdigest()[:16]


# ---------- running Kokoro ----------
INSTALL = "python -m pip install -r audio/requirements.txt"


def synthesize(root, jobs, engine, voice_pc=None):
    """jobs: [{"key", "text", "voice", "speed"}]. Writes .cache/tts/<key>.wav and <key>.json (word timing and,
    when Whisper is available, what it heard)."""
    out = cache_dir(root, "tts")
    jobs = [j for j in jobs if not (os.path.exists(os.path.join(out, j["key"] + ".wav")) and os.path.exists(os.path.join(out, j["key"] + ".json")))]
    if not jobs:
        print("narration: every clip is already made", flush=True); return
    if engine == "kokoro-ssh":
        print(f"narrating {len(jobs)} clips on the voice PC ...", flush=True)
        _ssh(root, jobs, out, voice_pc or {})
    elif engine == "kokoro-local":
        sys.path.insert(0, os.path.join(SHORTS, "homepc"))
        try:
            import tts_kokoro
        except ImportError as e:
            raise SystemExit(f"Kokoro is not installed on this computer ({e.name} is missing).\n"
                             f"Install it once with:  {INSTALL}\n"
                             "or narrate on a voice PC: set \"engine\": \"kokoro-ssh\" and \"voicePC\" in course.json.")
        print(f"narrating {len(jobs)} clips on this computer ...", flush=True)
        tts_kokoro.run(jobs, out)
    else:
        raise SystemExit(f"unknown voice engine {engine!r}: use \"kokoro-local\" or \"kokoro-ssh\" in course.json")


def _ssh(root, jobs, out, pc):
    host = (pc.get("host") or "").strip()
    if not host:
        raise SystemExit("course.json: \"voicePC\": {\"host\": \"user@address\", \"key\": \"path to the SSH key\"} is empty; "
                         "fill it in (see shorts/homepc/README.md) or use \"kokoro-local\"")
    rdir = (pc.get("dir") or "study-kit-tts").replace("\\", "/").rstrip("/")   # relative = in the remote user's home folder
    py = pc.get("python") or rdir + "/venv/Scripts/python.exe"
    win = lambda p: p.replace("/", "\\") if ":" in p or "/Scripts/" in p else p   # cmd.exe wants back slashes in a program path
    opts = ["-o", "BatchMode=yes", "-o", "ServerAliveInterval=30"]
    if pc.get("key"): opts += ["-o", "IdentitiesOnly=yes", "-i", os.path.expanduser(pc["key"])]
    ssh, scp = ["ssh"] + opts, ["scp", "-q"] + opts

    def run(cmd, tries=4):
        """Retries a dropped connection; the voice PC skips clips it already made, so a retry only does the rest."""
        for n in range(tries):
            r = subprocess.run(cmd)
            if r.returncode == 0: return
            if n + 1 < tries:
                print(f"   connection problem, retrying ({n + 1}/{tries - 1}) ...", flush=True); time.sleep(15)
        raise SystemExit("the voice PC did not answer (check that it is on and that voicePC in course.json is right)")
    tag = "jobs"                                    # one run at a time: the files are overwritten next time
    jf = os.path.join(out, f"_{tag}.json"); tar = os.path.join(out, f"_{tag}.tar")
    with open(jf, "w", encoding="utf-8") as f: json.dump(jobs, f)
    try:
        run(scp + [os.path.join(SHORTS, "homepc", "tts_kokoro.py"), f"{host}:{rdir}/tts_kokoro.py"])
        run(scp + [jf, f"{host}:{rdir}/{tag}.json"])
        run(ssh + [host, f"{win(py)} {rdir}/tts_kokoro.py {rdir}/{tag}.json {rdir}/out --pack {rdir}/{tag}.tar"])
        run(scp + [f"{host}:{rdir}/{tag}.tar", tar])
        with tarfile.open(tar) as tf:
            for m in tf.getmembers():
                name = os.path.basename(m.name)
                if m.isfile() and re.fullmatch(r"[0-9a-f]{16}\.(wav|json)", name):
                    with tf.extractfile(m) as src, open(os.path.join(out, name), "wb") as dst:
                        dst.write(src.read())
    finally:
        for p in (jf, tar):
            if os.path.exists(p): os.remove(p)
