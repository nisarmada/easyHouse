from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from scrapers.http import fetch_html, page_delay
from scrapers.listing import Listing

DEFAULT_SEARCH_URL = "https://www.pararius.com/apartments/amsterdam"

# Re-export for scripts that import from pararius.
__all__ = ["Listing", "DEFAULT_SEARCH_URL", "fetch_html", "parse_file", "parse_listings", "scrape_search"]


def page_url(base_url: str, page: int) -> str:
    base = base_url.rstrip("/")
    if page <= 1:
        return base
    return f"{base}/page-{page}"


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
        page_delay()

    return listings


def parse_file(path: str | Path) -> list[Listing]:
    return parse_listings(Path(path).read_text(encoding="utf-8"))
