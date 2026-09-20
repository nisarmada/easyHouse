from __future__ import annotations

import smtplib
from unittest.mock import patch

import db.db as dbmod
import pytest
from auth.service import resend_verification, signup, verify_email
from db.db import get_connection, init_db
from notify.smtp_config import save_service_smtp
from tests.local_smtp_sink import LocalSmtpSink


@pytest.fixture
def smtp_sink() -> LocalSmtpSink:
    sink = LocalSmtpSink()
    sink.start()
    try:
        yield sink
    finally:
        sink.stop()


def test_signup_sends_verification_email_end_to_end(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    smtp_sink: LocalSmtpSink,
) -> None:
    dbmod.DB_PATH = tmp_path / "delivery-test.db"
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EASYHOUSE_SMTP_HOST", raising=False)
    monkeypatch.delenv("EASYHOUSE_SMTP_FROM", raising=False)
    monkeypatch.delenv("EASYHOUSE_SMTP_USER", raising=False)
    monkeypatch.delenv("EASYHOUSE_SMTP_PASSWORD", raising=False)

    save_service_smtp(
        host="127.0.0.1",
        port=smtp_sink.port,
        from_address="easyHouse <alerts@easyhouse.test>",
        username="",
        password="",
        use_tls=False,
    )

    conn = get_connection()
    init_db(conn)
    result = signup(conn, email="renter@example.com", password="secretpass")
    assert result["email_sent"] is True

    message = smtp_sink.wait_for_message(
        to_address="renter@example.com",
        subject_contains="verification code",
    )
    code = smtp_sink.extract_verification_code(message)
    verified = verify_email(conn, code)
    assert verified["verified"] is True


def test_resend_verification_email_end_to_end(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    smtp_sink: LocalSmtpSink,
) -> None:
    dbmod.DB_PATH = tmp_path / "resend-delivery-test.db"
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EASYHOUSE_SMTP_HOST", raising=False)

    save_service_smtp(
        host="127.0.0.1",
        port=smtp_sink.port,
        from_address="easyHouse <alerts@easyhouse.test>",
        use_tls=False,
    )

    conn = get_connection()
    init_db(conn)
    with patch("auth.service.send_service_email"):
        signup(conn, email="renter@example.com", password="secretpass")
    token = conn.execute("SELECT token FROM sessions").fetchone()["token"]

    result = resend_verification(conn, token)
    assert result["email_sent"] is True

    message = smtp_sink.wait_for_message(
        to_address="renter@example.com",
        subject_contains="verification code",
    )
    code = smtp_sink.extract_verification_code(message)
    assert len(code) == 6


def test_signup_survives_smtp_auth_failure(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbmod.DB_PATH = tmp_path / "smtp-fail.db"
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EASYHOUSE_SMTP_HOST", raising=False)

    save_service_smtp(
        host="smtp.example.com",
        port=587,
        from_address="easyHouse <alerts@example.com>",
        username="mailer@example.com",
        password="bad",
    )

    conn = get_connection()
    init_db(conn)
    with patch(
        "auth.service.send_service_email",
        side_effect=smtplib.SMTPAuthenticationError(535, b"Auth failed"),
    ):
        result = signup(conn, email="renter@example.com", password="secretpass")

    assert result["email_sent"] is False
    assert result["account"]["verified"] is False
    code = conn.execute("SELECT token FROM verification_tokens").fetchone()["token"]
    assert len(code) == 6
