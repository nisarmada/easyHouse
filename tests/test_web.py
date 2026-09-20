from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import db.db as dbmod
from config import paths
from fastapi.testclient import TestClient
from web.app import app


def _write_test_configs() -> None:
    paths.ensure_user_data()
    paths.get_sources_path().write_text(
        json.dumps({"platforms": [{"name": "Pararius", "type": "pararius", "enabled": True}]}),
        encoding="utf-8",
    )
    paths.get_search_path().write_text(
        json.dumps({"city": "Amsterdam", "radius_km": 10, "center_lat": 52.3676, "center_lon": 4.9041}),
        encoding="utf-8",
    )


def test_dashboard_and_sources_api(tmp_path: Path) -> None:
    _write_test_configs()
    dbmod.DB_PATH = tmp_path / "web-test.db"
    client = TestClient(app)

    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert "data_dir" in health

    stats = client.get("/api/stats").json()
    assert "canonical_count" in stats

    sources = client.get("/api/sources").json()["sources"]
    assert len(sources) == 1
    assert sources[0]["type"] == "pararius"
    assert "amsterdam" in sources[0]["url"]

    search = client.get("/api/search").json()
    assert search["city"] == "Amsterdam"
    assert search["radius_km"] == 10

    landing = client.get("/")
    assert landing.status_code == 200
    assert "Housing is a human need" in landing.text
    assert "/app?view=search" in landing.text

    dashboard = client.get("/app")
    assert dashboard.status_code == 200
    assert "Choose where to search" in dashboard.text
    assert "easyHouse" in dashboard.text


def test_update_sources_validation() -> None:
    _write_test_configs()
    client = TestClient(app)
    response = client.put(
        "/api/sources",
        json={"sources": [{"name": "Bad", "type": "unknown", "enabled": True}]},
    )
    assert response.status_code == 400


def test_auth_signup_and_verify_api(monkeypatch: pytest.MonkeyPatch) -> None:
    _write_test_configs()
    monkeypatch.setenv("EASYHOUSE_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EASYHOUSE_SMTP_FROM", "easyHouse <alerts@example.com>")
    client = TestClient(app)

    with patch("auth.service.send_service_email"):
        signup = client.post(
            "/api/auth/signup",
            json={"email": "renter@example.com", "password": "secretpass"},
        )
    assert signup.status_code == 200
    body = signup.json()
    assert body["account"]["email"] == "renter@example.com"
    assert body["account"]["verified"] is False
    token = body["session_token"]

    status = client.get("/api/auth/status", headers={"Authorization": f"Bearer {token}"})
    assert status.json()["signed_in"] is True

    conn = dbmod.get_connection()
    dbmod.init_db(conn)
    verify_code = conn.execute("SELECT token FROM verification_tokens").fetchone()["token"]
    verified = client.post("/api/auth/verify", json={"code": verify_code})
    assert verified.status_code == 200
    assert verified.json()["verified"] is True

    alerts = client.put(
        "/api/auth/alerts",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert alerts.status_code == 200
    assert alerts.json()["alerts_enabled"] is True


def test_autostart_status_api() -> None:
    client = TestClient(app)
    response = client.get("/api/agent/autostart")
    assert response.status_code == 200
    body = response.json()
    assert "platform" in body
    assert "supported" in body
    assert "installed" in body


def test_cities_api() -> None:
    client = TestClient(app)
    response = client.get("/api/cities")
    assert response.status_code == 200
    cities = response.json()["cities"]
    assert any(city["name"] == "Amsterdam" for city in cities)
    amsterdam = next(city for city in cities if city["name"] == "Amsterdam")
    assert "Jordaan" in amsterdam["neighborhoods"]


def test_search_geocode_and_save_with_neighborhood() -> None:
    _write_test_configs()
    client = TestClient(app)

    geocode = client.post(
        "/api/search/geocode",
        json={"city": "Amsterdam", "neighborhood": "Jordaan"},
    )
    assert geocode.status_code == 200
    body = geocode.json()
    assert body["center_lat"]
    assert body["center_lon"]
    assert body["label"] == "Jordaan, Amsterdam"

    with patch("web.app.job_manager.start_scrape") as mock_scrape:
        saved = client.put(
            "/api/search",
            json={
                "city": "Amsterdam",
                "neighborhood": "Jordaan",
                "radius_km": 5,
                "center_lat": body["center_lat"],
                "center_lon": body["center_lon"],
            },
        )
        assert saved.status_code == 200
        search = saved.json()
        assert search["neighborhood"] == "Jordaan"
        assert search["radius_km"] == 5
        mock_scrape.assert_not_called()


def test_update_search_triggers_scrape_on_city_change() -> None:
    _write_test_configs()
    client = TestClient(app)

    with patch("web.app.job_manager.start_scrape") as mock_scrape:
        mock_scrape.return_value.id = "job-123"
        mock_scrape.return_value.status = "pending"
        mock_scrape.return_value.created_at = "2026-01-01T00:00:00+00:00"
        mock_scrape.return_value.finished_at = None
        mock_scrape.return_value.params = {"full_sync": True, "max_pages": None, "source_id": None}
        mock_scrape.return_value.results = []
        mock_scrape.return_value.error = None

        response = client.put(
            "/api/search",
            json={"city": "Rotterdam", "radius_km": 10},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["city"] == "Rotterdam"
        assert body["scrape_job"]["id"] == "job-123"
        mock_scrape.assert_called_once_with(max_pages=None, full_sync=True)


def test_update_search_radius_only_does_not_scrape() -> None:
    _write_test_configs()
    client = TestClient(app)

    with patch("web.app.job_manager.start_scrape") as mock_scrape:
        response = client.put(
            "/api/search",
            json={"city": "Amsterdam", "radius_km": 15},
        )
        assert response.status_code == 200
        assert response.json()["radius_km"] == 15
        assert "scrape_job" not in response.json()
        mock_scrape.assert_not_called()
