from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from bs4 import BeautifulSoup


@dataclass
class Listing:
	source: str
	external_id: str
	url: str
	title: str
	price_eur: int | None
	city: str | None = None

def parse_listings(html: str) -> list[Listing]:
	soup = BeautifulSoup(html, "html.parser")
	script = soup.find("script", type="application/ld+json")
	if not script or not script.string:
		return []

	data = json.loads(script.string)
	listings: list[Listing] = []

	for node in data.get("@graph", []):
		types = node.get("@type", [])
		if isinstance(types, str):
			types = [types]
		if "CollectionPage" not in types:
			continue
		
		for entry in node.get("mainEntity", {}).get("itemListElement", []):
			item = entry["item"]
			url = item["url"]
			external_id = url.rstrip("/").split("/")[-2]
			price = item.get("offers", {}).get("price")
			listings.append(
				Listing(
					source="pararius",
					external_id=external_id,
					url=url,
					title=item.get("name", ""),
					price_eur=int(price) if price is not None else None,
					city="Amsterdam",
				)
			)
	return listings

def parse_file(path: str | Path) -> list[Listing]:
	return parse_listings(Path(path).read_text(encoding="utf-8"))
