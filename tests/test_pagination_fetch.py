from __future__ import annotations

from unittest.mock import patch

from scrapers.fetch_errors import FetchError
from scrapers.listing import Listing
from scrapers.pagination import run_paginated_scrape


def test_run_paginated_scrape_returns_partial_on_later_page_failure() -> None:
    pages = {
        1: "<html>page1</html>",
        2: "<html>page2</html>",
    }

    def fake_fetch(url: str) -> str:
        if url.endswith("page-2"):
            raise FetchError("page 2 failed")
        return pages[1]

    def parse_page(html: str) -> list[Listing]:
        if "page1" in html:
            return [
                Listing(
                    source="pararius",
                    external_id="a",
                    url="https://example.com/a",
                    title="A",
                    price_eur=None,
                )
            ]
        return [
            Listing(
                source="pararius",
                external_id="b",
                url="https://example.com/b",
                title="B",
                price_eur=None,
            )
        ]

    with patch("scrapers.pagination.fetch_html", side_effect=fake_fetch):
        outcome = run_paginated_scrape(
            base_url="https://example.com/search",
            max_pages=None,
            page_url_for=lambda base, page: f"{base}/page-{page}",
            parse_page=parse_page,
            should_fetch_next=lambda html, page: page < 2,
        )

    assert len(outcome.listings) == 1
    assert outcome.error is not None
    assert outcome.pages_completed == 1
