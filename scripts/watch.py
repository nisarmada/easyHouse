from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.load import DEFAULT_SOURCES_PATH, enabled_sources
from db.db import get_connection, init_db, sync_listings, upsert_listings
from notify import notify_new_listings
from scrapers.registry import scrape_source

MAX_DETECTION_BUDGET_SEC = 300
POLL_INTERVAL_MIN_SEC = 45
POLL_INTERVAL_MAX_SEC = 90
DEFAULT_DEEP_INTERVAL_SEC = 1800

BACKOFF_STEPS_SEC = (30, 60, 180, 300)
PAUSE_AFTER_FAILURES = 4


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _print_new_listings(new_listings) -> None:
    for listing in new_listings:
        price = f"€{listing.price_eur:,}" if listing.price_eur else "?"
        print(f"NEW  {price:>10}  {listing.title}  {listing.url}")


def _print_removed_listings(removed) -> None:
    for row in removed:
        print(f"GONE             {row['title']}  {row['url']}")


def _run_poll(
    conn,
    source,
    *,
    max_pages: int | None,
    label: str,
    full_sync: bool,
) -> tuple[int, int, int]:
    listings = scrape_source(source, max_pages=max_pages)

    if full_sync:
        new_listings, removed = sync_listings(conn, listings)
    else:
        new_listings = upsert_listings(conn, listings)
        removed = []

    print(
        f"[{_now()}] {label} [{source.name}]: parsed {len(listings)}, "
        f"new {len(new_listings)}, removed {len(removed)}"
    )
    _print_new_listings(new_listings)
    notify_new_listings(new_listings)
    _print_removed_listings(removed)
    return len(listings), len(new_listings), len(removed)


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
) -> None:
    delay = random.uniform(poll_min, poll_max) + extra_delay
    elapsed = time.monotonic() - loop_start
    sleep_for = max(0.0, delay - elapsed)
    if sleep_for:
        print(f"[{_now()}] Sleeping {sleep_for:.0f}s until next poll")
        time.sleep(sleep_for)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Watch configured sources for new listings (bootstrap + fast polls)"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_SOURCES_PATH),
        help="Path to sources JSON (default: config/sources.json)",
    )
    parser.add_argument(
        "--deep-interval",
        type=int,
        default=DEFAULT_DEEP_INTERVAL_SEC,
        help=f"Seconds between full sync scans (default: {DEFAULT_DEEP_INTERVAL_SEC}, 0=disable)",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="Skip the initial full scrape (not recommended on first run)",
    )
    args = parser.parse_args()

    if POLL_INTERVAL_MIN_SEC > POLL_INTERVAL_MAX_SEC:
        parser.error("POLL_INTERVAL_MIN_SEC must be <= POLL_INTERVAL_MAX_SEC")
    if POLL_INTERVAL_MAX_SEC > MAX_DETECTION_BUDGET_SEC:
        parser.error(
            f"POLL_INTERVAL_MAX_SEC must be <= {MAX_DETECTION_BUDGET_SEC} (detection budget)"
        )

    sources = enabled_sources(args.config)
    if not sources:
        parser.error("No enabled sources in config")

    conn = get_connection()
    init_db(conn)

    source_names = ", ".join(source.name for source in sources)
    print(f"[{_now()}] Watching {len(sources)} source(s): {source_names}")
    for source in sources:
        print(f"  - {source.name}: {source.url}")

    if not args.skip_bootstrap:
        print(f"[{_now()}] Bootstrap: scraping all pages and syncing DB...")
        for source in sources:
            try:
                _run_poll(
                    conn,
                    source,
                    max_pages=None,
                    label="bootstrap",
                    full_sync=True,
                )
            except Exception as exc:
                print(f"[{_now()}] Bootstrap failed for {source.name}: {exc}")
                raise SystemExit(1) from exc

    print(
        f"[{_now()}] Fast poll: page 1 every {POLL_INTERVAL_MIN_SEC}–{POLL_INTERVAL_MAX_SEC}s (randomized) | "
        f"Full sync: {'off' if args.deep_interval == 0 else f'every {args.deep_interval}s when healthy'}"
    )

    last_deep_at = time.monotonic()
    consecutive_failures = 0

    try:
        while True:
            loop_start = time.monotonic()
            extra_delay = 0

            due_for_deep = (
                args.deep_interval > 0
                and consecutive_failures < 2
                and (loop_start - last_deep_at) >= args.deep_interval
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
            for source in sources:
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
                    print(f"[{_now()}] {label} failed for {source.name}: {exc}")

            if loop_failed:
                consecutive_failures += 1
                extra_delay = _failure_backoff_sec(consecutive_failures)
                print(
                    f"[{_now()}] Poll cycle had failures "
                    f"({consecutive_failures} in a row)"
                )
                if extra_delay:
                    print(f"[{_now()}] Backing off an extra {extra_delay}s before next poll")
                if consecutive_failures >= PAUSE_AFTER_FAILURES:
                    print(
                        f"[{_now()}] Many failures — staying in slow mode. "
                        "Consider waiting before restarting or checking your network."
                    )
            else:
                consecutive_failures = 0
                if due_for_deep:
                    last_deep_at = time.monotonic()

            _sleep_until_next_poll(
                loop_start,
                poll_min=POLL_INTERVAL_MIN_SEC,
                poll_max=POLL_INTERVAL_MAX_SEC,
                extra_delay=extra_delay,
            )
    except KeyboardInterrupt:
        print(f"\n[{_now()}] Stopped.")


if __name__ == "__main__":
    main()
