from __future__ import annotations

import pytest

from services.agent import AgentConfig
from services.watcher import WatcherConfig, validate_watcher_config


def test_validate_watcher_config_rejects_invalid_poll_range() -> None:
    config = WatcherConfig(poll_min_sec=100, poll_max_sec=50)
    with pytest.raises(ValueError, match="poll_min_sec"):
        validate_watcher_config(config)


def test_agent_config_defaults() -> None:
    config = AgentConfig()
    assert config.host == "127.0.0.1"
    assert config.port == 8080
    assert config.watcher is None
