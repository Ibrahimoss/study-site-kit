"""Build the study site from course.json and course/ into site/ (see specs/CONTRACT.md).

python -I engine/build.py [--root <repo>] [--target artifact|github-pages|file] [--stub]

  --root    the course repo (default: the folder that holds engine/)
  --target  overrides course.json hosting.target (default artifact)
  --stub    build units whose content file is missing with an empty placeholder instead of failing

Steps: slide thumbnails (not for the artifact target), small shorts posters (only when there are shorts), the data
blob, site/index.html (standalone, data inlined), the coverage report (build/coverage.md), every check, and for the
artifact target site/publish_plan.json. Prints "refs OK" and "no problems", or the problems, and exits 1 on problems.
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))

import coverage          # noqa: E402
import make_posters      # noqa: E402
import make_thumbs       # noqa: E402
from make_standalone import standalone  # noqa: E402

TARGETS = ("artifact", "github-pages", "file")
MB = 1024 * 1024
LIMITS = {"filesPerPublish": 255, "bytesPerPublish": 64 * MB, "filesPerVersion": 511, "bytesPerVersion": 256 * MB, "bytesPerFile": 16 * MB}

# Code highlighting per language; only the languages a course uses go into the page.
C_KW = ("int float double char void unsigned long short const return if else for while do break continue struct sizeof bool true false "
        "size_t typedef static extern auto signed switch case default goto new delete NULL nullptr enum union volatile register")
LANGS = {
    "c": {"kw": C_KW, "api": r"^(malloc|free|calloc|realloc|printf|scanf|fprintf|memcpy|memset|strlen|strcpy|strcmp|puts|exit)$",
          "line": "//", "block": True, "pp": True},
    "cuda": {"kw": C_KW, "q": "__global__ __device__ __host__ __shared__ __constant__ __syncthreads __managed__",
             "bi": "threadIdx blockIdx blockDim gridDim warpSize dim3", "api": r"^(cuda[A-Z]\w*|malloc|free|printf|memcpy|calloc)$",
             "line": "//", "block": True, "pp": True, "launch": True},
    "cpp": {"kw": C_KW + " class public private protected template typename namespace using virtual override this try catch throw "
                         "constexpr operator friend explicit inline mutable final noexcept",
            "api": r"^(std|cout|cin|cerr|endl|vector|string|map|set|unordered_map|pair|make_pair|printf|malloc|free)$",
            "line": "//", "block": True, "pp": True},
    "java": {"kw": "abstract boolean break byte case catch char class const continue default do double else enum extends final finally "
                   "float for if implements import instanceof int interface long new package private protected public return short "
                   "static super switch synchronized this throw throws try void volatile while true false null var record",
             "api": r"^(System|String|Math|Integer|Double|List|ArrayList|Map|HashMap|Set|HashSet|Arrays|Collections|Scanner|Object)$",
             "line": "//", "block": True},
    "javascript": {"kw": "var let const function return if else for while do break continue new this class extends super import export "
                         "from default async await try catch finally throw null undefined true false typeof instanceof of in switch case yield delete void",
                   "api": r"^(console|document|window|Math|JSON|Array|Object|Promise|fetch|Number|String|Map|Set|setTimeout)$",
                   "line": "//", "block": True, "tpl": True},
    "python": {"kw": "def class return if elif else for while in not and or is None True False import from as with try except finally "
                     "raise lambda yield pass break continue global nonlocal async await del assert",
               "bi": "self cls",
               "api": r"^(print|len|range|int|str|float|list|dict|set|tuple|open|input|enumerate|zip|map|filter|sorted|sum|min|max|abs|isinstance|type|super)$",
               "line": "#", "triple": True},
    "sql": {"kw": "select from where and or not insert into values update set delete create table drop alter add primary key foreign "
                  "references join inner left right outer full on group by order having as distinct union all null is in like between "
                  "exists case when then else end limit offset index view default unique check asc desc",
            "api": r"^(count|sum|avg|min|max|coalesce|upper|lower|length|substring|round|now|cast)$",
            "line": "--", "block": True, "ci": True},
}
LANG_NAMES = ("none",) + tuple(LANGS)
BLOCK_KEYS = ("p", "list", "steps", "code", "table", "defs", "tip", "note", "figure", "cells", "heading", "grid")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "study-lab"


class Build:
    def __init__(self, root, target, stub):
        self.root, self.target, self.stub = root, target, stub
        self.site = os.path.join(root, "site")
        self.course_dir = os.path.join(root, "course")
        self.problems, self.ref_problems, self.notes = [], [], []

    # ---------- helpers ----------
    def p(self, msg):
        self.problems.append(msg)

    def ref(self, msg):
        self.ref_problems.append(msg)

    def load(self, path, what, default=None, required=False):
        if not os.path.exists(path):
            if required:
                self.p(f"{what}: missing ({os.path.relpath(path, self.root)})")
            return default
        try:
            return json.load(open(path, encoding="utf-8"))
        except (ValueError, OSError) as e:
            self.p(f"{what}: not valid JSON ({os.path.relpath(path, self.root)}): {e}")
            return default

    # ---------- course.json ----------
    def read_course(self):
        c = self.load(os.path.join(self.root, "course.json"), "course.json", required=True)
        if not isinstance(c, dict):
            return None
        site = c.get("site") or {}
        if not site.get("title"):
            self.p("course.json: site.title is missing")
        lang = (c.get("code") or {}).get("language", "none")
        if lang not in LANG_NAMES:
            self.p(f"course.json: code.language {lang!r} is not one of {', '.join(LANG_NAMES)}")
            lang = "none"
        c["_lang"] = lang
        if not c.get("decks"):
            self.p("course.json: no decks")
        if not c.get("units"):
            self.p("course.json: no units")
        ids = [d.get("id") for d in c.get("decks", [])]
        hidden = {d.get("id") for d in c.get("decks", []) if d.get("publish", True) is False}
        if len(ids) != len(set(ids)):
            self.p("course.json: two decks share an id")
        for u in c.get("units", []):
            for k in ("id", "code", "title", "deck"):
                if not u.get(k):
                    self.p(f"course.json: unit {u.get('id', '?')} has no {k}")
            for d in [u.get("deck")] + list(u.get("tutorials") or []):
                if d and d not in ids:
                    self.p(f"course.json: unit {u.get('id')} names deck {d!r}, which is not in decks")
                elif d and d in hidden:
                    self.p(f"course.json: unit {u.get('id')} lists deck {d!r}, which has \"publish\": false (past papers are listed in decks only)")
        for x in c.get("papers") or []:
            if not x.get("id") or not x.get("name"):
                self.p(f"course.json: a paper needs id and name: {x}")
        for s in c.get("skills") or []:
            try:
                re.compile(s[0])
            except (re.error, TypeError, IndexError):
                self.p(f"course.json: skills entry {s!r} is not [regex, name]")
        at = (c.get("exam") or {}).get("at")
        if at and not re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?([+-]\d\d:\d\d|Z)?$", at):
            self.p(f"course.json: exam.at {at!r} is not an ISO date and time like 2027-03-14T10:00:00+03:00")
        return c

    # ---------- slides and text ----------
    def read_decks(self, c):
        from PIL import Image
        decks, text = {}, {}
        for dk in c.get("decks", []):
            did = dk["id"]
            ddir = os.path.join(self.site, "slides", did)
            hidden = dk.get("publish", True) is False
            if "publish" in dk and not isinstance(dk["publish"], bool):
                self.p(f"deck {did}: publish must be true or false")
            if hidden:
                # an unpublished deck (a graded paper: handwriting, maybe names) keeps its page images in .cache/slides/,
                # where the AI can read them but nothing ships them
                cdir = os.path.join(self.root, ".cache", "slides", did)
                if os.path.isdir(ddir):
                    if os.path.isdir(cdir):
                        shutil.rmtree(ddir)
                    else:
                        os.makedirs(os.path.dirname(cdir), exist_ok=True)
                        shutil.move(ddir, cdir)
                    self.notes.append(f"deck {did} is not published: moved its page images out of site/slides/ (they are in .cache/slides/{did}/)")
                ddir = cdir
            pages = sorted(int(m.group(1)) for f in (os.listdir(ddir) if os.path.isdir(ddir) else [])
                           for m in [re.match(r"^p(\d{3,})\.webp$", f)] if m)
            if not pages:
                self.p(f"deck {did}: no slide images (expected {'.cache' if hidden else 'site'}/slides/{did}/p001.webp ...; run engine/tools/extract.py)")
                continue
            first = int(dk.get("first") or pages[0])
            last = pages[-1]
            missing = [n for n in range(first, last + 1) if n not in set(pages)]
            if missing:
                self.p(f"deck {did}: missing slide images for pages {missing[:10]}{' ...' if len(missing) > 10 else ''}")
            with Image.open(os.path.join(ddir, f"p{first:03d}.webp" if first in pages else f"p{pages[0]:03d}.webp")) as im:
                w, h = im.size
            d = {"short": dk.get("short") or did, "title": dk.get("title") or dk.get("short") or did, "pages": last, "w": w, "h": h}
            if first > 1:
                d["first"] = first
            if hidden:
                d["hidden"] = True
            decks[did] = d
            tp = os.path.join(self.course_dir, "text", did + ".txt")
            if not os.path.exists(tp):
                self.p(f"deck {did}: no slide text (course/text/{did}.txt; run engine/tools/extract.py)")
                continue
            raw = open(tp, encoding="utf-8").read().replace("\r\n", "\n")
            parts = re.split(r"\n?=== " + re.escape(did) + r" page \d+ ===\n", "\n" + raw)[1:]
            if len(parts) != last:
                self.p(f"deck {did}: course/text/{did}.txt has {len(parts)} pages but the slides go up to page {last}")
            if not hidden:      # an unpublished deck's text stays out of the page too (no search hits, no slide links)
                text[did] = [re.sub(r"\s+", " ", x).strip() for x in parts]
        return decks, text

    # ---------- blocks ----------
    def check_blocks(self, bs, where, decks, units, langs):
        for b in bs or []:
            if not isinstance(b, dict) or not any(k in b for k in BLOCK_KEYS):
                self.p(f"{where}: unknown block {json.dumps(b, ensure_ascii=False)[:80]}")
                continue
            if "code" in b and b.get("lang"):
                langs.add(b["lang"])
            if "figure" in b:
                self.check_ref(b["figure"], f"{where} figure", decks)
                if (decks.get((b["figure"] or {}).get("deck")) or {}).get("hidden"):
                    self.p(f"{where}: a figure shows a page of {b['figure']['deck']!r}, a deck with \"publish\": false")
            if "cells" in b:
                cl = b["cells"]
                if not (isinstance(cl, dict) and isinstance(cl.get("blocks"), list)
                        and all(isinstance(bk, dict) and isinstance(bk.get("rows"), list) and all(isinstance(r, list) for r in bk["rows"]) for bk in cl["blocks"])):
                    self.p(f"{where}: cells must be {{\"cols\": n, \"blocks\": [{{\"label\": \"...\", \"rows\": [[...]]}}], \"hl\": [...], \"caption\": \"...\"}}")
            if "grid" in b:
                for n, card in enumerate(b["grid"]):
                    lk = card.get("link")
                    if lk:
                        if "unit" in lk:
                            u = units.get(lk["unit"])
                            if not u:
                                self.ref(f"{where} card {n + 1}: link to unknown unit {lk['unit']!r}")
                            elif lk.get("sec") and not 1 <= int(lk["sec"]) <= len(u["sections"]):
                                self.ref(f"{where} card {n + 1}: {lk['unit']} has no section {lk['sec']}")
                        else:
                            self.check_ref(lk, f"{where} card {n + 1} link", decks)
                    self.check_blocks(card.get("blocks"), f"{where} card {n + 1}", decks, units, langs)

    def check_ref(self, ref, where, decks):
        if not ref or ref.get("deck") not in decks:
            self.ref(f"{where}: bad ref {ref}")
            return
        d = decks[ref["deck"]]
        try:
            ok = d.get("first", 1) <= int(ref.get("page", 0)) <= d["pages"]
        except (TypeError, ValueError):
            ok = False
        if not ok:
            self.ref(f"{where}: bad ref {ref}")

    # ---------- units ----------
    def read_units(self, c, decks, langs):
        units = []
        papers = c.get("papers") or []
        first_paper = papers[0]["id"] if papers and papers[0].get("id") else None
        for uc in c.get("units", []):
            uid = uc.get("id")
            if not uid:
                continue
            path = os.path.join(self.course_dir, "content", uid + ".json")
            if os.path.exists(path):
                cont = self.load(path, f"unit {uid}", default={})
            elif self.stub:
                cont = {"summary": "Content for this unit is still being written."}
            else:
                self.p(f"unit {uid}: no content file (course/content/{uid}.json)")
                continue
            u = {"id": uid, "code": uc.get("code", uid), "title": uc.get("title", uid), "deck": uc.get("deck"), "tutorials": list(uc.get("tutorials") or [])}
            for k in ("summary", "objectives", "sections", "tutorial", "practice", "quiz", "cards"):
                u[k] = cont.get(k, [] if k != "summary" else "")

            def sid(kind, s):
                return uid + ":" + kind + ":" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]
            for q in u["quiz"]:
                q["id"] = sid("q", q.get("q", "") + "|" + (q.get("code") or ""))
            for c2 in u["cards"]:
                c2["id"] = sid("c", c2.get("front", ""))
            for pr in u["practice"]:   # later papers can repeat a question word for word, so their ids include the paper
                pfx = pr["paper"] + "|" + str(pr.get("plabel", "")) + "|" if pr.get("paper") and pr["paper"] != first_paper else ""
                pr["id"] = sid("p", pfx + pr.get("q", "") + "|" + (pr.get("qcode") or ""))
            for kind, arr in (("quiz", u["quiz"]), ("card", u["cards"]), ("practice", u["practice"])):
                ids = [x["id"] for x in arr]
                if len(ids) != len(set(ids)):
                    self.p(f"{uid} {kind}: duplicate ids (same question text twice)")
            units.append(u)
        um = {u["id"]: u for u in units}
        paper_ids = {x.get("id") for x in papers}
        for u in units:
            uid, dk = u["id"], decks.get(u["deck"])
            for i, s in enumerate(u["sections"]):
                if not s.get("title"):
                    self.p(f"{uid} section {i + 1}: no title")
                for pg in s.get("slides", []):
                    if not dk or not dk.get("first", 1) <= pg <= dk["pages"]:
                        self.ref(f"{uid} section {i + 1}: slide {pg} out of range")
                f = s.get("freq")
                if f is not None and (not isinstance(f, (int, float)) or not 0 <= f <= 5):
                    self.p(f"{uid} section {i + 1}: freq must be a number from 0 to 5")
                self.check_blocks(s.get("blocks"), f"{uid} section {i + 1}", decks, um, langs)
            for i, q in enumerate(u["quiz"]):
                self.check_ref(q.get("ref"), f"{uid} quiz {i + 1}", decks)
                if q.get("kind") == "mcq":
                    if not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(q.get("options", [])):
                        self.p(f"{uid} quiz {i + 1}: bad answer index")
                elif q.get("kind") == "tf":
                    if not isinstance(q.get("answer"), bool):
                        self.p(f"{uid} quiz {i + 1}: tf answer not bool")
                else:
                    self.p(f"{uid} quiz {i + 1}: unknown kind {q.get('kind')}")
            for i, c2 in enumerate(u["cards"]):
                self.check_ref(c2.get("ref"), f"{uid} card {i + 1}", decks)
            for i, t in enumerate(u["tutorial"]):
                self.check_ref({"deck": t.get("src"), "page": t.get("page", 0)}, f"{uid} tutorial {i + 1}", decks)
                self.check_blocks(t.get("a"), f"{uid} tutorial {i + 1}", decks, um, langs)
            for i, pr in enumerate(u["practice"]):
                if pr.get("ref"):
                    self.check_ref(pr["ref"], f"{uid} practice {i + 1}", decks)
                if not pr.get("a"):
                    self.p(f"{uid} practice {i + 1}: no model answer")
                if not isinstance(pr.get("marks"), (int, float)):
                    self.p(f"{uid} practice {i + 1}: marks missing")
                if not pr.get("slot"):
                    self.p(f"{uid} practice {i + 1}: slot missing")
                if "answerSource" in pr and pr["answerSource"] not in ("marked", "slides"):
                    self.p(f"{uid} practice {i + 1}: answerSource must be \"marked\" or \"slides\" (or left out), not {pr['answerSource']!r}")
                if pr.get("paper") and pr["paper"] not in paper_ids:
                    self.p(f"{uid} practice {i + 1}: paper {pr['paper']!r} is not in course.json papers")
                if pr.get("sec") is not None and not 1 <= int(pr["sec"]) <= len(u["sections"]):
                    self.ref(f"{uid} practice {i + 1}: sec {pr['sec']} out of range")
                self.check_blocks(pr.get("a"), f"{uid} practice {i + 1}", decks, um, langs)
                self.check_blocks(pr.get("qblocks"), f"{uid} practice {i + 1} question", decks, um, langs)
        return units

    # ---------- shorts and audio ----------
    def read_shorts(self, units):
        sdir = os.path.join(self.site, "shorts")
        mp = os.path.join(sdir, "manifest.json")
        man = self.load(mp, "site/shorts/manifest.json")
        if man is None:
            self.notes.append("shorts are on in course.json but site/shorts/manifest.json does not exist yet")
            return []
        order = {u["id"]: i for i, u in enumerate(units)}
        known_units = {u["id"]: u for u in units}
        scripts = os.path.join(self.course_dir, "shorts", "scripts")
        shorts, used = [], {"manifest.json"}
        for m in sorted(man, key=lambda m: (order.get(m.get("unit"), 99), m.get("id", ""))):
            video, poster = m.get("video") or m["id"] + ".mp4", m.get("poster") or m["id"] + ".jpg"
            music = m["music"] if isinstance(m.get("music"), str) else (m["id"] + ".music.m4a" if m.get("music") else None)
            if not os.path.exists(os.path.join(sdir, video)):
                self.p("short missing video: " + m["id"])
                continue
            if m.get("unit") not in known_units:
                self.p(f"short {m['id']}: unit {m.get('unit')!r} is not in course.json")
            item = {k: m.get(k) for k in ("id", "unit", "title", "caption", "kind", "duration")}
            item["video"], item["poster"] = video, poster
            if music and os.path.exists(os.path.join(sdir, music)):
                item["music"] = music
            used.update(x for x in (video, poster, music) if x)
            sp = os.path.join(scripts, m["id"] + ".json")
            if os.path.exists(sp):
                sc = self.load(sp, "short script " + m["id"], default={})
                item["look"] = sc.get("voice", "")
                item["sections"] = sc.get("sections", [])
                titles = {x["title"] for x in known_units.get(m.get("unit"), {}).get("sections", [])}
                bad = [t for t in item["sections"] if t not in titles]
                if bad:
                    self.ref("short " + m["id"] + " tags unknown sections: " + "; ".join(bad))
                if not item["sections"]:
                    self.p("short " + m["id"] + " has no sections tag")
            shorts.append(item)
        stale = sorted(f for f in os.listdir(sdir) if f not in used and os.path.isfile(os.path.join(sdir, f)))
        if stale:
            self.p("files in site/shorts/ that no short uses (delete them): " + ", ".join(stale))
        return shorts

    def read_audio(self, c, units):
        adir = os.path.join(self.site, "audio")
        man = self.load(os.path.join(adir, "manifest.json"), "site/audio/manifest.json")
        if man is None:
            self.notes.append("audio is on in course.json but site/audio/manifest.json does not exist yet")
            return []
        audio = [m for m in man if not m["id"].startswith("_")]
        for m in audio:
            if not os.path.exists(os.path.join(adir, m["file"])):
                self.p("audio lesson missing its file: " + m["id"])
        ids = {m["id"] for m in audio}
        uids = {u["id"] for u in units}
        for uid, aid in ((c.get("audio") or {}).get("units") or {}).items():
            if uid not in uids:
                self.p(f"course.json audio.units: {uid!r} is not a unit")
            if aid not in ids:
                self.notes.append(f"audio.units maps {uid} to lesson {aid!r}, which is not in site/audio/manifest.json yet")
        return audio

    # ---------- the whole build ----------
    def run(self):
        c = self.read_course()
        if c is None:
            return self.finish(None)
        feat = {"audio": False, "shorts": False, "mockExam": True, "studyPlan": True}
        feat.update(c.get("features") or {})
        os.makedirs(self.site, exist_ok=True)

        # 1. thumbnails (not for the artifact target: the page scales the full images there)
        sroot = os.path.join(self.site, "slides")
        if os.path.isdir(sroot):
            if self.target == "artifact":
                gone = 0
                for d in os.listdir(sroot):
                    t = os.path.join(sroot, d, "t")
                    if os.path.isdir(t):
                        shutil.rmtree(t)
                        gone += 1
                print(f"thumbnails: none for the artifact target{f' ({gone} folders removed)' if gone else ''}")
            else:
                make_thumbs.main(sroot)
        # 2. small posters, only when there are shorts
        if feat["shorts"] and os.path.exists(os.path.join(self.site, "shorts", "manifest.json")):
            make_posters.main(os.path.join(self.site, "shorts"))

        # 3. data
        decks, text = self.read_decks(c)
        langs = set()
        units = self.read_units(c, decks, langs)
        um = {u["id"]: u for u in units}
        content = os.path.join(self.course_dir, "content")
        pages = {}
        for name in ("brief", "revise"):
            doc = self.load(os.path.join(content, name + ".json"), f"course/content/{name}.json")
            if doc is not None:
                if not isinstance(doc, dict) or not isinstance(doc.get("blocks"), list):
                    self.p(f"course/content/{name}.json: needs a blocks list")
                    doc = None
                else:
                    self.check_blocks(doc["blocks"], name, decks, um, langs)
            pages[name] = doc
        gloss = self.load(os.path.join(content, "glossary.json"), "course/content/glossary.json")
        if gloss is not None and not (isinstance(gloss, dict) and all(isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) for x in v) for v in gloss.values())):
            self.p('course/content/glossary.json: must be {"term": ["short meaning", "one-line note"]}')
            gloss = None
        exam = None
        if feat["mockExam"]:
            exam = self.load(os.path.join(self.course_dir, "exam_blueprint.json"), "course/exam_blueprint.json")
            if exam:
                have = {pr["slot"] for u in units for pr in u["practice"] if pr.get("slot")}
                for q in exam.get("questions", []):
                    for part in q.get("parts", []):
                        slots = part["slot"] if isinstance(part["slot"], list) else [part["slot"]]
                        if not any(s in have for s in slots):
                            self.p(f"exam {q.get('title')}: no practice item for slot {slots}")
        shorts = self.read_shorts(units) if feat["shorts"] else []
        audio = self.read_audio(c, units) if feat["audio"] else []

        lang = c["_lang"]
        used = ({lang} | langs) - {"none", "text"}
        for x in sorted(used - set(LANGS)):
            self.p(f"code blocks use lang {x!r}; the page knows {', '.join(LANGS)} and text")
        site, ex = c.get("site") or {}, c.get("exam") or {}
        meta = {"title": site.get("title", ""), "subtitle": site.get("subtitle", ""), "slug": slug(site.get("title", "")),
                "url": site.get("url", ""), "exam": {"name": ex.get("name") or "Exam", "at": ex.get("at", ""), "covers": ex.get("covers", "")},
                "language": lang, "papers": [{"id": x["id"], "name": x["name"]} for x in c.get("papers") or [] if x.get("id")],
                "features": feat, "audioUnits": (c.get("audio") or {}).get("units") or {}, "skills": c.get("skills") or []}
        data = {"course": meta, "units": units, "decks": decks, "text": text, "exam": exam, "shorts": shorts, "audio": audio,
                "brief": pages["brief"], "revise": pages["revise"], "glossary": gloss or {},
                "hl": {k: LANGS[k] for k in sorted(used) if k in LANGS}, "thumbs": self.target != "artifact"}

        tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
        assert "/*DATA*/null" in tpl

        def write(data):
            blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
            page = (tpl.replace("__SITE_TITLE__", html.escape(meta["title"])).replace("__SITE_SUBTITLE__", html.escape(meta["subtitle"]))
                    .replace("/*DATA*/null", blob))
            out = standalone(page)
            open(os.path.join(self.site, "index.html"), "w", encoding="utf-8", newline="\n").write(out)
            return len(out.encode("utf-8"))
        size = write(data)

        # 4. hosting
        if self.target == "artifact":
            dropped = self.publish_plan(decks, audio, shorts, size)
            if dropped:
                if "shorts" in dropped:
                    data["shorts"], feat["shorts"] = [], False
                if "audio" in dropped:
                    data["audio"], feat["audio"] = [], False
                size = write(data)
        else:
            stale = os.path.join(self.site, "publish_plan.json")
            if os.path.exists(stale):
                os.remove(stale)
            if self.target == "github-pages":
                open(os.path.join(self.site, ".nojekyll"), "w").close()
        if size > LIMITS["bytesPerFile"] and self.target == "artifact":
            self.p(f"site/index.html is {size / MB:.1f} MB; an artifact page can be at most 16 MB")

        print(f"wrote site/index.html {size // 1024} KB; {len(units)} units, {len(decks)} decks, {len(data['shorts'])} shorts, {len(data['audio'])} audio lessons; target {self.target}")
        for u in units:
            print(f'{u["code"]:8} sections {len(u["sections"]):3} practice {len(u["practice"]):3} quiz {len(u["quiz"]):3} cards {len(u["cards"]):3} tutorial {len(u["tutorial"]):3}')

        # 5. coverage
        sc = [{"id": s["id"], "unit": s["unit"], "sections": s.get("sections", [])} for s in shorts]
        print(coverage.report(units, sc, exam, os.path.join(self.root, "build"), shorts_on=bool(feat["shorts"])) + " (build/coverage.md)")
        return self.finish(c)

    # ---------- artifact publish plan ----------
    def publish_plan(self, decks, audio, shorts, page_bytes):
        def entry(rel):
            path = os.path.join(self.site, rel.replace("/", os.sep))
            return (rel, os.path.getsize(path)) if os.path.exists(path) else None
        groups = {"slides": [], "audio": [], "shorts": []}
        for did, d in decks.items():
            if d.get("hidden"):
                continue
            for n in range(d.get("first", 1), d["pages"] + 1):
                e = entry(f"slides/{did}/p{n:03d}.webp")
                if e:
                    groups["slides"].append(e)
        for a in audio:
            e = entry("audio/" + a["file"])
            if e:
                groups["audio"].append(e)
        for s in shorts:
            for rel in ["shorts/" + s["video"], "shorts/p/" + make_posters.small_name(s["poster"])] + (["shorts/" + s["music"]] if s.get("music") else []):
                e = entry(rel)
                if e:
                    groups["shorts"].append(e)
        dropped = []
        for drop in ([], ["shorts"], ["shorts", "audio"]):
            dropped = [d for d in drop if groups[d]]
            files = [e for g in ("slides", "audio", "shorts") if g not in drop for e in groups[g]]
            if 1 + len(files) <= LIMITS["filesPerVersion"] and page_bytes + sum(b for _, b in files) <= LIMITS["bytesPerVersion"]:
                break
        else:
            self.p(f"the slides alone do not fit one artifact version ({1 + len(files)} files, "
                   f"{(page_bytes + sum(b for _, b in files)) / MB:.0f} MB; the limits are 511 files and 256 MB)")
        for rel, b in files:
            if b > LIMITS["bytesPerFile"]:
                self.p(f"site/{rel} is {b / MB:.1f} MB; an artifact file can be at most 16 MB")
        batches, cur, cur_b = [], ["index.html"], page_bytes
        for rel, b in files:
            if len(cur) + 1 > LIMITS["filesPerPublish"] or cur_b + b > LIMITS["bytesPerPublish"]:
                batches.append({"files": cur, "bytes": cur_b})
                cur, cur_b = [], 0
            cur.append(rel)
            cur_b += b
        batches.append({"files": cur, "bytes": cur_b})
        total = page_bytes + sum(b for _, b in files)
        plan = {
            "target": "artifact", "page": "index.html", "root": "site", "limits": LIMITS,
            "totals": {"files": 1 + len(files), "bytes": total}, "dropped": dropped,
            "howto": ("First publish: batch 1, with file_path site/index.html, files mapping each other path in batch 1 to site/<path>, "
                      "icon set to one generic word (for example \"book\") and description set to one sentence about the site. The title "
                      "comes from the page's <title>. Every later publish (the other batches, and any rebuild) passes the url the first "
                      "publish returned, with the same file_path and that batch's files, and no icon."),
            "batches": [{"n": i + 1, "count": len(x["files"]), "bytes": x["bytes"], "files": x["files"]} for i, x in enumerate(batches)],
        }
        json.dump(plan, open(os.path.join(self.site, "publish_plan.json"), "w", encoding="utf-8"), indent=1)
        print(f"publish plan: {1 + len(files)} files, {total / MB:.1f} MB in {len(batches)} batch{'es' if len(batches) != 1 else ''} (site/publish_plan.json)")
        for i, x in enumerate(batches):
            print(f"  batch {i + 1}: {len(x['files'])} files, {x['bytes'] / MB:.1f} MB")
        if dropped:
            print("  does not fit with everything: dropped " + " and ".join(dropped) + " from the page and the plan "
                  "(drop order: shorts, then audio). Host on github-pages to keep them.")
        return dropped

    def finish(self, c):
        for n in self.notes:
            print("note: " + n)
        if self.ref_problems:
            print("\n".join(self.ref_problems))
        else:
            print("refs OK")
        allp = self.problems + self.ref_problems
        if allp:
            print(f"\n{len(allp)} problem{'s' if len(allp) != 1 else ''}:")
            for x in allp:
                print("  - " + x)
            return 1
        print("no problems")
        return 0


def main():
    ap = argparse.ArgumentParser(description="Build the study site into site/.")
    ap.add_argument("--root", default=os.path.dirname(HERE), help="the course repo (default: the folder that holds engine/)")
    ap.add_argument("--target", choices=TARGETS, help="overrides course.json hosting.target")
    ap.add_argument("--stub", action="store_true", help="placeholder for units without a content file")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    target = a.target
    if not target:
        try:
            target = (json.load(open(os.path.join(root, "course.json"), encoding="utf-8")).get("hosting") or {}).get("target") or "artifact"
        except (OSError, ValueError):
            target = "artifact"
    if target not in TARGETS:
        print(f"course.json hosting.target {target!r} is not one of {', '.join(TARGETS)}")
        return 1
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    return Build(root, target, a.stub).run()


if __name__ == "__main__":
    sys.exit(main())
