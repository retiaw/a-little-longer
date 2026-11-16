#!/usr/bin/env python3
"""Build the static album site in `site/` from `A Little Longer/`.

Each series folder holds numbered photos and a README.md whose first `# ` line
is the series title and whose remaining paragraphs are its description.
Run from the repository root:

    python3 site/build_site.py
"""

import html
import re
import shutil
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ALBUM = ROOT / "A Little Longer"
SITE = ROOT / "site"
IMAGES = SITE / "images"

# Morning to evening, with mono as the coda. Unlisted series follow in name order.
ORDER = [
    "Morning by the Water’s Edge",
    "你不理光，光不理你",
    "Then Came the Rain",
    "Evening, As Always",
    "mono",
]
# Photo (file stem) standing for each series beside the index; the first entry is the
# cover shown by default. Series not listed fall back to their first portrait.
KEYS = {
    "Morning by the Water’s Edge": "03",
    "你不理光，光不理你": "01",
    "Then Came the Rain": "04",
    "Evening, As Always": "03",
    "mono": "05",
}
# Explicit URL identifiers for series whose titles need transliteration.
SLUGS = {
    "你不理光，光不理你": "ni-bu-li-guang-guang-bu-li-ni",
}
WIDTHS = (960, 1600, 2400)
QUALITY = 82
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
CJK = re.compile(r"[㐀-鿿豈-﫿]")


def natural_key(name):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def esc(text):
    return html.escape(text, quote=True)


def lang_attr(text):
    return ' lang="zh-Hans"' if CJK.search(text) else ""


def slugify(text, fallback):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().replace("’", "").replace("'", "")).strip("-")
    return slug or fallback


def read_readme(folder):
    lines = (folder / "README.md").read_text(encoding="utf-8").splitlines() if (folder / "README.md").exists() else []
    title, body = folder.name, []
    for line in lines:
        if line.startswith("# ") and title == folder.name and not body:
            title = line[2:].strip()
        else:
            body.append(line)
    paragraphs = [" ".join(p.split()) for p in "\n".join(body).split("\n\n") if p.strip()]
    return title, paragraphs


def export(source, target_dir, stem):
    """Write WebP renditions; keeps the ICC profile, drops EXIF (and any GPS)."""
    with Image.open(source) as original:
        icc = original.info.get("icc_profile")
        image = ImageOps.exif_transpose(original).convert("RGB")
    width, height = image.size
    tone = image.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    renditions = []
    for target in sorted({min(w, width) for w in WIDTHS}):
        resized = image if target == width else image.resize(
            (target, round(height * target / width)), Image.Resampling.LANCZOS)
        name = f"{stem}-{target}.webp"
        options = {"quality": QUALITY, "method": 6}
        if icc:
            options["icc_profile"] = icc
        resized.save(target_dir / name, "WEBP", **options)
        renditions.append((name, target))
    return {"width": width, "height": height, "ratio": width / height,
            "tone": "#%02x%02x%02x" % tone, "renditions": renditions}


def render_photo(photo, series_title, index, total):
    """A figure for the page pool; album.js sizes it and sets `sizes` per page."""
    base = f"images/{photo['slug']}"
    srcset = ", ".join(f"{base}/{name} {w}w" for name, w in photo["renditions"])
    middle = f"{base}/{photo['renditions'][min(1, len(photo['renditions']) - 1)][0]}"
    alt = f"{series_title}, {index} of {total}"
    return (
        f'        <figure data-ar="{photo["ratio"]:.4f}" style="background:{photo["tone"]}">'
        f'<img src="{esc(middle)}" srcset="{esc(srcset)}" sizes="100vw" '
        f'width="{photo["width"]}" height="{photo["height"]}" alt="{esc(alt)}" loading="lazy" decoding="async">'
        f"</figure>"
    )


def render_preview(series, active):
    """One stacked image in the index preview; album.js crossfades between them."""
    photo = series["key"]
    base = f"images/{photo['slug']}"
    srcset = ", ".join(f"{base}/{name} {w}w" for name, w in photo["renditions"])
    state = ' class="active"' if active else ""
    return (
        f'        <img{state} data-series="{series["slug"]}" '
        f'data-number="{series["number"]:02d}" data-title="{esc(series["title"])}" '
        f'src="{base}/{photo["renditions"][0][0]}" srcset="{esc(srcset)}" '
        f'sizes="(max-width: 900px) 0px, 420px" width="{photo["width"]}" height="{photo["height"]}" '
        f'alt="" style="background:{photo["tone"]}">'
    )


def build():
    folders = [p for p in ALBUM.iterdir() if p.is_dir()]
    rank = {name: i for i, name in enumerate(ORDER)}
    folders.sort(key=lambda p: (rank.get(p.name, len(ORDER)), natural_key(p.name)))

    shutil.rmtree(IMAGES, ignore_errors=True)
    IMAGES.mkdir(parents=True)

    series = []
    for number, folder in enumerate(folders, 1):
        title, paragraphs = read_readme(folder)
        slug = SLUGS.get(folder.name) or slugify(title, f"series-{number:02d}")
        files = sorted((f for f in folder.iterdir() if f.suffix.lower() in EXTENSIONS),
                       key=lambda f: natural_key(f.name))
        (IMAGES / slug).mkdir()
        photos = []
        for file in files:
            photo = export(file, IMAGES / slug, file.stem)
            photo["slug"] = slug
            photo["stem"] = file.stem
            photos.append(photo)
            print(f"{folder.name}/{file.name} -> {', '.join(n for n, _ in photo['renditions'])}")
        key = next((p for p in photos if p["stem"] == KEYS.get(folder.name)), None)
        key = key or next((p for p in photos if p["ratio"] < 1), photos[0])
        series.append({"number": number, "title": title, "paragraphs": paragraphs,
                       "slug": slug, "photos": photos, "key": key})

    album = ALBUM.name
    total = sum(len(s["photos"]) for s in series)
    index_items = "\n".join(
        f'        <li><a href="#/{s["slug"]}"><span class="num">{s["number"]:02d}</span>'
        f'<span class="name"{lang_attr(s["title"])}>{esc(s["title"])}</span>'
        f'<span class="count">{len(s["photos"])}</span></a></li>'
        for s in series)

    previews = "\n".join(render_preview(s, s is series[0]) for s in series)

    sections = []
    for s in series:
        desc = "\n".join(f"      <p{lang_attr(p)}>{esc(p)}</p>" for p in s["paragraphs"])
        figures = "\n".join(render_photo(photo, s["title"], i, len(s["photos"]))
                             for i, photo in enumerate(s["photos"], 1))
        sections.append(
            f'  <section class="series" id="{s["slug"]}" data-number="{s["number"]:02d}" '
            f'data-title="{esc(s["title"])}"{lang_attr(s["title"])}>\n'
            f'    <header class="series-head">\n'
            f'      <span class="num">{s["number"]:02d}</span>\n'
            f'      <h2>{esc(s["title"])}</h2>\n'
            f"{desc}\n"
            f"    </header>\n"
            f'    <div class="photos">\n{figures}\n    </div>\n'
            f"  </section>")

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(album)}</title>
  <meta name="description" content="{esc(album)} — {len(series)} series, {total} photographs.">
  <link rel="stylesheet" href="assets/style.css">
  <script>document.documentElement.classList.add("js")</script>
  <script src="assets/album.js" defer></script>
</head>
<body>
  <header class="cover">
    <div class="cover-inner">
      <p class="eyebrow">Photographs</p>
      <h1>{esc(album)}</h1>
      <nav class="index" aria-label="Series">
        <ol>
{index_items}
        </ol>
      </nav>
      <p class="colophon">{len(series)} series · {total} photographs</p>
    </div>
    <figure class="preview" aria-hidden="true">
      <div class="preview-frame">
{previews}
      </div>
      <figcaption><span class="num">{series[0]["number"]:02d}</span>
        <span class="name"{lang_attr(series[0]["title"])}>{esc(series[0]["title"])}</span></figcaption>
    </figure>
  </header>
  <div class="reader" hidden>
    <header class="reader-bar">
      <a class="home" href="#/">{esc(album)}</a>
      <span class="reader-title"></span>
    </header>
    <main class="stage" aria-live="polite"></main>
    <footer class="reader-bar">
      <button class="prev" type="button">&larr; Prev</button>
      <span class="counter"></span>
      <button class="next" type="button">Next &rarr;</button>
      <a class="back" href="#/">Back to index</a>
    </footer>
  </div>
{chr(10).join(sections)}
</body>
</html>
"""
    (SITE / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote {SITE / 'index.html'}: {len(series)} series, {total} photos")


if __name__ == "__main__":
    build()
