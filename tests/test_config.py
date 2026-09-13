from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.load import enabled_sources, get_source, load_sources


def test_load_sources(tmp_path: Path) -> None:
    config = tmp_path / "sources.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {"name": "Pararius", "url": "https://www.pararius.com/apartments/amsterdam"},
                    {
                        "name": "Disabled",
                        "url": "https://kamernet.nl/huren/appartement-amsterdam",
                        "enabled": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    sources = load_sources(config)
    assert len(sources) == 2
    assert sources[0].type == "pararius"
    assert sources[0].id == "pararius"

    enabled = enabled_sources(config)
    assert len(enabled) == 1
    assert enabled[0].name == "Pararius"


def test_get_source_unknown(tmp_path: Path) -> None:
    config = tmp_path / "sources.json"
    config.write_text(
        json.dumps({"sources": [{"name": "Pararius", "url": "https://www.pararius.com/apartments/amsterdam"}]}),
        encoding="utf-8",
    )

    source = get_source("pararius", config)
    assert source.name == "Pararius"

    with pytest.raises(ValueError, match="Unknown source"):
        get_source("missing", config)
