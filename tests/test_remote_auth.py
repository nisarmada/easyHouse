from __future__ import annotations

from unittest.mock import patch

import db.db as dbmod
import pytest
from auth.service import auth_status, login, logout, signup, verify_email
from config.paths import get_auth_config_path, get_notification_path, get_session_path
from db.db import get_connection, init_db


def test_remote_signup_syncs_local_session_and_profile(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbmod.DB_PATH = tmp_path / "remote-auth.db"
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EASYHOUSE_AUTH_URL", "https://auth.example.test")

    remote_result = {
        "session_token": "remote-token",
        "account": {"email": "renter@example.com", "verified": False, "alerts_enabled": True},
        "email_sent": True,
        "can_send_mail": True,
    }

    conn = get_connection()
    init_db(conn)

    with patch("auth.service.remote_signup", return_value=remote_result):
        result = signup(conn, email="renter@example.com", password="secretpass")

    assert result["email_sent"] is True
    assert get_session_path().exists()
    assert get_notification_path().exists()
    profile = __import__("json").loads(get_notification_path().read_text())
    assert profile["email"] == "renter@example.com"


def test_remote_auth_status_uses_worker(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EASYHOUSE_AUTH_URL", "https://auth.example.test")

    with patch(
        "auth.service.remote_status",
        return_value={
            "signed_in": True,
            "account": {"email": "renter@example.com", "verified": True, "alerts_enabled": True},
            "can_send_mail": True,
        },
    ):
        status = auth_status("token")

    assert status["remote_auth"] is True
    assert status["signed_in"] is True
    assert status["can_send_mail"] is True


def test_get_auth_url_ignores_placeholder_template(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EASYHOUSE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EASYHOUSE_AUTH_URL", raising=False)

    from config import paths

    paths.ensure_user_data()
    get_auth_config_path().write_text(
        '{"auth_url": "https://easyhouse-auth.YOUR_SUBDOMAIN.workers.dev"}\n',
        encoding="utf-8",
    )
    assert paths.get_auth_url() is None
