from __future__ import annotations

import json
from unittest.mock import patch

from config import paths
from config.search import save_search
from services.watcher import WatcherConfig, run_watcher
from threading import Event


def _write_configs(city: str = "Amsterdam") -> None:
    paths.ensure_user_data()
    paths.get_sources_path().write_text(
        json.dumps({"platforms": [{"name": "Pararius", "type": "pararius", "enabled": True}]}),
        encoding="utf-8",
    )
    save_search(city, 10, center_lat=52.3676, center_lon=4.9041)


def test_watcher_reloads_sources_after_city_change() -> None:
    _write_configs("Amsterdam")
    seen_urls: list[str] = []
    poll_count = 0
    stop = Event()

    def fake_scrape_and_store(conn, source, *, max_pages, full_sync):
        seen_urls.append(source.url)
        return type("Result", (), {"parsed": 0, "new_count": 0, "removed_count": 0, "new_listings": [], "removed": []})()

    def fake_sleep(*_args, **_kwargs):
        nonlocal poll_count
        poll_count += 1
        if poll_count == 1:
            save_search("Rotterdam", 10, center_lat=51.9225, center_lon=4.4792)
        if poll_count >= 2:
            stop.set()

    config = WatcherConfig(skip_bootstrap=True, poll_min_sec=1, poll_max_sec=1, deep_interval_sec=0)
    with patch("services.watcher.scrape_and_store", side_effect=fake_scrape_and_store), patch(
        "services.watcher._sleep_until_next_poll", side_effect=fake_sleep
    ):
        run_watcher(config, stop_event=stop)

    assert any("amsterdam" in url for url in seen_urls)
    assert any("rotterdam" in url for url in seen_urls)
