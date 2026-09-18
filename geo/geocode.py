from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "easyHouse/1.0"
LAST_REQUEST_AT = 0.0
MIN_INTERVAL_SEC = 1.0


def _rate_limit() -> None:
    global LAST_REQUEST_AT
    elapsed = time.monotonic() - LAST_REQUEST_AT
    if elapsed < MIN_INTERVAL_SEC:
        time.sleep(MIN_INTERVAL_SEC - elapsed)
    LAST_REQUEST_AT = time.monotonic()


def _fetch_coordinates(query: str) -> tuple[float, float] | None:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "limit": 1,
            "countrycodes": "nl",
        }
    )
    request = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    _rate_limit()
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload:
        return None
    return float(payload[0]["lat"]), float(payload[0]["lon"])


def _cache_get(conn: sqlite3.Connection, query: str) -> tuple[float, float] | None:
    row = conn.execute(
        "SELECT latitude, longitude FROM geocode_cache WHERE query = ?",
        (query,),
    ).fetchone()
    if row is None:
        return None
    return row["latitude"], row["longitude"]


def _cache_set(conn: sqlite3.Connection, query: str, lat: float, lon: float) -> None:
    conn.execute(
        """
        INSERT INTO geocode_cache (query, latitude, longitude)
        VALUES (?, ?, ?)
        ON CONFLICT(query) DO UPDATE SET
            latitude = excluded.latitude,
            longitude = excluded.longitude,
            cached_at = datetime('now')
        """,
        (query, lat, lon),
    )


def geocode_query(conn: sqlite3.Connection, query: str) -> tuple[float, float] | None:
    normalized = " ".join(query.split())
    if not normalized:
        return None

    cached = _cache_get(conn, normalized)
    if cached is not None:
        return cached

    try:
        coords = _fetch_coordinates(normalized)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
        return None

    if coords is None:
        return None

    _cache_set(conn, normalized, coords[0], coords[1])
    conn.commit()
    return coords


def geocode_city(conn: sqlite3.Connection, city: str) -> tuple[float, float] | None:
    return geocode_query(conn, f"{city}, Netherlands")


def geocode_listing(
    conn: sqlite3.Connection,
    *,
    street: str | None,
    house_number: str | None,
    postcode: str | None,
    city: str | None,
) -> tuple[float, float] | None:
    parts: list[str] = []
    if street:
        if house_number:
            parts.append(f"{street} {house_number}")
        else:
            parts.append(street)
    if postcode:
        parts.append(postcode)
    if city:
        parts.append(city)
    parts.append("Netherlands")
    if len(parts) <= 1:
        if city:
            return geocode_city(conn, city)
        return None
    return geocode_query(conn, ", ".join(parts))
