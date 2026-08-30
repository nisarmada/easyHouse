from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests

DEFAULT_SEARCH_URL = "https://www.pararius.com/apartments/amsterdam"

# Delay between paginated page fetches (deep scans).
PAGE_DELAY_SEC = 2.0
PAGE_DELAY_JITTER_SEC = 1.0

# Browser TLS profiles; stick to one that works, rotate only after failure.
IMPERSONATE_PROFILES = ("chrome131", "chrome124", "safari17_0")
PROFILE_SWITCH_DELAY_SEC = 4.0
FALLBACK_DELAY_SEC = 6.0

_preferred_profile_index = 0


@dataclass
class Listing:
    source: str
    external_id: str
    url: str
    title: str
    price_eur: int | None
    city: str | None = None


def page_url(base_url: str, page: int) -> str:
    base = base_url.rstrip("/")
    if page <= 1:
        return base
    return f"{base}/page-{page}"


def is_cloudflare_challenge(html: str) -> bool:
    return "Just a moment" in html or "cf-browser-verification" in html


def _fetch_with_curl_cffi(url: str, profile: str) -> str:
    response = cf_requests.get(url, impersonate=profile, timeout=30, allow_redirects=True)
    if response.status_code != 200 or is_cloudflare_challenge(response.text):
        raise RuntimeError(f"Blocked or bad response ({response.status_code}) for profile {profile}")
    return response.text


def _fetch_with_cloudscraper(url: str) -> str:
    import cloudscraper

    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "darwin", "mobile": False}
    )
    response = scraper.get(url, timeout=30)
    if response.status_code != 200 or is_cloudflare_challenge(response.text):
        raise RuntimeError(f"cloudscraper blocked or bad response ({response.status_code})")
    return response.text


def fetch_html(url: str) -> str:
    """
    Fetch a Pararius page defensively: prefer one working profile, switch slowly on failure.

    At most 3 HTTP attempts per URL with pauses between them (not a rapid burst).
    """
    global _preferred_profile_index
    errors: list[str] = []

    primary = IMPERSONATE_PROFILES[_preferred_profile_index]
    try:
        html = _fetch_with_curl_cffi(url, primary)
        return html
    except Exception as exc:
        errors.append(f"{primary}: {exc}")

    time.sleep(PROFILE_SWITCH_DELAY_SEC)

    alternate_index = (_preferred_profile_index + 1) % len(IMPERSONATE_PROFILES)
    alternate = IMPERSONATE_PROFILES[alternate_index]
    try:
        html = _fetch_with_curl_cffi(url, alternate)
        _preferred_profile_index = alternate_index
        return html
    except Exception as exc:
        errors.append(f"{alternate}: {exc}")

    time.sleep(FALLBACK_DELAY_SEC)

    try:
        html = _fetch_with_cloudscraper(url)
        return html
    except Exception as exc:
        errors.append(f"cloudscraper: {exc}")

    raise RuntimeError(f"Fetch failed for {url}: {' | '.join(errors)}")


def _page_delay() -> None:
    delay = PAGE_DELAY_SEC + random.uniform(0, PAGE_DELAY_JITTER_SEC)
    time.sleep(delay)


def has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("link", rel="next") is not None


def _city_from_url(url: str) -> str | None:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "apartments":
        return parts[1].replace("-", " ").title()
    return None


def parse_listings(html: str, *, city: str | None = None) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", type="application/ld+json")
    if not script or not script.string:
        return []

    data = json.loads(script.string)
    listings: list[Listing] = []

    for node in data.get("@graph", []):
        types = node.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if "CollectionPage" not in types:
            continue

        for entry in node.get("mainEntity", {}).get("itemListElement", []):
            item = entry["item"]
            listing_url = item["url"]
            external_id = listing_url.rstrip("/").split("/")[-2]
            price = item.get("offers", {}).get("price")
            listings.append(
                Listing(
                    source="pararius",
                    external_id=external_id,
                    url=listing_url,
                    title=item.get("name", ""),
                    price_eur=int(price) if price is not None else None,
                    city=city or _city_from_url(listing_url),
                )
            )
    return listings


def scrape_search(base_url: str = DEFAULT_SEARCH_URL, *, max_pages: int | None = None) -> list[Listing]:
    seen_ids: set[str] = set()
    listings: list[Listing] = []
    city = _city_from_url(base_url)
    page = 1

    while True:
        if max_pages is not None and page > max_pages:
            break

        html = fetch_html(page_url(base_url, page))
        batch = parse_listings(html, city=city)
        if not batch:
            break

        for listing in batch:
            if listing.external_id in seen_ids:
                continue
            seen_ids.add(listing.external_id)
            listings.append(listing)

        if not has_next_page(html):
            break

        page += 1
        _page_delay()

    return listings


def parse_file(path: str | Path) -> list[Listing]:
    return parse_listings(Path(path).read_text(encoding="utf-8"))
