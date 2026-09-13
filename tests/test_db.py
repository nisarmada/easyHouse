from __future__ import annotations

import sqlite3
from pathlib import Path

import db.db as dbmod
from db.db import init_db, sync_listings, upsert_listings
from scrapers.listing import Listing


def _use_temp_db(tmp_path: Path) -> sqlite3.Connection:
    dbmod.DB_PATH = tmp_path / "test.db"
    conn = dbmod.get_connection()
    init_db(conn)
    return conn


def test_search_id_backfill_on_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE listings (
            source TEXT, external_id TEXT, url TEXT, title TEXT,
            price_eur INTEGER, city TEXT,
            first_seen_at TEXT, last_seen_at TEXT,
            PRIMARY KEY (source, external_id)
        )
        """
    )
    conn.execute(
        "INSERT INTO listings VALUES ('pararius','old1','http://x','Old',1000,'Amsterdam',datetime('now'),datetime('now'))"
    )
    conn.commit()
    conn.close()

    dbmod.DB_PATH = db_path
    conn = dbmod.get_connection()
    init_db(conn)

    rows = [(row[0], row[1]) for row in conn.execute("SELECT external_id, search_id FROM listings")]
    assert rows == [("old1", "pararius")]

    new = [Listing("pararius", "new1", "http://y", "New", 2000, None, "pararius")]
    _, removed = sync_listings(conn, new)
    assert [row["external_id"] for row in removed] == ["old1"]
    remaining = [row[0] for row in conn.execute("SELECT external_id FROM listings")]
    assert remaining == ["new1"]


def test_sync_refuses_empty_scrape(tmp_path: Path) -> None:
    conn = _use_temp_db(tmp_path)
    try:
        sync_listings(conn, [])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_upsert_updates_existing_listing(tmp_path: Path) -> None:
    conn = _use_temp_db(tmp_path)
    listing = Listing("pararius", "1", "http://x", "First", 1000, "Amsterdam", "pararius")
    assert len(upsert_listings(conn, [listing])) == 1
    updated = Listing("pararius", "1", "http://x", "Updated", 1200, "Amsterdam", "pararius")
    assert len(upsert_listings(conn, [updated])) == 0
    row = conn.execute("SELECT title, price_eur FROM listings WHERE external_id = '1'").fetchone()
    assert row["title"] == "Updated"
    assert row["price_eur"] == 1200
