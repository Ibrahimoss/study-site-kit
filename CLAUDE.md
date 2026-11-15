# Study Site Kit: playbook for the AI

You are helping a person turn their course material into a complete study site: lessons for every chapter, the slides, practice questions with model answers, quizzes, flashcards, a mock exam, a study plan with a countdown, a one-page revision, and optionally audio lessons and short narrated videos.

**Assume the person is not technical.** Use plain words, one step at a time, and never ask them to edit code or JSON. You do all the technical work. When you need something from them (a file, a date, a yes), ask for exactly that and wait.

Read `specs/CONTRACT.md` before you start: it says where every file goes and what `course.json` holds. The other files in `specs/` tell you how to write each kind of content. Follow them.

## Ground rules

- **Never invent course content.** Every fact, definition, formula and answer comes from the person's material. If the material does not cover something, leave it out or say so.
- **Say whose answer it is.** A model answer is "marked correct" only when the material shows the teacher marked it correct (an answer key, a solved tutorial, full marks on a graded paper). Everything else is answered from the slides and labelled that way. Every practice item says which (`answerSource`: `"marked"` or `"slides"`, see CONTENT_SPEC and PAPER_SPEC).
- **Keep their material private.** It stays on their computer and in their own site. Do not put it in this kit's repo or any public place unless they ask.
- **Ask before anything leaves the computer**: publishing, pushing, creating accounts, sending anything.
- **Check before you say it works.** Build, run the checks, open the site in a browser, and look at it.
- Keep each message to the person short. Tell them what you are doing in one line when a step takes a while.

## Step 0: check the computer

Check for Python 3.10+, the Python packages in `engine/requirements.txt`, and, only if they want audio or shorts, ffmpeg and the packages in `audio/requirements.txt`. Install what is missing yourself where you can, explaining in one line what each thing is for. If something needs the person (an installer window, a password prompt), tell them exactly what to click.

## Step 1: ask a few questions

Ask these together, in plain words, with sensible defaults offered:

1. What is the subject, and what should the site be called?
2. Which exam is it for (midterm, final, a quiz), on what date and time, and which chapters does it cover?
3. What material do they have? Slides, tutorials or solved exercises, past exam papers (graded or with answer keys), notes, a syllabus.
4. Extras: **audio lessons** (listen to each chapter like a podcast) and **short videos** (narrated vertical clips over Minecraft parkour gameplay, like study TikToks). Both need a few extra installs and take longer to make; a computer with an NVIDIA graphics card makes them much faster.
5. Where to put the site: **a Claude Artifact link** (default: works right away from the Claude app, private until they share it) or **GitHub Pages** (a public website address, needs a free GitHub account), or just a file to open on this computer.

Write the answers into `course.json` (copy `course.example.json`). Leave `decks` and `units` as they are for now: you fill them in at step 3, once you have the material.

## Step 2: collect the material

Tell them exactly what to download and where to put it, for example:

> Please download these from your course page and put them in the `materials` folder of this project:
> - every lecture slide deck for the chapters in the exam (PDF is best; PowerPoint is fine)
> - tutorials or solved exercises
> - past exam papers, especially ones with answers or marks on them
> - anything else the teacher gave you (summaries, notes)
>
> Tell me when they are in.

Then list what you found and ask if anything is missing. Photos and scans are fine; you will read them. Phone photos can go in as they are (JPG or PNG; HEIC too once the `pillow-heif` package is installed): one photo, or one folder of photos per document, with the pages in name order.

For short videos: ask them to search for a **free-to-use Minecraft parkour gameplay** video (many channels publish "no copyright" gameplay for this), download it, and put it in `shorts/backgrounds/` as `minecraft-parkour.mp4`. If they skip this, shorts use a plain background.

## Step 3: map the course

1. Add every deck to `course.json` `decks`: lecture slides, tutorials, and past papers. A past paper is a deck too: give it its own id (for example `paper-a`) and list it in `decks` only, never in a unit's `tutorials`. A deck's `file` can be a PDF, a PowerPoint or Word file, one photo, or a folder of photos (pages in name order; they are combined into a PDF in `.cache/`).
2. **Privacy for papers:** graded scans show a student's handwriting and possibly names. By default give every past-paper deck `"publish": false`: its page images then stay in `.cache/slides/<deck>/` for you to read, the site ships none of them, and no slide link points at it. Turn it on only if the person asks and the pages show no names.
3. **Names on the slides:** ask whether the site may show the course code, the school's name and the teachers' names. If not, list those phrases (each spelling the slides use) in `course.json` `"redact": ["CSC 101", "Dr. Jane Smith", ...]`. The extract step removes them from the text and from the page images, keeping the background. It works on text only: check title pages and scans for logos or names in pictures.
4. Run `python -I engine/tools/extract.py`. It writes the slide text and images. Decks flagged "scanned" (all photo decks) have no text layer: read their page images.
5. Read the material and propose the list of units (usually one per chapter or slide deck), with short titles, and which tutorials belong to which unit. Show the list to the person, confirm it, and write it into `course.json` `units`.
6. If a deck starts with a title slide, set `first` to skip it.

## Step 4: write the lessons

For each unit, write `course/content/<unit>.json` following `specs/CONTENT_SPEC.md`: summary, sections that teach every slide that matters, solved tutorials, practice questions with model answers, a quiz and flashcards. Where your tools allow parallel helpers, give each unit to its own helper with CONTENT_SPEC and the unit's slide text, then review what comes back.

Then check every unit against its slides with `specs/VERIFY_SPEC.md`: every fact traceable, nothing important missing, answers right. Where your tools allow, give the check to a separate helper that did not write the unit (give it VERIFY_SPEC, the unit's content file and its slides); otherwise do it yourself as a separate pass after all units are written, going back to the slides rather than your notes. Fix what the check finds.

Optional pages: `brief.json` (what the exam looks like: structure, marks, what each question tends to ask, common traps; only from evidence such as past papers or what the teacher said), `revise.json` (the whole exam on one page), `glossary.json` (terms and symbols that appear in code spans or formulas; the page explains them on hover).

## Step 5: the exam

- **Past papers**: each one is already a deck from step 3 (in `decks`, not in any unit's `tutorials`, `"publish": false` by default). Transcribe each into a fixed mock paper following `specs/PAPER_SPEC.md`, name them in `course.json` `papers` (for example by semester), and never mark an answer correct unless the paper shows it was.
- **Random papers**: write `course/exam_blueprint.json` so the mock exam can draw a fresh paper in the same shape. Without past papers, base the shape on the units and say so in the brief.

## Step 6: extras (only if they asked)

- **Audio lessons**: write `course/audio/scripts/<id>.md` per `specs/AUDIO_STYLE.md` (spoken, nothing visual), add the unit map to `course.json` `audio.units`, run `python -I audio/narrate.py`. Listen-check any paragraph it reports as misheard.
- **Short videos**: write `course/shorts/scripts/<id>.json` per `specs/SHORTS_SPEC.md` and `specs/SHORTS_STYLE.md`, run `python -I shorts/render.py`, then `python -I shorts/checks/check.py`. Look at a few frames before moving on.

Both run on this computer (`kokoro-local`). If the person has a second PC with a strong graphics card, `shorts/homepc/README.md` sets it up as a voice PC (`kokoro-ssh`).

## Step 7: build and check

Run `python -I engine/build.py --target <artifact|github-pages|file>`. It must end with `refs OK` and no problems. Then open `site/index.html` in a browser (serve the `site` folder locally) and click through: home, a lesson, practice, quiz, flashcards, mock exam, study plan, revision, and the extras. No console errors. Fix and rebuild until it is clean. After every rebuild, hard-reload the browser (Ctrl+Shift+R, or Cmd+Shift+R on a Mac) so it does not show the old page from its cache.

## Step 8: publish (ask first)

- **Artifact** (default): build with `--target artifact`. Follow `site/publish_plan.json`: the first publish sends `site/index.html` with the Artifact tool, the first batch of files in `files` (published path -> local path), an `icon` (one generic word, for example `book`) and a one-sentence `description`; the title comes from the page's `<title>` (the site title in `course.json`). Every later publish (the other batches, and every republish after a rebuild) passes the `url` the first one returned, with no icon. Give the person the link and tell them it is private until they share it. If the plan says the course is too big, drop what it says (shorts first), or offer GitHub Pages instead.
- **GitHub Pages**: walk them through making a free GitHub account if they have none, create a repository (private is fine for the source; Pages makes the site itself public, so say so), remove the `site/` line from `.gitignore` so the slide images, audio and videos are pushed (the `materials/` folder stays out), push, and enable Pages with the workflow in `.github/workflows/pages.yml`. Copyrighted slides on a public site: warn them and let them choose.
- **File**: build with `--target file` and tell them which file to open.

## Later: adding material

When they bring new slides, papers or notes: extract, update only the affected units and papers, rebuild, check, and republish to the same place (the same Artifact `url`).
