from __future__ import annotations

import db.db as dbmod
import pytest
from fastapi.testclient import TestClient
from notify.smtp_config import save_service_smtp
from tests.local_smtp_sink import LocalSmtpSink
from tests.test_web import _write_test_configs
from web.app import app


@pytest.fixture
def smtp_sink() -> LocalSmtpSink:
    sink = LocalSmtpSink()
    sink.start()
    try:
        yield sink
    finally:
        sink.stop()


def test_signup_api_delivers_verification_email(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    smtp_sink: LocalSmtpSink,
) -> None:
    dbmod.DB_PATH = tmp_path / "api-delivery.db"
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EASYHOUSE_SMTP_HOST", raising=False)
    _write_test_configs()

    save_service_smtp(
        host="127.0.0.1",
        port=smtp_sink.port,
        from_address="easyHouse <alerts@easyhouse.test>",
        use_tls=False,
    )

    client = TestClient(app)
    response = client.post(
        "/api/auth/signup",
        json={"email": "renter@example.com", "password": "secretpass"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email_sent"] is True

    message = smtp_sink.wait_for_message(
        to_address="renter@example.com",
        subject_contains="verification code",
    )
    code = smtp_sink.extract_verification_code(message)
    verified = client.post("/api/auth/verify", json={"code": code})
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
