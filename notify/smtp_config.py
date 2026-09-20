from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from config.paths import ensure_user_data, user_data_dir


@dataclass(frozen=True)
class ServiceSmtpConfig:
    host: str
    port: int
    from_address: str
    username: str | None = None
    password: str | None = None
    use_tls: bool = True


def _smtp_path():
    return user_data_dir() / "smtp.json"


def _load_file() -> dict[str, Any]:
    path = _smtp_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_file(data: dict[str, Any]) -> None:
    ensure_user_data()
    path = _smtp_path()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _config_from_mapping(data: dict[str, Any]) -> ServiceSmtpConfig | None:
    host = str(data.get("host", "")).strip()
    from_address = str(data.get("from_address", "")).strip()
    if not host or not from_address:
        return None
    username = str(data.get("username", "")).strip() or None
    password = str(data.get("password", "")).strip() or None
    return ServiceSmtpConfig(
        host=host,
        port=int(data.get("port", 587)),
        from_address=from_address,
        username=username,
        password=password,
        use_tls=bool(data.get("use_tls", True)),
    )


def load_service_smtp_config() -> ServiceSmtpConfig | None:
    file_data = _load_file()
    merged = {
        "host": os.environ.get("EASYHOUSE_SMTP_HOST", file_data.get("host", "")),
        "port": os.environ.get("EASYHOUSE_SMTP_PORT", file_data.get("port", 587)),
        "from_address": os.environ.get("EASYHOUSE_SMTP_FROM", file_data.get("from_address", "")),
        "username": os.environ.get("EASYHOUSE_SMTP_USER", file_data.get("username", "")),
        "password": os.environ.get("EASYHOUSE_SMTP_PASSWORD", file_data.get("password", "")),
        "use_tls": file_data.get("use_tls", True),
    }
    if os.environ.get("EASYHOUSE_SMTP_USE_TLS") is not None:
        merged["use_tls"] = os.environ.get("EASYHOUSE_SMTP_USE_TLS", "true")
    return _config_from_mapping(merged)


def load_service_smtp_public() -> dict[str, Any]:
    file_data = _load_file()
    config = load_service_smtp_config()
    password_from_env = bool(os.environ.get("EASYHOUSE_SMTP_PASSWORD"))
    return {
        "configured": config is not None,
        "host": file_data.get("host") or os.environ.get("EASYHOUSE_SMTP_HOST", ""),
        "port": int(file_data.get("port") or os.environ.get("EASYHOUSE_SMTP_PORT", 587)),
        "from_address": file_data.get("from_address") or os.environ.get("EASYHOUSE_SMTP_FROM", ""),
        "username": file_data.get("username") or os.environ.get("EASYHOUSE_SMTP_USER", ""),
        "use_tls": file_data.get("use_tls", True),
        "has_password": bool(file_data.get("password")) or password_from_env,
        "source": "environment" if os.environ.get("EASYHOUSE_SMTP_HOST") else "file",
    }


def parse_from_address(from_address: str) -> str | None:
    cleaned = from_address.strip()
    if not cleaned:
        return None
    if "<" in cleaned and ">" in cleaned:
        inner = cleaned.split("<", 1)[1].split(">", 1)[0].strip()
        return inner or None
    if "@" in cleaned:
        return cleaned
    return None


def save_service_smtp(
    *,
    host: str,
    port: int,
    from_address: str,
    username: str = "",
    password: str | None = None,
    use_tls: bool = True,
) -> ServiceSmtpConfig:
    cleaned_host = host.strip()
    cleaned_from = from_address.strip()
    if not cleaned_host or not cleaned_from:
        raise ValueError("SMTP host and from address are required")

    existing = _load_file()
    payload = {
        "host": cleaned_host,
        "port": int(port),
        "from_address": cleaned_from,
        "username": username.strip(),
        "use_tls": use_tls,
    }
    if password:
        payload["password"] = password
    elif existing.get("password"):
        payload["password"] = existing["password"]

    _write_file(payload)
    config = _config_from_mapping(payload)
    if config is None:
        raise ValueError("Invalid SMTP settings")
    return config
