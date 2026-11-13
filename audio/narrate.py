"""Narrate the spoken lessons (course/audio/scripts/<id>.md) and publish them to site/audio/.

    python -I audio/narrate.py [--root <course folder>] [ids...]       (default: every script)

Install once for "kokoro-local":  python -m pip install -r audio/requirements.txt

Settings come from course.json:
  "audio":   {"engine": "kokoro-local" | "kokoro-ssh", "voice": "af_heart", "speed": 0.96}
  "voicePC": {"host": "user@address", "key": "~/.ssh/key", "dir": "study-kit-tts"}   (only for kokoro-ssh)

Each script is "# Title", then "## Section" headings and plain paragraphs (specs/AUDIO_STYLE.md). Every paragraph
is one Kokoro clip, said with the pronunciation lists (shorts/pronunciations.json and course/pronunciations.json),
joined with pauses, loudness-normalized and encoded as MP3. When Whisper is installed, every clip is also
listened to and paragraphs it heard differently are listed.
Output: site/audio/<id>-<hash>.mp3 (the name changes with the content, so the site can cache it) and
site/audio/manifest.json (title, file, duration and the start time of every section).
Clips are cached in .cache/tts/, so editing one paragraph only narrates that paragraph again.
"""
import difflib, glob, hashlib, json, os, re, subprocess, sys, wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "shorts"))
import speech                                     # course.json, pronunciations, the voice engines

SR = 24000
PAUSE = {"para": 0.6, "after_head": 0.75, "before_head": 1.2, "end": 1.0}
MIN_HEARD = 0.86                                  # Whisper agreement below this is reported for a listen


def parse(path):
    title, items, sec = None, [], None
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if b.startswith("# "):
            title = b[2:].strip(); continue
        if b.startswith("## "):
            sec = b[3:].strip(); items.append(("head", sec)); continue
        items.append(("para", re.sub(r"\s+", " ", b)))
    return title or os.path.splitext(os.path.basename(path))[0], items


def spoken_title(t):
    """'Unit 2: Cells | Part 1' is read as 'Unit 2. Cells. Part 1.' (a colon or bar becomes a full stop)."""
    return re.sub(r"\s*[:|]\s*", ". ", t).strip().rstrip(".")


def words(s):
    return re.findall(r"[a-z0-9]+", speech.plain_spoken(s).lower())


def read_wav(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def main(argv):
    root = speech.course_root(argv)
    course = speech.load_course(root)
    cfg = course.get("audio") or {}
    voice, speed = cfg.get("voice", "af_heart"), float(cfg.get("speed", 0.96))
    engine = cfg.get("engine", "kokoro-local")
    say = speech.Speech(root)
    cache = speech.cache_dir(root, "tts")
    out_dir = os.path.join(root, "site", "audio")
    scripts = sorted(glob.glob(os.path.join(root, "course", "audio", "scripts", "*.md")))
    if argv: scripts = [p for p in scripts if os.path.splitext(os.path.basename(p))[0] in argv]
    if not scripts:
        raise SystemExit("no audio scripts found in course/audio/scripts/" + (" for " + " ".join(argv) if argv else ""))
    plan, jobs, spelled = {}, {}, set()
    for p in scripts:
        sid = os.path.splitext(os.path.basename(p))[0]
        title, items = parse(p)
        seq = [("head0", spoken_title(title) + ".")]
        for kind, text in items:
            seq.append((kind, (text.rstrip(".") + ".") if kind == "head" else text))
        out = []
        for kind, text in seq:
            spelled.update(say.spelled_out(text))
            spoken = say.speakable(text, voice)
            k = speech.clip_key(voice, speed, spoken); out.append((kind, text, spoken, k))
            jobs[k] = {"key": k, "text": spoken, "voice": voice, "speed": speed}
        plan[sid] = (title, out)
    if spelled:
        print("read letter by letter:", ", ".join(sorted(spelled)), "(add any said as a word to course/pronunciations.json)")
    speech.synthesize(root, list(jobs.values()), engine, course.get("voicePC"))

    os.makedirs(out_dir, exist_ok=True)
    man_path = os.path.join(out_dir, "manifest.json")
    manifest = {}
    if os.path.exists(man_path):
        with open(man_path, encoding="utf-8") as f:
            manifest = {m["id"]: m for m in json.load(f)}
    artist = (course.get("site") or {}).get("title", "Study site")
    checked = False
    for sid, (title, out) in plan.items():
        pcm, chapters, t, weak = [], [], 0.0, []
        sil = lambda s: np.zeros(int(SR * s), dtype=np.float32)
        for n, (kind, text, spoken, k) in enumerate(out):
            if kind == "head" and n > 1: pcm.append(sil(PAUSE["before_head"])); t += PAUSE["before_head"]
            if kind == "head": chapters.append({"title": text.rstrip("."), "start": round(t, 1)})
            a = read_wav(os.path.join(cache, k + ".wav")); pcm.append(a); t += len(a) / SR
            with open(os.path.join(cache, k + ".json"), encoding="utf-8") as f:
                heard = json.load(f).get("heard")
            if heard is not None:
                checked = True
                ratio = difflib.SequenceMatcher(None, words(spoken), words(heard)).ratio()
                if ratio < MIN_HEARD and len(words(spoken)) > 3: weak.append((round(ratio, 2), text[:90], heard[:90]))
            gap = PAUSE["after_head"] if kind in ("head", "head0") else PAUSE["para"]
            pcm.append(sil(gap)); t += gap
        pcm.append(sil(PAUSE["end"]))
        audio = np.concatenate(pcm)
        wav = os.path.join(cache, "_" + sid + ".wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        tmp = os.path.join(out_dir, "_" + sid + ".mp3")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af", "loudnorm=I=-17:TP=-1.5:LRA=9",
                        "-ar", str(SR), "-ac", "1", "-c:a", "libmp3lame", "-b:a", "80k",
                        "-metadata", "title=" + title, "-metadata", "artist=" + artist, tmp], check=True)
        with open(tmp, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()[:10]
        name = f"{sid}-{h}.mp3"
        for old in glob.glob(os.path.join(out_dir, glob.escape(sid) + "-*.mp3")):
            if re.fullmatch(re.escape(sid) + r"-[0-9a-f]{10}\.mp3", os.path.basename(old)) and os.path.basename(old) != name:
                os.remove(old)
        os.replace(tmp, os.path.join(out_dir, name)); os.remove(wav)
        size = os.path.getsize(os.path.join(out_dir, name))
        manifest[sid] = {"id": sid, "title": title, "file": name, "duration": round(len(audio) / SR, 1),
                         "bytes": size, "chapters": chapters}
        print(f"{sid}: {len(audio) / SR / 60:.1f} min, {len(chapters)} sections, {size // 1024} KB"
              + (f", {len(weak)} paragraph(s) Whisper heard differently" if checked else ""))
        for r, said, heard in weak: print(f"   {r}  said: {said}\n         heard: {heard}")
    if not checked:
        print("note: the narration was not double-checked by Whisper (it is optional and not installed)")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(sorted(manifest.values(), key=lambda m: m["id"]), f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(errors="replace")
    main(sys.argv[1:])
