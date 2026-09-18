from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_SEARCH_PATH = CONFIG_DIR / "search.json"

PLATFORM_TEMPLATES = {
    "pararius": "https://www.pararius.com/apartments/{slug}",
    "kamernet": "https://kamernet.nl/huren/appartement-{slug}",
    "funda": "https://www.funda.nl/huur/{slug}/",
    "huurwoningen": "https://www.huurwoningen.nl/in/{slug}/",
    "housinganywhere": "https://housinganywhere.com/s/{display}--Netherlands",
}


@dataclass(frozen=True)
class SearchConfig:
    city: str
    radius_km: float
    center_lat: float | None = None
    center_lon: float | None = None

    @property
    def slug(self) -> str:
        return city_slug(self.city)

    @property
    def id(self) -> str:
        return self.slug

    def to_dict(self) -> dict[str, float | str | None]:
        return {
            "city": self.city,
            "radius_km": self.radius_km,
            "center_lat": self.center_lat,
            "center_lon": self.center_lon,
        }


def city_slug(city: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")
    return slug or "city"


def city_display(city: str) -> str:
    parts = re.split(r"[\s-]+", city.strip())
    return "-".join(part.capitalize() for part in parts if part)


def build_platform_url(platform: str, city: str) -> str:
    template = PLATFORM_TEMPLATES.get(platform)
    if template is None:
        raise ValueError(f"Unknown platform: {platform}")
    slug = city_slug(city)
    if platform == "housinganywhere":
        return template.format(display=city_display(city))
    return template.format(slug=slug)


def load_search(path: str | Path | None = None) -> SearchConfig:
    config_path = Path(path or DEFAULT_SEARCH_PATH)
    if not config_path.exists():
        return SearchConfig(city="Amsterdam", radius_km=10.0)

    data = json.loads(config_path.read_text(encoding="utf-8"))
    city = str(data.get("city", "Amsterdam")).strip() or "Amsterdam"
    radius_km = float(data.get("radius_km", 10))
    center_lat = data.get("center_lat")
    center_lon = data.get("center_lon")
    return SearchConfig(
        city=city,
        radius_km=max(0.5, radius_km),
        center_lat=float(center_lat) if center_lat is not None else None,
        center_lon=float(center_lon) if center_lon is not None else None,
    )


def save_search(
    city: str,
    radius_km: float,
    *,
    center_lat: float | None = None,
    center_lon: float | None = None,
    path: str | Path | None = None,
) -> SearchConfig:
    config_path = Path(path or DEFAULT_SEARCH_PATH)
    cleaned_city = city.strip()
    if not cleaned_city:
        raise ValueError("City is required")

    payload = {
        "city": cleaned_city,
        "radius_km": max(0.5, float(radius_km)),
    }
    if center_lat is not None and center_lon is not None:
        payload["center_lat"] = center_lat
        payload["center_lon"] = center_lon

    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return load_search(config_path)
