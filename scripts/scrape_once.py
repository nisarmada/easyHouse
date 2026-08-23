import sys
from pathlib import Path

sys.path.insert((0), str(Path(__file__).resolve().parents[1]))

from scrapers.pararius import parse_file

listings = parse_file("pararius.html")
print(f"Found {len(listings)} listings\n")
for listing in listings:
    price = f"€{listing.price_eur:,}" if listing.price_eur else "?"
    print(f"{price:>10}  {listing.title}  {listing.url}")
