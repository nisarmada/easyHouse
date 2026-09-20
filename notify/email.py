from __future__ import annotations

import smtplib
from email.message import EmailMessage

from db.db import get_connection, init_db
from notify.smtp_config import ServiceSmtpConfig, load_service_smtp_config


def send_service_email(
    *,
    to_address: str,
    subject: str,
    plain_body: str,
    html_body: str | None = None,
    config: ServiceSmtpConfig | None = None,
) -> None:
    smtp = config or load_service_smtp_config()
    if smtp is None:
        raise RuntimeError(
            "Email delivery is not configured. "
            "Add SMTP settings under Settings → Email delivery."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp.from_address
    message["To"] = to_address
    message.set_content(plain_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as client:
        if smtp.use_tls:
            client.starttls()
        if smtp.username and smtp.password:
            client.login(smtp.username, smtp.password)
        client.send_message(message)


def _format_listing_plain(listing) -> str:
    price = f"€{listing.price_eur:,}" if listing.price_eur else "?"
    city = f" ({listing.city})" if listing.city else ""
    return f"{price} — {listing.title}{city}\n{listing.url}"


def _format_listing_html(listing) -> str:
    price = f"€{listing.price_eur:,}" if listing.price_eur else "?"
    city = f" ({listing.city})" if listing.city else ""
    title = _escape_html(f"{listing.title}{city}")
    url = _escape_html(listing.url)
    return (
        f'<p><strong>{_escape_html(price)}</strong> — {title}<br>'
        f'<a href="{url}">{url}</a></p>'
    )


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def notify_email(listings: list) -> None:
    if not listings:
        return

    from auth.local_cache import load_session_token
    from auth.remote import RemoteAuthError, remote_notify
    from auth.service import get_active_notification_email
    from config.paths import remote_auth_enabled

    conn = get_connection()
    init_db(conn)
    to_address = get_active_notification_email(conn)
    if not to_address:
        return

    if remote_auth_enabled():
        token = load_session_token()
        if not token:
            return
        payload = [
            {
                "title": listing.title,
                "price_eur": listing.price_eur,
                "city": listing.city,
                "url": listing.url,
            }
            for listing in listings
        ]
        try:
            remote_notify(token, payload)
        except RemoteAuthError as exc:
            print(f"Notification warning: could not send alert email: {exc}")
        return

    config = load_service_smtp_config()
    if config is None:
        print("Notification warning: email delivery is not configured")
        return

    count = len(listings)
    subject = f"easyHouse: {count} new listing{'s' if count != 1 else ''}"
    plain_lines = [_format_listing_plain(listing) for listing in listings]
    plain_body = f"{count} new listing{'s' if count != 1 else ''}\n\n" + "\n\n".join(plain_lines)
    html_body = (
        f"<html><body><p>{count} new listing{'s' if count != 1 else ''}</p>"
        + "".join(_format_listing_html(listing) for listing in listings)
        + "</body></html>"
    )
    send_service_email(
        to_address=to_address,
        subject=subject,
        plain_body=plain_body,
        html_body=html_body,
        config=config,
    )
