from __future__ import annotations

from config.load import SourceConfig
from scrapers.funda import scrape_search as scrape_funda
from scrapers.housinganywhere import scrape_search as scrape_housinganywhere
from scrapers.huurwoningen import scrape_search as scrape_huurwoningen
from scrapers.kamernet import scrape_search as scrape_kamernet
from scrapers.listing import Listing
from scrapers.pararius import scrape_search as scrape_pararius

_SCRAPERS = {
    "pararius": scrape_pararius,
    "kamernet": scrape_kamernet,
    "funda": scrape_funda,
    "huurwoningen": scrape_huurwoningen,
    "housinganywhere": scrape_housinganywhere,
}


def scrape_source(source: SourceConfig, *, max_pages: int | None = None) -> list[Listing]:
    scraper = _SCRAPERS.get(source.type)
    if scraper is None:
        raise ValueError(f"Unsupported source type: {source.type!r}")

    listings = scraper(source.url, max_pages=max_pages)
    for listing in listings:
        listing.search_id = source.id
    return listings
