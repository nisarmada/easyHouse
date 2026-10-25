from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from scrapers.json_ld import iter_json_ld_scripts, node_types
from scrapers.listing import Listing
from scrapers.pagination import PaginatedScrapeOutcome, run_paginated_scrape

DEFAULT_SEARCH_URL = "https://www.huurwoningen.nl/in/amsterdam/"


def page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url if base_url.endswith("/") else f"{base_url.rstrip('/')}/"

    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _city_from_url(url: str) -> str | None:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "in":
        return parts[1].replace("-", " ").title()
    return None


def _external_id(listing_url: str) -> str:
    return listing_url.rstrip("/").split("/")[-2]


def has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("link", rel="next") is not None


def parse_listings(html: str, *, city: str | None = None) -> list[Listing]:
    listings: list[Listing] = []

    for node in iter_json_ld_scripts(html):
        main_entity = node.get("mainEntity")
        if not isinstance(main_entity, dict):
            continue
        if "ItemList" not in node_types(main_entity):
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
            offers = item.get("offers")
            price = offers.get("price") if isinstance(offers, dict) else None
            listings.append(
                Listing(
                    source="huurwoningen",
                    external_id=_external_id(listing_url),
                    url=listing_url,
                    title=str(item.get("name") or ""),
                    price_eur=int(price) if price is not None else None,
                    city=city,
                )
            )
        if listings:
            return listings

    return listings


def scrape_search(
    base_url: str = DEFAULT_SEARCH_URL,
    *,
    max_pages: int | None = None,
) -> PaginatedScrapeOutcome:
    city = _city_from_url(base_url)
    return run_paginated_scrape(
        base_url=base_url,
        max_pages=max_pages,
        page_url_for=page_url,
        parse_page=lambda html: parse_listings(html, city=city),
        should_fetch_next=lambda html, page: has_next_page(html),
    )
