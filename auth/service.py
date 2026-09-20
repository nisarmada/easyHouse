from __future__ import annotations

import sqlite3
from typing import Any

from auth.local_cache import (
    clear_notification_profile,
    clear_session_token,
    load_notification_profile,
    load_session_token,
    save_session_token,
    sync_account_state,
)
from auth.passwords import hash_password, verify_password
from auth.remote import RemoteAuthError, remote_login, remote_logout, remote_resend, remote_signup, remote_status, remote_update_alerts, remote_verify
from auth.store import (
    account_to_public,
    consume_verification_code,
    create_account,
    create_session,
    create_verification_code,
    delete_session,
    get_account_by_email,
    get_session_account,
    set_alerts_enabled,
)
from config.paths import remote_auth_enabled
from db.db import get_connection, init_db
from notify.email import send_service_email


def _validate_email(email: str) -> str:
    cleaned = email.strip().lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise ValueError("Enter a valid email address")
    return cleaned


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")


def _normalize_verification_code(code: str) -> str:
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) != 6:
        raise ValueError("Enter the 6-digit verification code")
    return digits


def _generate_verification_code() -> str:
    import secrets

    return f"{secrets.randbelow(1_000_000):06d}"


def _send_verification_email(email: str, code: str) -> None:
    subject = "Your easyHouse verification code"
    plain = (
        "Welcome to easyHouse.\n\n"
        f"Your verification code is: {code}\n\n"
        "Enter this code in the app to confirm your email and receive rental alerts.\n"
        "The code expires in 15 minutes."
    )
    html = (
        "<html><body>"
        "<p>Welcome to easyHouse.</p>"
        "<p>Your verification code is:</p>"
        f'<p style="font-size:28px;font-weight:700;letter-spacing:4px">{code}</p>'
        "<p>Enter this code in the app to confirm your email and receive rental alerts.</p>"
        "<p>The code expires in 15 minutes.</p>"
        "</body></html>"
    )
    send_service_email(to_address=email, subject=subject, plain_body=plain, html_body=html)


def _log_verification_code(email: str, code: str) -> None:
    print(f"[easyHouse] Verification code for {email}: {code}", flush=True)


def _issue_verification_code(conn: sqlite3.Connection, account_id: str, email: str) -> bool:
    code = _generate_verification_code()
    create_verification_code(conn, account_id, code)
    try:
        _send_verification_email(email, code)
        return True
    except Exception as exc:
        _log_verification_code(email, code)
        print(f"[easyHouse] Could not send verification email: {exc}", flush=True)
        return False


def _start_session(conn: sqlite3.Connection, account_id: str) -> str:
    import secrets

    token = secrets.token_urlsafe(32)
    create_session(conn, account_id, token)
    save_session_token(token)
    return token


def _apply_remote_auth_result(result: dict[str, Any]) -> dict[str, Any]:
    token = str(result.get("session_token", "")).strip()
    if token:
        save_session_token(token)
    account = result.get("account")
    can_send_mail = bool(result.get("can_send_mail", True))
    if isinstance(account, dict):
        sync_account_state(account, can_send_mail=can_send_mail)
    return result


def signup(conn: sqlite3.Connection, *, email: str, password: str) -> dict[str, Any]:
    if remote_auth_enabled():
        try:
            result = remote_signup(email=email, password=password)
        except RemoteAuthError as exc:
            raise ValueError(str(exc)) from exc
        return _apply_remote_auth_result(result)

    cleaned_email = _validate_email(email)
    _validate_password(password)

    if get_account_by_email(conn, cleaned_email) is not None:
        raise ValueError("An account with this email already exists")

    account = create_account(conn, email=cleaned_email, password_hash=hash_password(password))
    session_token = _start_session(conn, account["id"])
    email_sent = _issue_verification_code(conn, account["id"], cleaned_email)
    public = account_to_public(account)
    sync_account_state(public, can_send_mail=_service_smtp_configured())

    return {
        "session_token": session_token,
        "account": public,
        "email_sent": email_sent,
    }


def login(conn: sqlite3.Connection, *, email: str, password: str) -> dict[str, Any]:
    if remote_auth_enabled():
        try:
            result = remote_login(email=email, password=password)
        except RemoteAuthError as exc:
            raise ValueError(str(exc)) from exc
        return _apply_remote_auth_result(result)

    cleaned_email = _validate_email(email)
    account = get_account_by_email(conn, cleaned_email)
    if account is None or not verify_password(password, account["password_hash"]):
        raise ValueError("Invalid email or password")

    session_token = _start_session(conn, account["id"])
    public = account_to_public(account)
    sync_account_state(public, can_send_mail=_service_smtp_configured())
    return {
        "session_token": session_token,
        "account": public,
    }


def logout(conn: sqlite3.Connection, session_token: str | None) -> None:
    if remote_auth_enabled():
        try:
            remote_logout(session_token)
        except RemoteAuthError:
            pass
        clear_session_token()
        clear_notification_profile()
        return

    if session_token:
        delete_session(conn, session_token)
    clear_session_token()
    clear_notification_profile()


def verify_email(conn: sqlite3.Connection, code: str) -> dict[str, Any]:
    if remote_auth_enabled():
        try:
            account = remote_verify(code=_normalize_verification_code(code))
        except RemoteAuthError as exc:
            raise ValueError(str(exc)) from exc
        sync_account_state(account, can_send_mail=True)
        return account

    normalized = _normalize_verification_code(code)
    account = consume_verification_code(conn, normalized)
    if account is None:
        raise ValueError("Verification code is invalid or expired")
    public = account_to_public(account)
    sync_account_state(public, can_send_mail=_service_smtp_configured())
    return public


def resend_verification(conn: sqlite3.Connection, session_token: str) -> dict[str, Any]:
    if remote_auth_enabled():
        try:
            return remote_resend(session_token)
        except RemoteAuthError as exc:
            raise ValueError(str(exc)) from exc

    account = require_account(conn, session_token)
    if account["verified_at"] is not None:
        raise ValueError("Email is already verified")
    email_sent = _issue_verification_code(conn, account["id"], account["email"])
    return {"status": "sent", "email_sent": email_sent}


def require_account(conn: sqlite3.Connection, session_token: str | None) -> sqlite3.Row:
    if not session_token:
        raise ValueError("Not signed in")
    account = get_session_account(conn, session_token)
    if account is None:
        raise ValueError("Session expired — sign in again")
    return account


def get_current_account(conn: sqlite3.Connection, session_token: str | None) -> dict[str, Any] | None:
    if remote_auth_enabled():
        try:
            status = remote_status(session_token)
        except RemoteAuthError:
            return None
        account = status.get("account")
        if isinstance(account, dict):
            sync_account_state(account, can_send_mail=bool(status.get("can_send_mail", True)))
            return account
        clear_notification_profile()
        return None

    if not session_token:
        return None
    account = get_session_account(conn, session_token)
    if account is None:
        return None
    return account_to_public(account)


def get_active_notification_email(conn: sqlite3.Connection) -> str | None:
    if remote_auth_enabled():
        profile = load_notification_profile()
        if profile and profile["verified"] and profile["alerts_enabled"]:
            return profile["email"]
        return None

    token = load_session_token()
    if not token:
        return None
    account = get_session_account(conn, token)
    if account is None:
        return None
    if account["verified_at"] is None or not account["alerts_enabled"]:
        return None
    return account["email"]


def update_alerts(conn: sqlite3.Connection, session_token: str, *, enabled: bool) -> dict[str, Any]:
    if remote_auth_enabled():
        try:
            account = remote_update_alerts(session_token, enabled=enabled)
        except RemoteAuthError as exc:
            raise ValueError(str(exc)) from exc
        sync_account_state(account, can_send_mail=True)
        return account

    account = require_account(conn, session_token)
    if enabled and account["verified_at"] is None:
        raise ValueError("Verify your email before enabling alerts")
    set_alerts_enabled(conn, account["id"], enabled)
    refreshed = get_account_by_email(conn, account["email"])
    assert refreshed is not None
    public = account_to_public(refreshed)
    sync_account_state(public, can_send_mail=_service_smtp_configured())
    return public


def auth_status(session_token: str | None) -> dict[str, Any]:
    if remote_auth_enabled():
        try:
            status = remote_status(session_token)
        except RemoteAuthError as exc:
            return {
                "signed_in": False,
                "account": None,
                "can_send_mail": False,
                "remote_auth": True,
                "auth_error": str(exc),
            }
        account = status.get("account")
        if isinstance(account, dict):
            sync_account_state(account, can_send_mail=bool(status.get("can_send_mail", True)))
        return {
            "signed_in": bool(status.get("signed_in")),
            "account": account if isinstance(account, dict) else None,
            "can_send_mail": bool(status.get("can_send_mail", True)),
            "remote_auth": True,
        }

    conn = get_connection()
    init_db(conn)
    account = get_current_account(conn, session_token)
    return {
        "signed_in": account is not None,
        "account": account,
        "can_send_mail": _service_smtp_configured(),
        "remote_auth": False,
    }


def _service_smtp_configured() -> bool:
    from notify.smtp_config import load_service_smtp_config

    return load_service_smtp_config() is not None
