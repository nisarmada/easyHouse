import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.db import get_connection, init_db, sync_listings, upsert_listings
from scrapers.pararius import DEFAULT_SEARCH_URL, parse_file, scrape_search


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Pararius and print new listings")
    parser.add_argument(
        "--file",
        help="Parse a local HTML file instead of fetching live (for offline testing)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_SEARCH_URL,
        help="Pararius search URL to scrape live",
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

    conn = get_connection()
    init_db(conn)

    if args.file:
        listings = parse_file(args.file)
        new_listings = upsert_listings(conn, listings)
        removed = []
    else:
        if args.max_pages is not None and not args.no_sync:
            parser.error(
                "Sync deletes listings not in the scrape — only allowed on a full scrape. "
                "Omit --max-pages (scrape all) or pass --no-sync."
            )
        listings = scrape_search(args.url, max_pages=args.max_pages)
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

    for row in removed:
        print(f"GONE             {row['title']}  {row['url']}")


if __name__ == "__main__":
    main()
