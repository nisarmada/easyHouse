from __future__ import annotations

import json
from typing import Any

from config.paths import ensure_user_data, get_notification_path, get_session_path


def save_session_token(token: str) -> None:
    ensure_user_data()
    path = get_session_path()
    path.write_text(json.dumps({"token": token}, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def clear_session_token() -> None:
    path = get_session_path()
    if path.exists():
        path.unlink()


def load_session_token() -> str | None:
    path = get_session_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    token = str(data.get("token", "")).strip()
    return token or None


def save_notification_profile(
    *,
    email: str,
    verified: bool,
    alerts_enabled: bool,
    can_send_mail: bool = True,
) -> None:
    ensure_user_data()
    path = get_notification_path()
    payload = {
        "email": email,
        "verified": verified,
        "alerts_enabled": alerts_enabled,
        "can_send_mail": can_send_mail,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def clear_notification_profile() -> None:
    path = get_notification_path()
    if path.exists():
        path.unlink()


def load_notification_profile() -> dict[str, Any] | None:
    path = get_notification_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    email = str(data.get("email", "")).strip()
    if not email:
        return None
    return {
        "email": email,
        "verified": bool(data.get("verified")),
        "alerts_enabled": bool(data.get("alerts_enabled")),
        "can_send_mail": bool(data.get("can_send_mail", True)),
    }


def sync_account_state(account: dict[str, Any] | None, *, can_send_mail: bool = True) -> None:
    if account is None:
        clear_notification_profile()
        return
    save_notification_profile(
        email=str(account["email"]),
        verified=bool(account.get("verified")),
        alerts_enabled=bool(account.get("alerts_enabled")),
        can_send_mail=can_send_mail,
    )
