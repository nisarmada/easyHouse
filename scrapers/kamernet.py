from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from scrapers.listing import Listing
from scrapers.pagination import make_scrape_search

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

    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return {}

    response = (
        data.get("props", {})
        .get("pageProps", {})
        .get("targetPageProps", {})
        .get("findListingsResponse", {})
    )
    return response if isinstance(response, dict) else {}


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
    if not isinstance(raw_listings, list):
        return []

    inferred_city = city or _city_from_url(base_url)
    listings: list[Listing] = []

    for item in raw_listings:
        if not isinstance(item, dict):
            continue
        listing_id = item.get("listingId")
        if listing_id is None:
            continue
        listing_id = str(listing_id)
        street = item.get("street", "")
        house_number = item.get("houseNumber")
        listings.append(
            Listing(
                source="kamernet",
                external_id=listing_id,
                url=_listing_url(base_url, item),
                title=street,
                price_eur=int(item["totalRentalPrice"]) if item.get("totalRentalPrice") else None,
                city=item.get("city") or inferred_city,
                street=street or None,
                house_number=str(house_number) if house_number else None,
                postcode=item.get("postalCode") or None,
            )
        )
    return listings


scrape_search = make_scrape_search(
    default_search_url=DEFAULT_SEARCH_URL,
    page_url_for=page_url,
    has_next=has_next_page,
    page_parser=lambda base: lambda html: parse_listings(
        html, base_url=base, city=_city_from_url(base)
    ),
)
