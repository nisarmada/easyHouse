import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.db import get_connection, init_db, upsert_listings
from scrapers.pararius import parse_file

conn = get_connection()
init_db(conn)

listings = parse_file("pararius.html")
new_listings = upsert_listings(conn, listings)

print(f"Parsed {len(listings)} listings")
print(f"New: {len(new_listings)}\n")

for listing in new_listings:
    price = f"€{listing.price_eur:,}" if listing.price_eur else "?"
    print(f"NEW  {price:>10}  {listing.title}  {listing.url}")
