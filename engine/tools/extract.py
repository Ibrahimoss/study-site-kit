"""Read the course's slide decks: their text for the AI, and one image per page for the site.

    python -I engine/tools/extract.py [--root <course folder>] [--force]

For every deck in course.json ("decks": [{"id", "file", "first"}]) this writes
  course/text/<deck>.txt           the text of every page, after a "=== <deck> page N ===" line
  site/slides/<deck>/pNNN.webp     one image per page
  site/slides/_manifest.json       id, file, pages, w, h, bytes, first, scanned, publish (and a fingerprint of the file)
A deck with "publish": false (a graded past paper: a student's handwriting, maybe names) writes its page images
to .cache/slides/<deck>/ instead, so the AI can read them but the site never ships them.
PDF decks are read directly. PowerPoint and Word files (.pptx, .ppt, .docx, .doc, .odp, .odt) are first turned
into PDF with LibreOffice, if it is installed. Photos (.jpg, .jpeg, .png, .heic, .heif, .webp, .tif, .tiff, .bmp): a
deck's "file" may be one image or a folder of images (one page each, in name order); they are combined into a PDF in
.cache/img/ first (HEIC needs the pillow-heif package) and the deck is treated as scanned. A deck whose pages have no
text layer (a scan or photos) gets its images anyway and is marked "scanned": the AI must read those page images
instead of the text file.
Decks that did not change since the last run are skipped (--force redoes them all).

Needs: python -m pip install pymupdf pillow
"""
import hashlib, json, os, shutil, subprocess, sys

OFFICE = (".pptx", ".ppt", ".docx", ".doc", ".odp", ".odt", ".rtf")
IMAGES = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff", ".bmp")
VERSION = 3                                      # bump when the output format changes, so every deck is redone
MIN_TEXT = 3                                     # characters a page needs to count as having text (a title is enough)


def find_soffice():
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p: return p
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if os.path.exists(p): return p
    return None


def to_pdf(src, work):
    """A PDF copy of an office file, made by LibreOffice. Returns its path, or None with a message."""
    office = find_soffice()
    if not office:
        print(f"{os.path.splitext(os.path.basename(src))[0]}: needs LibreOffice to read {os.path.basename(src)}. Install it (free, libreoffice.org) and run this again, "
              "or save the file as PDF yourself and point course.json at the PDF.")
        return None
    os.makedirs(work, exist_ok=True)
    r = subprocess.run([office, "--headless", "--convert-to", "pdf", "--outdir", work, src], capture_output=True, text=True)
    out = os.path.join(work, os.path.splitext(os.path.basename(src))[0] + ".pdf")
    if r.returncode != 0 or not os.path.exists(out):
        print(f"LibreOffice could not convert {os.path.basename(src)}: {(r.stderr or r.stdout).strip()[:300]}")
        return None
    return out


def image_files(src):
    """The page images of a photo deck: the file itself, or every image in the folder, sorted by name."""
    if os.path.isdir(src):
        return sorted((os.path.join(src, f) for f in os.listdir(src) if f.lower().endswith(IMAGES) and not f.startswith(".")),
                      key=lambda p: os.path.basename(p).lower())
    return [src]


def images_to_pdf(files, out):
    """One PDF page per photo, upright (EXIF rotation applied). Returns out, or None with a message."""
    from PIL import Image, ImageOps
    if any(f.lower().endswith((".heic", ".heif")) for f in files):
        try:
            import pillow_heif                   # lets Pillow open HEIC photos, when it is installed
            pillow_heif.register_heif_opener()
        except ImportError:
            pass
    pages = []
    for f in files:
        try:
            with Image.open(f) as im:
                pages.append(ImageOps.exif_transpose(im).convert("RGB"))
        except Exception as e:
            hint = " (HEIC photos need: python -m pip install pillow-heif)" if f.lower().endswith((".heic", ".heif")) else ""
            print(f"could not open the photo {os.path.basename(f)}: {e}{hint}")
            return None
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return out


def fingerprint(path):
    h = hashlib.sha256(str(VERSION).encode())
    for p in image_files(path) if os.path.isdir(path) else [path]:
        h.update(os.path.basename(p).encode("utf-8"))
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()[:16]


def slide_dir(root, deck):
    """Where a deck's page images go: site/slides/<deck>, or .cache/slides/<deck> for a deck with "publish": false."""
    return os.path.join(root, ".cache" if deck.get("publish", True) is False else "site", "slides", deck["id"])


def extract(deck, pdf, root, photos=False):
    import fitz
    from PIL import Image
    did = deck["id"]
    doc = fitz.open(pdf)
    texts = [pg.get_text() for pg in doc]
    blank = [len("".join(t.split())) < MIN_TEXT for t in texts]
    scanned = photos or (doc.page_count > 0 and sum(blank) >= max(1, 0.8 * doc.page_count))
    dd = slide_dir(root, deck)
    rel = os.path.relpath(dd, root).replace(os.sep, "/")
    os.makedirs(os.path.join(root, "course", "text"), exist_ok=True)
    with open(os.path.join(root, "course", "text", did + ".txt"), "w", encoding="utf-8") as f:
        if scanned:
            f.write(f"[{did} is a scanned deck: its pages have no text layer. Read the page images "
                    f"{rel}/pNNN.webp instead.]\n")
        for i, t in enumerate(texts):
            f.write(f"\n=== {did} page {i + 1} ===\n")
            f.write(t if not blank[i] and not photos else f"[no text on this page: read {rel}/p{i + 1:03d}.webp]\n")
    os.makedirs(dd, exist_ok=True)
    other = os.path.join(root, "site" if deck.get("publish", True) is False else ".cache", "slides", did)
    if os.path.isdir(other):                     # publish changed since the last run: keep one copy, in the right place
        shutil.rmtree(other)
    tot, w, h = 0, 0, 0
    for i, pg in enumerate(doc):
        width = pg.rect.width; target = 1280 if width > 650 else 1000; z = target / width
        pix = pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        p = os.path.join(dd, f"p{i + 1:03d}.webp"); im.save(p, "WEBP", quality=72, method=6); tot += os.path.getsize(p)
        if i == 0: w, h = pix.width, pix.height
    for f in os.listdir(dd):                     # pages left over from a longer, older version of the deck
        if f.startswith("p") and f.endswith(".webp") and f[1:4].isdigit() and int(f[1:4]) > doc.page_count:
            os.remove(os.path.join(dd, f))
    return {"pages": doc.page_count, "w": w, "h": h, "bytes": tot, "scanned": scanned, "blank": sum(blank)}


def main(argv):
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(errors="replace")
    force = "--force" in argv
    if force: argv.remove("--force")
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    if "--root" in argv:
        i = argv.index("--root"); root = os.path.abspath(argv[i + 1]); del argv[i:i + 2]
    cj = os.path.join(root, "course.json")
    if not os.path.exists(cj): raise SystemExit(f"no course.json in {root} (pass --root <course folder>)")
    try:
        import fitz, PIL                         # noqa: F401
    except ImportError:
        raise SystemExit("needs two Python packages first:  python -m pip install pymupdf pillow")
    with open(cj, encoding="utf-8") as f:
        course = json.load(f)
    decks = course.get("decks") or []
    if not decks: raise SystemExit("course.json has no \"decks\" yet")
    mp = os.path.join(root, "site", "slides", "_manifest.json")
    old = {}
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            old = {m["id"]: m for m in json.load(f)}
    man, failed, scanned = [], [], []
    for deck in decks:
        did, rel = deck["id"], deck.get("file", "")
        src = os.path.join(root, rel)
        if not os.path.exists(src):
            print(f"{did}: file not found: {rel}"); failed.append(did)
            if did in old: man.append(old[did])
            continue
        fp = fingerprint(src)
        prev = old.get(did)
        have = prev and os.path.exists(os.path.join(root, "course", "text", did + ".txt")) and \
            os.path.exists(os.path.join(slide_dir(root, deck), "p001.webp"))
        if not force and have and prev.get("sha") == fp:
            entry = dict(prev, first=int(deck.get("first", 1)), publish=deck.get("publish", True) is not False)
            man.append(entry)
            if entry.get("scanned"): scanned.append(did)
            print(f"{did}: unchanged ({entry['pages']} pages{', scanned' if entry.get('scanned') else ''})")
            continue
        pdf, photos = src, False
        if os.path.isdir(src) or src.lower().endswith(IMAGES):
            files = image_files(src)
            if not files:
                print(f"{did}: the folder {rel} has no photos in it"); failed.append(did); continue
            pdf, photos = images_to_pdf(files, os.path.join(root, ".cache", "img", did + ".pdf")), True
            if not pdf:
                failed.append(did)
                if prev: man.append(prev)
                continue
        elif src.lower().endswith(OFFICE):
            pdf = to_pdf(src, os.path.join(root, ".cache", "pdf"))
            if not pdf:
                failed.append(did)
                if prev: man.append(prev)
                continue
        elif not src.lower().endswith(".pdf"):
            print(f"{did}: {rel} is not a PDF, PowerPoint or Word file, a photo, or a folder of photos"); failed.append(did); continue
        try:
            r = extract(deck, pdf, root, photos)
        except Exception as e:
            print(f"{did}: could not read {rel}: {e}"); failed.append(did); continue
        man.append({"id": did, "file": os.path.basename(rel), "pages": r["pages"], "w": r["w"], "h": r["h"], "bytes": r["bytes"],
                    "first": int(deck.get("first", 1)), "scanned": r["scanned"], "publish": deck.get("publish", True) is not False, "sha": fp})
        line = f"{did}: {r['pages']} pages, {r['w']}x{r['h']}, {r['bytes'] // 1024} KB"
        if r["scanned"]:
            scanned.append(did)
            line += f"  SCANNED: no text layer, read the page images in {os.path.relpath(slide_dir(root, deck), root).replace(os.sep, '/')}/"
        elif r["blank"]:
            line += f"  ({r['blank']} page(s) without text: read their images)"
        print(line)
    os.makedirs(os.path.dirname(mp), exist_ok=True)
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    if scanned: print("scanned decks (read the images, not the text):", ", ".join(scanned))
    if failed:
        print("problems with:", ", ".join(failed)); sys.exit(1)
    print("slides OK")


if __name__ == "__main__":
    main(sys.argv[1:])
