from __future__ import annotations

from pathlib import Path

import db.db as dbmod
from db.db import init_db, upsert_listings
from scrapers.address import enrich_listing, keys_for, parse_address, phase1_key, phase2_key
from scrapers.listing import Listing


def test_parse_address_with_postcode() -> None:
    street, house_number, postcode = parse_address(
        "Maassluisstraat 60 1062 GE Amsterdam",
        city="Amsterdam",
    )
    assert street == "Maassluisstraat"
    assert house_number == "60"
    assert postcode == "1062GE"


def test_parse_address_street_only() -> None:
    street, house_number, postcode = parse_address("Krammerstraat", city="Amsterdam")
    assert street == "Krammerstraat"
    assert house_number is None
    assert postcode is None


def test_phase2_key_when_postcode_available() -> None:
    listing = Listing(
        source="funda",
        external_id="1",
        url="http://x",
        title="Maassluisstraat 60 1062 GE Amsterdam",
        price_eur=2600,
        city="Amsterdam",
    )
    enrich_listing(listing)
    assert phase2_key(listing) == "s|amsterdam|1062GE|60"
    assert phase1_key(listing).startswith("w|amsterdam|")


def test_cross_source_dedup(tmp_path: Path) -> None:
    dbmod.DB_PATH = tmp_path / "dedup.db"
    conn = dbmod.get_connection()
    init_db(conn)

    pararius = Listing(
        "pararius",
        "p1",
        "http://pararius/x",
        "Maassluisstraat 60 1062 GE Amsterdam",
        2600,
        "Amsterdam",
        search_id="pararius",
    )
    funda = Listing(
        "funda",
        "f1",
        "http://funda/x",
        "Maassluisstraat 60 1062 GE Amsterdam",
        2600,
        "Amsterdam",
        search_id="funda",
    )

    first = upsert_listings(conn, [pararius])
    second = upsert_listings(conn, [funda])

    assert len(first) == 1
    assert len(second) == 0

    canonical_count = conn.execute("SELECT COUNT(*) FROM canonical_listings").fetchone()[0]
    source_count = conn.execute("SELECT COUNT(*) FROM listing_sources").fetchone()[0]
    assert canonical_count == 1
    assert source_count == 2


def test_weak_key_dedup_when_only_street_and_price_match(tmp_path: Path) -> None:
    dbmod.DB_PATH = tmp_path / "weak.db"
    conn = dbmod.get_connection()
    init_db(conn)

    first = Listing("kamernet", "k1", "http://k/1", "Oetewalerstraat", 1000, "Amsterdam", search_id="kamernet")
    second = Listing("pararius", "p1", "http://p/1", "Oetewalerstraat", 1000, "Amsterdam", search_id="pararius")

    assert len(upsert_listings(conn, [first])) == 1
    assert len(upsert_listings(conn, [second])) == 0

    strong, weak = keys_for(first)
    assert strong is None
    assert weak == phase1_key(first)


def test_strong_key_upgrades_existing_weak_match(tmp_path: Path) -> None:
    dbmod.DB_PATH = tmp_path / "upgrade.db"
    conn = dbmod.get_connection()
    init_db(conn)

    weak = Listing("kamernet", "k1", "http://k/1", "Oetewalerstraat", 1000, "Amsterdam", search_id="kamernet")
    strong = Listing(
        "funda",
        "f1",
        "http://f/1",
        "Oetewalerstraat 10 1094 PH Amsterdam",
        1000,
        "Amsterdam",
        search_id="funda",
    )

    upsert_listings(conn, [weak])
    upsert_listings(conn, [strong])

    row = conn.execute("SELECT listing_key FROM canonical_listings").fetchone()
    assert row["listing_key"].startswith("s|")
