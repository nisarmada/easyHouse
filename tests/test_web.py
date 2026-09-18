from __future__ import annotations

import json
from pathlib import Path

import db.db as dbmod
from fastapi.testclient import TestClient
from web.app import app


def test_dashboard_and_sources_api(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "sources.json"
    search_path = tmp_path / "search.json"
    config_path.write_text(
        json.dumps(
            {
                "platforms": [
                    {"name": "Pararius", "type": "pararius", "enabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    search_path.write_text(
        json.dumps({"city": "Amsterdam", "radius_km": 10, "center_lat": 52.3676, "center_lon": 4.9041}),
        encoding="utf-8",
    )
    monkeypatch.setattr("config.load.DEFAULT_SOURCES_PATH", config_path)
    monkeypatch.setattr("config.search.DEFAULT_SEARCH_PATH", search_path)
    monkeypatch.setattr("web.app.DEFAULT_SOURCES_PATH", config_path)

    dbmod.DB_PATH = tmp_path / "web-test.db"
    client = TestClient(app)

    assert client.get("/api/health").status_code == 200
    stats = client.get("/api/stats").json()
    assert "canonical_count" in stats

    sources = client.get("/api/sources").json()["sources"]
    assert len(sources) == 1
    assert sources[0]["type"] == "pararius"
    assert "amsterdam" in sources[0]["url"]

    search = client.get("/api/search").json()
    assert search["city"] == "Amsterdam"
    assert search["radius_km"] == 10

    page = client.get("/")
    assert page.status_code == 200
    assert "easyHouse" in page.text


def test_update_sources_validation(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "sources.json"
    search_path = tmp_path / "search.json"
    config_path.write_text(
        json.dumps({"platforms": [{"name": "Pararius", "type": "pararius", "enabled": True}]}),
        encoding="utf-8",
    )
    search_path.write_text(json.dumps({"city": "Amsterdam", "radius_km": 10}), encoding="utf-8")
    monkeypatch.setattr("config.load.DEFAULT_SOURCES_PATH", config_path)
    monkeypatch.setattr("config.search.DEFAULT_SEARCH_PATH", search_path)
    monkeypatch.setattr("web.app.DEFAULT_SOURCES_PATH", config_path)

    client = TestClient(app)
    response = client.put(
        "/api/sources",
        json={"sources": [{"name": "Bad", "type": "unknown", "enabled": True}]},
    )
    assert response.status_code == 400
