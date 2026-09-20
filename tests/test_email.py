from __future__ import annotations

from unittest.mock import MagicMock, patch

import db.db as dbmod
import pytest
from auth.service import signup, verify_email
from notify.email import notify_email, send_service_email
from notify.smtp_config import load_service_smtp_config, save_service_smtp
from scrapers.listing import Listing


@pytest.fixture
def smtp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EASYHOUSE_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EASYHOUSE_SMTP_FROM", "easyHouse <alerts@example.com>")
    monkeypatch.setenv("EASYHOUSE_SMTP_USER", "mailer@example.com")
    monkeypatch.setenv("EASYHOUSE_SMTP_PASSWORD", "secret")


def test_load_service_smtp_config_from_env(smtp_env: None) -> None:
    config = load_service_smtp_config()
    assert config is not None
    assert config.host == "smtp.example.com"
    assert config.from_address == "easyHouse <alerts@example.com>"


def test_save_service_smtp_to_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EASYHOUSE_SMTP_HOST", raising=False)
    save_service_smtp(
        host="smtp.example.com",
        port=587,
        from_address="easyHouse <you@example.com>",
        username="you@example.com",
        password="secret",
    )
    config = load_service_smtp_config()
    assert config is not None
    assert config.host == "smtp.example.com"
    assert config.password == "secret"


@patch("notify.email.smtplib.SMTP")
def test_send_service_email(mock_smtp: MagicMock, smtp_env: None) -> None:
    connection = MagicMock()
    mock_smtp.return_value.__enter__.return_value = connection

    send_service_email(
        to_address="you@example.com",
        subject="Test",
        plain_body="Hello",
        html_body="<p>Hello</p>",
    )

    connection.send_message.assert_called_once()


@patch("notify.email.smtplib.SMTP")
def test_notify_email_requires_verified_account(
    mock_smtp: MagicMock,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    smtp_env: None,
) -> None:
    dbmod.DB_PATH = tmp_path / "notify-test.db"
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    conn = dbmod.get_connection()
    dbmod.init_db(conn)

    listing = Listing("pararius", "1", "http://x", "Test", 1000, "Amsterdam", "pararius")
    notify_email([listing])
    mock_smtp.assert_not_called()

    with patch("auth.service.send_service_email"):
        signup(conn, email="renter@example.com", password="secretpass")
    code = conn.execute("SELECT token FROM verification_tokens").fetchone()["token"]
    verify_email(conn, code)

    connection = MagicMock()
    mock_smtp.return_value.__enter__.return_value = connection
    notify_email([listing])
    connection.send_message.assert_called_once()
