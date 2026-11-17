#!/usr/bin/env python3
"""Build the static album site in `site/` from `A Little Longer/`.

Each series folder holds numbered photos and a README.md whose first `# ` line
is the series title and whose remaining paragraphs are its description.
Run from the repository root:

    python3 site/build_site.py
"""

import html
import hashlib
import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ALBUM = ROOT / "A Little Longer"
BIO = ROOT / "bio"
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


def render_features(authors):
    """Keep featured authors in the same index/preview shell as our own series."""
    items, profiles = [], []
    for number, author in enumerate(authors, 1):
        slug = esc(author["slug"])
        items.append(
            f'        <li><a href="#/feature/{slug}" data-author="{slug}">'
            f'<span class="num">{number:02d}</span>'
            f'<span class="name">{esc(author.get("label", author["name"]))}</span>'
            f'<span class="count">{esc(author.get("index_note", author["album"]))}</span></a></li>')
        bio = "\n".join(
            f'          <p{lang_attr(p)}>' + re.sub(r"\*([^*]+)\*", r"<em>\1</em>", esc(p)) + '</p>'
            for p in author["bio"])
        photo = author.get("photo")
        photograph = ""
        if photo:
            responsive = f' srcset="{esc(photo["srcset"])}" sizes="(max-width: 900px) calc(100vw - 40px), 420px"' if photo.get("srcset") else ""
            image = f'<img src="{esc(photo["src"])}"{responsive} width="{photo["width"]}" height="{photo["height"]}" alt="{esc(photo["alt"])}" loading="lazy" decoding="async">'
            if photo.get("url"):
                image = f'<a href="{esc(photo["url"])}" target="_blank" rel="noopener noreferrer" aria-label="Read {esc(author["name"])}’s bio">{image}</a>'
            framing = ' feature-photo--self' if author["slug"] == "bio" else ""
            photograph = f'        <figure class="feature-photo{framing}">{image}</figure>\n'
        native = f'            <p class="author-native" lang="zh-Hans">{esc(author["native_name"])}</p>' if author.get("native_name") else ""
        links = ""
        if author.get("url"):
            links = f'''          <div class="feature-links">
            <a class="visit-album" href="{esc(author["url"])}" target="_blank" rel="noopener noreferrer">Visit {esc(author["album"])} <span aria-hidden="true">↗</span></a>
          </div>'''
        inactive = ' is-inactive' if number > 1 else ''
        state = ' inert aria-hidden="true"' if number > 1 else ''
        profiles.append(f'''      <article class="feature-bio{inactive}" data-author="{slug}"{state}>
{photograph}        <div class="feature-copy">
          <div class="feature-identity">
            <h2>{esc(author["name"])}</h2>
{native}
          </div>
          <div class="bio-copy">
{bio}
          </div>
{links}
        </div>
      </article>''')
    return "\n".join(items), "\n".join(profiles)


def read_bio():
    """Make the owner's README and portrait the first entry in Bio & Feature."""
    _, paragraphs = read_readme(BIO)
    paragraphs = [p for p in paragraphs if not p.startswith("<img ")]
    target = SITE / "assets" / "bio"
    target.mkdir(parents=True, exist_ok=True)
    photo = export(BIO / "portrait.png", target, "portrait")
    srcset = ", ".join(f"assets/bio/{name} {width}w" for name, width in photo["renditions"])
    return {
        "slug": "bio", "label": "Bio", "name": "Haochen Liu", "native_name": "刘浩宸",
        "album": ALBUM.name, "index_note": "",
        "bio": paragraphs,
        "photo": {
            "src": f'assets/bio/{photo["renditions"][-1][0]}', "srcset": srcset,
            "width": photo["width"], "height": photo["height"],
            "alt": "Haochen Liu standing by the water",
        },
    }


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
    authors = json.loads((SITE / "featured.json").read_text(encoding="utf-8"))
    feature_items, feature_profiles = render_features([read_bio(), *authors])
    feature_count = f'Bio · {len(authors)} featured {"author" if len(authors) == 1 else "authors"}'
    asset_versions = {
        name: hashlib.sha256((SITE / "assets" / name).read_bytes()).hexdigest()[:12]
        for name in ("style.css", "album.js")
    }

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
  <link rel="stylesheet" href="assets/style.css?v={asset_versions['style.css']}">
  <script>document.documentElement.classList.add("js")</script>
  <script src="assets/album.js?v={asset_versions['album.js']}" defer></script>
</head>
<body>
  <header class="cover" data-view="photographs">
    <div class="cover-inner">
      <nav class="eyebrow cover-nav" aria-label="Sections">
        <a href="#/" data-view="photographs" aria-current="page">Photographs</a>
        <a href="#/feature" data-view="feature">Bio &amp; Feature</a>
      </nav>
      <h1>{esc(album)}</h1>
      <div class="index-panels">
        <nav class="index" data-panel="photographs" aria-label="Series">
          <ol>
{index_items}
          </ol>
        </nav>
        <nav class="index is-inactive" data-panel="feature" aria-label="Featured authors" inert aria-hidden="true">
          <ol>
{feature_items}
          </ol>
        </nav>
      </div>
      <p class="colophon" data-photographs="{len(series)} series · {total} photographs" data-feature="{esc(feature_count)}">{len(series)} series · {total} photographs</p>
    </div>
    <div class="cover-aside">
    <figure class="preview" aria-hidden="true">
      <div class="preview-frame">
{previews}
      </div>
      <figcaption><span class="num">{series[0]["number"]:02d}</span>
        <span class="name"{lang_attr(series[0]["title"])}>{esc(series[0]["title"])}</span></figcaption>
    </figure>
    <div class="feature-profiles is-inactive" inert aria-hidden="true" aria-live="polite">
{feature_profiles}
    </div>
    </div>
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
  <footer class="copyright"><span>© 2026 <a href="https://github.com/retiaw">retiaw</a>. All rights reserved.</span></footer>
</body>
</html>
"""
    (SITE / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote {SITE / 'index.html'}: {len(series)} series, {total} photos")


if __name__ == "__main__":
    build()
