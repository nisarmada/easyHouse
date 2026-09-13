from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCES_PATH = CONFIG_DIR / "sources.json"


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
    if "pararius.com" in host:
        return "pararius"
    if "kamernet.nl" in host:
        return "kamernet"
    if "funda.nl" in host:
        return "funda"
    if "huurwoningen.nl" in host:
        return "huurwoningen"
    if "housinganywhere.com" in host:
        return "housinganywhere"
    raise ValueError(f"Cannot infer scraper type from URL: {url}")


def load_sources(path: str | Path = DEFAULT_SOURCES_PATH) -> tuple[SourceConfig, ...]:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))

    sources = tuple(
        SourceConfig(
            name=source["name"],
            url=source["url"],
            enabled=bool(source.get("enabled", True)),
            type=_infer_type(source["url"]),
            id=_slugify(source["name"]),
        )
        for source in data.get("sources", [])
    )

    if not sources:
        raise ValueError(f"No sources defined in {config_path}")

    return sources


def enabled_sources(path: str | Path = DEFAULT_SOURCES_PATH) -> list[SourceConfig]:
    return [source for source in load_sources(path) if source.enabled]


def get_source(source_key: str, path: str | Path = DEFAULT_SOURCES_PATH) -> SourceConfig:
    key = source_key.lower()
    for source in load_sources(path):
        if source.id == key or source.name.lower() == key:
            return source
    known = ", ".join(source.name for source in load_sources(path))
    raise ValueError(f"Unknown source {source_key!r}. Known sources: {known}")
