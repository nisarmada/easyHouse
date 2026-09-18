from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from config.search import SearchConfig, build_platform_url, load_search

CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCES_PATH = CONFIG_DIR / "sources.json"

DEFAULT_PLATFORMS = (
    {"name": "Pararius", "type": "pararius", "enabled": True},
    {"name": "Kamernet", "type": "kamernet", "enabled": True},
    {"name": "Funda", "type": "funda", "enabled": True},
    {"name": "Huurwoningen", "type": "huurwoningen", "enabled": True},
    {"name": "HousingAnywhere", "type": "housinganywhere", "enabled": True},
)

PLATFORM_TYPES = {
    "pararius.com": "pararius",
    "kamernet.nl": "kamernet",
    "funda.nl": "funda",
    "huurwoningen.nl": "huurwoningen",
    "housinganywhere.com": "housinganywhere",
}


@dataclass(frozen=True)
class SourceConfig:
    name: str
    url: str
    enabled: bool
    type: str
    id: str


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "source"


def _infer_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for needle, platform in PLATFORM_TYPES.items():
        if needle in host:
            return platform
    raise ValueError(f"Cannot infer scraper type from URL: {url}")


def _legacy_sources_to_platforms(sources: list[dict]) -> list[dict]:
    platforms: list[dict] = []
    for source in sources:
        platforms.append(
            {
                "name": source["name"],
                "type": _infer_type(source["url"]),
                "enabled": bool(source.get("enabled", True)),
            }
        )
    return platforms


def load_sources_raw(path: str | Path | None = None) -> dict:
    config_path = Path(path or DEFAULT_SOURCES_PATH)
    return json.loads(config_path.read_text(encoding="utf-8"))


def _write_sources_file(config_path: Path, data: dict) -> None:
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def ensure_sources_config(path: str | Path | None = None) -> None:
    """
    Normalize sources.json so both legacy (sources) and new (platforms) layouts work.
    """
    config_path = Path(path or DEFAULT_SOURCES_PATH)
    if not config_path.exists():
        _write_sources_file(
            config_path,
            {"platforms": [dict(platform) for platform in DEFAULT_PLATFORMS]},
        )
        ensure_sources_config(config_path)
        return

    data = load_sources_raw(config_path)
    changed = False

    platforms = data.get("platforms")
    if not platforms and data.get("sources"):
        platforms = _legacy_sources_to_platforms(data["sources"])
        data["platforms"] = platforms
        changed = True

    if not platforms:
        data["platforms"] = [dict(platform) for platform in DEFAULT_PLATFORMS]
        changed = True

    payload = {"platforms": data["platforms"]}
    if changed or data != payload:
        _write_sources_file(config_path, payload)


def _platform_rows(path: str | Path | None = None) -> list[dict]:
    config_path = Path(path or DEFAULT_SOURCES_PATH)
    ensure_sources_config(config_path)
    data = load_sources_raw(config_path)
    platforms = data.get("platforms") or []
    if platforms:
        return platforms
    if data.get("sources"):
        return _legacy_sources_to_platforms(data["sources"])
    raise ValueError(f"No platforms defined in {config_path}")


def load_sources(
    path: str | Path | None = None,
    *,
    search: SearchConfig | None = None,
) -> tuple[SourceConfig, ...]:
    search_config = search or load_search()
    platforms = _platform_rows(path)

    sources = tuple(
        SourceConfig(
            name=platform["name"],
            url=build_platform_url(platform["type"], search_config.city),
            enabled=bool(platform.get("enabled", True)),
            type=platform["type"],
            id=_slugify(platform["name"]),
        )
        for platform in platforms
    )

    if not sources:
        raise ValueError("No platforms defined")

    return sources


def enabled_sources(path: str | Path | None = None) -> list[SourceConfig]:
    return [source for source in load_sources(path) if source.enabled]


def get_source(source_key: str, path: str | Path | None = None) -> SourceConfig:
    key = source_key.lower()
    for source in load_sources(path):
        if source.id == key or source.name.lower() == key or source.type == key:
            return source
    known = ", ".join(source.name for source in load_sources(path))
    raise ValueError(f"Unknown source {source_key!r}. Known sources: {known}")


def save_platforms(platforms: list[dict], path: str | Path | None = None) -> tuple[SourceConfig, ...]:
    config_path = Path(path or DEFAULT_SOURCES_PATH)
    cleaned: list[dict] = []

    for platform in platforms:
        name = str(platform["name"]).strip()
        platform_type = str(platform["type"]).strip()
        if not name or not platform_type:
            raise ValueError("Each platform needs a name and type")
        build_platform_url(platform_type, load_search().city)
        cleaned.append(
            {
                "name": name,
                "type": platform_type,
                "enabled": bool(platform.get("enabled", True)),
            }
        )

    if not cleaned:
        raise ValueError("At least one platform is required")

    payload = {"platforms": cleaned}
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return load_sources(config_path)
