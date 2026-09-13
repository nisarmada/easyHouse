from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from scrapers.http import fetch_html, page_delay
from scrapers.listing import Listing

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
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []

    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string or len(script.string) < 1000:
            continue

        data = json.loads(script.string)
        for node in data.get("@graph", []):
            main_entity = node.get("mainEntity", {})
            if main_entity.get("@type") != "ItemList":
                continue

            for entry in main_entity.get("itemListElement", []):
                item = entry["item"]
                listing_url = item["url"]
                price = item.get("offers", {}).get("price")
                listings.append(
                    Listing(
                        source="huurwoningen",
                        external_id=_external_id(listing_url),
                        url=listing_url,
                        title=item.get("name", ""),
                        price_eur=int(price) if price is not None else None,
                        city=city,
                    )
                )
            return listings

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
