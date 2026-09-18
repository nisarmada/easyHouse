from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int
    to_address: str
    from_address: str
    username: str | None = None
    password: str | None = None
    use_tls: bool = True


def load_email_config() -> EmailConfig | None:
    to_address = os.environ.get("NOTIFY_EMAIL", "").strip()
    host = os.environ.get("SMTP_HOST", "").strip()
    if not to_address or not host:
        return None

    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USER", "").strip() or None
    password = os.environ.get("SMTP_PASSWORD", "").strip() or None
    from_address = os.environ.get("SMTP_FROM", "").strip() or username or "easyhouse@localhost"
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() not in {"0", "false", "no"}

    return EmailConfig(
        host=host,
        port=port,
        to_address=to_address,
        from_address=from_address,
        username=username,
        password=password,
        use_tls=use_tls,
    )


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


def build_email(listings: list, *, config: EmailConfig) -> EmailMessage:
    count = len(listings)
    subject = f"easyHouse: {count} new listing{'s' if count != 1 else ''}"

    plain_lines = [_format_listing_plain(listing) for listing in listings]
    plain_body = f"{count} new listing{'s' if count != 1 else ''}\n\n" + "\n\n".join(plain_lines)

    html_body = (
        f"<html><body><p>{count} new listing{'s' if count != 1 else ''}</p>"
        + "".join(_format_listing_html(listing) for listing in listings)
        + "</body></html>"
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.from_address
    message["To"] = config.to_address
    message.set_content(plain_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_email(message: EmailMessage, *, config: EmailConfig) -> None:
    with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
        if config.use_tls:
            smtp.starttls()
        if config.username and config.password:
            smtp.login(config.username, config.password)
        smtp.send_message(message)


def notify_email(listings: list) -> None:
    config = load_email_config()
    if config is None:
        return
    message = build_email(listings, config=config)
    send_email(message, config=config)
