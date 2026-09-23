# Isla Vista Dispatch

Live site: https://frosthage.github.io/isla-vista-dispatch/

Scrapes public rental listings around UC Santa Barbara every morning and publishes a static
site with two sections, **Isla Vista** and **Santa Barbara** (the rest of the south coast:
Goleta outside IV, downtown Santa Barbara, Montecito, Carpinteria). Each listing shows photos,
price, beds/baths, availability, description, manager contact and a map pin.

## Run locally

```sh
uv sync
uv run scrape                      # full run → ./site
uv run scrape --only appfolio,craigslist --no-images --cache   # quick dev run
python3 -m http.server -d site 8000   # then open http://localhost:8000/
```

Flags: `--only a,b` limits sources; `--no-images` hot-links photos instead of downloading and
thumbnailing them; `--cache` stores HTTP responses under `.cache/`; `--site-url URL` fetches the
previously published `listings.json` and `geocode_cache.json` from that URL so the build can mark
listings as **New**, track price changes and skip geocoding known addresses.

`uv run pytest` runs the parser tests against saved pages in `tests/fixtures/`.

## Sources

| Source | Module | Notes |
|---|---|---|
| Local property managers on AppFolio (Playa Life, Wolfe & Associates, IV Properties, SFM Vista Del Mar, Excellence PM, Harwin, D63, Cochrane, Koto, DMH, Gallagher) | `scrape/sources/appfolio.py` | AppFolio's robots.txt allows only the list page, so each listing carries one photo and a truncated description. |
| Meridian Group (Rent Manager) | `scrape/sources/meridian.py` | One listing per available unit. |
| MyUniStop (UCSB student marketplace) | `scrape/sources/myunistop.py` | Subleases and rooms from the public listing cards (street-level location, marked approximate). Detail pages sit behind a per-IP login wall after a few dozen views, so only the newest posts get full details, and property-manager leases are kept only when their detail page was readable and says open. |
| Craigslist Santa Barbara | `scrape/sources/craigslist.py` | apa / roo / sub categories, several queries. |
| Redfin | `scrape/sources/redfin.py` | Search results only; detail pages are bot-checked. Works from a home connection but Redfin answers HTTP 405 to GitHub-hosted runners, so the published site has no Redfin listings. |
| ApartmentGuide | `scrape/sources/apartmentguide.py` | Isla Vista, Goleta and Santa Barbara city pages. |
| Icon, Solis Isla Vista, State on Campus | `scrape/sources/complexes.py` | Purpose-built student communities. |
| IV Tenants Union rental guide, Pardall Center roster | `scrape/enrich.py` | Lease policies and contact info joined by manager name. |

Zillow, Apartments.com, Trulia, HotPads, ApartmentList and Rent.com block plain HTTP clients
and are not scraped. Sierra Property Management currently publishes no availability page.

Every request goes through `scrape/http.py`: one request per second per host (or the host's
`Crawl-delay`), retries, and a `robots.txt` check.

## Daily publishing (GitHub Pages)

`.github/workflows/build.yml` runs the scraper at 14:00 UTC daily (and on push / manual
dispatch) and deploys `site/` to GitHub Pages. One-time setup:

1. Create a GitHub repository named `isla-vista-dispatch` and push this project to `main`.
2. In the repository settings, open **Pages** and set **Source** to **GitHub Actions**.
3. Run the workflow once from the **Actions** tab. The site URL is shown on the deploy job.

Photos are part of the deploy artifact, not the git history.

## Layout

```
scrape/
  __main__.py     CLI and pipeline (sources → geocode → region → enrich → dedupe → diff → images → render)
  model.py        Listing dataclass
  http.py         shared HTTP client (throttle, retry, robots, cache)
  geocode.py      Nominatim geocoding with cache; Isla Vista / Santa Barbara classification
  images.py       photo download + 800px thumbnails
  enrich.py       IVTU + Pardall Center manager info
  build.py        dedupe, New/price badges, Jinja2 rendering
  sources/        one self-contained module per site
  templates/      base, index, region, listing
  static/         style.css, app.js (Leaflet map + filters)
data/geocode_cache.json   committed geocode cache (also published with the site)
```
