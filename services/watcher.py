from __future__ import annotations

import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from config.load import SourceConfig, enabled_sources
from config.paths import get_sources_path
from config.search_service import filter_listings_by_radius
from db.db import get_connection, init_db
from services.scrape_coordination import begin_scrape, end_scrape, is_cancelled
from services.scrape_runner import scrape_and_store

if TYPE_CHECKING:
    from scrapers.listing import Listing

MAX_DETECTION_BUDGET_SEC = 300
POLL_INTERVAL_MIN_SEC = 45
POLL_INTERVAL_MAX_SEC = 90
DEFAULT_DEEP_INTERVAL_SEC = 1800

BACKOFF_STEPS_SEC = (30, 60, 180, 300)
PAUSE_AFTER_FAILURES = 4


@dataclass
class WatcherConfig:
    config_path: str | Path | None = None
    deep_interval_sec: int = DEFAULT_DEEP_INTERVAL_SEC
    skip_bootstrap: bool = False
    poll_min_sec: int = POLL_INTERVAL_MIN_SEC
    poll_max_sec: int = POLL_INTERVAL_MAX_SEC


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _log(message: str) -> None:
    print(message, flush=True)


def _print_new_listings(new_listings: list[Listing]) -> None:
    for listing in new_listings:
        price = f"€{listing.price_eur:,}" if listing.price_eur else "?"
        _log(f"NEW  {price:>10}  {listing.title}  {listing.url}")


def _print_removed_listings(removed) -> None:
    for row in removed:
        _log(f"GONE             {row['title']}  {row['url']}")


def _run_poll(
    conn: sqlite3.Connection,
    source: SourceConfig,
    *,
    max_pages: int | None,
    label: str,
    full_sync: bool,
) -> tuple[int, int, int]:
    result = scrape_and_store(
        conn,
        source,
        max_pages=max_pages,
        full_sync=full_sync,
    )
    _log(
        f"[{_now()}] {label} [{source.name}]: parsed {result.parsed}, "
        f"new {result.new_count}, removed {result.removed_count}"
    )
    _print_new_listings(filter_listings_by_radius(conn, result.new_listings))
    _print_removed_listings(result.removed)
    return result.parsed, result.new_count, result.removed_count


def _failure_backoff_sec(consecutive_failures: int) -> int:
    if consecutive_failures <= 0:
        return 0
    index = min(consecutive_failures - 1, len(BACKOFF_STEPS_SEC) - 1)
    return BACKOFF_STEPS_SEC[index]


def _sleep_until_next_poll(
    loop_start: float,
    *,
    poll_min: int,
    poll_max: int,
    extra_delay: int = 0,
    stop_event: Event | None = None,
) -> None:
    delay = random.uniform(poll_min, poll_max) + extra_delay
    elapsed = time.monotonic() - loop_start
    sleep_for = max(0.0, delay - elapsed)
    if sleep_for <= 0:
        return

    _log(f"[{_now()}] Sleeping {sleep_for:.0f}s until next poll")
    deadline = time.monotonic() + sleep_for
    while time.monotonic() < deadline:
        if stop_event is not None and stop_event.is_set():
            return
        time.sleep(min(1.0, deadline - time.monotonic()))


def validate_watcher_config(config: WatcherConfig) -> None:
    if config.poll_min_sec > config.poll_max_sec:
        raise ValueError("poll_min_sec must be <= poll_max_sec")
    if config.poll_max_sec > MAX_DETECTION_BUDGET_SEC:
        raise ValueError(
            f"poll_max_sec must be <= {MAX_DETECTION_BUDGET_SEC} (detection budget)"
        )


def run_watcher(config: WatcherConfig, *, stop_event: Event | None = None) -> None:
    """
    Bootstrap (optional), then poll enabled sources until stop_event is set.

    Raises ValueError when config is invalid or no sources are enabled.
    Raises RuntimeError when bootstrap fails for any source.
    """
    validate_watcher_config(config)

    config_path = config.config_path or get_sources_path()
    conn = get_connection()
    init_db(conn)

    def _current_sources() -> list[SourceConfig]:
        sources = enabled_sources(config_path)
        if not sources:
            raise ValueError("No enabled platforms — enable at least one in the web UI under Platforms")
        return sources

    sources = _current_sources()
    source_names = ", ".join(source.name for source in sources)
    _log(f"[{_now()}] Watching {len(sources)} source(s): {source_names}")
    for source in sources:
        _log(f"  - {source.name}: {source.url}")

    if not config.skip_bootstrap:
        _log(f"[{_now()}] Bootstrap: scraping all pages and syncing DB...")
        generation = begin_scrape()
        try:
            for source in _current_sources():
                if stop_event is not None and stop_event.is_set() or is_cancelled(generation):
                    _log(f"[{_now()}] Bootstrap interrupted.")
                    return
                try:
                    _run_poll(
                        conn,
                        source,
                        max_pages=None,
                        label="bootstrap",
                        full_sync=True,
                    )
                except Exception as exc:
                    _log(f"[{_now()}] Bootstrap failed for {source.name}: {exc}")
                    raise RuntimeError(f"Bootstrap failed for {source.name}") from exc
        finally:
            end_scrape()

    _log(
        f"[{_now()}] Fast poll: page 1 every {config.poll_min_sec}–{config.poll_max_sec}s (randomized) | "
        f"Full sync: {'off' if config.deep_interval_sec == 0 else f'every {config.deep_interval_sec}s when healthy'}"
    )

    last_deep_at = time.monotonic()
    consecutive_failures = 0

    while stop_event is None or not stop_event.is_set():
        loop_start = time.monotonic()
        extra_delay = 0

        due_for_deep = (
            config.deep_interval_sec > 0
            and consecutive_failures < 2
            and (loop_start - last_deep_at) >= config.deep_interval_sec
        )

        if due_for_deep:
            label = "full sync"
            max_pages = None
            full_sync = True
        else:
            label = "fast poll"
            max_pages = 1
            full_sync = False

        loop_failed = False
        generation = begin_scrape()
        try:
            sources = _current_sources()
            for source in sources:
                if stop_event is not None and stop_event.is_set() or is_cancelled(generation):
                    break
                try:
                    _run_poll(
                        conn,
                        source,
                        max_pages=max_pages,
                        label=label,
                        full_sync=full_sync,
                    )
                except Exception as exc:
                    loop_failed = True
                    _log(f"[{_now()}] {label} failed for {source.name}: {exc}")
        finally:
            end_scrape()

        if stop_event is not None and stop_event.is_set():
            break

        if loop_failed:
            consecutive_failures += 1
            extra_delay = _failure_backoff_sec(consecutive_failures)
            _log(
                f"[{_now()}] Poll cycle had failures "
                f"({consecutive_failures} in a row)"
            )
            if extra_delay:
                _log(f"[{_now()}] Backing off an extra {extra_delay}s before next poll")
            if consecutive_failures >= PAUSE_AFTER_FAILURES:
                _log(
                    f"[{_now()}] Many failures — staying in slow mode. "
                    "Consider waiting before restarting or checking your network."
                )
        else:
            consecutive_failures = 0
            if due_for_deep:
                last_deep_at = time.monotonic()

        _sleep_until_next_poll(
            loop_start,
            poll_min=config.poll_min_sec,
            poll_max=config.poll_max_sec,
            extra_delay=extra_delay,
            stop_event=stop_event,
        )

    _log(f"[{_now()}] Watcher stopped.")
