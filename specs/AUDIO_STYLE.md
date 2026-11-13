# Spoken lessons: writing guide

You are writing the script of an audio lesson a student listens to with no screen (walking, on a bus). It is read
by a synthetic voice (Kokoro; the voice is `audio.voice` in `course.json`, by default `af_heart`, an American
female narrator), so write for the ear.

Paths are relative to the course folder (the repository root, or the folder given with `--root`).

## Content

- Source of truth: the unit's slides (`course/text/<deck>.txt`, tutorials in the text files of their decks, page
  images in `site/slides/<deck>/pNNN.webp` when a page is a figure) and the unit's lesson
  (`course/content/<unit>.json`: sections, practice, quiz, cards). Teach what the slides teach, including the
  definitions the exam expects word for word, and the corrections the lesson makes to slide errors. Add nothing
  beyond the slides except what is needed to understand.
- Cover the unit in the order of its lesson sections. Every section gets its own heading.
- After each section's explanation, add one short paragraph starting "What you need to know:" with the facts,
  definitions, comparisons or rules the exam asks for, said plainly (two to five points, spoken as sentences, not
  a list).
- End with a section "## Recap" listing the must-knows of the whole unit in under 200 words.
- Never say or imply the material comes from past exams, and never name the course code, school or teacher.

## For the ear

- Never refer to anything visual: no "as you can see", "in this figure", "the table below", "on the slide",
  "look at". Describe diagrams and tables in words: "Picture a tree. The first branch splits into heads and
  tails..."
- Never read code or symbols literally. Explain what code does the way a lecturer would. Say formulas in words:
  "the probability of A given B is the probability of both, divided by the probability of B".
- Numbers as people say them: "five hundred twelve", "two to the power ten", "zero point two five". No
  coordinates or fractions read as pairs of digits.
- Short sentences, mostly under 22 words. One idea per sentence. Signpost: "There are three rules. First...".
- No markdown emphasis, no bullet lists, no tables, no em dashes, no brackets, no slashes, no ampersands. Use
  commas and full stops. Paragraphs of 2 to 6 sentences.

## Words the voice must say right

- Acronyms: write them in capitals as usual. Any word of two or more capitals is read letter by letter
  automatically ("DNA" is "dee en ay"), plural included ("DNAs").
- A word said as a word (NASA, LASER, SQL said "sequel"), a symbol-heavy term, or a name the voice gets wrong goes
  in `course/pronunciations.json`: `"spell": {"pH": "p h"}` for a plain respelling, or `"words"` with exact Kokoro
  phonemes. The kit already handles a few common ones (`shorts/pronunciations.json`); the course file wins over
  it. See `shorts/pronunciations.example.json`.
- `narrate.py` prints the capital words it is about to spell out; check that list before a long run.

## Format

A Markdown file `course/audio/scripts/<id>.md`: first line `# <Unit code>: <title>` (for example
`# U2: Conditional probability`; the colon is read as a full stop), then `## <Section title>` headings, then
plain paragraphs separated by blank lines. Nothing else (no front matter, no lists). Each paragraph is narrated as
one clip, so editing one paragraph only narrates that paragraph again. Length: about 145 spoken words per minute;
aim for 8 to 15 minutes per unit unless told otherwise.

## Making it

1. Map each unit to its lesson in `course.json`: `"audio": {"units": {"u1": "u1"}}` (unit id to script id), so
   the unit page shows its Listen button. Turn on `features.audio`.
2. `python -I audio/narrate.py [--root <course folder>] [ids...]` narrates every script (or the ids given) into
   `site/audio/<id>-<hash>.mp3` and `site/audio/manifest.json`, with a chapter mark per section. It needs ffmpeg
   and Kokoro (`audio/requirements.txt`), or a voice PC (`"engine": "kokoro-ssh"`, see `shorts/homepc/README.md`).
3. When Whisper is installed, every paragraph is listened back and the ones it heard differently are printed.
   Fix the spelling or add a pronunciation for each, and narrate again.
4. Rebuild the site.
