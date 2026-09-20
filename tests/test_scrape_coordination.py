from __future__ import annotations

import json
import threading
import time
from unittest.mock import patch

from config import paths
from config.load import load_sources
from config.search import save_search
from services.scrape_coordination import cancel_current_scrape, is_cancelled
from services.scrape_runner import ScrapeResult, run_scrape
from web.jobs import JobManager


def _write_configs(city: str = "Amsterdam") -> None:
    paths.ensure_user_data()
    paths.get_sources_path().write_text(
        json.dumps(
            {
                "platforms": [
                    {"name": "Pararius", "type": "pararius", "enabled": True},
                    {"name": "Funda", "type": "funda", "enabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    save_search(city, 10, center_lat=52.3676, center_lon=4.9041)


def test_load_sources_reflects_city_change() -> None:
    _write_configs("Amsterdam")
    amsterdam_urls = {source.url for source in load_sources()}
    assert all("amsterdam" in url for url in amsterdam_urls)

    save_search("Rotterdam", 10, center_lat=51.9225, center_lon=4.4792)
    rotterdam_urls = {source.url for source in load_sources()}
    assert all("rotterdam" in url for url in rotterdam_urls)
    assert amsterdam_urls.isdisjoint(rotterdam_urls)


def test_cancel_current_scrape_invalidates_generation() -> None:
    from services.scrape_coordination import begin_scrape, end_scrape

    generation = begin_scrape()
    try:
        assert not is_cancelled(generation)
        cancel_current_scrape()
        assert is_cancelled(generation)
    finally:
        end_scrape()


def test_rapid_city_change_jobs_use_latest_search_config() -> None:
    _write_configs("Amsterdam")
    seen_urls: list[str] = []
    lock = threading.Lock()
    first_started = threading.Event()
    release_first = threading.Event()

    def fake_scrape_and_store(conn, source, *, max_pages, full_sync):
        with lock:
            seen_urls.append(source.url)
        if not first_started.is_set():
            first_started.set()
            release_first.wait(timeout=2)
        return ScrapeResult(source_name=source.name, parsed=1, new_count=0, removed_count=0)

    manager = JobManager()
    with patch("services.scrape_runner.scrape_and_store", side_effect=fake_scrape_and_store):
        job1 = manager.start_scrape(max_pages=None, full_sync=True)
        assert first_started.wait(timeout=2)

        save_search("Rotterdam", 10, center_lat=51.9225, center_lon=4.4792)
        job2 = manager.start_scrape(max_pages=None, full_sync=True)
        release_first.set()

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            j2 = manager.get(job2.id)
            if j2 and j2.status in {"completed", "cancelled", "failed"}:
                break
            time.sleep(0.05)

        j1 = manager.get(job1.id)
        j2 = manager.get(job2.id)
        assert j1 is not None and j2 is not None
        assert j1.status == "cancelled"
        assert j2.status == "completed"
        assert any("rotterdam" in url for url in seen_urls)
        assert not any(url.endswith("/amsterdam") or "/amsterdam/" in url for url in seen_urls if "rotterdam" in url)
