from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from scrapers.http import fetch_html, page_delay
from scrapers.listing import Listing

DEFAULT_SEARCH_URL = "https://housinganywhere.com/s/Amsterdam--Netherlands"


def page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url.rstrip("/")

    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _city_from_url(url: str) -> str | None:
    slug = urlparse(url).path.strip("/").split("/")[-1]
    if "--" in slug:
        return slug.split("--", 1)[0].replace("-", " ").title()
    return None


def _parse_hydration(html: str) -> tuple[list[dict], dict | None]:
    match = re.search(r'window\.__staticRouterHydrationData = JSON\.parse\("(.+?)"\)', html)
    if not match:
        return [], None

    raw = match.group(1).encode("utf-8").decode("unicode_escape")
    loader_data = json.loads(raw).get("loaderData", {})
    for value in loader_data.values():
        if isinstance(value, dict) and "listings" in value:
            return value.get("listings", []), value.get("pageInfo")
    return [], None


def parse_listings(html: str, *, city: str | None = None) -> list[Listing]:
    raw_listings, _ = _parse_hydration(html)
    listings: list[Listing] = []

    for item in raw_listings:
        listing_id = str(item["id"])
        path = item.get("unitTypePath") or item.get("listingPath")
        if not path:
            continue

        street = item.get("street", "")
        item_city = item.get("city") or city
        title = street or item.get("propertyType", "Listing")
        house_number = item.get("houseNumber") or item.get("streetNumber")
        postcode = item.get("zip") or item.get("postalCode")
        price_eur = item.get("priceEUR")
        if price_eur is None and item.get("price") is not None:
            price_eur = int(item["price"]) // 100

        listings.append(
            Listing(
                source="housinganywhere",
                external_id=listing_id,
                url=f"https://housinganywhere.com{path}",
                title=title,
                price_eur=int(price_eur) if price_eur is not None else None,
                city=item_city,
                street=street or None,
                house_number=str(house_number) if house_number else None,
                postcode=str(postcode) if postcode else None,
            )
        )

    return listings


def _has_next_page(html: str, current_page: int) -> bool:
    _, page_info = _parse_hydration(html)
    if not page_info:
        return False
    pages = page_info.get("pages")
    if pages is None:
        return False
    return current_page < int(pages)


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

        if not _has_next_page(html, page):
            break

        page += 1
        page_delay()

    return listings
