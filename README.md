# Study Site Kit

Turn your course slides into a full study website, made for you by an AI assistant.

You get a lesson for every chapter, your slides, practice questions with model answers, quizzes, flashcards, a mock exam, a study plan with a countdown to your exam, and a one-page final revision. If you want, you also get audio lessons you can listen to and short narrated videos over Minecraft parkour.

You do not need to know how to code.

## How to use it

1. **Get this folder onto your computer.** On GitHub, click the green **Code** button, then **Download ZIP**, and unzip it.
2. **Open the folder with Claude.** In the Claude desktop app, open the **Code** tab and choose this folder (or run `claude` in it, if you use the terminal).
3. **Say: "make my study site".** Claude will ask you a few questions (your subject, your exam date, what extras you want) and tell you exactly which files to download from your course page. Put them in the `materials` folder and tell it when they are in.

That's it. Claude builds the site, checks it, and gives you a link. By default the link is a private Claude Artifact that you can share when you want. You can also choose a GitHub Pages website or a single file.

## Good to know

- **Your material stays yours.** Your slides and papers stay on your computer and in your own site. Nothing goes in this kit.
- **Answers are labelled.** An answer is marked "correct" only when your material shows your teacher marked it correct. Everything else says it comes from the slides.
- **Extras take longer.** Audio lessons and videos need a few extra installs, and take much less time on a computer with an NVIDIA graphics card.
- **Adding more later.** Drop new files into `materials` and say "add these".

## For the curious

`CLAUDE.md` is the step-by-step guide the AI follows. `specs/` says how each kind of content is written. `engine/` builds the site. `audio/` and `shorts/` make the extras.

MIT licence.
