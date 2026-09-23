from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from scrape import build, geocode, http, images
from scrape.model import Listing

log = logging.getLogger("scrape")


def main() -> None:
    ap = argparse.ArgumentParser(prog="scrape", description="Scrape student rentals around UCSB and build the static site")
    ap.add_argument("--only", help="comma-separated source names to run (default: all)")
    ap.add_argument("--no-images", action="store_true", help="hot-link photos instead of downloading them")
    ap.add_argument("--site-url", help="URL of the currently published site; used to fetch the previous run's listings.json and geocode cache")
    ap.add_argument("--cache", action="store_true", help="cache HTTP responses on disk (development)")
    ap.add_argument("--out", default="site", help="output directory (default: site)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    http.cache_enabled = args.cache
    today = date.today().isoformat()
    out_dir = Path(args.out)

    from scrape.sources import appfolio, apartmentguide, complexes, craigslist, meridian, myunistop, redfin
    sources = {
        "appfolio": appfolio.fetch,
        "meridian": meridian.fetch,
        "myunistop": myunistop.fetch,
        "craigslist": craigslist.fetch,
        "redfin": redfin.fetch,
        "apartmentguide": apartmentguide.fetch,
        "complexes": complexes.fetch,
    }
    wanted = [s.strip() for s in args.only.split(",")] if args.only else list(sources)
    unknown = [w for w in wanted if w not in sources]
    if unknown:
        sys.exit(f"unknown source(s): {', '.join(unknown)}; choose from {', '.join(sources)}")

    previous: list[dict] = []
    if args.site_url:
        base = args.site_url.rstrip("/")
        r = http.get(f"{base}/listings.json")
        if r is not None:
            try:
                previous = r.json()
                log.info("previous run: %d listings", len(previous))
            except ValueError:
                log.warning("previous listings.json unreadable")
        r = http.get(f"{base}/geocode_cache.json")
        if r is not None:
            try:
                geocode.merge_cache(r.json())
            except ValueError:
                pass

    listings: list[Listing] = []
    for name in wanted:
        try:
            got = sources[name]()
        except Exception:
            log.exception("source %s failed", name)
            got = []
        log.info("%s: %d listings", name, len(got))
        listings.extend(got)

    for lst in listings:
        if lst.lat is None and lst.address:
            hit = geocode.geocode(lst.address, lst.city, lst.zip)
            if hit:
                lst.lat, lst.lng = hit
                lst.geo_precision = "geocoded"
        lst.region = geocode.classify_region(lst.lat, lst.lng, lst.city)
    dropped = [l for l in listings if l.region is None]
    if dropped:
        log.info("dropped %d listings outside the south coast or without a location", len(dropped))
    listings = [l for l in listings if l.region is not None]

    from scrape import enrich
    enrich.apply(listings)
    listings = build.dedupe(listings)
    build.apply_history(listings, previous, today)

    if out_dir.exists():
        for child in out_dir.iterdir():
            if child.name != "img":
                if child.is_dir():
                    import shutil
                    shutil.rmtree(child)
                else:
                    child.unlink()
    if not args.no_images:
        images.localize(listings, out_dir)
    build.render(listings, out_dir, today, geocode.dump())
    geocode.save()

    by = Counter((l.region, l.source) for l in listings)
    print("\nSummary")
    for region in build.REGIONS:
        total = sum(c for (r, _), c in by.items() if r == region)
        print(f"  {build.REGIONS[region]['name']}: {total}")
        for (r, s), c in sorted(by.items()):
            if r == region:
                print(f"    {s:15} {c}")
    print(f"  new today: {sum(1 for l in listings if l.first_seen == today)}")
    print(f"  output: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
