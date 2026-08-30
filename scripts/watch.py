from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.db import get_connection, init_db, sync_listings, upsert_listings
from scrapers.pararius import DEFAULT_SEARCH_URL, scrape_search

MAX_DETECTION_BUDGET_SEC = 300
MAX_FAST_POLL_INTERVAL_SEC = 240
DEFAULT_POLL_INTERVAL_SEC = 60
DEFAULT_DEEP_INTERVAL_SEC = 1800
INTERVAL_JITTER_SEC = 10

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
    url: str,
    *,
    max_pages: int | None,
    label: str,
    full_sync: bool,
) -> tuple[int, int, int]:
    listings = scrape_search(url, max_pages=max_pages)

    if full_sync:
        new_listings, removed = sync_listings(conn, listings)
    else:
        new_listings = upsert_listings(conn, listings)
        removed = []

    print(
        f"[{_now()}] {label}: parsed {len(listings)}, "
        f"new {len(new_listings)}, removed {len(removed)}"
    )
    _print_new_listings(new_listings)
    _print_removed_listings(removed)
    return len(listings), len(new_listings), len(removed)


def _failure_backoff_sec(consecutive_failures: int) -> int:
    if consecutive_failures <= 0:
        return 0
    index = min(consecutive_failures - 1, len(BACKOFF_STEPS_SEC) - 1)
    return BACKOFF_STEPS_SEC[index]


def _sleep_until_next_poll(interval: int, loop_start: float, extra_delay: int = 0) -> None:
    jitter = random.uniform(0, INTERVAL_JITTER_SEC)
    elapsed = time.monotonic() - loop_start
    sleep_for = max(0.0, interval + jitter + extra_delay - elapsed)
    if sleep_for:
        time.sleep(sleep_for)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Watch Pararius for new listings (bootstrap full sync + fast polls)"
    )
    parser.add_argument("--url", default=DEFAULT_SEARCH_URL, help="Pararius search URL")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SEC,
        help=f"Base seconds between fast polls (default: {DEFAULT_POLL_INTERVAL_SEC}, max: {MAX_FAST_POLL_INTERVAL_SEC})",
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

    if args.interval > MAX_FAST_POLL_INTERVAL_SEC:
        parser.error(
            f"--interval must be <= {MAX_FAST_POLL_INTERVAL_SEC}s "
            f"(detection budget is {MAX_DETECTION_BUDGET_SEC}s)"
        )

    conn = get_connection()
    init_db(conn)

    print(f"[{_now()}] Watching {args.url}")

    if not args.skip_bootstrap:
        print(f"[{_now()}] Bootstrap: scraping all pages and syncing DB...")
        try:
            _run_poll(conn, args.url, max_pages=None, label="bootstrap", full_sync=True)
        except Exception as exc:
            print(f"[{_now()}] Bootstrap failed: {exc}")
            raise SystemExit(1) from exc

    print(
        f"[{_now()}] Fast poll: page 1 every ~{args.interval}s (+0–{INTERVAL_JITTER_SEC}s jitter) | "
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

            try:
                _run_poll(
                    conn,
                    url=args.url,
                    max_pages=max_pages,
                    label=label,
                    full_sync=full_sync,
                )
                consecutive_failures = 0
                if due_for_deep:
                    last_deep_at = time.monotonic()
            except Exception as exc:
                consecutive_failures += 1
                extra_delay = _failure_backoff_sec(consecutive_failures)
                print(f"[{_now()}] {label} failed ({consecutive_failures} in a row): {exc}")
                if extra_delay:
                    print(f"[{_now()}] Backing off an extra {extra_delay}s before next poll")
                if consecutive_failures >= PAUSE_AFTER_FAILURES:
                    print(
                        f"[{_now()}] Many failures — staying in slow mode. "
                        "Consider waiting before restarting or checking your network."
                    )

            _sleep_until_next_poll(args.interval, loop_start, extra_delay=extra_delay)
    except KeyboardInterrupt:
        print(f"\n[{_now()}] Stopped.")


if __name__ == "__main__":
    main()
