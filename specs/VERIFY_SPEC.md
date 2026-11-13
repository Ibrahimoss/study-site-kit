# Verification pass for the study content

Another writer produced study content for a course's exam. Your job is to be the
skeptical second reader. A wrong answer key or a wrong flashcard teaches the student the wrong thing,
so check each item against the source, not against your memory of what the writer probably meant.

Paths are relative to the repository root.

- Schema and block types: `specs/CONTENT_SPEC.md` (read it first).
- Content to verify: `course/content/<unit>.json`.
- Sources: per-page slide text `course/text/<deck>.txt` (markers `=== <deck> page N ===`) and slide images
  `site/slides/<deck>/pNNN.webp` (`.cache/slides/<deck>/pNNN.webp` for a deck with `"publish": false`; view
  them when text is thin or the page is a figure).
  The decks include the student's own annotations; the printed instructor text is the authority for what
  the exam marks, and established facts of the field are the authority when an annotation is wrong.

## What to check

1. Every quiz item:
   - The keyed answer is correct according to the slides.
   - No other option is also defensibly correct. If two options are both right, rewrite the weaker
     distractor so it is clearly wrong.
   - For code questions, trace the code by hand. Recompute every number, index and count yourself.
   - The `explain` text agrees with the key, and `ref` points at a page that actually teaches the answer.
   - True/false statements are unambiguous.
2. Every flashcard: the back is correct and answers the front; `ref` page is relevant.
3. Every tutorial item: the solution is correct (recompute numbers, check code compiles in principle and
   produces the right result, check formulas on a concrete case).
4. Practice items: the model answer is right and complete for the marks, `answerSource` is `"marked"` only
   where the material shows the teacher marked it correct (`specs/CONTENT_SPEC.md`, `specs/PAPER_SPEC.md`),
   and "Full marks needs" gives per-point marks only where the paper or teacher shows them.
5. Sections: `freq` only where past papers back it up; remove it otherwise.
6. Lesson sections: read them for factual errors, wrong formulas, wrong code, or claims that contradict
   the slides. Do not rewrite for style.

## How to fix

- Fix confirmed errors directly in the JSON, keeping the schema. Keep the writer's style. Do not rewrite
  things that are correct.
- After editing, validate:
  `python -I -c "import json,sys;d=json.load(open(sys.argv[1],encoding='utf-8'));print(len(d['sections']),len(d['quiz']),len(d['cards']),len(d['tutorial']))" <file>`
- Do not reorder or delete quiz items or cards (their positions are used as ids). Rewrite in place.

## Report

A list of every change: unit, item (e.g. `quiz 7`, `card 12`, `tutorial 2`, `section 4`), what was wrong,
what you changed. Then anything you suspect but could not confirm. Keep it short.
