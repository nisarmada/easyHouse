from __future__ import annotations

import smtplib

from notify.email import notify_email
from scrapers.listing import Listing


def notify_new_listings(listings: list[Listing]) -> None:
    """Send email notifications when new listings are found."""
    if not listings:
        return

    try:
        notify_email(listings)
    except (RuntimeError, TimeoutError, OSError, smtplib.SMTPException) as exc:
        print(f"Notification warning: email: {exc}")
