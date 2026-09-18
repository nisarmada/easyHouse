from __future__ import annotations

from geo.distance import haversine_km


def test_haversine_amsterdam_to_nearby() -> None:
    center = (52.3676, 4.9041)
    nearby = (52.3700, 4.9100)
    distance = haversine_km(center[0], center[1], nearby[0], nearby[1])
    assert 0 < distance < 2


def test_haversine_rotterdam_is_far_from_amsterdam() -> None:
    amsterdam = (52.3676, 4.9041)
    rotterdam = (51.9244, 4.4777)
    distance = haversine_km(amsterdam[0], amsterdam[1], rotterdam[0], rotterdam[1])
    assert distance > 50
