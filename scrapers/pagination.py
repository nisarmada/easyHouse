from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from scrapers.fetch_errors import FetchError, FetchNotFound
from scrapers.http import fetch_html, page_delay
from scrapers.listing import Listing


def merge_unique_batch(
    seen_ids: set[str],
    listings: list[Listing],
    batch: list[Listing],
) -> int:
    """Append listings not yet seen. Returns count of newly added items."""
    added = 0
    for listing in batch:
        if listing.external_id in seen_ids:
            continue
        seen_ids.add(listing.external_id)
        listings.append(listing)
        added += 1
    return added


@dataclass
class PaginatedScrapeOutcome:
    listings: list[Listing]
    error: str | None = None
    pages_completed: int = 0


def run_paginated_scrape(
    *,
    base_url: str,
    max_pages: int | None,
    page_url_for: Callable[[str, int], str],
    parse_page: Callable[[str], list[Listing]],
    should_fetch_next: Callable[[str, int], bool],
) -> PaginatedScrapeOutcome:
    seen_ids: set[str] = set()
    listings: list[Listing] = []
    page = 1
    pages_completed = 0

    while True:
        if max_pages is not None and page > max_pages:
            break

        url = page_url_for(base_url, page)
        try:
            html = fetch_html(url)
        except FetchNotFound as exc:
            if pages_completed == 0:
                return PaginatedScrapeOutcome([], str(exc), pages_completed=0)
            return PaginatedScrapeOutcome(listings, str(exc), pages_completed=pages_completed)
        except FetchError as exc:
            if pages_completed == 0:
                return PaginatedScrapeOutcome([], str(exc), pages_completed=0)
            return PaginatedScrapeOutcome(listings, str(exc), pages_completed=pages_completed)

        batch = parse_page(html)
        pages_completed = page
        if not batch:
            break

        if merge_unique_batch(seen_ids, listings, batch) == 0:
            break

        if not should_fetch_next(html, page):
            break

        page += 1
        page_delay()

    return PaginatedScrapeOutcome(listings, error=None, pages_completed=pages_completed)
