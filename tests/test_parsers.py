from __future__ import annotations

from scrapers.funda import parse_listings as parse_funda
from scrapers.huurwoningen import has_next_page as huurwoningen_has_next
from scrapers.kamernet import has_next_page as kamernet_has_next
from scrapers.pararius import has_next_page as pararius_has_next, parse_listings as parse_pararius

PARARIUS_HTML = """
<html><head><link rel="next" href="/apartments/amsterdam/page-2"></head>
<body><script type="application/ld+json">{
  "@graph": [{
    "@type": "CollectionPage",
    "mainEntity": {
      "itemListElement": [{
        "item": {
          "url": "https://www.pararius.com/apartment-for-rent/amsterdam/a617ab3b/krammerstraat",
          "name": "Krammerstraat",
          "offers": {"price": 3100}
        }
      }]
    }
  }]
}</script></body></html>
"""

FUNDA_HTML = """
<html><body>
<a href="/detail/huur/amsterdam/appartement-maassluisstraat-60/80934793/" aria-label="Maassluisstraat 60">Maassluisstraat</a>
<script type="application/ld+json">{
  "@type": ["ItemList", "WebPage"],
  "itemListElement": [{
    "url": "https://www.funda.nl/detail/huur/amsterdam/appartement-maassluisstraat-60/80934793/"
  }]
}</script>
</body></html>
"""

KAMERNET_HTML = """
<html><body><script id="__NEXT_DATA__" type="application/json">{
  "props": {
    "pageProps": {
      "targetPageProps": {
        "findListingsResponse": {
          "total": 40,
          "listings": [
            {"listingId": 1, "street": "Street 1", "totalRentalPrice": 900, "citySlug": "amsterdam", "streetSlug": "street-1", "city": "Amsterdam"}
          ]
        }
      }
    }
  }
}</script></body></html>
"""

HUURWONINGEN_HTML = """
<html><head><link rel="next" href="/in/amsterdam/?page=2"></head><body></body></html>
"""


def test_pararius_parse_and_next_page() -> None:
    listings = parse_pararius(PARARIUS_HTML, city="Amsterdam")
    assert len(listings) == 1
    assert listings[0].external_id == "a617ab3b"
    assert listings[0].price_eur == 3100
    assert pararius_has_next(PARARIUS_HTML) is True


def test_funda_merges_cards_and_json_ld() -> None:
    listings = parse_funda(FUNDA_HTML, city="Amsterdam")
    assert len(listings) == 1
    assert listings[0].external_id == "80934793"
    assert listings[0].title == "Maassluisstraat 60"


def test_kamernet_has_next_page() -> None:
    assert kamernet_has_next(KAMERNET_HTML, current_page=1) is True
    assert kamernet_has_next(KAMERNET_HTML, current_page=40) is False


def test_huurwoningen_has_next_page() -> None:
    assert huurwoningen_has_next(HUURWONINGEN_HTML) is True
    assert huurwoningen_has_next("<html></html>") is False
