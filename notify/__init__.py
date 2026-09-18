from __future__ import annotations

import json
import os
import smtplib
import urllib.error
import urllib.parse
import urllib.request

from notify.email import notify_email
from scrapers.listing import Listing


def _format_listing(listing: Listing) -> str:
    price = f"€{listing.price_eur:,}" if listing.price_eur else "?"
    return f"{price} — {listing.title}\n{listing.url}"


def _format_message(listings: list[Listing]) -> str:
    header = f"{len(listings)} new listing{'s' if len(listings) != 1 else ''}"
    body = "\n\n".join(_format_listing(listing) for listing in listings)
    return f"{header}\n\n{body}"


def _post_json(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status >= 400:
            raise RuntimeError(f"Notification failed ({response.status})")


def _notify_telegram(listings: list[Listing]) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": _format_message(listings),
        "disable_web_page_preview": False,
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status >= 400:
            raise RuntimeError(f"Telegram notification failed ({response.status})")


def _notify_webhook(listings: list[Listing]) -> None:
    webhook_url = os.environ.get("NOTIFY_WEBHOOK_URL")
    if not webhook_url:
        return

    payload = {
        "text": _format_message(listings),
        "listings": [
            {
                "source": listing.source,
                "external_id": listing.external_id,
                "url": listing.url,
                "title": listing.title,
                "price_eur": listing.price_eur,
                "city": listing.city,
                "search_id": listing.search_id,
            }
            for listing in listings
        ],
    }
    _post_json(webhook_url, payload)


def notify_new_listings(listings: list[Listing]) -> None:
    """Send optional notifications when new listings are found."""
    if not listings:
        return

    errors: list[str] = []
    channels = (
        ("email", notify_email),
        ("telegram", _notify_telegram),
        ("webhook", _notify_webhook),
    )
    for name, sender in channels:
        try:
            sender(listings)
        except (urllib.error.URLError, RuntimeError, TimeoutError, OSError, smtplib.SMTPException) as exc:
            errors.append(f"{name}: {exc}")

    if errors:
        print(f"Notification warning: {' | '.join(errors)}")
