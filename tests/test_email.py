from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from notify.email import EmailConfig, build_email, load_email_config, notify_email
from scrapers.listing import Listing


def test_load_email_config_returns_none_when_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert load_email_config() is None


def test_load_email_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_EMAIL", "you@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "mailer@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "easyHouse <mailer@example.com>")

    config = load_email_config()
    assert config is not None
    assert config.to_address == "you@example.com"
    assert config.host == "smtp.example.com"
    assert config.port == 465
    assert config.username == "mailer@example.com"
    assert config.password == "secret"
    assert config.from_address == "easyHouse <mailer@example.com>"


def test_build_email_plain_and_html() -> None:
    listing = Listing("pararius", "1", "http://x", "Krammerstraat", 3100, "Amsterdam", "pararius")
    config = EmailConfig(
        host="smtp.example.com",
        port=587,
        to_address="you@example.com",
        from_address="easyhouse@example.com",
    )

    message = build_email([listing], config=config)
    assert message["Subject"] == "easyHouse: 1 new listing"
    assert message["To"] == "you@example.com"

    parts = list(message.walk())
    bodies = [part.get_payload(decode=True).decode() for part in parts if part.get_content_type() in {"text/plain", "text/html"}]
    assert any("€3,100" in body and "Krammerstraat" in body for body in bodies)
    assert any("<a href=" in body for body in bodies)


@patch("notify.email.smtplib.SMTP")
def test_notify_email_sends_when_configured(mock_smtp: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_EMAIL", "you@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "mailer@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")

    connection = MagicMock()
    mock_smtp.return_value.__enter__.return_value = connection

    listing = Listing("pararius", "1", "http://x", "Test", 1000, "Amsterdam", "pararius")
    notify_email([listing])

    connection.starttls.assert_called_once()
    connection.login.assert_called_once_with("mailer@example.com", "secret")
    connection.send_message.assert_called_once()
