from __future__ import annotations

import sqlite3
from pathlib import Path

from scrapers.listing import Listing

DB_PATH = Path(__file__).resolve().parents[1] / "easyhouse.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _backfill_search_id(conn: sqlite3.Connection) -> None:
    """Legacy rows used search_id='default'; match source slug used by config."""
    conn.execute(
        "UPDATE listings SET search_id = source WHERE search_id = 'default'"
    )
    conn.commit()


def _ensure_search_id_column(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(listings)")}
    if "search_id" not in columns:
        conn.execute(
            "ALTER TABLE listings ADD COLUMN search_id TEXT NOT NULL DEFAULT 'default'"
        )
        conn.commit()
    _backfill_search_id(conn)


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            source        TEXT NOT NULL,
            external_id   TEXT NOT NULL,
            url           TEXT NOT NULL,
            title         TEXT NOT NULL,
            price_eur     INTEGER,
            city          TEXT,
            search_id     TEXT NOT NULL DEFAULT 'default',
            first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source, external_id)
        )
    """)
    conn.commit()
    _ensure_search_id_column(conn)


def upsert_listings(conn: sqlite3.Connection, listings: list[Listing]) -> list[Listing]:
    new_ones: list[Listing] = []

    for listing in listings:
        exists = conn.execute(
            "SELECT 1 FROM listings WHERE source = ? AND external_id = ?",
            (listing.source, listing.external_id),
        ).fetchone()

        if exists is None:
            conn.execute(
                """
                INSERT INTO listings (source, external_id, url, title, price_eur, city, search_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing.source,
                    listing.external_id,
                    listing.url,
                    listing.title,
                    listing.price_eur,
                    listing.city,
                    listing.search_id,
                ),
            )
            new_ones.append(listing)
        else:
            conn.execute(
                """
                UPDATE listings SET
                    url = ?,
                    title = ?,
                    price_eur = ?,
                    city = ?,
                    search_id = ?,
                    last_seen_at = datetime('now')
                WHERE source = ? AND external_id = ?
                """,
                (
                    listing.url,
                    listing.title,
                    listing.price_eur,
                    listing.city,
                    listing.search_id,
                    listing.source,
                    listing.external_id,
                ),
            )

    conn.commit()
    return new_ones


def remove_stale_listings(
    conn: sqlite3.Connection,
    source: str,
    search_id: str,
    seen_external_ids: set[str],
) -> list[sqlite3.Row]:
    """Delete listings for this source/search that were not in the latest full scrape."""
    if not seen_external_ids:
        return []

    placeholders = ",".join("?" * len(seen_external_ids))
    params = [source, search_id, *seen_external_ids]

    stale = conn.execute(
        f"""
        SELECT external_id, title, url
        FROM listings
        WHERE source = ? AND search_id = ? AND external_id NOT IN ({placeholders})
        """,
        params,
    ).fetchall()

    conn.execute(
        f"""
        DELETE FROM listings
        WHERE source = ? AND search_id = ? AND external_id NOT IN ({placeholders})
        """,
        params,
    )
    conn.commit()
    return stale


def sync_listings(conn: sqlite3.Connection, listings: list[Listing]) -> tuple[list[Listing], list[sqlite3.Row]]:
    """
    Upsert all scraped listings, then delete DB rows for this search that are no longer live.

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
