from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.load import DEFAULT_SOURCES_PATH, get_source
from config.search import load_search
from config.search_service import filter_listings_by_radius
from db.db import get_connection, init_db, upsert_listings
from notify import notify_new_listings
from scrapers.pararius import parse_file
from services.scrape_runner import run_scrape


def _print_new_listings(listings) -> None:
    for listing in listings:
        price = f"€{listing.price_eur:,}" if listing.price_eur else "?"
        print(f"NEW  {price:>10}  {listing.title}  {listing.url}")


def _print_removed_listings(removed) -> None:
    for row in removed:
        print(f"GONE             {row['title']}  {row['url']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape configured sources and print new listings")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_SOURCES_PATH),
        help="Path to sources JSON (default: config/sources.json)",
    )
    parser.add_argument(
        "--source",
        help="Scrape one source by name (default: all enabled sources)",
    )
    parser.add_argument(
        "--file",
        help="Parse a local HTML file instead of fetching live (offline testing; pararius only)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max search pages to fetch (default: all pages)",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Do not remove listings missing from this scrape (default: sync on full scrape)",
    )
    args = parser.parse_args()

    if args.file:
        search = load_search()
        conn = get_connection()
        init_db(conn)
        listings = parse_file(args.file)
        for listing in listings:
            listing.search_id = search.id
            if not listing.city:
                listing.city = search.city
        new_listings = upsert_listings(conn, listings)
        print(f"Parsed {len(listings)} listings")
        print(f"New: {len(new_listings)}")
        print(f"Removed: 0\n")
        _print_new_listings(new_listings)
        notify_new_listings(filter_listings_by_radius(conn, new_listings))
        return

    if args.max_pages is not None and not args.no_sync:
        parser.error(
            "Sync deletes listings not in the scrape — only allowed on a full scrape. "
            "Omit --max-pages (scrape all) or pass --no-sync."
        )

    try:
        results = run_scrape(
            source_id=args.source,
            max_pages=args.max_pages,
            full_sync=not args.no_sync,
            config_path=args.config,
        )
    except ValueError as exc:
        parser.error(str(exc))

    for result in results:
        print(f"\n=== {result.source_name} ===")
        if result.error:
            print(f"ERROR: {result.error}")
            continue

        print(f"Parsed {result.parsed} listings")
        print(f"New: {result.new_count}")
        print(f"Removed: {result.removed_count}\n")
        _print_new_listings(result.new_listings)
        _print_removed_listings(result.removed)


if __name__ == "__main__":
    main()
