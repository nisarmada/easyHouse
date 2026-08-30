from __future__ import annotations

import sqlite3
from pathlib import Path

from scrapers.pararius import Listing

DB_PATH = Path(__file__).resolve().parents[1] / "easyhouse.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            source        TEXT NOT NULL,
            external_id   TEXT NOT NULL,
            url           TEXT NOT NULL,
            title         TEXT NOT NULL,
            price_eur     INTEGER,
            city          TEXT,
            first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source, external_id)
        )
    """)
    conn.commit()


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
                INSERT INTO listings (source, external_id, url, title, price_eur, city)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    listing.source,
                    listing.external_id,
                    listing.url,
                    listing.title,
                    listing.price_eur,
                    listing.city,
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
                    last_seen_at = datetime('now')
                WHERE source = ? AND external_id = ?
                """,
                (
                    listing.url,
                    listing.title,
                    listing.price_eur,
                    listing.city,
                    listing.source,
                    listing.external_id,
                ),
            )

    conn.commit()
    return new_ones
