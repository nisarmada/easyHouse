from __future__ import annotations

import json

from config import paths
from config.load import load_sources
from config.search import build_platform_url, city_slug, load_search, save_search


def test_city_slug() -> None:
    assert city_slug("Amsterdam") == "amsterdam"
    assert city_slug("Den Haag") == "den-haag"


def test_build_platform_urls() -> None:
    assert build_platform_url("pararius", "Rotterdam") == "https://www.pararius.com/apartments/rotterdam"
    assert build_platform_url("funda", "Utrecht") == "https://www.funda.nl/huur/utrecht/"
    assert (
        build_platform_url("housinganywhere", "Den Haag")
        == "https://housinganywhere.com/s/Den-Haag--Netherlands"
    )


def test_load_sources_uses_search_city() -> None:
    paths.ensure_user_data()
    paths.get_sources_path().write_text(
        json.dumps({"platforms": [{"name": "Pararius", "type": "pararius", "enabled": True}]}),
        encoding="utf-8",
    )
    paths.get_search_path().write_text(
        json.dumps({"city": "Rotterdam", "radius_km": 8}),
        encoding="utf-8",
    )

    sources = load_sources()
    assert "rotterdam" in sources[0].url


def test_save_search_persists_center() -> None:
    paths.ensure_user_data()
    saved = save_search("Utrecht", 12, center_lat=52.09, center_lon=5.12)
    assert saved.city == "Utrecht"
    assert saved.radius_km == 12
    assert saved.center_lat == 52.09

    reloaded = load_search()
    assert reloaded.city == "Utrecht"
    assert reloaded.center_lat == 52.09
