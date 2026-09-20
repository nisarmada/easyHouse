#!/usr/bin/env python3
"""Run each configured scraper twice and report consistency."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.load import load_sources
from config.paths import ensure_user_data, get_sources_path
from scrapers.registry import scrape_source


def run_once(source, *, max_pages: int) -> tuple[int, set[str]]:
    listings = scrape_source(source, max_pages=max_pages)
    return len(listings), {listing.external_id for listing in listings}


def main() -> int:
    ensure_user_data()
    sources = load_sources(get_sources_path())
    failures = 0

    for source in sources:
        print(f"\n=== {source.name} ({source.type}) ===")
        print(source.url)

        try:
            count1, ids1 = run_once(source, max_pages=1)
            count2, ids2 = run_once(source, max_pages=1)
        except Exception as exc:
            print(f"FAIL  {exc}")
            failures += 1
            continue

        stable = ids1 == ids2 and count1 == count2
        status = "OK" if stable and count1 > 0 else "WARN"
        if count1 == 0:
            status = "FAIL"
            failures += 1
        elif not stable:
            status = "WARN"
            failures += 1

        overlap = len(ids1 & ids2)
        print(f"{status}  page-1 count: {count1} / {count2}  id overlap: {overlap}/{max(len(ids1), 1)}")
        if count1:
            sample = scrape_source(source, max_pages=1)[0]
            price = f"€{sample.price_eur:,}" if sample.price_eur else "?"
            print(f"      sample: {price}  {sample.title}  {sample.url}")

    print(f"\nDone. Failures: {failures}/{len(sources)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
