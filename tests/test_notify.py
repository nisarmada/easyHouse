from __future__ import annotations

from notify import notify_new_listings
from scrapers.listing import Listing


def test_notify_noop_without_config(capsys) -> None:
    notify_new_listings(
        [Listing("pararius", "1", "http://x", "Test", 1000, "Amsterdam", "pararius")]
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
