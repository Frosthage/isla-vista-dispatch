"""One shared HTTP client: descriptive UA, retries, per-host rate limit, on-disk cache, robots.txt check."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger("http")

UA = "isla-vista-dispatch/0.1 (+https://github.com/Frosthage/isla-vista-dispatch; student housing index)"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

CACHE_DIR = Path(".cache")
MIN_INTERVAL_PER_HOST = 1.0  # seconds

_client = httpx.Client(
    follow_redirects=True,
    timeout=httpx.Timeout(30.0),
    headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"},
)
_last_hit: dict[str, float] = {}
_lock = threading.Lock()
_robots: dict[str, RobotFileParser | None] = {}
_crawl_delay: dict[str, float] = {}
cache_enabled = False   # set True by the CLI for local development


def _throttle(host: str) -> None:
    """Space request *starts* to one per MIN_INTERVAL_PER_HOST (or the host's Crawl-delay); thread-safe."""
    interval = max(MIN_INTERVAL_PER_HOST, _crawl_delay.get(host, 0.0))
    with _lock:
        now = time.monotonic()
        last = _last_hit.get(host)
        slot = now if last is None else max(now, last + interval)
        _last_hit[host] = slot
    if slot > now:
        time.sleep(slot - now)


def _allowed(url: str) -> bool:
    """robots.txt check for the generic '*' agent; also records the host's Crawl-delay."""
    parts = urlsplit(url)
    host = parts.netloc
    if host not in _robots:
        rp = RobotFileParser()
        try:
            r = _client.get(f"{parts.scheme}://{host}/robots.txt")
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
                _robots[host] = rp
                delay = rp.crawl_delay("*")
                if delay:
                    _crawl_delay[host] = float(delay)
            else:
                _robots[host] = None
        except httpx.HTTPError:
            _robots[host] = None
    rp = _robots[host]
    if rp is None:
        return True
    return rp.can_fetch("*", url)


def get(url: str, *, params: dict | None = None, headers: dict | None = None, retries: int = 3) -> httpx.Response | None:
    """GET with throttle/retry. Returns None on 4xx/5xx after retries or robots disallow."""
    req = _client.build_request("GET", url, params=params, headers=headers)
    full = str(req.url)
    key = hashlib.sha1(full.encode()).hexdigest()
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_enabled and cache_file.exists():
        d = json.loads(cache_file.read_text())
        return httpx.Response(d["status"], text=d["text"], request=req)
    if not _allowed(full):
        log.warning("robots.txt disallows %s", full)
        return None
    host = urlsplit(full).netloc
    for attempt in range(retries):
        _throttle(host)
        try:
            r = _client.send(req)
        except httpx.HTTPError as e:
            log.warning("%s: %s (attempt %d)", full, e, attempt + 1)
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            log.warning("%s: HTTP %d (attempt %d)", full, r.status_code, attempt + 1)
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code >= 400:
            log.warning("%s: HTTP %d", full, r.status_code)
            return None
        if cache_enabled:
            CACHE_DIR.mkdir(exist_ok=True)
            cache_file.write_text(json.dumps({"status": r.status_code, "text": r.text}))
        return r
    return None


def get_text(url: str, **kw) -> str | None:
    r = get(url, **kw)
    return r.text if r is not None else None


def download(url: str, dest: Path, min_interval: float = MIN_INTERVAL_PER_HOST) -> bool:
    """Download a binary (image) to dest. Returns True on success."""
    host = urlsplit(url).netloc
    with _lock:
        last = _last_hit.get(host)
        if last is not None:
            wait = min_interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        _last_hit[host] = time.monotonic()
    try:
        r = _client.get(url)
    except httpx.HTTPError as e:
        log.warning("download %s: %s", url, e)
        return False
    if r.status_code != 200 or not r.content:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return True
