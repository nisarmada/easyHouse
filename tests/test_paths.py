from __future__ import annotations

import json
from pathlib import Path

from config import paths
from config.load import load_sources
from config.search import load_search


def test_user_data_dir_seeds_config_files() -> None:
    root = paths.ensure_user_data()
    assert root.is_dir()
    assert paths.get_search_path().exists()
    assert paths.get_sources_path().exists()

    search = load_search()
    assert search.city == "Amsterdam"
    sources = load_sources()
    assert len(sources) >= 1


def test_user_data_dir_honors_override(tmp_path: Path) -> None:
    custom = tmp_path / "custom-home"
    paths.set_user_data_dir(custom)
    paths.ensure_user_data()

    assert paths.get_db_path() == custom / "easyhouse.db"
    assert paths.get_notify_path() == custom / "notify.json"


def test_seed_preserves_existing_search(tmp_path: Path) -> None:
    custom = tmp_path / "existing"
    paths.set_user_data_dir(custom)
    config_dir = custom / "config"
    config_dir.mkdir(parents=True)
    search_path = config_dir / "search.json"
    search_path.write_text(json.dumps({"city": "Utrecht", "radius_km": 5}), encoding="utf-8")

    paths.ensure_user_data()
    assert load_search().city == "Utrecht"
