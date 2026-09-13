from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from scrapers.http import fetch_html, page_delay
from scrapers.listing import Listing

DEFAULT_SEARCH_URL = "https://www.funda.nl/huur/amsterdam/"

# Funda embeds ~15 listings in static HTML; deeper pages need JS we cannot run.
# Pagination stops when a page returns no new listing IDs.


def page_url(base_url: str, page: int) -> str:
    base = base_url.rstrip("/") + "/"
    if page <= 1:
        return base
    return f"{base.rstrip('/')}/p{page}/"


def _city_from_url(url: str) -> str | None:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "huur":
        return parts[1].replace("-", " ").title()
    return None


def _title_from_url(url: str) -> str:
    slug = urlparse(url).path.strip("/").split("/")[-2]
    slug = re.sub(r"^(appartement|huis|studio|kamer)-", "", slug)
    return slug.replace("-", " ").title()


def _external_id(url: str) -> str:
    match = re.search(r"/(\d+)/?$", url)
    if not match:
        raise ValueError(f"Could not parse Funda listing id from {url}")
    return match.group(1)


def _normalize_listing_url(href: str) -> str:
    if not href.startswith("http"):
        return f"https://www.funda.nl{href}"
    return href


def _card_details(html: str) -> dict[str, tuple[str, int | None, str]]:
    soup = BeautifulSoup(html, "html.parser")
    details: dict[str, tuple[str, int | None, str]] = {}

    for anchor in soup.find_all("a", href=re.compile(r"/detail/huur/.+/\d+/?$")):
        href = _normalize_listing_url(anchor["href"])
        external_id = _external_id(href)
        title = anchor.get("aria-label") or anchor.get_text(" ", strip=True) or _title_from_url(href)

        price_eur: int | None = None
        node = anchor
        for _ in range(8):
            node = node.parent
            if node is None:
                break
            text = node.get_text(" ", strip=True)
            match = re.search(r"€\s*([\d.]+)\s*p\.?m", text)
            if match:
                price_eur = int(match.group(1).replace(".", ""))
                break

        details[external_id] = (title, price_eur, href)

    return details


def _listings_from_json_ld(html: str, cards: dict[str, tuple[str, int | None, str]], *, city: str | None) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []

    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        data = json.loads(script.string)
        types = data.get("@type")
        if isinstance(types, str):
            types = [types]
        if "ItemList" not in types:
            continue

        for entry in data.get("itemListElement", []):
            listing_url = _normalize_listing_url(entry["url"])
            external_id = _external_id(listing_url)
            card_title, card_price, card_url = cards.get(external_id, ("", None, listing_url))
            listings.append(
                Listing(
                    source="funda",
                    external_id=external_id,
                    url=card_url or listing_url,
                    title=card_title or _title_from_url(listing_url),
                    price_eur=card_price,
                    city=city,
                )
            )
        break

    return listings


def parse_listings(html: str, *, city: str | None = None) -> list[Listing]:
    cards = _card_details(html)
    listings = _listings_from_json_ld(html, cards, city=city)

    seen_ids = {listing.external_id for listing in listings}
    for external_id, (title, price_eur, url) in cards.items():
        if external_id in seen_ids:
            continue
        listings.append(
            Listing(
                source="funda",
                external_id=external_id,
                url=url,
                title=title or _title_from_url(url),
                price_eur=price_eur,
                city=city,
            )
        )

    return listings


def scrape_search(base_url: str = DEFAULT_SEARCH_URL, *, max_pages: int | None = None) -> list[Listing]:
    if max_pages is not None and max_pages < 1:
        return []

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

        new_in_batch = 0
        for listing in batch:
            if listing.external_id in seen_ids:
                continue
            seen_ids.add(listing.external_id)
            listings.append(listing)
            new_in_batch += 1

        if new_in_batch == 0:
            break

        page += 1
        page_delay()

    return listings
