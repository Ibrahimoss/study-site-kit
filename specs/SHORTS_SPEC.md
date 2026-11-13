# Short videos: script format

The site has a TikTok-style **Shorts** feed: vertical videos (720x1280) with a synthetic narrator, animated
visuals and burned-in captions, over Minecraft parkour gameplay or a drawn background. Each short teaches ONE
exam-relevant point or asks ONE exam-style question. You write the scripts (JSON); `shorts/render.py` turns them
into video. How to write them well is in `specs/SHORTS_STYLE.md`; this file is the format.

Paths are relative to the course folder (the repository root, or the folder given with `--root`).

- Scripts: `course/shorts/scripts/<id>.json`, one short per file, the file name matching `id`.
- Source of truth: the unit's lesson (`course/content/<unit>.json`: sections, practice with model answers, quiz,
  cards) and its slides (`course/text/<deck>.txt`, images in `site/slides/<deck>/pNNN.webp`). Write shorts after
  the lessons are written and verified.
- Rendered files: `site/shorts/<id>-<hash>.mp4`, `.jpg` (poster), `.music.m4a` and `site/shorts/manifest.json`.

**Never say where a question comes from** (no "this was asked", no years, no papers); just teach it.

## Short format

```json
{
  "id": "u1-mean-vs-median",
  "unit": "u1",
  "kind": "question",
  "size": "standard",
  "title": "Mean or median?",
  "caption": "One extreme value moves the mean but not the median.",
  "sections": ["Measures of centre"],
  "voice": "bf_emma",
  "bg": "gameplay",
  "scenes": [ ... ]
}
```

| field | meaning |
|---|---|
| `id` | `<unit>-<slug>`: lowercase letters, digits and dashes; the same as the file name |
| `unit` | a unit id from `course.json` |
| `kind` | `"question"` (has a quiz scene) or `"explain"` (has none) |
| `size` | `"micro"`, `"standard"` (default) or `"deep"`; sets the scene count and the length (SHORTS_STYLE) |
| `title` | 1 to 40 characters, shown on the video and in the feed |
| `caption` | at most 120 characters, shown under the video in the feed |
| `sections` | titles of the unit's lesson sections this short covers, spelled exactly as in `course/content/<unit>.json`. Required: the site shows the short under those sections and counts it in the coverage report, and the build fails on a short with no tag or an unknown title |
| `voice` | optional Kokoro voice; default `shorts.voice` in `course.json`, then `audio.voice`, then `af_heart`. Alternate voices between neighbouring shorts |
| `theme` | optional: the narrator's second color scheme (below) |
| `bg` | optional `"gameplay"` or `"drawn"`: overrides `shorts.background` in `course.json` for this short |

### Voices and looks

Each voice comes with two color schemes; the first is used unless `theme` names the second:

| voice | narrator | schemes |
|---|---|---|
| `af_heart` | American, female | `ember`, `sunset` |
| `af_bella` | American, female | `ocean`, `aurora` |
| `am_michael` | American, male | `circuit`, `terminal` |
| `am_fenrir` | American, male | `neon`, `space` |
| `am_puck` | American, male | `blueprint`, `pop` |
| `bf_emma` | British, female | `paper`, `chalkboard` |

Other Kokoro voices (`bm_george`, ...) work too and get the `circuit` scheme. Over gameplay footage the light
schemes (`paper`, `pop`) are swapped for the narrator's dark one so the text stays readable.

### Backgrounds

By default a short plays over Minecraft parkour gameplay: `shorts.backgroundFile` in `course.json` (default
`shorts/backgrounds/minecraft-parkour.mp4`; it may also name a folder of videos). Each short plays its own
stretch, dimmed under the text; the footage's own sound is never used. If the file is missing, or `bg` (or
`shorts.background`) is `"drawn"`, the short gets the scheme's drawn, animated background instead, and the
renderer prints one line saying so. The kit ships no video; see `shorts/backgrounds/README.md`.

## Scenes

A `hook` first (a micro short may open on a `quiz` instead), a `card` last. Every scene has `say`.
Optional on any scene: `"hold"`, the pause in seconds after its last line (default 0.12).

### Narration (`say`)

`say` is a string, or a list of strings for scenes that reveal things step by step (one line per step). Each
line is narrated and also becomes the captions. `shorts/checks/check.py` enforces these:

- At most 14 words per line; aim for 4 to 12.
- **No digits or symbols**: write numbers and operators as words ("one half", "twenty percent", "x squared").
  Digits, brackets, slashes, `=`, `+`, `%`, `_`, `^`, `:` and backticks are refused in narration.
- `**word**` highlights caption words in the accent color; at most two highlights per line.
- No filler openers ("So", "Now", "Basically", "Let's take a look", "As we can see"), no "i.e." or "e.g.".
- Never name syntax ("comma", "brackets", "semicolon", "underscore"): say what the code does instead.
- Never hint where a question came from ("past paper", "was asked", "last year", a year).

### Pronunciation

The narrator reads each line with the kit's word list (`shorts/pronunciations.json`) merged with the course's
own `course/pronunciations.json` (the course wins):

- `"spell": {"text": "how to say it"}`: a plain respelling, matched exactly (`{"NaCl": "sodium chloride"}`).
- `"words": {"WORD": {"us": "...", "gb": "..."}}`: exact sounds in Kokoro phonemes, for words a respelling
  cannot fix; `us` for the American voices, `gb` for the British ones. Matched as whole words, ignoring case.
- Any other word of two or more capitals is read **letter by letter** automatically ("DNA", plural "DNAs").
  That is right for most acronyms; list the ones said as a word (NASA, LASER) in `course/pronunciations.json`.
  `render.py tts` and `check.py` print every word that will be spelled out.

See `shorts/pronunciations.example.json` for the shape.

### Scene types

Text shown on screen may use inline `` `code` `` and `**bold**` (accent color), and may contain digits and
symbols.

- `hook`: `text` (the big line, at most 10 words), optional `kicker` (a short tag, e.g. "Quick question"),
  optional `sub` (a smaller line), `say`.
- `bullets`: `title`, `items` (2 to 5 items, at most 6 words each), `say` (a list; line i reveals item i;
  `"offset": n` lets the first n lines play before item 1 appears).
- `formula`: `title`, optional `given` (a boxed problem statement), `lines` (revealed one per `say` line after
  `offset`; the last line is boxed as the result unless `"box": false`), `say`.
- `code`: `title`, `code` (a multi-line string, at most 14 lines of at most 46 characters), `say`, and optional
  lists with one entry per `say` line: `hl` (1-based line numbers to highlight), `show` (how many lines are
  visible), `notes` (a sentence under the code). Colored as the course's `code.language`.
- `cells`: `title`, `cells` (`{"cols": 2, "blocks": [{"label": "Outcomes", "rows": [["HH", "HT"], ["TH", "TT"]]}],
  "caption": "..."}`; at most 8 cells per row), `say`, optional per-line `hl` (cell texts to highlight) and
  `notes`.
- `tree`: `title`, `tree` (nested `["op", left, right]` with string leaves, e.g.
  `["+", ["*", "2", "x"], ["/", "y", "3"]]`), `say`, optional per-line `steps` (the depth being evaluated,
  deepest first, root depth 0, `null` for none) and `notes`.
- `quiz`: `q`, optional `code`, `options` (exactly 4 short options), `answer` (0 to 3), optional `think`
  (seconds of silent countdown, default 2), optional `notes` (one per reveal line), `say` (at least two lines:
  line 1 asks and ends with "Pause and pick one."; line 2 starts with the right letter, "B." or "Answer B.",
  then names the option's content and says why).
- `compare`: `title`, `heads` (2 column titles), `rows` (a list of `[left, right]`, revealed one per `say` line
  after `offset`), `say`.
- `card`: `text` (the takeaway, at most 14 words), optional `kicker` ("Remember", "Answer", "Common mistake";
  default "Answer"), optional `sub`, optional `"tone": "warn"` (accent color instead of green, for traps), `say`.

## Example

```json
{
  "id": "u1-mean-vs-median", "unit": "u1", "kind": "question", "size": "standard",
  "title": "Mean or median?", "caption": "One extreme value moves the mean but not the median.",
  "sections": ["Measures of centre"], "voice": "bf_emma",
  "scenes": [
    {"type": "hook", "kicker": "Quick question", "text": "One huge value. Which average moves?",
     "say": "One huge value joins the data. Which average moves?"},
    {"type": "formula", "title": "Five salaries", "given": "`2, 3, 3, 4, 40`",
     "lines": ["mean = 52 / 5 = **10.4**", "median = **3**"],
     "say": ["The mean adds them up and divides by five. Ten point four.", "The median is the middle value. **Three**."]},
    {"type": "quiz", "q": "Which average describes a typical salary here?",
     "options": ["The mean", "The median", "Both equally", "Neither"], "answer": 1,
     "say": ["Which one describes a typical salary? Pause and pick one.",
             "B. The **median**, because one extreme value drags the mean up."]},
    {"type": "card", "kicker": "Remember", "text": "Skewed data: report the **median**.",
     "say": "Skewed data? Report the median."}
  ]
}
```

## Making and checking

Every command takes `--root <course folder>` when the course is not the repository root.

1. `python -I shorts/checks/check.py [ids...] [--lines]`: the format, the narration rules and the estimated
   length. `--lines` lists every narration line with its word count. Fix everything it reports.
2. `python -I shorts/render.py tts [ids...]`: narrates the lines (cached in `.cache/tts/`, so only changed
   lines are narrated again).
3. `python -I shorts/render.py sheet <id>`: prints the real duration and any `WARNING` lines (text too wide, or
   running into the captions), and writes `.cache/shorts/frames/<id>_sheet.jpg`, one still per narration line.
   Look at the sheet. Fix anything that overflows, overlaps, is clipped or is too small to read, and any length
   outside the size's range; run it again until clean.
   `python -I shorts/render.py frames <id> <seconds> ...` saves single frames for a closer look.
4. `python -I shorts/render.py video [ids...]`: renders the videos into `site/shorts/` and updates the
   manifest. `python -I shorts/render.py audio [ids...]` rebuilds only the sound of rendered shorts.
5. Run `check.py` once more (it now also checks the rendered files and the real lengths), then rebuild the site.

Narration runs with Kokoro on this computer (`"engine": "kokoro-local"`) or on a voice PC (`"kokoro-ssh"`, see
`shorts/homepc/README.md`); rendering needs ffmpeg.

## Accuracy

Every fact, formula and number must match the course content. Recompute every number (a quick Python check)
and test every formula on at least two cases of your figure. Quiz distractors must be clearly wrong, with
exactly one right answer.

Report: the ids you wrote with their durations, and anything you were unsure of.
