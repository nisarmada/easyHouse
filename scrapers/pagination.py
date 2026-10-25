from __future__ import annotations

from scrapers.listing import Listing


def merge_unique_batch(
    seen_ids: set[str],
    listings: list[Listing],
    batch: list[Listing],
) -> int:
    """Append listings not yet seen. Returns count of newly added items."""
    added = 0
    for listing in batch:
        if listing.external_id in seen_ids:
            continue
        seen_ids.add(listing.external_id)
        listings.append(listing)
        added += 1
    return added
