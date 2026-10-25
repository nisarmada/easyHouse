from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from bs4 import BeautifulSoup


def loads_json_ld(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def normalize_json_ld_roots(data: Any) -> list[dict]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def iter_json_ld_nodes(data: Any) -> Iterator[dict]:
    for root in normalize_json_ld_roots(data):
        graph = root.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                if isinstance(node, dict):
                    yield node
            continue
        yield root


def node_types(node: dict) -> list[str]:
    raw = node.get("@type")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [value for value in raw if isinstance(value, str)]
    return []


def iter_json_ld_scripts(html: str) -> Iterator[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        data = loads_json_ld(script.string.strip())
        if data is None:
            continue
        yield from iter_json_ld_nodes(data)
