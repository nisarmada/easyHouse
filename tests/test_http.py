from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scrapers.fetch_errors import FetchNotFound, FetchRateLimited
from scrapers.http import fetch_html, is_cloudflare_challenge


def test_is_cloudflare_challenge() -> None:
    assert is_cloudflare_challenge("Just a moment...") is True
    assert is_cloudflare_challenge("<html>ok</html>") is False


def test_fetch_html_404_does_not_sleep_through_all_profiles() -> None:
    response = MagicMock(status_code=404, text="not found", headers={})
    with patch("scrapers.http.cf_requests.get", return_value=response):
        with patch("scrapers.http.time.sleep") as sleep_mock:
            with pytest.raises(FetchNotFound):
                fetch_html("https://example.com/missing")
            sleep_mock.assert_not_called()


def test_fetch_html_429_waits_retry_after() -> None:
    ok = MagicMock(status_code=200, text="<html>ok</html>", headers={})
    limited = MagicMock(status_code=429, text="slow down", headers={"Retry-After": "2"})

    with patch("scrapers.http.cf_requests.get", side_effect=[limited, ok]):
        with patch("scrapers.http.time.sleep") as sleep_mock:
            html = fetch_html("https://example.com/list")
            assert "ok" in html
            assert sleep_mock.call_args_list[0].args[0] == 2
