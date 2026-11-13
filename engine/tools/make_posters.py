"""Small poster copies for the Shorts feed: shorts/p/<poster name>.webp, 360 px wide, about 15 KB each.

The feed shows a poster while a short's video is still loading. Full posters are 720 x 1280 JPGs of about 85 KB,
so the page could only afford them for the current and next short; on a slow link the short after that stayed
black for seconds. Small posters are cheap enough to fetch several shorts ahead. A copy is written only when it is
missing or older than its poster, and copies of posters that no longer exist are removed. Run from build_site.sh.

python -I make_posters.py <shorts_dir>
"""
import json
import os
import sys

from PIL import Image

WIDTH = 360


def small_name(poster):
    return os.path.splitext(poster)[0] + ".webp"


def main(root):
    man = json.load(open(os.path.join(root, "manifest.json"), encoding="utf-8"))
    out = os.path.join(root, "p"); os.makedirs(out, exist_ok=True)
    want, made = set(), 0
    for m in man:
        poster = m.get("poster") or m["id"] + ".jpg"
        src, dst = os.path.join(root, poster), os.path.join(out, small_name(poster))
        want.add(small_name(poster))
        if not os.path.exists(src) or (os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src)):
            continue
        im = Image.open(src).convert("RGB")
        im.thumbnail((WIDTH, WIDTH * 4))
        im.save(dst, "WEBP", quality=70, method=6)
        made += 1
    removed = 0
    for f in os.listdir(out):
        if f not in want:
            os.remove(os.path.join(out, f)); removed += 1
    print(f"small posters: {made} written, {removed} removed")


if __name__ == "__main__":
    main(sys.argv[1])
