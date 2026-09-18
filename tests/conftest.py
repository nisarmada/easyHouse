from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mock_geocoding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "geo.geocode.geocode_query",
        lambda conn, query: (52.3676, 4.9041),
    )
    monkeypatch.setattr(
        "geo.geocode.geocode_city",
        lambda conn, city: (52.3676, 4.9041),
    )
    monkeypatch.setattr(
        "geo.geocode.geocode_listing",
        lambda conn, **kwargs: (52.3676, 4.9041),
    )
