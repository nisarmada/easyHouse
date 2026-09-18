from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Listing:
    source: str
    external_id: str
    url: str
    title: str
    price_eur: int | None
    city: str | None = None
    search_id: str = "default"
    street: str | None = None
    house_number: str | None = None
    postcode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
