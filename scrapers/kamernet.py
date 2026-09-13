from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from scrapers.http import fetch_html, page_delay
from scrapers.listing import Listing

DEFAULT_SEARCH_URL = "https://kamernet.nl/huren/appartement-amsterdam"


def page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url.rstrip("/")

    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["pageNo"] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _category_slug(base_url: str) -> str:
    parts = urlparse(base_url).path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "huren":
        return parts[1].split("-")[0]
    return "appartement"


def _city_from_url(base_url: str) -> str | None:
    parts = urlparse(base_url).path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "huren":
        slug = parts[1].split("-", 1)
        if len(slug) == 2:
            return slug[1].replace("-", " ").title()
    return None


def _listing_url(base_url: str, listing: dict) -> str:
    parsed = urlparse(base_url)
    category = _category_slug(base_url)
    path = (
        f"/huren/{category}-{listing['citySlug']}/"
        f"{listing['streetSlug']}/{category}-{listing['listingId']}"
    )
    return urlunparse(parsed._replace(path=path, query="", fragment=""))


def _find_listings_response(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return {}

    data = json.loads(script.string)
    return (
        data.get("props", {})
        .get("pageProps", {})
        .get("targetPageProps", {})
        .get("findListingsResponse", {})
    )


def has_next_page(html: str, current_page: int) -> bool:
    response = _find_listings_response(html)
    total = response.get("total")
    page_size = len(response.get("listings", []))
    if not total or not page_size:
        return False
    return current_page * page_size < total


def parse_listings(html: str, *, base_url: str, city: str | None = None) -> list[Listing]:
    response = _find_listings_response(html)
    raw_listings = response.get("listings", [])
    inferred_city = city or _city_from_url(base_url)
    listings: list[Listing] = []

    for item in raw_listings:
        listing_id = str(item["listingId"])
        street = item.get("street", "")
        listings.append(
            Listing(
                source="kamernet",
                external_id=listing_id,
                url=_listing_url(base_url, item),
                title=street,
                price_eur=int(item["totalRentalPrice"]) if item.get("totalRentalPrice") else None,
                city=item.get("city") or inferred_city,
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
        batch = parse_listings(html, base_url=base_url, city=city)
        if not batch:
            break

        for listing in batch:
            if listing.external_id in seen_ids:
                continue
            seen_ids.add(listing.external_id)
            listings.append(listing)

        if not has_next_page(html, page):
            break

        page += 1
        page_delay()

    return listings
