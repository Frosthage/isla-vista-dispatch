"""Download listing photos and write ~800px JPEG thumbnails into the site."""
from __future__ import annotations

import hashlib
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from scrape import http
from scrape.model import Listing

log = logging.getLogger("images")

MAX_PHOTOS = 10
THUMB_WIDTH = 800
ORIG_CACHE = Path(".cache/img")


def _one(url: str, out_dir: Path) -> str | None:
    key = hashlib.sha1(url.encode()).hexdigest()
    rel = f"img/{key}.jpg"
    dest = out_dir / rel
    if dest.exists():
        return rel
    orig = ORIG_CACHE / key
    if not orig.exists():
        if not http.download(url, orig, min_interval=0.15):
            return None
    try:
        im = Image.open(orig)
        im.load()
    except (OSError, Image.DecompressionBombError) as e:
        log.warning("bad image %s: %s", url, e)
        orig.unlink(missing_ok=True)
        return None
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    if im.width > THUMB_WIDTH:
        im = im.resize((THUMB_WIDTH, round(im.height * THUMB_WIDTH / im.width)), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80, optimize=True)
    dest.write_bytes(buf.getvalue())
    return rel


def localize(listings: list[Listing], out_dir: Path) -> None:
    jobs: list[tuple[Listing, int, str]] = []
    for lst in listings:
        lst.photos = lst.photos[:MAX_PHOTOS]
        for i, url in enumerate(lst.photos):
            if url.startswith("http"):
                jobs.append((lst, i, url))
    log.info("downloading %d photos for %d listings", len(jobs), len(listings))
    results: dict[tuple[str, int], str | None] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (lst, i, url), rel in zip(jobs, ex.map(lambda j: _one(j[2], out_dir), jobs)):
            results[(lst.id, i)] = rel
    for lst in listings:
        lst.photos = [results.get((lst.id, i), None) or "" for i in range(len(lst.photos))]
        lst.photos = [p for p in lst.photos if p]
