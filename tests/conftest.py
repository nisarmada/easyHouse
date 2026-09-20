from __future__ import annotations

import pytest

from config import paths


@pytest.fixture(autouse=True)
def _isolated_user_data(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "easyhouse-home"
    paths.set_user_data_dir(home)
    yield
    paths.set_user_data_dir(None)


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
