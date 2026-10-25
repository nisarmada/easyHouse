from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from scrapers.json_ld import iter_json_ld_scripts, node_types
from scrapers.listing import Listing
from scrapers.pagination import make_scrape_search

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


def _external_id(url: str) -> str | None:
    match = re.search(r"/(\d+)/?$", url)
    if not match:
        return None
    return match.group(1)


def _normalize_listing_url(href: str) -> str:
    if not href.startswith("http"):
        return f"https://www.funda.nl{href}"
    return href


_DETAIL_HREF = re.compile(r"/detail/huur/.+/\d+/?$")
_PRICE_RE = re.compile(r"€\s*([\d.]+)\s*p\.?m")


def _price_from_anchor(anchor: Tag) -> int | None:
    def _parse_price(text: str) -> int | None:
        match = _PRICE_RE.search(text)
        if not match:
            return None
        return int(match.group(1).replace(".", ""))

    direct = _parse_price(anchor.get_text(" ", strip=True))
    if direct is not None:
        return direct

    sibling_chunks = [anchor.get_text(" ", strip=True)]
    for sibling in anchor.next_siblings:
        if isinstance(sibling, Tag) and sibling.name == "a":
            href = sibling.get("href", "")
            if _DETAIL_HREF.search(href):
                break
        if isinstance(sibling, Tag):
            sibling_chunks.append(sibling.get_text(" ", strip=True))
        elif isinstance(sibling, str) and sibling.strip():
            sibling_chunks.append(sibling.strip())
    sibling_price = _parse_price(" ".join(sibling_chunks))
    if sibling_price is not None:
        return sibling_price

    node: Tag | None = anchor.parent
    for _ in range(8):
        if node is None:
            break
        detail_links = node.find_all("a", href=_DETAIL_HREF)
        if len(detail_links) == 1:
            single_card_price = _parse_price(node.get_text(" ", strip=True))
            if single_card_price is not None:
                return single_card_price
        if len(detail_links) > 1:
            break
        node = node.parent
    return None


def _card_details(html: str) -> dict[str, tuple[str, int | None, str]]:
    soup = BeautifulSoup(html, "html.parser")
    details: dict[str, tuple[str, int | None, str]] = {}

    for anchor in soup.find_all("a", href=_DETAIL_HREF):
        href = _normalize_listing_url(anchor["href"])
        external_id = _external_id(href)
        if not external_id:
            continue
        title = anchor.get("aria-label") or anchor.get_text(" ", strip=True) or _title_from_url(href)
        price_eur = _price_from_anchor(anchor)
        details[external_id] = (title, price_eur, href)

    return details


def _listings_from_json_ld(html: str, cards: dict[str, tuple[str, int | None, str]], *, city: str | None) -> list[Listing]:
    listings: list[Listing] = []

    for data in iter_json_ld_scripts(html):
        if "ItemList" not in node_types(data):
            continue

        for entry in data.get("itemListElement", []):
            if not isinstance(entry, dict):
                continue
            listing_url = entry.get("url")
            if not listing_url:
                continue
            listing_url = _normalize_listing_url(str(listing_url))
            external_id = _external_id(listing_url)
            if not external_id:
                continue
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


scrape_search = make_scrape_search(
    default_search_url=DEFAULT_SEARCH_URL,
    page_url_for=page_url,
    has_next=lambda _html, _page: True,
    page_parser=lambda base: lambda html: parse_listings(html, city=_city_from_url(base)),
    skip_when=lambda max_pages: max_pages is not None and max_pages < 1,
)
