from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from config.load import SourceConfig, enabled_sources, ensure_sources_config, get_source
from config.search_service import filter_listings_by_radius
from db.db import get_connection, init_db, sync_listings, upsert_listings
from notify import notify_new_listings
from scrapers.listing import Listing
from scrapers.registry import scrape_source
from services.scrape_coordination import begin_scrape, end_scrape, is_cancelled


@dataclass
class ScrapeResult:
    source_name: str
    parsed: int
    new_count: int
    removed_count: int
    new_listings: list[Listing] = field(default_factory=list)
    removed: list = field(default_factory=list)
    error: str | None = None


@dataclass
class RunScrapeResult:
    results: list[ScrapeResult]
    cancelled: bool = False


def scrape_and_store(
    conn: sqlite3.Connection,
    source: SourceConfig,
    *,
    max_pages: int | None,
    full_sync: bool,
) -> ScrapeResult:
    listings = scrape_source(source, max_pages=max_pages)
    if full_sync:
        new_listings, removed = sync_listings(conn, listings)
    else:
        new_listings = upsert_listings(conn, listings)
        removed = []

    notify_new_listings(filter_listings_by_radius(conn, new_listings))
    return ScrapeResult(
        source_name=source.name,
        parsed=len(listings),
        new_count=len(new_listings),
        removed_count=len(removed),
        new_listings=new_listings,
        removed=removed,
    )


def run_scrape(
    *,
    source_id: str | None = None,
    max_pages: int | None = 1,
    full_sync: bool = False,
    config_path: str | Path | None = None,
) -> RunScrapeResult:
    ensure_sources_config(config_path)
    conn = get_connection()
    init_db(conn)

    generation = begin_scrape()
    cancelled = False
    try:
        if source_id:
            sources = [get_source(source_id, config_path)]
        else:
            sources = enabled_sources(config_path)

        if not sources:
            raise ValueError("No enabled platforms — enable at least one in the web UI under Platforms")

        results: list[ScrapeResult] = []
        for source in sources:
            if is_cancelled(generation):
                cancelled = True
                break
            try:
                results.append(
                    scrape_and_store(conn, source, max_pages=max_pages, full_sync=full_sync)
                )
            except Exception as exc:
                results.append(
                    ScrapeResult(
                        source_name=source.name,
                        parsed=0,
                        new_count=0,
                        removed_count=0,
                        error=str(exc),
                    )
                )
        return RunScrapeResult(results=results, cancelled=cancelled)
    finally:
        end_scrape()
