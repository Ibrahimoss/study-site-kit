# Background videos for the shorts

The shorts look best over a gameplay video playing behind the text, the way many study videos do. The kit does
not come with one: you add your own.

## What to put here

1. Find a Minecraft parkour gameplay video that you are allowed to reuse. Look for "no copyright" or
   "free to use" gameplay, or record your own. Any length works; 10 minutes or more gives every short a
   different stretch.
2. Save it in this folder as `minecraft-parkour.mp4`.
3. Render the shorts again.

That is all. Each short plays its own part of the video, darkened so the words stay easy to read. The sound
of the video is never used.

## Good to know

- Another file name or place: set `"backgroundFile"` under `"shorts"` in `course.json`. It can also name a
  folder of videos; each short then gets one of them.
- No video here: the shorts get a drawn, animated background instead, and the renderer prints one line to
  remind you.
- Plain backgrounds on purpose: set `"background": "drawn"` under `"shorts"` in `course.json`. One short can
  choose for itself with `"bg": "gameplay"` or `"bg": "drawn"` in its script.
- Videos in this folder are never committed (see `.gitignore` here), so they stay on your computer.
