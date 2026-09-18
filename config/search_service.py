from __future__ import annotations

import sqlite3

from config.search import SearchConfig, load_search, save_search
from db.db import get_connection, init_db
from geo.distance import haversine_km
from geo.geocode import geocode_city


def get_active_search(conn: sqlite3.Connection | None = None) -> SearchConfig:
    search = load_search()
    if search.center_lat is not None and search.center_lon is not None:
        return search

    own_conn = conn is None
    if own_conn:
        conn = get_connection()
        init_db(conn)

    coords = geocode_city(conn, search.city)
    if coords is None:
        return search

    updated = save_search(
        search.city,
        search.radius_km,
        center_lat=coords[0],
        center_lon=coords[1],
    )
    if own_conn:
        conn.commit()
    return updated


def listing_within_radius(
    conn: sqlite3.Connection,
    *,
    latitude: float | None,
    longitude: float | None,
    search: SearchConfig | None = None,
) -> bool:
    search = search or get_active_search(conn)
    if search.center_lat is None or search.center_lon is None:
        return True
    if latitude is None or longitude is None:
        return False

    distance = haversine_km(search.center_lat, search.center_lon, latitude, longitude)
    return distance <= search.radius_km


def filter_listings_by_radius(conn: sqlite3.Connection, listings: list) -> list:
    search = get_active_search(conn)
    return [
        listing
        for listing in listings
        if listing_within_radius(
            conn,
            latitude=getattr(listing, "latitude", None),
            longitude=getattr(listing, "longitude", None),
            search=search,
        )
    ]
