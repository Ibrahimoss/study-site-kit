"""Small copies of every slide for the Slides tab's thumbnail strip: slides/<deck>/t/pNNN.webp, 200 px wide.

The strip shows each page at about 83 x 62 px, so loading the 1280 px slide for it costs about 240 times the pixels
(CH3.3: 67 images, 2.9 MB). A thumbnail is written only when it is missing or older than its slide, and thumbnails of
deleted slides are removed. Run from build_site.sh.

python -I make_thumbs.py <slides_dir>
"""
import os
import sys

from PIL import Image

WIDTH = 200


def main(root):
    made = removed = 0
    for deck in sorted(os.listdir(root)):
        d = os.path.join(root, deck)
        if not os.path.isdir(d):
            continue
        pages = {f for f in os.listdir(d) if f.startswith("p") and f.endswith(".webp")}
        t = os.path.join(d, "t"); os.makedirs(t, exist_ok=True)
        for f in sorted(pages):
            src, dst = os.path.join(d, f), os.path.join(t, f)
            if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
                continue
            im = Image.open(src).convert("RGB")
            im.thumbnail((WIDTH, WIDTH * 4))
            im.save(dst, "WEBP", quality=72, method=6)
            made += 1
        for f in os.listdir(t):
            if f not in pages:
                os.remove(os.path.join(t, f)); removed += 1
    print(f"thumbnails: {made} written, {removed} removed")


if __name__ == "__main__":
    main(sys.argv[1])
