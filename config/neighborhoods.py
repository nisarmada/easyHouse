from __future__ import annotations

# Common neighborhoods / districts for major Dutch rental markets.
NEIGHBORHOODS: dict[str, list[str]] = {
    "Amsterdam": [
        "Centrum",
        "Jordaan",
        "De Pijp",
        "Oud-West",
        "Oud-Zuid",
        "Amsterdam Oost",
        "Amsterdam Noord",
        "Amsterdam West",
        "Amsterdam Zuid",
        "Amsterdam Nieuw-West",
        "Amsterdam Zuidoost",
        "Bos en Lommer",
        "Indische Buurt",
        "Watergraafsmeer",
        "Slotervaart",
    ],
    "Rotterdam": [
        "Centrum",
        "Kralingen",
        "Katendrecht",
        "Delfshaven",
        "Blijdorp",
        "Noord",
        "Hillegersberg",
        "Charlois",
        "Feijenoord",
        "Kop van Zuid",
    ],
    "Utrecht": [
        "Centrum",
        "Lombok",
        "Oudwijk",
        "Wittevrouwen",
        "Oost",
        "Overvecht",
        "Leidsche Rijn",
        "Kanaleneiland",
        "Lunetten",
    ],
    "Den Haag": [
        "Centrum",
        "Scheveningen",
        "Duinoord",
        "Statenkwartier",
        "Bezuidenhout",
        "Laak",
        "Escamp",
        "Segbroek",
    ],
    "Eindhoven": ["Centrum", "Strijp-S", "Woensel", "Tongelre", "Gestel"],
    "Groningen": ["Centrum", "Oosterpoort", "Helpman", "Korreweg", "Paddepoel"],
}

SUPPORTED_CITIES = tuple(NEIGHBORHOODS.keys())


def neighborhoods_for_city(city: str) -> list[str]:
    return list(NEIGHBORHOODS.get(city.strip(), []))
