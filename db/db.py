from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from config.paths import ensure_user_data, get_db_path
from geo.geocode import geocode_listing
from scrapers.address import enrich_listing, keys_for, primary_key
from scrapers.listing import Listing

DB_PATH: Path | None = None


def _resolve_db_path() -> Path:
    if DB_PATH is not None:
        return DB_PATH
    return get_db_path()


def get_connection() -> sqlite3.Connection:
    ensure_user_data()
    conn = sqlite3.connect(_resolve_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _legacy_listings_columns(conn: sqlite3.Connection) -> set[str]:
    if not _table_exists(conn, "listings"):
        return set()
    return {row[1] for row in conn.execute("PRAGMA table_info(listings)")}


def _backfill_search_id(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "listing_sources"):
        return
    conn.execute(
        "UPDATE listing_sources SET search_id = source WHERE search_id = 'default'"
    )
    conn.commit()


def _migrate_legacy_listings(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "listings"):
        return
    if conn.execute("SELECT COUNT(*) FROM listing_sources").fetchone()[0] > 0:
        conn.execute("DROP TABLE IF EXISTS listings")
        conn.commit()
        return

    columns = _legacy_listings_columns(conn)
    rows = conn.execute("SELECT * FROM listings").fetchall()
    for row in rows:
        listing = Listing(
            source=row["source"],
            external_id=row["external_id"],
            url=row["url"],
            title=row["title"],
            price_eur=row["price_eur"],
            city=row["city"],
            search_id=row["search_id"] if "search_id" in columns else row["source"],
        )
        _upsert_one(conn, listing)

    conn.execute("DROP TABLE listings")
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    from auth.store import init_accounts

    init_accounts(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS canonical_listings (
            id              TEXT PRIMARY KEY,
            listing_key     TEXT NOT NULL UNIQUE,
            listing_key_weak  TEXT,
            title           TEXT NOT NULL,
            price_eur       INTEGER,
            city            TEXT,
            postcode        TEXT,
            street          TEXT,
            house_number    TEXT,
            best_url        TEXT NOT NULL,
            first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listing_sources (
            canonical_id    TEXT NOT NULL,
            source          TEXT NOT NULL,
            external_id     TEXT NOT NULL,
            url             TEXT NOT NULL,
            search_id       TEXT NOT NULL DEFAULT 'default',
            first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source, external_id),
            FOREIGN KEY (canonical_id) REFERENCES canonical_listings(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_listings_weak "
        "ON canonical_listings(listing_key_weak)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocode_cache (
            query       TEXT PRIMARY KEY,
            latitude    REAL NOT NULL,
            longitude   REAL NOT NULL,
            cached_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    _ensure_coordinate_columns(conn)
    conn.commit()
    _migrate_legacy_listings(conn)
    _backfill_search_id(conn)


def _ensure_coordinate_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(canonical_listings)")}
    if "latitude" not in columns:
        conn.execute("ALTER TABLE canonical_listings ADD COLUMN latitude REAL")
    if "longitude" not in columns:
        conn.execute("ALTER TABLE canonical_listings ADD COLUMN longitude REAL")


def _resolve_coordinates(
    conn: sqlite3.Connection,
    listing: Listing,
) -> tuple[float | None, float | None]:
    return geocode_listing(
        conn,
        street=listing.street,
        house_number=listing.house_number,
        postcode=listing.postcode,
        city=listing.city,
    )


def _find_canonical_id(
    conn: sqlite3.Connection,
    strong_key: str | None,
    weak_key: str,
) -> str | None:
    if strong_key:
        row = conn.execute(
            "SELECT id FROM canonical_listings WHERE listing_key = ?",
            (strong_key,),
        ).fetchone()
        if row:
            return row["id"]

    row = conn.execute(
        """
        SELECT id FROM canonical_listings
        WHERE listing_key = ? OR listing_key_weak = ?
        """,
        (weak_key, weak_key),
    ).fetchone()
    return row["id"] if row else None


def _create_canonical(
    conn: sqlite3.Connection,
    listing: Listing,
    strong_key: str | None,
    weak_key: str,
) -> str:
    canonical_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO canonical_listings (
            id, listing_key, listing_key_weak, title, price_eur, city,
            postcode, street, house_number, best_url, latitude, longitude
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            canonical_id,
            primary_key(strong_key, weak_key),
            weak_key if strong_key else None,
            listing.title,
            listing.price_eur,
            listing.city,
            listing.postcode,
            listing.street,
            listing.house_number,
            listing.url,
            listing.latitude,
            listing.longitude,
        ),
    )
    return canonical_id


def _upgrade_canonical(
    conn: sqlite3.Connection,
    canonical_id: str,
    listing: Listing,
    strong_key: str | None,
    weak_key: str,
) -> None:
    conn.execute(
        """
        UPDATE canonical_listings SET
            listing_key = ?,
            listing_key_weak = ?,
            title = ?,
            price_eur = ?,
            city = COALESCE(?, city),
            postcode = COALESCE(?, postcode),
            street = COALESCE(?, street),
            house_number = COALESCE(?, house_number),
            best_url = ?,
            latitude = COALESCE(?, latitude),
            longitude = COALESCE(?, longitude),
            last_seen_at = datetime('now')
        WHERE id = ?
        """,
        (
            primary_key(strong_key, weak_key),
            weak_key if strong_key else None,
            listing.title,
            listing.price_eur,
            listing.city,
            listing.postcode,
            listing.street,
            listing.house_number,
            listing.url,
            listing.latitude,
            listing.longitude,
            canonical_id,
        ),
    )


def _upsert_one(conn: sqlite3.Connection, listing: Listing) -> bool:
    """
    Upsert a listing source row and its canonical listing.
    Returns True when this is the first time the canonical listing was seen.
    """
    enrich_listing(listing)
    latitude, longitude = _resolve_coordinates(conn, listing)
    listing.latitude = latitude
    listing.longitude = longitude
    strong_key, weak_key = keys_for(listing)

    canonical_id = _find_canonical_id(conn, strong_key, weak_key)
    is_new_canonical = canonical_id is None

    if is_new_canonical:
        canonical_id = _create_canonical(conn, listing, strong_key, weak_key)
    else:
        _upgrade_canonical(conn, canonical_id, listing, strong_key, weak_key)

    source_exists = conn.execute(
        "SELECT 1 FROM listing_sources WHERE source = ? AND external_id = ?",
        (listing.source, listing.external_id),
    ).fetchone()

    if source_exists is None:
        conn.execute(
            """
            INSERT INTO listing_sources (
                canonical_id, source, external_id, url, search_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                canonical_id,
                listing.source,
                listing.external_id,
                listing.url,
                listing.search_id,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE listing_sources SET
                canonical_id = ?,
                url = ?,
                search_id = ?,
                last_seen_at = datetime('now')
            WHERE source = ? AND external_id = ?
            """,
            (
                canonical_id,
                listing.url,
                listing.search_id,
                listing.source,
                listing.external_id,
            ),
        )

    return is_new_canonical and source_exists is None


def upsert_listings(conn: sqlite3.Connection, listings: list[Listing]) -> list[Listing]:
    """Return listings that are newly seen canonical entries (deduped across sources)."""
    new_ones: list[Listing] = []

    for listing in listings:
        if _upsert_one(conn, listing):
            new_ones.append(listing)

    conn.commit()
    return new_ones


def _cleanup_orphan_canonicals(conn: sqlite3.Connection) -> None:
    conn.execute("""
        DELETE FROM canonical_listings
        WHERE id NOT IN (SELECT DISTINCT canonical_id FROM listing_sources)
    """)


def remove_stale_listings(
    conn: sqlite3.Connection,
    source: str,
    search_id: str,
    seen_external_ids: set[str],
) -> list[sqlite3.Row]:
    """Delete source rows for this search that were not in the latest full scrape."""
    if not seen_external_ids:
        return []

    placeholders = ",".join("?" * len(seen_external_ids))
    params = [source, search_id, *seen_external_ids]

    stale = conn.execute(
        f"""
        SELECT ls.external_id, c.title, ls.url
        FROM listing_sources ls
        JOIN canonical_listings c ON c.id = ls.canonical_id
        WHERE ls.source = ? AND ls.search_id = ? AND ls.external_id NOT IN ({placeholders})
        """,
        params,
    ).fetchall()

    conn.execute(
        f"""
        DELETE FROM listing_sources
        WHERE source = ? AND search_id = ? AND external_id NOT IN ({placeholders})
        """,
        params,
    )
    _cleanup_orphan_canonicals(conn)
    conn.commit()
    return stale


def sync_listings(conn: sqlite3.Connection, listings: list[Listing]) -> tuple[list[Listing], list[sqlite3.Row]]:
    """
    Upsert all scraped listings, then delete source rows for this search that are no longer live.

    Only call after a full multi-page scrape — not after a page-1 fast poll.
    """
    if not listings:
        raise ValueError("Refusing to sync an empty scrape (possible fetch failure)")

    source = listings[0].source
    search_id = listings[0].search_id
    new_ones = upsert_listings(conn, listings)
    seen_ids = {listing.external_id for listing in listings}
    removed = remove_stale_listings(conn, source, search_id, seen_ids)
    return new_ones, removed
