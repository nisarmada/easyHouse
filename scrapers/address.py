from __future__ import annotations

import re

from scrapers.listing import Listing

POSTCODE_RE = re.compile(r"\b(\d{4}\s?[A-Za-z]{2})\b")
HOUSE_NUMBER_RE = re.compile(r"(\d+[\w-]*)$")
STREET_SUFFIXES = (
    "straat",
    "weg",
    "laan",
    "gracht",
    "plein",
    "dijk",
    "pad",
    "hof",
    "kade",
    "singel",
    "steeg",
    "baan",
    "ring",
    "boulevard",
    "plantsoen",
    "park",
    "square",
)


def normalize_postcode(postcode: str) -> str:
    return re.sub(r"\s+", "", postcode.upper())


def normalize_city(city: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")
    return slug or "unknown"


def normalize_street(street: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", street.lower()).strip("-")
    return slug or "unknown"


def normalize_house_number(house_number: str) -> str:
    return house_number.lower().strip()


def parse_address(title: str, *, city: str | None = None) -> tuple[str | None, str | None, str | None]:
    """Extract street, house number, and postcode from a listing title."""
    text = " ".join(title.split())
    postcode: str | None = None

    match = POSTCODE_RE.search(text)
    if match:
        postcode = normalize_postcode(match.group(1))
        text = (text[: match.start()] + " " + text[match.end() :]).strip()

    if city:
        text = re.sub(re.escape(city), "", text, flags=re.IGNORECASE).strip(" ,")

    street: str | None = None
    house_number: str | None = None

    number_match = HOUSE_NUMBER_RE.search(text)
    if number_match:
        house_number = normalize_house_number(number_match.group(1))
        street = text[: number_match.start()].strip(" ,")
    else:
        street = text.strip(" ,") or None

    if street and not _looks_like_street(street) and house_number is None:
        return street, None, postcode

    return street or None, house_number, postcode


def _looks_like_street(street: str) -> bool:
    lower = street.lower()
    return any(lower.endswith(suffix) or f"{suffix} " in lower for suffix in STREET_SUFFIXES)


def street_from_title(title: str) -> str:
    street, house_number, _ = parse_address(title)
    if street and house_number:
        return f"{street} {house_number}"
    return street or title.strip()


def enrich_listing(listing: Listing) -> Listing:
    """Fill address fields from title when scrapers did not provide them."""
    if not listing.street or not listing.postcode or not listing.house_number:
        street, house_number, postcode = parse_address(listing.title, city=listing.city)
        if not listing.street and street:
            listing.street = street
        if not listing.house_number and house_number:
            listing.house_number = house_number
        if not listing.postcode and postcode:
            listing.postcode = postcode
    return listing


def phase1_key(listing: Listing) -> str:
    street = listing.street or street_from_title(listing.title)
    city = normalize_city(listing.city or "")
    price = listing.price_eur if listing.price_eur is not None else -1
    return f"w|{city}|{normalize_street(street)}|{price}"


def phase2_key(listing: Listing) -> str | None:
    if not listing.postcode or not listing.house_number or not listing.city:
        return None
    return (
        f"s|{normalize_city(listing.city)}|{listing.postcode}|"
        f"{normalize_house_number(listing.house_number)}"
    )


def keys_for(listing: Listing) -> tuple[str | None, str]:
    """Return (strong_key, weak_key). Strong uses postcode+house number when available."""
    enrich_listing(listing)
    weak = phase1_key(listing)
    strong = phase2_key(listing)
    return strong, weak


def primary_key(strong: str | None, weak: str) -> str:
    return strong or weak
