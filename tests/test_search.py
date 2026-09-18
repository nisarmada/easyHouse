from __future__ import annotations

import json
from pathlib import Path

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


def test_load_sources_uses_search_city(tmp_path: Path, monkeypatch) -> None:
    sources_path = tmp_path / "sources.json"
    search_path = tmp_path / "search.json"
    sources_path.write_text(
        json.dumps({"platforms": [{"name": "Pararius", "type": "pararius", "enabled": True}]}),
        encoding="utf-8",
    )
    search_path.write_text(json.dumps({"city": "Rotterdam", "radius_km": 8}), encoding="utf-8")

    monkeypatch.setattr("config.search.DEFAULT_SEARCH_PATH", search_path)
    monkeypatch.setattr("config.load.load_search", lambda path=None: load_search(search_path))

    sources = load_sources(sources_path, search=load_search(search_path))
    assert "rotterdam" in sources[0].url


def test_save_search_persists_center(tmp_path: Path, monkeypatch) -> None:
    search_path = tmp_path / "search.json"
    monkeypatch.setattr("config.search.DEFAULT_SEARCH_PATH", search_path)

    saved = save_search("Utrecht", 12, center_lat=52.09, center_lon=5.12)
    assert saved.city == "Utrecht"
    assert saved.radius_km == 12
    assert saved.center_lat == 52.09
