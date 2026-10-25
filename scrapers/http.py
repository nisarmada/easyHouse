from __future__ import annotations

import random
import threading
import time
from email.utils import parsedate_to_datetime
from typing import Any

from curl_cffi import requests as cf_requests

from scrapers.fetch_errors import (
    FetchCloudflareChallenge,
    FetchError,
    FetchHttpStatus,
    FetchNotFound,
    FetchRateLimited,
    FetchUnavailable,
)

# Delay between paginated page fetches (deep scans).
PAGE_DELAY_SEC = 2.0
PAGE_DELAY_JITTER_SEC = 1.0

# Browser TLS profiles; stick to one that works, rotate only after failure.
IMPERSONATE_PROFILES = ("chrome131", "chrome124", "safari17_0")
PROFILE_SWITCH_DELAY_SEC = 4.0
FALLBACK_DELAY_SEC = 6.0

MAX_RATE_LIMIT_RETRIES = 3

_tls = threading.local()


def _preferred_profile_index() -> int:
    value = getattr(_tls, "profile_index", None)
    if value is None:
        value = 0
        _tls.profile_index = value
    return value


def _set_preferred_profile_index(index: int) -> None:
    _tls.profile_index = index % len(IMPERSONATE_PROFILES)


def is_cloudflare_challenge(html: str) -> bool:
    return "Just a moment" in html or "cf-browser-verification" in html


def _parse_retry_after(response: Any, *, default: float) -> float:
    raw = response.headers.get("Retry-After")
    if not raw:
        return default
    raw = str(raw).strip()
    if raw.isdigit():
        return max(float(raw), 1.0)
    try:
        retry_at = parsedate_to_datetime(raw)
        return max(retry_at.timestamp() - time.time(), 1.0)
    except (TypeError, ValueError, OverflowError):
        return default


def _validate_response(response: Any, *, profile: str, client: str) -> str:
    status = int(response.status_code)
    text = response.text or ""

    if is_cloudflare_challenge(text):
        raise FetchCloudflareChallenge(
            f"{client} Cloudflare challenge (HTTP {status}) profile={profile}"
        )

    if status == 404:
        raise FetchNotFound(f"{client} HTTP 404 for profile={profile}")
    if status == 429:
        raise FetchRateLimited(
            f"{client} HTTP 429 for profile={profile}",
            retry_after_seconds=_parse_retry_after(response, default=30.0),
        )
    if status == 503:
        raise FetchUnavailable(
            f"{client} HTTP 503 for profile={profile}",
            retry_after_seconds=_parse_retry_after(response, default=15.0),
        )
    if status != 200:
        raise FetchHttpStatus(
            f"{client} HTTP {status} for profile={profile}",
            status_code=status,
        )
    return text


def _fetch_with_curl_cffi(url: str, profile: str) -> str:
    response = cf_requests.get(url, impersonate=profile, timeout=30, allow_redirects=True)
    return _validate_response(response, profile=profile, client="curl_cffi")


def _fetch_with_cloudscraper(url: str) -> str:
    import cloudscraper

    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "darwin", "mobile": False}
    )
    response = scraper.get(url, timeout=30)
    return _validate_response(response, profile="cloudscraper", client="cloudscraper")


def _fetch_with_profile_rotation(url: str) -> str:
    errors: list[str] = []
    preferred = _preferred_profile_index()
    primary = IMPERSONATE_PROFILES[preferred]

    try:
        return _fetch_with_curl_cffi(url, primary)
    except FetchNotFound:
        raise
    except (FetchRateLimited, FetchUnavailable):
        raise
    except FetchCloudflareChallenge as exc:
        errors.append(f"{primary}: {exc}")
    except FetchError as exc:
        errors.append(f"{primary}: {exc}")

    time.sleep(PROFILE_SWITCH_DELAY_SEC)

    alternate_index = (preferred + 1) % len(IMPERSONATE_PROFILES)
    alternate = IMPERSONATE_PROFILES[alternate_index]
    try:
        html = _fetch_with_curl_cffi(url, alternate)
        _set_preferred_profile_index(alternate_index)
        return html
    except FetchNotFound:
        raise
    except (FetchRateLimited, FetchUnavailable):
        raise
    except FetchCloudflareChallenge as exc:
        errors.append(f"{alternate}: {exc}")
    except FetchError as exc:
        errors.append(f"{alternate}: {exc}")

    time.sleep(FALLBACK_DELAY_SEC)

    try:
        return _fetch_with_cloudscraper(url)
    except FetchNotFound:
        raise
    except FetchError as exc:
        errors.append(f"cloudscraper: {exc}")

    raise FetchError(f"Fetch failed for {url}: {' | '.join(errors)}")


def fetch_html(url: str) -> str:
    """
    Fetch a page with status-aware retries.

    404 fails immediately. 429/503 honor Retry-After with bounded retries.
    Cloudflare challenges rotate profiles and fall back to cloudscraper.
    """
    rate_limit_attempt = 0
    while True:
        try:
            return _fetch_with_profile_rotation(url)
        except FetchNotFound:
            raise
        except (FetchRateLimited, FetchUnavailable) as exc:
            if rate_limit_attempt >= MAX_RATE_LIMIT_RETRIES - 1:
                raise
            time.sleep(exc.retry_after_seconds)
            rate_limit_attempt += 1


def page_delay() -> None:
    delay = PAGE_DELAY_SEC + random.uniform(0, PAGE_DELAY_JITTER_SEC)
    time.sleep(delay)
