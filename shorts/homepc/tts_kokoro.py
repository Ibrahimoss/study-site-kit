"""Kokoro narration: turns a list of text jobs into wav clips with word timing.

Used two ways:
- on this computer, imported by shorts/speech.py (engine "kokoro-local");
- on the voice PC, run over SSH (engine "kokoro-ssh"):
    python tts_kokoro.py <jobs.json> <outdir> [--pack <out.tar>]

jobs.json: [{"key": "...", "text": "...", "voice": "af_heart", "speed": 1.0}, ...]
Writes <outdir>/<key>.wav (24 kHz mono 16-bit) and <outdir>/<key>.json:
  {"words": [{"w": "cell", "s": 0.12, "e": 0.40}, ...],   word timing (Kokoro's own, else Whisper's)
   "heard": "what Whisper heard", "timing": "kokoro" | "whisper" | "none"}
"heard" is only there when Whisper (openai-whisper) is installed; it is optional and only double-checks the voice.
Clips that already exist are skipped, so an interrupted run carries on where it stopped. --pack puts this run's
clips in one tar file to copy back.
Uses the GPU when PyTorch sees one, else the CPU (slower, fine for a course).
"""
import json, os, re, sys, tarfile, time

SR = 24000
_pipes, _whisper = {}, [None]


def _device():
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def _pipeline(voice, dev):
    """American voices (a*) and British voices (b*) need their own pronunciation rules; they share one model."""
    from kokoro import KPipeline
    lang = voice[0] if voice[:1] in ("a", "b") else "a"
    if lang not in _pipes:
        first = next(iter(_pipes.values()), None)
        kw = dict(lang_code=lang, device=dev) if first is None else dict(lang_code=lang, model=first.model, device=dev)
        try:
            _pipes[lang] = KPipeline(repo_id="hexgrad/Kokoro-82M", **kw)
        except TypeError:                        # older Kokoro without repo_id
            _pipes[lang] = KPipeline(**kw)
    return _pipes[lang]


def _whisper_model(dev):
    """Whisper is optional: None when it is not installed."""
    if _whisper[0] is None:
        try:
            import whisper
        except ImportError:
            _whisper[0] = False
            print("note: Whisper is not installed, so the narration is not double-checked "
                  "(optional: python -m pip install openai-whisper)", flush=True)
        else:
            _whisper[0] = whisper.load_model("small.en", device=dev)
    return _whisper[0] or None


def _to_16k(a):
    import numpy as np
    n = int(len(a) * 16000 / SR)
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)


def run(jobs, out):
    import numpy as np
    import soundfile as sf
    os.makedirs(out, exist_ok=True)
    dev = _device()
    print("voice device:", dev, flush=True)
    t_start, done = time.time(), 0
    for j in jobs:
        wav = os.path.join(out, j["key"] + ".wav"); meta = os.path.join(out, j["key"] + ".json")
        if os.path.exists(wav) and os.path.exists(meta):
            continue
        parts, words, t0 = [], [], 0.0
        for res in _pipeline(j["voice"], dev)(j["text"], voice=j["voice"], speed=float(j.get("speed", 1.0)), split_pattern=None):
            a = getattr(res, "audio", None)
            if a is None:
                continue
            a = a.detach().cpu().numpy() if hasattr(a, "detach") else np.asarray(a)
            for tk in (getattr(res, "tokens", None) or []):
                s, e = getattr(tk, "start_ts", None), getattr(tk, "end_ts", None)
                txt = (getattr(tk, "text", "") or "").strip()
                if s is not None and e is not None and re.search(r"\w", txt):
                    words.append({"w": txt, "s": round(t0 + float(s), 3), "e": round(t0 + float(e), 3)})
            parts.append(a.astype(np.float32)); t0 += len(a) / SR
        audio = np.concatenate(parts) if parts else np.zeros(SR // 2, dtype=np.float32)
        sf.write(wav, audio, SR, subtype="PCM_16")
        info = {"words": words, "timing": "kokoro" if words else "none"}
        wm = _whisper_model(dev)
        if wm is not None:
            r = wm.transcribe(_to_16k(audio), language="en", word_timestamps=True, fp16=(dev == "cuda"), condition_on_previous_text=False)
            info["heard"] = r.get("text", "").strip()
            if not words:
                info["timing"] = "whisper"
                info["words"] = [{"w": w["word"].strip(), "s": round(float(w["start"]), 3), "e": round(float(w["end"]), 3)}
                                 for seg in r.get("segments", []) for w in seg.get("words", [])]
        with open(meta, "w", encoding="utf-8") as f:
            json.dump(info, f)
        done += 1
        if done % 10 == 0:
            print(f"   {done} of {len(jobs)} clips, {time.time() - t_start:.0f} s", flush=True)
    print(f"DONE {done} new clips in {time.time() - t_start:.0f} s", flush=True)


def pack(jobs, out, tar_path):
    with tarfile.open(tar_path, "w") as tf:
        for j in jobs:
            for ext in (".wav", ".json"):
                p = os.path.join(out, j["key"] + ext)
                if os.path.exists(p): tf.add(p, arcname=j["key"] + ext)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    os.environ.setdefault("HF_HOME", os.path.join(here, "hf"))      # the voice model lives next to this file
    args = sys.argv[1:]
    tar_path = None
    if "--pack" in args:
        i = args.index("--pack"); tar_path = args[i + 1]; del args[i:i + 2]
    with open(args[0], encoding="utf-8") as f:
        job_list = json.load(f)
    run(job_list, args[1])
    if tar_path: pack(job_list, args[1], tar_path)
