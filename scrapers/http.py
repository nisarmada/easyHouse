from __future__ import annotations

import random
import time

from curl_cffi import requests as cf_requests

# Delay between paginated page fetches (deep scans).
PAGE_DELAY_SEC = 2.0
PAGE_DELAY_JITTER_SEC = 1.0

# Browser TLS profiles; stick to one that works, rotate only after failure.
IMPERSONATE_PROFILES = ("chrome131", "chrome124", "safari17_0")
PROFILE_SWITCH_DELAY_SEC = 4.0
FALLBACK_DELAY_SEC = 6.0

_preferred_profile_index = 0


def is_cloudflare_challenge(html: str) -> bool:
    return "Just a moment" in html or "cf-browser-verification" in html


def _fetch_with_curl_cffi(url: str, profile: str) -> str:
    response = cf_requests.get(url, impersonate=profile, timeout=30, allow_redirects=True)
    if response.status_code != 200 or is_cloudflare_challenge(response.text):
        raise RuntimeError(f"Blocked or bad response ({response.status_code}) for profile {profile}")
    return response.text


def _fetch_with_cloudscraper(url: str) -> str:
    import cloudscraper

    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "darwin", "mobile": False}
    )
    response = scraper.get(url, timeout=30)
    if response.status_code != 200 or is_cloudflare_challenge(response.text):
        raise RuntimeError(f"cloudscraper blocked or bad response ({response.status_code})")
    return response.text


def fetch_html(url: str) -> str:
    """
    Fetch a page defensively: prefer one working profile, switch slowly on failure.

    At most 3 HTTP attempts per URL with pauses between them (not a rapid burst).
    """
    global _preferred_profile_index
    errors: list[str] = []

    primary = IMPERSONATE_PROFILES[_preferred_profile_index]
    try:
        return _fetch_with_curl_cffi(url, primary)
    except Exception as exc:
        errors.append(f"{primary}: {exc}")

    time.sleep(PROFILE_SWITCH_DELAY_SEC)

    alternate_index = (_preferred_profile_index + 1) % len(IMPERSONATE_PROFILES)
    alternate = IMPERSONATE_PROFILES[alternate_index]
    try:
        html = _fetch_with_curl_cffi(url, alternate)
        _preferred_profile_index = alternate_index
        return html
    except Exception as exc:
        errors.append(f"{alternate}: {exc}")

    time.sleep(FALLBACK_DELAY_SEC)

    try:
        return _fetch_with_cloudscraper(url)
    except Exception as exc:
        errors.append(f"cloudscraper: {exc}")

    raise RuntimeError(f"Fetch failed for {url}: {' | '.join(errors)}")


def page_delay() -> None:
    delay = PAGE_DELAY_SEC + random.uniform(0, PAGE_DELAY_JITTER_SEC)
    time.sleep(delay)
