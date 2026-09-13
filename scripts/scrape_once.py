import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.load import DEFAULT_SOURCES_PATH, enabled_sources, get_source
from db.db import get_connection, init_db, sync_listings, upsert_listings
from notify import notify_new_listings
from scrapers.pararius import parse_file
from scrapers.registry import scrape_source


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

    if args.source:
        sources = [get_source(args.source, args.config)]
    else:
        sources = enabled_sources(args.config)
        if not sources:
            parser.error("No enabled sources in config")

    conn = get_connection()
    init_db(conn)

    if args.file:
        listings = parse_file(args.file)
        if args.source:
            search_id = get_source(args.source, args.config).id
            for listing in listings:
                listing.search_id = search_id
        new_listings = upsert_listings(conn, listings)
        removed = []
        print(f"Parsed {len(listings)} listings")
        print(f"New: {len(new_listings)}")
        print(f"Removed: {len(removed)}\n")
        for listing in new_listings:
            price = f"€{listing.price_eur:,}" if listing.price_eur else "?"
            print(f"NEW  {price:>10}  {listing.title}  {listing.url}")
        notify_new_listings(new_listings)
        return

    if args.max_pages is not None and not args.no_sync:
        parser.error(
            "Sync deletes listings not in the scrape — only allowed on a full scrape. "
            "Omit --max-pages (scrape all) or pass --no-sync."
        )

    for source in sources:
        print(f"\n=== {source.name} ===")
        print(source.url)
        listings = scrape_source(source, max_pages=args.max_pages)
        if args.no_sync:
            new_listings = upsert_listings(conn, listings)
            removed = []
        else:
            new_listings, removed = sync_listings(conn, listings)

        print(f"Parsed {len(listings)} listings")
        print(f"New: {len(new_listings)}")
        print(f"Removed: {len(removed)}\n")

        for listing in new_listings:
            price = f"€{listing.price_eur:,}" if listing.price_eur else "?"
            print(f"NEW  {price:>10}  {listing.title}  {listing.url}")
        notify_new_listings(new_listings)

        for row in removed:
            print(f"GONE             {row['title']}  {row['url']}")


if __name__ == "__main__":
    main()
