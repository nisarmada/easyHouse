from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from config.paths import get_auth_url


class RemoteAuthError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = get_auth_url()
    if not base:
        raise RemoteAuthError("Remote auth is not configured")

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        f"{base}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = detail
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict) and parsed.get("detail"):
                message = str(parsed["detail"])
        except json.JSONDecodeError:
            pass
        raise RemoteAuthError(message or f"Remote auth failed ({exc.code})", exc.code) from exc
    except urllib.error.URLError as exc:
        raise RemoteAuthError(f"Could not reach auth service: {exc.reason}") from exc


def remote_signup(*, email: str, password: str) -> dict[str, Any]:
    return _request("POST", "/auth/signup", payload={"email": email, "password": password})


def remote_login(*, email: str, password: str) -> dict[str, Any]:
    return _request("POST", "/auth/login", payload={"email": email, "password": password})


def remote_logout(token: str | None) -> None:
    if token:
        _request("POST", "/auth/logout", token=token)


def remote_verify(*, code: str) -> dict[str, Any]:
    return _request("POST", "/auth/verify", payload={"code": code})


def remote_resend(token: str) -> dict[str, Any]:
    return _request("POST", "/auth/resend-verification", token=token)


def remote_update_alerts(token: str, *, enabled: bool) -> dict[str, Any]:
    return _request("PUT", "/auth/alerts", token=token, payload={"enabled": enabled})


def remote_status(token: str | None) -> dict[str, Any]:
    return _request("GET", "/auth/status", token=token)


def remote_notify(token: str, listings: list[dict[str, Any]]) -> dict[str, Any]:
    return _request("POST", "/auth/notify", token=token, payload={"listings": listings})


def remote_health() -> dict[str, Any]:
    return _request("GET", "/health")
