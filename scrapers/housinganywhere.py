from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from scrapers.js_string import extract_json_parse_payload
from scrapers.listing import Listing
from scrapers.pagination import PaginatedScrapeOutcome, run_paginated_scrape

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


def _price_eur_from_item(item: dict) -> int | None:
    if item.get("priceEUR") is not None:
        return int(item["priceEUR"])

    raw = item.get("price")
    if raw is None:
        return None
    amount = int(raw)

    unit = str(item.get("priceUnit") or item.get("priceType") or "").lower()
    if "cent" in unit or item.get("priceInCents") is True:
        return amount // 100

    currency = str(item.get("priceCurrency") or item.get("currency") or "").upper()
    if currency and currency != "EUR":
        return amount

    if amount >= 20_000:
        return amount // 100
    return amount


def _parse_hydration(html: str) -> tuple[list[dict], dict | None]:
    payload = extract_json_parse_payload(
        html,
        marker="window.__staticRouterHydrationData = JSON.parse",
    )
    if not isinstance(payload, dict):
        return [], None

    loader_data = payload.get("loaderData", {})
    if not isinstance(loader_data, dict):
        return [], None

    for value in loader_data.values():
        if isinstance(value, dict) and "listings" in value:
            listings = value.get("listings", [])
            page_info = value.get("pageInfo")
            if isinstance(listings, list):
                return listings, page_info if isinstance(page_info, dict) else None
    return [], None


def parse_listings(html: str, *, city: str | None = None) -> list[Listing]:
    raw_listings, _ = _parse_hydration(html)
    listings: list[Listing] = []

    for item in raw_listings:
        if not isinstance(item, dict):
            continue
        listing_id = item.get("id")
        if listing_id is None:
            continue
        listing_id = str(listing_id)

        path = item.get("unitTypePath") or item.get("listingPath")
        if not path:
            continue

        street = item.get("street", "")
        item_city = item.get("city") or city
        title = street or item.get("propertyType", "Listing")
        house_number = item.get("houseNumber") or item.get("streetNumber")
        postcode = item.get("zip") or item.get("postalCode")
        price_eur = _price_eur_from_item(item)

        listings.append(
            Listing(
                source="housinganywhere",
                external_id=listing_id,
                url=f"https://housinganywhere.com{path}",
                title=title,
                price_eur=price_eur,
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
        should_fetch_next=_has_next_page,
    )
