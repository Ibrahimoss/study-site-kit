# Past papers into mock papers

Each past paper becomes a fixed mock paper: every part in its original order, with its own question numbers, and a model answer for each part.

## The paper is a deck

Each past paper is a deck in `course.json` `decks`, with its own id (`paper-a`, `paper-b`, ...), extracted like any other deck. List it in `decks` only, never in a unit's `tutorials`.

**Privacy.** Graded scans show a student's handwriting and possibly names. By default give every paper deck `"publish": false`: its page images go to `.cache/slides/<deck>/` (read them there), the site ships none of them, and no slide link points at the paper. Set it to `true` only if the person asks and the pages show no names.

## Reading the papers

Papers are often phone photos or scans of graded answer sheets: the printed questions, the student's handwriting, and the grader's marks (points per part, ticks, crosses, strike-throughs). Render the pages at a readable size and zoom into crops where the handwriting is small. Ignore stickers, doodles and notes the student added for themselves.

The same paper often appears more than once (a compiled PDF plus separate files). Transcribe each distinct paper once, picking the copy with the clearest grading.

Leave out questions on topics the slides do not cover (older syllabus), and say so in the brief.

## One practice item per part

Add each part to the `practice` array of the unit it belongs to, with these extra fields:

| field | meaning |
|---|---|
| `paper` | paper id, matching `course.json` `papers` (`"A"`, `"B"`, ...) |
| `slot` | `"paper-<id in lower case>"` |
| `pq`, `pp`, `plabel` | question number, part order within it, printed label (`"3.1 a.ii"`); leave `plabel` empty (`""`) for a question with only one part |
| `examstyle` | `true` |
| `sec` | 1-based index of the most relevant lesson section in that unit |
| `marks` | the marks printed for the part; estimate from the grader's numbers and the paper total only when none are printed |
| `answerSource` | `"marked"` or `"slides"` (below; the same field every practice item carries, CONTENT_SPEC) |

`q` is the question text, faithfully transcribed (markdown allowed); `qcode` holds code given in the question; `qblocks` holds tables and figures (use `cells` grids for numbered-cell figures). Leave out the cover sheet, the student's details, and anything that identifies the school or teacher unless the person wants it.

Multiple-choice questions become clickable on the site: put the options in `qblocks` as one list, each item starting with its letter (`"A. ..."`, `"b) ..."`), and start the model answer's key line with `Answer: C` (or `**C. ...**`). The build turns these into `choices` and `choice` (0-based index of the right option); you can also set those two fields yourself.

The model answer `a` starts with a `**Full marks needs:**` paragraph and a list of the points that earn the marks, then the full answer. Give marks per point only when the paper or the teacher shows them (the grader's numbers beside each point, a marking scheme); otherwise list the points without marks.

`ref` is optional: point it at the slide that teaches the answer. A ref to the paper's own page is allowed, but the page shows no link to a deck with `"publish": false`.

## Who says the answer is right

- `"marked"` only when the material shows the teacher counted that answer as fully correct: full marks for the part, a clean tick with no deductions, an official answer key, or a solved tutorial. The model answer is then that answer, cleanly written up (fix spelling, keep its content and method).
- `"slides"` everywhere else: write the correct answer from the slides. Never present a part-mark or crossed-out answer as correct. Partial marks can show you what was wrong.
- If a full-marks answer is plainly wrong when you check it (a formula that fails on the figure), use `"slides"` with the correct answer and a one-line note.

The site shows a badge on every answer saying which kind it is.

## Arithmetic

Do numeric parts step by step and check them twice: results that must match a figure (an index formula against the numbered cells) must be checked against two or three cells of that figure.
