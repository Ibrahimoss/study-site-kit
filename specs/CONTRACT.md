# Internal contract (for whoever works on the kit)

This is how the pieces of the kit talk to each other. The playbook (CLAUDE.md) and the README are written from it.

## Layout of a course built with the kit

```
course.json                      the course config (below); the only file that names the subject
materials/                       what the person downloaded: any folder structure, PDFs, PPTX, photos (git-ignored)
course/                          everything the AI writes for this course (committed in the person's own copy)
  text/<deck>.txt                slide text, "=== <deck> page N ===" separators (made by engine/tools/extract.py)
  content/<unit>.json            one per unit: summary, objectives, sections, tutorial, practice, quiz, cards (CONTENT_SPEC)
  content/brief.json             optional: the "what the exam looks like" page, as blocks
  content/revise.json            optional: the one-page final revision, as blocks
  content/glossary.json          optional: {"term": ["short meaning", "one-line note"]}, shown on hover where a term appears in a code span
  exam_blueprint.json            optional: random-paper layout (questions -> parts -> practice slots)
  audio/scripts/<id>.md          optional: spoken lesson scripts (AUDIO_STYLE)
  shorts/scripts/<id>.json       optional: short scripts (SHORTS_SPEC)
  pronunciations.json            optional: course words the voices must say right (merged over the kit's defaults)
site/                            build output, served as it is (git-ignored in the kit, committed or published by the person)
  index.html                     the whole app, data inlined
  slides/<deck>/pNNN.webp        slide images (and t/pNNN.webp thumbnails unless the target is "artifact"); none for a deck with "publish": false
  slides/<deck>.N.js             artifact target only: slide packs, the deck's page images as data URIs, each file under 8 MB
  slides/_manifest.json          what extract.py read: pages, size, scanned, publish per deck
  audio/<id>-<hash>.mp3, audio/manifest.json
  shorts/<id>-<hash>.mp4 / .jpg, shorts/p/*.jpg, shorts/manifest.json
shorts/backgrounds/              background clips for shorts (git-ignored); default style: Minecraft parkour gameplay
build/coverage.md, coverage.csv  the coverage report every build writes: where quiz items, cards (and shorts) are thin (git-ignored)
.cache/                          working files (git-ignored): img/<deck>.pdf made from photos, pdf/ made from office files,
  slides/<deck>/pNNN.webp        and the page images of decks with "publish": false (read by the AI, never shipped)
```

Paths are always relative to the repo root. Nothing outside the repo is read, except the optional remote voice PC.

## course.json

```json
{
  "site":   { "title": "Biology Midterm Lab", "subtitle": "BIO 101", "url": "" },
  "exam":   { "name": "Midterm", "at": "2027-03-14T10:00:00+03:00", "covers": "Units 1 to 4" },
  "code":   { "language": "none" },
  "decks":  [ { "id": "u1", "file": "materials/Unit 1 - Cells.pdf", "short": "Unit 1 slides", "title": "Unit 1 - Cells", "first": 2 },
              { "id": "paper-a", "file": "materials/Spring 2026 midterm", "short": "Spring 2026 paper", "title": "Spring 2026 midterm (graded)", "publish": false } ],
  "units":  [ { "id": "u1", "code": "U1", "title": "Cells", "deck": "u1", "tutorials": [] } ],
  "papers": [ { "id": "A", "name": "Spring 2026" } ],
  "features": { "audio": false, "shorts": false, "mockExam": true, "studyPlan": true },
  "audio":  { "engine": "kokoro-local", "voice": "af_heart", "speed": 0.96, "units": { "u1": "u1" } },
  "shorts": { "engine": "kokoro-local", "background": "gameplay", "backgroundFile": "shorts/backgrounds/minecraft-parkour.mp4" },
  "voicePC": { "host": "", "key": "" },
  "hosting": { "target": "artifact" }
}
```

- `code.language`: `none`, `c`, `cuda`, `cpp`, `python`, `java`, `javascript`, `sql`. Drives code highlighting; `none` hides code-specific UI.
- `decks[].file`: a PDF, a PowerPoint or Word file (needs LibreOffice), one photo (JPG, PNG, HEIC with `pillow-heif`), or a folder of photos (one page each, sorted by name). Photos are combined into a PDF in `.cache/img/` and treated as scanned.
- `decks[].first`: first page to show (skips a title slide). `units[].deck` names the unit's own deck; `tutorials` lists extra deck ids.
- Past papers are decks too: each has its own deck id and is listed in `decks`, never in a unit's `tutorials`. Their parts become practice items (PAPER_SPEC).
- `decks[].publish` (default `true`): `false` keeps the deck private. Graded scans show a student's handwriting and possibly names, so past-paper decks default to `false`. extract.py writes its page images to `.cache/slides/<deck>/` (the AI reads them there); the build leaves them out of `site/`, the page data (no text, no search hits) and the publish plan, and the page shows no slide link to it. A unit's own deck or tutorial cannot be unpublished, and no `figure` may show one of its pages.
- `papers`: display names of fixed mock papers; practice items carry `"paper": "<id>"` (see PAPER_SPEC). Order here is the button order.
- `audio.units`: unit id -> audio lesson id, so a unit page shows its Listen button.
- `audio.engine` / `shorts.engine`: `kokoro-local` (this computer, GPU if present, else CPU) or `kokoro-ssh` (the `voicePC`, set up with shorts/homepc/setup.ps1).
- `hosting.target`: `artifact` (default: a Claude Artifact page), `github-pages`, or `file`.

## Build

`python -I engine/build.py [--target artifact|github-pages|file]` (bash wrapper: `engine/build_site.sh`)
1. Reads course.json and course/.
2. Thumbnails, posters, the data blob, index.html, the coverage report (`build/`), and every check.
3. Prints `refs OK` and `no problems`, or the list of problems, and exits non-zero on problems.

Target `artifact`: no thumbnail folder (the page scales the full images), slide packs instead of one file per page (each published deck's pages go into `site/slides/<deck>.N.js`, scripts that set `window.__SLIDES__[deck][page]` to a `data:image/webp` URI, each under 8 MB, so a big deck splits; the page loads a pack only when a view shows one of its pages; the loose `pNNN.webp` files stay on disk but are not in the plan), and a `site/publish_plan.json` grouping the files into publish batches within the Artifact limits (255 files and 64 MB per publish, 511 files and 256 MB per version, 16 MB per file). If the course does not fit, the plan says what to drop first (shorts, then audio) and the build prints it. Its `howto`: the first publish passes `file_path` site/index.html, batch 1 in `files`, an `icon` (one generic word, such as `book`) and a one-sentence `description`; the title comes from the page `<title>`; every later publish passes the `url` the first one returned.
