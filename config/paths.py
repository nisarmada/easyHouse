from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_CONFIG_DIR = PROJECT_ROOT / "config"

_override_root: Path | None = None


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return PROJECT_ROOT


def bundled_config_dir() -> Path:
    bundled = project_root() / "config"
    if bundled.is_dir():
        return bundled
    return BUNDLED_CONFIG_DIR


def user_data_dir() -> Path:
    if _override_root is not None:
        return _override_root
    override = os.environ.get("EASYHOUSE_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".easyhouse"


def set_user_data_dir(path: Path | None) -> None:
    global _override_root
    _override_root = path


def config_dir() -> Path:
    return user_data_dir() / "config"


def get_db_path() -> Path:
    return user_data_dir() / "easyhouse.db"


def get_search_path() -> Path:
    return config_dir() / "search.json"


def get_sources_path() -> Path:
    return config_dir() / "sources.json"


def get_notify_path() -> Path:
    return user_data_dir() / "notify.json"


def get_session_path() -> Path:
    return user_data_dir() / "session.json"


def get_auth_config_path() -> Path:
    return user_data_dir() / "auth.json"


def get_notification_path() -> Path:
    return user_data_dir() / "notification.json"


def bundled_auth_config_path() -> Path:
    return bundled_config_dir() / "auth.json"


def get_auth_url() -> str | None:
    override = os.environ.get("EASYHOUSE_AUTH_URL", "").strip()
    if override:
        return override.rstrip("/")

    user_path = get_auth_config_path()
    if user_path.exists():
        try:
            data = json.loads(user_path.read_text(encoding="utf-8"))
            url = str(data.get("auth_url", "")).strip().rstrip("/")
            if url and "YOUR_SUBDOMAIN" not in url:
                return url
        except (json.JSONDecodeError, OSError):
            pass

    bundled = bundled_auth_config_path()
    if bundled.exists():
        try:
            data = json.loads(bundled.read_text(encoding="utf-8"))
            url = str(data.get("auth_url", "")).strip().rstrip("/")
            if url and "YOUR_SUBDOMAIN" not in url:
                return url
        except (json.JSONDecodeError, OSError):
            pass
    return None


def remote_auth_enabled() -> bool:
    return get_auth_url() is not None


def _write_default_search(path: Path) -> None:
    path.write_text(
        json.dumps({"city": "Amsterdam", "radius_km": 10.0}, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_default_sources(path: Path) -> None:
    from config.load import DEFAULT_PLATFORMS

    payload = {"platforms": [dict(platform) for platform in DEFAULT_PLATFORMS]}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_config_file(name: str, writer) -> None:
    dest = config_dir() / name
    if dest.exists():
        return
    source = bundled_config_dir() / name
    if source.exists():
        shutil.copy(source, dest)
        return
    writer(dest)


def ensure_user_data() -> Path:
    root = user_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    config_dir().mkdir(parents=True, exist_ok=True)

    _seed_config_file("search.json", _write_default_search)
    _seed_config_file("sources.json", _write_default_sources)
    return root
