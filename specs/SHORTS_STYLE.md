# Short videos: writing style

The format is in `specs/SHORTS_SPEC.md`; this file is how to make a short worth watching. A short is watched on
a phone, often with half attention, scrolling past anything slow. It has to hook in the first two seconds, teach
one thing, and end on a line the student remembers.

## Sizes

Every script has `"size"`. The size sets the length and the number of scenes, and `shorts/checks/check.py`
enforces both (estimated from the text, then measured once narrated):

| size | length | scenes | use it for |
|---|---|---|---|
| `micro` | 7-17 s | 2-4 | one formula, one rule, one trap, one quick quiz. About 20-35 spoken words. |
| `standard` | 16-34 s | 3-6 | a concept with one worked example. About 45-75 words. |
| `deep` | 32-58 s | 4-8 | a step-by-step derivation, a full worked problem, a code walkthrough. About 80-125 words. |

Pick the size from how big the idea is, not to fill time. A micro short still has a hook and ends on a card; it
may open straight on a quiz scene. If a short runs long, cut words, not content; if the idea needs more, split it
into two shorts.

## Pace

- Lines of 4 to 12 words (never more than 14). One idea per line.
- A new visual beat every 2 to 4 seconds: the next bullet, the next formula line, a highlighted cell or code
  line, the next row of a comparison. In deep shorts every line should reveal or highlight something.
- The hook is a question or a bold claim the student wants answered: "Why is the median safer here?",
  "This answer loses half the marks." Never a greeting or a topic announcement.
- The last card is the takeaway in at most 14 words, the line they should still remember in the exam.

## For the ear

- Spoken, conversational sentences: "Here's the trick." "Pause and try it." Contractions are fine.
- Numbers and symbols as words in `say` ("three quarters", "p of A given B", "x squared"); the digits and
  symbols belong on screen.
- Never read code or notation character by character. Describe it: "the sum of every value times its
  probability", not "sigma x p of x".
- Words the voice must say a special way go in `course/pronunciations.json` (SHORTS_SPEC, Pronunciation).
  Acronyms in capitals are spelled out letter by letter on their own.

## Topics

Draw from the unit's lesson (`course/content/<unit>.json`), in this order of value:

- **Traps**: the mistakes the lesson's `tip` and `note` blocks warn about, and the tempting wrong options in the
  quiz.
- **Formulas**: what each symbol means, when to use it, one quick worked number.
- **Worked problems**: a practice problem cut down to its key step; ask for the answer in a quiz scene.
- **Comparisons**: two ideas students mix up, side by side in a `compare` scene.
- **Definitions** the exam expects word for word, with one example that makes them stick.
- **Code** (only for courses with code): what a snippet prints, spot the bug, fill the missing line.

Do not repeat a topic that already has a short (see the titles in `course/shorts/scripts/*.json`); a harder or
different angle on the same section is fine. Spread shorts over the units in proportion to the exam weight.
Tag every short with the lesson `sections` it covers.

## On screen

- Bullets: at most 6 words each. Formulas and code in backticks.
- Code: at most 46 characters per line and 14 lines; use `show` to reveal it step by step.
- Keep the bottom of each scene clear of the captions: the `sheet` command prints `WARNING` lines when content
  runs too low or too wide.

## Accuracy

Every fact must be in the content files, and every number recomputed. A wrong short is worse than no short.
