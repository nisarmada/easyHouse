from __future__ import annotations

from unittest.mock import patch

import db.db as dbmod
import pytest
from auth.service import get_active_notification_email, login, signup, verify_email
from config.paths import get_session_path
from db.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _smtp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EASYHOUSE_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EASYHOUSE_SMTP_FROM", "easyHouse <alerts@example.com>")
    monkeypatch.setenv("EASYHOUSE_SMTP_USER", "mailer@example.com")
    monkeypatch.setenv("EASYHOUSE_SMTP_PASSWORD", "secret")


def test_signup_verify_and_notify(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbmod.DB_PATH = tmp_path / "auth-test.db"
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    conn = get_connection()
    init_db(conn)

    sent: list[str] = []

    def _capture(**kwargs):
        sent.append(kwargs["to_address"])

    with patch("auth.service.send_service_email", side_effect=_capture):
        result = signup(conn, email="renter@example.com", password="secretpass")

    assert result["account"]["email"] == "renter@example.com"
    assert result["account"]["verified"] is False
    assert result["email_sent"] is True
    assert sent == ["renter@example.com"]


def test_signup_succeeds_when_email_service_unavailable(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbmod.DB_PATH = tmp_path / "auth-no-smtp.db"
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EASYHOUSE_SMTP_HOST", raising=False)
    conn = get_connection()
    init_db(conn)

    result = signup(conn, email="renter@example.com", password="secretpass")
    assert result["email_sent"] is False
    assert result["account"]["verified"] is False
    code = conn.execute("SELECT token FROM verification_tokens").fetchone()["token"]
    assert len(code) == 6
    assert get_session_path().exists()

    code = conn.execute(
        "SELECT token FROM verification_tokens"
    ).fetchone()["token"]
    assert len(code) == 6
    verify_email(conn, code)

    assert get_active_notification_email(conn) == "renter@example.com"


def test_login_existing_account(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbmod.DB_PATH = tmp_path / "auth-login.db"
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    conn = get_connection()
    init_db(conn)

    with patch("auth.service.send_service_email"):
        signup(conn, email="renter@example.com", password="secretpass")

    get_session_path().unlink(missing_ok=True)
    with patch("auth.service.send_service_email"):
        result = login(conn, email="renter@example.com", password="secretpass")

    assert result["session_token"]
    assert result["account"]["email"] == "renter@example.com"
