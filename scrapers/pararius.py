from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from scrapers.http import fetch_html, page_delay
from scrapers.json_ld import iter_json_ld_scripts, node_types
from scrapers.listing import Listing
from scrapers.pagination import merge_unique_batch

DEFAULT_SEARCH_URL = "https://www.pararius.com/apartments/amsterdam"


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
    listings: list[Listing] = []

    for node in iter_json_ld_scripts(html):
        if "CollectionPage" not in node_types(node):
            continue

        main_entity = node.get("mainEntity")
        if not isinstance(main_entity, dict):
            continue

        for entry in main_entity.get("itemListElement", []):
            if not isinstance(entry, dict):
                continue
            item = entry.get("item")
            if not isinstance(item, dict):
                continue
            listing_url = item.get("url")
            if not listing_url:
                continue
            listing_url = str(listing_url)
            external_id = listing_url.rstrip("/").split("/")[-2]
            offers = item.get("offers")
            price = offers.get("price") if isinstance(offers, dict) else None
            listings.append(
                Listing(
                    source="pararius",
                    external_id=external_id,
                    url=listing_url,
                    title=str(item.get("name") or ""),
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

        if merge_unique_batch(seen_ids, listings, batch) == 0:
            break

        if not has_next_page(html):
            break

        page += 1
        page_delay()

    return listings


def parse_file(path: str | Path) -> list[Listing]:
    return parse_listings(Path(path).read_text(encoding="utf-8"))
