from __future__ import annotations

import sqlite3
from typing import Any

from config.search import SearchConfig
from config.search_service import get_active_search


def _haversine_sql(alias: str = "c") -> str:
    return f"""
        CASE
            WHEN ? IS NULL OR ? IS NULL OR {alias}.latitude IS NULL OR {alias}.longitude IS NULL THEN NULL
            ELSE (
                6371 * acos(
                    MIN(1, MAX(-1,
                        cos(radians(?)) * cos(radians({alias}.latitude))
                        * cos(radians({alias}.longitude) - radians(?))
                        + sin(radians(?)) * sin(radians({alias}.latitude))
                    ))
                )
            )
        END
    """


def _radius_clause(search: SearchConfig) -> tuple[str, list[Any]]:
    if search.center_lat is None or search.center_lon is None:
        return "", []
    return (
        """
        c.latitude IS NOT NULL
        AND c.longitude IS NOT NULL
        AND (
            6371 * acos(
                MIN(1, MAX(-1,
                    cos(radians(?)) * cos(radians(c.latitude))
                    * cos(radians(c.longitude) - radians(?))
                    + sin(radians(?)) * sin(radians(c.latitude))
                ))
            )
        ) <= ?
        """,
        [search.center_lat, search.center_lon, search.center_lat, search.radius_km],
    )


def get_dashboard_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    search = get_active_search(conn)
    radius_sql, radius_params = _radius_clause(search)
    radius_filter = f" AND {radius_sql}" if radius_sql else ""

    canonical_count = conn.execute(
        f"SELECT COUNT(*) FROM canonical_listings c WHERE 1=1{radius_filter}",
        radius_params,
    ).fetchone()[0]
    source_rows = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM listing_sources ls
        JOIN canonical_listings c ON c.id = ls.canonical_id
        WHERE 1=1{radius_filter}
        """,
        radius_params,
    ).fetchone()[0]
    new_24h = conn.execute(
        f"""
        SELECT COUNT(*) FROM canonical_listings c
        WHERE first_seen_at >= datetime('now', '-1 day')
        {radius_filter}
        """,
        radius_params,
    ).fetchone()[0]
    by_source = conn.execute(
        f"""
        SELECT ls.source, COUNT(*) AS count
        FROM listing_sources ls
        JOIN canonical_listings c ON c.id = ls.canonical_id
        WHERE 1=1{radius_filter}
        GROUP BY ls.source
        ORDER BY count DESC
        """,
        radius_params,
    ).fetchall()
    by_city = conn.execute(
        f"""
        SELECT COALESCE(c.city, 'Unknown') AS city, COUNT(*) AS count
        FROM canonical_listings c
        WHERE 1=1{radius_filter}
        GROUP BY c.city
        ORDER BY count DESC
        LIMIT 8
        """,
        radius_params,
    ).fetchall()
    return {
        "canonical_count": canonical_count,
        "source_rows": source_rows,
        "new_24h": new_24h,
        "by_source": [dict(row) for row in by_source],
        "by_city": [dict(row) for row in by_city],
        "search": search.to_dict(),
    }


def list_listings(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
    source: str | None = None,
    search: str | None = None,
    apply_radius: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    active_search = get_active_search(conn)
    clauses: list[str] = []
    params: list[Any] = []

    if source:
        clauses.append(
            "EXISTS (SELECT 1 FROM listing_sources ls2 WHERE ls2.canonical_id = c.id AND ls2.source = ?)"
        )
        params.append(source)

    if search:
        clauses.append(
            "(c.title LIKE ? OR c.city LIKE ? OR c.street LIKE ? OR c.postcode LIKE ?)"
        )
        term = f"%{search}%"
        params.extend([term, term, term, term])

    if apply_radius:
        radius_sql, radius_params = _radius_clause(active_search)
        if radius_sql:
            clauses.append(radius_sql)
            params.extend(radius_params)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    haversine = _haversine_sql("c")
    center_lat = active_search.center_lat
    center_lon = active_search.center_lon

    total = conn.execute(
        f"SELECT COUNT(*) FROM canonical_listings c {where}",
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT
            c.id,
            c.title,
            c.price_eur,
            c.city,
            c.postcode,
            c.street,
            c.house_number,
            c.best_url,
            c.latitude,
            c.longitude,
            c.first_seen_at,
            c.last_seen_at,
            {haversine} AS distance_km,
            (
                SELECT GROUP_CONCAT(source, ',')
                FROM listing_sources ls
                WHERE ls.canonical_id = c.id
            ) AS sources
        FROM canonical_listings c
        {where}
        ORDER BY (distance_km IS NULL), distance_km ASC, c.first_seen_at DESC
        LIMIT ? OFFSET ?
        """,
        [
            center_lat,
            center_lon,
            center_lat,
            center_lon,
            center_lat,
            *params,
            limit,
            offset,
        ],
    ).fetchall()

    listings = []
    for row in rows:
        item = dict(row)
        item["sources"] = item["sources"].split(",") if item["sources"] else []
        if item["distance_km"] is not None:
            item["distance_km"] = round(item["distance_km"], 1)
        listings.append(item)
    return listings, total


def get_listing(conn: sqlite3.Connection, canonical_id: str) -> dict[str, Any] | None:
    active_search = get_active_search(conn)
    haversine = _haversine_sql("c")
    center_lat = active_search.center_lat
    center_lon = active_search.center_lon

    row = conn.execute(
        f"""
        SELECT c.*, {haversine} AS distance_km
        FROM canonical_listings c
        WHERE c.id = ?
        """,
        [center_lat, center_lon, center_lat, center_lon, center_lat, canonical_id],
    ).fetchone()
    if row is None:
        return None

    sources = conn.execute(
        """
        SELECT source, external_id, url, search_id, first_seen_at, last_seen_at
        FROM listing_sources
        WHERE canonical_id = ?
        ORDER BY source
        """,
        (canonical_id,),
    ).fetchall()
    result = dict(row)
    if result.get("distance_km") is not None:
        result["distance_km"] = round(result["distance_km"], 1)
    result["sources"] = [dict(source) for source in sources]
    return result
