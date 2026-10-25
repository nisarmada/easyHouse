from __future__ import annotations

import json

from scrapers.funda import parse_listings as parse_funda
from scrapers.housinganywhere import _price_eur_from_item, parse_listings as parse_housinganywhere
from scrapers.js_string import decode_js_string_literal, extract_json_parse_payload
from scrapers.json_ld import iter_json_ld_scripts, loads_json_ld


def test_decode_js_string_literal_preserves_unicode() -> None:
    raw = r"caf\u00e9 \"quoted\""
    assert decode_js_string_literal(raw) == 'café "quoted"'


def test_extract_json_parse_payload() -> None:
    html = r'<script>window.__staticRouterHydrationData = JSON.parse("{\"loaderData\":{\"x\":{\"listings\":[{\"id\":1,\"unitTypePath\":\"/u/1\",\"priceEUR\":1200}],\"pageInfo\":{\"pages\":1}}}}");</script>'
    payload = extract_json_parse_payload(html)
    assert isinstance(payload, dict)
    listings = parse_housinganywhere(html)
    assert len(listings) == 1
    assert listings[0].price_eur == 1200


def test_housinganywhere_price_cents_heuristic() -> None:
    assert _price_eur_from_item({"price": 150000, "priceEUR": None}) == 1500
    assert _price_eur_from_item({"price": 1500, "priceEUR": None}) == 1500
    assert _price_eur_from_item({"price": 150000, "priceInCents": True}) == 1500


def test_loads_json_ld_skips_invalid() -> None:
    assert loads_json_ld("{not json") is None


def test_iter_json_ld_scripts_skips_malformed_and_parses_list_root() -> None:
    html = """
    <script type="application/ld+json">{ broken</script>
    <script type="application/ld+json">[{"@type":"ItemList","itemListElement":[]}]</script>
    """
    nodes = list(iter_json_ld_scripts(html))
    assert len(nodes) == 1
    assert nodes[0]["@type"] == "ItemList"


def test_funda_price_scoped_to_card() -> None:
    html = """
    <html><body>
    <div>
      <a href="/detail/huur/amsterdam/a/111/">Listing A</a>
      <span>€ 1.500 p.m.</span>
      <a href="/detail/huur/amsterdam/b/222/">Listing B</a>
      <span>€ 2.200 p.m.</span>
    </div>
    <script type="application/ld+json">{
      "@type": "ItemList",
      "itemListElement": [
        {"url": "https://www.funda.nl/detail/huur/amsterdam/a/111/"},
        {"url": "https://www.funda.nl/detail/huur/amsterdam/b/222/"}
      ]
    }</script>
    </body></html>
    """
    listings = {item.external_id: item.price_eur for item in parse_funda(html, city="Amsterdam")}
    assert listings["111"] == 1500
    assert listings["222"] == 2200
