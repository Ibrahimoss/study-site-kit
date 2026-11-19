# Study content: writing spec

You are writing study content for one or more units of a course. A student will use it to revise for an
exam (its name, date and scope are in `course.json`). The content is rendered by an existing web page, so
it must follow the JSON schema below exactly. Paths are relative to the repository root.

## Inputs

- Per-page slide text: `course/text/<deck>.txt`. Each page starts with a marker line `=== <deck> page N ===`.
- Slide images: `site/slides/<deck>/pNNN.webp` (N zero-padded to 3 digits, 1-based, same N as the text
  markers); a deck with `"publish": false` in `course.json` (usually a graded past paper) has them in
  `.cache/slides/<deck>/pNNN.webp` instead. View them whenever a page's text is thin or garbled, or the page is a diagram, table, figure,
  photo or code screenshot: text extraction misses everything inside images. Decks marked "scanned" in
  `site/slides/_manifest.json` (scans and every deck made from photos) have no text at all; read every page image.
- Decks may carry the student's own handwritten notes. They are useful hints but sometimes imprecise. The
  printed slide text is the teacher's wording and is what the exam marks.
- Deck ids, unit ids and which tutorials belong to which unit: `course.json` (`decks`, `units`).

## Output

Write one file per unit: `course/content/<unit>.json` (UTF-8), named by the unit id in `course.json`.
After writing, validate it:
`python -I -c "import json,sys;d=json.load(open(sys.argv[1],encoding='utf-8'));print(len(d['sections']),len(d['quiz']),len(d['cards']),len(d['tutorial']))" <file>`

### Schema

```json
{
  "id": "u3",
  "summary": "2-3 sentences: what this unit teaches and why it matters.",
  "objectives": ["Calculate ...", "Explain why ..."],
  "sections": [
    {
      "title": "Short heading",
      "slides": [12, 13, 14],
      "blocks": [ { "p": "..." }, { "code": "..." } ]
    }
  ],
  "tutorial": [
    {
      "src": "t-u3",
      "page": 1,
      "q": "The question as asked (inline markup allowed)",
      "qcode": "optional code that is part of the question",
      "a": [ { "p": "..." }, { "code": "..." } ]
    }
  ],
  "quiz": [
    { "kind": "mcq", "q": "...", "code": "optional", "options": ["...", "...", "...", "..."],
      "answer": 2, "explain": "...", "ref": { "deck": "u3", "page": 14 } },
    { "kind": "tf", "q": "...", "answer": false, "explain": "...", "ref": { "deck": "u3", "page": 9 } }
  ],
  "practice": [
    { "slot": "u3-calc", "topic": "Short topic name", "marks": 4, "q": "An exam-style question",
      "qcode": "optional code given in the question", "qblocks": [ { "p": "**a.** ... *(2 marks)*" } ],
      "a": [ { "p": "**Full marks needs:**" }, { "list": ["...", "..."] }, { "p": "The full model answer" } ],
      "answerSource": "slides", "ref": { "deck": "u3", "page": 9 } }
  ],
  "cards": [
    { "front": "...", "back": "...", "ref": { "deck": "u3", "page": 5 } }
  ]
}
```

- `sections[].slides`: the pages of the unit's own lecture deck that the section covers.
- `ref` may point at any deck (lecture or tutorial). Every quiz question and card needs a `ref` to the page
  where the answer is taught.
- `practice`: written, exam-style problems with marks and a model answer that starts with what earns full
  marks. `slot` groups interchangeable problems for the random mock paper (`course/exam_blueprint.json`
  picks one problem per slot); use `"extra"` for problems not in the blueprint. Items transcribed from past
  papers carry the extra fields in `specs/PAPER_SPEC.md`. Optional `"examstyle": true` with `"sec"` (1-based
  section) shows the problem under that lesson section. When a section has past-paper questions, it shows
  only those, each badged with its paper and question number, and leaves the written ones to the Practice tab.
- `answerSource` on every practice item: whose answer the model answer is. `"marked"` only when the material
  shows the teacher marked that answer correct (a solved tutorial, an answer key, full marks on a graded
  paper); `"slides"` otherwise (you worked it out from the slides). The page shows a badge for each; an item
  without `answerSource` shows no badge. The build accepts only these two values.
- "Full marks needs" lists the points that earn the marks. Put marks on each point (`(1 mark)`) only when the
  paper or the teacher shows how the marks are split; otherwise list the points without marks.
- `answer` for mcq is the 0-based index of the correct option. The page shuffles the options every time it
  shows a question, so their order in the file does not matter; never write an option that depends on its
  position ("all of the above", "both A and B").
- `code` / `qcode` are raw source strings with `\n` newlines and normal indentation (4 spaces).
- `src` / `page` in tutorial items point at the tutorial page where the question appears.
- Optional on a section: `"freq": 0-5`, how often the topic comes up in exams (0 rare, 5 nearly every
  paper). Set it only from past-paper evidence (count the papers it appears in); without that evidence,
  leave it out. It drives the "How often" badges, the dots in the section index and the study-plan order. A
  section without it is unknown: no badge, no dots, and a neutral place in the plan (not last).
  `"priority": "high"` marks a must-know section.

### Block types (the only ones the page understands)

- `{"p": "text"}` paragraph
- `{"list": ["item", "item"]}` bullet list
- `{"steps": ["first", "second"]}` numbered list. Only for real sequences (an algorithm, a procedure).
- `{"code": "source", "lang": "..."}`. `lang` is optional: without it the block is coloured as the course's
  `code.language` (course.json). Values: `c`, `cuda`, `cpp`, `python`, `java`, `javascript`, `sql`, or
  `text` (no colours: formulas, output, pseudo-code). Quiz `code` and practice `qcode` always use the
  course language. A course with `code.language: "none"` should use `text` for any code block it has.
- `{"table": {"head": ["Col", "Col"], "rows": [["a", "b"], ["c", "d"]]}}`
- `{"defs": [["Term", "Definition"], ["Term", "Definition"]]}` definition list
- `{"tip": "text"}` exam tip or common trap
- `{"note": "text"}` correction or clarification where an annotation or slide is imprecise
- `{"figure": {"deck": "u2", "page": 14, "caption": "What the diagram shows"}}` shows the original slide
  image inline. Use it for diagrams that words cannot replace (architectures, memory layouts, grids of
  blocks, index pictures). Do not overuse: at most about one per section. Never from a deck with
  `"publish": false` (the build rejects it).
- `{"cells": {"cols": 2, "blocks": [ {"label": "Block 0", "rows": [[0, 1, 2], [3, 4, 5]]}, {"label": "Block 1",
  "rows": [[6, 7, 8], [9, 10, 11]]} ], "hl": [4, 10], "caption": "What the figure shows"}}` redraws a figure
  of numbered cells (an array split into blocks, a matrix, a grid of threads) as text. `blocks` is a list of
  small labelled tables, each `rows` a list of rows of values; `cols` is how many blocks sit side by side
  (default 1); every value listed in `hl` is highlighted wherever it appears (values compare as text);
  `label` and `caption` are optional and take inline markup, cell values are shown as plain text. Use it
  when a question needs the student to read cell numbers off a figure.
- `{"heading": "text", "aside": "small note on the right", "id": "optional-anchor", "jump": "short label"}`
  a section heading inside a page. Meant for `brief.json` and `revise.json` (below): when a page has two or
  more top-level headings, each becomes a jump button at the top of the page (labelled `jump`, else the
  heading). Without `id` the anchor is made from the heading's words.
- `{"grid": [ {"title": "Card title", "link": {"unit": "u1", "sec": 3}, "tone": "warn", "blocks": [ ... ]} ]}`
  a grid of cards, each holding its own blocks. `link` is optional: `{"unit", "sec"}` opens that lesson
  section (1-based; leave `sec` out for the unit overview), `{"deck", "page"}` opens a slide. `"tone": "warn"`
  draws the card in red, for traps and warnings. Inside a card, a `code` block with `"lang": "text"` is
  shown as a light formula box instead of a dark code block.

Inline markup inside any text string (p, list items, table cells, q, options, explain, front, back):
`**bold**`, `*italic*`, `` `code` ``. No HTML, no Markdown headings, no links. Math as plain text
(e.g. `v = d / t`, `N/32`, `2^k`).

### Pages besides the units (all optional; leave a file out and its button disappears)

- `course/content/brief.json`, the "Exam brief" page (what the exam usually looks like: its shape, the
  question types that come up most, where marks are lost), and `course/content/revise.json`, the "Final
  revision" page (the whole exam on one page). Both use the same shape:

  ```json
  {
    "title": "What the exam usually looks like",
    "intro": "One or two sentences under the title (inline markup allowed).",
    "scope": "Optional: what is in and out of the exam, shown with a side rule.",
    "blocks": [ { "heading": "The paper", "aside": "25 marks · 60 min" }, { "grid": [ ... ] }, { "table": ... } ]
  }
  ```

  Any block type above works in `blocks`; `heading` and `grid` are the usual skeleton. Card links and
  figures are checked by the build like every other reference.
- `course/content/glossary.json`: `{"term": ["short meaning", "one-line note"]}`, for the terms and
  symbols a student meets in formulas or code (`P(A | B)`, `σ`, `pH`, `malloc`). Wherever a term appears in
  an inline `` `code` `` span, as the whole span or as a whole word inside a longer one (`` `P(A | B) =
  P(A ∩ B) / P(B)` ``), it shows the meaning on hover, focus or tap. Matching is case-sensitive and by whole
  words, so write each term exactly as the lessons do; put formulas and symbols in `` `code` `` spans for
  them to be found. A trailing `()` on a whole span is ignored.
- Practice triage (the "Time I have" bar on the Practice tab) picks one problem per skill. By default each
  distinct `topic` is a skill; `course.json` may group topics with `"skills": [["regex", "Skill name"], ...]`
  (case-insensitive, first match wins).

## How much to write

- Sections: cover every slide that has real content (skip the title page and empty pages). About one
  section per 2-5 slides. Explain each idea properly in your own words, the way a good TA would before an
  exam. Keep the instructor's definitions and lists recognisable, because the exam expects them. Include
  the full code from the slides (cleaned up, compilable-looking) and walk through it.
- Quiz: about one question per 2 to 3 content slides, up to 25 per unit. The source wins over any count:
  a short deck gets few questions; never pad with trivia or repeats. Roughly 70% mcq with 4
  options and 30% tf. Where the course has code or calculations, include questions that make the student
  work them out (what this code prints, what this formula gives, spot the bug). Distractors
  must be plausible mistakes a student would really make. `explain` says why the right answer is right
  and, when useful, why the tempting wrong one is wrong.
- Cards: about one per content slide, up to 30 per unit; again the source wins, never pad. Definitions, comparisons, formulas, function signatures, formulas, "what is X
  used for". Front is a short prompt; back is a crisp answer (1-3 sentences or a short formula/code).
- Tutorial: every question in the matching tutorial PDFs, with the worked solution given there, cleaned up
  and explained. If the given solution has a mistake, fix it and add a `note` block saying what changed.

## Style

Plain, direct English. Short sentences. Name things the way the course does. No filler, no emoji, no
"Great question". Facts must be correct: if the slides use an outdated value, keep the course's number (it is what the
exam marks) and add a short note with the current value only where it matters.
Do not invent content outside the course scope, but you may add a clarifying sentence or a small worked
example when it helps understanding.

Return a short report: the files you wrote, the counts (sections / quiz / cards / tutorial), and anything
on the slides you could not read or were unsure about.

## The random mock paper (optional)

`course/exam_blueprint.json` gives the shape of a paper; each part names one or more practice slots and
the page draws one practice problem from them every time a new paper is made:

```json
{ "title": "Mock exam", "questions": [
  { "title": "Question 1", "parts": [ { "slot": ["u1-defs", "u1-compare"], "maxMarks": 4 }, { "slot": "u1-calc", "maxMarks": 4 } ] } ] }
```

`title` is shown above every random paper. Every slot named here needs at least one practice item; the build checks it.

## Charts page (optional)

`course/content/charts.json` adds a "Charts" button (its label is `title`) and a page that shows chosen
slides together, for example every state machine and flowchart:
`{"title": "...", "intro": "...", "groups": [{"title": "...", "note": "...", "items": [{"deck": "t3-4", "page": 17, "title": "...", "note": "..."}]}]}`.
Each item shows the slide large, opens full screen when tapped, and links to the lesson section that covers it.
The build checks every deck and page.
